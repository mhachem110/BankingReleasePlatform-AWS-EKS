"""Restrict the protected Kubernetes operator session to this run's RDS secrets."""
import json
import os
import re

ACCOUNT = "866934333672"
REGION = "us-east-2"


if __name__ == "__main__":
    arns = []
    for environment in ("dev", "prod"):
        value = json.loads(os.environ.get(environment.upper() + "_DATA_INTERFACE_JSON") or "{}")
        if value.get("verified") is not True or value.get("environment") != environment:
            raise ValueError("Only same-run verified data may be read")
        arn = value.get("outputs", {}).get("master_secret_arn", "")
        if not re.fullmatch(r"arn:aws:secretsmanager:us-east-2:" + ACCOUNT + r":secret:rds!db-[A-Za-z0-9/_+=.@!-]+", arn):
            raise ValueError("Wrong RDS-managed secret ARN")
        arns.append(arn)
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
        {"Effect": "Allow", "Action": "eks:DescribeCluster",
         "Resource": f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/banking-dev"},
        {"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": arns},
        {"Effect": "Allow", "Action": "kms:Decrypt",
         "Resource": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*",
         "Condition": {"ForAnyValue:StringEquals": {"kms:ResourceAliases": "alias/banking-release-platform-runtime"}}}
    ]}
    serialized = json.dumps(policy, separators=(",", ":"))
    if len(serialized) > 2048:
        raise ValueError("Operator session cap exceeds the STS inline limit")
    with open(os.environ["GITHUB_OUTPUT"], "a") as out:
        out.write("session_policy=" + serialized + "\n")
