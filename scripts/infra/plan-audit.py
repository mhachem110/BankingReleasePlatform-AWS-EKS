"""Audit the actual saved plan, not just its resource type allowlist."""
import ipaddress
import json
from pathlib import Path

UNTAGGABLE = {"terraform_data", "aws_route", "aws_route_table_association",
              "aws_ecr_lifecycle_policy", "aws_eks_access_policy_association"}


def inventory_addresses():
    addresses = {"terraform_data.prerequisites"}
    resources = {
        "network": {
            "aws_vpc": ["this"], "aws_default_security_group": ["closed"],
            "aws_internet_gateway": ["this"], "aws_eip": ["nat"], "aws_nat_gateway": ["this"],
            "aws_route_table": ["public"], "aws_route": ["internet"],
            "aws_vpc_endpoint": ["s3"], "aws_cloudwatch_log_group": ["flow"], "aws_flow_log": ["this"]},
        "eks": {"aws_cloudwatch_log_group": ["cluster"], "aws_eks_cluster": ["this"],
                "aws_iam_openid_connect_provider": ["cluster"],
                "aws_eks_fargate_profile": ["coredns", "controller", "banking"],
                "aws_eks_access_entry": ["operator", "deployer"],
                "aws_eks_access_policy_association": ["operator", "deployer"]},
    }
    for module, kinds in resources.items():
        for kind, names in kinds.items():
            addresses.update(f"module.{module}.{kind}.{name}" for name in names)
    for index in ("0", "1"):
        for tier in ("public", "application", "database"):
            addresses.add(f'module.network.aws_subnet.{tier}["{index}"]')
            addresses.add(f'module.network.aws_route_table_association.{tier}["{index}"]')
        for tier in ("application", "database"):
            addresses.add(f'module.network.aws_route_table.{tier}["{index}"]')
        addresses.add(f'module.network.aws_route.nat["{index}"]')
    for service in ("account", "payment"):
        for kind in ("aws_ecr_repository", "aws_ecr_lifecycle_policy"):
            addresses.add(f'module.registry.{kind}.service["{service}"]')
    addresses.update(f'module.eks.aws_eks_addon.this["{name}"]' for name in ("coredns", "metrics-server"))
    return addresses


def common_tags(inputs):
    result = {"Project": "BankingReleasePlatform", "Environment": "dev", "ManagedBy": "Terraform",
              "Owner": inputs.get("owner", "MahmoudHachem"), "Purpose": "CloudEngineerTraining"}
    if inputs.get("cost_center") is not None:
        result["CostCenter"] = inputs["cost_center"]
    return result


