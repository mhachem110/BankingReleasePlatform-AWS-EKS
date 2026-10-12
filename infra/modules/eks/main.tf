terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
}
variable "name" { type = string }
variable "tags" { type = map(string) }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "cluster_role_arn" { type = string }
variable "fargate_execution_role_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/[^/]+$", var.fargate_execution_role_arn))
    error_message = "EKS Fargate execution role must have no IAM path."
  }
}
variable "kms_key_arn" { type = string }
variable "kubernetes_version" { type = string }
variable "endpoint_cidrs" {
  type = list(string)
  validation {
    condition = length(var.endpoint_cidrs) > 0 && alltrue([
      for cidr in var.endpoint_cidrs : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) >= 24, false)
    ])
    error_message = "Supply approved IPv4 operator/runner CIDRs of /24 or narrower."
  }
}
variable "operator_role_arn" { type = string }
variable "deployer_role_arn" { type = string }
variable "addon_versions" {
  type = map(string)
  validation {
    condition = toset(keys(var.addon_versions)) == toset(["coredns", "metrics-server"]) && alltrue([
      for version in values(var.addon_versions) : can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+-eksbuild\\.[0-9]+$", version))
    ])
    error_message = "Pin exactly CoreDNS and Metrics Server; no EC2 DaemonSet add-ons."
  }
}
locals { addon_configuration = jsondecode(file("${path.module}/addon-configuration.json")) }
resource "aws_cloudwatch_log_group" "cluster" {
  tags = merge(var.tags, { Component = "logging", Name = "${var.name}-cluster-logs" })
  # checkov:skip=CKV_AWS_338:Development logs retain 30 days; review annual retention in Phase 6.
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
}
resource "aws_eks_cluster" "this" {
  tags = merge(var.tags, { Component = "eks", Name = "${var.name}" })
  # checkov:skip=CKV_AWS_339:Scanner 3.3.17 predates EKS 1.36; review AWS release calendar before deployment.
  # checkov:skip=CKV_AWS_39:Private endpoint plus explicit /24-or-narrower operator CIDRs.
  # checkov:skip=CKV_AWS_38:Public HTTPS needed for approved external operator; private endpoint enabled.
  name                          = var.name
  deletion_protection           = true
  role_arn                      = var.cluster_role_arn
  version                       = var.kubernetes_version
  enabled_cluster_log_types     = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  bootstrap_self_managed_addons = false
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
# Cluster issuer is separate from GitHub OIDC. IAM retrieves the initial CA
# thumbprint; no guessed certificate hash. No IAM roles are Terraform-managed.
resource "aws_iam_openid_connect_provider" "cluster" {
  url            = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list = ["sts.amazonaws.com"]
  tags           = merge(var.tags, { Component = "security" }, { Name = "${var.name}-irsa" })
}
# EKS profile creation is sequential. The root waits for private NAT routes.
resource "aws_eks_fargate_profile" "coredns" {
  tags                   = merge(var.tags, { Component = "fargate", Name = "${var.name}-coredns" })
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name}-coredns"
  pod_execution_role_arn = var.fargate_execution_role_arn
  subnet_ids             = var.subnet_ids
  selector {
    namespace = "kube-system"
    labels    = { "k8s-app" = "kube-dns" }
  }
}
resource "aws_eks_fargate_profile" "controller" {
  tags                   = merge(var.tags, { Component = "fargate", Name = "${var.name}-controller" })
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name}-controller"
  pod_execution_role_arn = var.fargate_execution_role_arn
  subnet_ids             = var.subnet_ids
  selector {
    namespace = "kube-system"
    labels    = { "app.kubernetes.io/name" = "aws-load-balancer-controller" }
  }
  selector {
    namespace = "kube-system"
    labels    = { "k8s-app" = "metrics-server" }
  }
  depends_on = [aws_eks_fargate_profile.coredns]
}
resource "aws_eks_fargate_profile" "banking" {
  tags                   = merge(var.tags, { Component = "fargate", Name = "${var.name}-app" })
  cluster_name           = aws_eks_cluster.this.name
  fargate_profile_name   = "${var.name}-app"
  pod_execution_role_arn = var.fargate_execution_role_arn
  subnet_ids             = var.subnet_ids
  selector { namespace = "banking-dev" }
  depends_on = [aws_eks_fargate_profile.controller]
}
resource "aws_eks_access_entry" "operator" {
  tags          = merge(var.tags, { Component = "security", Name = "${var.name}-operator-access" })
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
  tags              = merge(var.tags, { Component = "security", Name = "${var.name}-deployer-access" })
  cluster_name      = aws_eks_cluster.this.name
  principal_arn     = var.deployer_role_arn
  kubernetes_groups = ["banking-release-verifier"]
  type              = "STANDARD"
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
  tags                        = merge(var.tags, { Component = "eks", Name = "${var.name}-${each.key}-addon" })
  for_each                    = var.addon_versions
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = each.key
  addon_version               = each.value
  resolve_conflicts_on_create = "NONE"
  resolve_conflicts_on_update = "NONE"
  configuration_values        = jsonencode(local.addon_configuration[each.key])
  depends_on                  = [aws_eks_fargate_profile.banking]
}
output "cluster_name" { value = aws_eks_cluster.this.name }
output "endpoint" { value = aws_eks_cluster.this.endpoint }
output "cluster_security_group_id" { value = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id }
output "oidc_issuer_url" { value = aws_iam_openid_connect_provider.cluster.url }
output "oidc_provider_arn" { value = aws_iam_openid_connect_provider.cluster.arn }
output "fargate_profiles" {
  value = {
    coredns    = aws_eks_fargate_profile.coredns.fargate_profile_name
    controller = aws_eks_fargate_profile.controller.fargate_profile_name
    banking    = aws_eks_fargate_profile.banking.fargate_profile_name
  }
}
