"""Package the single source-only handoff; no credentials, generated tfvars or AWS calls."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def export(output):
    paths = [ROOT / "docs/infrastructure" / name for name in
             ("ADMIN-REQUEST.md", "DEPLOYMENT.md", "DATA-DEPLOYMENT.md", "TAGGING.md", "COSTS.md", "PHASE6-OFFLINE.md")]
    paths += sorted((ROOT / "iam/phase3").rglob("*.json"))
    paths += sorted((ROOT / "iam/phase3").rglob("*.md"))
    paths += [ROOT / "scripts/infra" / name for name in
              ("prepare-admin-request.py", "guard.py", "data_iam.py", "data_guard.py", "data_preflight.py", "data_verify.py", "export-irsa-request.py")]
    paths += [ROOT / ".github/workflows/data-operations.yml"]
    paths += [ROOT / "iam/phase3/deployer-verification-rbac.yaml", ROOT / "docs/deployment/DATA-AND-EVENTS.md",
              ROOT / "docs/deployment/monitoring/aws-logging.yaml", ROOT / "docs/deployment/monitoring/prometheus-rbac.yaml"]
    paths = sorted(set(paths))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"sourceCommit":commit, "scope":"One source-only administrator handoff; proposals, not authorization",
                "credentialsIncluded":False, "files":{}}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(relative, data)
            manifest["files"][relative] = hashlib.sha256(data).hexdigest()
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    print(json.dumps({"package":str(output), "sourceCommit":commit, "files":len(paths),
                      "sha256":hashlib.sha256(output.read_bytes()).hexdigest(), "liveAws":False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/administrator-handoff/Banking-Consolidated-Administrator-Handoff.zip")
    export(parser.parse_args().output)
