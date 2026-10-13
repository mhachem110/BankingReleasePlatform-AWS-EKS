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
             ("SINGLE-PROVISIONER.md", "ADMIN-REQUEST.md", "READINESS-2026-10-12.md", "DEPLOYMENT.md", "DATA-DEPLOYMENT.md", "TAGGING.md", "COSTS.md", "PHASE6-OFFLINE.md", "SHARED-CLUSTER.md", "RESOURCE-INVENTORY.md", "cost-model.json", "shared-demo-prices.json")]
    paths += sorted((ROOT / "iam/provisioning").rglob("*.json"))
    paths += [ROOT / "iam/provisioning/README.md"]
    paths += sorted((ROOT / "infra/iam-prerequisites").glob("*.tf"))
    paths += [p for p in (ROOT / "infra").rglob("*") if p.is_file() and ".terraform" not in p.parts and
              (p.suffix == ".tf" or p.name.endswith((".tftest.hcl", ".tfvars.example", ".tfbackend.example")) or p.name == ".terraform.lock.hcl")]
    paths += [ROOT / "infra/iam-prerequisites/.terraform.lock.hcl", ROOT / "infra/backend/iam-prerequisites.s3.tfbackend.example", ROOT / ".github/workflows/iam-prerequisites.yml", ROOT / ".github/workflows/network-prerequisites.yml", ROOT / ".github/workflows/infra-operations.yml"]
    paths += [ROOT / "scripts/infra" / name for name in ("network_seed.py", "iam_contract.py", "iam_guard.py", "audit-bootstrap-role.py", "platform_caps.py", "provisioner_policies.py", "validate-provisioner-policies.py", "preflight.py", "plan-audit.py", "write-backend.py", "requirements.txt")]
    paths += sorted((ROOT / "iam/phase3").rglob("*.json"))
    paths += sorted((ROOT / "iam/phase3").rglob("*.md"))
    paths += [ROOT / "scripts/infra" / name for name in
              ("prepare-admin-request.py", "guard.py", "data_iam.py", "data_guard.py", "data_preflight.py", "data_verify.py", "export-irsa-request.py", "audit-deployment-roles.py", "inspect-prerequisites.py", "reconcile-evidence.py", "shared-demo-cost.py", "capacity-review.py")]
    paths += [ROOT / ".github/workflows/data-operations.yml", ROOT / ".github/workflows/verify-prerequisites.yml"]
    paths += [ROOT / "helm/banking/namespaces" / (name + ".yaml") for name in ("banking-dev", "banking-prod")]
    paths += sorted((ROOT / "infra/environments/prod/data").glob("*.tf"))
    paths += [ROOT / "docs/infrastructure/ACCEPTANCE.md"]
    paths += [ROOT / "iam/phase3/deployer-verification-rbac.yaml", ROOT / "docs/deployment/DATA-AND-EVENTS.md",
              ROOT / "docs/deployment/monitoring/aws-logging.yaml", ROOT / "docs/deployment/monitoring/prometheus-rbac.yaml",
              ROOT / "docs/deployment/monitoring/prod-prometheus-rbac.yaml", ROOT / "docs/deployment/monitoring/prod-prometheus.yml"]
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
