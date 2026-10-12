"""Fail closed on Phase 3 inputs and saved plans. Never calls AWS."""
import hashlib
import json
import os
import re
from pathlib import Path

STATE_KEY = "banking-release-platform/dev/platform/terraform.tfstate"
ROLE_NAMES = {
    "cluster_role_arn": "cloudbatch818-mahmoud-banking-eks-cluster",
    "fargate_execution_role_arn": "cloudbatch818-mahmoud-banking-fargate-execution",
    "flow_log_role_arn": "cloudbatch818-mahmoud-banking-flow-logs",
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
    allowed = set(ROLE_NAMES) | {"operator_role_arn", "deployer_role_arn", "kms_key_arn",
        "availability_zones", "vpc_cidr", "endpoint_cidrs", "kubernetes_version", "addon_versions", "owner", "cost_center"}
    if set(inputs) - allowed:
        raise ValueError("Unknown/stale platform fields are not accepted.")
    inputs.setdefault("kubernetes_version", "1.36")
    inputs.setdefault("owner", "MahmoudHachem")
    for field in ("owner", "cost_center"):
        value = inputs.get(field)
        if (field == "owner" or value is not None) and (not isinstance(value, str) or not value.strip() or len(value) > 128 or value != value.strip() or "REPLACE" in value.upper()):
            raise ValueError("Use only an approved nonblank " + field + "; omit CostCenter until assigned.")
    for field, name in ROLE_NAMES.items():
        if not re.fullmatch(r"arn:aws:iam::" + account + r":role/(?:[\w+=,.@-]+/)*" + name, inputs[field]):
            raise ValueError("Administrator role ARN does not match " + field)
    if "/" in inputs["fargate_execution_role_arn"].split(":role/")[1]:
        raise ValueError("Fargate execution roles cannot have an IAM path.")
    for field in ("operator_role_arn", "deployer_role_arn"):
        if not inputs[field].startswith(f"arn:aws:iam::{account}:role/") or inputs[field].endswith("/cloudbatch818-mahmoud-cloudops-bootstrap"):
            raise ValueError("Access entries must use verified same-account IAM roles.")
    if inputs["operator_role_arn"] == inputs["deployer_role_arn"]:
        raise ValueError("Operator and namespace deployer must be distinct.")
    if len(set(inputs[k] for k in [*ROLE_NAMES, "operator_role_arn", "deployer_role_arn"])) != 5:
        raise ValueError("Service roles, operator and application identities must all be distinct.")
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
    "aws_ecr_lifecycle_policy", "aws_eks_cluster", "aws_eks_fargate_profile", "aws_iam_openid_connect_provider", "aws_eks_access_entry", "aws_eks_access_policy_association",
    "aws_eks_addon",
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
        if item["type"] == "aws_iam_openid_connect_provider":
            if item["address"] != "module.eks.aws_iam_openid_connect_provider.cluster":
                raise ValueError("Only the new Banking cluster OIDC provider is allowed.")
            after = item["change"].get("after") or {}
            if after.get("client_id_list") != ["sts.amazonaws.com"] or (after.get("tags", {}).get("Project") != "BankingReleasePlatform" or after.get("tags", {}).get("Environment") != "dev"):
                raise ValueError("Cluster OIDC provider must have the reviewed audience and tags.")
            issuer = after.get("url")
            if issuer is None and item["change"].get("after_unknown", {}).get("url") is not True:
                raise ValueError("Cluster issuer must be present or explicitly computed by the new cluster.")
            if issuer is not None and not re.fullmatch(r"https://oidc\.eks\.us-east-2\.amazonaws\.com/id/[A-Za-z0-9]+", issuer):
                raise ValueError("Never manage GitHub or another Region's identity provider.")
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
        {"Effect": "Allow", "Action": ["ec2:*", "eks:*", "ecr:*", "logs:*"],
         "Resource": "*", "Condition": {"StringEquals": {"aws:RequestedRegion": region}}},
        {"Effect": "Allow", "Action": ["iam:GetRole", "iam:ListAttachedRolePolicies", "iam:GetRolePolicy", "iam:ListRolePolicies"],
         "Resource": "*"},
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": [inputs[k] for k in ROLE_NAMES],
         "Condition": {"StringEquals": {"iam:PassedToService": ["eks.amazonaws.com", "eks-fargate-pods.amazonaws.com", "vpc-flow-logs.amazonaws.com"]}}},
        {"Effect": "Allow", "Action": ["iam:CreateOpenIDConnectProvider", "iam:GetOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags", "iam:TagOpenIDConnectProvider"],
         "Resource": f"arn:aws:iam::{account}:oidc-provider/oidc.eks.{region}.amazonaws.com/id/*"},
        {"Effect": "Allow", "Action": ["kms:DescribeKey", "kms:CreateGrant", "kms:ListGrants"], "Resource": inputs["kms_key_arn"]},
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
        plan = json.loads(Path(args.path).read_text(encoding="utf-8"))
        report = verify_plan(plan)
        import importlib.util
        spec = importlib.util.spec_from_file_location("plan_audit", Path(__file__).with_name("plan-audit.py"))
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        report.update(audit.audit(plan, json.loads(Path("platform.tfvars.json").read_text())))
        report["plan_sha256"] = hashlib.sha256(Path("platform.tfplan").read_bytes()).hexdigest()
        print(json.dumps(report, indent=2))
