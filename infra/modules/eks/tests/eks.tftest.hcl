mock_provider "aws" {
  mock_data "aws_vpc" { defaults = { cidr_block = "10.70.0.0/16" } }
}
variables {
  name                 = "banking-dev"
  vpc_id               = "vpc-00000000000000000"
  subnet_ids           = ["subnet-00000000000000001", "subnet-00000000000000002"]
  cluster_role_arn     = "arn:aws:iam::123456789012:role/test-cluster"
  node_role_arn        = "arn:aws:iam::123456789012:role/test-nodes"
  controller_role_arn  = "arn:aws:iam::123456789012:role/test-controller"
  operator_role_arn    = "arn:aws:iam::123456789012:role/test-operator"
  deployer_role_arn    = "arn:aws:iam::123456789012:role/test-deployer"
  kms_key_arn          = "arn:aws:kms:us-east-2:123456789012:key/00000000-0000-0000-0000-000000000000"
  kubernetes_version   = "1.36"
  node_release_version = "1.36.0-offline-fixture"
  endpoint_cidrs       = ["203.0.113.10/32"]
  addon_versions = {
    vpc-cni                = "v1.0.0-eksbuild.1"
    kube-proxy             = "v1.0.0-eksbuild.1"
    coredns                = "v1.0.0-eksbuild.1"
    metrics-server         = "v1.0.0-eksbuild.1"
    eks-pod-identity-agent = "v1.0.0-eksbuild.1"
  }
}
run "cluster_security" {
  command = plan
  assert {
    condition     = aws_eks_cluster.this.access_config[0].authentication_mode == "API" && !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "Access must be explicit; creator must not receive implicit cluster admin."
  }
  assert {
    condition     = aws_eks_access_policy_association.deployer.access_scope[0].type == "namespace" && aws_eks_access_policy_association.deployer.access_scope[0].namespaces == toset(["banking-dev"])
    error_message = "Application deployer must not receive cluster-wide rights."
  }
  assert {
    condition     = aws_eks_cluster.this.upgrade_policy[0].support_type == "STANDARD" && length(aws_eks_cluster.this.enabled_cluster_log_types) == 5
    error_message = "Avoid automatic extended-support charges and retain all control-plane log types."
  }
  assert {
    condition     = aws_launch_template.nodes.metadata_options[0].http_tokens == "required" && aws_launch_template.nodes.metadata_options[0].http_put_response_hop_limit == 1 && aws_launch_template.nodes.block_device_mappings[0].ebs[0].encrypted
    error_message = "Worker disks must be encrypted; pods must not inherit node metadata credentials."
  }
  assert {
    condition     = aws_eks_node_group.this.scaling_config[0].desired_size == 2 && aws_eks_node_group.this.capacity_type == "ON_DEMAND" && aws_eks_node_group.this.ami_type == "AL2023_x86_64_STANDARD"
    error_message = "Reviewed baseline uses two managed AL2023 workers."
  }
}
run "public_endpoint_rejected" {
  command = plan
  variables { endpoint_cidrs = ["0.0.0.0/0"] }
  expect_failures = [var.endpoint_cidrs]
}
run "missing_addon_rejected" {
  command = plan
  variables { addon_versions = {} }
  expect_failures = [var.addon_versions]
}
