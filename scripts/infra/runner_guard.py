"""Bind the ephemeral runner plan to the reviewed platform and exact backend."""
import json
import os
from pathlib import Path
import re

from iam_contract import ACCOUNT, BOOTSTRAP, BUCKET, REGION, require

KEY = "banking-release-platform/shared/runner/terraform.tfstate"
PROJECT = "banking-release-deployer"


def configuration(env):
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS"
            and env.get("GITHUB_REF") == "refs/heads/dev", "Runner provisioning uses reviewed dev only")
    require(env.get("AWS_OPERATIONS_ENABLED") == "true" and env.get("CLEANUP_ENABLED") != "true",
            "Creation and cleanup cannot overlap")
    require(env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and env.get("AWS_REGION") == REGION
            and env.get("TF_STATE_BUCKET") == BUCKET and env.get("ROLE_ARN") == BOOTSTRAP,
            "Wrong AWS identity, Region or Terraform backend")
    platform = json.loads(env.get("PLATFORM_INTERFACE_JSON") or "{}")
    connection = env.get("CODEBUILD_GITHUB_CONNECTION_ARN", "")
    require(re.fullmatch(r"arn:aws:codeconnections:us-east-2:" + ACCOUNT + r":connection/[a-f0-9-]{36}", connection),
            "An approved account-owned GitHub App connection ARN is required")
    outputs = platform.get("outputs", {})
    require(platform.get("verified") is True and outputs.get("cluster_name", {}).get("value") == "banking-dev"
            and len(outputs.get("application_subnet_ids", {}).get("value", [])) == 2,
            "The same-run verified private EKS platform is required")
    return {"account": ACCOUNT, "region": REGION, "bucket": BUCKET, "key": KEY,
            "cluster": "banking-dev", "subnets": outputs["application_subnet_ids"]["value"],
            "vpc": outputs["vpc_id"]["value"], "project": PROJECT, "github_connection_arn": connection}


if __name__ == "__main__":
    config = configuration(os.environ)
    Path("runner-config.json").write_text(json.dumps(config, sort_keys=True, indent=2))
    Path("runner.tfbackend.json").write_text(json.dumps({
        "bucket": BUCKET, "key": KEY, "region": REGION, "encrypt": True,
        "use_lockfile": True, "allowed_account_ids": [ACCOUNT],
        "workspace_key_prefix": "banking-release-platform/_workspaces"
    }, sort_keys=True, indent=2))
