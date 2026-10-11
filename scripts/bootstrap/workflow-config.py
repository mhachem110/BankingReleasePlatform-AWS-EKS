"""Validate reviewed inputs and narrow the reused role's session. No AWS calls."""
import json
import os
import re


def configuration(values):
    account, region, bucket = (values[name] for name in
                              ("AWS_EXPECTED_ACCOUNT_ID", "AWS_REGION", "TF_STATE_BUCKET"))
    if values.get("GITHUB_REF") != "refs/heads/dev":
        raise ValueError("AWS operations must run from reviewed dev.")
    if not re.fullmatch(r"[0-9]{12}", account) or not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]+", region):
        raise ValueError("Supply the reviewed AWS account and Region.")
    if bucket != "mhachem-banking-tfstate-" + account:
        raise ValueError("Use this project's proposed dedicated bucket; other buckets need separate review.")
    role = values.get("ROLE_ARN", "")
    if not re.fullmatch(r"arn:aws:iam::" + account + r":role/(?:[A-Za-z0-9+=,.@_-]+/)*cloudbatch818-mahmoud-cloudops-bootstrap", role):
        raise ValueError("Copy the existing role ARN from IAM, including :role/ and any actual path.")
    operation = values["OPERATION"]
    if operation not in {"connectivity", "initialize", "plan", "apply"}:
        raise ValueError("Unknown operation.")
    root = "infra/bootstrap" if operation == "initialize" or values.get("TARGET") == "bootstrap" else "infra/environments/dev"
    key = "banking-release-platform/bootstrap/terraform.tfstate" if root == "infra/bootstrap" else "banking-release-platform/dev/foundation/terraform.tfstate"
    if operation == "initialize":
        required = "RESUME-APPROVED-INITIALIZATION" if values.get("RESUME") == "true" else "CREATE-APPROVED-STATE-BUCKET"
        if values.get("APPROVAL") != required or values.get("DEDICATED_BUCKET_MANAGEMENT_APPROVED") != "true":
            raise ValueError("Dedicated initialization requires the exact explicit approval and approval flag.")
        if values.get("TF_STATE_KMS_KEY_ARN"):
            raise ValueError("Initial dedicated bootstrap uses SSE-S3; customer KMS requires separate review.")
    elif operation in {"plan", "apply"}:
        if values.get("BOOTSTRAP_STATE_READY") != "true":
            raise ValueError("Verify dedicated bucket/state initialization before remote operations.")
        if root == "infra/bootstrap" and values.get("DEDICATED_BUCKET_MANAGEMENT_APPROVED") != "true":
            raise ValueError("Managing the dedicated bucket requires explicit approval.")
        if operation == "apply" and values.get("APPROVAL") != "APPLY-REVIEWED-PLAN":
            raise ValueError("Apply requires explicit approval of this run's saved plan.")
    statements = [{"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"}]
    if operation == "connectivity":
        statements.append({"Effect": "Allow", "Action": "iam:GetOpenIDConnectProvider",
                           "Resource": f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"})
        statements.append({"Effect": "Allow", "Action": ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies"],
                           "Resource": role})
    elif operation == "initialize" and values.get("RESUME") == "true":
        # This recovery already has seven imports. Allow metadata/state reads
        # and lock writes only: no bucket repair, state overwrite or IAM access.
        arn = "arn:aws:s3:::" + bucket
        keys = ["banking-release-platform/bootstrap/terraform.tfstate",
                "banking-release-platform/dev/foundation/terraform.tfstate"]
        statements.extend([
            {"Effect": "Allow", "Action": ["s3:GetBucket*", "s3:GetEncryptionConfiguration",
             "s3:GetLifecycleConfiguration", "s3:GetAccelerateConfiguration", "s3:GetReplicationConfiguration",
             "s3:ListBucket"], "Resource": arn},
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": [arn + "/" + k for k in keys]},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
             "Resource": [arn + "/" + k + ".tflock" for k in keys]},
        ])
    else:
        # Session policies only restrict the role. The separate exact-action S3
        # inline policy supplies actual grants; this cap excludes Retail/EC2/EKS/IAM.
        arn = "arn:aws:s3:::" + bucket
        statements.append({"Effect": "Allow", "Action": "s3:*", "Resource": [arn, arn + "/*"]})
        kms = values.get("TF_STATE_KMS_KEY_ARN", "")
        if kms:
            if not re.fullmatch(r"arn:aws:kms:" + region + ":" + account + r":key/[A-Za-z0-9-]+", kms):
                raise ValueError("KMS key must be the separately approved key in this account/Region.")
            statements.append({"Effect": "Allow", "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"], "Resource": kms})
    policy = json.dumps({"Version": "2012-10-17", "Statement": statements}, separators=(",", ":"))
    if len(policy) > 2048:
        raise ValueError("Session policy exceeds STS plaintext limit.")
    return {"root": root, "key": key, "session_policy": policy}


def main():
    outputs = configuration(os.environ)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        for name, value in outputs.items():
            stream.write(f"{name}={value}\n")
    print("Validated approved inputs and scoped temporary session permissions; no AWS operation performed.")


if __name__ == "__main__":
    main()
