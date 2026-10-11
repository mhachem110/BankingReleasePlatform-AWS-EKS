import importlib.util
import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load("workflow-config.py")
seed = load("initialize-state-bucket.py")
imports = load("import-state-bucket.py")
oidc = load("check-oidc-provider.py")
ACCOUNT = "0" * 12
BUCKET = "mhachem-banking-tfstate-" + ACCOUNT


def aws_error(code):
    return seed.AwsError("test", subprocess.CompletedProcess([], 1, "", f"An error occurred ({code})"))


class OperationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(AWS_EXPECTED_ACCOUNT_ID=ACCOUNT, AWS_REGION="us-east-2", TF_STATE_BUCKET=BUCKET,
                           ROLE_ARN=f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-bootstrap",
                           GITHUB_REF="refs/heads/dev", OPERATION="connectivity")

    def test_connectivity_cannot_create_bucket_or_access_retail_services(self):
        policy = json.loads(config.configuration(self.values)["session_policy"])
        self.assertEqual({"sts:GetCallerIdentity", "iam:GetOpenIDConnectProvider"}, {s["Action"] for s in policy["Statement"]})

    def test_wrong_ref_bucket_and_malformed_arn_are_rejected(self):
        for name, value in [("GITHUB_REF", "refs/heads/bootstrap"), ("TF_STATE_BUCKET", "mhachem-retail-fixture"),
                            ("ROLE_ARN", f"arn:aws:iam::{ACCOUNT}/cloudbatch818-mahmoud-cloudops-bootstrap")]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                config.configuration(dict(self.values, **{name: value}))

    def test_explicit_approval_is_needed_before_creation(self):
        self.values.update(OPERATION="initialize", DEDICATED_BUCKET_MANAGEMENT_APPROVED="true")
        with self.assertRaises(ValueError):
            config.configuration(self.values)
        self.values["APPROVAL"] = "CREATE-APPROVED-STATE-BUCKET"
        result = config.configuration(self.values)
        self.assertEqual("infra/bootstrap", result["root"])
        policy = json.loads(result["session_policy"])
        s3 = next(s for s in policy["Statement"] if s["Action"] == "s3:*")
        self.assertEqual(["arn:aws:s3:::" + BUCKET, "arn:aws:s3:::" + BUCKET + "/*"], s3["Resource"])
        self.assertLess(len(result["session_policy"]), 2048)

    def test_recovery_requires_a_different_approval(self):
        self.values.update(OPERATION="initialize", DEDICATED_BUCKET_MANAGEMENT_APPROVED="true", RESUME="true", APPROVAL="CREATE-APPROVED-STATE-BUCKET")
        with self.assertRaises(ValueError):
            config.configuration(self.values)
        self.values["APPROVAL"] = "RESUME-APPROVED-INITIALIZATION"
        config.configuration(self.values)

    def test_remote_operations_require_verified_state(self):
        self.values.update(OPERATION="plan")
        with self.assertRaises(ValueError):
            config.configuration(self.values)
        self.values.update(BOOTSTRAP_STATE_READY="true")
        config.configuration(self.values)

    def test_apply_requires_exact_approval(self):
        self.values.update(OPERATION="apply", BOOTSTRAP_STATE_READY="true")
        with self.assertRaises(ValueError):
            config.configuration(self.values)
        self.values["APPROVAL"] = "APPLY-REVIEWED-PLAN"
        config.configuration(self.values)

    def test_foreign_customer_kms_key_is_rejected(self):
        self.values.update(OPERATION="plan", BOOTSTRAP_STATE_READY="true", TF_STATE_KMS_KEY_ARN="arn:aws:kms:us-east-2:" + "1" * 12 + ":key/test")
        with self.assertRaises(ValueError):
            config.configuration(self.values)


