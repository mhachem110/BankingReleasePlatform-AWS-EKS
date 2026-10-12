"""Exercise the saved-plan guard against Terraform's real mock-plan encoding."""
import json
import shutil
import subprocess
import sys
import unittest
import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from guard import verify_plan
spec = importlib.util.spec_from_file_location("plan_audit", ROOT / "scripts/infra/plan-audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MockPlanGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("terraform"):
            raise RuntimeError("Terraform must be installed for infrastructure validation.")
        result = subprocess.run(
            ["terraform", "-chdir=infra/environments/dev/platform", "test", "-json", "-verbose"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        event = next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == "integrated_plan")
        # Terraform test emits resource payloads without saved-plan header flags.
        # Preserve its actual changes; only supply those envelope flags here.
        cls.plan = dict(resource_changes=event["test_plan"]["resource_changes"], applyable=True, complete=True)
        account = "123456789012"
        from guard import ROLE_NAMES
        cls.inputs = {field: f"arn:aws:iam::{account}:role/{name}" for field, name in ROLE_NAMES.items()}
        cls.inputs.update(operator_role_arn=f"arn:aws:iam::{account}:role/test-operator",
            deployer_role_arn=f"arn:aws:iam::{account}:role/test-deployer", owner="MahmoudHachem",
            kms_key_arn=f"arn:aws:kms:us-east-2:{account}:key/11111111-2222-4333-8444-555555555555",
            endpoint_cidrs=["203.0.113.10/32"], availability_zones=["us-east-2a", "us-east-2b"],
            kubernetes_version="1.36", addon_versions={n:"v1.0.0-eksbuild.1" for n in ("coredns", "metrics-server")})

    def test_actual_fargate_plan_is_accepted_without_ec2_or_role_resources(self):
        plan = self.plan
        report = verify_plan(plan)
        kinds = [r["type"] for r in report["resources"]]
        self.assertEqual(kinds.count("aws_eks_fargate_profile"), 3)
        self.assertEqual(kinds.count("aws_iam_openid_connect_provider"), 1)
        self.assertEqual(kinds.count("aws_eks_addon"), 2)
        self.assertNotIn("aws_eks_node_group", kinds)
        self.assertNotIn("aws_iam_role", kinds)
        self.assertEqual(report["managed_updates"], 0)
        self.assertEqual(report["managed_deletes"], 0)
        report = audit.audit(plan, self.inputs, require_effective_tags=False)
        self.assertEqual(report["taggable_resources"], 31)
        self.assertFalse(report["effective_tags_verified"])

    def test_live_guard_requires_resolved_effective_tags(self):
        with self.assertRaisesRegex(ValueError, "tags_all"):
            audit.audit(self.plan, self.inputs)

    def test_effective_tag_conflict_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        for item in plan["resource_changes"]:
            if item.get("mode") == "managed" and item["type"] not in audit.UNTAGGABLE:
                item["change"]["after"]["tags_all"] = dict(item["change"]["after"]["tags"])
        audit.audit(plan, self.inputs)
        next(r for r in plan["resource_changes"] if r["type"] == "aws_vpc")["change"]["after"]["tags_all"]["Owner"] = "OtherProject"
        with self.assertRaises(ValueError):
            audit.audit(plan, self.inputs)

    def test_configuration_and_tag_regressions_rejected(self):
        cases = [
            ("module.network.aws_vpc.this", "enable_dns_support", False),
            ('module.network.aws_subnet.application["0"]', "map_public_ip_on_launch", True),
            ('module.network.aws_subnet.database["0"]', "cidr_block", "10.70.32.0/20"),
            ("module.eks.aws_eks_cluster.this", "bootstrap_self_managed_addons", True),
            ('module.registry.aws_ecr_repository.service["account"]', "force_delete", True),
            ("module.network.aws_cloudwatch_log_group.flow", "retention_in_days", 0),
            ("module.network.aws_vpc.this", "tags", {"Project": "BankingReleasePlatform"}),
        ]
        for address, field, value in cases:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                next(r for r in plan["resource_changes"] if r["address"] == address)["change"]["after"][field] = value
                with self.assertRaises(ValueError):
                    audit.audit(plan, self.inputs, require_effective_tags=False)

    def test_missing_or_extra_resource_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["resource_changes"].pop()
        with self.assertRaises(ValueError):
            audit.audit(plan, self.inputs, require_effective_tags=False)

    def test_cost_center_is_optional_not_fabricated(self):
        self.assertNotIn("CostCenter", audit.common_tags(self.inputs))
        self.assertEqual(audit.common_tags(dict(self.inputs, cost_center="approved-test"))["CostCenter"], "approved-test")


if __name__ == "__main__":
    unittest.main()
