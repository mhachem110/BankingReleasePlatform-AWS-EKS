"""Read-only bucket prerequisites. Never creates or repairs AWS resources."""
import argparse
import json
import subprocess

def aws(*args):
    result = subprocess.run(["aws", "s3api", *args, "--output", "json"], check=True, capture_output=True, text=True)
    return json.loads(result.stdout or "{}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--kms-key-arn", default="")
    args = parser.parse_args()
    common = ["--bucket", args.bucket, "--expected-bucket-owner", args.account, "--region", args.region]
    # Each metadata request verifies the expected owner. Avoid HeadBucket, which
    # requires unconditioned ListBucket access on a reused shared bucket.
    actual_region = aws("get-bucket-location", *common).get("LocationConstraint") or "us-east-1"
    if actual_region == "EU":
        actual_region = "eu-west-1"
    if actual_region != args.region:
        raise RuntimeError("Approved Region does not match the bucket.")
    if aws("get-bucket-versioning", *common).get("Status") != "Enabled":
        raise RuntimeError("Approved bucket must have versioning Enabled.")
    public = aws("get-public-access-block", *common)["PublicAccessBlockConfiguration"]
    if not all(public.get(key) is True for key in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
        raise RuntimeError("Bucket-level public access blocking must be enabled.")
    rules = aws("get-bucket-encryption", *common)["ServerSideEncryptionConfiguration"]["Rules"]
    encryption = rules[0]["ApplyServerSideEncryptionByDefault"]
    expected = "aws:kms" if args.kms_key_arn else "AES256"
    if encryption["SSEAlgorithm"] != expected or (args.kms_key_arn and encryption.get("KMSMasterKeyID") != args.kms_key_arn):
        raise RuntimeError("Encryption does not match the reviewed backend configuration.")
    print("Verified bucket owner, Region, versioning, encryption and public-access safeguards.")

if __name__ == "__main__":
    main()
