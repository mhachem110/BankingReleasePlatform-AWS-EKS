mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "866934333672" } }
  mock_data "aws_vpc" { defaults = { cidr_block = "10.70.0.0/16", tags = { Project = "BankingReleasePlatform", Environment = "dev" } } }
  mock_data "aws_subnet" { defaults = { vpc_id = "vpc-0123456789abcdef0", map_public_ip_on_launch = false, tags = { Name = "banking-dev-database-synthetic" } } }
  mock_data "aws_route_table" { defaults = { vpc_id = "vpc-0123456789abcdef0", routes = [{ cidr_block = "10.70.0.0/16", gateway_id = "local" }] } }
  mock_data "aws_security_group" { defaults = { vpc_id = "vpc-0123456789abcdef0", name = "eks-cluster-sg-banking-dev-synthetic" } }
  mock_data "aws_eks_cluster" { defaults = { status = "ACTIVE", vpc_config = [{ vpc_id = "vpc-0123456789abcdef0", cluster_security_group_id = "sg-0123456789abcdef0" }] } }
  mock_resource "aws_db_instance" {
    defaults = { master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-2:866934333672:secret:synthetic", secret_status = "active", kms_key_id = "arn:aws:kms:us-east-2:866934333672:key/11111111-2222-3333-4444-555555555555" }] }
  }
}
variables {
  vpc_id                    = "vpc-0123456789abcdef0"
  database_subnet_ids       = ["subnet-0123456789abcdef0", "subnet-1123456789abcdef0"]
  cluster_security_group_id = "sg-0123456789abcdef0"
  kms_key_arn               = "arn:aws:kms:us-east-2:866934333672:key/11111111-2222-3333-4444-555555555555"
  engine_version            = "17.6"
  instance_class            = "db.t4g.micro"
  monitoring_role_arn       = "arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-banking-rds-monitoring-prod"
  alert_topic_arn           = "arn:aws:sns:us-east-2:866934333672:banking-prod-synthetic-alerts"
}
run "valid_data_scope" {
  command = plan
  assert {
    condition     = module.data_services.database_identifier == "banking-prod-postgres" && module.data_services.payment_queue_name == "banking-prod-payments"
    error_message = "Production must never share development database/queues."
  }
}
run "unrelated_cluster_security_group_rejected" {
  command = plan
  override_data {
    target = data.aws_eks_cluster.platform
    values = { status = "ACTIVE", vpc_config = [{ vpc_id = "vpc-0123456789abcdef0", cluster_security_group_id = "sg-unrelated" }] }
  }
  expect_failures = [terraform_data.prerequisites]
}
run "wrong_environment_vpc_rejected" {
  command = plan
  override_data {
    target = data.aws_vpc.platform
    values = { tags = { Project = "OtherProject", Environment = "dev" } }
  }
  expect_failures = [terraform_data.prerequisites]
}
run "wrong_key_region_rejected" {
  command = plan
  variables { kms_key_arn = "arn:aws:kms:us-east-1:866934333672:key/11111111-2222-3333-4444-555555555555" }
  expect_failures = [var.kms_key_arn]
}
run "database_default_egress_route_rejected" {
  command = plan
  override_data {
    target = data.aws_route_table.database["subnet-0123456789abcdef0"]
    values = {
      vpc_id = "vpc-0123456789abcdef0"
      routes = [{ cidr_block = "0.0.0.0/0", gateway_id = "igw-synthetic" }]
    }
  }
  expect_failures = [terraform_data.prerequisites]
}
