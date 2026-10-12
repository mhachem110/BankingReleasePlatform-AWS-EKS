# Synthetic mock fixtures only. These values are not deployment inputs.
mock_provider "aws" {
  mock_resource "aws_db_instance" {
    defaults = {
      address = "synthetic-postgres.test"
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:us-east-2:866934333672:secret:synthetic-mock"
        secret_status = "active"
        kms_key_id    = "arn:aws:kms:us-east-2:866934333672:key/11111111-2222-3333-4444-555555555555"
      }]
    }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:us-east-2:866934333672:synthetic-mock-queue" }
  }
}
variables {
  name                      = "banking-dev"
  vpc_id                    = "vpc-0123456789abcdef0"
  database_subnet_ids       = ["subnet-0123456789abcdef0", "subnet-1123456789abcdef0"]
  cluster_security_group_id = "sg-0123456789abcdef0"
  kms_key_arn               = "arn:aws:kms:us-east-2:866934333672:key/11111111-2222-3333-4444-555555555555"
  engine_version            = "17.6"
  instance_class            = "db.t4g.micro"
  monitoring_role_arn       = "arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-banking-rds-monitoring"
  alert_topic_arn           = "arn:aws:sns:us-east-2:866934333672:banking-dev-synthetic-alerts"
  tags                      = { Project = "BankingReleasePlatform", Environment = "dev", ManagedBy = "Terraform", Owner = "MahmoudHachem", Purpose = "CloudEngineerTraining" }
}
run "database_private_tls_secrets_and_recovery" {
  command = apply
  assert {
    condition = (!aws_db_instance.this.publicly_accessible && aws_db_instance.this.storage_encrypted &&
      aws_db_instance.this.deletion_protection && !aws_db_instance.this.skip_final_snapshot &&
      aws_db_instance.this.manage_master_user_password && aws_db_instance.this.backup_retention_period == 7 &&
      aws_db_instance.this.monitoring_interval == 60 && aws_db_instance.this.auto_minor_version_upgrade &&
    aws_db_instance.this.max_allocated_storage == 40 && aws_vpc_security_group_ingress_rule.postgres.from_port == 5432)
    error_message = "Private database, managed secret, encryption and recovery protections are required."
  }
  assert {
    condition     = length(aws_security_group.database.egress) == 0 && length(aws_db_subnet_group.this.subnet_ids) == 2
    error_message = "Use both isolated subnets, with no database-initiated broad egress."
  }
  assert {
    condition     = contains([for p in aws_db_parameter_group.this.parameter : "${p.name}=${p.value}"], "rds.force_ssl=1")
    error_message = "RDS must force PostgreSQL TLS."
  }
}
run "messaging_and_alarm_controls" {
  command = apply
  assert {
    condition = (aws_sqs_queue.payments.kms_master_key_id == var.kms_key_arn && aws_sqs_queue.dead.kms_master_key_id == var.kms_key_arn &&
      aws_sqs_queue.dead.message_retention_seconds > aws_sqs_queue.payments.message_retention_seconds &&
      aws_sqs_queue.payments.visibility_timeout_seconds == 30 &&
      jsondecode(aws_sqs_queue_redrive_policy.payments.redrive_policy).maxReceiveCount == 5 &&
    jsondecode(aws_sqs_queue_redrive_allow_policy.dead.redrive_allow_policy).redrivePermission == "byQueue")
    error_message = "Encrypted queues, retry/retention and exact source redrive controls are required."
  }
  assert {
    condition = (length(aws_cloudwatch_metric_alarm.this) == 5 &&
      alltrue([for alarm in aws_cloudwatch_metric_alarm.this : toset(alarm.alarm_actions) == toset([var.alert_topic_arn])]) &&
    aws_cloudwatch_log_group.application.retention_in_days == 30 && aws_cloudwatch_log_group.application.kms_key_id == var.kms_key_arn)
    error_message = "All five owned alarms need an approved destination; logs must be encrypted/retained."
  }
}
