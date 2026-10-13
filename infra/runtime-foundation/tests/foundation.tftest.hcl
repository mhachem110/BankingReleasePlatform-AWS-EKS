mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "866934333672" } }
}
run "project_key_and_operator_only" {
  command = plan
  assert {
    condition     = aws_kms_key.runtime.enable_key_rotation && aws_kms_key.runtime.deletion_window_in_days == 7 && !aws_kms_key.runtime.multi_region
    error_message = "Use one rotated symmetric project key with a seven-day recovery window."
  }
  assert {
    condition     = aws_iam_role.operator.name == "cloudbatch818-mahmoud-banking-operator" && !aws_iam_role.operator.force_detach_policies
    error_message = "Never replace or force-detach a shared identity."
  }
}
