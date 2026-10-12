terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    key                  = "banking-release-platform/dev/data/terraform.tfstate"
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}
provider "aws" {
  region              = "us-east-2"
  allowed_account_ids = ["866934333672"]
  default_tags { tags = local.tags }
}
variable "vpc_id" { type = string }
variable "database_subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.database_subnet_ids) == 2 && length(distinct(var.database_subnet_ids)) == 2
    error_message = "Supply both isolated database subnets from verified Banking platform outputs."
  }
}
variable "cluster_security_group_id" { type = string }
variable "kms_key_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:kms:us-east-2:866934333672:key/[a-f0-9-]{36}$", var.kms_key_arn))
    error_message = "Supply the actual administrator-approved Ohio data-services key."
  }
}
variable "engine_version" {
  type = string
  validation {
    condition     = can(regex("^17\\.[0-9]+$", var.engine_version))
    error_message = "Supply an exact approved/supported PostgreSQL 17 patch from the Ohio RDS catalog."
  }
}
variable "instance_class" {
  type = string
  validation {
    condition     = can(regex("^db\\.t4g\\.(micro|small|medium)$", var.instance_class))
    error_message = "Supply a reviewed supported development class; review cost and capacity before planning."
  }
}
variable "alert_topic_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:sns:us-east-2:866934333672:banking-dev-[A-Za-z0-9_-]+$", var.alert_topic_arn))
    error_message = "Supply an existing authorized alert destination, subscribers and delivery approval."
  }
}
variable "monitoring_role_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:iam::866934333672:role/([A-Za-z0-9_+=,.@-]+/)*cloudbatch818-mahmoud-banking-rds-monitoring$", var.monitoring_role_arn))
    error_message = "Provide the actual approved RDS Enhanced Monitoring service role; never a bootstrap/deployer role."
  }
}
variable "cost_center" {
  type     = string
  default  = null
  nullable = true
}
locals {
  tags = merge({ Project = "BankingReleasePlatform", Environment = "dev", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", ManagedBy = "Terraform" },
  var.cost_center == null ? {} : { CostCenter = var.cost_center })
}
data "aws_caller_identity" "current" {}
data "aws_vpc" "platform" { id = var.vpc_id }
data "aws_subnet" "database" {
  for_each = toset(var.database_subnet_ids)
  id       = each.value
}
data "aws_route_table" "database" {
  for_each  = toset(var.database_subnet_ids)
  subnet_id = each.value
}
data "aws_security_group" "cluster" { id = var.cluster_security_group_id }
data "aws_eks_cluster" "platform" { name = "banking-dev" }
resource "terraform_data" "prerequisites" {
  lifecycle {
    precondition {
      condition = (data.aws_caller_identity.current.account_id == "866934333672" &&
        lookup(data.aws_vpc.platform.tags, "Project", "") == "BankingReleasePlatform" &&
        lookup(data.aws_vpc.platform.tags, "Environment", "") == "dev" &&
        alltrue([for subnet in data.aws_subnet.database : subnet.vpc_id == var.vpc_id && !subnet.map_public_ip_on_launch &&
        startswith(lookup(subnet.tags, "Name", ""), "banking-dev-database-")]) &&
        alltrue([for table in data.aws_route_table.database : table.vpc_id == var.vpc_id && length(table.routes) > 0 &&
        alltrue([for route in table.routes : route.gateway_id == "local" && route.cidr_block == data.aws_vpc.platform.cidr_block])]) &&
        data.aws_eks_cluster.platform.status == "ACTIVE" &&
        data.aws_eks_cluster.platform.vpc_config[0].vpc_id == var.vpc_id &&
        data.aws_eks_cluster.platform.vpc_config[0].cluster_security_group_id == var.cluster_security_group_id &&
        data.aws_security_group.cluster.vpc_id == var.vpc_id &&
      startswith(data.aws_security_group.cluster.name, "eks-cluster-sg-banking-dev-"))
      error_message = "Require the exact Banking/dev VPC, isolated database subnets/routes and Banking EKS cluster SG; never adopt unrelated resources."
    }
  }
}
module "data_services" {
  source                    = "../../../modules/data-services"
  name                      = "banking-dev"
  vpc_id                    = var.vpc_id
  database_subnet_ids       = var.database_subnet_ids
  cluster_security_group_id = var.cluster_security_group_id
  kms_key_arn               = var.kms_key_arn
  engine_version            = var.engine_version
  instance_class            = var.instance_class
  monitoring_role_arn       = var.monitoring_role_arn
  alert_topic_arn           = var.alert_topic_arn
  tags                      = local.tags
  depends_on                = [terraform_data.prerequisites]
}
output "interface" { value = module.data_services }
