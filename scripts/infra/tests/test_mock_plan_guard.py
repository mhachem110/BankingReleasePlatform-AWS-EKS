"""Exercise the saved-plan guard against Terraform's real mock-plan encoding."""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from guard import verify_plan


class MockPlanGuardTests(unittest.TestCase):
    def test_actual_fargate_plan_is_accepted_without_ec2_or_role_resources(self):
        self.assertIsNotNone(shutil.which("terraform"), "Terraform must be installed for infrastructure validation.")
        result = subprocess.run(
            ["terraform", "-chdir=infra/environments/dev/platform", "test", "-json", "-verbose"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        event = next(e for e in events if e.get("type") == "test_plan" and e.get("@testrun") == "integrated_plan")
        # Terraform test emits resource payloads without saved-plan header flags.
        # Preserve its actual changes; only supply those envelope flags here.
        plan = dict(event["test_plan"], applyable=True, complete=True)
        report = verify_plan(plan)
        kinds = [r["type"] for r in report["resources"]]
        self.assertEqual(kinds.count("aws_eks_fargate_profile"), 3)
        self.assertEqual(kinds.count("aws_iam_openid_connect_provider"), 1)
        self.assertEqual(kinds.count("aws_eks_addon"), 2)
        self.assertNotIn("aws_eks_node_group", kinds)
        self.assertNotIn("aws_iam_role", kinds)
        self.assertEqual(report["managed_updates"], 0)
        self.assertEqual(report["managed_deletes"], 0)


if __name__ == "__main__":
    unittest.main()
