import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("iam", Path(__file__).parents[1] / "check-iam-configuration.py")
iam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iam)

class IamInspectionTests(unittest.TestCase):
    def test_denied_read_reports_aws_reason_without_suppressing_it(self):
        result = subprocess.CompletedProcess([], 254, "", "An error occurred (AccessDenied): no identity-based policy allows iam:GetRole")
        output = io.StringIO()
        with patch.object(iam.subprocess, "run", return_value=result), contextlib.redirect_stdout(output):
            self.assertIsNone(iam.read("get-role", "--role-name", "fixture"))
        self.assertIn("no identity-based policy allows iam:GetRole", output.getvalue())

    def test_all_read_blockers_are_collected_before_failing(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"AWS_EXPECTED_ACCOUNT_ID": "0" * 12, "ROLE_ARN": "fixture"}), \
             patch.object(iam, "read", return_value=None) as reader, contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "IAM verification incomplete"):
                iam.main()
        self.assertEqual(6, reader.call_count)
        self.assertIn("CloudOpsTrackerBootstrap", output.getvalue())
        self.assertIn("BankingReleasePlatformState", output.getvalue())
        self.assertIn("OIDC provider", output.getvalue())

    def test_complete_matching_configuration_uses_only_reads(self):
        account = "0" * 12
        arn = f"arn:aws:iam::{account}:role/cloudbatch818-mahmoud-cloudops-bootstrap"
        trust = {"Sid": "FixtureTrust", "Effect": "Allow"}
        policy = {"Version": "2012-10-17", "Statement": []}
        def reader(operation, *arguments):
            return {
                "get-open-id-connect-provider": {"Url": "token.actions.githubusercontent.com", "ClientIDList": ["sts.amazonaws.com"]},
                "get-role": {"Role": {"Arn": arn, "AssumeRolePolicyDocument": {"Statement": [trust]}}},
                "list-role-policies": {"PolicyNames": ["FixturePolicy"]},
                "list-attached-role-policies": {"AttachedPolicies": []},
                "get-role-policy": {"PolicyDocument": policy},
            }[operation]
        with patch.dict(os.environ, {"AWS_EXPECTED_ACCOUNT_ID": account, "ROLE_ARN": arn}), \
             patch.object(iam, "POLICIES", {"FixturePolicy": iam.fingerprint(policy)}), \
             patch.object(iam, "TRUST", {"FixtureTrust": iam.fingerprint(trust)}), \
             patch.object(iam, "read", side_effect=reader) as calls, contextlib.redirect_stdout(io.StringIO()):
            iam.main()
        self.assertTrue(all(call.args[0].startswith(("get-", "list-")) for call in calls.call_args_list))
