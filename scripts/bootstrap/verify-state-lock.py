"""Exercise S3 lock contention; never overwrite or force-unlock another lock."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

ROOT_KEYS = {
    "infra/bootstrap": "banking-release-platform/bootstrap/terraform.tfstate",
    "infra/environments/dev": "banking-release-platform/dev/foundation/terraform.tfstate",
}


def checked(command, runner):
    result = runner(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Verification command failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "{}")


def verify(bucket, account, region, root, runner=subprocess.run):
    if not re.fullmatch(r"[0-9]{12}", account) or bucket != "mhachem-banking-tfstate-" + account:
        raise ValueError("Lock verification is limited to the approved Banking bucket.")
    if region != "us-east-2" or root not in ROOT_KEYS:
        raise ValueError("Use only the approved Phase 2 Region and roots.")
    key = ROOT_KEYS[root]
    backend = json.loads((Path(root) / ".terraform/terraform.tfstate").read_text())["backend"]
    config = backend["config"]
    if backend["type"] != "s3" or any(config.get(name) != value for name, value in
            {"bucket": bucket, "key": key, "region": region, "use_lockfile": True}.items()):
        raise RuntimeError("Initialized backend differs from the approved locked S3 backend.")
    lock_id = str(uuid.uuid4())
    lock = {"ID": lock_id, "Operation": "OperationTypePlan", "Info": "Phase 2 contention verification",
            "Who": "github-actions:" + os.environ.get("GITHUB_RUN_ID", "local-operator"),
            "Version": "1.15.8", "Created": datetime.now(timezone.utc).isoformat(), "Path": bucket + "/" + key}
    common = ["--bucket", bucket, "--key", key + ".tflock", "--expected-bucket-owner", account, "--region", region]
    with tempfile.TemporaryDirectory() as directory:
        body, downloaded = Path(directory) / "lock.json", Path(directory) / "downloaded-lock.json"
        body.write_text(json.dumps(lock), encoding="utf-8")
        # Conditional creation refuses an existing lock, including a racing writer.
        created = checked(["aws", "s3api", "put-object", *common, "--body", str(body),
                           "--if-none-match", "*", "--server-side-encryption", "AES256", "--output", "json"], runner)
        etag = created.get("ETag")
        if not etag:
            raise RuntimeError("Missing test-lock ETag; stop for operator investigation, never force-unlock.")
        try:
            result = runner(["terraform", "-chdir=" + root, "plan", "-input=false", "-refresh=false",
                             "-lock-timeout=0s", "-no-color"], capture_output=True, text=True)
            diagnostic = result.stdout + result.stderr
            if not result.returncode or "Error acquiring the state lock" not in diagnostic or lock_id not in diagnostic:
                raise RuntimeError("Terraform did not report contention on this exact test lock.")
            print(f"Verified Terraform rejects a competing plan while the test lock is held: {key}.")
        finally:
            # Read back identity AND ETag; conditional deletion cannot remove a replacement lock.
            current = checked(["aws", "s3api", "get-object", *common, str(downloaded), "--output", "json"], runner)
            if current.get("ETag") != etag or json.loads(downloaded.read_text())["ID"] != lock_id:
                raise RuntimeError("Lock ownership changed; leave it untouched for operator investigation.")
            checked(["aws", "s3api", "delete-object", *common, "--if-match", etag, "--output", "json"], runner)
            head = runner(["aws", "s3api", "head-object", *common, "--output", "json"], capture_output=True, text=True)
            if not head.returncode or not re.search(r"\((404|NoSuchKey|NotFound)\)", head.stderr):
                raise RuntimeError("Cannot verify test-lock removal; stop before another plan.")
            print(f"Verified only this run's test lock was removed: {key}. No force-unlock used.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--root", choices=ROOT_KEYS, required=True)
    args = parser.parse_args()
    verify(args.bucket, args.account, args.region, args.root)
