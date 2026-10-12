"""Application operations only. Never provisions infrastructure or changes IAM."""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "mhachem110/BankingReleasePlatform-AWS-EKS"
ROUTES = {"dev": "dev", "stage": "stage", "uat": "uat", "prod": "main"}
PREVIOUS = {"stage": "dev", "uat": "stage", "prod": "uat"}
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
SHA = re.compile(r"[a-f0-9]{40}")

def runtime_values(environment):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate runtime configuration key")
            result[key] = value
        return result
    values = json.loads(os.environ.get("APP_RUNTIME_VALUES_JSON") or "{}", object_pairs_hook=unique)
    if not isinstance(values, dict) or set(values) - {"persistence", "messaging", "monitoring"}:
        raise ValueError("Runtime configuration permits only non-secret persistence/messaging/monitoring references")
    allowed = {"persistence": {"enabled", "accountSecretName", "paymentSecretName", "caConfigMapName"},
               "messaging": {"enabled", "approved", "roleArn", "queueUrl", "deadLetterQueueUrl"},
               "monitoring": {"scrape"}}
    for section, settings in values.items():
        if not isinstance(settings, dict) or set(settings) - allowed[section]:
            raise ValueError("Unknown runtime setting; plaintext credentials and arbitrary Helm overrides are forbidden")
    if values.get("persistence", {}).get("enabled") or values.get("messaging", {}).get("enabled"):
        if environment != "dev" or os.environ.get("APP_DATA_OPERATIONS_ENABLED") != "true":
            raise ValueError("Data/messaging requires separate explicit dev authorization")
    return values

def run(args, *, capture=False, check=True, **kwargs):
    result = subprocess.run([str(a) for a in args], check=check, text=True, encoding="utf-8",
                            capture_output=capture, **kwargs)
    return result.stdout.strip() if capture else result

def json_run(args):
    return json.loads(run(args, capture=True))

def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Required environment variable: {name}")
    return value

def config(environment, *, publishing=False):
    if environment not in ROUTES:
        raise ValueError("Unknown deployment environment")
    if required("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("Unexpected repository")
    if required("GITHUB_REF") != "refs/heads/" + ROUTES[environment]:
        raise ValueError("Use the reviewed environment branch")
    if required("APP_DEPLOYMENTS_ENABLED") != "true":
        raise ValueError("Application operations are disabled")
    if publishing and environment != "dev":
        raise ValueError("Publish only from reviewed dev")
    account = required("AWS_ACCOUNT_ID")
    region = required("AWS_REGION")
    if not re.fullmatch(r"[0-9]{12}", account) or not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]", region):
        raise ValueError("Invalid AWS account/Region")
    role = required("APP_DEPLOY_ROLE_ARN")
    if not re.fullmatch(r"arn:aws:iam::" + account + r":role/[A-Za-z0-9_+=,.@/-]+", role):
        raise ValueError("Invalid approved application role ARN")
    if role in [os.environ.get("INFRA_ROLE_ARN"), os.environ.get("BOOTSTRAP_ROLE_ARN")]:
        raise ValueError("Application and infrastructure roles must be separate")
    registry = f"{account}.dkr.ecr.{region}.amazonaws.com"
    repos = {}
    for service in ("account", "payment"):
        repo = required("ECR_" + service.upper() + "_REPOSITORY")
        if repo != f"{registry}/banking-dev-{service}":
            raise ValueError("Use the approved immutable Banking ECR repository")
        repos[service] = repo
    result = {"environment": environment, "region": region, "account": account, "role": role, "repos": repos}
    if not publishing:
        result["cluster"] = required("EKS_CLUSTER_NAME")
        result["namespace"] = required("K8S_NAMESPACE")
        if result["cluster"] != "banking-" + environment or result["namespace"] != "banking-" + environment:
            raise ValueError("Environment must use its own approved cluster and namespace")
    return result

def validate_manifest(manifest, repos):
    if set(manifest) != {"version", "sourceCommit", "publishRunId", "images"} or manifest["version"] != 1:
        raise ValueError("Invalid release manifest format")
    if not SHA.fullmatch(str(manifest["sourceCommit"])) or not re.fullmatch(r"[1-9][0-9]*", str(manifest["publishRunId"])):
        raise ValueError("Invalid manifest provenance")
    if set(manifest["images"]) != {"account", "payment"}:
        raise ValueError("Exactly two images required")
    for service, image in manifest["images"].items():
        if set(image) != {"repository", "digest"} or image["repository"] != repos[service] or not DIGEST.fullmatch(image["digest"]):
            raise ValueError("Unapproved repository or non-immutable image")
    return manifest

def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def helm_values(manifest):
    return {"images": manifest["images"], "ingress": {"enabled": False},
            "demonstration": {"enabled": False, "failPaymentReadiness": False}}
