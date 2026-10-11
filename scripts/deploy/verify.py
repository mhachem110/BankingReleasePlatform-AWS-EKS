"""Rollout, ready Pod, Fargate node and exact-digest verification."""
from common import json_run, run

def verify(namespace, release, manifest):
    for service in ("account", "payment"):
        name = release + "-" + service
        run(["kubectl", "-n", namespace, "rollout", "status", "deployment/" + name, "--timeout=600s"])
        deployment = json_run(["kubectl", "-n", namespace, "get", "deployment", name, "-o", "json"])
        expected = manifest["images"][service]["repository"] + "@" + manifest["images"][service]["digest"]
        if deployment["spec"]["template"]["spec"]["containers"][0]["image"] != expected:
            raise ValueError("Deployment digest mismatch")
        replicas = deployment["spec"]["replicas"]
        if replicas < 1 or deployment["status"].get("readyReplicas", 0) != replicas:
            raise ValueError("Not all replicas are ready")
        pods = json_run(["kubectl", "-n", namespace, "get", "pods", "-l", "app=" + name, "-o", "json"])["items"]
        active = [p for p in pods if not p["metadata"].get("deletionTimestamp")]
        if len(active) != replicas:
            raise ValueError("Replica count mismatch")
        for pod in active:
            ready = any(c["type"] == "Ready" and c["status"] == "True" for c in pod["status"].get("conditions", []))
            if pod["status"]["phase"] != "Running" or not ready:
                raise ValueError("Unhealthy Pod")
            if pod["spec"]["containers"][0]["image"] != expected:
                raise ValueError("Pod digest mismatch")
            statuses = pod["status"].get("containerStatuses", [])
            if not statuses or not all(s.get("ready") and s.get("imageID") for s in statuses):
                raise ValueError("Container runtime has not verified image readiness")
            node = json_run(["kubectl", "get", "node", pod["spec"]["nodeName"], "-o", "json"])
            if node["metadata"]["labels"].get("eks.amazonaws.com/compute-type") != "fargate":
                raise ValueError("Application Pod is not running on Fargate")
        if service == "payment":
            env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
            expected_dns = f"http://{release}-account.{namespace}.svc.cluster.local:8080/"
            if {"name": "AccountApi__BaseUrl", "value": expected_dns} not in env:
                raise ValueError("Payment dependency is not Kubernetes DNS")
    print("PASS: exact digests, desired replicas, ready Pods and Fargate nodes")
