"""Render additive administrator policies locally. Never calls AWS."""
import argparse
import json
import re
from pathlib import Path
from guard import STATE_KEY, ROLE_NAMES

CONTROLLER_ROLE = "cloudbatch818-mahmoud-banking-alb-controller"


def controller_trust(account, region, issuer):
    if not re.fullmatch(r"[0-9]{12}", account) or region != "us-east-2":
        raise ValueError("Use the verified Banking account and Region.")
    if not re.fullmatch(r"https://oidc\.eks\.us-east-2\.amazonaws\.com/id/[A-Fa-f0-9]{32}", issuer):
        raise ValueError("Supply the actual banking-dev EKS issuer from verified Terraform/AWS outputs.")
    host = issuer.removeprefix("https://")
    return {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Federated": f"arn:aws:iam::{account}:oidc-provider/{host}"},
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {"StringEquals": {
            host + ":aud": "sts.amazonaws.com",
            host + ":sub": "system:serviceaccount:kube-system:aws-load-balancer-controller"
        }}
    }]}


def policies(account, region, bucket, key_arn, issuer=None, role_arns=None):
    if not re.fullmatch(r"[0-9]{12}", account) or region != "us-east-2" or bucket != "mhachem-banking-tfstate-" + account:
        raise ValueError("Use the verified Banking account, Ohio Region and dedicated bucket.")
    if not re.fullmatch(r"arn:aws:kms:us-east-2:" + account + r":key/[a-f0-9-]{36}", key_arn):
        raise ValueError("An administrator must provide the actual approved key ARN.")
    role_arn = {field: f"arn:aws:iam::{account}:role/{name}" for field, name in ROLE_NAMES.items()}
    if role_arns:
        role_arn.update({field: value for field, value in role_arns.items() if value is not None})
    for field, name in ROLE_NAMES.items():
        if not re.fullmatch(r"arn:aws:iam::" + account + r":role/(?:[\w+=,.@-]+/)*" + name, role_arn[field]):
            raise ValueError("Actual service role ARN/name does not match: " + field)
    if "/" in role_arn["fargate_execution_role_arn"].split(":role/")[1]:
        raise ValueError("Fargate execution role must not have a path.")
    files = {}
    services = {"cluster_role_arn": "eks.amazonaws.com",
                "fargate_execution_role_arn": "eks-fargate-pods.amazonaws.com",
                "flow_log_role_arn": "vpc-flow-logs.amazonaws.com"}
    for field, service in services.items():
        statement = {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}
        if field == "flow_log_role_arn":
            statement["Condition"] = {"StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:ec2:{region}:{account}:vpc-flow-log/*"}}
        if field == "fargate_execution_role_arn":
            statement["Condition"] = {"StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:eks:{region}:{account}:fargateprofile/banking-dev/*"}}
        files[ROLE_NAMES[field] + "-trust.json"] = {"Version": "2012-10-17", "Statement": [statement]}
    if issuer is not None:
        files[CONTROLLER_ROLE + "-trust.json"] = controller_trust(account, region, issuer)
    log_arn = f"arn:aws:logs:{region}:{account}:log-group:/banking/banking-dev/vpc-flow"
    files["BankingFlowLogs.json"] = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], "Resource": log_arn + ":*"},
        {"Effect": "Allow", "Action": "logs:DescribeLogGroups", "Resource": "*"},
    ]}
    statements = [
        {"Effect": "Allow", "Action": "iam:PassRole", "Resource": role_arn[field],
         "Condition": {"StringEquals": {"iam:PassedToService": service}}}
        for field, service in services.items()
    ]
    state = "arn:aws:s3:::" + bucket
    provider = f"arn:aws:iam::{account}:oidc-provider/oidc.eks.{region}.amazonaws.com/id/*"
    statements.extend([
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": state,
         "Condition": {"StringLike": {"s3:prefix": [STATE_KEY, STATE_KEY + ".tflock", "banking-release-platform/_workspaces/*"]}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": state + "/" + STATE_KEY},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": state + "/" + STATE_KEY + ".tflock"},
        {"Effect": "Allow", "Action": ["kms:DescribeKey", "kms:ListGrants"], "Resource": key_arn},
        {"Effect": "Allow", "Action": "kms:CreateGrant", "Resource": key_arn,
         "Condition": {"Bool": {"kms:GrantIsForAWSResource": "true"}}},
        {"Effect": "Allow", "Action": ["iam:CreateOpenIDConnectProvider", "iam:TagOpenIDConnectProvider"],
         "Resource": provider,
         "Condition": {"StringEquals": {"aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev"}}},
        {"Effect": "Allow", "Action": ["iam:GetOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags"], "Resource": provider},
    ])
    files["BankingReleasePlatformPhase3.json"] = {"Version": "2012-10-17", "Statement": statements}
    # This complete key policy is for a NEW dedicated key only. Existing shared
    # keys require an additive administrator review preserving all old statements.
    files["BankingKeyPolicy.json"] = {"Version": "2012-10-17", "Statement": [
        {"Sid": "EnableAccountIAMDelegation", "Effect": "Allow", "Principal": {"AWS": f"arn:aws:iam::{account}:root"}, "Action": "kms:*", "Resource": "*"},
        {"Sid": "BankingLogsOnly", "Effect": "Allow", "Principal": {"Service": f"logs.{region}.amazonaws.com"},
         "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"], "Resource": "*",
         "Condition": {"ArnLike": {"kms:EncryptionContext:aws:logs:arn": [
             f"arn:aws:logs:{region}:{account}:log-group:/aws/eks/banking-dev/cluster", log_arn]}}},
    ]}
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--kms-key-arn", required=True)
    parser.add_argument("--oidc-issuer", help="Only after banking-dev exists; never guess its issuer.")
    parser.add_argument("--cluster-role-arn")
    parser.add_argument("--flow-log-role-arn")
    parser.add_argument("--output", default="artifacts/phase3-admin")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in policies(args.account, args.region, args.bucket, args.kms_key_arn, args.oidc_issuer, {"cluster_role_arn": args.cluster_role_arn, "flow_log_role_arn": args.flow_log_role_arn}).items():
        (output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("Rendered complete additive policies. No AWS calls; preserve Retail, GitHub trust and Phase 2 policies.")
    if not args.oidc_issuer:
        print("Controller IRSA trust deferred until the actual cluster issuer is verified.")