def audit(plan, inputs, *, require_effective_tags=True):
    """Mock providers leave tags_all unknown; real saved plans must resolve it."""
    managed = {r["address"]: r for r in plan["resource_changes"] if r.get("mode") == "managed"}
    if set(managed) != inventory_addresses():
        raise ValueError("Exact initial inventory mismatch: " + str(sorted(set(managed) ^ inventory_addresses())))
    common = common_tags(inputs)
    rows = []
    for address, item in sorted(managed.items()):
        kind, after = item["type"], item["change"].get("after") or {}
        if kind not in UNTAGGABLE:
            component = ("logging" if kind in {"aws_flow_log", "aws_cloudwatch_log_group"} else
                         "security" if kind in {"aws_default_security_group", "aws_iam_openid_connect_provider", "aws_eks_access_entry"} else
                         "fargate" if kind == "aws_eks_fargate_profile" else
                         "network" if address.startswith("module.network.") else
                         "registry" if address.startswith("module.registry.") else "eks")
            for field in (["tags", "tags_all"] if require_effective_tags else ["tags"]):
                tags = after.get(field) or {}
                if any(tags.get(k) != v for k, v in dict(common, Component=component).items()):
                    raise ValueError("Missing/incorrect/unknown " + field + ": " + address)
                if not tags.get("Name", "").startswith("banking-dev"):
                    raise ValueError("Meaningful Banking Name tag required: " + address)
                if inputs.get("cost_center") is None and "CostCenter" in tags:
                    raise ValueError("No unapproved CostCenter: " + address)
        rows.append({"address": address, "type": kind, "name": after.get("name") or after.get("fargate_profile_name") or (after.get("tags") or {}).get("Name"),
                     "tags": after.get("tags"), "tags_all": after.get("tags_all"),
                     "tags_supported": kind not in UNTAGGABLE})

    def resource(address):
        return managed[address]["change"]["after"]

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    vpc = resource("module.network.aws_vpc.this")
    require(vpc["cidr_block"] == inputs.get("vpc_cidr", "10.70.0.0/16") and vpc["enable_dns_support"] and vpc["enable_dns_hostnames"], "VPC CIDR/DNS mismatch")
    base = ipaddress.ip_network(vpc["cidr_block"], strict=True)
    ranges = []
    for tier, offsets, prefix in [("public", (0, 1), 24), ("application", (2, 3), 20), ("database", (64, 65), 24)]:
        for index, offset in enumerate(offsets):
            subnet = resource(f'module.network.aws_subnet.{tier}["{index}"]')
            cidr = str(ipaddress.ip_network((int(base.network_address) + offset * 2 ** (32-prefix), prefix)))
            require(subnet["cidr_block"] == cidr and subnet["availability_zone"] == inputs["availability_zones"][index] and subnet["map_public_ip_on_launch"] is False, "Subnet CIDR/AZ/public-IP mismatch")
            ranges.append(ipaddress.ip_network(cidr))
            discovery = "kubernetes.io/role/elb" if tier == "public" else "kubernetes.io/role/internal-elb"
            if tier != "database":
                require(subnet["tags"].get(discovery) == "1", "Missing ALB discovery tag")
            if tier == "database":
                require(resource(f'module.network.aws_route_table.database["{index}"]')["route"] == [], "Database external routing is forbidden")
    require(not any(a.overlaps(b) for i, a in enumerate(ranges) for b in ranges[i+1:]), "Subnet ranges overlap")
    require(all(resource(a)["destination_cidr_block"] == "0.0.0.0/0" for a in managed if a.startswith("module.network.aws_route.")), "Unexpected default route")
    sg = resource("module.network.aws_default_security_group.closed")
    require(sg["ingress"] == [] and sg["egress"] == [], "VPC default group must stay closed")
    endpoint = resource("module.network.aws_vpc_endpoint.s3")
    require(endpoint["vpc_endpoint_type"] == "Gateway" and len(endpoint["route_table_ids"]) == 2, "S3 endpoint must serve both application route tables")
    require(endpoint["service_name"] == "com.amazonaws.us-east-2.s3" and json.loads(endpoint["policy"])["Statement"] == [{"Sid":"RegionalECRLayersOnly", "Effect":"Allow", "Principal":"*", "Action":["s3:GetObject"], "Resource":["arn:aws:s3:::prod-us-east-2-starport-layer-bucket/*"]}], "S3 endpoint must restrict access to regional ECR layers")
    cluster = resource("module.eks.aws_eks_cluster.this")
    require(cluster["name"] == "banking-dev" and cluster["role_arn"] == inputs["cluster_role_arn"] and cluster["version"] == inputs["kubernetes_version"], "Cluster identity/version mismatch")
    network = cluster["vpc_config"][0]
    require(network["endpoint_private_access"] and network["endpoint_public_access"] and set(network["public_access_cidrs"]) == set(inputs["endpoint_cidrs"]), "Endpoint protection mismatch")
    require(all(ipaddress.ip_network(c).version == 4 and ipaddress.ip_network(c).prefixlen >= 24 for c in network["public_access_cidrs"]), "Unsafe public endpoint CIDR")
    require(cluster["access_config"] == [{"authentication_mode": "API", "bootstrap_cluster_creator_admin_permissions": False}], "Implicit creator access forbidden")
    require(not cluster["bootstrap_self_managed_addons"] and not cluster.get("compute_config"), "EC2/Auto Mode bootstrap forbidden")
    require(cluster["deletion_protection"] is True, "EKS deletion protection must remain enabled")
    require(set(cluster["enabled_cluster_log_types"]) == {"api", "audit", "authenticator", "controllerManager", "scheduler"}, "Control-plane logs incomplete")
    require(cluster["encryption_config"][0]["provider"][0]["key_arn"] == inputs["kms_key_arn"] and cluster["encryption_config"][0]["resources"] == ["secrets"], "Cluster KMS mismatch")
    selectors = {"coredns": [{"namespace": "kube-system", "labels": {"k8s-app": "kube-dns"}}],
        "controller": [{"namespace": "kube-system", "labels": {"app.kubernetes.io/name": "aws-load-balancer-controller"}}, {"namespace": "kube-system", "labels": {"k8s-app": "metrics-server"}}],
        "banking": [{"namespace": "banking-dev"}]}
    for name, desired in selectors.items():
        profile = resource("module.eks.aws_eks_fargate_profile." + name)
        normalized = [{"namespace": s["namespace"], **({"labels": s["labels"]} if s.get("labels") else {})} for s in profile["selector"]]
        require(sorted(normalized, key=str) == sorted(desired, key=str) and profile["cluster_name"] == "banking-dev" and profile["fargate_profile_name"] == "banking-dev-" + ("app" if name == "banking" else name) and profile["pod_execution_role_arn"] == inputs["fargate_execution_role_arn"] and len(profile["subnet_ids"]) == 2, "Fargate profile mismatch")
    configs = json.loads(Path("infra/modules/eks/addon-configuration.json").read_text())
    for name, config in configs.items():
        addon = resource(f'module.eks.aws_eks_addon.this["{name}"]')
        require(addon["addon_version"] == inputs["addon_versions"][name] and json.loads(addon["configuration_values"]) == config and addon["resolve_conflicts_on_create"] == "NONE", "Add-on pin/configuration mismatch")
    for name, namespace, policy in [("operator", False, "AmazonEKSClusterAdminPolicy"), ("deployer", True, "AmazonEKSEditPolicy")]:
        entry = resource("module.eks.aws_eks_access_entry." + name)
        association = resource("module.eks.aws_eks_access_policy_association." + name)
        require(entry["principal_arn"] == inputs[name + "_role_arn"] and association["policy_arn"] == "arn:aws:eks::aws:cluster-access-policy/" + policy, "Access identity/policy mismatch")
        scope = association["access_scope"][0]
        require(scope["type"] == ("namespace" if namespace else "cluster") and (not namespace or scope["namespaces"] == ["banking-dev"]), "Application access must stay namespace scoped")
    for address in ("module.eks.aws_cloudwatch_log_group.cluster", "module.network.aws_cloudwatch_log_group.flow"):
        log = resource(address)
        require(log["retention_in_days"] == 30 and log["kms_key_id"] == inputs["kms_key_arn"], "Encrypted log retention mismatch")
    require(resource("module.network.aws_flow_log.this")["iam_role_arn"] == inputs["flow_log_role_arn"], "Flow-log service role mismatch")
    for name in ("account", "payment"):
        repo = resource(f'module.registry.aws_ecr_repository.service["{name}"]')
        lifecycle = resource(f'module.registry.aws_ecr_lifecycle_policy.service["{name}"]')
        require(repo["name"] == "banking-dev-" + name and repo["image_tag_mutability"] == "IMMUTABLE" and repo["force_delete"] is False and repo["image_scanning_configuration"][0]["scan_on_push"] and repo["encryption_configuration"][0]["encryption_type"] == "AES256", "ECR release protection mismatch")
        rules = json.loads(lifecycle["policy"])["rules"]
        require(len(rules) == 1 and rules[0]["selection"] == {"tagStatus": "untagged", "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 7}, "Tagged rollback releases must be retained")
    return {"inventory": rows, "taggable_resources": sum(r["tags_supported"] for r in rows),
            "effective_tags_verified": require_effective_tags, "subnet_layout": [str(c) for c in ranges]}
