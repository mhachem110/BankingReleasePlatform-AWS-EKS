# Shared project runtime prerequisites. The EKS issuer and key come from verified
# platform/foundation outputs; no role, email address or secret is guessed here.
terraform {
  required_version = ">= 1.15.0, < 2.0.0"
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
  backend "s3" {
    encrypt              = true
    use_lockfile         = true
    workspace_key_prefix = "banking-release-platform/_workspaces"
  }
}
provider "aws" {
  region              = "us-east-2"
  allowed_account_ids = ["866934333672"]
  default_tags { tags = local.tags }
}
variable "kms_key_arn" { type = string }
variable "oidc_issuer_url" { type = string }
variable "oidc_provider_arn" { type = string }
variable "data_session_policies" {
  description = "Canonical dev/prod data policies generated from the verified platform interface"
  type        = map(string)
}
variable "payment_permissions" {
  description = "Exact payment-only dev/prod SQS and KMS policies from the verified runtime key"
  type        = map(string)
}
locals {
  account = "866934333672"
  region  = "us-east-2"
  issuer  = trimprefix(var.oidc_issuer_url, "https://")
  tags    = { Project = "BankingReleasePlatform", Environment = "shared", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining", Component = "runtime-prerequisites" }
  environments = {
    dev  = { role = "cloudbatch818-mahmoud-banking-rds-monitoring", policy = "BankingReleasePlatformPhase6Session" }
    prod = { role = "cloudbatch818-mahmoud-banking-rds-monitoring-prod", policy = "BankingReleasePlatformPhase6ProdSession" }
  }
}
data "aws_caller_identity" "current" {}
resource "terraform_data" "authorization" {
  lifecycle {
    precondition {
      condition = (
        data.aws_caller_identity.current.account_id == local.account &&
        can(regex("^arn:aws:kms:us-east-2:866934333672:key/[a-f0-9-]{36}$", var.kms_key_arn)) &&
        can(regex("^https://oidc.eks.us-east-2.amazonaws.com/id/[A-Fa-f0-9]{32}$", var.oidc_issuer_url)) &&
        var.oidc_provider_arn == "arn:aws:iam::${local.account}:oidc-provider/${local.issuer}" &&
        toset(keys(var.data_session_policies)) == toset(keys(local.environments)) &&
        toset(keys(var.payment_permissions)) == toset(keys(local.environments))
      )
      error_message = "Use the exact verified Banking EKS issuer, project key and two generated session caps."
    }
  }
}
# RDS Enhanced Monitoring writes to its AWS-owned metrics group. Trust is
# restricted to the one named database in this account for each environment.
resource "aws_iam_role" "monitoring" {
  for_each = local.environments
  name     = each.value.role
  path     = "/"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "monitoring.rds.amazonaws.com" }, Action = "sts:AssumeRole",
    Condition = { StringEquals = { "aws:SourceAccount" = local.account },
                  ArnEquals = { "aws:SourceArn" = "arn:aws:rds:${local.region}:${local.account}:db:banking-${each.key}-postgres" } }
  }] })
  tags       = merge(local.tags, { Environment = each.key, Name = each.value.role })
  depends_on = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy_attachment" "monitoring" {
  for_each   = local.environments
  role       = aws_iam_role.monitoring[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
# A payment Pod gets only its own queue and KMS-through-SQS permissions. The
# OIDC trust binds the live EKS issuer to one namespace/service account.
resource "aws_iam_role" "payment" {
  for_each = local.environments
  name     = "cloudbatch818-mahmoud-banking-payment-runtime-${each.key}"
  path     = "/"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Federated = var.oidc_provider_arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = {
      "${local.issuer}:aud" = "sts.amazonaws.com",
      "${local.issuer}:sub" = "system:serviceaccount:banking-${each.key}:banking-payment"
    } }
  }] })
  tags       = merge(local.tags, { Environment = each.key, Name = "banking-${each.key}-payment-runtime" })
  depends_on = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy" "payment" {
  for_each = local.environments
  name     = "BankingPaymentRuntime"
  role     = aws_iam_role.payment[each.key].id
  policy   = var.payment_permissions[each.key]
}
# Alert delivery needs its own key policy: SNS sends into an encrypted SQS
# queue and CloudWatch publishes into an encrypted topic. The application key
# intentionally has different encryption contexts and remains untouched.
resource "aws_kms_key" "alerts" {
  description             = "Banking dev/prod alarm topic and delivery queues"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "AccountIAM", Effect = "Allow", Principal = { AWS = "arn:aws:iam::${local.account}:root" }, Action = "kms:*", Resource = "*" },
    { Sid = "BankingAlarmPublishers", Effect = "Allow", Principal = { Service = ["cloudwatch.amazonaws.com", "sns.amazonaws.com"] },
      Action = ["kms:Decrypt", "kms:GenerateDataKey*"], Resource = "*",
      Condition = { StringEquals = {
        "kms:EncryptionContext:aws:sns:topicArn" = [for env in keys(local.environments) : "arn:aws:sns:${local.region}:${local.account}:banking-${env}-alerts"]
      } } },
    { Sid = "BankingAlertQueues", Effect = "Allow", Principal = { Service = "sns.amazonaws.com" },
      Action = ["kms:Decrypt", "kms:GenerateDataKey*"], Resource = "*",
      Condition = { StringEquals = {
        "kms:EncryptionContext:aws:sqs:arn" = [for env in keys(local.environments) : "arn:aws:sqs:${local.region}:${local.account}:banking-${env}-alerts"]
      } } }
  ] })
  tags       = merge(local.tags, { Name = "banking-alert-delivery" })
  depends_on = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
