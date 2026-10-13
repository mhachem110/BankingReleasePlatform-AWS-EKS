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
  default_tags { tags = local.common_tags }
}
variable "aws_region" { type = string }
variable "expected_account_id" { type = string }
variable "state_bucket_name" { type = string }
variable "vpc_cidr" {
  type    = string
  default = "10.70.0.0/16"
  validation {
    condition     = var.vpc_cidr == "10.70.0.0/16"
    error_message = "The initial Banking VPC uses the reviewed 10.70.0.0/16 CIDR."
  }
}
variable "owner" {
  type    = string
  default = "MahmoudHachem"
}
variable "cost_center" {
  type     = string
  default  = null
  nullable = true
}
locals {
  common_tags = merge({
    Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform",
    Owner   = var.owner, Purpose = "CloudEngineerTraining"
  }, var.cost_center == null ? {} : { CostCenter = var.cost_center })
}
data "aws_caller_identity" "current" {}
# Same addresses and backend key as the full platform: no import/state move.
resource "terraform_data" "prerequisites" {
  lifecycle {
    precondition {
      condition = (var.aws_region == "us-east-2" && var.expected_account_id == "866934333672" &&
        data.aws_caller_identity.current.account_id == var.expected_account_id &&
      var.state_bucket_name == "mhachem-banking-tfstate-866934333672")
      error_message = "Use only the verified Ohio Banking account and existing state bucket."
    }
  }
}
module "network" {
  source     = "../modules/vpc-seed"
  name       = "banking-dev"
  cidr       = var.vpc_cidr
  tags       = local.common_tags
  depends_on = [terraform_data.prerequisites]
}
output "vpc_id" { value = module.network.vpc_id }
output "default_security_group_id" { value = module.network.default_security_group_id }
