"""Offline security and promotion regressions; no AWS/Kubernetes API calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import isolation
import provenance
from test_operations import environment, manifest
from test_helm import render


class SharedClusterTests(unittest.TestCase):
    def test_production_uses_shared_cluster_and_own_namespace(self):
        values = environment() | {"APP_RELEASE_MODE":"shared-cluster-demo", "GITHUB_REF":"refs/heads/main",
                                   "K8S_NAMESPACE":"banking-prod"}
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(common.config("prod")["cluster"], "banking-dev")
            self.assertEqual(common.predecessor("prod"), "dev")
            for target in ("stage", "uat"):
                with self.assertRaises(ValueError):
                    common.config(target)
            with self.assertRaises(ValueError):
                common.config("prod", publishing=True)
        for bad in [{"K8S_NAMESPACE":"banking-dev"}, {"EKS_CLUSTER_NAME":"banking-prod"},
                    {"GITHUB_REF":"refs/heads/dev"}, {"APP_RELEASE_MODE":"skip-provenance"}]:
            with patch.dict(os.environ, values | bad, clear=True), self.assertRaises(ValueError):
                common.config("prod")

    def test_sessions_bound_to_images_and_discovery_without_cloud_mutation(self):
        with patch.dict(os.environ, environment(), clear=True):
            cfg = common.config("dev")
        for publishing in (False, True):
            cap = json.loads(common.application_session_policy(cfg, publishing=publishing))
            self.assertLessEqual(len(json.dumps(cap)), 2048)
            actions = {a for s in cap["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
            self.assertEqual("ecr:PutImage" in actions, publishing)
            self.assertFalse(any(a.startswith(("iam:", "ec2:", "s3:", "rds:", "sqs:")) or "*" in a for a in actions))
            self.assertNotIn("eks:CreateAccessEntry", actions)
        with self.assertRaises(ValueError):
            common.application_session_policy(cfg | {"environment":"prod"}, publishing=True)

    def test_prod_requires_successful_dev_receipt_with_same_digests_mode_and_cluster(self):
        trusted = {"id": 456, "head_sha":"d"*40, "status":"completed", "conclusion":"success",
                   "event":"workflow_dispatch", "head_branch":"dev", "path":".github/workflows/app-deploy.yml",
                   "repository":{"full_name":common.REPOSITORY}}
        api = [{"workflow_runs":[trusted]}, {"artifacts":[{"name":"deployment-dev-123", "expired":False}]}]
        with patch.dict(os.environ, {"APP_RELEASE_MODE":"shared-cluster-demo"}, clear=True):
            good = provenance.deployment_receipt("dev", manifest(), trusted["head_sha"], trusted["id"])
            for changes in [None, {"cluster":"banking-prod"}, {"namespace":"banking-prod"},
                            {"manifestHash":"tampered"}, {"deploymentCommit":"e"*40},
                            {"releaseMode":"sequential"}, {"runId":"999"}]:
                receipt = good if changes is None else good | changes
                def obtain(run_id, name, directory):
                    common.save_json(Path(directory)/"deployment.json", receipt)
                with patch.object(provenance, "json_run", side_effect=copy.deepcopy(api)) as read, patch.object(provenance, "obtain", side_effect=obtain):
                    if changes is None:
                        provenance.verify_previous("prod", manifest())
                        self.assertIn("branch=dev", read.call_args_list[0].args[0][2])
                    else:
                        with self.assertRaises(ValueError):
                            provenance.verify_previous("prod", manifest())
            with patch.object(provenance, "json_run", return_value={"workflow_runs":[]}):
                with self.assertRaises(ValueError):
                    provenance.verify_previous("prod", manifest())

    def test_live_authorization_guard_rejects_cross_namespace_and_cluster_rights(self):
        for namespace in ("banking-dev", "banking-prod"):
            def scoped(args, **kwargs):
                return "yes" if "-n" in args and args[-1] == namespace and "roles.rbac.authorization.k8s.io" not in args and "rolebindings.rbac.authorization.k8s.io" not in args else "no"
            isolation.verify_access(namespace, scoped)
            with self.assertRaises(ValueError):
                isolation.verify_access(namespace, lambda *args, **kwargs: "yes")
            with self.assertRaises(ValueError):
                isolation.verify_access(namespace, lambda *args, **kwargs: "error")

    def test_operator_rbac_has_no_cross_namespace_bindings_or_mutating_cluster_grants(self):
        resources = list(yaml.safe_load_all((common.ROOT/"iam/phase3/deployer-verification-rbac.yaml").read_text()))
        for item in resources:
            if item["kind"] == "Role":
                self.assertIn(item["metadata"]["namespace"], ["banking-dev", "banking-prod"])
                self.assertFalse(any("*" in r["verbs"] or "*" in r["resources"] or "rbac.authorization.k8s.io" in r["apiGroups"] for r in item["rules"]))
            if item["kind"] == "RoleBinding":
                self.assertEqual(item["subjects"][0]["name"], item["metadata"]["namespace"].replace("banking-", "banking-release-"))
            if item["kind"] == "ClusterRole":
                self.assertTrue(all(r["verbs"] == ["get"] for r in item["rules"]))
                self.assertFalse(any("secrets" in r["resources"] for r in item["rules"]))

    def test_prod_helm_dns_and_all_resources_stay_in_prod_namespace(self):
        resources = render("--namespace", "banking-prod", "-f", str(common.ROOT/"helm/banking/environments/prod.yaml"))
        self.assertTrue(all(i["metadata"]["namespace"] == "banking-prod" for i in resources))
        payment = next(i for i in resources if i["kind"] == "Deployment" and i["metadata"]["name"] == "banking-payment")
        self.assertIn({"name":"AccountApi__BaseUrl", "value":"http://banking-account.banking-prod.svc.cluster.local:8080/"}, payment["spec"]["template"]["spec"]["containers"][0]["env"])

    def test_promotion_snapshot_rejects_changed_dev_or_unverified_health(self):
        spec = importlib.util.spec_from_file_location("snapshots", common.ROOT/"scripts/deploy/promotion-snapshot.py")
        snapshot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(snapshot)
        before = {"account":"866934333672", "region":"us-east-2", "cluster":"banking-dev",
            "namespace":"banking-dev", "verifiedFargateAndSmoke":True, "atUTC":"2026-10-12T12:00:00Z",
            "deployments": {s:{"uid":s, "generation":3, "replicas":2, "image":"image@sha256:"+"a"*64} for s in ("account","payment")}}
        after = copy.deepcopy(before)
        after["atUTC"]="2026-10-12T12:10:00Z"
        self.assertTrue(snapshot.compare(before, after)["developmentUnchangedAndHealthy"])
        for field, value in [("generation",4),("replicas",3),("image","image@sha256:"+"b"*64),("uid","replacement")]:
            bad = copy.deepcopy(after)
            bad["deployments"]["payment"][field]=value
            with self.assertRaises(ValueError):
                snapshot.compare(before, bad)
        for changes in [{"verifiedFargateAndSmoke":False},{"namespace":"banking-prod"},{"account":"123456789012"}]:
            with self.assertRaises(ValueError):
                snapshot.compare(before, after | changes)


if __name__ == "__main__":
    unittest.main()
