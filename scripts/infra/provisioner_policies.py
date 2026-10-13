"""Generate additive Banking proposals and stage-specific managed session caps.
Never installs policies. Templates with unresolved identifiers are not deployable.
"""
import argparse
import json
import re
from pathlib import Path
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BOUNDARY, BUCKET, STATE_KEY, ROLE_ARNS, ATTACHMENTS, TAGS, digest


def policy(rows):
    return {"Version": "2012-10-17", "Statement": rows}


def allow(actions, resources, condition=None, sid=None):
    row = {"Effect": "Allow", "Action": actions, "Resource": resources}
    if condition:
        row["Condition"] = condition
    if sid:
        row["Sid"] = sid
    return row


def region(extra=None):
    return {"StringEquals": dict({"aws:RequestedRegion": REGION}, **(extra or {}))}


def tagged(env="dev", request=False):
    prefix = "aws:RequestTag/" if request else "aws:ResourceTag/"
    return region({prefix + "Project": "BankingReleasePlatform", prefix + "Environment": env})


def backend(key, read_keys=()):
    bucket = "arn:aws:s3:::" + BUCKET
    return [allow("sts:GetCallerIdentity", "*"),
        allow(["s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration", "s3:GetBucketPublicAccessBlock", "s3:GetBucketPolicy", "s3:GetBucketOwnershipControls", "s3:GetBucketTagging", "s3:GetLifecycleConfiguration"], bucket),
        allow("s3:ListBucket", bucket, {"StringLike": {"s3:prefix": [key, key + ".tflock", "banking-release-platform/_workspaces/*"]}}),
        allow(["s3:GetObject", "s3:PutObject"], bucket + "/" + key),
        allow(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], bucket + "/" + key + ".tflock")] + ([allow("s3:GetObject", [bucket + "/" + k for k in read_keys])] if read_keys else [])


def additional_state():
    keys = ["banking-release-platform/dev/platform/terraform.tfstate", "banking-release-platform/dev/data/terraform.tfstate", "banking-release-platform/prod/data/terraform.tfstate", STATE_KEY]
    bucket = "arn:aws:s3:::" + BUCKET
    return policy([allow("s3:ListBucket", bucket, {"StringLike": {"s3:prefix": keys + [k + ".tflock" for k in keys] + ["banking-release-platform/_workspaces/*"]}}, "BankingAdditionalStateList"),
        allow(["s3:GetObject", "s3:PutObject"], [bucket + "/" + k for k in keys], sid="BankingAdditionalStateReadWrite"),
        allow(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], [bucket + "/" + k + ".tflock" for k in keys], sid="BankingAdditionalLockReadWriteDelete")])


