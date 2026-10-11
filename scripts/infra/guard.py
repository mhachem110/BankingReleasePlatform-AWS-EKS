"""Fail closed on Phase 3 inputs and saved plans. Never calls AWS."""
import hashlib
import json
import os
import re
from pathlib import Path

STATE_KEY = "banking-release-platform/dev/platform/terraform.tfstate"
ROLE_NAMES = {
    "cluster_role_arn": "cloudbatch818-mahmoud-banking-eks-cluster",
    "node_role_arn": "cloudbatch818-mahmoud-banking-eks-nodes",
    "flow_log_role_arn": "cloudbatch818-mahmoud-banking-flow-logs",
    "controller_role_arn": "cloudbatch818-mahmoud-banking-alb-controller",
}


def configuration(env):
    if env.get("GITHUB_REF") != "refs/heads/dev" or env.get("AWS_OPERATIONS_ENABLED") != "true":
        raise ValueError("Only reviewed dev and an explicitly enabled AWS gate can run.")
    if env.get("BOOTSTRAP_STATE_READY") != "true":
        raise ValueError("The completed Phase 2 backend is required.")
    if env.get("OPERATION") not in {"plan", "apply"}:
        raise ValueError("Only plan and reviewed saved-plan apply are supported; no destroy.")
    if env["OPERATION"] == "apply" and env.get("APPROVAL") != "APPLY-REVIEWED-PHASE3-PLAN":
        raise ValueError("Apply requires the exact Phase 3 approval phrase and environment review.")
    account = env["AWS_EXPECTED_ACCOUNT_ID"]
    if not re.fullmatch(r"[0-9]{12}", account) or env["AWS_REGION"] != "us-east-2":
        raise ValueError("Verify account and approved Ohio Region.")
    if env["TF_STATE_BUCKET"] != "mhachem-banking-tfstate-" + account:
        raise ValueError("Only the existing dedicated Banking bucket is allowed.")
    inputs = json.loads(env["PLATFORM_INPUTS_JSON"])
    for field, name in ROLE_NAMES.items():
        if not re.fullmatch(r"arn:aws:iam::" + account + r":role/(?:[\w+=,.@-]+/)*" + name, inputs[field]):
            raise ValueError("Administrator role ARN does not match " + field)
    for field in ("operator_role_arn", "deployer_role_arn"):
        if not inputs[field].startswith(f"arn:aws:iam::{account}:role/") or inputs[field].endswith("/cloudbatch818-mahmoud-cloudops-bootstrap"):
            raise ValueError("Access entries must use verified same-account IAM roles.")
    if inputs["operator_role_arn"] == inputs["deployer_role_arn"]:
        raise ValueError("Operator and namespace deployer must be distinct.")
    if not re.fullmatch(r"arn:aws:kms:us-east-2:" + account + r":key/[a-f0-9-]{36}", inputs["kms_key_arn"]):
        raise ValueError("Use the administrator-approved symmetric KMS key.")
    if inputs.get("kubernetes_version", "1.36") != "1.36":
        raise ValueError("Only the reviewed Kubernetes baseline is allowed.")
    inputs.update(aws_region=env["AWS_REGION"], expected_account_id=account,
                  state_bucket_name=env["TF_STATE_BUCKET"])
    return inputs


ALLOWED_TYPES = {
    "terraform_data", "aws_vpc", "aws_default_security_group", "aws_subnet", "aws_internet_gateway",
    "aws_eip", "aws_nat_gateway", "aws_route_table", "aws_route", "aws_route_table_association",
    "aws_vpc_endpoint", "aws_cloudwatch_log_group", "aws_flow_log", "aws_ecr_repository",
    "aws_ecr_lifecycle_policy", "aws_eks_cluster", "aws_security_group",
    "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule", "aws_launch_template",
    "aws_eks_node_group", "aws_eks_access_entry", "aws_eks_access_policy_association",
    "aws_eks_addon", "aws_eks_pod_identity_association",
}


def verify_plan(plan):
    if not plan.get("applyable") or plan.get("errored") or plan.get("complete") is False:
        raise ValueError("Plan must be complete and applyable.")
    resources = []
    for item in plan.get("resource_changes", []):
        if item.get("mode") != "managed":
            continue
        if item["type"] not in ALLOWED_TYPES or not (
                item["address"] == "terraform_data.prerequisites" or
                item["address"].startswith(("module.network.", "module.registry.", "module.eks."))):
            raise ValueError("Resource outside reviewed Banking platform scope: " + item["address"])
        actions = item["change"]["actions"]
        if actions not in (["create"], ["no-op"]):
            raise ValueError("Initial Phase 3 cannot mutate or delete an existing resource: " + item["address"])
        if actions == ["create"]:
            resources.append({"address": item["address"], "type": item["type"]})
    if not resources:
        raise ValueError("This first-deployment workflow requires a reviewed creation plan.")
    return {"managed_creates": len(resources), "resources": resources, "managed_updates": 0, "managed_deletes": 0}


def session_policy(inputs):
    account, region, bucket = inputs["expected_account_id"], inputs["aws_region"], inputs["state_bucket_name"]
    arn = "arn:aws:s3:::" + bucket
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
        {"Effect": "Allow", "Action": ["ec2:*", "eks:*", "ecr:*", "logs:*", "ssm:GetParameter"],
         "Resource": "*", "Condition": {"StringEquals": {"aws:RequestedRegion": region}}},
        {"Effect": "Allow", "Action": ["iam:GetRole", "iam:ListAttachedRolePolicies", "iam:GetRolePolicy", "iam:ListRolePolicies"],
         "Resource": "*"},
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": [inputs[k] for k in ROLE_NAMES],
         "Condition": {"StringEquals": {"iam:PassedToService": ["eks.amazonaws.com", "ec2.amazonaws.com", "vpc-flow-logs.amazonaws.com", "pods.eks.amazonaws.com"]}}},
        {"Effect": "Allow", "Action": ["kms:DescribeKey", "kms:CreateGrant", "kms:ListGrants", "kms:RetireGrant"], "Resource": inputs["kms_key_arn"]},
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucket*", "s3:GetEncryptionConfiguration", "s3:GetLifecycleConfiguration"], "Resource": arn},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": arn + "/" + STATE_KEY},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": arn + "/" + STATE_KEY + ".tflock"},
    ]}
    result = json.dumps(policy, separators=(",", ":"))
    if len(result) > 2048:
        raise ValueError("STS session cap exceeds 2048 characters; use shorter verified role paths or separately review managed session policies.")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inputs", "plan"])
    parser.add_argument("--path")
    args = parser.parse_args()
    if args.command == "inputs":
        values = configuration(os.environ)
        Path("platform.tfvars.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("session_policy=" + session_policy(values) + "\n")
    else:
        report = verify_plan(json.loads(Path(args.path).read_text(encoding="utf-8")))
        report["plan_sha256"] = hashlib.sha256(Path("platform.tfplan").read_bytes()).hexdigest()
        print(json.dumps(report, indent=2))
