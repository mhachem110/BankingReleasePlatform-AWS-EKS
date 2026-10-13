mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "866934333672" } }
}
variables {
  aws_region          = "us-east-2"
  expected_account_id = "866934333672"
  state_bucket_name   = "mhachem-banking-tfstate-866934333672"
}
run "vpc_without_iam_or_kms" {
  command = plan
}
run "wrong_account" {
  command = plan
  variables { expected_account_id = "000000000000" }
  expect_failures = [terraform_data.prerequisites]
}
run "wrong_cidr" {
  command = plan
  variables { vpc_cidr = "10.80.0.0/16" }
  expect_failures = [var.vpc_cidr]
}
