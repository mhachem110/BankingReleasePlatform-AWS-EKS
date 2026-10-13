"""Validate GitHub metadata only; never import, build or execute PR-provided code."""
import json
import os
import re
import urllib.request
from pathlib import PurePosixPath

# Verified GitHub user ID, not an AWS account ID. Changes require a security PR.
CLOUD_OWNER_IDS = frozenset({150286776})
ROUTES = {
    "dev": frozenset({"feature/app", "bootstrap", "infra"}),
    "stage": frozenset({"dev"}),
    "uat": frozenset({"stage"}),
    "main": frozenset({"uat"}),
}
APP_PREFIXES = ("apps/",)
APP_FILES = frozenset({
    "README.md", ".dockerignore", "compose.yaml", "compose.yml",
    "BankingReleasePlatform.sln", "Directory.Build.props", "global.json",
    "scripts/smoke-test.ps1", "scripts/test-local.ps1",
})
# Owner-authored application release changes only; shared cloud ownership remains.
APP_RELEASE_PREFIXES = ("helm/banking/", "scripts/deploy/")
APP_RELEASE_FILES = frozenset({
    ".github/workflows/app-ci.yml", ".github/workflows/app-validation.yml",
    ".github/workflows/app-publish.yml", ".github/workflows/app-deploy.yml",
})
BOOTSTRAP_PREFIXES = (
    "infra/bootstrap/", "infra/backend/", "infra/modules/state-bucket/",
    "scripts/bootstrap/", "infra/iam/bootstrap/", "policies/bootstrap/",
)
BOOTSTRAP_FILES = frozenset({
    "README.md", ".gitignore", ".github/workflows/terraform-operations.yml",
    ".github/workflows/terraform-validation.yml",
    "infra/environments/dev/main.tf", "infra/environments/dev/.terraform.lock.hcl",
})
CLOUD_PREFIXES = (
    "infra/", "helm/", ".github/", "scripts/bootstrap/", "scripts/infra/",
    "scripts/deploy/", "scripts/governance/", "policies/",
    "config/aws/", "config/iam/",
)
CLOUD_FILES = frozenset({"AGENTS.md", ".gitignore", "scripts/README.md"})
# Exact legacy documentation paths retained here only so infra PRs can move or
# retire these historical files. A wildcard docs/ exception would weaken the
# fail-closed path policy for future application and infrastructure changes.
LEGACY_DOC_PATHS = frozenset({
    "docs/architecture.md", "docs/assignment-requirements.md",
    "docs/deployment/ARCHITECTURE.md", "docs/deployment/CHAT1-REQUIREMENTS.md",
    "docs/deployment/DATA-AND-EVENTS.md", "docs/deployment/DEMO-PRESENTATION.md",
    "docs/deployment/ENVIRONMENT.md", "docs/deployment/INCIDENTS.md",
    "docs/deployment/offline-evidence.json", "docs/deployment/PHASE6-OFFLINE-REPORT.md",
    "docs/deployment/README.md", "docs/deployment/REPORT.md", "docs/deployment/RUNBOOK.md",
    "docs/governance/security-verification.md", "docs/governance/security.md",
    "docs/infrastructure/ACCEPTANCE.md", "docs/infrastructure/ADMIN-REQUEST.md",
    "docs/infrastructure/ARCHITECTURE.md", "docs/infrastructure/ASSIGNMENT-MAPPING.md",
    "docs/infrastructure/CLEANUP.md", "docs/infrastructure/COSTS.md",
    "docs/infrastructure/DATA-DEPLOYMENT.md", "docs/infrastructure/DEPLOYMENT.md",
    "docs/infrastructure/FINAL-INTEGRATION.md", "docs/infrastructure/INDEX.md",
    "docs/infrastructure/INTERFACE.md", "docs/infrastructure/PHASE6-OFFLINE.md",
    "docs/infrastructure/PIPELINE-PRESENTATION.md", "docs/infrastructure/POLICY-PREREQUISITES.md",
    "docs/infrastructure/PREPARATION-REPORT.md", "docs/infrastructure/PROJECT-PIPELINE.md",
    "docs/infrastructure/READINESS-2026-10-12.md", "docs/infrastructure/RECONCILIATION.md",
    "docs/infrastructure/REFERENCE-IAM-REVIEW.md", "docs/infrastructure/REPORT.md",
    "docs/infrastructure/REQUIREMENTS.md", "docs/infrastructure/RESOURCE-INVENTORY.md",
    "docs/infrastructure/RUNTIME-FOUNDATION.md", "docs/infrastructure/SHARED-CLUSTER.md",
    "docs/infrastructure/SINGLE-PROVISIONER.md", "docs/infrastructure/TAGGING.md",
    "docs/infrastructure/VPC-OIDC-TEST.md", "docs/phase-1-pr.md", "docs/phase-1-report.md",
    "docs/phase2/BOOTSTRAP.md", "docs/phase2/COMPLETION.md", "docs/phase2/IAM.md",
    "docs/phase2/REPORT.md", "docs/reference-project-review.md",
})
MAX_FILES = 3000  # GitHub's list-files endpoint limit; reject larger PRs.


class PolicyError(ValueError):
    pass


def validate_path(path):
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        raise PolicyError("Invalid repository-relative path.")
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise PolicyError("Non-canonical path rejected.")
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise PolicyError("Control characters in paths are rejected.")
    return path


def forbidden_artifact(path):
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    return (
        any(part.lower() in {".terraform", "bin", "obj", "__pycache__"} for part in parts)
        or name == ".env" or name.startswith(".env.") and name != ".env.example"
        or bool(re.search(r"\.tfstate(?:\.|$)", name))
        or name.endswith((".tfplan", ".tfvars", ".tfvars.json", ".tfbackend", ".tfbackend.json",
                          ".pem", ".key", ".pfx", ".dll", ".exe", ".pyc"))
        or name in {"backend_override.tf", "credentials", "credentials.json"}
    )


