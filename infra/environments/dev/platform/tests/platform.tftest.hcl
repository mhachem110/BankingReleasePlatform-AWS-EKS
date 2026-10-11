mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_kms_key" { defaults = { key_state = "Enabled" } }
  mock_data "aws_vpc" { defaults = { cidr_block = "10.70.0.0/16" } }
}
override_data {
  target = data.aws_iam_role.cluster
  values = { arn = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-eks-cluster" }
}
override_data {
  target = data.aws_iam_role.nodes
  values = { arn = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-eks-nodes" }
}
override_data {
  target = data.aws_iam_role.flow
  values = { arn = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-flow-logs" }
}
override_data {
  target = data.aws_iam_role.controller
  values = { arn = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-alb-controller" }
}
variables {
  aws_region           = "us-east-2"
  expected_account_id  = "123456789012"
  state_bucket_name    = "mhachem-banking-tfstate-123456789012"
  availability_zones   = ["us-east-2a", "us-east-2b"]
  cluster_role_arn     = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-eks-cluster"
  node_role_arn        = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-eks-nodes"
  flow_log_role_arn    = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-flow-logs"
  controller_role_arn  = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-banking-alb-controller"
  operator_role_arn    = "arn:aws:iam::123456789012:role/test-operator"
  deployer_role_arn    = "arn:aws:iam::123456789012:role/test-deployer"
  kms_key_arn          = "arn:aws:kms:us-east-2:123456789012:key/11111111-2222-4333-8444-555555555555"
  endpoint_cidrs       = ["203.0.113.10/32"]
  node_release_version = "1.36.0-offline-fixture"
  addon_versions = {
    vpc-cni                = "v1.0.0-eksbuild.1"
    kube-proxy             = "v1.0.0-eksbuild.1"
    coredns                = "v1.0.0-eksbuild.1"
    metrics-server         = "v1.0.0-eksbuild.1"
    eks-pod-identity-agent = "v1.0.0-eksbuild.1"
  }
}
run "integrated_plan" {
  command = plan
  assert {
    condition     = output.cluster_name == "banking-dev" && output.dev_platform_state_key == "banking-release-platform/dev/platform/terraform.tfstate"
    error_message = "Platform modules must use Banking identities and their own state path."
  }
}
run "bootstrap_role_as_node_rejected" {
  command = plan
  variables { node_role_arn = "arn:aws:iam::123456789012:role/cloudbatch818-mahmoud-cloudops-bootstrap" }
  expect_failures = [terraform_data.prerequisites]
}
