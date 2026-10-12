import copy
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/infra"))
import data_guard as guard
import data_iam as iam
import data_preflight as preflight
import data_verify as verification
import yaml


def values():
    return {"vpc_id":"vpc-0123456789abcdef0", "database_subnet_ids":["subnet-0123456789abcdef0","subnet-1123456789abcdef0"],
        "cluster_security_group_id":"sg-0123456789abcdef0", "kms_key_arn":"arn:aws:kms:us-east-2:866934333672:key/11111111-2222-3333-4444-555555555555",
        "engine_version":"17.6", "instance_class":"db.t4g.micro", "monitoring_role_arn":"arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-banking-rds-monitoring",
        "alert_topic_arn":"arn:aws:sns:us-east-2:866934333672:banking-dev-synthetic-alerts"}


def environment():
    return {"GITHUB_REPOSITORY":"mhachem110/BankingReleasePlatform-AWS-EKS", "GITHUB_REF":"refs/heads/dev",
        "AWS_OPERATIONS_ENABLED":"true", "DATA_OPERATIONS_ENABLED":"true", "BOOTSTRAP_STATE_READY":"true",
        "AWS_EXPECTED_ACCOUNT_ID":guard.ACCOUNT, "AWS_REGION":guard.REGION, "TF_STATE_BUCKET":"mhachem-banking-tfstate-"+guard.ACCOUNT,
        "OPERATION":"plan", "DATA_INPUTS_JSON":json.dumps(values()),
        "DATA_SESSION_POLICY_ARN":"arn:aws:iam::866934333672:policy/BankingReleasePlatformPhase6Session", "DATA_SESSION_POLICY_SHA256":"a"*64}


def review():
    return {"account":guard.ACCOUNT, "region":guard.REGION, "instance_class":"db.t4g.micro", "engine_version":"17.6",
        "observed_at":datetime.now(timezone.utc).isoformat(), "reviewed_by":"synthetic fixture", "pricing_evidence":"offline synthetic fixture only",
        "monthly_usd_upper_bound":100, "migration_usd_upper_bound":10, "max_storage_gib":40,
        "included_components":sorted(guard.COMPONENTS), "capacity_and_connections_approved":True,
        "alert_delivery_approved":True, "key_policy_reviewed":True}


