import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

def load(name):
    path = Path(__file__).parents[1] / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

backend = load("write-backend-config.py")
environment = load("check-github-environment.py")
bucket = load("verify-state-bucket.py")

class BackendSafetyTests(unittest.TestCase):
    def setUp(self):
        self.values = {"TF_STATE_BUCKET": "banking-offline-test-fixture", "AWS_REGION": "us-east-1", "AWS_EXPECTED_ACCOUNT_ID": "0" * 12}

    def test_backend_locks_and_isolates_state(self):
        config = backend.configuration(self.values, "banking-release-platform/bootstrap/terraform.tfstate")
        self.assertTrue(config["encrypt"])
        self.assertTrue(config["use_lockfile"])
        self.assertEqual("banking-release-platform/_workspaces", config["workspace_key_prefix"])
        self.assertEqual(["0" * 12], config["allowed_account_ids"])

    def test_foreign_state_key_is_rejected(self):
        with self.assertRaises(ValueError):
            backend.configuration(self.values, "retail/bootstrap.tfstate")

    def test_foreign_kms_account_is_rejected(self):
        self.values["TF_STATE_KMS_KEY_ARN"] = "arn:aws:kms:us-east-1:" + "1" * 12 + ":key/test"
        with self.assertRaises(ValueError):
            backend.configuration(self.values, "banking-release-platform/bootstrap/terraform.tfstate")

    def test_unprotected_environment_fails_before_aws_authentication(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"}), patch.object(environment, "get", return_value={"protection_rules": []}):
            with self.assertRaises(RuntimeError):
                environment.main()

    def test_branch_wildcard_cannot_authorize_environment(self):
        env = {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}], "deployment_branch_policy": {"custom_branch_policies": True}, "can_admins_bypass": False}
        policies = {"total_count": 1, "branch_policies": [{"name": "*", "type": "branch"}]}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"}), patch.object(environment, "get", side_effect=[env, policies]):
            with self.assertRaises(RuntimeError):
                environment.main()

    def test_only_dev_branch_can_authorize_bootstrap_environment(self):
        env = {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}], "deployment_branch_policy": {"custom_branch_policies": True}, "can_admins_bypass": False}
        for name, kind, allowed in [("dev", "branch", True), ("main", "branch", False), ("dev", "tag", False)]:
            with self.subTest(name=name, kind=kind):
                policies = {"total_count": 1, "branch_policies": [{"name": name, "type": kind}]}
                with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/repo"}), patch.object(environment, "get", side_effect=[env, policies]):
                    if allowed:
                        environment.main()
                    else:
                        with self.assertRaises(RuntimeError):
                            environment.main()

    def test_bucket_wrong_region_is_rejected(self):
        argv = ["verify", "--bucket", "banking-offline-test-fixture", "--account", "0" * 12, "--region", "us-west-2"]
        with patch("sys.argv", argv), patch.object(bucket, "aws", side_effect=[{"LocationConstraint": "us-east-1"}]):
            with self.assertRaises(RuntimeError):
                bucket.main()

    def test_bucket_suspended_versioning_is_rejected(self):
        argv = ["verify", "--bucket", "banking-offline-test-fixture", "--account", "0" * 12, "--region", "us-east-1"]
        with patch("sys.argv", argv), patch.object(bucket, "aws", side_effect=[{}, {"Status": "Suspended"}]):
            with self.assertRaises(RuntimeError):
                bucket.main()

if __name__ == "__main__":
    unittest.main()
