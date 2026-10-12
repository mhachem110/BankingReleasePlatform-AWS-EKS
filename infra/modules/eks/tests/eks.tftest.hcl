mock_provider "aws" {
  mock_data "aws_vpc" { defaults = { cidr_block = "10.70.0.0/16" } }
}
variables {
  tags                       = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform", Owner = "TestOwner", Purpose = "CloudEngineerTraining" }
  name                       = "banking-dev"
  vpc_id                     = "vpc-00000000000000000"
  subnet_ids                 = ["subnet-00000000000000001", "subnet-00000000000000002"]
  cluster_role_arn           = "arn:aws:iam::123456789012:role/test-cluster"
  fargate_execution_role_arn = "arn:aws:iam::123456789012:role/test-fargate"
  operator_role_arn          = "arn:aws:iam::123456789012:role/test-operator"
  deployer_role_arn          = "arn:aws:iam::123456789012:role/test-deployer"
  kms_key_arn                = "arn:aws:kms:us-east-2:123456789012:key/00000000-0000-0000-0000-000000000000"
  kubernetes_version         = "1.36"
  endpoint_cidrs             = ["203.0.113.10/32"]
  addon_versions = {
    coredns        = "v1.0.0-eksbuild.1"
    metrics-server = "v1.0.0-eksbuild.1"
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
    condition     = aws_eks_access_entry.deployer.kubernetes_groups == toset(["banking-release-verifier"])
    error_message = "Release verification must use the explicit read-only RBAC group."
  }
  assert {
    condition     = aws_eks_cluster.this.upgrade_policy[0].support_type == "STANDARD" && length(aws_eks_cluster.this.enabled_cluster_log_types) == 5
    error_message = "Avoid automatic extended-support charges and retain all control-plane log types."
  }
  assert {
    condition     = !aws_eks_cluster.this.bootstrap_self_managed_addons && toset(keys(aws_eks_addon.this)) == toset(["coredns", "metrics-server"])
    error_message = "Fargate must not bootstrap EC2 DaemonSets or a Pod Identity agent."
  }
  assert {
    condition     = one(aws_eks_fargate_profile.banking.selector).namespace == "banking-dev" && try(length(one(aws_eks_fargate_profile.banking.selector).labels), 0) == 0
    error_message = "Every banking-dev Pod must match the application profile."
  }
  assert {
    condition     = one(aws_eks_fargate_profile.coredns.selector).labels["k8s-app"] == "kube-dns" && length(aws_eks_fargate_profile.controller.selector) == 2
    error_message = "DNS, controller and Metrics Server must have matching profiles."
  }
  assert {
    condition     = aws_eks_fargate_profile.banking.subnet_ids == toset(var.subnet_ids) && aws_eks_fargate_profile.banking.pod_execution_role_arn == var.fargate_execution_role_arn
    error_message = "Fargate must use reviewed private subnets and the distinct execution role."
  }
  assert {
    condition     = jsondecode(aws_eks_addon.this["coredns"].configuration_values).computeType == "Fargate" && length(jsondecode(aws_eks_addon.this["coredns"].configuration_values).topologySpreadConstraints) == 0
    error_message = "CoreDNS must explicitly schedule on Fargate without unsupported spreading."
  }
  assert {
    condition     = aws_iam_openid_connect_provider.cluster.client_id_list == toset(["sts.amazonaws.com"])
    error_message = "The cluster IRSA provider must require STS audience."
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
run "execution_role_path_rejected" {
  command = plan
  variables { fargate_execution_role_arn = "arn:aws:iam::123456789012:role/path/test-fargate" }
  expect_failures = [var.fargate_execution_role_arn]
}
run "daemonset_addons_rejected" {
  command = plan
  variables {
    addon_versions = {
      coredns                = "v1.0.0-eksbuild.1"
      metrics-server         = "v1.0.0-eksbuild.1"
      eks-pod-identity-agent = "v1.0.0-eksbuild.1"
    }
  }
  expect_failures = [var.addon_versions]
}
