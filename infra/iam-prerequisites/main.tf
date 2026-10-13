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
variable "permissions_boundary_arn" {
  type = string
  validation {
    condition     = var.permissions_boundary_arn == "arn:aws:iam::866934333672:policy/cloudbatch818-mahmoud-banking-service-boundary"
    error_message = "Only the separately authorized, administrator-controlled Banking service boundary is allowed."
  }
}
variable "boundary_policy_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.boundary_policy_sha256))
    error_message = "Pin the canonical SHA256 of the reviewed live boundary document."
  }
}
locals {
  proposal = "${path.module}/../../iam/phase3/proposed"
  tags     = { Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "service-iam" }
  roles = {
    cluster = "cloudbatch818-mahmoud-banking-eks-cluster"
    fargate = "cloudbatch818-mahmoud-banking-fargate-execution"
    flow    = "cloudbatch818-mahmoud-banking-flow-logs"
  }
}
data "aws_caller_identity" "current" {}
data "aws_iam_policy" "boundary" { arn = var.permissions_boundary_arn }
resource "terraform_data" "authorization" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == "866934333672" && sha256(jsonencode(jsondecode(data.aws_iam_policy.boundary.policy))) == var.boundary_policy_sha256
      error_message = "Stop if the account or administrator-controlled boundary differs from the reviewed document."
    }
  }
}
resource "aws_iam_role" "service" {
  for_each              = local.roles
  name                  = each.value
  path                  = "/"
  description           = "Banking ${each.key} service identity; no GitHub or IAM administration"
  assume_role_policy    = file("${local.proposal}/${each.value}-trust.json")
  permissions_boundary  = var.permissions_boundary_arn
  max_session_duration  = 3600
  force_detach_policies = false
  tags                  = merge(local.tags, { Name = each.value })
  depends_on            = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.service["cluster"].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_iam_role_policy_attachment" "fargate" {
  role       = aws_iam_role.service["fargate"].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSFargatePodExecutionRolePolicy"
}
resource "aws_iam_role_policy" "flow" {
  name   = "BankingFlowLogs"
  role   = aws_iam_role.service["flow"].name
  policy = file("${local.proposal}/BankingFlowLogs.json")
}
output "service_roles" { value = { for k, r in aws_iam_role.service : k => r.arn } }
output "permissions_boundary_arn" { value = var.permissions_boundary_arn }
output "boundary_policy_sha256" { value = var.boundary_policy_sha256 }
output "contract_version" { value = 1 }
output "state_key" { value = "banking-release-platform/shared/iam-prerequisites/terraform.tfstate" }
