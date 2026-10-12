"""Protected Helm transaction; failed smoke tests restore the previous revision."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from common import ROOT, config, helm_values, json_run, run, save_json, validate_manifest
from provenance import manifest_hash, verify_previous, verify_publication
from verify import verify

def previous_revision(namespace, release):
    releases = json_run(["helm", "list", "-n", namespace, "--all", "--filter", "^" + release + "$", "-o", "json"])
    if not releases:
        return None
    status = json_run(["helm", "status", release, "-n", namespace, "-o", "json"])
    if status["info"]["status"] != "deployed":
        raise ValueError("Existing release is not deployed; inspect/recover it before a new deployment")
    return status["version"]

def transaction(namespace, release, values, environment, manifest, *, command=run, revision=None):
    arguments = ["helm", "upgrade", "--install", release, ROOT / "helm/banking",
        "-n", namespace, "-f", ROOT / "helm/banking/environments" / (environment + ".yaml"),
        "-f", values, "--reset-values", "--rollback-on-failure", "--wait=watcher",
        "--timeout", "10m", "--history-max", "10"]
    try:
        command(arguments)
        verify(namespace, release, manifest)
        command([sys.executable, ROOT / "scripts/deploy/kube-smoke.py", "--namespace", namespace, "--release", release])
    except Exception:
        # Collect evidence before rollback; diagnostics must not hide the original error.
        for args in [
            ["kubectl", "-n", namespace, "get", "pods,services,deployments", "-o", "wide"],
            ["kubectl", "-n", namespace, "get", "events", "--sort-by=.lastTimestamp"],
            ["helm", "history", release, "-n", namespace, "-o", "json"],
            *[["kubectl", "-n", namespace, "logs", "deployment/" + release + "-" + s,
               "--all-containers", "--tail=100"] for s in ("account", "payment")]]:
            try:
                command(args, check=False)
            except Exception as error:
                print("Diagnostic unavailable:", error)
        if revision is not None:
            command(["helm", "rollback", release, str(revision), "-n", namespace, "--wait", "--timeout", "10m"])
            old_values = json.loads(command(["helm", "get", "values", release, "-n", namespace, "-o", "json"], capture=True))
            verify(namespace, release, {"images": old_values["images"]})
            command([sys.executable, ROOT / "scripts/deploy/kube-smoke.py", "--namespace", namespace, "--release", release])
        else:
            # Helm 4 rollback-on-failure removes failed installs; smoke failure after
            # a successful first install needs explicit release cleanup.
            command(["helm", "uninstall", release, "-n", namespace, "--ignore-not-found", "--wait"], check=False)
        raise

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--environment", required=True)
    p.add_argument("--manifest", default="release/release.json")
    args = p.parse_args()
    cfg = config(args.environment)
    manifest = validate_manifest(json.loads(Path(args.manifest).read_text()), cfg["repos"])
    # Recheck provenance immediately before mutation, after the remote security scan.
    verify_publication(manifest)
    verify_previous(args.environment, manifest)
    identity = json_run(["aws", "sts", "get-caller-identity"])
    if identity["Account"] != cfg["account"]:
        raise ValueError("Unexpected AWS identity")
    cluster = json_run(["aws", "eks", "describe-cluster", "--name", cfg["cluster"],
                        "--region", cfg["region"]])["cluster"]
    if cluster["status"] != "ACTIVE":
        raise ValueError("EKS cluster is not ACTIVE")
    if run(["helm", "version", "--template", "{{.Version}}"], capture=True).split(".")[0] != "v4":
        raise ValueError("Use the pinned Helm 4 tool")
    with tempfile.TemporaryDirectory() as directory:
        os.environ["KUBECONFIG"] = str(Path(directory) / "kubeconfig")
        run(["aws", "eks", "update-kubeconfig", "--name", cfg["cluster"], "--region", cfg["region"]])
        run(["kubectl", "get", "namespace", cfg["namespace"]])
        revision = previous_revision(cfg["namespace"], "banking")
        values = Path(directory) / "images.json"
        save_json(values, helm_values(manifest))
        run(["helm", "lint", ROOT / "helm/banking", "--strict", "-f", values])
        transaction(cfg["namespace"], "banking", values, args.environment, manifest, revision=revision)
        run(["helm", "history", "banking", "-n", cfg["namespace"]])
    save_json("release/deployment.json", {"environment": args.environment,
        "manifestHash": manifest_hash(manifest), "publishRunId": manifest["publishRunId"]})
    print("Deployment, Fargate rollout verification and integration smoke succeeded.")
