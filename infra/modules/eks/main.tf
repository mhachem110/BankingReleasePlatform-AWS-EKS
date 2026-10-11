terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
}
variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "cluster_role_arn" { type = string }
variable "node_role_arn" { type = string }
variable "controller_role_arn" { type = string }
variable "kms_key_arn" { type = string }
variable "kubernetes_version" { type = string }
variable "node_release_version" { type = string }
variable "endpoint_cidrs" {
  type = list(string)
  validation {
    condition = length(var.endpoint_cidrs) > 0 && alltrue([
      for cidr in var.endpoint_cidrs : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) >= 24, false)
    ])
    error_message = "Supply approved IPv4 operator/runner CIDRs of /24 or narrower; never 0.0.0.0/0."
  }
}
variable "operator_role_arn" { type = string }
variable "deployer_role_arn" { type = string }
variable "addon_versions" {
  type = map(string)
  validation {
    condition = toset(keys(var.addon_versions)) == toset(["vpc-cni", "kube-proxy", "coredns", "metrics-server", "eks-pod-identity-agent"]) && alltrue([
      for version in values(var.addon_versions) : can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+-eksbuild\\.[0-9]+$", version))
    ])
    error_message = "Supply exactly five reviewed, compatible, pinned EKS add-on versions."
  }
}
resource "aws_cloudwatch_log_group" "cluster" {
  # checkov:skip=CKV_AWS_338:Development control-plane logs retain 30 days; review annual retention in Phase 6.
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
}
resource "aws_eks_cluster" "this" {
  # checkov:skip=CKV_AWS_339:Scanner 3.3.17 predates EKS 1.36; AWS lists it in standard support until 2027-08-02. See COSTS.md.
  # checkov:skip=CKV_AWS_39:Private access plus explicit /24-or-narrower operator CIDRs; no unrestricted public endpoint.
  # checkov:skip=CKV_AWS_38:Public HTTPS is needed for an approved external operator; private endpoint remains enabled.
  name                          = var.name
  role_arn                      = var.cluster_role_arn
  version                       = var.kubernetes_version
  enabled_cluster_log_types     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  bootstrap_self_managed_addons = true
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  upgrade_policy { support_type = "STANDARD" }
  encryption_config {
    resources = ["secrets"]
    provider { key_arn = var.kms_key_arn }
  }
  vpc_config {
    subnet_ids              = var.subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.endpoint_cidrs
  }
  depends_on = [aws_cloudwatch_log_group.cluster]
}
resource "aws_security_group" "nodes" {
  name_prefix = "${var.name}-nodes-"
  description = "Private managed nodes: peer traffic and control-plane connections"
  vpc_id      = var.vpc_id
  tags        = { Name = "${var.name}-nodes", "kubernetes.io/cluster/${var.name}" = "owned" }
}
resource "aws_vpc_security_group_ingress_rule" "peers" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "-1"
  description                  = "Node and pod traffic inside this node group"
}
resource "aws_vpc_security_group_ingress_rule" "control" {
  for_each                     = toset(["443", "10250", "10251", "9443"])
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = tonumber(each.key)
  to_port                      = tonumber(each.key)
  description                  = "Control plane to kubelet and admission webhooks"
}
resource "aws_vpc_security_group_ingress_rule" "api" {
  security_group_id            = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Private nodes to Kubernetes API"
}
resource "aws_vpc_security_group_egress_rule" "peers" {
  security_group_id            = aws_security_group.nodes.id
  referenced_security_group_id = aws_security_group.nodes.id
  ip_protocol                  = "-1"
  description                  = "Private node and pod communication"
}
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS via NAT or gateway endpoint for AWS APIs and image pulls"
}
resource "aws_vpc_security_group_egress_rule" "dns" {
  for_each          = toset(["tcp", "udp"])
  security_group_id = aws_security_group.nodes.id
  cidr_ipv4         = "${cidrhost(data.aws_vpc.this.cidr_block, 2)}/32"
  ip_protocol       = each.key
  from_port         = 53
  to_port           = 53
  description       = "VPC resolver DNS"
}
data "aws_vpc" "this" { id = var.vpc_id }
resource "aws_launch_template" "nodes" {
  name_prefix            = "${var.name}-"
  update_default_version = true
  vpc_security_group_ids = [aws_security_group.nodes.id]
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  monitoring { enabled = true }
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.name}-worker", Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform" }
  }
}
resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name}-workers"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.subnet_ids
  version         = var.kubernetes_version
  release_version = var.node_release_version
  ami_type        = "AL2023_x86_64_STANDARD"
  capacity_type   = "ON_DEMAND"
  instance_types  = ["t3.medium"]
  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 3
  }
  update_config { max_unavailable = 1 }
  launch_template {
    id      = aws_launch_template.nodes.id
    version = tostring(aws_launch_template.nodes.latest_version)
  }
  depends_on = [aws_vpc_security_group_ingress_rule.api, aws_vpc_security_group_ingress_rule.control,
  aws_vpc_security_group_egress_rule.https, aws_vpc_security_group_egress_rule.dns, aws_vpc_security_group_egress_rule.peers]
}
resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = var.operator_role_arn
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}
resource "aws_eks_access_entry" "deployer" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = var.deployer_role_arn
  type          = "STANDARD"
}
resource "aws_eks_access_policy_association" "deployer" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.deployer.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
  access_scope {
    type       = "namespace"
    namespaces = ["banking-dev"]
  }
}
resource "aws_eks_addon" "this" {
  for_each                    = var.addon_versions
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.key
  addon_version               = each.value
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "NONE"
  configuration_values        = each.key == "vpc-cni" ? jsonencode({ enableNetworkPolicy = "true" }) : null
  # Nodes bootstrap with AWS defaults and their explicitly approved CNI policy.
  # Waiting on healthy nodes avoids add-on/node creation dependency deadlocks.
  depends_on = [aws_eks_node_group.this]
}
resource "aws_eks_pod_identity_association" "controller" {
  cluster_name    = aws_eks_cluster.this.name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = var.controller_role_arn
  depends_on      = [aws_eks_addon.this]
}
output "cluster_name" { value = aws_eks_cluster.this.name }
output "endpoint" { value = aws_eks_cluster.this.endpoint }
output "node_security_group_id" { value = aws_security_group.nodes.id }
output "node_group_name" { value = aws_eks_node_group.this.node_group_name }
