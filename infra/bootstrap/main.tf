terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.68.0" }
  }
  # The explicit GitHub initialize operation seeds the secured bucket first,
  # then imports these resources directly into S3 state. No local state handoff.
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}

variable "aws_region" {
  type        = string
  description = "Owner-approved AWS Region; no assumed default."
}
variable "expected_account_id" {
  type        = string
  description = "Verified target account, supplied outside committed configuration."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Supply the verified 12-digit AWS account ID."
  }
}
variable "state_bucket_name" {
  type        = string
  description = "Dedicated bucket approved for this root to manage; never a shared existing bucket."
}
provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]
  default_tags {
    tags = { Project = "BankingReleasePlatform", Environment = "bootstrap", ManagedBy = "Terraform" }
  }
}
module "state_bucket" {
  source      = "../modules/state-bucket"
  bucket_name = var.state_bucket_name
}
output "state_bucket_name" { value = module.state_bucket.bucket_name }
output "bootstrap_state_key" { value = "banking-release-platform/bootstrap/terraform.tfstate" }
