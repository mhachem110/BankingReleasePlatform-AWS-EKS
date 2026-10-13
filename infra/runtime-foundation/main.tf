terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}
provider "aws" {
  region              = "us-east-2"
  allowed_account_ids = ["866934333672"]
  default_tags { tags = local.tags }
}
locals {
  tags      = { Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "runtime-foundation" }
  documents = "${path.module}/../../iam/runtime-foundation"
  operator  = "cloudbatch818-mahmoud-banking-operator"
}
data "aws_caller_identity" "current" {}
resource "terraform_data" "authorization" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "866934333672"
      error_message = "Use only the reviewed Banking account."
    }
  }
}
# This is a new project key. Existing state/backend and shared keys are retained.
resource "aws_kms_key" "runtime" {
  description                        = "Banking runtime encryption for EKS, logs and application data"
  key_usage                          = "ENCRYPT_DECRYPT"
  customer_master_key_spec           = "SYMMETRIC_DEFAULT"
  multi_region                       = false
  is_enabled                         = true
  enable_key_rotation                = true
  rotation_period_in_days            = 365
  deletion_window_in_days            = 7
  bypass_policy_lockout_safety_check = false
  policy                             = file("${local.documents}/key-policy.json")
  tags                               = merge(local.tags, { Name = "banking-runtime" })
  depends_on                         = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_kms_alias" "runtime" {
  name          = "alias/banking-release-platform-runtime"
  target_key_id = aws_kms_key.runtime.key_id
}
# AWS permission is restricted to describing the one cluster. Kubernetes access
# is granted separately through an explicit EKS access entry in the platform.
resource "aws_iam_role" "operator" {
  name                  = local.operator
  path                  = "/"
  assume_role_policy    = file("${local.documents}/operator-trust.json")
  max_session_duration  = 3600
  force_detach_policies = false
  tags                  = merge(local.tags, { Name = local.operator })
  depends_on            = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy" "operator" {
  name   = "BankingOperator"
  role   = aws_iam_role.operator.name
  policy = file("${local.documents}/operator-policy.json")
}
output "kms_key_arn" { value = aws_kms_key.runtime.arn }
output "operator_role_arn" { value = aws_iam_role.operator.arn }
output "state_key" { value = "banking-release-platform/shared/runtime-foundation/terraform.tfstate" }
output "contract_version" { value = 1 }
