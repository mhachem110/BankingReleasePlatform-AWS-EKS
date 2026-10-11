"""Render additive administrator policy files locally; performs no AWS requests."""
import argparse
import json
import re
from pathlib import Path
from guard import STATE_KEY, ROLE_NAMES


def policies(account, region, bucket, key_arn):
    if not re.fullmatch(r"[0-9]{12}", account) or region != "us-east-2" or bucket != "mhachem-banking-tfstate-" + account:
        raise ValueError("Use the verified Banking account, Ohio Region and dedicated bucket.")
    if not re.fullmatch(r"arn:aws:kms:us-east-2:" + account + r":key/[a-f0-9-]{36}", key_arn):
        raise ValueError("An administrator must provide the actual approved key ARN.")
    role_arn = {field: f"arn:aws:iam::{account}:role/{name}" for field, name in ROLE_NAMES.items()}
    files = {}
    for field, service in [("cluster_role_arn", "eks.amazonaws.com"), ("node_role_arn", "ec2.amazonaws.com"),
                           ("flow_log_role_arn", "vpc-flow-logs.amazonaws.com")]:
        statement = {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}
        if field == "flow_log_role_arn":
            statement["Condition"] = {"StringEquals": {"aws:SourceAccount": account},
                                       "ArnLike": {"aws:SourceArn": f"arn:aws:ec2:{region}:{account}:vpc-flow-log/*"}}
        files[ROLE_NAMES[field] + "-trust.json"] = {"Version": "2012-10-17", "Statement": [statement]}
    files[ROLE_NAMES["controller_role_arn"] + "-trust.json"] = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow", "Principal": {"Service": "pods.eks.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:TagSession"],
        "Condition": {"StringEquals": {"aws:RequestTag/eks-cluster-name": "banking-dev",
            "aws:RequestTag/kubernetes-namespace": "kube-system",
            "aws:RequestTag/kubernetes-service-account": "aws-load-balancer-controller"}}
    }]}
    log_arn = f"arn:aws:logs:{region}:{account}:log-group:/banking/banking-dev/vpc-flow"
    files["BankingFlowLogs.json"] = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], "Resource": log_arn + ":*"},
        {"Effect": "Allow", "Action": "logs:DescribeLogGroups", "Resource": "*"},
    ]}
    statements = []
    for field, service in [("cluster_role_arn", "eks.amazonaws.com"), ("node_role_arn", "ec2.amazonaws.com"),
                           ("flow_log_role_arn", "vpc-flow-logs.amazonaws.com"), ("controller_role_arn", "pods.eks.amazonaws.com")]:
        statements.append({"Effect": "Allow", "Action": "iam:PassRole", "Resource": role_arn[field],
                           "Condition": {"StringEquals": {"iam:PassedToService": service}}})
    state = "arn:aws:s3:::" + bucket
    statements.extend([
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": state,
         "Condition": {"StringLike": {"s3:prefix": [STATE_KEY, STATE_KEY + ".tflock", "banking-release-platform/_workspaces/*"]}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": state + "/" + STATE_KEY},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": state + "/" + STATE_KEY + ".tflock"},
        {"Effect": "Allow", "Action": ["kms:DescribeKey", "kms:ListGrants"], "Resource": key_arn},
        {"Effect": "Allow", "Action": "kms:CreateGrant", "Resource": key_arn,
         "Condition": {"Bool": {"kms:GrantIsForAWSResource": "true"}}},
    ])
    files["BankingReleasePlatformPhase3.json"] = {"Version": "2012-10-17", "Statement": statements}
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
    parser.add_argument("--output", default="artifacts/phase3-admin")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in policies(args.account, args.region, args.bucket, args.kms_key_arn).items():
        (output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("Rendered complete additive administrator policies; no AWS calls. Never replace Retail or Phase 2 policies.")
