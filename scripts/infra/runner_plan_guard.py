"""Reject runner plans outside the exact project inventory or with deletions."""
import json
from pathlib import Path
import sys

ALLOWED = {
    "terraform_data.scope", "aws_iam_policy.boundary", "aws_iam_role.runner",
    "aws_iam_role_policy.runner", "aws_security_group.runner",
    "aws_vpc_security_group_egress_rule.https", "aws_vpc_security_group_ingress_rule.eks_api",
    "aws_cloudwatch_log_group.runner", "aws_codebuild_project.runner",
    "aws_codebuild_webhook.runner",
}


def review(plan):
    changes = []
    for item in plan.get("resource_changes", []):
        if item.get("mode") != "managed":
            continue
        address = item["address"]
        actions = item["change"]["actions"]
        if address not in ALLOWED or actions not in (["create"], ["no-op"]):
            raise ValueError("Unexpected runner plan change: " + address + " " + repr(actions))
        after = item["change"].get("after") or {}
        if address == "aws_codebuild_project.runner":
            if after.get("name") != "banking-release-deployer" or after.get("project_visibility") != "PRIVATE":
                raise ValueError("Runner project name/visibility differs")
        if address == "aws_iam_role.runner" and after.get("name") != "cloudbatch818-mahmoud-banking-codebuild-runner":
            raise ValueError("Runner service role differs")
        changes.append({"address": address, "actions": actions})
    if {row["address"] for row in changes} != ALLOWED:
        raise ValueError("Runner plan does not cover the exact expected Terraform inventory")
    return {"resources": sorted(changes, key=lambda row: row["address"]),
            "creates": sum(row["actions"] == ["create"] for row in changes),
            "updates": 0, "deletes": 0}


if __name__ == "__main__":
    report = review(json.loads(Path(sys.argv[1]).read_text()))
    Path("runner-plan-review.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2))
