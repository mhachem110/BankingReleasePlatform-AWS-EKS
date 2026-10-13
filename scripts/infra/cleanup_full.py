"""Reviewed destroy guard for full Banking Terraform states; never the S3 backend."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from cleanup_guard import aws, check_identity, other_state_empty, plan_review, rows
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, require
from network_seed import interface

KEYS = {
    "dev-data": "banking-release-platform/dev/data/terraform.tfstate",
    "prod-data": "banking-release-platform/prod/data/terraform.tfstate",
    "runtime-prerequisites": "banking-release-platform/shared/runtime-prerequisites/terraform.tfstate",
    "runner": "banking-release-platform/shared/runner/terraform.tfstate",
    "platform": "banking-release-platform/dev/platform/terraform.tfstate",
}
DEPENDENCIES = {
    "dev-data": (), "prod-data": (),
    "runtime-prerequisites": ("dev-data", "prod-data"),
    "runner": (),
    "platform": ("dev-data", "prod-data", "runtime-prerequisites", "runner"),
}
UNTAGGABLE = {"terraform_data", "aws_route", "aws_route_table_association",
              "aws_ecr_lifecycle_policy", "aws_eks_access_policy_association",
              "aws_iam_role_policy", "aws_iam_role_policy_attachment",
              "aws_sqs_queue_policy", "aws_sqs_queue_redrive_policy", "aws_sqs_queue_redrive_allow_policy",
              "aws_cloudwatch_log_metric_filter", "aws_kms_alias", "aws_sns_topic_subscription",
              "aws_codebuild_webhook"}


def inputs(env):
    target = env.get("TARGET")
    require(target in KEYS and env.get("OPERATION") in {"plan", "apply"}, "Unknown full-stack cleanup target/operation")
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and
            env.get("GITHUB_REF") == "refs/heads/dev" and
            env.get("CLEANUP_ENABLED") == "true" and env.get("AWS_OPERATIONS_ENABLED") == "false",
            "Only the protected cleanup window on dev may destroy Banking resources")
    require(env.get("ROLE_ARN") == BOOTSTRAP and env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and
            env.get("AWS_REGION") == REGION and env.get("TF_STATE_BUCKET") == BUCKET,
            "Wrong cleanup role/account/Region/backend")
    require(re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) and
            re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")), "Actual workflow run required")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "DESTROY-REVIEWED-BANKING-" + target.upper(),
                "Exact destroy phrase and separate protected review required")
    if target in {"dev-data", "prod-data"}:
        require(env.get("DATA_DISPOSITION") == "FINAL-SNAPSHOT-RETAIN",
                "Explicit data deletion with retained final snapshot required")
    receipt_value = env.get("KUBERNETES_CLEANUP_REVIEW_JSON", "")
    return {"target": target, "key": KEYS[target], "account": ACCOUNT, "region": REGION,
            "run": env["GITHUB_RUN_ID"], "attempt": env["GITHUB_RUN_ATTEMPT"],
            "data_disposition": env.get("DATA_DISPOSITION", ""),
            "kubernetes_receipt_sha256": hashlib.sha256(receipt_value.encode()).hexdigest()}


def backend(config):
    return {"bucket": BUCKET, "region": REGION, "key": config["key"], "encrypt": True,
            "use_lockfile": True, "allowed_account_ids": [ACCOUNT],
            "workspace_key_prefix": "banking-release-platform/_workspaces"}


def inventory(target):
    if target in {"dev-data", "prod-data"}:
        from data_guard import inventory as data_inventory
        return data_inventory()
    if target == "runtime-prerequisites":
        from runtime_prerequisites import inventory as runtime_inventory
        return runtime_inventory()
    if target == "runner":
        from runner_plan_guard import ALLOWED
        return ALLOWED
    spec = importlib.util.spec_from_file_location("plan_audit", Path(__file__).with_name("plan-audit.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inventory_addresses()


def state_review(state, config, env):
    managed = rows(state)
    require(managed and {r["address"] for r in managed} == inventory(config["target"]),
            "Full-stack cleanup requires the exact complete owned native state")
    require(len(managed) == len({r["address"] for r in managed}) and state.get("lineage") and
            isinstance(state.get("serial"), int), "Invalid or duplicate state inventory")
    target = config["target"]
    expected_env = "prod" if target == "prod-data" else "dev" if target in {"dev-data", "platform"} else "shared"
    for item in managed:
        address, kind, value = item["address"], item["type"], item["values"]
        require(value.get("id"), "Resource ID missing: " + address)
        if kind not in UNTAGGABLE:
            tags = value.get("tags") or {}
            allowed_env = {"dev", "prod"} if target in {"runtime-prerequisites", "platform"} else {expected_env}
            require(tags.get("Project") == "BankingReleasePlatform" and
                    tags.get("Environment") in allowed_env and tags.get("ManagedBy") == "Terraform",
                    "Unowned resource in selected state: " + address)
        arn = value.get("arn")
        if arn:
            fields = arn.split(":")
            require(len(fields) > 5 and fields[4] == ACCOUNT and fields[3] in {"", REGION},
                    "Resource ARN leaves the approved account/Region")
        if kind == "aws_db_instance":
            name = "banking-" + target.removesuffix("-data") + "-postgres"
            require(value.get("identifier") == name and value.get("deletion_protection") is True and
                    value.get("skip_final_snapshot") is False and
                    value.get("final_snapshot_identifier") == name + "-final-reviewed",
                    "Protected RDS/final snapshot contract differs")
        if kind == "aws_eks_cluster":
            require(value.get("name") == "banking-dev" and value.get("deletion_protection") is True,
                    "Unexpected EKS cluster/protection")
        if kind == "aws_ecr_repository":
            require(value.get("name") in {"banking-dev-account", "banking-dev-payment"} and
                    value.get("force_delete") is False, "ECR images must be inventoried separately")
        if kind == "aws_vpc":
            seed = interface(env)
            require(value.get("id") == seed["vpc_id"] and value.get("cidr_block") == "10.70.0.0/16",
                    "Only the seeded Banking VPC may be deleted")
        if address == "aws_codebuild_project.runner":
            require(value.get("name") == "banking-release-deployer" and value.get("project_visibility") == "PRIVATE",
                    "Unexpected CodeBuild project")
        if address == "aws_iam_role.runner":
            require(value.get("arn") == f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-codebuild-runner",
                    "Unexpected runner service role")
    return {"target": target, "state_key": config["key"], "lineage": state["lineage"],
            "serial": state["serial"], "inventory": managed}


def receipt(env):
    value = json.loads(env.get("KUBERNETES_CLEANUP_REVIEW_JSON") or "{}")
    require(value.get("account") == ACCOUNT and value.get("cluster") == "banking-dev" and
            value.get("verified") is True and value.get("workloads_removed") is True and
            value.get("load_balancers_removed") is True and
            re.fullmatch(r"[1-9][0-9]*", str(value.get("run_id", ""))) and
            re.fullmatch(r"[a-f0-9]{40}", str(value.get("commit", ""))),
            "Provide the successful protected application cleanup receipt")
    return value


def preflight(config, report, env):
    identity = check_identity()
    receipt(env)
    for target in DEPENDENCIES[config["target"]]:
        other_state_empty(KEYS[target])
    for item in report["inventory"]:
        value = item["values"]
        if item["type"] == "aws_ecr_repository":
            require(not aws("ecr", "list-images", "--repository-name", value["name"])["imageIds"],
                    "Retain/archive reviewed image digests, then empty only project ECR repositories")
        if item["type"] == "aws_db_instance":
            name = value["identifier"]
            live = aws("rds", "describe-db-instances", "--db-instance-identifier", name)["DBInstances"][0]
            require(live["DBInstanceIdentifier"] == name and live.get("DeletionProtection") is True,
                    "Live protected database differs")
            require(aws("rds", "describe-db-snapshots", "--db-snapshot-identifier", name + "-final-reviewed",
                        absent_codes=("DBSnapshotNotFound",)).get("absent"),
                    "Final snapshot identifier already exists; review retention before any retry")
        if item["type"] == "aws_eks_cluster":
            live = aws("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
            require(live["name"] == "banking-dev" and live.get("deletionProtection") is True,
                    "Live protected EKS cluster differs")
    return {"identity": identity, "dependencies_empty": True,
            "kubernetes_cleanup_run": receipt(env)["run_id"]}


def read_cap(config):
    bucket = "arn:aws:s3:::" + BUCKET
    rows = [
        {"Effect": "Allow", "Action": ["sts:GetCallerIdentity", "ec2:Describe*", "eks:Describe*", "eks:List*",
                                      "rds:Describe*", "rds:List*", "ecr:Describe*", "ecr:List*", "ecr:Get*", "sqs:Get*", "sqs:List*",
                                      "sns:Get*", "sns:List*", "iam:Get*", "iam:List*", "kms:Describe*",
                                      "kms:Get*", "kms:List*", "logs:Describe*", "logs:List*", "cloudwatch:Describe*", "cloudwatch:List*",
                                      "elasticloadbalancing:Describe*", "codebuild:BatchGet*", "codebuild:List*"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["s3:Get*", "s3:ListBucket"], "Resource": bucket},
        {"Effect": "Allow", "Action": "s3:GetObject", "Resource": bucket + "/banking-release-platform/*/terraform.tfstate"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
         "Resource": bucket + "/" + config["key"] + ".tflock"},
    ]
    text = json.dumps({"Version": "2012-10-17", "Statement": rows}, separators=(",", ":"))
    require(len(text) <= 2048, "Full cleanup read cap exceeds STS limit")
    return text


def delete_cap(config):
    # The exact state IDs, ownership tags, dependency receipt and binary plan
    # are checked twice. IAM deletes additionally name only project identities.
    doc = json.loads(read_cap(config))
    target = config["target"]
    actions = {
        "dev-data": ["rds:Delete*", "rds:ModifyDBInstance", "rds:CreateDBSnapshot", "sqs:DeleteQueue", "sqs:SetQueueAttributes",
                     "ec2:DeleteSecurityGroup", "ec2:RevokeSecurityGroupIngress", "logs:Delete*", "cloudwatch:DeleteAlarms"],
        "prod-data": ["rds:Delete*", "rds:ModifyDBInstance", "rds:CreateDBSnapshot", "sqs:DeleteQueue", "sqs:SetQueueAttributes",
                      "ec2:DeleteSecurityGroup", "ec2:RevokeSecurityGroupIngress", "logs:Delete*", "cloudwatch:DeleteAlarms"],
        "runtime-prerequisites": ["sns:DeleteTopic", "sns:Unsubscribe", "sqs:DeleteQueue", "sqs:SetQueueAttributes",
                                  "kms:ScheduleKeyDeletion", "kms:DeleteAlias"],
        "runner": ["codebuild:DeleteProject", "codebuild:DeleteWebhook", "ec2:DeleteSecurityGroup",
                   "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress", "logs:DeleteLogGroup"],
        "platform": ["ec2:Delete*", "ec2:Disassociate*", "ec2:Detach*", "ec2:ReleaseAddress", "ec2:Revoke*",
                     "eks:Delete*", "eks:UpdateClusterConfig", "ecr:DeleteRepository", "ecr:DeleteLifecyclePolicy", "logs:DeleteLogGroup"],
    }[target]
    doc["Statement"].append({"Effect": "Allow", "Action": actions, "Resource": "*",
                             "Condition": {"StringEquals": {"aws:RequestedRegion": REGION}}})
    if target in {"runner", "runtime-prerequisites", "platform"}:
        doc["Statement"].append({"Effect": "Allow", "Action": ["iam:DeleteRole", "iam:DeleteRolePolicy",
                                  "iam:DetachRolePolicy", "iam:DeletePolicy", "iam:DeleteOpenIDConnectProvider"],
                                 "Resource": [f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-*",
                                              f"arn:aws:iam::{ACCOUNT}:policy/BankingReleasePlatform*",
                                              f"arn:aws:iam::{ACCOUNT}:policy/cloudbatch818-mahmoud-banking-codebuild-runner-boundary",
                                              f"arn:aws:iam::{ACCOUNT}:oidc-provider/oidc.eks.us-east-2.amazonaws.com/id/*"]})
    doc["Statement"].append({"Effect": "Allow", "Action": "s3:PutObject",
                             "Resource": "arn:aws:s3:::" + BUCKET + "/" + config["key"]})
    text = json.dumps(doc, separators=(",", ":"))
    require(len(text) <= 2048, "Full cleanup delete cap exceeds STS limit")
    return text


def unlock(config, reviewed):
    # The saved plan was separately approved before this narrow protection
    # change. Terraform destroys the same state immediately afterward.
    inventory = reviewed["inventory"]
    if config["target"] in {"dev-data", "prod-data"}:
        db = next(row for row in inventory if row["type"] == "aws_db_instance")
        name = db["values"]["identifier"]
        aws("rds", "modify-db-instance", "--db-instance-identifier", name,
            "--no-deletion-protection", "--apply-immediately")
        wait("rds", "db-instance-available", "--db-instance-identifier", name)
        require(aws("rds", "describe-db-instances", "--db-instance-identifier", name)["DBInstances"][0]
                .get("DeletionProtection") is False, "RDS deletion protection remains enabled")
    if config["target"] == "platform":
        cluster = next(row for row in inventory if row["type"] == "aws_eks_cluster")
        require(cluster["values"]["name"] == "banking-dev", "Wrong cluster unlock target")
        aws("eks", "update-cluster-config", "--name", "banking-dev", "--no-deletion-protection")
        wait("eks", "cluster-active", "--name", "banking-dev")
        require(aws("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
                .get("deletionProtection") is False, "EKS deletion protection remains enabled")


def wait(service, waiter, *args):
    result = subprocess.run(["aws", service, "wait", waiter, *args, "--region", REGION, "--no-cli-pager"],
                            capture_output=True, text=True, timeout=1800)
    require(result.returncode == 0, "AWS protection update did not reach the reviewed deletion state")


def verify(config):
    require(not rows(json.loads(Path("cleanup-state.json").read_text())), "Selected Terraform state is not empty")
    check_identity()
    target = config["target"]
    if target in {"dev-data", "prod-data"}:
        name = "banking-" + target.removesuffix("-data") + "-postgres"
        require(aws("rds", "describe-db-instances", "--db-instance-identifier", name,
                    absent_codes=("DBInstanceNotFound",)).get("absent"), "Database still exists")
        snapshot = aws("rds", "describe-db-snapshots", "--db-snapshot-identifier", name + "-final-reviewed")
        require(snapshot["DBSnapshots"][0]["DBInstanceIdentifier"] == name,
                "Retained final snapshot missing or belongs to another database")
    if target == "platform":
        require(aws("eks", "describe-cluster", "--name", "banking-dev",
                    absent_codes=("ResourceNotFoundException",)).get("absent"), "EKS cluster still exists")
    if target == "runner":
        require(not aws("codebuild", "batch-get-projects", "--names", "banking-release-deployer")["projects"],
                "CodeBuild runner project still exists")
    if target == "runtime-prerequisites":
        key = next((r for r in json.loads(Path("cleanup-state-review.json").read_text())["inventory"]
                    if r["type"] == "aws_kms_key"), None)
        if key:
            meta = aws("kms", "describe-key", "--key-id", key["values"]["arn"])["KeyMetadata"]
            require(meta["KeyState"] == "PendingDeletion", "Alert KMS key is not scheduled for deletion")
    Path("cleanup-verification.json").write_text(json.dumps({"target": config["target"], "account": ACCOUNT,
        "region": REGION, "state_key": config["key"], "managed_resources_remaining": 0,
        "final_snapshot_retained": config["target"] in {"dev-data", "prod-data"}, "verified": True}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inputs", "preflight", "plan", "saved", "delete-cap", "unlock", "verify"])
    command = parser.parse_args().command
    config = inputs(os.environ)
    if command == "inputs":
        Path("cleanup-config.json").write_text(json.dumps(config, indent=2))
        Path("cleanup.tfbackend.json").write_text(json.dumps(backend(config), indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy=" + read_cap(config) + "\n")
    elif command == "delete-cap":
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy=" + delete_cap(config) + "\n")
    elif command == "preflight":
        report = state_review(json.loads(Path("cleanup-state.json").read_text()), config, os.environ)
        Path("cleanup-state-review.json").write_text(json.dumps(report, indent=2))
        Path("cleanup-preflight.json").write_text(json.dumps(preflight(config, report, os.environ), indent=2))
    elif command == "plan":
        report = plan_review(json.loads(Path("cleanup-plan.json").read_text()),
                             json.loads(Path("cleanup-state-review.json").read_text()))
        report["saved_plan_sha256"] = hashlib.sha256(Path("cleanup.tfplan").read_bytes()).hexdigest()
        Path("cleanup-plan-review.json").write_text(json.dumps(report, indent=2))
    elif command == "saved":
        require(config == json.loads(Path("reviewed/cleanup-config.json").read_text()) and
                backend(config) == json.loads(Path("reviewed/cleanup.tfbackend.json").read_text()),
                "Reviewed full cleanup input/backend changed")
        fresh = json.loads(Path("cleanup-state-review.json").read_text())
        require(fresh == json.loads(Path("reviewed/cleanup-state-review.json").read_text()),
                "State changed since the reviewed full cleanup plan")
        report = json.loads(Path("reviewed/cleanup-plan-review.json").read_text())
        require(hashlib.sha256(Path("reviewed/cleanup.tfplan").read_bytes()).hexdigest() ==
                report["saved_plan_sha256"] == os.environ.get("REVIEWED_DIGEST"), "Saved plan hash changed")
        require(plan_review(json.loads(Path("cleanup-plan.json").read_text()), fresh) ==
                {k: v for k, v in report.items() if k != "saved_plan_sha256"}, "Saved destroy inventory changed")
    elif command == "unlock":
        unlock(config, json.loads(Path("reviewed/cleanup-state-review.json").read_text()))
    else:
        verify(config)
