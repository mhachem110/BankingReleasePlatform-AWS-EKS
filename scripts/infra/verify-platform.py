"""Read-only post-apply verification. No kubectl writes or AWS modifications."""
import json
from pathlib import Path
from preflight import aws


def verify(values, outputs, call=aws):
    cluster = call("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
    network = cluster["resourcesVpcConfig"]
    access = cluster["accessConfig"]
    if cluster["status"] != "ACTIVE" or cluster["version"] != values["kubernetes_version"]:
        raise RuntimeError("Cluster is not ACTIVE at the reviewed version.")
    if not network["endpointPrivateAccess"] or not network["endpointPublicAccess"] or set(network["publicAccessCidrs"]) != set(values["endpoint_cidrs"]):
        raise RuntimeError("Endpoint protections do not match reviewed CIDRs.")
    if access["authenticationMode"] != "API" or access["bootstrapClusterCreatorAdminPermissions"]:
        raise RuntimeError("Cluster access must use explicit identities.")
    enabled = {t for setting in cluster["logging"]["clusterLogging"] if setting["enabled"] for t in setting["types"]}
    if enabled != {"api", "audit", "authenticator", "controllerManager", "scheduler"}:
        raise RuntimeError("Control-plane logs are incomplete.")
    if not any(c["resources"] == ["secrets"] and c["provider"]["keyArn"] == values["kms_key_arn"] for c in cluster["encryptionConfig"]):
        raise RuntimeError("Cluster secrets encryption key mismatch.")
    if call("eks", "list-nodegroups", "--cluster-name", "banking-dev")["nodegroups"]:
        raise RuntimeError("The Fargate-only platform must not have managed EC2 node groups.")
    expected_subnets = set(outputs["application_subnet_ids"]["value"])
    expected = {
        "banking-dev-coredns": [{"namespace": "kube-system", "labels": {"k8s-app": "kube-dns"}}],
        "banking-dev-controller": [
            {"namespace": "kube-system", "labels": {"app.kubernetes.io/name": "aws-load-balancer-controller"}},
            {"namespace": "kube-system", "labels": {"k8s-app": "metrics-server"}}],
        "banking-dev-app": [{"namespace": "banking-dev"}],
    }
    names = call("eks", "list-fargate-profiles", "--cluster-name", "banking-dev")["fargateProfileNames"]
    if set(names) != set(expected):
        raise RuntimeError("Fargate profile names do not match the reviewed architecture.")
    for name, selectors in expected.items():
        profile = call("eks", "describe-fargate-profile", "--cluster-name", "banking-dev", "--fargate-profile-name", name)["fargateProfile"]
        normalized = [{"namespace": s["namespace"], **({"labels": s["labels"]} if s.get("labels") else {})} for s in profile["selectors"]]
        if profile["status"] != "ACTIVE" or profile.get("health", {}).get("issues") or profile["podExecutionRoleArn"] != values["fargate_execution_role_arn"] or set(profile["subnets"]) != expected_subnets:
            raise RuntimeError("Fargate profile is unhealthy or incorrectly configured: " + name)
        if sorted(normalized, key=str) != sorted(selectors, key=str):
            raise RuntimeError("Fargate selectors mismatch: " + name)
    configs = json.loads(Path("infra/modules/eks/addon-configuration.json").read_text())
    if set(call("eks", "list-addons", "--cluster-name", "banking-dev")["addons"]) != set(configs):
        raise RuntimeError("Unexpected or missing managed add-ons.")
    for name, version in values["addon_versions"].items():
        addon = call("eks", "describe-addon", "--cluster-name", "banking-dev", "--addon-name", name)["addon"]
        if addon["status"] != "ACTIVE" or addon["health"]["issues"] or addon["addonVersion"] != version or json.loads(addon["configurationValues"]) != configs[name]:
            raise RuntimeError("Pinned Fargate add-on configuration/health mismatch: " + name)
    issuer = cluster["identity"]["oidc"]["issuer"]
    if issuer != outputs["oidc_issuer_url"]["value"]:
        raise RuntimeError("Cluster issuer output mismatch.")
    provider_arn = f"arn:aws:iam::{values['expected_account_id']}:oidc-provider/{issuer.removeprefix('https://')}"
    if provider_arn != outputs["oidc_provider_arn"]["value"]:
        raise RuntimeError("Cluster OIDC provider output mismatch.")
    provider = call("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", provider_arn)
    tags = {t["Key"]: t["Value"] for t in provider["Tags"]}
    if provider["Url"].removeprefix("https://") != issuer.removeprefix("https://") or provider["ClientIDList"] != ["sts.amazonaws.com"] or not provider["ThumbprintList"] or (tags.get("Project") != "BankingReleasePlatform" or tags.get("Environment") != "dev"):
        raise RuntimeError("Cluster OIDC provider protections mismatch.")
    for field, policy, scope in [
        ("operator_role_arn", "AmazonEKSClusterAdminPolicy", {"type": "cluster"}),
        ("deployer_role_arn", "AmazonEKSEditPolicy", {"type": "namespace", "namespaces": ["banking-dev"]}),
    ]:
        entries = call("eks", "list-associated-access-policies", "--cluster-name", "banking-dev", "--principal-arn", values[field])["associatedAccessPolicies"]
        if len(entries) != 1 or not entries[0]["policyArn"].endswith("/" + policy) or {k:v for k,v in entries[0]["accessScope"].items() if v != []} != scope:
            raise RuntimeError("Approved operator/deployer access scope mismatch.")
    deployer_entry = call("eks", "describe-access-entry", "--cluster-name", "banking-dev", "--principal-arn", values["deployer_role_arn"])["accessEntry"]
    if deployer_entry.get("kubernetesGroups") != ["banking-release-verifier"]:
        raise RuntimeError("Deployer verification group mismatch.")
    for name in ["/aws/eks/banking-dev/cluster", "/banking/banking-dev/vpc-flow"]:
        logs = [g for g in call("logs", "describe-log-groups", "--log-group-name-prefix", name)["logGroups"] if g["logGroupName"] == name]
        if len(logs) != 1 or logs[0].get("kmsKeyId") != values["kms_key_arn"] or logs[0].get("retentionInDays") != 30:
            raise RuntimeError("Encrypted log retention mismatch.")
    for name in ["banking-dev-account", "banking-dev-payment"]:
        repo = call("ecr", "describe-repositories", "--repository-names", name)["repositories"][0]
        if repo["imageTagMutability"] != "IMMUTABLE" or not repo["imageScanningConfiguration"]["scanOnPush"]:
            raise RuntimeError("ECR immutable tags/scanning mismatch.")
    print("Verified ACTIVE Fargate-only cluster, three profiles, two pinned healthy add-ons, IRSA provider, explicit access, encrypted logs and immutable ECR. Application/controller rollout remains separately authorized.")


if __name__ == "__main__":
    verify(json.loads(Path("platform.tfvars.json").read_text()),
           json.loads(Path("platform-outputs.json").read_text()))