class InitializationSafetyTests(unittest.TestCase):
    def test_denied_head_is_not_treated_as_absence(self):
        caller = Mock(side_effect=aws_error("403"))
        with self.assertRaises(RuntimeError):
            seed.seed(BUCKET, ACCOUNT, "us-east-2", caller=caller)
        self.assertEqual(1, caller.call_count)

    def test_existing_bucket_is_not_automatically_adopted(self):
        caller = Mock(return_value={})
        with self.assertRaises(RuntimeError):
            seed.seed(BUCKET, ACCOUNT, "us-east-2", caller=caller)
        self.assertEqual(1, caller.call_count)

    def test_creation_race_never_leads_to_bucket_configuration(self):
        caller = Mock(side_effect=[aws_error("404"), aws_error("BucketAlreadyOwnedByYou")])
        with self.assertRaises(seed.AwsError):
            seed.seed(BUCKET, ACCOUNT, "us-east-2", caller=caller)
        self.assertEqual(2, caller.call_count)

    def test_new_seed_has_region_security_and_no_current_state_expiry(self):
        caller = Mock(side_effect=[aws_error("404")] + [{}] * 8)
        seed.seed(BUCKET, ACCOUNT, "us-east-2", caller=caller)
        calls = {call.args[0]: call.args for call in caller.call_args_list}
        create = calls["create-bucket"]
        self.assertEqual({"LocationConstraint": "us-east-2"}, json.loads(create[create.index("--create-bucket-configuration") + 1]))
        for name in ["put-public-access-block", "put-bucket-versioning", "put-bucket-encryption", "put-bucket-policy", "put-bucket-ownership-controls", "put-bucket-lifecycle-configuration"]:
            self.assertIn("--expected-bucket-owner", calls[name])
        rule = json.loads(calls["put-bucket-lifecycle-configuration"][-1])["Rules"][0]
        self.assertNotIn("Expiration", rule)

    def test_recovery_checks_markers_before_writing(self):
        caller = Mock(side_effect=[{}, {"LocationConstraint": "us-east-2"}, {"TagSet": [{"Key": "Project", "Value": "Other"}]}])
        with self.assertRaises(RuntimeError):
            seed.seed(BUCKET, ACCOUNT, "us-east-2", resume=True, caller=caller)
        self.assertFalse(any(c.args[0].startswith("put-") for c in caller.call_args_list))

    def test_resume_of_absent_bucket_does_not_create_one(self):
        caller = Mock(side_effect=aws_error("404"))
        with self.assertRaises(RuntimeError):
            seed.seed(BUCKET, ACCOUNT, "us-east-2", resume=True, caller=caller)
        self.assertEqual(1, caller.call_count)


class ImportAndProviderSafetyTests(unittest.TestCase):
    def test_import_addresses_match_the_seven_actual_resources(self):
        source = (Path(__file__).parents[3] / "infra/modules/state-bucket/main.tf").read_text()
        actual = {f"module.state_bucket.{kind}.{name}" for kind, name in re.findall(r'resource "([^"]+)" "([^"]+)"', source)}
        self.assertEqual(imports.ADDRESSES, actual)
        self.assertEqual(7, len(actual))

    def test_foreign_resource_id_and_address_are_rejected(self):
        resource = {"module": "module.state_bucket", "type": "aws_s3_bucket", "name": "state", "mode": "managed", "instances": [{"attributes": {"id": BUCKET}}]}
        self.assertEqual({"module.state_bucket.aws_s3_bucket.state"}, imports.existing_resources({"resources": [resource]}, BUCKET))
        for field, value in [("module", "module.other"), ("type", "aws_iam_role")]:
            with self.assertRaises(RuntimeError):
                imports.existing_resources({"resources": [dict(resource, **{field: value})]}, BUCKET)
        with self.assertRaises(RuntimeError):
            imports.existing_resources({"resources": [resource]}, "other-bucket")

    def test_oidc_provider_requires_exact_issuer_and_audience(self):
        oidc.verify({"Url": "token.actions.githubusercontent.com", "ClientIDList": ["sts.amazonaws.com"]})
        for provider in [{"Url": "other.example", "ClientIDList": ["sts.amazonaws.com"]},
                         {"Url": "token.actions.githubusercontent.com", "ClientIDList": ["other-audience"]}]:
            with self.assertRaises(RuntimeError):
                oidc.verify(provider)
