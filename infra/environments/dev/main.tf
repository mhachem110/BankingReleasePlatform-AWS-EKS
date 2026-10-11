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
variable "aws_region" {
  type        = string
  description = "Owner-approved AWS Region."
}
variable "expected_account_id" {
  type        = string
  description = "Verified account supplied through local inputs or GitHub environment variables."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Supply the verified 12-digit account ID."
  }
}
variable "state_bucket_name" {
  type        = string
  description = "Approved backend bucket, independently verified before initialization."
}
provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform" }
  }
}
# The workflow verifies bucket metadata separately, without taking ownership of it.
# This root reads identity and records approved configuration; no VPC/EKS resources.
data "aws_caller_identity" "current" {}
output "aws_account_verified" {
  value = data.aws_caller_identity.current.account_id == var.expected_account_id
  precondition {
    condition     = data.aws_caller_identity.current.account_id == var.expected_account_id
    error_message = "Unexpected AWS account."
  }
}
output "approved_state_bucket" { value = var.state_bucket_name }
output "dev_state_key" { value = "banking-release-platform/dev/foundation/terraform.tfstate" }
