import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "audit-deployment-roles.py"
spec = importlib.util.spec_from_file_location("role_audit", path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class RoleAuditTests(unittest.TestCase):
    def test_banking_inline_policy_never_masks_broad_original_permissions(self):
        role = {"AssumeRolePolicyDocument":{"Statement":[{"Effect":"Allow", "Principal":{"Federated":f"arn:aws:iam::{audit.ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"},
            "Action":"sts:AssumeRoleWithWebIdentity", "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com", "token.actions.githubusercontent.com:sub":audit.PREFIX+"dev"}}}]}}
        inline = {"BankingReleasePlatformDevDeploy":{"PolicyDocument":{"Statement":[{"Effect":"Allow", "Action":"eks:DescribeCluster", "Resource":"*"}]}}}
        managed = {n:{"metadata":{"Policy":{"PolicyName":audit.ROLES["dev"]+"-"+n}}, "effectiveVersion":{"PolicyVersion":{"Document":{"Statement":[{"Effect":"Allow", "Action":"iam:*", "Resource":"*"}]}}}} for n in ("core","iam","services")}
        result = audit.review_role(role, inline, managed, "dev")
        self.assertTrue(result["exactBankingTrustFound"])
        self.assertTrue(result["originalManagedPolicyNamesPresent"])
        self.assertTrue(result["reviewFindings"])
        self.assertFalse(result["bankingLeastPrivilegeEstablished"])

    def test_denied_document_cannot_be_reported_as_complete(self):
        result = audit.review_role({}, {}, {"denied":{"inspectionError":"AccessDenied"}}, "prod")
        self.assertFalse(result["documentsComplete"])
        self.assertFalse(result["exactBankingTrustFound"])

    def test_wrong_account_and_mutations_fail_before_collection(self):
        with self.assertRaises(ValueError):
            audit.collect(call=lambda *args, **kwargs: {"Account":"999999999999"})
        with self.assertRaises(ValueError):
            audit.read("iam", "put-role-policy")

    def test_denied_policy_inventory_is_not_an_empty_complete_inventory(self):
        def fake(service, operation, *args, **kwargs):
            if operation == "get-caller-identity":
                return {"Account": audit.ACCOUNT}
            if operation == "list-role-policies":
                return {"inspectionError": "AccessDenied: iam:ListRolePolicies"}
            return {}
        result = audit.collect(call=fake)
        self.assertTrue(all(not r["review"]["documentsComplete"] for r in result["roles"].values()))
        self.assertIn("inspectionError", result["roles"]["dev"]["inlineInventory"])

    def test_readonly_workflow_never_enables_terraform_or_paid_actions(self):
        import json, yaml
        workflow = (path.parents[2]/".github/workflows/verify-prerequisites.yml").read_text(encoding="utf-8")
        data = yaml.safe_load(workflow)
        self.assertEqual(data["jobs"]["inspect"]["environment"], "bootstrap")
        self.assertIn("refs/heads/dev", data["jobs"]["inspect"]["if"])
        for step in data["jobs"]["inspect"]["steps"]:
            if "uses" in step:
                self.assertRegex(step["uses"], r"@[a-f0-9]{40}$")
            policy = step.get("with", {}).get("inline-session-policy")
            if policy:
                cap = json.loads(policy)
                self.assertLessEqual(len(policy), 2048)
                self.assertTrue(all((a == "iam:SimulatePrincipalPolicy" or a.split(":",1)[1].startswith(("Get", "List", "Describe"))) for s in cap["Statement"] for a in s["Action"]))
        for forbidden in ("terraform plan", "terraform apply", "aws-access-key-id", "pull_request_target"):
            self.assertNotIn(forbidden, workflow)

    def test_current_cost_sensitivity_has_one_cluster_and_separate_databases(self):
        spec = importlib.util.spec_from_file_location("shared_cost", path.with_name("shared-demo-cost.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.estimate()
        self.assertEqual(result["assumptions"]["clusters"], 1)
        self.assertEqual(result["assumptions"]["database_instances"], 2)
        self.assertEqual(result["fixed_and_compute_subtotal_usd"], "279.17")
        self.assertTrue(result["excluded_requires_approved_usage"])
        with self.assertRaises(ValueError):
            module.estimate("db.m8g.large")


if __name__ == "__main__":
    unittest.main()
