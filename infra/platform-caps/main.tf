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
variable "documents" { type = map(string) }
variable "bindings" { type = map(string) }
locals {
  names = toset([for i in [1, 2, 3] : "BankingTerraformProvisioner-Platform-${i}"])
  tags  = { Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "platform-caps" }
}
data "aws_caller_identity" "current" {}
resource "terraform_data" "authorization" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "866934333672" && toset(keys(var.documents)) == local.names
      error_message = "Publish only the three reviewed Banking platform session caps."
    }
  }
}
# These are session restrictions, not role attachments or bootstrap permission
# additions. The pipeline regenerates each document from verified dependencies.
resource "aws_iam_policy" "project" {
  for_each    = local.names
  name        = each.value
  path        = "/"
  description = "Banking platform session restriction; never attached to bootstrap"
  policy      = var.documents[each.value]
  tags        = merge(local.tags, { Name = each.value })
  depends_on  = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
output "bindings" { value = var.bindings }
output "policies" { value = { for name, item in aws_iam_policy.project : name => { arn = item.arn, sha256 = sha256(var.documents[name]) } } }
output "state_key" { value = "banking-release-platform/shared/platform-caps/terraform.tfstate" }
output "contract_version" { value = 1 }
