import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from guard import STATE_KEY, ROLE_NAMES, configuration, session_policy, verify_plan
from preflight import overlaps
spec = importlib.util.spec_from_file_location("admin", ROOT / "scripts/infra/prepare-admin-request.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


def fixture():
    account = "123456789012"
    inputs = {field: f"arn:aws:iam::{account}:role/{name}" for field, name in ROLE_NAMES.items()}
    inputs.update(operator_role_arn=f"arn:aws:iam::{account}:role/operator",
                  deployer_role_arn=f"arn:aws:iam::{account}:role/deployer",
                  kms_key_arn=f"arn:aws:kms:us-east-2:{account}:key/00000000-0000-0000-0000-000000000000")
    return dict(GITHUB_REF="refs/heads/dev", AWS_OPERATIONS_ENABLED="true", BOOTSTRAP_STATE_READY="true",
                OPERATION="plan", AWS_EXPECTED_ACCOUNT_ID=account, AWS_REGION="us-east-2",
                TF_STATE_BUCKET="mhachem-banking-tfstate-" + account, PLATFORM_INPUTS_JSON=json.dumps(inputs))


class SafetyTests(unittest.TestCase):
    def test_provider_locks_cover_windows_and_linux(self):
        import re
        reference = (ROOT / "infra/bootstrap/.terraform.lock.hcl").read_text()
        hashes = set(re.findall(r'"h1:[^"]+"', reference))
        self.assertGreaterEqual(len(hashes), 2)
        for path in ["infra/modules/network", "infra/modules/registry", "infra/modules/eks", "infra/environments/dev/platform"]:
            with self.subTest(path=path):
                lock = (ROOT / path / ".terraform.lock.hcl").read_text()
                self.assertIn('version     = "6.68.0"', lock)
                self.assertTrue(hashes <= set(re.findall(r'"h1:[^"]+"', lock)))

    def test_additive_admin_permissions(self):
        values = configuration(fixture())
        files = admin.policies(values["expected_account_id"], values["aws_region"], values["state_bucket_name"], values["kms_key_arn"])
        self.assertNotIn("CloudOpsTrackerBootstrap.json", files)
        self.assertNotIn("BankingReleasePlatformState.json", files)
        policy = files["BankingReleasePlatformPhase3.json"]
        passes = [s for s in policy["Statement"] if s["Action"] == "iam:PassRole"]
        self.assertEqual(len(passes), 4)
        self.assertEqual({s["Resource"] for s in passes}, {values[k] for k in ROLE_NAMES})
        for statement in policy["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            self.assertNotIn("iam:CreateRole", actions)
            if "s3:DeleteObject" in actions:
                self.assertTrue(statement["Resource"].endswith(".tflock"))

    def test_controller_trust_exact_service_account(self):
        values = configuration(fixture())
        files = admin.policies(values["expected_account_id"], values["aws_region"], values["state_bucket_name"], values["kms_key_arn"])
        trust = files[ROLE_NAMES["controller_role_arn"] + "-trust.json"]["Statement"][0]
        self.assertEqual(trust["Principal"], {"Service": "pods.eks.amazonaws.com"})
        self.assertIn("sts:TagSession", trust["Action"])
        self.assertEqual(trust["Condition"]["StringEquals"]["aws:RequestTag/kubernetes-service-account"], "aws-load-balancer-controller")

    def test_inputs_and_session_cap(self):
        values = configuration(fixture())
        cap = session_policy(values)
        self.assertLessEqual(len(cap), 2048)
        statements = json.loads(cap)["Statement"]
        for statement in statements:
            actions = statement["Action"]
            if isinstance(actions, str):
                actions = [actions]
            self.assertFalse(any(action in ["iam:*", "iam:CreateRole", "iam:PutRolePolicy", "s3:CreateBucket"] for action in actions))
        objects = [statement for statement in statements if statement["Action"] == ["s3:GetObject", "s3:PutObject"]]
        self.assertEqual(objects[0]["Resource"].split("/", 3)[-1], "platform/terraform.tfstate")

    def test_gates_fail_closed(self):
        for key, value in [("GITHUB_REF", "refs/heads/infra"), ("AWS_OPERATIONS_ENABLED", "false"),
                           ("BOOTSTRAP_STATE_READY", "false"), ("OPERATION", "destroy"),
                           ("AWS_REGION", "us-east-1"), ("TF_STATE_BUCKET", "retail-state")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration(dict(fixture(), **{key: value}))

    def test_apply_requires_exact_approval(self):
        with self.assertRaises(ValueError):
            configuration(dict(fixture(), OPERATION="apply", APPROVAL="APPLY-REVIEWED-PLAN"))
        configuration(dict(fixture(), OPERATION="apply", APPROVAL="APPLY-REVIEWED-PHASE3-PLAN"))

    def test_retail_role_cannot_be_reused(self):
        env = fixture()
        values = json.loads(env["PLATFORM_INPUTS_JSON"])
        values["node_role_arn"] = values["node_role_arn"].replace("banking", "retail")
        env["PLATFORM_INPUTS_JSON"] = json.dumps(values)
        with self.assertRaises(ValueError):
            configuration(env)

    def test_existing_resource_mutations_rejected(self):
        for actions in [["update"], ["delete"], ["delete", "create"], ["create", "delete"]]:
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                verify_plan({"applyable": True, "resource_changes": [{"mode": "managed", "type": "aws_vpc", "address": "module.network.aws_vpc.this", "change": {"actions": actions}}]})

    def test_new_banking_resources_allowed(self):
        result = verify_plan({"applyable": True, "complete": True, "resource_changes": [{"mode": "managed", "type": "aws_vpc", "address": "module.network.aws_vpc.this", "change": {"actions": ["create"]}}]})
        self.assertEqual(result["managed_creates"], 1)

    def test_bucket_and_iam_changes_rejected(self):
        for kind in ["aws_s3_bucket", "aws_iam_role", "aws_iam_role_policy", "aws_db_instance"]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_plan({"applyable": True, "resource_changes": [{"mode": "managed", "type": kind, "address": "module.network." + kind + ".this", "change": {"actions": ["create"]}}]})

    def test_secondary_cidr_overlap_rejected(self):
        with self.assertRaises(ValueError):
            overlaps("10.70.0.0/16", [{"CidrBlockAssociationSet": [{"CidrBlock": "10.70.64.0/24", "CidrBlockState": {"State": "associated"}}]}])
        overlaps("10.70.0.0/16", [{"CidrBlockAssociationSet": [{"CidrBlock": "10.20.0.0/16", "CidrBlockState": {"State": "associated"}}]}])

    def test_phase2_state_paths_unchanged(self):
        self.assertNotIn(STATE_KEY, (ROOT / "scripts/bootstrap/workflow-config.py").read_text())
        self.assertNotIn('module "network"', (ROOT / "infra/environments/dev/main.tf").read_text())

    def test_workflow_protected_and_separate(self):
        workflow = (ROOT / ".github/workflows/infra-operations.yml").read_text()
        self.assertEqual(workflow.count("environment: bootstrap"), 2)
        self.assertIn("cmp platform.tfvars.json reviewed/platform.tfvars.json", workflow)
        self.assertIn("sha256sum --check --strict", workflow)
        self.assertIn("needs: [prerequisites, plan]", workflow)
        self.assertNotIn("terraform destroy", workflow)
        self.assertNotIn("force-unlock", workflow)
        self.assertNotIn("pull_request_target", workflow)


if __name__ == "__main__":
    unittest.main()
