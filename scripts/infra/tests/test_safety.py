import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from guard import STATE_KEY, ROLE_NAMES, configuration, session_policy, verify_plan
from preflight import overlaps, verify_service_role, verify_addon_schema, verify_addon_version, verify_managed_policies
spec = importlib.util.spec_from_file_location("admin", ROOT / "scripts/infra/prepare-admin-request.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)


def fixture():
    account = "866934333672"
    inputs = {field: f"arn:aws:iam::{account}:role/{name}" for field, name in ROLE_NAMES.items()}
    inputs.update(operator_role_arn=f"arn:aws:iam::{account}:role/operator",
                  deployer_role_arn=f"arn:aws:iam::{account}:role/deployer",
                  prod_deployer_role_arn=f"arn:aws:iam::{account}:role/prod-deployer",
                  kms_key_arn=f"arn:aws:kms:us-east-2:{account}:key/00000000-0000-0000-0000-000000000000")
    return dict(ROLE_ARN="arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-cloudops-bootstrap", IAM_PREREQUISITES_READY="true", IAM_BOUNDARY_POLICY_SHA256="a"*64, GITHUB_REF="refs/heads/dev", AWS_OPERATIONS_ENABLED="true", BOOTSTRAP_STATE_READY="true",
                OPERATION="plan", AWS_EXPECTED_ACCOUNT_ID=account, AWS_REGION="us-east-2",
                TF_STATE_BUCKET="mhachem-banking-tfstate-" + account, PLATFORM_INPUTS_JSON=json.dumps(inputs))


class SafetyTests(unittest.TestCase):
    def test_administrator_tags_match_actual_ownership(self):
        values = configuration(fixture())
        args = (values["expected_account_id"], "us-east-2", values["state_bucket_name"], values["kms_key_arn"])
        tags = admin.policies(*args)["BankingAdministratorTags.json"]
        self.assertTrue(all(t["ManagedBy"] == "Administrator" and "CostCenter" not in t for t in tags.values()))
        self.assertEqual(tags, json.loads((ROOT / "infra/iam/phase3/proposed/BankingAdministratorTags.json").read_text()))
        alternate = admin.policies(*args, administrator_managed_by="ApprovedManual", cost_center="approved-test")["BankingAdministratorTags.json"]
        self.assertTrue(all(t["ManagedBy"] == "ApprovedManual" and t["CostCenter"] == "approved-test" for t in alternate.values()))
        with self.assertRaises(ValueError):
            admin.policies(*args, administrator_managed_by="Terraform")
        spec = importlib.util.spec_from_file_location("tag_audit", ROOT / "scripts/infra/plan-audit.py")
        tag_audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tag_audit)
        self.assertEqual(tag_audit.common_tags(values)["ManagedBy"], "Terraform")

    def test_same_named_customer_policy_cannot_substitute_for_aws_managed(self):
        name = "AmazonEKSClusterPolicy"
        verify_managed_policies([{"PolicyName":name,"PolicyArn":"arn:aws:iam::aws:policy/"+name}], {name})
        with self.assertRaises(ValueError):
            verify_managed_policies([{"PolicyName":name,"PolicyArn":"arn:aws:iam::123456789012:policy/"+name}], {name})
    def test_access_role_cannot_be_an_eks_service_identity(self):
        env = fixture()
        values = json.loads(env["PLATFORM_INPUTS_JSON"])
        values["operator_role_arn"] = values["cluster_role_arn"]
        env["PLATFORM_INPUTS_JSON"] = json.dumps(values)
        with self.assertRaises(ValueError):
            configuration(env)

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
        self.assertEqual(len(passes), 3)
        self.assertEqual({s["Resource"] for s in passes}, {values[k] for k in ROLE_NAMES})
        for statement in policy["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            self.assertNotIn("iam:CreateRole", actions)
            if "s3:DeleteObject" in actions:
                self.assertTrue(statement["Resource"].endswith(".tflock"))

    def test_controller_trust_exact_service_account(self):
        values = configuration(fixture())
        issuer = "https://oidc.eks.us-east-2.amazonaws.com/id/" + "A" * 32
        trust = admin.controller_trust(values["expected_account_id"], "us-east-2", issuer)["Statement"][0]
        self.assertEqual(trust["Action"], "sts:AssumeRoleWithWebIdentity")
        self.assertNotIn("Service", trust["Principal"])
        self.assertEqual(trust["Principal"]["Federated"], "arn:aws:iam::866934333672:oidc-provider/" + issuer[8:])
        self.assertEqual(trust["Condition"]["StringEquals"][issuer[8:] + ":sub"], "system:serviceaccount:kube-system:aws-load-balancer-controller")
        self.assertEqual(trust["Condition"]["StringEquals"][issuer[8:] + ":aud"], "sts.amazonaws.com")

    def test_controller_issuer_not_guessed(self):
        with self.assertRaises(ValueError):
            admin.controller_trust("123456789012", "us-east-2", "https://token.actions.githubusercontent.com")
        values = configuration(fixture())
        files = admin.policies(values["expected_account_id"], "us-east-2", values["state_bucket_name"], values["kms_key_arn"])
        self.assertNotIn(admin.CONTROLLER_ROLE + "-trust.json", files)

    def test_inputs_and_session_cap(self):
        values = configuration(fixture())
        cap = session_policy(values)
        self.assertLessEqual(len(cap), 2048)
        statements = json.loads(cap)["Statement"]
        for statement in statements:
            actions = statement["Action"]
            if isinstance(actions, str):
                actions = [actions]
            self.assertEqual(statement["Effect"], "Deny")
            self.assertIn("iam:CreateRole", actions)
        self.assertTrue(all(row["Effect"] == "Deny" for row in statements))

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
        values["fargate_execution_role_arn"] = values["fargate_execution_role_arn"].replace("banking", "retail")
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

    def test_fargate_execution_trust_bound_to_bank(self):
        values = configuration(fixture())
        files = admin.policies(values["expected_account_id"], "us-east-2", values["state_bucket_name"], values["kms_key_arn"])
        policy = files[ROLE_NAMES["fargate_execution_role_arn"] + "-trust.json"]
        role = {"Arn": values["fargate_execution_role_arn"], "AssumeRolePolicyDocument": policy, "PermissionsBoundary": {"PermissionsBoundaryArn": "arn:aws:iam::866934333672:policy/cloudbatch818-mahmoud-banking-service-boundary"}}
        verify_service_role("fargate_execution_role_arn", role, values)
        invalid = copy.deepcopy(role)
        invalid["AssumeRolePolicyDocument"]["Statement"][0]["Condition"]["ArnLike"]["aws:SourceArn"] = "*"
        with self.assertRaises(ValueError):
            verify_service_role("fargate_execution_role_arn", invalid, values)

    def test_fargate_role_path_rejected(self):
        env = fixture()
        inputs = json.loads(env["PLATFORM_INPUTS_JSON"])
        inputs["fargate_execution_role_arn"] = inputs["fargate_execution_role_arn"].replace(":role/", ":role/path/")
        env["PLATFORM_INPUTS_JSON"] = json.dumps(inputs)
        with self.assertRaises(ValueError):
            configuration(env)

    def test_addon_compatibility_requires_fargate(self):
        version = {"addonVersion": "v1.0.0-eksbuild.1", "architecture": ["amd64"], "computeTypes": ["Fargate"], "compatibilities": [{"clusterVersion": "1.36"}]}
        payload = {"addons": [{"addonVersions": [version]}]}
        verify_addon_version("coredns", version["addonVersion"], "1.36", payload)
        version["computeTypes"] = ["EC2"]
        with self.assertRaises(ValueError):
            verify_addon_version("coredns", version["addonVersion"], "1.36", payload)

    def test_addon_schema_validation_rejects_unsupported_fields(self):
        from jsonschema import ValidationError
        schema = {"type": "object", "additionalProperties": False, "properties": {"computeType": {"enum": ["Fargate"]}}}
        verify_addon_schema({"computeType": "Fargate"}, schema)
        with self.assertRaises(ValidationError):
            verify_addon_schema({"computeType": "Fargate", "invented": True}, schema)

    def test_new_cluster_oidc_only(self):
        item = {"mode": "managed", "type": "aws_iam_openid_connect_provider", "address": "module.eks.aws_iam_openid_connect_provider.cluster", "change": {"actions": ["create"], "after": {"url": "https://oidc.eks.us-east-2.amazonaws.com/id/" + "A"*32, "client_id_list": ["sts.amazonaws.com"], "tags": {"Project": "BankingReleasePlatform", "Environment": "dev"}}}}
        verify_plan({"applyable": True, "resource_changes": [item]})
        item["change"]["after"]["url"] = "https://token.actions.githubusercontent.com"
        with self.assertRaises(ValueError):
            verify_plan({"applyable": True, "resource_changes": [item]})

    def test_ec2_nodes_and_pod_identity_rejected(self):
        for kind in ["aws_eks_node_group", "aws_launch_template", "aws_eks_pod_identity_association"]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_plan({"applyable": True, "resource_changes": [{"mode": "managed", "type": kind, "address": "module.eks." + kind + ".this", "change": {"actions": ["create"]}}]})

    def test_addon_resources_guaranteed_and_no_network_policy_claim(self):
        config = json.loads((ROOT / "infra/modules/eks/addon-configuration.json").read_text())
        for value in config.values():
            self.assertEqual(value["resources"]["requests"], value["resources"]["limits"])
        self.assertNotIn("enableNetworkPolicy", json.dumps(config))
        source = (ROOT / "infra/modules/eks/main.tf").read_text()
        self.assertNotIn('resource "aws_iam_role"', source)

    def test_old_worker_inputs_rejected(self):
        env = fixture()
        values = json.loads(env["PLATFORM_INPUTS_JSON"])
        values["node_role_arn"] = "arn:aws:iam::123456789012:role/old-worker"
        env["PLATFORM_INPUTS_JSON"] = json.dumps(values)
        with self.assertRaises(ValueError):
            configuration(env)

    def test_cost_model_reproducible(self):
        spec = importlib.util.spec_from_file_location("cost", ROOT / "scripts/infra/cost-estimate.py")
        cost = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cost)
        result = cost.estimate(json.loads((ROOT / "infra/cost/cost-model.json").read_text()))
        self.assertEqual(result["subtotal_monthly_usd"], "240.61")
        self.assertIn("ALB/LCU/public IPv4 charges", result["excluded"])

    def test_cluster_provider_permissions_do_not_modify_github(self):
        values = configuration(fixture())
        files = admin.policies(values["expected_account_id"], "us-east-2", values["state_bucket_name"], values["kms_key_arn"])
        for statement in files["BankingReleasePlatformPhase3.json"]["Statement"]:
            actions = statement["Action"] if isinstance(statement["Action"], list) else [statement["Action"]]
            if any("OpenIDConnectProvider" in action for action in actions):
                self.assertIn(":oidc-provider/oidc.eks.us-east-2.amazonaws.com/id/", statement["Resource"])
                self.assertNotIn("iam:DeleteOpenIDConnectProvider", actions)
                self.assertNotIn("iam:UpdateOpenIDConnectProviderThumbprint", actions)
        self.assertNotIn("iam:CreateServiceLinkedRole", json.dumps(files))

    def test_admin_generator_preserves_returned_role_paths(self):
        values = configuration(fixture())
        cluster = values["cluster_role_arn"].replace(":role/", ":role/approved/")
        files = admin.policies(values["expected_account_id"], "us-east-2", values["state_bucket_name"],
                               values["kms_key_arn"], role_arns={"cluster_role_arn": cluster})
        statement = files["BankingReleasePlatformPhase3.json"]["Statement"][0]
        self.assertEqual(statement["Resource"], cluster)
        self.assertEqual(statement["Condition"]["StringEquals"]["iam:PassedToService"], "eks.amazonaws.com")


if __name__ == "__main__":
    unittest.main()
