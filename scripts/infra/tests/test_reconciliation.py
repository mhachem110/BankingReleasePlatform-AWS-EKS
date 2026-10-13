"""Synthetic metadata exercises readiness failure modes without AWS access."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts/infra" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reconciliation = load("reconcile-evidence")
inspector = load("inspect-prerequisites")


def fixture():
    return ({"identity": {"Account": reconciliation.ACCOUNT}, "roles": {}, "prerequisiteRoles": {}},
            {"observedAt": "2026-10-13T00:06:01Z", "checks": {
                "identity": {"Account": reconciliation.ACCOUNT}, "clusters": {"clusters": []}}})


def catalog(name, **changes):
    version = {"addonVersion": "v1.0.0-eksbuild.1", "architecture": ["amd64"], "computeTypes": ["fargate"],
               "compatibilities": [{"clusterVersion": "1.36", "defaultVersion": True}]}
    version.update(changes)
    return {"addons": [{"addonName": name, "addonVersions": [version]}]}


class ReadinessTests(unittest.TestCase):
    def test_denied_service_role_is_not_reported_as_absent(self):
        audit, prerequisites = fixture()
        names = reconciliation.ROLE_NAMES
        audit["prerequisiteRoles"] = {
            names[0]: {"role": {"inspectionError": "NoSuchEntity: role cannot be found"}},
            names[1]: {"role": {"inspectionError": "AccessDenied: iam:GetRole", "operation": "iam:get-role"}}}
        report = reconciliation.reconcile(audit, prerequisites)
        self.assertEqual(report["serviceRoles"][names[0]]["status"], "ABSENT")
        self.assertEqual(report["serviceRoles"][names[1]]["status"], "DENIED")
        self.assertEqual(report["serviceRoles"][names[2]]["status"], "UNVERIFIED")
        self.assertIn("iam:GetRole", report["missingReadPermissions"])

    def test_green_collection_with_quota_denial_cannot_authorize_plan(self):
        audit, prerequisites = fixture()
        prerequisites["checks"]["fargateQuota"] = {"inspectionError": "AccessDeniedException when calling ListServiceQuotas"}
        report = reconciliation.reconcile(audit, prerequisites)
        self.assertEqual(report["missingReadPermissions"], ["servicequotas:ListServiceQuotas"])
        self.assertEqual(report["livePlanReadiness"], "BLOCKED")
        self.assertFalse(report["authorizesAwsOperations"])
        self.assertIn("BLOCKED", reconciliation.markdown(report))

    def test_wrong_or_missing_account_is_rejected_in_either_file(self):
        for section in ("audit", "prerequisites"):
            audit, prerequisites = fixture()
            if section == "audit": audit["identity"] = {"Account": "999999999999"}
            else: prerequisites["checks"]["identity"] = {}
            with self.subTest(section=section), self.assertRaises(ValueError):
                reconciliation.reconcile(audit, prerequisites)

    def test_organization_denial_is_not_an_empty_deny_inventory(self):
        audit, prerequisites = fixture()
        audit["organizationDenies"] = [{"inventory": {"inspectionError": "AccessDeniedException: no access",
                                                        "operation": "organizations:list-policies-for-target"}}]
        report = reconciliation.reconcile(audit, prerequisites)
        self.assertEqual(report["missingReadPermissions"], ["organizations:ListPoliciesForTarget"])
        self.assertEqual(report["diagnostics"][0]["status"], "DENIED")

    def test_valid_banking_inline_does_not_mask_retained_privileges(self):
        audit, prerequisites = fixture()
        audit["roles"]["dev"] = {"role": {"Arn": "synthetic-role"},
            "inlinePolicies": {"BankingReleasePlatformDevDeploy": {}},
            "review": {"exactBankingTrustFound": True, "documentsComplete": True,
                       "reviewFindings": [{"actions": ["iam:PutRolePolicy"]}]}}
        result = reconciliation.reconcile(audit, prerequisites)["deploymentRoles"]["dev"]
        self.assertTrue(result["bankingTrustObserved"])
        self.assertTrue(result["bankingInlinePolicyObserved"])
        self.assertEqual(result["broadPermissionFindings"], 1)
        self.assertTrue(result["administratorScopeReviewRequired"])
        self.assertFalse(result["liveEnvironmentOidcAndRbacVerified"])

    def test_existing_cluster_requires_state_reconciliation_and_denied_is_not_absent(self):
        for value, expected in (({"clusters": ["banking-dev"]}, "PRESENT_REQUIRES_STATE_RECONCILIATION"),
                                ({"inspectionError": "AccessDeniedException"}, "DENIED")):
            audit, prerequisites = fixture()
            prerequisites["checks"]["clusters"] = value
            self.assertEqual(reconciliation.reconcile(audit, prerequisites)["bankingCluster"], expected)

    def test_schema_collection_does_not_imply_administrator_approval(self):
        audit, prerequisites = fixture()
        prerequisites["checks"]["corednsCatalog"] = catalog("coredns")
        result = reconciliation.reconcile(audit, prerequisites)["addonCandidates"]["coredns"]
        self.assertEqual(result["catalogCandidate"], "v1.0.0-eksbuild.1")
        self.assertFalse(result["schemaCollected"])
        self.assertFalse(result["administratorApproved"])
        prerequisites["checks"]["corednsSchema"] = {"configurationSchema": "{}", "addonVersion": "wrong-version"}
        self.assertFalse(reconciliation.reconcile(audit, prerequisites)["addonCandidates"]["coredns"]["schemaCollected"])


class InspectorTests(unittest.TestCase):
    def inspect(self, catalogs, inputs=None):
        calls = []
        def reader(service, operation, *args):
            calls.append((service, operation, args))
            if operation == "get-caller-identity": return {"Account": reconciliation.ACCOUNT}
            if operation == "list-clusters": return {"clusters": []}
            if operation == "describe-addon-versions": return catalogs[args[1]]
            if operation == "describe-addon-configuration": return {"addonVersion": args[-1], "configurationSchema": "{}"}
            return {}
        return inspector.inspect(reader=reader, inputs=inputs or {}), calls

    def test_defaults_resolve_exact_fargate_schema_without_full_platform_inputs(self):
        result, calls = self.inspect({name: catalog(name) for name in ("coredns", "metrics-server")})
        self.assertEqual(len([c for c in calls if c[1] == "describe-addon-configuration"]), 2)
        self.assertEqual(result["checks"]["corednsSchema"]["addonVersion"], "v1.0.0-eksbuild.1")
        self.assertFalse(result["addonCandidates"]["coredns"]["administratorApproved"])

    def test_unsupported_or_ambiguous_catalog_cannot_select_schema(self):
        unsupported = catalog("coredns", computeTypes=["ec2"])
        ambiguous = catalog("metrics-server")
        second = copy.deepcopy(ambiguous["addons"][0]["addonVersions"][0])
        second["addonVersion"] = "v2.0.0-eksbuild.1"
        ambiguous["addons"][0]["addonVersions"].append(second)
        result, calls = self.inspect({"coredns": unsupported, "metrics-server": ambiguous})
        self.assertFalse(any(c[1] == "describe-addon-configuration" for c in calls))
        self.assertTrue(all("inspectionError" in c for c in result["addonCandidates"].values()))

    def test_administrator_pin_still_requires_catalog_compatibility(self):
        catalogs = {name: catalog(name) for name in ("coredns", "metrics-server")}
        result, _ = self.inspect(catalogs, {"addon_versions": {"coredns": "v9.0.0-eksbuild.99"}})
        self.assertIn("inspectionError", result["addonCandidates"]["coredns"])
        self.assertNotIn("corednsSchema", result["checks"])


if __name__ == "__main__":
    unittest.main()
