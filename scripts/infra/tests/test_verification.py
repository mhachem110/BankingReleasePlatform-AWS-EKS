"""Post-apply verifier regression: only synthetic responses, never AWS."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
spec = importlib.util.spec_from_file_location("verify_platform", ROOT / "scripts/infra/verify-platform.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def fixture():
    key = "arn:aws:kms:us-east-2:123456789012:key/11111111-2222-4333-8444-555555555555"
    issuer = "https://oidc.eks.us-east-2.amazonaws.com/id/" + "A" * 32
    provider = "arn:aws:iam::123456789012:oidc-provider/" + issuer[8:]
    values = {"kubernetes_version": "1.36", "endpoint_cidrs": ["203.0.113.1/32"],
              "kms_key_arn": key, "expected_account_id": "123456789012",
              "fargate_execution_role_arn": "arn:aws:iam::123456789012:role/fargate",
              "operator_role_arn": "arn:aws:iam::123456789012:role/operator",
              "deployer_role_arn": "arn:aws:iam::123456789012:role/deployer",
              "addon_versions": {"coredns": "v1.0.0-eksbuild.1", "metrics-server": "v1.0.0-eksbuild.1"}}
    outputs = {"application_subnet_ids": {"value": ["subnet-one", "subnet-two"]},
               "oidc_issuer_url": {"value": issuer}, "oidc_provider_arn": {"value": provider}}
    profiles = {
        "banking-dev-coredns": [{"namespace": "kube-system", "labels": {"k8s-app": "kube-dns"}}],
        "banking-dev-controller": [{"namespace": "kube-system", "labels": {"app.kubernetes.io/name": "aws-load-balancer-controller"}},
                                  {"namespace": "kube-system", "labels": {"k8s-app": "metrics-server"}}],
        "banking-dev-app": [{"namespace": "banking-dev", "labels": {}}],
    }
    configs = json.loads((ROOT / "infra/modules/eks/addon-configuration.json").read_text())
    data = {
        "cluster": {"status": "ACTIVE", "version": "1.36", "resourcesVpcConfig": {"endpointPrivateAccess": True, "endpointPublicAccess": True, "publicAccessCidrs": values["endpoint_cidrs"]},
                    "accessConfig": {"authenticationMode": "API", "bootstrapClusterCreatorAdminPermissions": False},
                    "logging": {"clusterLogging": [{"enabled": True, "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"]}]},
                    "encryptionConfig": [{"resources": ["secrets"], "provider": {"keyArn": key}}],
                    "identity": {"oidc": {"issuer": issuer}}},
        "verification_groups": ["banking-release-verifier"], "nodes": [], "profiles": {
            name: {"status": "ACTIVE", "podExecutionRoleArn": values["fargate_execution_role_arn"],
                   "subnets": outputs["application_subnet_ids"]["value"], "selectors": selectors}
            for name, selectors in profiles.items()},
        "addons": {name: {"status": "ACTIVE", "health": {"issues": []}, "addonVersion": values["addon_versions"][name],
                          "configurationValues": json.dumps(config)} for name, config in configs.items()},
        "provider": {"Url": issuer[8:], "ClientIDList": ["sts.amazonaws.com"], "ThumbprintList": ["a"*40],
                     "Tags": [{"Key": "Project", "Value": "BankingReleasePlatform"}, {"Key": "Environment", "Value": "dev"}]},
    }

    def call(service, operation, *args):
        if operation == "describe-cluster": return {"cluster": data["cluster"]}
        if operation == "list-nodegroups": return {"nodegroups": data["nodes"]}
        if operation == "list-fargate-profiles": return {"fargateProfileNames": list(data["profiles"])}
        if operation == "describe-fargate-profile": return {"fargateProfile": data["profiles"][args[-1]]}
        if operation == "list-addons": return {"addons": list(data["addons"])}
        if operation == "describe-addon": return {"addon": data["addons"][args[-1]]}
        if operation == "get-open-id-connect-provider": return data["provider"]
        if operation == "describe-access-entry": return {"accessEntry": {"kubernetesGroups": data["verification_groups"]}}
        if operation == "list-associated-access-policies":
            operator = args[-1] == values["operator_role_arn"]
            policy = "AmazonEKSClusterAdminPolicy" if operator else "AmazonEKSEditPolicy"
            scope = {"type": "cluster", "namespaces": []} if operator else {"type": "namespace", "namespaces": ["banking-dev"]}
            return {"associatedAccessPolicies": [{"policyArn": "arn:aws:eks::aws:cluster-access-policy/" + policy, "accessScope": scope}]}
        if operation == "describe-log-groups":
            return {"logGroups": [{"logGroupName": args[-1], "kmsKeyId": key, "retentionInDays": 30}]}
        if operation == "describe-repositories":
            return {"repositories": [{"imageTagMutability": "IMMUTABLE", "imageScanningConfiguration": {"scanOnPush": True}}]}
        raise AssertionError("Unexpected API call: " + operation)
    return values, outputs, data, call


class VerificationTests(unittest.TestCase):
    def test_complete_fargate_platform(self):
        values, outputs, _, call = fixture()
        verify.verify(values, outputs, call)

    def test_verification_group_cannot_be_missing_or_admin(self):
        for groups in [[], ["system:masters"], ["banking-release-verifier", "system:masters"]]:
            values, outputs, data, call = fixture()
            data["verification_groups"] = groups
            with self.subTest(groups=groups), self.assertRaises(RuntimeError):
                verify.verify(values, outputs, call)

    def test_profiles_must_be_active_and_private(self):
        for field, wrong in [("status", "CREATE_FAILED"), ("subnets", ["subnet-other"]),
                             ("podExecutionRoleArn", "arn:aws:iam::123456789012:role/other")]:
            values, outputs, data, call = fixture()
            data["profiles"]["banking-dev-app"][field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify.verify(values, outputs, call)

    def test_ec2_worker_not_accepted(self):
        values, outputs, data, call = fixture()
        data["nodes"] = ["workers"]
        with self.assertRaises(RuntimeError):
            verify.verify(values, outputs, call)

    def test_controller_or_metrics_selector_mismatch_rejected(self):
        values, outputs, data, call = fixture()
        data["profiles"]["banking-dev-controller"]["selectors"][1]["labels"] = {"wrong": "metrics"}
        with self.assertRaises(RuntimeError):
            verify.verify(values, outputs, call)

    def test_core_dns_ec2_configuration_rejected(self):
        values, outputs, data, call = fixture()
        config = json.loads(data["addons"]["coredns"]["configurationValues"])
        config["computeType"] = "EC2"
        data["addons"]["coredns"]["configurationValues"] = json.dumps(config)
        with self.assertRaises(RuntimeError):
            verify.verify(values, outputs, call)

    def test_provider_audience_and_issuer_mismatch_rejected(self):
        for field, wrong in [("ClientIDList", ["other"]), ("Url", "token.actions.githubusercontent.com")]:
            values, outputs, data, call = fixture()
            data["provider"][field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verify.verify(values, outputs, call)

    def test_cluster_creator_admin_rejected(self):
        values, outputs, data, call = fixture()
        data["cluster"]["accessConfig"]["bootstrapClusterCreatorAdminPermissions"] = True
        with self.assertRaises(RuntimeError):
            verify.verify(values, outputs, call)


if __name__ == "__main__":
    unittest.main()
