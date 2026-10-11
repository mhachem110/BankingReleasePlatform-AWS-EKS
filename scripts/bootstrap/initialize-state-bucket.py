"""Explicitly authorized first-time bucket seed; never run by PR validation."""
import argparse
import json
import re
import subprocess

TAGS = {"Project": "BankingReleasePlatform", "Environment": "bootstrap", "ManagedBy": "Terraform"}


class AwsError(RuntimeError):
    def __init__(self, operation, result):
        self.code = (re.search(r"\(([^)]+)\)", result.stderr) or [None, "Unknown"])[1]
        super().__init__(f"AWS {operation} failed with {self.code}; stop and inspect the authorized run.")


def aws(operation, *args):
    result = subprocess.run(["aws", "s3api", operation, *args, "--output", "json"], capture_output=True, text=True)
    if result.returncode:
        raise AwsError(operation, result)
    return json.loads(result.stdout or "{}")


def seed(bucket, account, region, resume=False, caller=aws):
    if not re.fullmatch(r"[0-9]{12}", account) or bucket != "mhachem-banking-tfstate-" + account:
        raise ValueError("Initialization is limited to this account's explicitly approved Banking bucket.")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]+", region) or region == "us-east-1":
        raise ValueError("Review a LocationConstraint Region; current proposal is us-east-2.")
    common = ["--bucket", bucket, "--expected-bucket-owner", account, "--region", region]
    try:
        caller("head-bucket", *common)
        exists = True
    except AwsError as error:
        if error.code not in {"404", "NoSuchBucket", "NotFound"}:
            raise RuntimeError("Bucket ownership/absence is ambiguous; do not create or adopt it.") from error
        exists = False
    if exists and not resume:
        raise RuntimeError("Bucket already exists; explicit recovery review is required, never automatic adoption.")
    if resume and not exists:
        raise RuntimeError("Resume expects a verified previously seeded dedicated bucket.")
    if resume:
        location = caller("get-bucket-location", *common).get("LocationConstraint") or "us-east-1"
        tags = {tag["Key"]: tag["Value"] for tag in caller("get-bucket-tagging", *common)["TagSet"]}
        if location != region or tags != TAGS:
            raise RuntimeError("Existing bucket Region/ownership markers differ; stop for administrator review.")
    else:
        # If this loses a race or its result is ambiguous, stop. Never proceed
        # after BucketAlreadyOwnedByYou/BucketAlreadyExists as though we created it.
        caller("create-bucket", "--bucket", bucket, "--region", region,
               "--create-bucket-configuration", json.dumps({"LocationConstraint": region}))
        caller("put-bucket-tagging", *common, "--tagging",
               json.dumps({"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]}))
    caller("put-public-access-block", *common, "--public-access-block-configuration",
           json.dumps({name: True for name in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}))
    caller("put-bucket-ownership-controls", *common, "--ownership-controls",
           json.dumps({"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}))
    caller("put-bucket-versioning", *common, "--versioning-configuration", '{"Status":"Enabled"}')
    caller("put-bucket-encryption", *common, "--server-side-encryption-configuration",
           json.dumps({"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}))
    arn = "arn:aws:s3:::" + bucket
    caller("put-bucket-policy", *common, "--policy", json.dumps({"Version": "2012-10-17", "Statement": [{
        "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
        "Resource": [arn, arn + "/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}))
    caller("put-bucket-lifecycle-configuration", *common, "--lifecycle-configuration", json.dumps({"Rules": [{
        "ID": "retain-current-state-and-limit-old-versions", "Status": "Enabled", "Filter": {},
        "NoncurrentVersionExpiration": {"NoncurrentDays": 90},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}]}))
    print("Dedicated bucket seed completed. Verify safeguards before initializing/importing remote state.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    seed(args.bucket, args.account, args.region, args.resume)


if __name__ == "__main__":
    main()
