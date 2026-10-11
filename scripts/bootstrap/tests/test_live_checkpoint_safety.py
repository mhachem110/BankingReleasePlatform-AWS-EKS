import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


locks = load("verify-state-lock.py")
plans = load("verify-bootstrap-plan.py")
bucket_check = load("verify-state-bucket.py")
diagnosis = load("inspect-lifecycle.py")
ACCOUNT = "0" * 12
BUCKET = "mhachem-banking-tfstate-" + ACCOUNT


class LiveLockSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.directory.name)
        path = Path("infra/bootstrap/.terraform")
        path.mkdir(parents=True)
        (path / "terraform.tfstate").write_text(json.dumps({"backend": {"type": "s3", "config": {
            "bucket": BUCKET, "key": locks.ROOT_KEYS["infra/bootstrap"], "region": "us-east-2", "use_lockfile": True}}}))
        self.calls, self.held = [], {}
        self.existing, self.changed, self.plan_succeeds, self.read_denied = False, False, False, False

    def tearDown(self):
        os.chdir(self.previous)
        self.directory.cleanup()

    def runner(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == "terraform":
            return subprocess.CompletedProcess(command, 0 if self.plan_succeeds else 1, "",
                                               "Error acquiring the state lock: " + self.held["ID"])
        operation = command[2]
        if operation == "put-object":
            if self.existing:
                return subprocess.CompletedProcess(command, 254, "", "(PreconditionFailed) Existing lock")
            self.held = json.loads(Path(command[command.index("--body") + 1]).read_text())
            return subprocess.CompletedProcess(command, 0, '{"ETag":"test-etag"}', "")
        if operation == "get-object":
            if self.read_denied:
                return subprocess.CompletedProcess(command, 254, "", "(AccessDenied) Cannot read lock")
            document = dict(self.held, ID="different-lock") if self.changed else self.held
            Path(command[command.index("--output") - 1]).write_text(json.dumps(document))
            return subprocess.CompletedProcess(command, 0, '{"ETag":"test-etag"}', "")
        if operation == "delete-object":
            return subprocess.CompletedProcess(command, 0, "{}", "")
        return subprocess.CompletedProcess(command, 254, "", "(404) Not Found")

    def verify(self):
        locks.verify(BUCKET, ACCOUNT, "us-east-2", "infra/bootstrap", runner=self.runner)

    def test_contention_and_cleanup_are_conditional_and_scoped(self):
        self.verify()
        put, delete = self.calls[0], next(c for c in self.calls if c[2] == "delete-object")
        self.assertEqual("*", put[put.index("--if-none-match") + 1])
        self.assertEqual("test-etag", delete[delete.index("--if-match") + 1])
        for call in self.calls:
            if call[0] == "aws":
                self.assertEqual(BUCKET, call[call.index("--bucket") + 1])
                self.assertEqual(locks.ROOT_KEYS["infra/bootstrap"] + ".tflock", call[call.index("--key") + 1])
        self.assertFalse(any("force-unlock" in call for call in self.calls))

    def test_existing_lock_is_never_deleted_or_overwritten(self):
        self.existing = True
        with self.assertRaises(RuntimeError):
            self.verify()
        self.assertEqual(1, len(self.calls))

    def test_changed_lock_identity_is_left_untouched(self):
        self.changed = True
        with self.assertRaises(RuntimeError):
            self.verify()
        self.assertFalse(any(c[2] == "delete-object" for c in self.calls))

    def test_unexpected_plan_success_fails_and_cleans_up_owned_lock(self):
        self.plan_succeeds = True
        with self.assertRaises(RuntimeError):
            self.verify()
        self.assertTrue(any(c[2] == "delete-object" for c in self.calls))

    def test_denied_lock_read_never_causes_blind_deletion(self):
        self.read_denied = True
        with self.assertRaises(RuntimeError):
            self.verify()
        self.assertFalse(any(c[2] == "delete-object" for c in self.calls))

    def test_wrong_backend_or_region_never_writes_a_lock(self):
        for region, name in [("us-west-2", BUCKET), ("us-east-2", "other-bucket")]:
            with self.assertRaises(ValueError):
                locks.verify(name, ACCOUNT, region, "infra/bootstrap", runner=self.runner)
        Path("infra/bootstrap/.terraform/terraform.tfstate").write_text('{"backend":{"type":"local","config":{}}}')
        with self.assertRaises(RuntimeError):
            self.verify()
        self.assertEqual([], self.calls)


class VerificationPlanTests(unittest.TestCase):
    def test_lifecycle_diagnosis_accepts_only_the_reproduced_filter_difference(self):
        before = {"rule": [{"filter": [], "noncurrent_version_expiration": [{"noncurrent_days": 90}],
                            "abort_incomplete_multipart_upload": [{"days_after_initiation": 7}], "expiration": []}]}
        after = copy.deepcopy(before)
        after["rule"][0]["filter"] = [{"and": [], "object_size_greater_than": None,
                                      "object_size_less_than": None, "prefix": "", "tag": []}]
        change = {"actions": ["update"], "before": before, "after": after}
        diagnosis.filter_only_difference(change)
        for field, value in [("expiration", [{"days": 1}]), ("filter", [{"prefix": "subset/"}]),
                             ("noncurrent_version_expiration", [{"noncurrent_days": 1}])]:
            altered = copy.deepcopy(change)
            altered["after"]["rule"][0][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                diagnosis.filter_only_difference(altered)

    def test_any_managed_resource_mutation_is_rejected(self):
        for actions in [["create"], ["update"], ["delete"], ["delete", "create"]]:
            with self.subTest(actions=actions), self.assertRaises(RuntimeError):
                plans.verify({"resource_changes": [{"address": "module.state_bucket.aws_s3_bucket.state",
                             "mode": "managed", "change": {"actions": actions}}]})

    def test_output_changes_and_read_only_data_are_allowed(self):
        plans.verify({"resource_changes": [{"address": "data.aws_caller_identity.current", "mode": "data",
                      "change": {"actions": ["read"]}}], "output_changes": {"key": {"actions": ["create"]}}})

    def test_lifecycle_cannot_expire_current_state(self):
        lifecycle = {"Status": "Enabled", "Filter": {}, "NoncurrentVersionExpiration": {"NoncurrentDays": 90},
                     "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}, "Expiration": {"Days": 1}}
        arn = "arn:aws:s3:::" + BUCKET
        values = [{"LocationConstraint": "us-east-2"}, {"Status": "Enabled"},
                  {"PublicAccessBlockConfiguration": {k: True for k in ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"]}},
                  {"ServerSideEncryptionConfiguration": {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}},
                  {"OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}},
                  {"Policy": json.dumps({"Statement": [{"Effect": "Deny", "Principal": "*", "Action": "s3:*",
                   "Resource": [arn, arn + "/*"], "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]})},
                  {"Rules": [lifecycle]}]
        with patch("sys.argv", ["verify", "--bucket", BUCKET, "--account", ACCOUNT, "--region", "us-east-2"]), \
                patch.object(bucket_check, "aws", side_effect=values), self.assertRaises(RuntimeError):
            bucket_check.main()
