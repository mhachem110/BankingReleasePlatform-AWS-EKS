# This dedicated teardown root has no resource creation configuration. It reads
# one explicitly selected Banking state with the same pinned root AWS provider.
# The protected workflow validates every existing address/ID/tag before saving
# a destroy-only plan; creation roots retain their prevent_destroy safeguards.
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
  region              = "us-east-2"
  allowed_account_ids = ["866934333672"]
}
