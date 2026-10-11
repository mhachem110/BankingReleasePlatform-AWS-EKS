"""Record the explicitly seeded seven resources directly in the S3 backend."""
import argparse
import json
import subprocess

TYPES = ("aws_s3_bucket", "aws_s3_bucket_ownership_controls", "aws_s3_bucket_public_access_block",
         "aws_s3_bucket_versioning", "aws_s3_bucket_server_side_encryption_configuration",
         "aws_s3_bucket_policy", "aws_s3_bucket_lifecycle_configuration")
ADDRESSES = frozenset("module.state_bucket." + name + ".state" for name in TYPES)


def existing_resources(state, bucket):
    found = set()
    for resource in state.get("resources", []):
        address = resource.get("module", "") + "." + resource["type"] + "." + resource["name"]
        instances = resource.get("instances", [])
        if address not in ADDRESSES or resource.get("mode") != "managed" or len(instances) != 1 or instances[0].get("attributes", {}).get("id") != bucket:
            raise RuntimeError("Remote state contains unexpected resource identities; never overwrite it.")
        if address in found:
            raise RuntimeError("Duplicate resource address in remote state.")
        found.add(address)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    args = parser.parse_args()
    command = ["terraform", "-chdir=infra/bootstrap"]
    result = subprocess.run(command + ["state", "pull"], capture_output=True, text=True)
    if result.returncode:
        if "No state file was found" not in result.stderr:
            raise RuntimeError("Cannot safely read bootstrap state; stop before importing.")
        state = {}
    else:
        state = json.loads(result.stdout)
    existing = existing_resources(state, args.bucket)
    for address in sorted(ADDRESSES - existing):
        subprocess.run(command + ["import", "-input=false", "-lock-timeout=5m", address, args.bucket], check=True)
    final = subprocess.run(command + ["state", "pull"], capture_output=True, text=True, check=True)
    if existing_resources(json.loads(final.stdout), args.bucket) != ADDRESSES:
        raise RuntimeError("Remote state import is incomplete; use the explicit recovery procedure.")
    print("All seven dedicated-bucket resources recorded in S3 state. No state artifact or local handoff was used.")


if __name__ == "__main__":
    main()
