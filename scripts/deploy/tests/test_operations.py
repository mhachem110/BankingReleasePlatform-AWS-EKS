import copy
import importlib.util
import json
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
import common
import deploy
import provenance

def manifest():
    return {"version":1, "sourceCommit":"a"*40, "publishRunId":"123",
            "images":{s:{"repository":f"123456789012.dkr.ecr.us-east-2.amazonaws.com/banking-dev-{s}",
                         "digest":"sha256:" + c*64} for s,c in [("account","b"),("payment","c")]}}

def environment():
    return {"GITHUB_REPOSITORY":common.REPOSITORY,"GITHUB_REF":"refs/heads/dev",
            "APP_DEPLOYMENTS_ENABLED":"true","APP_DEPLOY_ROLE_ARN":"arn:aws:iam::123456789012:role/banking-app-deploy",
            "AWS_ACCOUNT_ID":"123456789012","AWS_REGION":"us-east-2",
            "ECR_ACCOUNT_REPOSITORY":manifest()["images"]["account"]["repository"],
            "ECR_PAYMENT_REPOSITORY":manifest()["images"]["payment"]["repository"],
            "EKS_CLUSTER_NAME":"banking-dev","K8S_NAMESPACE":"banking-dev"}

class GuardTests(unittest.TestCase):
    def test_occupied_forward_port_never_calls_kubectl_or_uses_other_server(self):
        spec = importlib.util.spec_from_file_location("kube_smoke", DEPLOY / "kube-smoke.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 18081))
            with patch.object(module.subprocess, "Popen") as launch, self.assertRaises(OSError):
                with module.forwards("banking-dev", "banking"):
                    self.fail("Occupied port was accepted")
            launch.assert_not_called()

    def test_runtime_data_uses_fixed_namespace_references_and_rejects_secrets(self):
        runtime = {"persistence":{"enabled":True,"accountSecretName":"banking-dev-account-db"}}
        with patch.dict(os.environ, {"APP_RUNTIME_VALUES_JSON":json.dumps(runtime)}, clear=True), self.assertRaises(ValueError):
            common.runtime_values("dev")
        with patch.dict(os.environ, {}, clear=True):
            actual = common.runtime_values("dev")
            self.assertEqual(actual["persistence"]["accountSecretName"], "banking-account-db")
            self.assertEqual(actual["messaging"]["queueUrl"],
                             "https://sqs.us-east-2.amazonaws.com/866934333672/banking-dev-payments")
            self.assertEqual(common.runtime_values("prod")["persistence"]["paymentSecretName"], "banking-payment-db")
            self.assertEqual(common.runtime_values("stage"), {})
        with patch.dict(os.environ, {"APP_RUNTIME_VALUES_JSON":json.dumps(runtime)}, clear=True), self.assertRaises(ValueError):
            common.runtime_values("stage")
        for values in [{"images":{}},{"persistence":{"password":"never-accepted"}},{"messaging":{"accessKey":"never-accepted"}}]:
            with patch.dict(os.environ, {"APP_RUNTIME_VALUES_JSON":json.dumps(values),"APP_DATA_OPERATIONS_ENABLED":"true"}, clear=True), self.assertRaises(ValueError):
                common.runtime_values("dev")
        with patch.dict(os.environ, {"APP_RUNTIME_VALUES_JSON":'{"monitoring":{},"monitoring":{}}'}, clear=True), self.assertRaises(ValueError):
            common.runtime_values("dev")

    def test_disabled_missing_wrong_account_or_infrastructure_role(self):
        bad = [
            {"APP_DEPLOYMENTS_ENABLED":""},{"APP_DEPLOYMENTS_ENABLED":"false"},
            {"GITHUB_REF":"refs/heads/feature/app"},{"GITHUB_REF":"refs/heads/infra"},
            {"GITHUB_REPOSITORY":"attacker/repo"},{"AWS_ACCOUNT_ID":"oops"},
            {"APP_DEPLOY_ROLE_ARN":"arn:aws:iam::999999999999:role/app"},
            {"INFRA_ROLE_ARN":environment()["APP_DEPLOY_ROLE_ARN"]},
            {"BOOTSTRAP_ROLE_ARN":environment()["APP_DEPLOY_ROLE_ARN"]},
            {"ECR_ACCOUNT_REPOSITORY":"123456789012.dkr.ecr.us-east-2.amazonaws.com/other"},
            {"EKS_CLUSTER_NAME":"banking-prod"},{"K8S_NAMESPACE":"default"},
        ]
        for changes in bad:
            with self.subTest(changes=changes), patch.dict(os.environ, environment()|changes, clear=True), self.assertRaises(ValueError):
                common.config("dev")

    def test_environment_isolation_and_exact_branch_routes(self):
        for target, branch in common.ROUTES.items():
            values = environment() | {"GITHUB_REF":"refs/heads/"+branch,
                "EKS_CLUSTER_NAME":"banking-"+target,"K8S_NAMESPACE":"banking-"+target}
            with patch.dict(os.environ, values, clear=True):
                self.assertEqual(common.config(target)["environment"], target)
                if target != "dev":
                    with self.assertRaises(ValueError):
                        common.config(target, publishing=True)

    def test_digest_and_repository_tampering_fail_closed(self):
        repos = {s:i["repository"] for s,i in manifest()["images"].items()}
        self.assertEqual(common.validate_manifest(manifest(),repos), manifest())
        for field,value in [("digest","latest"),("digest","sha256:"+"a"*63),("repository","evil.invalid/image")]:
            m = manifest()
            m["images"]["payment"][field] = value
            with self.assertRaises(ValueError):
                common.validate_manifest(m,repos)
        m = manifest()
        m["images"]["other"] = m["images"]["account"]
        with self.assertRaises(ValueError):
            common.validate_manifest(m,repos)

    def test_manifest_source_fields_and_shell_metacharacters_rejected(self):
        repos = {s:i["repository"] for s,i in manifest()["images"].items()}
        for field,value in [("sourceCommit","$(evil)"),("publishRunId","123;evil"),("version",2)]:
            m=manifest()
            m[field]=value
            with self.assertRaises(ValueError):
                common.validate_manifest(m,repos)

    def test_provenance_rejects_untrusted_failed_wrong_workflow_runs(self):
        good = {"status":"completed","conclusion":"success","event":"workflow_dispatch",
                "head_branch":"dev","head_sha":"a"*40,"path":".github/workflows/app-publish.yml",
                "repository":{"full_name":common.REPOSITORY}}
        provenance.validate_run(good,workflow="app-publish.yml",branch="dev",commit="a"*40)
        for changes in [{"conclusion":"failure"},{"status":"in_progress"},{"head_branch":"feature/app"},
                        {"event":"pull_request"},{"path":".github/workflows/evil.yml"},
                        {"repository":{"full_name":"attacker/fork"}},{"head_sha":"b"*40}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                provenance.validate_run(good|changes,workflow="app-publish.yml",branch="dev",commit="a"*40)

    def test_promotions_require_previous_deployment(self):
        with patch.object(provenance, "json_run", return_value={"workflow_runs":[]}):
            for target in ("stage","uat","prod"):
                with self.assertRaises(ValueError):
                    provenance.verify_previous(target,manifest())
            provenance.verify_previous("dev",manifest())

    def test_previous_deployment_checks_exact_digest_pair(self):
        trusted={"id":1,"status":"completed","conclusion":"success","event":"workflow_dispatch",
                 "head_branch":"dev","path":".github/workflows/app-deploy.yml",
                 "repository":{"full_name":common.REPOSITORY}}
        api=[{"workflow_runs":[trusted]}, {"artifacts":[{"name":"deployment-dev-123","expired":False}]}]
        def obtain(run_id,name,directory):
            common.save_json(Path(directory)/"deployment.json",{"environment":"dev",
                "publishRunId":"123","manifestHash":provenance.manifest_hash(manifest())})
        with patch.object(provenance,"json_run",side_effect=api),patch.object(provenance,"obtain",side_effect=obtain):
            provenance.verify_previous("stage",manifest())
        def corrupt(run_id,name,directory):
            common.save_json(Path(directory)/"deployment.json",{"environment":"dev",
                "publishRunId":"123","manifestHash":"wrong"})
        with patch.object(provenance,"json_run",side_effect=api),patch.object(provenance,"obtain",side_effect=corrupt),self.assertRaises(ValueError):
            provenance.verify_previous("stage",manifest())

class RollbackTests(unittest.TestCase):
    def test_smoke_failure_rolls_back_exact_previous_revision_and_stays_failed(self):
        commands=[]
        smoke_calls=0
        def command(args, **kwargs):
            nonlocal smoke_calls
            commands.append([str(x) for x in args])
            if "kube-smoke.py" in str(args):
                smoke_calls+=1
                if smoke_calls == 1:
                    raise RuntimeError("Integration smoke failed")
            if args[:3] == ["helm","get","values"]:
                return json.dumps({"images":manifest()["images"]})
            return ""
        with patch.object(deploy,"verify") as verify, self.assertRaisesRegex(RuntimeError,"Integration smoke failed"):
            deploy.transaction("banking-dev","banking","images.json","dev",manifest(),command=command,revision=7)
        rollback=next(c for c in commands if c[:2] == ["helm","rollback"])
        self.assertEqual(rollback[2:5],["banking","7","-n"])
        self.assertEqual(smoke_calls,2)
        self.assertEqual(verify.call_count,2)

    def test_failed_first_install_cleans_release_without_namespace_deletion(self):
        commands=[]
        def command(args,**kwargs):
            commands.append([str(x) for x in args])
            if args[:2] == ["helm","upgrade"]:
                raise RuntimeError("Startup failed")
            return ""
        with self.assertRaisesRegex(RuntimeError,"Startup failed"):
            deploy.transaction("banking-dev","banking","values.json","dev",manifest(),command=command)
        self.assertTrue(any(c[:2] == ["helm","uninstall"] for c in commands))
        self.assertFalse(any(c[:2] == ["helm","rollback"] for c in commands))
        self.assertFalse(any("namespace" in c and "delete" in c for c in commands))

    def test_rollback_failure_is_visible(self):
        def command(args,**kwargs):
            if args[:2] == ["helm","upgrade"]:
                raise RuntimeError("Upgrade failed")
            if args[:2] == ["helm","rollback"]:
                raise RuntimeError("Rollback failed")
            return ""
        with self.assertRaisesRegex(RuntimeError,"Rollback failed"):
            deploy.transaction("banking-dev","banking","values.json","dev",manifest(),command=command,revision=2)

    def test_success_does_not_roll_back(self):
        commands=[]
        with patch.object(deploy,"verify"):
            deploy.transaction("banking-dev","banking","values.json","dev",manifest(),
                command=lambda args,**kwargs:commands.append([str(x) for x in args]),revision=4)
        self.assertFalse(any(c[:2] == ["helm","rollback"] for c in commands))

class WorkflowTests(unittest.TestCase):
    def test_no_privileged_pr_events_or_infrastructure_apply(self):
        import yaml
        root=DEPLOY.parents[1]
        for name in ["app-ci.yml","app-validation.yml","app-publish.yml","app-deploy.yml"]:
            workflow=yaml.safe_load((root/".github/workflows"/name).read_text())
            events=workflow.get("on",workflow.get(True,{}))
            self.assertNotIn("pull_request_target", events)
            text=(root/".github/workflows"/name).read_text()
            self.assertNotIn("terraform apply",text)
            self.assertNotIn("aws-access-key-id",text)
            self.assertNotIn("secrets: inherit",text)
            for job in workflow["jobs"].values():
                for step in job.get("steps",[]):
                    if "uses" in step:
                        self.assertRegex(step["uses"],r"@[a-f0-9]{40}$")

if __name__ == "__main__":
    unittest.main()
