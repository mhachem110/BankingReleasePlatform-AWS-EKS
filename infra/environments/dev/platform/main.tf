terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}
provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform" }
  }
}
variable "aws_region" { type = string }
variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Provide the reviewed account ID."
  }
}
variable "state_bucket_name" { type = string }
variable "availability_zones" { type = list(string) }
variable "vpc_cidr" {
  type    = string
  default = "10.70.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.vpc_cidr)) && try(split("/", var.vpc_cidr)[1] == "16", false)
    error_message = "Use an approved, non-overlapping IPv4 /16."
  }
}
variable "cluster_role_arn" { type = string }
variable "node_role_arn" { type = string }
variable "flow_log_role_arn" { type = string }
variable "controller_role_arn" { type = string }
variable "operator_role_arn" { type = string }
variable "deployer_role_arn" { type = string }
variable "kms_key_arn" { type = string }
variable "endpoint_cidrs" { type = list(string) }
variable "kubernetes_version" {
  type    = string
  default = "1.36"
  validation {
    condition     = var.kubernetes_version == "1.36"
    error_message = "This reviewed baseline uses Kubernetes 1.36; upgrade in a separate PR."
  }
}
variable "node_release_version" { type = string }
variable "addon_versions" { type = map(string) }
locals { name = "banking-dev" }
data "aws_caller_identity" "current" {}
data "aws_iam_role" "cluster" { name = "cloudbatch818-mahmoud-banking-eks-cluster" }
data "aws_iam_role" "nodes" { name = "cloudbatch818-mahmoud-banking-eks-nodes" }
data "aws_iam_role" "flow" { name = "cloudbatch818-mahmoud-banking-flow-logs" }
data "aws_iam_role" "controller" { name = "cloudbatch818-mahmoud-banking-alb-controller" }
data "aws_kms_key" "this" { key_id = var.kms_key_arn }
resource "terraform_data" "prerequisites" {
  lifecycle {
    precondition {
      condition = (var.aws_region == "us-east-2" && data.aws_caller_identity.current.account_id == var.expected_account_id &&
        data.aws_iam_role.cluster.arn == var.cluster_role_arn && data.aws_iam_role.nodes.arn == var.node_role_arn &&
        data.aws_iam_role.flow.arn == var.flow_log_role_arn && data.aws_iam_role.controller.arn == var.controller_role_arn &&
        length(distinct([var.cluster_role_arn, var.node_role_arn, var.flow_log_role_arn, var.controller_role_arn])) == 4 &&
        var.operator_role_arn != var.deployer_role_arn &&
        !endswith(var.operator_role_arn, "/cloudbatch818-mahmoud-cloudops-bootstrap") &&
        !endswith(var.deployer_role_arn, "/cloudbatch818-mahmoud-cloudops-bootstrap") &&
        alltrue([for arn in [var.operator_role_arn, var.deployer_role_arn] : startswith(arn, "arn:aws:iam::${var.expected_account_id}:role/")]) &&
        startswith(var.kms_key_arn, "arn:aws:kms:${var.aws_region}:${var.expected_account_id}:key/") &&
      data.aws_kms_key.this.key_state == "Enabled")
      error_message = "Administrator-provided distinct roles, enabled key and account must match verified inputs."
    }
  }
}
module "network" {
  source             = "../../../modules/network"
  name               = local.name
  cidr               = var.vpc_cidr
  availability_zones = var.availability_zones
  flow_log_role_arn  = var.flow_log_role_arn
  logs_kms_key_arn   = var.kms_key_arn
  depends_on         = [terraform_data.prerequisites]
}
module "registry" {
  source     = "../../../modules/registry"
  name       = local.name
  depends_on = [terraform_data.prerequisites]
}
module "eks" {
  source               = "../../../modules/eks"
  name                 = local.name
  vpc_id               = module.network.vpc_id
  subnet_ids           = module.network.application_subnet_ids
  cluster_role_arn     = var.cluster_role_arn
  node_role_arn        = var.node_role_arn
  controller_role_arn  = var.controller_role_arn
  kms_key_arn          = var.kms_key_arn
  kubernetes_version   = var.kubernetes_version
  node_release_version = var.node_release_version
  endpoint_cidrs       = var.endpoint_cidrs
  operator_role_arn    = var.operator_role_arn
  deployer_role_arn    = var.deployer_role_arn
  addon_versions       = var.addon_versions
  # Ensure private outbound routes/NAT are ready before workers bootstrap.
  depends_on = [module.network]
}
output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "application_subnet_ids" { value = module.network.application_subnet_ids }
output "database_subnet_ids" { value = module.network.database_subnet_ids }
output "ecr_repositories" { value = module.registry.repositories }
output "cluster_name" { value = module.eks.cluster_name }
output "node_group_name" { value = module.eks.node_group_name }
output "node_security_group_id" { value = module.eks.node_security_group_id }
output "dev_platform_state_key" { value = "banking-release-platform/dev/platform/terraform.tfstate" }
