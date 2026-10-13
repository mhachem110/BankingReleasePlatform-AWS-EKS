"""Restore a previously successful release in one protected namespace.

The target comes from a trusted deployment receipt and publication manifest.
An arbitrary image, Helm values file or cross-environment revision is rejected.
This restores application code; it does not reverse database migrations/payments.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from common import ROOT, ROUTES, REPOSITORY, config, json_run, run, save_json, validate_manifest
from provenance import deployment_receipt, obtain, validate_run, verify_publication
from isolation import verify_access
from verify import verify


def approved_release(environment, deployment_run_id):
    cfg = config(environment)
    if not re.fullmatch(r"[1-9][0-9]*", deployment_run_id):
        raise ValueError("A successful deployment run ID is required")
    info = json_run(["gh", "api", f"repos/{REPOSITORY}/actions/runs/{deployment_run_id}"])
    validate_run(info, workflow="app-deploy.yml", branch=ROUTES[environment])
    artifacts = json_run(["gh", "api", f"repos/{REPOSITORY}/actions/runs/{deployment_run_id}/artifacts"])["artifacts"]
    candidates = [a for a in artifacts if not a["expired"] and
                  re.fullmatch(r"deployment-" + environment + r"-[1-9][0-9]*", a["name"])]
    if len(candidates) != 1:
        raise ValueError("Exactly one retained successful deployment receipt is required")
    with tempfile.TemporaryDirectory() as directory:
        obtain(deployment_run_id, candidates[0]["name"], directory)
        receipt = json.loads((Path(directory) / "deployment.json").read_text())
        publication = str(receipt["publishRunId"])
        manifest_dir = Path(directory) / "publication"
        obtain(publication, "release-manifest", manifest_dir)
        manifest = validate_manifest(json.loads((manifest_dir / "release.json").read_text()), cfg["repos"])
    if candidates[0]["name"] != f"deployment-{environment}-{publication}" or receipt != deployment_receipt(
            environment, manifest, info["head_sha"], info["id"]):
        raise ValueError("Deployment receipt does not bind the selected digest pair/environment")
    verify_publication(manifest)
    return cfg, manifest


def rollback(environment, revision, manifest):
    cfg = config(environment)
    if revision < 1:
        raise ValueError("A positive Helm revision is required")
    identity = json_run(["aws", "sts", "get-caller-identity"])
    if identity["Account"] != cfg["account"]:
        raise ValueError("Wrong rollback account")
    with tempfile.TemporaryDirectory() as directory:
        os.environ["KUBECONFIG"] = str(Path(directory) / "kubeconfig")
        run(["aws", "eks", "update-kubeconfig", "--name", cfg["cluster"], "--region", cfg["region"]])
        verify_access(cfg["namespace"])
        history = json_run(["helm", "history", "banking", "-n", cfg["namespace"], "-o", "json"])
        selected = [r for r in history if int(r["revision"]) == revision and r["status"] in {"deployed", "superseded"}]
        if len(selected) != 1:
            raise ValueError("Target must be a retained successful Helm revision")
        # Capture only in memory: Helm values can contain sensitive references.
        values = json_run(["helm", "get", "values", "banking", "-n", cfg["namespace"],
                           "--revision", str(revision), "-o", "json"])
        if values.get("images") != manifest["images"]:
            raise ValueError("Revision images do not match the approved deployment receipt")
        run(["helm", "rollback", "banking", str(revision), "-n", cfg["namespace"],
             "--wait", "--timeout", "10m", "--cleanup-on-fail"])
        verify(cfg["namespace"], "banking", manifest)
        # Readiness alone is insufficient: verify Account/Payment communication
        # before publishing a successful recovery receipt.
        run([sys.executable, ROOT / "scripts/deploy/kube-smoke.py", "--namespace",
             cfg["namespace"], "--release", "banking"])
    save_json("release/rollback.json", {"environment": environment, "namespace": cfg["namespace"],
        "restoredRevision": revision, "publishRunId": manifest["publishRunId"],
        "images": manifest["images"], "runId": os.environ["GITHUB_RUN_ID"], "verified": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "restore"])
    parser.add_argument("--environment", required=True, choices=list(ROUTES))
    parser.add_argument("--deployment-run-id", required=True)
    parser.add_argument("--revision", required=True, type=int)
    args = parser.parse_args()
    if args.revision < 1:
        raise ValueError("A positive Helm revision is required")
    _, manifest = approved_release(args.environment, args.deployment_run_id)
    if args.command == "prepare":
        save_json("release/rollback-release.json", manifest)
    else:
        rollback(args.environment, args.revision, manifest)
