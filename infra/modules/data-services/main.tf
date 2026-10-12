terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "database_subnet_ids" { type = list(string) }
variable "cluster_security_group_id" { type = string }
variable "kms_key_arn" { type = string }
variable "engine_version" { type = string }
variable "instance_class" { type = string }
variable "monitoring_role_arn" { type = string }
variable "alert_topic_arn" { type = string }
variable "tags" { type = map(string) }

resource "aws_security_group" "database" {
  name        = "${var.name}-database"
  description = "Private PostgreSQL from the approved Banking Fargate cluster only"
  vpc_id      = var.vpc_id
  ingress     = []
  egress      = []
  tags        = merge(var.tags, { Name = "${var.name}-database", Component = "database" })
}
resource "aws_vpc_security_group_ingress_rule" "postgres" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = var.cluster_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Approved Banking Fargate Pod ENIs"
  tags                         = merge(var.tags, { Name = "${var.name}-postgres-ingress", Component = "database" })
}
resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-database"
  subnet_ids = var.database_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name}-database-subnets", Component = "database" })
}
resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-postgres17"
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_connections"
    value = "1"
  }
  parameter {
    name  = "log_disconnections"
    value = "1"
  }
  tags = merge(var.tags, { Name = "${var.name}-postgres17", Component = "database" })
}
resource "aws_cloudwatch_log_group" "database" {
  # checkov:skip=CKV_AWS_338:Training logs retain 30 days; longer retention requires separate cost approval.
  for_each          = toset(["postgresql", "upgrade"])
  name              = "/aws/rds/instance/${var.name}-postgres/${each.key}"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
  tags              = merge(var.tags, { Name = "${var.name}-database-${each.key}", Component = "logging" })
}
resource "aws_db_instance" "this" {
  # checkov:skip=CKV_AWS_157:Single-AZ development baseline; no database HA claim. Multi-AZ needs separate cost approval.
  # checkov:skip=CKV_AWS_353:Performance Insights/Database Insights is not enabled without separate service/cost approval.
  identifier                          = "${var.name}-postgres"
  engine                              = "postgres"
  engine_version                      = var.engine_version
  instance_class                      = var.instance_class
  allocated_storage                   = 20
  max_allocated_storage               = 40
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  db_name                             = "banking"
  username                            = "banking_migrator"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.kms_key_arn
  db_subnet_group_name                = aws_db_subnet_group.this.name
  parameter_group_name                = aws_db_parameter_group.this.name
  vpc_security_group_ids              = [aws_security_group.database.id]
  publicly_accessible                 = false
  multi_az                            = false
  iam_database_authentication_enabled = true
  deletion_protection                 = true
  backup_retention_period             = 7
  backup_window                       = "03:00-04:00"
  maintenance_window                  = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade          = true
  monitoring_interval                 = 60
  monitoring_role_arn                 = var.monitoring_role_arn
  apply_immediately                   = false
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.name}-postgres-final-reviewed"
  copy_tags_to_snapshot               = true
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]
  tags                                = merge(var.tags, { Name = "${var.name}-postgres", Component = "database" })
  depends_on                          = [aws_cloudwatch_log_group.database]
}
resource "aws_sqs_queue" "dead" {
  name                      = "${var.name}-payments-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = var.kms_key_arn
  tags                      = merge(var.tags, { Name = "${var.name}-payments-dlq", Component = "messaging" })
}
resource "aws_sqs_queue" "payments" {
  name                       = "${var.name}-payments"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 2
  max_message_size           = 4096
  kms_master_key_id          = var.kms_key_arn
  tags                       = merge(var.tags, { Name = "${var.name}-payments", Component = "messaging" })
}
resource "aws_sqs_queue_redrive_policy" "payments" {
  queue_url = aws_sqs_queue.payments.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead.arn
    maxReceiveCount     = 5
  })
}
resource "aws_sqs_queue_redrive_allow_policy" "dead" {
  queue_url = aws_sqs_queue.dead.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.payments.arn]
  })
}
resource "aws_sqs_queue_policy" "tls" {
  for_each  = { payments = aws_sqs_queue.payments, dead = aws_sqs_queue.dead }
  queue_url = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "DenyUnencryptedTransport", Effect = "Deny", Principal = "*", Action = "sqs:*",
      Resource = each.value.arn, Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_cloudwatch_log_group" "application" {
  # checkov:skip=CKV_AWS_338:Training application logs retain 30 days; do not silently expand paid retention.
  name              = "/banking/${var.name}/application"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
  tags              = merge(var.tags, { Name = "${var.name}-application-logs", Component = "logging" })
}
resource "aws_cloudwatch_log_metric_filter" "http_errors" {
  name           = "${var.name}-http-5xx"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "{ $.State.Status >= 500 }"
  metric_transformation {
    name          = "Http5xx"
    namespace     = "BankingReleasePlatform/${var.tags.Environment}"
    value         = "1"
    default_value = 0
    unit          = "Count"
  }
}
locals {
  alarms = {
    database_cpu     = { namespace = "AWS/RDS", metric = "CPUUtilization", threshold = 80, comparison = "GreaterThanThreshold", statistic = "Average", period = 300, dimensions = { DBInstanceIdentifier = aws_db_instance.this.identifier }, severity = "warning" }
    database_storage = { namespace = "AWS/RDS", metric = "FreeStorageSpace", threshold = 5368709120, comparison = "LessThanThreshold", statistic = "Minimum", period = 300, dimensions = { DBInstanceIdentifier = aws_db_instance.this.identifier }, severity = "critical" }
    queue_age        = { namespace = "AWS/SQS", metric = "ApproximateAgeOfOldestMessage", threshold = 120, comparison = "GreaterThanThreshold", statistic = "Maximum", period = 60, dimensions = { QueueName = aws_sqs_queue.payments.name }, severity = "warning" }
    dead_letters     = { namespace = "AWS/SQS", metric = "ApproximateNumberOfMessagesVisible", threshold = 0, comparison = "GreaterThanThreshold", statistic = "Maximum", period = 60, dimensions = { QueueName = aws_sqs_queue.dead.name }, severity = "critical" }
    http_errors      = { namespace = "BankingReleasePlatform/${var.tags.Environment}", metric = "Http5xx", threshold = 5, comparison = "GreaterThanOrEqualToThreshold", statistic = "Sum", period = 60, dimensions = {}, severity = "critical" }
  }
}
resource "aws_cloudwatch_metric_alarm" "this" {
  for_each            = local.alarms
  alarm_name          = "${var.name}-${each.key}"
  alarm_description   = "${each.value.severity}; owner=${var.tags.Owner}; runbook=docs/deployment/INCIDENTS.md"
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  statistic           = each.value.statistic
  period              = each.value.period
  evaluation_periods  = 2
  treat_missing_data  = "notBreaching"
  dimensions          = each.value.dimensions
  alarm_actions       = [var.alert_topic_arn]
  actions_enabled     = true
  ok_actions          = [var.alert_topic_arn]
  tags                = merge(var.tags, { Name = "${var.name}-${each.key}", Component = "monitoring", Severity = each.value.severity })
}
output "database_endpoint" { value = aws_db_instance.this.address }
output "master_secret_arn" { value = aws_db_instance.this.master_user_secret[0].secret_arn }
output "payment_queue_url" { value = aws_sqs_queue.payments.id }
output "dead_letter_queue_url" { value = aws_sqs_queue.dead.id }
output "queue_arns" { value = [aws_sqs_queue.payments.arn, aws_sqs_queue.dead.arn] }
output "application_log_group" { value = aws_cloudwatch_log_group.application.name }

output "database_identifier" { value = aws_db_instance.this.identifier }
output "payment_queue_name" { value = aws_sqs_queue.payments.name }