resource "aws_kms_alias" "alerts" {
  name          = "alias/banking-release-platform-alerts"
  target_key_id = aws_kms_key.alerts.key_id
}
# A project-owned alert queue gives every CloudWatch alarm a durable destination.
# Same-account SNS/SQS subscription is automatic after the account authorizes
# Subscribe. No email address, webhook credential or external destination is stored.
resource "aws_sqs_queue" "alerts" {
  for_each                  = local.environments
  name                      = "banking-${each.key}-alerts"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.alerts.arn
  tags                      = merge(local.tags, { Environment = each.key, Name = "banking-${each.key}-alerts" })
  depends_on                = [terraform_data.authorization]
}
resource "aws_sns_topic" "alerts" {
  for_each          = local.environments
  name              = "banking-${each.key}-alerts"
  kms_master_key_id = aws_kms_key.alerts.arn
  tags              = merge(local.tags, { Environment = each.key, Name = "banking-${each.key}-alerts" })
  depends_on        = [terraform_data.authorization]
}
resource "aws_sqs_queue_policy" "alerts" {
  for_each  = local.environments
  queue_url = aws_sqs_queue.alerts[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "OnlyOwnedAlertTopic", Effect = "Allow", Principal = { Service = "sns.amazonaws.com" },
      Action = "sqs:SendMessage", Resource = aws_sqs_queue.alerts[each.key].arn,
      Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.alerts[each.key].arn },
                    StringEquals = { "aws:SourceAccount" = local.account } } },
    { Sid = "DenyPlaintext", Effect = "Deny", Principal = "*", Action = "sqs:*",
      Resource = aws_sqs_queue.alerts[each.key].arn,
      Condition = { Bool = { "aws:SecureTransport" = "false" } } }
  ] })
}
resource "aws_sns_topic_subscription" "alerts" {
  for_each   = local.environments
  topic_arn  = aws_sns_topic.alerts[each.key].arn
  protocol   = "sqs"
  endpoint   = aws_sqs_queue.alerts[each.key].arn
  depends_on = [aws_sqs_queue_policy.alerts]
}
# Data plans are capped independently for dev and prod. These policy documents
# are passed as reviewed source, and are never attached to the bootstrap role.
resource "aws_iam_policy" "data_session" {
  for_each    = local.environments
  name        = each.value.policy
  path        = "/"
  description = "Banking ${each.key} data Terraform session restriction"
  policy      = var.data_session_policies[each.key]
  tags        = merge(local.tags, { Environment = each.key, Name = each.value.policy })
  depends_on  = [terraform_data.authorization]
  lifecycle { prevent_destroy = true }
}
output "interface" {
  value = { for env, value in local.environments : env => {
    monitoring_role_arn    = aws_iam_role.monitoring[env].arn
    payment_role_arn       = aws_iam_role.payment[env].arn
    alert_topic_arn        = aws_sns_topic.alerts[env].arn
    alert_queue_url        = aws_sqs_queue.alerts[env].id
    data_policy_arn        = aws_iam_policy.data_session[env].arn
    data_policy_sha256     = sha256(var.data_session_policies[env])
    subscription_arn      = aws_sns_topic_subscription.alerts[env].arn
  } } }
output "alert_key_arn" { value = aws_kms_key.alerts.arn }
output "state_key" { value = "banking-release-platform/shared/runtime-prerequisites/terraform.tfstate" }
output "contract_version" { value = 1 }
