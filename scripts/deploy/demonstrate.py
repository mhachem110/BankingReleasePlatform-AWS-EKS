"""Explicitly approved dev-only restart, scaling and failed-upgrade demonstration."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from common import ROOT, config, json_run, run, save_json
from verify import verify

def smoke(namespace):
    run([sys.executable, ROOT / "scripts/deploy/kube-smoke.py", "--namespace", namespace])

def upgrade(namespace, values, *extra):
    return run(["helm", "upgrade", "banking", ROOT / "helm/banking", "-n", namespace,
        "-f", values, "--reset-values", "--wait=watcher", "--rollback-on-failure",
        "--timeout", "10m", *extra], check=False).returncode

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true", help="Requires separate explicit live-test authorization")
    args = p.parse_args()
    if not args.execute:
        print("Pending live approval. Covers Pods, Services, DNS/payment, restart, scale, history, rollback and logs.")
        sys.exit(0)
    cfg = config("dev")
    cluster = json_run(["aws", "eks", "describe-cluster", "--name", cfg["cluster"], "--region", cfg["region"]])["cluster"]
    context = json_run(["kubectl", "config", "view", "--minify", "-o", "json"])
    if cluster["status"] != "ACTIVE" or context["clusters"][0]["cluster"]["server"] != cluster["endpoint"]:
        raise ValueError("Current Kubernetes context is not the approved banking-dev cluster")
    namespace = cfg["namespace"]
    values = json_run(["helm", "get", "values", "banking", "-n", namespace, "-a", "-o", "json"])
    if values["autoscaling"]["enabled"] or values["demonstration"]["enabled"]:
        raise ValueError("Demonstration requires normal fixed-replica deployment")
    manifest = {"images": values["images"]}
    verify(namespace, "banking", manifest)
    evidence = ROOT / "artifacts/application/demonstration"
    evidence.mkdir(parents=True, exist_ok=True)
    mutated = False
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / "original-values.json"
        save_json(snapshot, values)
        try:
            save_json(evidence / "pods-before.json", json_run(["kubectl", "-n", namespace, "get", "pods", "-o", "json"]))
            save_json(evidence / "services.json", json_run(["kubectl", "-n", namespace, "get", "services", "-o", "json"]))
            smoke(namespace)
            before = json_run(["kubectl", "-n", namespace, "get", "pods", "-l", "app=banking-payment", "-o", "json"])
            old_uids = {p["metadata"]["uid"] for p in before["items"]}
            mutated = True
            run(["kubectl", "-n", namespace, "rollout", "restart", "deployment/banking-payment"])
            verify(namespace, "banking", manifest)
            after = json_run(["kubectl", "-n", namespace, "get", "pods", "-l", "app=banking-payment", "-o", "json"])
            new_uids = {p["metadata"]["uid"] for p in after["items"] if not p["metadata"].get("deletionTimestamp")}
            if old_uids & new_uids:
                raise AssertionError("Restart did not replace every Payment Pod")
            smoke(namespace)
            if upgrade(namespace, snapshot, "--set", "replicas.account=3", "--set", "replicas.payment=3"):
                raise RuntimeError("Scaling upgrade failed")
            verify(namespace, "banking", manifest)
            smoke(namespace)
            save_json(evidence / "pods-scaled.json", json_run(["kubectl", "-n", namespace, "get", "pods", "-o", "json"]))
            if upgrade(namespace, snapshot):
                raise RuntimeError("Could not restore replicas")
            before_fault = json_run(["helm", "status", "banking", "-n", namespace, "-o", "json"])["version"]
            # Wrong readiness path leaves old ready Pods serving while upgrade times out.
            if upgrade(namespace, snapshot, "--set", "demonstration.enabled=true",
                       "--set", "demonstration.failPaymentReadiness=true", "--timeout", "6m") == 0:
                raise AssertionError("Injected readiness failure unexpectedly succeeded")
            save_json(evidence / "failure-events.json", json_run(["kubectl", "-n", namespace, "get", "events", "-o", "json"]))
            verify(namespace, "banking", manifest)
            restored = json_run(["helm", "get", "values", "banking", "-n", namespace, "-a", "-o", "json"])
            if restored["images"] != values["images"] or restored["demonstration"] != values["demonstration"]:
                raise AssertionError("Rollback did not restore images and healthy readiness")
            smoke(namespace)
            save_json(evidence / "helm-history.json", json_run(["helm", "history", "banking", "-n", namespace, "-o", "json"]))
            for service in ("account", "payment"):
                logs = run(["kubectl", "-n", namespace, "logs", "deployment/banking-" + service, "--tail=100"], capture=True)
                (evidence / (service + ".log")).write_text(logs)
            save_json(evidence / "result.json", {"status": "passed", "failedFromRevision": before_fault,
                "checks": ["ready-fargate-pods", "services", "payment-account-dns", "restart-recovery",
                           "scale-to-three", "replica-restoration", "failed-readiness-rollback", "history", "logs"]})
        finally:
            if mutated:
                if upgrade(namespace, snapshot):
                    raise RuntimeError("Restore failed; inspect release and roll back manually")
                verify(namespace, "banking", manifest)
                smoke(namespace)
    print("Live demonstration passed; original release configuration restored.")