class DataSafetyTests(unittest.TestCase):
    def test_post_apply_rejects_extra_db_group_before_claiming_isolation(self):
        # AWS-style metadata from a private DB can still carry a second open SG.
        database={"DBInstanceIdentifier":"banking-dev-postgres","DBInstanceStatus":"available","Engine":"postgres",
            "EngineVersion":"17.6","DBInstanceClass":"db.t4g.micro","DBName":"banking","PubliclyAccessible":False,
            "StorageEncrypted":True,"KmsKeyId":values()["kms_key_arn"],"MultiAZ":False,"DeletionProtection":True,
            "BackupRetentionPeriod":7,"AllocatedStorage":20,"MaxAllocatedStorage":40,"IAMDatabaseAuthenticationEnabled":True,
            "MonitoringInterval":60,"MonitoringRoleArn":values()["monitoring_role_arn"],
            "VpcSecurityGroups":[{"VpcSecurityGroupId":"sg-approved","Status":"active"},{"VpcSecurityGroupId":"sg-unreviewed","Status":"active"}]}
        with self.assertRaisesRegex(ValueError,"exactly one"):
            verification.verify(database, {}, {}, values())

    def test_workflow_uses_two_reviews_disabled_gate_same_run_hash_and_data_state(self):
        workflow=yaml.safe_load((ROOT/".github/workflows/data-operations.yml").read_text())
        jobs=workflow["jobs"]
        self.assertIn("DATA_OPERATIONS_ENABLED == 'true'",jobs["prerequisites"]["if"])
        self.assertNotIn("id-token",jobs["prerequisites"]["permissions"])
        for name in ("plan","apply"):
            self.assertEqual(jobs[name]["environment"],"bootstrap")
            self.assertEqual(jobs[name]["permissions"]["id-token"],"write")
            credential=next(s for s in jobs[name]["steps"] if s.get("uses","").startswith("aws-actions/"))
            self.assertIn("DATA_SESSION_POLICY_ARN",credential["with"]["managed-session-policies"])
            self.assertNotIn("aws-access-key-id",credential["with"])
        self.assertEqual(jobs["apply"]["needs"],["prerequisites","plan"])
        self.assertIn("APPLY-REVIEWED-PHASE6-PLAN",jobs["apply"]["if"])
        commands="\n".join(s.get("run","") for s in jobs["apply"]["steps"])
        self.assertIn("sha256sum --check --strict",commands)
        self.assertIn("cmp data-cost-review.json reviewed/data-cost-review.json",commands)
        self.assertIn('apply -input=false -lock-timeout=5m "$GITHUB_WORKSPACE/reviewed/data.tfplan"',commands)
        self.assertNotIn("-auto-approve",commands);self.assertNotIn("-target",commands)
        self.assertEqual(guard.backend(environment())["key"],guard.STATE_KEY)
        for job in jobs.values():
            for step in job["steps"]:
                if "uses" in step:self.assertRegex(step["uses"],r"@[a-f0-9]{40}$")

    def test_disabled_wrong_branch_account_region_and_apply_fail_closed(self):
        env = environment()
        self.assertEqual(guard.configuration(env), values())
        for key, bad in [("DATA_OPERATIONS_ENABLED","false"), ("AWS_OPERATIONS_ENABLED","false"),
                         ("GITHUB_REF","refs/heads/infra"), ("AWS_REGION","us-east-1"), ("AWS_EXPECTED_ACCOUNT_ID","0"*12),
                         ("OPERATION","destroy"), ("OPERATION","apply"), ("DATA_SESSION_POLICY_SHA256","")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.configuration({**env,key:bad})
        self.assertEqual(guard.configuration({**env,"OPERATION":"apply","APPROVAL":"APPLY-REVIEWED-PHASE6-PLAN"}), values())

    def test_credentials_unknown_duplicate_inputs_and_wrong_resource_scope_rejected(self):
        for extra in ("password", "account", "role_arn", "root", "target"):
            with self.assertRaises(ValueError):
                guard.configuration({**environment(),"DATA_INPUTS_JSON":json.dumps({**values(),extra:"never"})})
        with self.assertRaises(ValueError):
            guard.configuration({**environment(),"DATA_INPUTS_JSON":'{"vpc_id":"one","vpc_id":"two"}'})
        for key, bad in [("kms_key_arn",values()["kms_key_arn"].replace("us-east-2","us-east-1")),
                         ("monitoring_role_arn","arn:aws:iam::866934333672:role/bootstrap"), ("database_subnet_ids",["subnet-bad"]),
                         ("instance_class","db.r7g.16xlarge")]:
            with self.assertRaises(ValueError):
                guard.configuration({**environment(),"DATA_INPUTS_JSON":json.dumps({**values(),key:bad})})

    def test_dated_complete_cost_and_capacity_review_required(self):
        self.assertIn("Administrator", guard.cost_review(review(), values())["provenance"])
        changes = [("monthly_usd_upper_bound", True), ("migration_usd_upper_bound", 0), ("max_storage_gib",20),
                   ("engine_version","17.5"), ("included_components",[]), ("key_policy_reviewed",False),
                   ("observed_at",(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())]
        for key, bad in changes:
            with self.subTest(key=key), self.assertRaises(ValueError):
                guard.cost_review({**review(),key:bad}, values())

    def test_session_cap_is_bounded_without_iam_keys_deletion_or_other_state_writes(self):
        policy = iam.session_cap(values(), environment()["DATA_SESSION_POLICY_ARN"])
        actions = {a for row in policy["Statement"] for a in (row["Action"] if isinstance(row["Action"],list) else [row["Action"]])}
        self.assertLessEqual(len(json.dumps(policy,separators=(",",":"))),6144)
        self.assertNotIn("iam:CreateRole",actions); self.assertNotIn("kms:CreateKey",actions)
        self.assertNotIn("rds:DeleteDBInstance",actions); self.assertNotIn("sns:Publish",actions)
        for row in policy["Statement"]:
            if "s3:PutObject" in row["Action"]:
                self.assertIn(guard.STATE_KEY,row["Resource"])
                self.assertNotIn("/platform/",row["Resource"])
        passed = next(row for row in policy["Statement"] if row["Action"]=="iam:PassRole")
        self.assertEqual(passed["Resource"],values()["monitoring_role_arn"])
        self.assertEqual(passed["Condition"]["StringEquals"]["iam:PassedToService"],"monitoring.rds.amazonaws.com")

    def test_payment_irsa_exact_subject_and_no_dlq_consumption_or_static_keys(self):
        trust = iam.payment_trust("https://oidc.eks.us-east-2.amazonaws.com/id/"+"A"*32)
        condition = trust["Statement"][0]["Condition"]["StringEquals"]
        self.assertIn("system:serviceaccount:banking-dev:banking-payment",condition.values())
        with self.assertRaises(ValueError):
            iam.payment_trust("https://token.actions.githubusercontent.com")
        permissions = iam.payment_permissions(values()["kms_key_arn"])
        dead = next(s for s in permissions["Statement"] if isinstance(s["Resource"],str) and s["Resource"].endswith("-dlq"))
        self.assertEqual(dead["Action"],"sqs:GetQueueAttributes")

    def test_preflight_rejects_drifted_policy_unconfirmed_destination_and_wrong_monitoring_trust(self):
        env=environment(); cap=iam.session_cap(values(),env["DATA_SESSION_POLICY_ARN"]);env["DATA_SESSION_POLICY_SHA256"]=guard.digest(cap)
        role={"Arn":values()["monitoring_role_arn"],"AssumeRolePolicyDocument":iam.monitoring_trust()}
        attached=[{"PolicyArn":"arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"}]
        key={"Arn":values()["kms_key_arn"],"KeyState":"Enabled","KeySpec":"SYMMETRIC_DEFAULT","KeyUsage":"ENCRYPT_DECRYPT"}
        topic={"TopicArn":values()["alert_topic_arn"],"SubscriptionsConfirmed":"1"}
        preflight.verify(role,attached,key,topic,cap,values(),env)
        with self.assertRaises(ValueError):
            preflight.verify(role,attached,key,{**topic,"SubscriptionsConfirmed":"0"},cap,values(),env)
        with self.assertRaises(ValueError):
            preflight.verify({**role,"AssumeRolePolicyDocument":{}},attached,key,topic,cap,values(),env)
        with self.assertRaises(ValueError):
            preflight.verify(role,attached,key,topic,{"Statement":[]},values(),env)


class DataMockPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result=subprocess.run(["terraform","-chdir=infra/environments/dev/data","test","-json","-verbose"],
                              cwd=ROOT,check=True,capture_output=True,text=True,encoding="utf-8",timeout=90)
        events=[json.loads(line) for line in result.stdout.splitlines()]
        event=next(e for e in events if e.get("type")=="test_plan" and e.get("@testrun")=="valid_data_scope")
        cls.plan={"resource_changes":event["test_plan"]["resource_changes"],"applyable":True,"complete":True}

    def test_real_mock_encoding_exact_creation_inventory(self):
        self.assertEqual(guard.audit(self.plan,values(),effective_tags=False)["managed_creates"],21)
        with self.assertRaises(ValueError):
            guard.audit(self.plan,values())

    def test_unknown_extra_missing_replacement_and_existing_resources_rejected(self):
        for actions in (["delete"],["update"],["delete","create"],["no-op"]):
            plan=copy.deepcopy(self.plan);plan["resource_changes"][0]["change"]["actions"]=actions
            with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)
        plan=copy.deepcopy(self.plan);plan["resource_changes"].pop()
        with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)
        plan=copy.deepcopy(self.plan);plan["resource_changes"].append({"mode":"managed","address":"aws_iam_role.bad"})
        with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)

    def test_public_unencrypted_cost_growth_and_role_drift_rejected(self):
        for field, bad in (("publicly_accessible",True),("storage_encrypted",False),("max_allocated_storage",1000),
                           ("manage_master_user_password",False),("monitoring_role_arn","arn:wrong"),("skip_final_snapshot",True)):
            plan=copy.deepcopy(self.plan)
            next(r for r in plan["resource_changes"] if r["type"]=="aws_db_instance")["change"]["after"][field]=bad
            with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)

    def test_policy_overrides_and_wrong_tags_rejected(self):
        plan=copy.deepcopy(self.plan)
        next(r for r in plan["resource_changes"] if r["type"]=="aws_sqs_queue_redrive_policy")["change"]["after"]["redrive_policy"]='{"maxReceiveCount":999}'
        with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)
        plan=copy.deepcopy(self.plan)
        next(r for r in plan["resource_changes"] if r["type"]=="aws_db_instance")["change"]["after"]["tags"]["Project"]="OtherProject"
        with self.assertRaises(ValueError):guard.audit(plan,values(),effective_tags=False)


if __name__ == "__main__":
    unittest.main()
