"""Render reviewed IAM proposals only. Never calls AWS or replaces shared policies."""
import json
import re
from data_guard import ACCOUNT, REGION, STATE_KEY, digest, require


def monitoring_trust():
    return {"Version":"2012-10-17", "Statement":[{"Effect":"Allow",
        "Principal":{"Service":"monitoring.rds.amazonaws.com"}, "Action":"sts:AssumeRole",
        "Condition":{"StringEquals":{"aws:SourceAccount":ACCOUNT},
                     "ArnEquals":{"aws:SourceArn":f"arn:aws:rds:{REGION}:{ACCOUNT}:db:banking-dev-postgres"}}}]}


def payment_trust(issuer):
    require(re.fullmatch(r"https://oidc\.eks\.us-east-2\.amazonaws\.com/id/[A-Fa-f0-9]{32}", issuer), "Actual banking-dev issuer required")
    host = issuer.removeprefix("https://")
    return {"Version":"2012-10-17", "Statement":[{"Effect":"Allow",
        "Principal":{"Federated":f"arn:aws:iam::{ACCOUNT}:oidc-provider/{host}"}, "Action":"sts:AssumeRoleWithWebIdentity",
        "Condition":{"StringEquals":{host+":aud":"sts.amazonaws.com", host+":sub":"system:serviceaccount:banking-dev:banking-payment"}}}]}


def payment_permissions(key):
    require(re.fullmatch(f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}", key), "Approved data key required")
    source = f"arn:aws:sqs:{REGION}:{ACCOUNT}:banking-dev-payments"
    return {"Version":"2012-10-17", "Statement":[
        {"Effect":"Allow", "Action":["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"], "Resource":source},
        {"Effect":"Allow", "Action":"sqs:GetQueueAttributes", "Resource":source+"-dlq"},
        {"Effect":"Allow", "Action":["kms:Decrypt", "kms:GenerateDataKey"], "Resource":key,
         "Condition":{"StringEquals":{"kms:ViaService":f"sqs.{REGION}.amazonaws.com"}}}]}


def session_cap(values, policy_arn):
    region = {"StringEquals":{"aws:RequestedRegion":REGION}}
    key = values["kms_key_arn"]
    require(re.fullmatch(f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}", key), "Actual approved key required")
    statement = []
    def allow(actions, resources, condition=None):
        row = {"Effect":"Allow", "Action":actions, "Resource":resources}
        if condition:
            row["Condition"] = condition
        statement.append(row)
    allow(["sts:GetCallerIdentity", "ec2:Describe*", "eks:DescribeCluster", "rds:Describe*", "sqs:ListQueues", "logs:DescribeLogGroups", "cloudwatch:DescribeAlarms"], "*", region)
    allow(["rds:CreateDBInstance", "rds:ModifyDBInstance", "rds:CreateDBSubnetGroup", "rds:CreateDBParameterGroup",
           "rds:ModifyDBParameterGroup", "rds:AddTagsToResource", "rds:ListTagsForResource"],
          f"arn:aws:rds:{REGION}:{ACCOUNT}:*:banking-dev-*", region)
    allow(["sqs:CreateQueue", "sqs:GetQueueUrl", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:ListQueueTags"],
          [f"arn:aws:sqs:{REGION}:{ACCOUNT}:banking-dev-payments", f"arn:aws:sqs:{REGION}:{ACCOUNT}:banking-dev-payments-dlq"], region)
    logs = [f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{name}:*" for name in
            ("/banking/banking-dev/application", "/aws/rds/instance/banking-dev-postgres/postgresql", "/aws/rds/instance/banking-dev-postgres/upgrade")]
    allow(["logs:CreateLogGroup", "logs:AssociateKmsKey", "logs:PutRetentionPolicy", "logs:TagResource", "logs:TagLogGroup",
           "logs:ListTagsForResource", "logs:ListTagsLogGroup", "logs:PutMetricFilter", "logs:DescribeMetricFilters"], logs, region)
    allow(["cloudwatch:PutMetricAlarm", "cloudwatch:TagResource", "cloudwatch:ListTagsForResource"],
          f"arn:aws:cloudwatch:{REGION}:{ACCOUNT}:alarm:banking-dev-*", region)
    allow("ec2:CreateSecurityGroup", [f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/{values['vpc_id']}",
          f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/*"],
          {"StringEquals":{"aws:RequestedRegion":REGION, "aws:RequestTag/Project":"BankingReleasePlatform", "aws:RequestTag/Environment":"dev"}})
    allow("ec2:CreateTags", f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/*",
          {"StringEquals":{"ec2:CreateAction":"CreateSecurityGroup", "aws:RequestTag/Project":"BankingReleasePlatform", "aws:RequestTag/Environment":"dev"}})
    allow(["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress"], f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/*",
          {"StringEquals":{"aws:RequestedRegion":REGION, "aws:ResourceTag/Project":"BankingReleasePlatform", "aws:ResourceTag/Environment":"dev"}})
    allow("iam:PassRole", values["monitoring_role_arn"], {"StringEquals":{"iam:PassedToService":"monitoring.rds.amazonaws.com"}})
    allow(["iam:GetRole", "iam:ListAttachedRolePolicies"], values["monitoring_role_arn"])
    allow("iam:GetRole", f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS")
    allow(["iam:GetPolicy", "iam:GetPolicyVersion"], policy_arn)
    allow(["kms:DescribeKey", "kms:GetKeyPolicy", "kms:ListGrants", "kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], key, region)
    allow("kms:CreateGrant", key, {"Bool":{"kms:GrantIsForAWSResource":"true"}, "StringEquals":{"aws:RequestedRegion":REGION}})
    # RDS creates a generated rds!db-* master secret. No secret-value read or deletion.
    allow(["secretsmanager:CreateSecret", "secretsmanager:TagResource", "secretsmanager:DescribeSecret"],
          f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:rds!db-*", region)
    allow("sns:GetTopicAttributes", values["alert_topic_arn"], region)
    bucket = f"arn:aws:s3:::mhachem-banking-tfstate-{ACCOUNT}"
    allow(["s3:GetBucket*", "s3:GetEncryptionConfiguration", "s3:GetLifecycleConfiguration"], bucket)
    allow("s3:ListBucket", bucket, {"StringLike":{"s3:prefix":[STATE_KEY, STATE_KEY+".tflock", "banking-release-platform/_workspaces/*"]}})
    allow(["s3:GetObject", "s3:PutObject"], bucket+"/"+STATE_KEY)
    allow(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], bucket+"/"+STATE_KEY+".tflock")
    policy = {"Version":"2012-10-17", "Statement":statement}
    require(len(json.dumps(policy, separators=(",", ":"))) <= 6144, "Managed policy exceeds AWS quota; separate reviewed policy design required")
    return policy


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, help="Complete actual approved data input JSON; never credentials")
    parser.add_argument("--policy-arn", required=True)
    parser.add_argument("--issuer", help="Actual verified EKS issuer, only after Phase 3")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = json.loads(Path(args.inputs).read_text())
    policy = session_cap(values, args.policy_arn)
    folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
    files = {"BankingReleasePlatformPhase6Session.json":policy, "RdsMonitoring-trust.json":monitoring_trust(),
             "PaymentRuntime-permissions.json":payment_permissions(values["kms_key_arn"]),
             "review.json":{"policyArn":args.policy_arn, "policySha256":digest(policy), "status":"Proposal only; not applied"}}
    if args.issuer:
        files["PaymentRuntime-trust.json"] = payment_trust(args.issuer)
    for name, value in files.items():
        (folder/name).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print("Rendered additive proposals only. Existing policies/trusts remain untouched.")
