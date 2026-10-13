"""Security boundaries around the new runner and full-stack teardown."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET
import cleanup_full
import runner_guard
import runner_plan_guard


class RunnerTests(unittest.TestCase):
    def setup(self):
        connection = f"arn:aws:codeconnections:{REGION}:{ACCOUNT}:connection/12345678-1234-1234-1234-123456789012"
        outputs = {"cluster_name": {"value": "banking-dev"}, "application_subnet_ids": {"value": ["subnet-a", "subnet-b"]},
                   "vpc_id": {"value": "vpc-approved"}}
        return {"GITHUB_REPOSITORY": "mhachem110/BankingReleasePlatform-AWS-EKS", "GITHUB_REF": "refs/heads/dev",
                "AWS_OPERATIONS_ENABLED": "true", "CLEANUP_ENABLED": "false", "AWS_EXPECTED_ACCOUNT_ID": ACCOUNT,
                "AWS_REGION": REGION, "TF_STATE_BUCKET": BUCKET, "ROLE_ARN": BOOTSTRAP,
                "CODEBUILD_GITHUB_CONNECTION_ARN": connection,
                "PLATFORM_INTERFACE_JSON": json.dumps({"verified": True, "outputs": outputs})}

    def test_runner_requires_actual_approved_connection_and_platform(self):
        valid = self.setup()
        self.assertEqual(runner_guard.configuration(valid)["project"], "banking-release-deployer")
        for change in ({"CODEBUILD_GITHUB_CONNECTION_ARN": ""},
                       {"CODEBUILD_GITHUB_CONNECTION_ARN": valid["CODEBUILD_GITHUB_CONNECTION_ARN"].replace(ACCOUNT, "000000000000")},
                       {"GITHUB_REF": "refs/heads/infra"},
                       {"PLATFORM_INTERFACE_JSON": json.dumps({"verified": False, "outputs": {}})}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner_guard.configuration(valid | change)

    def test_runner_plan_refuses_extra_project_and_all_mutations(self):
        rows = [{"mode": "managed", "address": address, "change": {"actions": ["create"],
                 "after": ({"name": "banking-release-deployer", "project_visibility": "PRIVATE"}
                           if address == "aws_codebuild_project.runner" else
                           {"name": "cloudbatch818-mahmoud-banking-codebuild-runner"}
                           if address == "aws_iam_role.runner" else {})}}
                for address in runner_plan_guard.ALLOWED]
        plan = {"resource_changes": rows}
        self.assertEqual(runner_plan_guard.review(plan)["creates"], len(rows))
        for mutation in ("delete", "update", "extra", "public"):
            changed = copy.deepcopy(plan)
            if mutation in {"delete", "update"}:
                changed["resource_changes"][0]["change"]["actions"] = [mutation]
            elif mutation == "extra":
                changed["resource_changes"].append({"mode": "managed", "address": "aws_iam_role.unrelated",
                                                    "change": {"actions": ["create"], "after": {}}})
            else:
                next(x for x in changed["resource_changes"] if x["address"] == "aws_codebuild_project.runner")["change"]["after"]["project_visibility"] = "PUBLIC_READ"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runner_plan_guard.review(changed)


class FullCleanupTests(unittest.TestCase):
    def setup(self, target="runner"):
        return {"GITHUB_REPOSITORY": "mhachem110/BankingReleasePlatform-AWS-EKS",
                "GITHUB_REF": "refs/heads/dev", "CLEANUP_ENABLED": "true", "AWS_OPERATIONS_ENABLED": "false",
                "ROLE_ARN": BOOTSTRAP, "AWS_EXPECTED_ACCOUNT_ID": ACCOUNT, "AWS_REGION": REGION,
                "TF_STATE_BUCKET": BUCKET, "TARGET": target, "OPERATION": "plan",
                "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "DATA_DISPOSITION": "FINAL-SNAPSHOT-RETAIN"}

    def test_full_cleanup_requires_data_decision_and_second_review(self):
        self.assertEqual(cleanup_full.inputs(self.setup("dev-data"))["key"], cleanup_full.KEYS["dev-data"])
        with self.assertRaisesRegex(ValueError, "snapshot"):
            cleanup_full.inputs(self.setup("prod-data") | {"DATA_DISPOSITION": "none"})
        with self.assertRaisesRegex(ValueError, "phrase"):
            cleanup_full.inputs(self.setup() | {"OPERATION": "apply", "APPROVAL": ""})
        with self.assertRaisesRegex(ValueError, "protected cleanup"):
            cleanup_full.inputs(self.setup() | {"AWS_OPERATIONS_ENABLED": "true"})

    def test_full_destroy_caps_fit_and_cannot_touch_backend_bucket(self):
        for target in cleanup_full.KEYS:
            cfg = cleanup_full.inputs(self.setup(target))
            self.assertLessEqual(len(cleanup_full.read_cap(cfg)), 2048)
            cap = json.loads(cleanup_full.delete_cap(cfg))
            self.assertLessEqual(len(cleanup_full.delete_cap(cfg)), 2048)
            self.assertNotIn("s3:DeleteBucket", json.dumps(cap))
            self.assertNotIn("cloudops-bootstrap", json.dumps(cap))
            self.assertNotIn("Retail", json.dumps(cap))

    def test_runner_teardown_rejects_unowned_or_missing_resource(self):
        env = self.setup()
        cfg = cleanup_full.inputs(env)
        resources = []
        for address in cleanup_full.inventory("runner"):
            kind, name = address.split(".", 1)
            value = {"id": name}
            if kind not in cleanup_full.UNTAGGABLE:
                value["tags"] = {"Project": "BankingReleasePlatform", "Environment": "shared", "ManagedBy": "Terraform"}
            if address == "aws_codebuild_project.runner":
                value.update(name="banking-release-deployer", project_visibility="PRIVATE")
            if address == "aws_iam_role.runner":
                value["arn"] = f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-codebuild-runner"
            resources.append({"mode": "managed", "type": kind, "name": name,
                              "instances": [{"attributes": value}]})
        state = {"lineage": "lineage", "serial": 1, "resources": resources}
        self.assertEqual(len(cleanup_full.state_review(state, cfg, env)["inventory"]), len(resources))
        broken = copy.deepcopy(state)
        next(r for r in broken["resources"] if r["type"] == "aws_codebuild_project")["instances"][0]["attributes"]["tags"]["Project"] = "Retail"
        with self.assertRaisesRegex(ValueError, "Unowned"):
            cleanup_full.state_review(broken, cfg, env)
        broken = copy.deepcopy(state)
        broken["resources"].pop()
        with self.assertRaisesRegex(ValueError, "exact complete"):
            cleanup_full.state_review(broken, cfg, env)


if __name__ == "__main__":
    unittest.main()
