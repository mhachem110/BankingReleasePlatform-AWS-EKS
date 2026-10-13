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
    tags = local.common_tags
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
variable "fargate_execution_role_arn" { type = string }
variable "flow_log_role_arn" { type = string }
variable "operator_role_arn" { type = string }
variable "deployer_role_arn" { type = string }
variable "prod_deployer_role_arn" { type = string }
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
variable "addon_versions" { type = map(string) }
variable "owner" {
  type    = string
  default = "MahmoudHachem"
  validation {
    condition     = length(trimspace(var.owner)) > 0 && length(var.owner) <= 128
    error_message = "Use the approved non-sensitive project owner tag."
  }
}
variable "cost_center" {
  type     = string
  default  = null
  nullable = true
  validation {
    condition     = var.cost_center == null ? true : length(trimspace(var.cost_center)) > 0 && length(var.cost_center) <= 128
    error_message = "Omit CostCenter until an actual approved value is assigned."
  }
}
locals {
  name = "banking-dev"
  common_tags = merge({
    Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform",
    Owner   = var.owner, Purpose = "CloudEngineerTraining"
  }, var.cost_center == null ? {} : { CostCenter = var.cost_center })
}
data "aws_caller_identity" "current" {}
data "aws_iam_role" "cluster" { name = "cloudbatch818-mahmoud-banking-eks-cluster" }
data "aws_iam_role" "fargate" { name = "cloudbatch818-mahmoud-banking-fargate-execution" }
data "aws_iam_role" "flow" { name = "cloudbatch818-mahmoud-banking-flow-logs" }
# Read the actual Terraform-managed IAM stage outputs. No administrator role
# ARN is a substitute for this independently locked state contract.
data "terraform_remote_state" "iam" {
  backend = "s3"
  config = {
    bucket              = var.state_bucket_name
    key                 = "banking-release-platform/shared/iam-prerequisites/terraform.tfstate"
    region              = var.aws_region
    encrypt             = true
    allowed_account_ids = [var.expected_account_id]
  }
}
variable "iam_boundary_policy_sha256" { type = string }
locals { service_roles = data.terraform_remote_state.iam.outputs.service_roles }
data "aws_kms_key" "this" { key_id = var.kms_key_arn }
resource "terraform_data" "prerequisites" {
  lifecycle {
    precondition {
      condition = (var.aws_region == "us-east-2" && data.aws_caller_identity.current.account_id == var.expected_account_id &&
        data.aws_iam_role.cluster.arn == var.cluster_role_arn && data.aws_iam_role.fargate.arn == var.fargate_execution_role_arn &&
        data.aws_iam_role.flow.arn == var.flow_log_role_arn &&
        data.terraform_remote_state.iam.outputs.contract_version == 1 &&
        data.terraform_remote_state.iam.outputs.state_key == "banking-release-platform/shared/iam-prerequisites/terraform.tfstate" &&
        data.terraform_remote_state.iam.outputs.permissions_boundary_arn == "arn:aws:iam::${var.expected_account_id}:policy/cloudbatch818-mahmoud-banking-service-boundary" &&
        data.terraform_remote_state.iam.outputs.boundary_policy_sha256 == var.iam_boundary_policy_sha256 &&
        local.service_roles == { cluster = var.cluster_role_arn, fargate = var.fargate_execution_role_arn, flow = var.flow_log_role_arn } &&
        length(distinct([var.cluster_role_arn, var.fargate_execution_role_arn, var.flow_log_role_arn, var.operator_role_arn, var.deployer_role_arn, var.prod_deployer_role_arn])) == 6 &&
        var.operator_role_arn != var.deployer_role_arn &&
        !endswith(var.operator_role_arn, "/cloudbatch818-mahmoud-cloudops-bootstrap") &&
        !endswith(var.deployer_role_arn, "/cloudbatch818-mahmoud-cloudops-bootstrap") &&
        !endswith(var.prod_deployer_role_arn, "/cloudbatch818-mahmoud-cloudops-bootstrap") &&
        alltrue([for arn in [var.operator_role_arn, var.deployer_role_arn, var.prod_deployer_role_arn] : startswith(arn, "arn:aws:iam::${var.expected_account_id}:role/")]) &&
        startswith(var.kms_key_arn, "arn:aws:kms:${var.aws_region}:${var.expected_account_id}:key/") &&
      data.aws_kms_key.this.key_state == "Enabled")
      error_message = "Terraform-managed IAM outputs, reviewed boundary, distinct access roles, enabled key and account must match verified inputs."
    }
  }
}
module "network" {
  aws_region         = var.aws_region
  tags               = local.common_tags
  source             = "../../../modules/network"
  name               = local.name
  cidr               = var.vpc_cidr
  availability_zones = var.availability_zones
  flow_log_role_arn  = local.service_roles.flow
  logs_kms_key_arn   = var.kms_key_arn
  depends_on         = [terraform_data.prerequisites]
}
module "registry" {
  tags       = local.common_tags
  source     = "../../../modules/registry"
  name       = local.name
  depends_on = [terraform_data.prerequisites]
}
module "eks" {
  tags                       = local.common_tags
  source                     = "../../../modules/eks"
  name                       = local.name
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.application_subnet_ids
  cluster_role_arn           = local.service_roles.cluster
  fargate_execution_role_arn = local.service_roles.fargate
  kms_key_arn                = var.kms_key_arn
  kubernetes_version         = var.kubernetes_version
  endpoint_cidrs             = var.endpoint_cidrs
  operator_role_arn          = var.operator_role_arn
  deployer_role_arn          = var.deployer_role_arn
  prod_deployer_role_arn     = var.prod_deployer_role_arn
  addon_versions             = var.addon_versions
  # Ensure private outbound routes/NAT are ready before Fargate profiles launch Pods.
  depends_on = [module.network]
}
output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "application_subnet_ids" { value = module.network.application_subnet_ids }
output "database_subnet_ids" { value = module.network.database_subnet_ids }
output "ecr_repositories" { value = module.registry.repositories }
output "cluster_name" { value = module.eks.cluster_name }
output "fargate_profiles" { value = module.eks.fargate_profiles }
output "cluster_security_group_id" { value = module.eks.cluster_security_group_id }
output "oidc_issuer_url" { value = module.eks.oidc_issuer_url }
output "oidc_provider_arn" { value = module.eks.oidc_provider_arn }
output "cluster_endpoint" { value = module.eks.endpoint }
output "controller_irsa_service_account" { value = "system:serviceaccount:kube-system:aws-load-balancer-controller" }
output "dev_platform_state_key" { value = "banking-release-platform/dev/platform/terraform.tfstate" }

output "application_namespaces" { value = ["banking-dev", "banking-prod"] }
output "common_resource_tags" { value = local.common_tags }

output "default_security_group_id" { value = module.network.default_security_group_id }
