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
    ownership = aws("get-bucket-ownership-controls", *common)["OwnershipControls"]["Rules"]
    if not any(rule.get("ObjectOwnership") == "BucketOwnerEnforced" for rule in ownership):
        raise RuntimeError("Bucket owner enforcement must disable ACLs.")
    policy = json.loads(aws("get-bucket-policy", *common)["Policy"])
    statements = policy["Statement"] if isinstance(policy["Statement"], list) else [policy["Statement"]]
    arn = "arn:aws:s3:::" + args.bucket
    if not any(s.get("Effect") == "Deny" and s.get("Principal") == "*" and s.get("Action") == "s3:*"
               and set(s.get("Resource", [])) >= {arn, arn + "/*"}
               and s.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") in ("false", False) for s in statements):
        raise RuntimeError("Bucket policy must deny insecure transport for bucket and objects.")
    lifecycle = aws("get-bucket-lifecycle-configuration", *common)["Rules"]
    if len(lifecycle) != 1 or lifecycle[0].get("Status") != "Enabled" or lifecycle[0].get("Filter") != {} \
            or lifecycle[0].get("NoncurrentVersionExpiration", {}).get("NoncurrentDays") != 90 \
            or lifecycle[0].get("AbortIncompleteMultipartUpload", {}).get("DaysAfterInitiation") != 7 \
            or "Expiration" in lifecycle[0]:
        raise RuntimeError("Lifecycle must preserve current state, retain old versions for 90 days and abort incomplete uploads after seven days.")
    print("Verified bucket owner, Region, versioning, encryption, public blocking, ACL enforcement, TLS-only policy and lifecycle.")

if __name__ == "__main__":
    main()
