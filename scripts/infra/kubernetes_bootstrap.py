"""Fail-closed verification around the reviewed Banking namespace/RBAC install."""
import json
import os
import subprocess
import sys
from pathlib import Path

ACCOUNT = "866934333672"
REGION = "us-east-2"
OPERATOR = f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-operator"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(*args):
    return json.loads(subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout)


def main(stage):
    env = os.environ
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and
            env.get("GITHUB_REF") == "refs/heads/dev" and env.get("AWS_REGION") == REGION and
            env.get("AWS_ACCOUNT_ID") == ACCOUNT and env.get("BANKING_OPERATOR_ROLE_ARN") == OPERATOR,
            "Wrong project/branch/account/operator")
    platform = json.loads(env.get("PLATFORM_INTERFACE_JSON") or "{}")
    outputs = platform.get("outputs", {})
    require(platform.get("verified") is True and outputs.get("cluster_name", {}).get("value") == "banking-dev",
            "Only the verified Banking cluster may be configured")
    identity = command("aws", "sts", "get-caller-identity")
    require(identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(
        f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-banking-operator/"), "Wrong OIDC role")
    cluster = command("aws", "eks", "describe-cluster", "--name", "banking-dev", "--region", REGION)["cluster"]
    require(cluster.get("status") == "ACTIVE" and cluster.get("endpoint") == outputs["cluster_endpoint"]["value"],
            "EKS endpoint/status changed")
    if stage == "preflight":
        return
    for environment in ("dev", "prod"):
        namespace = "banking-" + environment
        group = "banking-release-" + environment
        item = command("kubectl", "get", "namespace", namespace, "-o", "json")
        labels = item["metadata"]["labels"]
        require(labels.get("pod-security.kubernetes.io/enforce") == "restricted" and
                labels.get("banking.example/environment") == environment, "Namespace policy changed")
        quota = command("kubectl", "get", "resourcequota", "banking-release-capacity", "-n", namespace, "-o", "json")
        require(quota["spec"]["hard"]["services.loadbalancers"] == "0", "Unexpected public LoadBalancer quota")
        binding = command("kubectl", "get", "rolebinding", "banking-release", "-n", namespace, "-o", "json")
        require(binding["roleRef"]["name"] == "banking-release" and
                binding["subjects"] == [{"kind": "Group", "apiGroup": "rbac.authorization.k8s.io", "name": group}],
                "Release group binding changed")
        role = command("kubectl", "get", "role", "banking-release", "-n", namespace, "-o", "json")
        require(not any("roles" in rule.get("resources", []) or "rolebindings" in rule.get("resources", [])
                        for rule in role["rules"]), "Release role may modify RBAC")
    Path("kubernetes-bootstrap-verification.json").write_text(json.dumps({
        "cluster": "banking-dev", "namespaces": ["banking-dev", "banking-prod"],
        "release_groups": ["banking-release-dev", "banking-release-prod"], "verified": True}, indent=2))


if __name__ == "__main__":
    require(len(sys.argv) == 2 and sys.argv[1] in {"preflight", "verify"}, "Use preflight or verify")
    main(sys.argv[1])
