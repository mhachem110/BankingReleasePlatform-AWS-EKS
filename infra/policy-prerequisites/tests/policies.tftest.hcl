mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "866934333672" } }
}
run "two_project_policies_only" {
  command = plan
  assert {
    condition     = length(aws_iam_policy.project) == 2 && aws_iam_policy.project["boundary"].name == "cloudbatch818-mahmoud-banking-service-boundary" && aws_iam_policy.project["iam_cap"].name == "BankingTerraformProvisioner-IamPrerequisites"
    error_message = "Only the two reviewed project policies may be published."
  }
}
