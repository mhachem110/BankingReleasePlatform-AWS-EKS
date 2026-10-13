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
  tags = { Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "policy-iam" }
  policies = {
    boundary = { name = "cloudbatch818-mahmoud-banking-service-boundary", file = "BankingServicePermissionsBoundary.json" }
    iam_cap  = { name = "BankingTerraformProvisioner-IamPrerequisites", file = "BankingTerraformProvisioner-IamPrerequisites.json" }
  }
}
data "aws_caller_identity" "current" {}
resource "terraform_data" "authorization" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "866934333672"
      error_message = "Use the verified Banking account."
    }
  }
}
resource "aws_iam_policy" "project" {
  for_each    = local.policies
  name        = each.value.name
  path        = "/"
  description = "Reviewed Banking ${each.key}; does not attach permissions to bootstrap"
  policy      = file("${path.module}/../../iam/provisioning/proposed/${each.value.file}")
  tags        = merge(local.tags, { Name = each.value.name })
  depends_on  = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
output "policy_arns" { value = { for key, item in aws_iam_policy.project : key => item.arn } }
output "policy_sha256" { value = { for key, item in aws_iam_policy.project : key => sha256(jsonencode(jsondecode(item.policy))) } }
output "state_key" { value = "banking-release-platform/shared/policy-prerequisites/terraform.tfstate" }
