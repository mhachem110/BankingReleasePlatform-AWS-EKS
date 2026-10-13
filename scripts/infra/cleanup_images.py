"""Retire exact project ECR image digests after application Pods are absent."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ACCOUNT = "866934333672"
REPOSITORIES = ("banking-dev-account", "banking-dev-payment")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def aws(*args):
    result = subprocess.run(["aws", *args, "--region", "us-east-2", "--output", "json", "--no-cli-pager"],
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Project image cleanup AWS operation failed: " + args[1])
    return json.loads(result.stdout) if result.stdout.strip() else {}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inventory():
    identity = aws("sts", "get-caller-identity")
    require(identity["Account"] == ACCOUNT and "assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/" in identity["Arn"],
            "Only the Banking bootstrap identity may retire project images")
    result = {"account": ACCOUNT, "region": "us-east-2", "repositories": {}}
    for name in REPOSITORIES:
        repo = aws("ecr", "describe-repositories", "--repository-names", name)["repositories"][0]
        require(repo["repositoryName"] == name and repo["registryId"] == ACCOUNT,
                "Unexpected ECR repository")
        tags = aws("ecr", "list-tags-for-resource", "--resource-arn", repo["repositoryArn"])["tags"]
        values = {row["Key"]: row["Value"] for row in tags}
        require(values.get("Project") == "BankingReleasePlatform" and values.get("ManagedBy") == "Terraform",
                "ECR repository ownership changed")
        ids = aws("ecr", "list-images", "--repository-name", name)["imageIds"]
        result["repositories"][name] = {"arn": repo["repositoryArn"],
                                        "digests": sorted({row["imageDigest"] for row in ids})}
    return result


if __name__ == "__main__":
    require(os.environ.get("TARGET") == "applications" and os.environ.get("CLEANUP_ENABLED") == "true" and
            os.environ.get("AWS_OPERATIONS_ENABLED") == "false", "Protected image cleanup window required")
    if os.environ["OPERATION"] == "plan":
        Path("images-cleanup-plan.json").write_text(json.dumps(inventory(), indent=2))
    else:
        require(os.environ.get("APPROVAL") == "DESTROY-REVIEWED-BANKING-APPLICATIONS",
                "Exact image-retirement approval required")
        reviewed = json.loads(Path("reviewed/images-cleanup-plan.json").read_text())
        require(digest(reviewed) == os.environ.get("REVIEWED_IMAGE_DIGEST") and inventory() == reviewed,
                "ECR image inventory changed since protected review")
        for name, record in reviewed["repositories"].items():
            digests = record["digests"]
            for start in range(0, len(digests), 100):
                ids = [{"imageDigest": value} for value in digests[start:start + 100]]
                result = aws("ecr", "batch-delete-image", "--repository-name", name,
                             "--image-ids", json.dumps(ids))
                require(not result.get("failures"), "ECR reported a digest deletion failure")
        after = inventory()
        require(all(not value["digests"] for value in after["repositories"].values()),
                "Project ECR repositories still contain images")
        receipt = json.loads(Path("kubernetes-cleanup-verification.json").read_text())
        receipt["images_removed"] = True
        receipt["image_plan_sha256"] = os.environ["REVIEWED_IMAGE_DIGEST"]
        Path("kubernetes-cleanup-verification.json").write_text(json.dumps(receipt, indent=2))
