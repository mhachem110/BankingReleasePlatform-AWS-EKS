"""Inventory and remove only the two Banking releases and their bootstrap objects."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ACCOUNT = "866934333672"
NAMESPACES = ("banking-dev", "banking-prod")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(*args, timeout=180):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Kubernetes cleanup command failed: " + " ".join(args[:3]))
    return result.stdout


def preflight(operation):
    require(os.environ.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and
            os.environ.get("GITHUB_REF") == "refs/heads/dev" and
            os.environ.get("CLEANUP_ENABLED") == "true" and
            os.environ.get("AWS_OPERATIONS_ENABLED") == "false", "Protected cleanup window required")
    require(os.environ.get("AWS_REGION") == "us-east-2" and
            os.environ.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and
            os.environ.get("TARGET") == "applications", "Wrong account/Region/target")
    if operation == "apply":
        require(os.environ.get("APPROVAL") == "DESTROY-REVIEWED-BANKING-APPLICATIONS",
                "Exact application cleanup phrase required")
    identity = json.loads(run("aws", "sts", "get-caller-identity", "--output", "json"))
    require(identity.get("Account") == ACCOUNT and "assumed-role/cloudbatch818-mahmoud-banking-operator/" in identity.get("Arn", ""),
            "Only the approved Banking operator may remove Kubernetes resources")


def inventory():
    result = {"account": ACCOUNT, "cluster": "banking-dev", "namespaces": {}, "controller": None}
    for namespace in NAMESPACES:
        item = json.loads(run("kubectl", "get", "namespace", namespace, "-o", "json"))
        labels = item["metadata"].get("labels", {})
        require(labels.get("app.kubernetes.io/part-of") == "banking" and
                labels.get("banking.example/environment") == namespace.removeprefix("banking-"),
                "Namespace ownership changed")
        releases = json.loads(run("helm", "list", "-n", namespace, "--all", "-o", "json"))
        require({r["name"] for r in releases} <= {"banking"}, "Unrelated Helm release in namespace")
        ingress = json.loads(run("kubectl", "get", "ingress", "-n", namespace, "-o", "json"))["items"]
        require({r["metadata"]["name"] for r in ingress} <= {"banking"}, "Unrelated ingress in namespace")
        objects = json.loads(run("kubectl", "get",
                                 "all,serviceaccounts,secrets,configmaps,roles,rolebindings,resourcequotas,networkpolicies,poddisruptionbudgets,horizontalpodautoscalers,ingresses",
                                 "-n", namespace, "-o", "json"))["items"]
        for obj in objects:
            name = obj["metadata"]["name"]
            labels = obj["metadata"].get("labels", {})
            if name in {"default", "kube-root-ca.crt", "banking-release", "banking-release-capacity",
                        "banking-account-db", "banking-payment-db", "banking-rds-ca"}:
                continue
            if name.startswith("sh.helm.release.v1.banking.v") and obj["kind"] == "Secret":
                continue
            require(labels.get("app.kubernetes.io/part-of") == "banking" and
                    labels.get("banking.example/environment") == namespace.removeprefix("banking-"),
                    "Unrelated namespaced object would be deleted: " + obj["kind"] + "/" + name)
        result["namespaces"][namespace] = {"uid": item["metadata"]["uid"],
                                            "helm": [r["name"] for r in releases],
                                            "ingress": [r["metadata"]["name"] for r in ingress],
                                            "objects": sorted(obj["kind"] + "/" + obj["metadata"]["name"] for obj in objects)}
    controller = json.loads(run("helm", "list", "-n", "kube-system", "--all", "--filter",
                                "^aws-load-balancer-controller$", "-o", "json"))
    require(len(controller) <= 1, "Unexpected controller release inventory")
    result["controller"] = "aws-load-balancer-controller" if controller else None
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_absent():
    for namespace in NAMESPACES:
        result = subprocess.run(["kubectl", "get", "namespace", namespace, "-o", "json"],
                                capture_output=True, text=True, timeout=60)
        require(result.returncode != 0 and "NotFound" in result.stderr, "Namespace still exists: " + namespace)
    result = json.loads(run("helm", "list", "-n", "kube-system", "--all", "--filter",
                            "^aws-load-balancer-controller$", "-o", "json"))
    require(not result, "ALB controller Helm release remains")
    for kind in ("clusterrole", "clusterrolebinding"):
        for name in ("banking-release-verifier-dev", "banking-release-verifier-prod"):
            result = subprocess.run(["kubectl", "get", kind, name], capture_output=True, text=True)
            require(result.returncode != 0 and "NotFound" in result.stderr, "Cluster RBAC remains")
    for kind, name, namespace in (("serviceaccount", "aws-load-balancer-controller", "kube-system"),
                                  ("namespace", "aws-observability", None)):
        command = ["kubectl", "get", kind, name]
        if namespace:
            command.extend(["-n", namespace])
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        require(result.returncode != 0 and "NotFound" in result.stderr,
                "Project Kubernetes bootstrap resource remains: " + kind + "/" + name)
    return {"account": ACCOUNT, "cluster": "banking-dev", "workloads_removed": True,
            "load_balancers_removed": False, "verified": False,
            "run_id": os.environ.get("GITHUB_RUN_ID"), "commit": os.environ.get("GITHUB_SHA")}


if __name__ == "__main__":
    operation = os.environ["OPERATION"]
    preflight(operation)
    if operation == "plan":
        record = inventory()
        Path("kubernetes-cleanup-plan.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record, indent=2))
    else:
        reviewed = json.loads(Path("reviewed/kubernetes-cleanup-plan.json").read_text())
        require(digest(reviewed) == os.environ.get("REVIEWED_DIGEST"), "Reviewed inventory digest changed")
        require(inventory() == reviewed, "Kubernetes inventory changed since review")
        for namespace in NAMESPACES:
            if "banking" in reviewed["namespaces"][namespace]["helm"]:
                run("helm", "uninstall", "banking", "-n", namespace, "--wait", "--timeout", "10m", timeout=900)
        if reviewed["controller"]:
            run("helm", "uninstall", "aws-load-balancer-controller", "-n", "kube-system",
                "--wait", "--timeout", "10m", timeout=900)
        for namespace in NAMESPACES:
            run("kubectl", "delete", "namespace", namespace, "--wait=true", "--timeout=10m", timeout=900)
        for name in ("banking-release-verifier-dev", "banking-release-verifier-prod"):
            run("kubectl", "delete", "clusterrolebinding", name, "--ignore-not-found")
            run("kubectl", "delete", "clusterrole", name, "--ignore-not-found")
        run("kubectl", "delete", "serviceaccount", "aws-load-balancer-controller", "-n", "kube-system", "--ignore-not-found")
        run("kubectl", "delete", "namespace", "aws-observability", "--ignore-not-found", "--wait=true", timeout=900)
        Path("kubernetes-cleanup-verification.json").write_text(json.dumps(verify_absent(), indent=2))
