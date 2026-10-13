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

def release_mode():
    mode = os.environ.get("APP_RELEASE_MODE", "sequential")
    if mode not in {"sequential", "shared-cluster-demo"}:
        raise ValueError("Unknown reviewed release mode")
    return mode

def predecessor(environment):
    if release_mode() == "shared-cluster-demo":
        if environment not in {"dev", "prod"}:
            raise ValueError("Stage/UAT deployments are inactive in the approved demonstration")
        return "dev" if environment == "prod" else None
    return PREVIOUS.get(environment)

def application_session_policy(cfg, *, publishing=False):
    if publishing and cfg["environment"] != "dev":
        raise ValueError("Production cannot publish images")
    actions = ["ecr:DescribeRepositories", "ecr:DescribeImages", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    if publishing:
        actions += ["ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"]
    statements = [{"Effect":"Allow", "Action":["sts:GetCallerIdentity", "ecr:GetAuthorizationToken"], "Resource":"*"},
        {"Effect":"Allow", "Action":actions, "Resource":[f"arn:aws:ecr:{cfg['region']}:{cfg['account']}:repository/banking-dev-{s}" for s in ("account","payment")]}]
    if not publishing:
        statements.append({"Effect":"Allow", "Action":"eks:DescribeCluster", "Resource":f"arn:aws:eks:{cfg['region']}:{cfg['account']}:cluster/{cfg['cluster']}"})
    value = json.dumps({"Version":"2012-10-17", "Statement":statements}, separators=(",", ":"))
    if len(value) > 2048:
        raise ValueError("Application STS cap exceeds the supported limit")
    return value

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
    if environment in {"dev", "prod"}:
        # Data bootstrap installs these exact namespace-owned objects from the
        # verified RDS/SQS interfaces. No GitHub setting carries a password or
        # manually copied queue/role ARN.
        queue = f"https://sqs.us-east-2.amazonaws.com/866934333672/banking-{environment}-payments"
        expected = {
            "persistence": {"enabled": True, "accountSecretName": "banking-account-db",
                            "paymentSecretName": "banking-payment-db", "caConfigMapName": "banking-rds-ca"},
            "messaging": {"enabled": True, "approved": True,
                          "roleArn": f"arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-banking-payment-runtime-{environment}",
                          "queueUrl": queue, "deadLetterQueueUrl": queue + "-dlq"},
            "monitoring": {"scrape": True},
        }
        if values and values != expected:
            raise ValueError("Dev/prod must use the exact verified database, queue and namespace references")
        return expected
    if values.get("persistence", {}).get("enabled") or values.get("messaging", {}).get("enabled"):
        raise ValueError("Stage/UAT use only their reviewed stateless demonstration until separate data infrastructure exists")
    if values.get("messaging", {}).get("enabled"):
        settings = values["messaging"]
        prefix = f"https://sqs.us-east-2.amazonaws.com/866934333672/banking-{environment}-payments"
        if (settings.get("approved") is not True or values.get("persistence", {}).get("enabled") is not True or
                settings.get("roleArn") != f"arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-banking-payment-runtime-{environment}" or
                settings.get("queueUrl") != prefix or settings.get("deadLetterQueueUrl") != prefix + "-dlq"):
            raise ValueError("Messaging must use the approved namespace-specific runtime role and queues")
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
    predecessor(environment)
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
        expected_cluster = "banking-dev" if release_mode() == "shared-cluster-demo" else "banking-" + environment
        if result["cluster"] != expected_cluster or result["namespace"] != "banking-" + environment:
            raise ValueError("Use the approved cluster and the environment-specific namespace")
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
