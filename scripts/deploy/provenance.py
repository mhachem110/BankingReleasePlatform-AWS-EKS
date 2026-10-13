"""Accept artifacts only from successful reviewed-dev publication runs."""
import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from common import predecessor, release_mode, REPOSITORY, ROOT, config, json_run, run, save_json, validate_manifest

def validate_run(run_info, *, workflow, branch, commit=None):
    if (run_info.get("status") != "completed" or run_info.get("conclusion") != "success"
        or run_info.get("event") != "workflow_dispatch" or run_info.get("head_branch") != branch
        or run_info.get("path") != ".github/workflows/" + workflow
        or run_info.get("repository", {}).get("full_name") != REPOSITORY
        or (commit and run_info.get("head_sha") != commit)):
        raise ValueError("Artifact source is not a successful trusted workflow run")

def obtain(run_id, name, directory):
    if not re.fullmatch(r"[1-9][0-9]*", str(run_id)):
        raise ValueError("Run ID must be numeric")
    run(["gh", "run", "download", str(run_id), "--repo", REPOSITORY,
         "--name", name, "--dir", directory])

def manifest_hash(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def deployment_receipt(environment, manifest, commit, run_id):
    if release_mode() != "shared-cluster-demo":
        return {"environment": environment, "manifestHash": manifest_hash(manifest),
                "publishRunId": manifest["publishRunId"]}
    if environment not in {"dev", "prod"} or not re.fullmatch(r"[a-f0-9]{40}", str(commit)) or not re.fullmatch(r"[1-9][0-9]*", str(run_id)):
        raise ValueError("Actual deployment commit/run required for demonstration evidence")
    return {"version": 2, "environment": environment, "cluster": "banking-dev",
            "namespace": "banking-" + environment, "releaseMode": "shared-cluster-demo",
            "sourceCommit": manifest["sourceCommit"], "deploymentCommit": commit, "runId": str(run_id),
            "manifestHash": manifest_hash(manifest), "publishRunId": manifest["publishRunId"]}

def verify_publication(manifest):
    info = json_run(["gh", "api", f"repos/{REPOSITORY}/actions/runs/{manifest['publishRunId']}"])
    # Keep receipts from the original publisher valid. New publication is an
    # App CD operation; the reusable child retains the same immutable manifest.
    workflow = info.get("path", "").removeprefix(".github/workflows/")
    if workflow not in {"app-publish.yml", "app-deploy.yml"}:
        raise ValueError("Publication must originate from the reviewed application publisher")
    validate_run(info, workflow=workflow, branch="dev", commit=manifest["sourceCommit"])
    run(["git", "merge-base", "--is-ancestor", manifest["sourceCommit"], "HEAD"], cwd=ROOT)

def verify_previous(environment, manifest):
    previous = predecessor(environment)
    if previous is None:
        return
    branch = {"prod":"main"}.get(previous, previous)
    # Bounded, fail-closed search. Retain evidence artifacts across the promotion window.
    runs = json_run(["gh", "api", f"repos/{REPOSITORY}/actions/workflows/app-deploy.yml/runs?branch={branch}&status=success&per_page=100"])["workflow_runs"]
    for info in runs:
        try:
            validate_run(info, workflow="app-deploy.yml", branch=branch)
        except ValueError:
            continue
        artifacts = json_run(["gh", "api", f"repos/{REPOSITORY}/actions/runs/{info['id']}/artifacts"])["artifacts"]
        name = f"deployment-{previous}-{manifest['publishRunId']}"
        if not any(a["name"] == name and not a["expired"] for a in artifacts):
            continue
        with tempfile.TemporaryDirectory() as directory:
            obtain(info["id"], name, directory)
            evidence = json.loads((Path(directory) / "deployment.json").read_text())
            if evidence == deployment_receipt(previous, manifest, info.get("head_sha"), info["id"]):
                return
    raise ValueError("No successful predecessor deployment with the exact digest pair and reviewed release mode")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--environment", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--output", default="release/release.json")
    args = p.parse_args()
    if args.run_id < 1:
        raise ValueError("Positive publication run ID required")
    cfg = config(args.environment)
    with tempfile.TemporaryDirectory() as directory:
        obtain(args.run_id, "release-manifest", directory)
        manifest = validate_manifest(json.loads((Path(directory) / "release.json").read_text()), cfg["repos"])
    if manifest["publishRunId"] != str(args.run_id):
        raise ValueError("Publication run does not match manifest")
    verify_publication(manifest)
    verify_previous(args.environment, manifest)
    save_json(args.output, manifest)
    print("Publication provenance, branch ancestry and reviewed promotion evidence passed.")
