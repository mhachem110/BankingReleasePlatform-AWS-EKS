mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "866934333672" } }
}
variables {
  documents = jsondecode(file("tests/fixtures.json")).documents
  bindings  = jsondecode(file("tests/fixtures.json")).bindings
}
run "three_session_caps_without_role_attachments" {
  command = plan
  assert {
    condition     = length(aws_iam_policy.project) == 3 && output.state_key == "banking-release-platform/shared/platform-caps/terraform.tfstate"
    error_message = "Create only the three bounded policies in their dedicated state."
  }
}
