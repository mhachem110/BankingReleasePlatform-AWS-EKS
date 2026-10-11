"""Read-only AWS prerequisite/collision check; credentials come from protected OIDC."""
import ipaddress
import json
from jsonschema import validators
import subprocess
from pathlib import Path


def aws(*args):
    result = subprocess.run(["aws", *args, "--output", "json", "--no-cli-pager"], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def overlaps(cidr, vpcs):
    proposed = ipaddress.ip_network(cidr, strict=True)
    for vpc in vpcs:
        for association in vpc.get("CidrBlockAssociationSet", []):
            if association.get("CidrBlockState", {}).get("State") in {"associated", "associating"} and proposed.overlaps(ipaddress.ip_network(association["CidrBlock"])):
                raise ValueError("Proposed CIDR overlaps an existing VPC; stop without changes.")



def verify_service_role(field, role, values):
    if role["Arn"] != values[field] or role.get("PermissionsBoundary"):
        raise ValueError("Role identity/boundary requires administrator review: " + field)
    service = {"cluster_role_arn": "eks.amazonaws.com",
               "fargate_execution_role_arn": "eks-fargate-pods.amazonaws.com",
               "flow_log_role_arn": "vpc-flow-logs.amazonaws.com"}[field]
    statements = role["AssumeRolePolicyDocument"]["Statement"]
    matches = [s for s in statements if s.get("Effect") == "Allow" and s.get("Principal", {}).get("Service") == service
               and "sts:AssumeRole" in ([s.get("Action")] if isinstance(s.get("Action"), str) else s.get("Action", []))]
    if not matches:
        raise ValueError("Required service trust is absent: " + field)
    if field == "fargate_execution_role_arn":
        if "/" in role["Arn"].split(":role/")[1]:
            raise ValueError("Fargate execution role cannot have a path.")
        expected = f"arn:aws:eks:us-east-2:{values['expected_account_id']}:fargateprofile/banking-dev/*"
        if not all(s.get("Condition", {}).get("ArnLike", {}).get("aws:SourceArn") == expected and
                   s.get("Condition", {}).get("StringEquals", {}).get("aws:SourceAccount") == values["expected_account_id"]
                   for s in matches):
            raise ValueError("Fargate trust must be scoped to this account and Banking profiles.")


def verify_addon_version(addon, pinned, version, available):
    candidates = [v for entry in available["addons"] for v in entry["addonVersions"]
                  if v["addonVersion"] == pinned and "amd64" in v.get("architecture", []) and
                  "fargate" in [kind.lower() for kind in v.get("computeTypes", [])] and
                  any(c["clusterVersion"] == version for c in v.get("compatibilities", []))]
    if not candidates:
        raise ValueError("Pinned add-on must explicitly support this Kubernetes version and Fargate: " + addon)


def verify_addon_schema(config, schema):
    validator = validators.validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(config)

def main():
    values = json.loads(Path("platform.tfvars.json").read_text())
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != values["expected_account_id"]:
        raise ValueError("Wrong account.")
    overlaps(values.get("vpc_cidr", "10.70.0.0/16"), aws("ec2", "describe-vpcs")["Vpcs"])
    names = aws("eks", "list-clusters")["clusters"]
    if "banking-dev" in names:
        raise ValueError("A Banking cluster already exists; initial deployment must be reviewed separately.")
    repos = aws("ecr", "describe-repositories")["repositories"]
    if any(repo["repositoryName"] in {"banking-dev-account", "banking-dev-payment"} for repo in repos):
        raise ValueError("Banking ECR name already exists; never adopt another resource automatically.")
    active_zones = {zone["ZoneName"] for zone in aws("ec2", "describe-availability-zones")["AvailabilityZones"] if zone["State"] == "available"}
    if len(set(values["availability_zones"])) != 2 or not set(values["availability_zones"]) <= active_zones:
        raise ValueError("Exactly two available AZs are required.")
    from guard import ROLE_NAMES
    for field, name in ROLE_NAMES.items():
        role = aws("iam", "get-role", "--role-name", name)["Role"]
        verify_service_role(field, role, values)
        required = {"cluster_role_arn": {"AmazonEKSClusterPolicy"},
                    "fargate_execution_role_arn": {"AmazonEKSFargatePodExecutionRolePolicy"}}
        if field in required:
            attached = {policy["PolicyName"] for policy in aws("iam", "list-attached-role-policies", "--role-name", name)["AttachedPolicies"]}
            if not required[field] <= attached:
                raise ValueError("Required managed role policy is absent: " + field)
    for name, service in [("AWSServiceRoleForAmazonEKS", "eks.amazonaws.com"),
                          ("AWSServiceRoleForAmazonEKSForFargate", "eks-fargate.amazonaws.com")]:
        role = aws("iam", "get-role", "--role-name", name)["Role"]
        if role["Arn"] != f"arn:aws:iam::{values['expected_account_id']}:role/aws-service-role/{service}/{name}":
            raise ValueError("Administrator must confirm existing service-linked role: " + name)
    for field in ["operator_role_arn", "deployer_role_arn"]:
        role = aws("iam", "get-role", "--role-name", values[field].split("/")[-1])["Role"]
        if role["Arn"] != values[field]:
            raise ValueError("Access role ARN mismatch.")
    key = aws("kms", "describe-key", "--key-id", values["kms_key_arn"])["KeyMetadata"]
    if key["KeyState"] != "Enabled" or key["KeySpec"] != "SYMMETRIC_DEFAULT" or key["KeyUsage"] != "ENCRYPT_DECRYPT":
        raise ValueError("An enabled symmetric encryption KMS key is required.")
    version = values.get("kubernetes_version", "1.36")
    versions = aws("eks", "describe-cluster-versions", "--cluster-versions", version)
    if not any(v["clusterVersion"] == version and v.get("versionStatus") == "STANDARD_SUPPORT" for v in versions["clusterVersions"]):
        raise ValueError("Reviewed Kubernetes version is unavailable or outside standard support.")
    configs = json.loads(Path("infra/modules/eks/addon-configuration.json").read_text())
    for addon, pinned in values["addon_versions"].items():
        available = aws("eks", "describe-addon-versions", "--addon-name", addon, "--kubernetes-version", version)
        verify_addon_version(addon, pinned, version, available)
        schema = aws("eks", "describe-addon-configuration", "--addon-name", addon, "--addon-version", pinned)
        verify_addon_schema(configs[addon], json.loads(schema["configurationSchema"]))
    print("Verified account, non-overlapping CIDR, absent Banking names, AZs, role identities, service-linked roles, key and pinned Fargate add-on schemas. No AWS writes.")


if __name__ == "__main__":
    main()
