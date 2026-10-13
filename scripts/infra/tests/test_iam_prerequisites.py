import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
from iam_contract import ACCOUNT, BOOTSTRAP, BOUNDARY, STATE_KEY, ROLE_ARNS, ROLE_NAMES, digest
from iam_guard import configuration, verify_plan, permission_simulations
from provisioner_policies import generate, additional_state, iam_stage, service_boundary
from platform_caps import review, verify


def env():
    boundary = json.loads((ROOT / "infra/iam/provisioning/proposed/BankingServicePermissionsBoundary.json").read_text())
    return dict(GITHUB_REF="refs/heads/dev", IAM_PREREQUISITES_ENABLED="true", BOOTSTRAP_STATE_READY="true", ROLE_ARN=BOOTSTRAP,
        AWS_REGION="us-east-2", AWS_EXPECTED_ACCOUNT_ID=ACCOUNT, TF_STATE_BUCKET="mhachem-banking-tfstate-" + ACCOUNT,
        IAM_BOUNDARY_POLICY_SHA256=digest(boundary), OPERATION="plan")


class IamPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["terraform", "-chdir=infra/iam-prerequisites", "test", "-json", "-verbose"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=90)
        plan = next(json.loads(line)["test_plan"] for line in run.stdout.splitlines() if json.loads(line).get("type") == "test_plan" and json.loads(line).get("@testrun") == "three_service_roles_only")
        cls.plan = dict(resource_changes=plan["resource_changes"], applyable=True, complete=True)
        cls.inputs = configuration(env())

    def test_actual_mock_inventory_has_only_three_roles(self):
        report = verify_plan(self.plan, self.inputs, effective_tags=False)
        self.assertEqual(len(report["iam_roles"]), 3)
        self.assertEqual(report["managed_creates"], 7)

    def test_live_plan_requires_resolved_effective_tags(self):
        with self.assertRaisesRegex(ValueError, "role tags"):
            verify_plan(self.plan, self.inputs)

    def test_extra_missing_import_update_delete_replace_rejected(self):
        for actions in (["update"], ["delete"], ["no-op"], ["delete", "create"]):
            plan = copy.deepcopy(self.plan)
            plan["resource_changes"][0]["change"]["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(ValueError):
                verify_plan(plan, self.inputs, False)
        for mutation in ("missing", "extra", "import"):
            plan = copy.deepcopy(self.plan)
            if mutation == "missing":
                plan["resource_changes"].pop()
            elif mutation == "extra":
                plan["resource_changes"].append(dict(plan["resource_changes"][0], address="aws_iam_role.unrelated"))
            else:
                plan["resource_changes"][0]["change"]["importing"] = {"id": "retail-role"}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_plan(plan, self.inputs, False)

    def test_trust_role_name_boundary_and_attachment_escalation_rejected(self):
        role_address = 'aws_iam_role.service["cluster"]'
        for field, value in (("name", "cloudbatch818-mahmoud-retail-admin"), ("permissions_boundary", None), ("path", "/unreviewed/"), ("assume_role_policy", json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": BOOTSTRAP}, "Action": "sts:AssumeRole"}]}))):
            plan = copy.deepcopy(self.plan)
            next(r for r in plan["resource_changes"] if r["address"] == role_address)["change"]["after"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_plan(plan, self.inputs, False)
        plan = copy.deepcopy(self.plan)
        next(r for r in plan["resource_changes"] if r["type"] == "aws_iam_role_policy_attachment")["change"]["after"]["policy_arn"] = "arn:aws:iam::aws:policy/AdministratorAccess"
        with self.assertRaises(ValueError):
            verify_plan(plan, self.inputs, False)

    def test_inline_flow_policy_cannot_gain_iam(self):
        plan = copy.deepcopy(self.plan)
        next(r for r in plan["resource_changes"] if r["type"] == "aws_iam_role_policy")["change"]["after"]["policy"] = json.dumps({"Statement": [{"Effect": "Allow", "Action": "iam:*", "Resource": "*"}]})
        with self.assertRaises(ValueError):
            verify_plan(plan, self.inputs, False)

    def test_disabled_wrong_identity_and_wrong_boundary_stop(self):
        for key, value in (("GITHUB_REF", "refs/heads/infra"), ("IAM_PREREQUISITES_ENABLED", "false"), ("ROLE_ARN", ROLE_ARNS["cluster"]), ("AWS_REGION", "us-east-1"), ("IAM_BOUNDARY_POLICY_SHA256", "b"*64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration(dict(env(), **{key: value}))
        with self.assertRaises(ValueError):
            configuration(dict(env(), OPERATION="apply", APPROVAL="APPLY-REVIEWED-PHASE3-PLAN"))
        configuration(dict(env(), OPERATION="apply", APPROVAL="APPLY-REVIEWED-BANKING-IAM-PLAN"))


class PolicyTests(unittest.TestCase):
    def test_proposals_are_reproducible_and_within_managed_quota(self):
        for name, doc in generate().items():
            self.assertEqual(doc, json.loads((ROOT / "infra/iam/provisioning/proposed" / name).read_text()))
            self.assertLessEqual(len(json.dumps(doc, separators=(",", ":"))), 6144)

    def test_aws_action_resource_compatibility_and_create_cluster_exception(self):
        spec = importlib.util.spec_from_file_location("sar_validator", ROOT / "scripts/infra/validate-provisioner-policies.py")
        validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)
        metadata = json.loads((ROOT / "infra/iam/provisioning/service-authorization-reference.json").read_text())
        docs = generate()
        self.assertGreater(validator.validate(docs, metadata)["aws_actions_checked"], 100)
        bad = copy.deepcopy(docs)
        row = next(s for doc in bad.values() for s in doc["Statement"] if s["Action"] == "eks:CreateCluster")
        row["Resource"] = f"arn:aws:eks:us-east-2:{ACCOUNT}:cluster/banking-dev"
        with self.assertRaisesRegex(ValueError, "requires Resource"):
            validator.validate(bad, metadata)

    def test_additional_state_only_exact_objects_and_locks(self):
        writes = [s for s in additional_state()["Statement"] if "s3:PutObject" in s["Action"]]
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(r.endswith(".tflock") for s in writes if "s3:DeleteObject" in s["Action"] for r in s["Resource"]))
        self.assertEqual(len(writes[0]["Resource"]), 4)
        self.assertTrue(any(STATE_KEY in r for r in writes[0]["Resource"]))
        self.assertFalse(any("retail" in r or "bootstrap/terraform" in r for s in writes for r in s["Resource"]))

    def test_iam_grants_require_exact_names_and_boundary(self):
        rows = iam_stage()["Statement"]
        create = next(s for s in rows if s["Action"] == "iam:CreateRole")
        self.assertEqual(set(create["Resource"]), set(ROLE_ARNS.values()))
        self.assertEqual(create["Condition"]["StringEquals"]["iam:PermissionsBoundary"], BOUNDARY)
        attach = [s for s in rows if s["Action"] == "iam:AttachRolePolicy"]
        self.assertEqual(len(attach), 2)
        self.assertTrue(all("iam:PolicyARN" in s["Condition"]["ArnEquals"] for s in attach))
        inline = next(s for s in rows if s["Action"] == "iam:PutRolePolicy")
        self.assertEqual(inline["Resource"], ROLE_ARNS["flow"])
        self.assertFalse(any(s["Effect"] == "Allow" and any(a in json.dumps(s["Action"]) for a in ["iam:CreatePolicy", "iam:PutRolePermissionsBoundary", "iam:PassRole"]) for s in rows))

    def test_preplan_simulation_denials_and_missing_context_stop_without_writes(self):
        calls = []
        def call(service, operation, *args):
            calls.append(operation)
            return {"EvaluationResults": [{"EvalActionName": "iam:CreateRole", "EvalDecision": "explicitDeny", "EvalResourceName": ROLE_ARNS["cluster"]}]}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            permission_simulations(call)
        self.assertEqual(calls, ["simulate-principal-policy"])
        def incomplete(service, operation, *args):
            actions = args[args.index("--action-names")+1:args.index("--resource-arns")]
            arn = args[args.index("--resource-arns")+1]
            return {"EvaluationResults": [{"EvalActionName": action, "EvalDecision": "allowed", "EvalResourceName": arn, "MissingContextValues": ["aws:PrincipalOrgID"]} for action in actions]}
        with self.assertRaisesRegex(ValueError, "blocks"):
            permission_simulations(incomplete)

    def test_identity_iam_grant_does_not_deny_routine_platform_passrole(self):
        # The IAM grant is also attached to the common bootstrap role. Its
        # denials must not prevent a separately authorized platform session.
        self.assertFalse(any("iam:PassRole" in s["Action"] for s in iam_stage()["Statement"] if s["Effect"] == "Deny"))
        passes = [s for doc in generate().values() for s in doc["Statement"] if s["Effect"] == "Allow" and s["Action"] == "iam:PassRole" and s["Resource"] in ROLE_ARNS.values()]
        self.assertEqual(len(passes), 3)
        self.assertTrue(all(len(s["Condition"]["StringEquals"]) == 1 for s in passes))

    def test_service_boundary_denies_iam_and_bootstrap_assumption(self):
        deny = [s for s in service_boundary()["Statement"] if s["Effect"] == "Deny"]
        self.assertEqual(deny, [{"Effect": "Deny", "Action": ["iam:*", "sts:AssumeRole*"], "Resource": "*"}])
        for s in service_boundary()["Statement"]:
            if s["Effect"] == "Allow":
                self.assertIn(s["Condition"]["ArnEquals"]["aws:PrincipalArn"], ROLE_ARNS.values())

    def test_iam_workflow_is_protected_with_separate_exact_saved_apply(self):
        source = (ROOT / ".github/workflows/iam-prerequisites.yml").read_text()
        self.assertEqual(source.count("environment: bootstrap"), 2)
        for marker in ("APPLY-REVIEWED-BANKING-IAM-PLAN", "sha256sum --check --strict", "cmp iam-policy-review.json reviewed/iam-policy-review.json", "cmp iam.tfbackend.json reviewed/iam.tfbackend.json", "managed-session-policies", "iam_guard.py verify"):
            self.assertIn(marker, source)
        for marker in ("pull_request_target", "terraform destroy", "force-unlock", "terraform import"):
            self.assertNotIn(marker, source)

    def test_routine_caps_reject_wrong_names_and_hash_drift(self):
        from test_safety import fixture
        values = fixture()
        inputs = json.loads(values['PLATFORM_INPUTS_JSON'])
        inputs.update(deployer_role_arn=f'arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-dev', prod_deployer_role_arn=f'arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-prod')
        values['PLATFORM_INPUTS_JSON'] = json.dumps(inputs)
        docs = [json.loads(json.dumps(generate(key=inputs['kms_key_arn'], sg="sg-0123456789abcdef0")[f"BankingTerraformProvisioner-Platform-{i}.json"]).replace(f"arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__", inputs['operator_role_arn'])) for i in (1, 2, 3)]
        rows = [{"arn": f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-Platform-{i}", "sha256": digest(doc)} for i, doc in enumerate(docs, 1)]
        values.update(PLATFORM_POLICY_REVIEW_JSON=json.dumps(rows), NETWORK_SEED_REVIEW_JSON=json.dumps(dict(account=ACCOUNT, region="us-east-2", state_key="banking-release-platform/dev/platform/terraform.tfstate", vpc_id="vpc-0123456789abcdef0", default_security_group_id="sg-0123456789abcdef0")))
        def call(service, operation, *args):
            return {"Policy": {"DefaultVersionId": "v1"}} if operation == "get-policy" else {"PolicyVersion": {"Document": docs[int(args[1][-1]) - 1]}}
        self.assertEqual(len(verify(values, call)), 3)
        rows[0]["sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(dict(values, PLATFORM_POLICY_REVIEW_JSON=json.dumps(rows)), call)
        docs[0]['Statement'].append(dict(Effect='Allow', Action='ec2:DeleteVpc', Resource='*'))
        rows[0]['sha256'] = digest(docs[0])
        with self.assertRaisesRegex(ValueError, "bounded source"):
            verify(dict(values, PLATFORM_POLICY_REVIEW_JSON=json.dumps(rows)), call)

    def test_session_policy_output_has_one_arn_per_line_for_pinned_aws_action(self):
        from test_safety import fixture
        environment = dict(os.environ, **fixture())
        rows = [{"arn": f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-Platform-{i}", "sha256": "a"*64} for i in (1, 2, 3)]
        environment["PLATFORM_POLICY_REVIEW_JSON"] = json.dumps(rows)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "github-output"
            environment["GITHUB_OUTPUT"] = str(output)
            subprocess.run([sys.executable, str(ROOT / "scripts/infra/guard.py"), "inputs"], env=environment, cwd=folder, check=True, capture_output=True, text=True)
            value = output.read_text().split("managed_session_policies<<BANKING_STAGE_POLICIES\n")[1].split("\nBANKING_STAGE_POLICIES")[0]
            self.assertEqual(value.splitlines(), [r["arn"] for r in rows])
            self.assertNotIn(",", value)

    def test_terraform_platform_consumes_actual_managed_outputs(self):
        source = (ROOT / "infra/environments/dev/platform/main.tf").read_text()
        self.assertIn('data "terraform_remote_state" "iam"', source)
        for role in ("cluster", "fargate", "flow"):
            self.assertIn("local.service_roles." + role, source)
        self.assertNotIn('resource "aws_iam_role"', source)


class BootstrapAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("bootstrap_audit", ROOT / "scripts/infra/audit-bootstrap-role.py")
        cls.audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.audit)

    def test_service_boundary_absence_and_denied_inspection_are_distinct(self):
        for message, expected in (("NoSuchEntity: policy does not exist", "ABSENT"),
                                  ("AccessDenied: iam:GetPolicy", "DENIED"),
                                  ("network failure", "UNVERIFIED")):
            calls = []
            def call(service, operation, *args):
                calls.append((service, operation, args))
                return {"inspectionError": message}
            result = self.audit.service_boundary_inventory(call)
            self.assertEqual(result["status"], expected)
            self.assertEqual(calls, [("iam", "get-policy", ("--policy-arn", BOUNDARY))])
            self.assertFalse(result["awsOrAccountRequirementVerified"])

    def test_service_boundary_version_drift_is_visible_without_granting_rights(self):
        source = json.loads((ROOT / "infra/iam/provisioning/proposed/BankingServicePermissionsBoundary.json").read_text())
        for document, matches in ((source, True), ({"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}, False)):
            calls = []
            def call(service, operation, *args):
                calls.append((service, operation))
                if operation == "get-policy":
                    return {"Policy": {"Arn": BOUNDARY, "DefaultVersionId": "v2"}}
                return {"PolicyVersion": {"Document": document}}
            result = self.audit.service_boundary_inventory(call)
            self.assertEqual(result["status"], "PRESENT")
            self.assertEqual(result["matchesReviewedProposal"], matches)
            self.assertFalse(result["awsOrAccountRequirementVerified"])
            self.assertEqual(calls, [("iam", "get-policy"), ("iam", "get-policy-version")])

    def test_service_boundary_unreadable_version_is_not_reported_as_present(self):
        def call(service, operation, *args):
            return {"Policy": {"Arn": BOUNDARY, "DefaultVersionId": "v2"}} if operation == "get-policy" else {"inspectionError": "AccessDenied: iam:GetPolicyVersion"}
        result = self.audit.service_boundary_inventory(call)
        self.assertEqual(result["status"], "DENIED")
        self.assertNotIn("matchesReviewedProposal", result)

    def test_retail_allow_cannot_authorize_banking_role_creation(self):
        report = {"inlinePolicies": {"original": {"PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": ["iam:CreateRole"], "Resource": f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-retail-*"}]}}}, "managedPoliciesIncludingBoundary": {}}
        result = self.audit.candidate_grants(report, "iam:CreateRole", ROLE_ARNS["cluster"])
        self.assertEqual(result["matchingAllowStatements"], [])
        self.assertFalse(result["effectiveAuthorizationProven"])

    def test_simulation_only_calls_read_api_and_retains_denials(self):
        calls = []
        def call(service, operation, *args):
            calls.append((service, operation))
            return {"operation": "iam:simulate-principal-policy", "inspectionError": "AccessDenied: no identity-based policy allows iam:SimulatePrincipalPolicy"}
        report = {"inlinePolicies": {}, "managedPoliciesIncludingBoundary": {}}
        probes = self.audit.simulations(report, call)
        self.assertEqual(calls, [("iam", "simulate-principal-policy")]*3)
        report.update(simulations=probes, baselineInlineDocumentsUnchanged={}, baselineTrustStatementsUnchanged={})
        summary = self.audit.summarize(report)
        self.assertEqual(len(summary["simulationReadDenials"]), 3)
        self.assertEqual(summary["status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