def iam_stage():
    rows = backend(STATE_KEY)
    rows += [allow(["iam:GetRole", "iam:ListRolePolicies", "iam:GetRolePolicy", "iam:ListAttachedRolePolicies", "iam:ListRoleTags"], list(ROLE_ARNS.values()) + [BOOTSTRAP]),
        allow(["iam:GetPolicy", "iam:GetPolicyVersion"], [BOUNDARY, f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-IamPrerequisites", *ATTACHMENTS.values()]),
        allow(["iam:CreateRole", "iam:TagRole"], list(ROLE_ARNS.values()), {"StringEquals": dict({"iam:PermissionsBoundary": BOUNDARY}, **{"aws:RequestTag/" + k: v for k, v in TAGS.items() if k in {"Project", "Environment", "ManagedBy"}})})]
    # TagRole's additional authorization during CreateRole is evaluated with the
    # request tags; boundary is enforced on CreateRole, not on TagRole itself.
    rows[-1]["Action"] = "iam:CreateRole"
    rows.append(allow("iam:TagRole", list(ROLE_ARNS.values()), {"StringEquals": {"aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "shared", "aws:RequestTag/ManagedBy": "Terraform"}}))
    for key, arn in ATTACHMENTS.items():
        rows.append(allow("iam:AttachRolePolicy", ROLE_ARNS[key], {"ArnEquals": {"iam:PolicyARN": arn}, "StringEquals": {"iam:PermissionsBoundary": BOUNDARY, "aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Environment": "shared"}}))
    rows.append(allow("iam:PutRolePolicy", ROLE_ARNS["flow"], {"StringEquals": {"iam:PermissionsBoundary": BOUNDARY, "aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Environment": "shared"}}))
    rows.append(allow("iam:SimulatePrincipalPolicy", BOOTSTRAP))
    rows.append({"Effect": "Deny", "Action": ["iam:PutRolePermissionsBoundary", "iam:DeleteRolePermissionsBoundary", "iam:UpdateAssumeRolePolicy", "iam:DeleteRole", "iam:UntagRole", "iam:DetachRolePolicy", "iam:DeleteRolePolicy"], "Resource": list(ROLE_ARNS.values())})
    return policy(rows)


def service_boundary():
    def on_role(key, condition=None):
        result = condition or region()
        result.setdefault("ArnEquals", {})["aws:PrincipalArn"] = ROLE_ARNS[key]
        return result
    rows = [allow(["ec2:DescribeInstances", "ec2:DescribeNetworkInterfaces", "ec2:DescribeVpcs", "ec2:DescribeDhcpOptions", "ec2:DescribeAvailabilityZones", "ec2:DescribeInstanceTopology"], "*", on_role("cluster")),
        allow("ec2:CreateTags", f"arn:aws:ec2:{REGION}:{ACCOUNT}:instance/*", on_role("cluster", {**region(), "ForAllValues:StringEquals": {"aws:TagKeys": ["kubernetes.io/cluster/banking-dev"]}, "Null": {"aws:TagKeys": "false"}})),
        allow("kms:DescribeKey", f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*", on_role("cluster")),
        allow("ecr:GetAuthorizationToken", "*", on_role("fargate")),
        allow(["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], [f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/banking-dev-{s}" for s in ("account", "payment")] + [f"arn:aws:ecr:{REGION}:602401143452:repository/eks/*"], on_role("fargate")),
        # System add-ons/controller images use AWS public ECR registry accounts.
        # Their exact repository inventory must be reviewed before platform apply.
        allow(["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/banking/banking-dev/vpc-flow:*", on_role("flow")),
        allow("logs:DescribeLogGroups", "*", on_role("flow")),
        {"Effect": "Deny", "Action": ["iam:*", "sts:AssumeRole*"], "Resource": "*"}]
    return policy(rows)


def vpc_seed(key):
    rows = backend("banking-release-platform/dev/platform/terraform.tfstate", [STATE_KEY])
    rows += [allow(["ec2:DescribeVpcs", "ec2:DescribeSecurityGroups", "ec2:DescribeTags"], "*", region()),
        allow("ec2:DescribeVpcAttribute", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/*", tagged()),
        allow("ec2:CreateVpc", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/*", {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev", "aws:RequestTag/Name": "banking-dev-vpc"}}),
        allow("ec2:CreateTags", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/*", {"StringEquals": {"aws:RequestedRegion": REGION, "ec2:CreateAction": "CreateVpc", "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev"}}),
        allow("ec2:ModifyVpcAttribute", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/*", tagged()),
        allow("iam:GetRole", list(ROLE_ARNS.values())),
        allow(["iam:GetPolicy", "iam:GetPolicyVersion"], f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-VpcSeed"),
        allow("kms:DescribeKey", key, region())]
    return policy(rows)


def platform(key, vpc, sg):
    ec2 = lambda resource: f"arn:aws:ec2:{REGION}:{ACCOUNT}:{resource}/*"
    rows = backend("banking-release-platform/dev/platform/terraform.tfstate", [STATE_KEY])
    rows += [allow(["ec2:DescribeVpcs", "ec2:DescribeVpcAttribute", "ec2:DescribeSubnets", "ec2:DescribeInternetGateways", "ec2:DescribeAddresses", "ec2:DescribeNatGateways", "ec2:DescribeRouteTables", "ec2:DescribeVpcEndpoints", "ec2:DescribeSecurityGroups", "ec2:DescribeSecurityGroupRules", "ec2:DescribeFlowLogs", "ec2:DescribeAvailabilityZones", "ec2:DescribeNetworkInterfaces", "ec2:DescribeTags", "eks:ListClusters", "eks:DescribeClusterVersions", "eks:DescribeAddonVersions", "eks:DescribeAddonConfiguration"], "*", region()),
        allow(["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListRoleTags"], list(ROLE_ARNS.values()) + [BOOTSTRAP, f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-dev", f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-prod", f"arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__", f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/eks.amazonaws.com/AWSServiceRoleForAmazonEKS", f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/eks-fargate.amazonaws.com/AWSServiceRoleForAmazonEKSForFargate"]),
        allow(["iam:GetPolicy", "iam:GetPolicyVersion"], [BOUNDARY, f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-Platform-*"])]
    create = {"CreateVpc": "vpc", "CreateSubnet": "subnet", "CreateInternetGateway": "internet-gateway", "AllocateAddress": "elastic-ip", "CreateNatGateway": "natgateway", "CreateRouteTable": "route-table", "CreateVpcEndpoint": "vpc-endpoint", "CreateSecurityGroup": "security-group"}
    for action, resource in create.items():
        rows.append(allow("ec2:" + action, ec2(resource), tagged(request=True)))
    # Required existing parent resources are separately authorized with resource tags.
    parents = {"CreateSubnet": ["vpc"], "CreateRouteTable": ["vpc"], "CreateNatGateway": ["subnet", "elastic-ip", "vpc"], "CreateVpcEndpoint": ["vpc", "route-table"], "CreateSecurityGroup": ["vpc"]}
    for action, resources in parents.items():
        rows.append(allow("ec2:" + action, [ec2(r) for r in resources], tagged()))
    rows.append(allow("ec2:CreateTags", [ec2(r) for r in create.values()] + [ec2("vpc-flow-log")], {"StringEquals": {"ec2:CreateAction": list(create) + ["CreateFlowLogs"], "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev", "aws:RequestedRegion": REGION}}))
    mutations = {"ModifyVpcAttribute": ["vpc"], "ModifySubnetAttribute": ["subnet"], "AttachInternetGateway": ["vpc", "internet-gateway"], "CreateRoute": ["route-table"], "AssociateRouteTable": ["route-table", "subnet"], "CreateFlowLogs": ["vpc"], "AuthorizeSecurityGroupIngress": ["security-group"], "RevokeSecurityGroupIngress": ["security-group"], "RevokeSecurityGroupEgress": ["security-group"]}
    for action, resources in mutations.items():
        rows.append(allow("ec2:" + action, [ec2(r) for r in resources], tagged()))
    rows.append(allow("ec2:CreateFlowLogs", ec2("vpc-flow-log"), tagged(request=True)))
    # The default SG is untagged when AWS creates the VPC. Do not grant arbitrary
    # retagging: this exact resource must be resolved and reviewed before apply.
    rows.append(allow("ec2:CreateTags", f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/{sg}", tagged(request=True), "ExactNewVpcDefaultGroupTagging"))
    eks_resources = [f"arn:aws:eks:{REGION}:{ACCOUNT}:{r}/banking-dev" + ("/*" if r != "cluster" else "") for r in ("cluster", "fargateprofile", "addon", "access-entry")]
    rows.append(allow(["eks:CreateFargateProfile", "eks:CreateAddon"], f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/banking-dev", {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": ["dev", "prod"]}}))
    for principal, environment in [(f"arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__", "dev"), (f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-dev", "dev"), (f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-deploy-prod", "prod")]:
        rows.append(allow("eks:CreateAccessEntry", f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/banking-dev", {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": environment, "eks:principalArn": principal, "eks:accessEntryType": "STANDARD"}}))
    rows.append(allow("eks:TagResource", eks_resources, {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": ["dev", "prod"]}}))
    rows.append(allow("eks:CreateCluster", "*", {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev", "aws:RequestTag/Name": "banking-dev", "eks:kubernetesVersion": "1.36"}, "Bool": {"eks:bootstrapClusterCreatorAdminPermissions": "false", "eks:bootstrapSelfManagedAddons": "false", "eks:deletionProtection": "true"}, "ForAllValues:ArnEquals": {"eks:encryptionConfigProviderKeyArns": key}, "Null": {"eks:encryptionConfigProviderKeyArns": "false"}}))
    rows.append(allow("eks:AssociateAccessPolicy", f"arn:aws:eks:{REGION}:{ACCOUNT}:access-entry/banking-dev/*", {**region(), "ArnEquals": {"eks:policyArn": "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"}, "StringEquals": {"aws:RequestedRegion": REGION, "eks:accessScope": "cluster"}}))
    rows.append(allow(["eks:DescribeCluster", "eks:DescribeFargateProfile", "eks:ListFargateProfiles", "eks:DescribeAddon", "eks:ListAddons", "eks:DescribeAccessEntry", "eks:ListAccessEntries", "eks:ListAssociatedAccessPolicies", "eks:ListTagsForResource", "eks:DescribeUpdate", "eks:ListUpdates"], eks_resources, region()))
    repos = [f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/banking-dev-{s}" for s in ("account", "payment")]
    rows.append(allow(["ecr:CreateRepository", "ecr:DescribeRepositories", "ecr:GetLifecyclePolicy", "ecr:PutLifecyclePolicy", "ecr:ListTagsForResource", "ecr:TagResource"], repos, region()))
    logs = [f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{g}:*" for g in ("/aws/eks/banking-dev/cluster", "/banking/banking-dev/vpc-flow")]
    logs = list(dict.fromkeys(logs + [g.removesuffix(":*") for g in logs]))
    rows.append(allow(["logs:CreateLogGroup", "logs:AssociateKmsKey", "logs:PutRetentionPolicy", "logs:TagResource", "logs:TagLogGroup", "logs:ListTagsForResource", "logs:ListTagsLogGroup"], logs, region()))
    rows.append(allow("logs:DescribeLogGroups", "*", region()))
    for role, service in (("cluster", "eks.amazonaws.com"), ("fargate", "eks-fargate-pods.amazonaws.com"), ("flow", "vpc-flow-logs.amazonaws.com")):
        rows.append(allow("iam:PassRole", ROLE_ARNS[role], {"StringEquals": {"iam:PassedToService": service}}))
    rows.append(allow(["iam:CreateOpenIDConnectProvider", "iam:TagOpenIDConnectProvider"], f"arn:aws:iam::{ACCOUNT}:oidc-provider/oidc.eks.{REGION}.amazonaws.com/id/*", {"StringEquals": {"aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev"}}))
    rows.append(allow(["iam:GetOpenIDConnectProvider", "iam:ListOpenIDConnectProviderTags"], f"arn:aws:iam::{ACCOUNT}:oidc-provider/oidc.eks.{REGION}.amazonaws.com/id/*"))
    rows += [allow(["kms:DescribeKey", "kms:GetKeyPolicy", "kms:ListGrants"], key, region()), allow("kms:CreateGrant", key, {**region(), "Bool": {"kms:GrantIsForAWSResource": "true"}})]
    return policy(rows)


def data(env, key):
    name = "banking-" + env
    rows = backend(f"banking-release-platform/{env}/data/terraform.tfstate", ["banking-release-platform/dev/platform/terraform.tfstate"])
    rows.append(allow(["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeSecurityGroupRules", "rds:DescribeDBInstances", "rds:DescribeDBSnapshots", "rds:DescribeDBSubnetGroups", "rds:DescribeDBParameterGroups", "rds:DescribeDBParameters", "rds:DescribeDBEngineVersions", "rds:DescribeOrderableDBInstanceOptions", "sqs:ListQueues", "cloudwatch:DescribeAlarms", "logs:DescribeLogGroups"], "*", region()))
    rds = [f"arn:aws:rds:{REGION}:{ACCOUNT}:{kind}:{name}-*" for kind in ("db", "subgrp", "pg")]
    rows.append(allow(["rds:CreateDBInstance", "rds:CreateDBSubnetGroup", "rds:CreateDBParameterGroup", "rds:ModifyDBParameterGroup", "rds:AddTagsToResource", "rds:ListTagsForResource"], rds, region()))
    queues = [f"arn:aws:sqs:{REGION}:{ACCOUNT}:{name}-payments{s}" for s in ("", "-dlq")]
    rows.append(allow(["sqs:CreateQueue", "sqs:GetQueueUrl", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:ListQueueTags"], queues, region()))
    groups = [f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{g}:*" for g in (f"/banking/{name}/application", f"/aws/rds/instance/{name}-postgres/postgresql", f"/aws/rds/instance/{name}-postgres/upgrade")]
    groups = list(dict.fromkeys(groups + [g.removesuffix(":*") for g in groups]))
    rows.append(allow(["logs:CreateLogGroup", "logs:AssociateKmsKey", "logs:PutRetentionPolicy", "logs:TagResource", "logs:TagLogGroup", "logs:ListTagsForResource", "logs:ListTagsLogGroup", "logs:PutMetricFilter", "logs:DescribeMetricFilters"], groups, region()))
    rows.append(allow(["cloudwatch:PutMetricAlarm", "cloudwatch:TagResource", "cloudwatch:ListTagsForResource"], f"arn:aws:cloudwatch:{REGION}:{ACCOUNT}:alarm:{name}-*", region()))
    rows.append(allow("ec2:CreateSecurityGroup", f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/*", tagged(env, True)))
    rows.append(allow("ec2:CreateSecurityGroup", f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/__BANKING_VPC_ID__", region()))
    rows.append(allow("ec2:CreateTags", [f"arn:aws:ec2:{REGION}:{ACCOUNT}:{r}/*" for r in ("security-group", "security-group-rule")], {**tagged(env, True), "StringEquals": {**tagged(env, True)["StringEquals"], "ec2:CreateAction": ["CreateSecurityGroup", "AuthorizeSecurityGroupIngress"]}}))
    rows.append(allow(["ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress"], f"arn:aws:ec2:{REGION}:{ACCOUNT}:security-group/*", tagged(env)))
    monitoring = f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-rds-monitoring" + ("-prod" if env == "prod" else "")
    rows += [allow(["iam:GetRole", "iam:ListAttachedRolePolicies"], monitoring),
        allow("iam:GetRole", f"arn:aws:iam::{ACCOUNT}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS"),
        allow("eks:DescribeCluster", f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/banking-dev", region())]
    rows.append(allow("iam:PassRole", monitoring, {"StringEquals": {"iam:PassedToService": "monitoring.rds.amazonaws.com"}}))
    rows += [allow(["kms:DescribeKey", "kms:GetKeyPolicy", "kms:ListGrants", "kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], key, region()), allow("kms:CreateGrant", key, {**region(), "Bool": {"kms:GrantIsForAWSResource": "true"}})]
    # Generated RDS secret identifiers cannot be known at first plan. Limit to
    # RDS-mediated creation, not arbitrary access to other RDS master secrets.
    rows.append(allow(["secretsmanager:CreateSecret", "secretsmanager:TagResource", "secretsmanager:DescribeSecret"], f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:rds!db-*", {**region(), "ForAnyValue:StringEquals": {"aws:CalledVia": "rds.amazonaws.com"}}))
    rows.append(allow(["iam:GetPolicy", "iam:GetPolicyVersion"], f"arn:aws:iam::{ACCOUNT}:policy/BankingReleasePlatformPhase6Session"))
    rows.append(allow("sns:GetTopicAttributes", f"arn:aws:sns:{REGION}:{ACCOUNT}:__APPROVED_ALERT_TOPIC__", region()))
    return policy(rows)


def split(document, name):
    # AWS managed policies have a 6144-character non-whitespace quota.
    groups = [[]]
    for row in document["Statement"]:
        if len(json.dumps(policy(groups[-1] + [row]), separators=(",", ":"))) > 6000:
            groups.append([])
        groups[-1].append(row)
    return {name + (f"-{i + 1}" if len(groups) > 1 else "") + ".json": policy(rows) for i, rows in enumerate(groups)}


def generate(key="arn:aws:kms:us-east-2:866934333672:key/__APPROVED_KMS_KEY_ID__", vpc="__BANKING_VPC_ID__", sg="__NEW_VPC_DEFAULT_SG_ID__"):
    documents = {"BankingTerraformAdditionalState.json": additional_state(), "BankingServicePermissionsBoundary.json": service_boundary(), "BankingTerraformProvisioner-IamPrerequisites.json": iam_stage(), "BankingTerraformReadOnlyReconciliation.json": policy([allow("iam:SimulatePrincipalPolicy", BOOTSTRAP)])}
    documents["BankingTerraformProvisioner-VpcSeed.json"] = vpc_seed(key)
    documents.update(split(platform(key, vpc, sg), "BankingTerraformProvisioner-Platform"))
    documents.update(split(data("dev", key), "BankingTerraformProvisioner-DataDev"))
    documents.update(split(data("prod", key), "BankingTerraformProvisioner-DataProd"))
    return documents


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--kms-key-arn")
    parser.add_argument("--vpc-id")
    parser.add_argument("--default-security-group-id")
    parser.add_argument("--operator-role-arn")
    parser.add_argument("--dev-alert-topic-arn")
    parser.add_argument("--prod-alert-topic-arn")
    args = parser.parse_args()
    overrides = {k: v for k, v in {"key": args.kms_key_arn, "vpc": args.vpc_id, "sg": args.default_security_group_id}.items() if v}
    if args.kms_key_arn and not re.fullmatch(f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}", args.kms_key_arn):
        raise ValueError("Use an explicitly approved key in the Banking account/Region")
    for value, pattern in ((args.vpc_id, r"vpc-[a-f0-9]{8,17}"), (args.default_security_group_id, r"sg-[a-f0-9]{8,17}")):
        if value and not re.fullmatch(pattern, value):
            raise ValueError("Use a verified exact AWS resource ID")
    folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
    documents = generate(**overrides)
    nominations = {"operator_role": args.operator_role_arn, "dev_alert_topic": args.dev_alert_topic_arn, "prod_alert_topic": args.prod_alert_topic_arn}
    for field, value in nominations.items():
        pattern = f"arn:aws:iam::{ACCOUNT}:role/[A-Za-z0-9_+=,.@/-]+" if field == "operator_role" else f"arn:aws:sns:{REGION}:{ACCOUNT}:banking-{'prod' if field == 'prod_alert_topic' else 'dev'}-[A-Za-z0-9_-]+"
        if value and (not re.fullmatch(pattern, value) or value == BOOTSTRAP or value in ROLE_ARNS.values()):
            raise ValueError("Nominate a distinct approved same-account operator role or environment-specific alert topic")
    for name, document in list(documents.items()):
        serialized = json.dumps(document)
        if args.operator_role_arn:
            serialized = serialized.replace(f"arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__", args.operator_role_arn)
        alert = args.prod_alert_topic_arn if "DataProd" in name else args.dev_alert_topic_arn
        if alert:
            serialized = serialized.replace(f"arn:aws:sns:{REGION}:{ACCOUNT}:__APPROVED_ALERT_TOPIC__", alert)
        if args.vpc_id:
            serialized = serialized.replace("__BANKING_VPC_ID__", args.vpc_id)
        document = json.loads(serialized); documents[name] = document
        if len(json.dumps(document, separators=(",", ":"))) > 6144:
            raise ValueError("Finalized policy exceeds managed quota; re-review its split")
        (folder / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    manifest = {"status": "PROPOSAL_ONLY", "source": "Reviewed Terraform source and offline inventory; no live plan authorization claimed", "files": {name: {"sha256": digest(doc), "characters": len(json.dumps(doc, separators=(",", ":"))), "containsUnresolvedInputs": "__" in json.dumps(doc)} for name, doc in documents.items()}}
    (folder / "review-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Generated additive proposals only. No IAM, AWS or GitHub permissions changed.")
