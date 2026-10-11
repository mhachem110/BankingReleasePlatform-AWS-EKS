"""Generate DRAFT additive IAM JSON locally. Never calls or changes AWS."""
import argparse
import copy
import json
import re
from pathlib import Path

STATE_KEYS = [
    "banking-release-platform/bootstrap/terraform.tfstate",
    "banking-release-platform/dev/foundation/terraform.tfstate",
]
BUCKET_READ = [
    "s3:GetBucketLocation", "s3:GetBucketAcl", "s3:GetBucketCORS",
    "s3:GetBucketWebsite", "s3:GetBucketLogging", "s3:GetAccelerateConfiguration",
    "s3:GetBucketRequestPayment", "s3:GetBucketObjectLockConfiguration",
    "s3:GetReplicationConfiguration", "s3:GetBucketTagging", "s3:GetBucketVersioning",
    "s3:GetEncryptionConfiguration", "s3:GetBucketPublicAccessBlock",
    "s3:GetBucketPolicy", "s3:GetBucketOwnershipControls", "s3:GetLifecycleConfiguration",
]
BUCKET_WRITE = [
    "s3:CreateBucket", "s3:PutBucketVersioning", "s3:PutEncryptionConfiguration",
    "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls",
    "s3:PutBucketPolicy", "s3:PutBucketTagging", "s3:PutLifecycleConfiguration",
]

def document(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if value.get("Version") != "2012-10-17" or not value.get("Statement"):
        raise ValueError("Supply a complete current IAM policy with Version and Statement.")
    return value

def trust_update(current, account, settings):
    prefix = settings["sub_claim_prefix"]
    expected = "repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979"
    if settings.get("use_default") is not True or settings.get("use_immutable_subject") is not True or prefix != expected:
        raise ValueError("OIDC settings differ from the verified repository; inspect before proceeding.")
    statement = {
        "Sid": "GitHubOIDCBankingBootstrap",
        "Effect": "Allow",
        "Principal": {"Federated": f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"},
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {"StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": prefix + ":environment:bootstrap",
        }},
    }
    result = copy.deepcopy(current)
    if isinstance(result["Statement"], dict):
        result["Statement"] = [result["Statement"]]
    existing = next((s for s in result["Statement"] if s.get("Sid") == statement["Sid"]), None)
    if existing is not None and existing != statement:
        raise ValueError("Existing Banking trust differs; do not overwrite automatically.")
    if existing is None:
        result["Statement"].append(statement)
    return result

def s3_addition(bucket, mode, kms_key_arn=""):
    arn = f"arn:aws:s3:::{bucket}"
    statements = [
        {"Sid": "BankingBackendBucketRead", "Effect": "Allow", "Action": BUCKET_READ, "Resource": arn},
        {"Sid": "BankingBackendPrefixList", "Effect": "Allow", "Action": "s3:ListBucket", "Resource": arn,
         "Condition": {"StringLike": {"s3:prefix": ["banking-release-platform/*"]}}},
        {"Sid": "BankingStateReadWrite", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
         "Resource": [arn + "/" + key for key in STATE_KEYS]},
        {"Sid": "BankingStateLockReadWriteDelete", "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": [arn + "/" + key + ".tflock" for key in STATE_KEYS]},
    ]
    if mode == "dedicated":
        # The dedicated aws_s3_bucket resource refresh uses HeadBucket. Shared
        # buckets stay outside Terraform ownership and retain prefix-only listing.
        statements.append({"Sid": "BankingDedicatedBucketRefresh", "Effect": "Allow",
                           "Action": "s3:ListBucket", "Resource": arn})
        statements.append({"Sid": "BankingApprovedDedicatedBucketManagement", "Effect": "Allow",
                           "Action": BUCKET_WRITE, "Resource": arn})
    if kms_key_arn:
        statements.append({"Sid": "BankingBackendApprovedKMSKey", "Effect": "Allow",
                           "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
                           "Resource": kms_key_arn})
    return {"Version": "2012-10-17", "Statement": statements}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--current-trust", required=True)
    p.add_argument("--current-permissions", required=True)
    p.add_argument("--oidc-settings", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--bucket", required=True)
    p.add_argument("--mode", choices=["reuse", "dedicated"], required=True)
    p.add_argument("--kms-key-arn", default="")
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    if not re.fullmatch(r"[0-9]{12}", a.account):
        p.error("Use the verified account ID.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", a.bucket) or ".." in a.bucket:
        p.error("Use the exact approved bucket name.")
    if a.kms_key_arn and not re.fullmatch(r"arn:aws:kms:[a-z0-9-]+:" + a.account + r":key/[a-zA-Z0-9-]+", a.kms_key_arn):
        p.error("Use the verified customer KMS key ARN in the target account.")
    trust = document(a.current_trust)
    permissions = document(a.current_permissions)
    settings = json.loads(Path(a.oidc_settings).read_text(encoding="utf-8-sig"))
    output = Path(a.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for filename, value in {
        "proposed-trust.json": trust_update(trust, a.account, settings),
        "proposed-additional-s3-policy.json": s3_addition(a.bucket, a.mode, a.kms_key_arn),
        "existing-permissions-unchanged.json": permissions,
    }.items():
        (output / filename).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("Draft JSON generated. Preserve the existing inline policy. Review authorization, SCPs and bucket policy before applying any addition.")

if __name__ == "__main__":
    main()
