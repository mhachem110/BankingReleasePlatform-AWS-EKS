"""Write an ignored partial backend file from reviewed inputs; no AWS access."""
import argparse
import json
import os
import re
from pathlib import Path

def configuration(values, key):
    bucket = values["TF_STATE_BUCKET"]
    region = values["AWS_REGION"]
    account = values["AWS_EXPECTED_ACCOUNT_ID"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket) or ".." in bucket:
        raise ValueError("Use the exact approved S3 bucket name.")
    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+", region) or not re.fullmatch(r"[0-9]{12}", account):
        raise ValueError("Use the verified AWS Region and account ID.")
    if key not in ("banking-release-platform/bootstrap/terraform.tfstate", "banking-release-platform/dev/foundation/terraform.tfstate"):
        raise ValueError("Unapproved state key.")
    result = dict(bucket=bucket, region=region, key=key, encrypt=True, use_lockfile=True,
                  allowed_account_ids=[account], workspace_key_prefix="banking-release-platform/_workspaces")
    kms = values.get("TF_STATE_KMS_KEY_ARN", "")
    if kms:
        if not re.fullmatch(r"arn:aws:kms:" + re.escape(region) + ":" + account + r":key/[a-zA-Z0-9-]+", kms):
            raise ValueError("KMS ARN must match the approved account and Region.")
        result["kms_key_id"] = kms
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    settings = configuration(os.environ, a.key)
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(f"{name} = {json.dumps(value)}" for name, value in settings.items()) + "\n", encoding="utf-8")
    print("Wrote reviewed partial backend configuration; no AWS operation performed.")

if __name__ == "__main__":
    main()
