mock_provider "aws" {}
variables {
  name = "banking-dev"
  tags = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform", Owner = "TestOwner", Purpose = "CloudEngineerTraining" }
}
run "release_retention" {
  command = plan
  assert {
    condition     = length(aws_ecr_repository.service) == 2 && alltrue([for repo in aws_ecr_repository.service : repo.image_tag_mutability == "IMMUTABLE" && repo.image_scanning_configuration[0].scan_on_push && !repo.force_delete])
    error_message = "Both repositories must prevent tag overwrite, scan images, and prevent forced deletion."
  }
  assert {
    condition     = alltrue([for policy in aws_ecr_lifecycle_policy.service : jsondecode(policy.policy).rules[0].selection.tagStatus == "untagged"])
    error_message = "Tagged rollback releases must not expire."
  }
}