def cloud_owned(path):
    name = PurePosixPath(path).name
    return (
        path.startswith(CLOUD_PREFIXES) or path in CLOUD_FILES or path in LEGACY_DOC_PATHS
        or name == "CODEOWNERS" or name.endswith((".tf", ".tf.json", ".hcl"))
        or ".tfvars" in name or ".tfbackend" in name
    )


def application_release_path(path):
    name = PurePosixPath(path).name
    sensitive = name == "CODEOWNERS" or name.endswith((".tf", ".tf.json", ".hcl")) or ".tfvars" in name or ".tfbackend" in name
    return not sensitive and (path.startswith(APP_RELEASE_PREFIXES) or path in APP_RELEASE_FILES)


def application_path(path):
    if application_release_path(path):
        return True
    if cloud_owned(path):
        return False
    name = PurePosixPath(path).name
    root_docker = "/" not in path and (name.startswith("Dockerfile") or
        name.startswith("docker-compose") and name.endswith((".yaml", ".yml")))
    return path.startswith(APP_PREFIXES) or path in APP_FILES or root_docker


def changed_paths(files):
    result = set()
    for file in files:
        if not isinstance(file, dict) or "filename" not in file:
            raise PolicyError("Malformed file metadata.")
        if file.get("status") == "renamed" and not file.get("previous_filename"):
            raise PolicyError("Rename metadata must include the original path.")
        result.add(validate_path(file["filename"]))
        if "previous_filename" in file:
            result.add(validate_path(file["previous_filename"]))
    return sorted(result)


def validate(pr, files, repository):
    head, base = pr["head"], pr["base"]
    if head.get("repo", {}).get("full_name") != repository or base.get("repo", {}).get("full_name") != repository:
        raise PolicyError("Only same-repository working branches and promotions are allowed.")
    source, destination = head["ref"], base["ref"]
    if source not in ROUTES.get(destination, frozenset()):
        raise PolicyError("Source/destination route is not authorized.")
    count = pr.get("changed_files")
    if not isinstance(count, int) or count < 1 or count > MAX_FILES or count != len(files):
        raise PolicyError("Missing, truncated or excessive changed-file list; split/retry the PR.")
    paths = changed_paths(files)
    if any(forbidden_artifact(path) for path in paths):
        raise PolicyError("Generated artifacts, private key material or real backend/state inputs are forbidden.")
    cloud_author = pr.get("user", {}).get("id") in CLOUD_OWNER_IDS
    if destination != "dev":
        if not cloud_author:
            raise PolicyError("Promotion PRs must be authored by an authorized cloud engineer.")
        return paths
    if source == "feature/app":
        if any(application_release_path(path) for path in paths) and not cloud_author:
            raise PolicyError("Application release paths require an authorized cloud-owner author.")
        denied = [path for path in paths if not application_path(path)]
        if denied:
            raise PolicyError("Application PR contains cloud/unknown paths: " + json.dumps(denied))
    elif source == "bootstrap":
        if not cloud_author:
            raise PolicyError("Bootstrap PR must be authored by an authorized cloud engineer.")
        denied = [path for path in paths if not (path.startswith(BOOTSTRAP_PREFIXES) or path in BOOTSTRAP_FILES)]
        if denied:
            raise PolicyError("Bootstrap PR contains paths outside its scope: " + json.dumps(denied))
    else:
        if not cloud_author:
            raise PolicyError("Infrastructure PR must be authored by an authorized cloud engineer.")
        # Cloud engineers may make reviewed cross-cutting application edits here.
        denied = [path for path in paths if not (cloud_owned(path) or application_path(path))]
        if denied or not any(cloud_owned(path) for path in paths):
            raise PolicyError("Infra PR requires a cloud-owned change and no unknown paths: " + json.dumps(denied))
    return paths


def api_get(repository, suffix):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise PolicyError("Invalid repository identity.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{suffix}",
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "BankingReleasePlatform-PathPolicy"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def snapshot(pr):
    return pr["head"]["sha"], pr["base"]["sha"], pr["base"]["ref"], pr["head"]["ref"]


def collect(repository, number, expected_head, getter=api_get):
    if not str(number).isdigit() or int(number) < 1:
        raise PolicyError("Invalid PR number.")
    suffix = f"pulls/{int(number)}"
    pr = getter(repository, suffix)
    if pr["head"]["sha"] != expected_head:
        raise PolicyError("PR head changed before validation; rerun on the current commit.")
    count = pr.get("changed_files")
    if not isinstance(count, int) or not 1 <= count <= MAX_FILES:
        raise PolicyError("PR exceeds supported file-list size or contains no changes.")
    files = []
    for page in range(1, (count + 99) // 100 + 1):
        batch = getter(repository, suffix + f"/files?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise PolicyError("Invalid file-list response.")
        files.extend(batch)
    after = getter(repository, suffix)
    if snapshot(pr) != snapshot(after) or pr["changed_files"] != after["changed_files"]:
        raise PolicyError("PR changed during validation; rerun the check.")
    if len(files) != count:
        raise PolicyError("GitHub returned an incomplete file list; fail closed.")
    return pr, files


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    pr, files = collect(repository, os.environ["PR_NUMBER"], os.environ["PR_HEAD_SHA"])
    paths = validate(pr, files, repository)
    print(json.dumps({"head": pr["head"]["sha"], "files": len(files), "paths_validated": len(paths),
                      "result": "Branch scope and cloud-author policy passed."}))


if __name__ == "__main__":
    main()
