"""Read-only AWS prerequisite/collision check; credentials come from protected OIDC."""
import ipaddress
import json
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
        if role["Arn"] != values[field]:
            raise ValueError("Role ARN mismatch: " + field)
        if role.get("PermissionsBoundary"):
            raise ValueError("Role boundary needs administrator review: " + field)
        services = {"cluster_role_arn": "eks.amazonaws.com", "node_role_arn": "ec2.amazonaws.com",
                    "flow_log_role_arn": "vpc-flow-logs.amazonaws.com", "controller_role_arn": "pods.eks.amazonaws.com"}
        statements = role["AssumeRolePolicyDocument"]["Statement"]
        if not any(s.get("Effect") == "Allow" and s.get("Principal", {}).get("Service") == services[field]
                   and "sts:AssumeRole" in ([s.get("Action")] if isinstance(s.get("Action"), str) else s.get("Action", []))
                   for s in statements):
            raise ValueError("Required service trust is absent: " + field)
        required = {"cluster_role_arn": {"AmazonEKSClusterPolicy"},
                    "node_role_arn": {"AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"}}
        if field in required:
            attached = {policy["PolicyName"] for policy in aws("iam", "list-attached-role-policies", "--role-name", name)["AttachedPolicies"]}
            if not required[field] <= attached:
                raise ValueError("Required AWS managed role policies are absent: " + field)
    for field in ["operator_role_arn", "deployer_role_arn"]:
        role = aws("iam", "get-role", "--role-name", values[field].split("/")[-1])["Role"]
        if role["Arn"] != values[field]:
            raise ValueError("Access role ARN mismatch.")
    key = aws("kms", "describe-key", "--key-id", values["kms_key_arn"])["KeyMetadata"]
    if key["KeyState"] != "Enabled" or key["KeySpec"] != "SYMMETRIC_DEFAULT" or key["KeyUsage"] != "ENCRYPT_DECRYPT":
        raise ValueError("An enabled symmetric encryption KMS key is required.")
    version = values.get("kubernetes_version", "1.36")
    release = aws("ssm", "get-parameter", "--name", f"/aws/service/eks/optimized-ami/{version}/amazon-linux-2023/x86_64/standard/recommended/release_version")["Parameter"]["Value"]
    if release != values["node_release_version"]:
        raise ValueError("Review and pin the current AL2023 release: " + release)
    for addon, pinned in values["addon_versions"].items():
        available = aws("eks", "describe-addon-versions", "--addon-name", addon, "--kubernetes-version", version)
        if not any(item["addonVersion"] == pinned and "amd64" in item.get("architecture", []) for entry in available["addons"] for item in entry["addonVersions"]):
            raise ValueError("Pinned add-on is not compatible: " + addon)
    print("Verified account, non-overlapping CIDR, absent Banking names, AZs, role identities, key and pinned releases. No AWS writes.")


if __name__ == "__main__":
    main()
