import importlib.util
import unittest
from pathlib import Path

script = Path(__file__).parents[1] / "prepare-iam-policies.py"
spec = importlib.util.spec_from_file_location("policies", script)
policies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policies)

class PolicySafetyTests(unittest.TestCase):
    def test_existing_trust_is_preserved(self):
        current = {"Version": "2012-10-17", "Statement": [{"Sid": "ExistingProject", "Effect": "Allow", "Action": "sts:AssumeRoleWithWebIdentity", "Principal": {"Federated": "existing-test-principal"}}]}
        settings = {"use_default": True, "use_immutable_subject": True, "sub_claim_prefix": "repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979"}
        updated = policies.trust_update(current, "0" * 12, settings)
        self.assertEqual(current["Statement"][0], updated["Statement"][0])
        self.assertEqual(1, len(current["Statement"]))
        self.assertEqual(2, len(updated["Statement"]))
        self.assertEqual(updated, policies.trust_update(updated, "0" * 12, settings))

    def test_wrong_oidc_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            policies.trust_update({"Statement": []}, "0" * 12, {"sub_claim_prefix": "repo:wrong/repo"})

    def test_shared_bucket_has_no_bucket_write_permissions(self):
        result = policies.s3_addition("banking-offline-test-fixture", "reuse")
        actions = [action for s in result["Statement"] for action in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])]
        self.assertFalse(set(actions).intersection(policies.BUCKET_WRITE))
        self.assertNotIn("s3:DeleteBucket", actions)

    def test_deletion_is_limited_to_lock_files(self):
        for mode in ("reuse", "dedicated"):
            result = policies.s3_addition("banking-offline-test-fixture", mode)
            delete = [s for s in result["Statement"] if "s3:DeleteObject" in s["Action"]]
            self.assertEqual(1, len(delete))
            self.assertTrue(all(arn.endswith(".tflock") for arn in delete[0]["Resource"]))
            self.assertFalse(any("iam:" in str(s["Action"]) for s in result["Statement"]))

if __name__ == "__main__":
    unittest.main()
