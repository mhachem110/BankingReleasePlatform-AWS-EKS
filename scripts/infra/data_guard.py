"""Offline, fail-closed contract for the separate initial data-services deployment."""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACCOUNT = "866934333672"
REGION = "us-east-2"
STATE_KEY = "banking-release-platform/dev/data/terraform.tfstate"
ROOT = "infra/environments/dev/data"
MODULE_SHA256 = "709be704536ebfd2e0a3a065ae3db96c7cae15e47df43ad0b0200dc137de045d"
MODULE = "module.data_services."
COMPONENTS = {"rds", "gp3_max_storage", "backups_snapshots", "cpu_credits", "secrets",
              "sqs", "kms", "logs", "metrics_alarms", "monitoring_pods", "data_transfer", "migration_surge"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def configuration(env):
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and
            env.get("GITHUB_REF") == "refs/heads/dev", "Only reviewed Banking/dev may deploy")
    require(all(env.get(k) == "true" for k in ("AWS_OPERATIONS_ENABLED", "DATA_OPERATIONS_ENABLED", "BOOTSTRAP_STATE_READY")),
            "Separate explicit data authorization and completed backend are required")
    require(env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and env.get("AWS_REGION") == REGION and
            env.get("TF_STATE_BUCKET") == "mhachem-banking-tfstate-" + ACCOUNT, "Wrong account/region/backend")
    require(env.get("OPERATION") in {"plan", "apply"}, "No destroy or recovery operation is authorized")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "APPLY-REVIEWED-PHASE6-PLAN", "Require explicit Phase 6 apply phrase and second review")
    from iam_contract import BOOTSTRAP
    require(env.get("ROLE_ARN") == BOOTSTRAP, "Data Terraform must use the single protected bootstrap identity")
    values = json.loads(env["DATA_INPUTS_JSON"], object_pairs_hook=unique)
    fields = {"vpc_id", "database_subnet_ids", "cluster_security_group_id", "kms_key_arn",
              "engine_version", "instance_class", "monitoring_role_arn", "alert_topic_arn", "cost_center"}
    require(isinstance(values, dict) and not set(values) - fields and fields - {"cost_center"} <= set(values),
            "Supply only complete non-secret approved data inputs")
    for key, prefix in (("vpc_id", "vpc"), ("cluster_security_group_id", "sg")):
        require(isinstance(values[key], str) and re.fullmatch(prefix + r"-[a-f0-9]{17}", values[key]), "Invalid actual resource ID")
    subnets = values["database_subnet_ids"]
    require(isinstance(subnets, list) and len(subnets) == len(set(subnets)) == 2 and
            all(isinstance(s, str) and re.fullmatch(r"subnet-[a-f0-9]{17}", s) for s in subnets), "Require two actual database subnets")
    patterns = {
        "kms_key_arn": f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}",
        "engine_version": r"17\.[0-9]+", "instance_class": r"db\.t4g\.(micro|small|medium)",
        "monitoring_role_arn": f"arn:aws:iam::{ACCOUNT}:role/(?:[A-Za-z0-9_+=,.@-]+/)*cloudbatch818-mahmoud-banking-rds-monitoring",
        "alert_topic_arn": f"arn:aws:sns:{REGION}:{ACCOUNT}:banking-dev-[A-Za-z0-9_-]+"}
    for key, pattern in patterns.items():
        require(isinstance(values[key], str) and re.fullmatch(pattern, values[key]), "Invalid approved " + key)
    if values.get("cost_center") is not None:
        require(isinstance(values["cost_center"], str) and values["cost_center"].strip() == values["cost_center"] and
                0 < len(values["cost_center"]) <= 128 and "REPLACE" not in values["cost_center"].upper(), "Actual CostCenter only")
    policy = env.get("DATA_SESSION_POLICY_ARN", "")
    require(re.fullmatch(f"arn:aws:iam::{ACCOUNT}:policy/(?:[A-Za-z0-9_+=,.@-]+/)*BankingReleasePlatformPhase6Session", policy),
            "Require separately administrator-approved managed session cap")
    require(re.fullmatch(r"[a-f0-9]{64}", env.get("DATA_SESSION_POLICY_SHA256", "")), "Require the reviewed session-policy digest")
    return values


def cost_review(review, values, now=None):
    now = now or datetime.now(timezone.utc)
    require(review.get("account") == ACCOUNT and review.get("region") == REGION and
            review.get("instance_class") == values["instance_class"] and review.get("engine_version") == values["engine_version"],
            "Cost review must match actual data inputs")
    observed = datetime.fromisoformat(review["observed_at"].replace("Z", "+00:00"))
    require(observed.tzinfo is not None and timedelta(0) <= now - observed <= timedelta(hours=24), "Current dated cost review required")
    require(isinstance(review.get("reviewed_by"), str) and bool(review["reviewed_by"].strip()) and
            isinstance(review.get("pricing_evidence"), str) and bool(review["pricing_evidence"].strip()), "Actual reviewer and pricing evidence required")
    for field in ("monthly_usd_upper_bound", "migration_usd_upper_bound"):
        number = review.get(field)
        require(not isinstance(number, bool) and isinstance(number, (float, int)) and math.isfinite(number) and number > 0,
                "Explicit positive reviewed cost bounds required")
    require(set(review.get("included_components", [])) == COMPONENTS and review.get("max_storage_gib") == 40 and
            review.get("capacity_and_connections_approved") is True and review.get("alert_delivery_approved") is True and
            review.get("key_policy_reviewed") is True, "Review all charge/capacity/key/notification components")
    return {"provenance": "Administrator/owner-supplied estimates, not measured AWS spend", "review": review, "sha256": digest(review)}


def inventory():
    kinds = {"aws_security_group": ["database"], "aws_vpc_security_group_ingress_rule": ["postgres"],
             "aws_db_subnet_group": ["this"], "aws_db_parameter_group": ["this"], "aws_db_instance": ["this"],
             "aws_sqs_queue": ["payments", "dead"], "aws_sqs_queue_redrive_policy": ["payments"],
             "aws_sqs_queue_redrive_allow_policy": ["dead"], "aws_cloudwatch_log_group": ["application"],
             "aws_cloudwatch_log_metric_filter": ["http_errors"]}
    addresses = {"terraform_data.prerequisites"}
    addresses.update(MODULE + kind + "." + name for kind, names in kinds.items() for name in names)
    addresses.update(MODULE + f'aws_cloudwatch_log_group.database["{name}"]' for name in ("postgresql", "upgrade"))
    addresses.update(MODULE + f'aws_sqs_queue_policy.tls["{name}"]' for name in ("payments", "dead"))
    addresses.update(MODULE + f'aws_cloudwatch_metric_alarm.this["{name}"]' for name in
                     ("database_cpu", "database_storage", "queue_age", "dead_letters", "http_errors"))
    return addresses


def audit(plan, values, *, effective_tags=True):
    source = Path(__file__).resolve().parents[2] / "infra/modules/data-services/main.tf"
    require(hashlib.sha256(source.read_text().replace("\r\n", "\n").encode()).hexdigest() == MODULE_SHA256,
            "Reviewed module source changed; review/update the data contract before planning")
    require(plan.get("applyable") is True and not plan.get("errored") and plan.get("complete") is True, "Require complete applyable plan")
    resources = [r for r in plan.get("resource_changes", []) if r.get("mode") == "managed"]
    managed = {r["address"]: r for r in resources}
    require(len(managed) == len(resources) and set(managed) == inventory(), "Exact 21-entry data inventory mismatch")
    require(all(r["change"]["actions"] == ["create"] for r in resources),
            "Initial data workflow permits only creation: existing/no-op/update/delete/replacement requires separate recovery review")
    common = {"Project": "BankingReleasePlatform", "Environment": "dev", "ManagedBy": "Terraform",
              "Owner": "MahmoudHachem", "Purpose": "CloudEngineerTraining"}
    if values.get("cost_center") is not None:
        common["CostCenter"] = values["cost_center"]
    untaggable = {"terraform_data", "aws_sqs_queue_redrive_policy", "aws_sqs_queue_redrive_allow_policy",
                  "aws_sqs_queue_policy", "aws_cloudwatch_log_metric_filter"}
    for address, item in managed.items():
        require(item["type"] == address.removeprefix(MODULE).split(".")[0], "Address/type mismatch")
        if item["type"] not in untaggable:
            component = ("database" if item["type"] in {"aws_security_group", "aws_vpc_security_group_ingress_rule",
                        "aws_db_subnet_group", "aws_db_parameter_group", "aws_db_instance"} else
                        "messaging" if item["type"] == "aws_sqs_queue" else "monitoring" if item["type"] == "aws_cloudwatch_metric_alarm" else "logging")
            for field in (["tags", "tags_all"] if effective_tags else ["tags"]):
                tags = item["change"]["after"].get(field) or {}
                require(all(tags.get(k) == v for k, v in dict(common, Component=component).items()) and
                        tags.get("Name", "").startswith("banking-dev") and
                        (values.get("cost_center") is not None or "CostCenter" not in tags), "Resolved approved tags required: " + address)

    def after(resource):
        return managed[MODULE + resource]["change"]["after"]
    database = after("aws_db_instance.this")
    expected = {"identifier": "banking-dev-postgres", "engine": "postgres", "engine_version": values["engine_version"],
        "instance_class": values["instance_class"], "allocated_storage": 20, "max_allocated_storage": 40, "storage_type": "gp3",
        "storage_encrypted": True, "kms_key_id": values["kms_key_arn"], "master_user_secret_kms_key_id": values["kms_key_arn"],
        "manage_master_user_password": True, "username": "banking_migrator", "db_name": "banking", "publicly_accessible": False,
        "multi_az": False, "iam_database_authentication_enabled": True, "deletion_protection": True, "backup_retention_period": 7,
        "skip_final_snapshot": False, "final_snapshot_identifier": "banking-dev-postgres-final-reviewed", "copy_tags_to_snapshot": True,
        "monitoring_interval": 60, "monitoring_role_arn": values["monitoring_role_arn"], "auto_minor_version_upgrade": True,
        "apply_immediately": False, "backup_window": "03:00-04:00", "maintenance_window": "sun:04:00-sun:05:00"}
    require(all(database.get(k) == v for k, v in expected.items()) and not database.get("password") and
            set(database.get("enabled_cloudwatch_logs_exports", [])) == {"postgresql", "upgrade"}, "Database privacy/encryption/recovery/cost mismatch")
    group = after("aws_security_group.database")
    require(group["vpc_id"] == values["vpc_id"] and group["name"] == "banking-dev-database" and
            group["ingress"] == group["egress"] == [], "Database SG scope mismatch")
    ingress = after("aws_vpc_security_group_ingress_rule.postgres")
    require(ingress["referenced_security_group_id"] == values["cluster_security_group_id"] and
            ingress["ip_protocol"] == "tcp" and ingress["from_port"] == ingress["to_port"] == 5432 and
            not ingress.get("cidr_ipv4") and not ingress.get("cidr_ipv6"), "Only approved cluster SG TCP5432 may reach database")
    subnet = after("aws_db_subnet_group.this")
    require(subnet["name"] == "banking-dev-database" and set(subnet["subnet_ids"]) == set(values["database_subnet_ids"]), "Database subnets mismatch")
    parameter = after("aws_db_parameter_group.this")
    require(parameter["name"] == "banking-dev-postgres17" and parameter["family"] == "postgres17" and
            {p["name"]: p["value"] for p in parameter["parameter"]} == {"rds.force_ssl":"1", "log_connections":"1", "log_disconnections":"1"}, "PostgreSQL TLS/log parameters mismatch")
    for kind, name, retention in (("payments", "banking-dev-payments", 86400), ("dead", "banking-dev-payments-dlq", 1209600)):
        queue = after("aws_sqs_queue." + kind)
        require(queue["name"] == name and queue["kms_master_key_id"] == values["kms_key_arn"] and
                queue["message_retention_seconds"] == retention and not queue.get("fifo_queue"), "SQS identity/encryption/retention mismatch")
    queue = after("aws_sqs_queue.payments")
    require(queue["visibility_timeout_seconds"] == 30 and queue["receive_wait_time_seconds"] == 2 and queue["max_message_size"] == 4096, "Queue retry/size mismatch")
    source_arn = f"arn:aws:sqs:{REGION}:{ACCOUNT}:banking-dev-payments"
    dead_arn = source_arn + "-dlq"
    def policy_contract(resource, field, expected):
        change = managed[MODULE + resource]["change"]
        value = change["after"].get(field)
        if value is None:
            # New queue ARNs are computed. Their policy expressions/constants are
            # bound to the reviewed module fingerprint, then checked against AWS after apply.
            require(change.get("after_unknown", {}).get(field) is True, "Unexplained missing policy")
        else:
            require(json.loads(value) == expected, "Queue policy/redrive mismatch")
    policy_contract("aws_sqs_queue_redrive_policy.payments", "redrive_policy",
                    {"deadLetterTargetArn":dead_arn, "maxReceiveCount":5})
    policy_contract("aws_sqs_queue_redrive_allow_policy.dead", "redrive_allow_policy",
                    {"redrivePermission":"byQueue", "sourceQueueArns":[source_arn]})
    for name, arn in (("payments", source_arn), ("dead", dead_arn)):
        policy_contract(f'aws_sqs_queue_policy.tls["{name}"]', "policy", {"Version":"2012-10-17", "Statement":[{
            "Sid":"DenyUnencryptedTransport", "Effect":"Deny", "Principal":"*", "Action":"sqs:*", "Resource":arn,
            "Condition":{"Bool":{"aws:SecureTransport":"false"}}}]})
    for resource, name in (("application", "/banking/banking-dev/application"),
                           ('database["postgresql"]', "/aws/rds/instance/banking-dev-postgres/postgresql"),
                           ('database["upgrade"]', "/aws/rds/instance/banking-dev-postgres/upgrade")):
        log = after("aws_cloudwatch_log_group." + resource)
        require(log["name"] == name and log["retention_in_days"] == 30 and log["kms_key_id"] == values["kms_key_arn"], "Log retention/key mismatch")
    alarms = {"database_cpu": ("AWS/RDS", "CPUUtilization", 80, "GreaterThanThreshold", "Average", 300),
              "database_storage": ("AWS/RDS", "FreeStorageSpace", 5368709120, "LessThanThreshold", "Minimum", 300),
              "queue_age": ("AWS/SQS", "ApproximateAgeOfOldestMessage", 120, "GreaterThanThreshold", "Maximum", 60),
              "dead_letters": ("AWS/SQS", "ApproximateNumberOfMessagesVisible", 0, "GreaterThanThreshold", "Maximum", 60),
              "http_errors": ("BankingReleasePlatform/dev", "Http5xx", 5, "GreaterThanOrEqualToThreshold", "Sum", 60)}
    for name, configuration in alarms.items():
        alarm = after(f'aws_cloudwatch_metric_alarm.this["{name}"]')
        require(tuple(alarm.get(k) for k in ("namespace", "metric_name", "threshold", "comparison_operator", "statistic", "period")) == configuration and
                alarm["alarm_name"] == "banking-dev-" + name and alarm["evaluation_periods"] == 2 and
                alarm["actions_enabled"] and alarm["alarm_actions"] == alarm["ok_actions"] == [values["alert_topic_arn"]], "Owned alarm configuration mismatch")
    return {"managed_creates": len(managed), "managed_updates": 0, "managed_deletes": 0, "module_sha256":MODULE_SHA256,
            "resources": sorted(managed), "effective_tags_verified": effective_tags}


def backend(env):
    return {"bucket": env["TF_STATE_BUCKET"], "region": REGION, "key": STATE_KEY, "encrypt": True,
            "use_lockfile": True, "allowed_account_ids": [ACCOUNT], "workspace_key_prefix":"banking-release-platform/_workspaces"}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inputs", "plan"))
    args = parser.parse_args()
    values = configuration(os.environ)
    review = cost_review(json.loads(os.environ["DATA_COST_REVIEW_JSON"], object_pairs_hook=unique), values)
    if args.command == "inputs":
        Path("data.tfvars.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
        Path("data.tfbackend.json").write_text(json.dumps(backend(os.environ), indent=2), encoding="utf-8")
        Path("data-cost-review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    else:
        report = audit(json.loads(Path("data-plan.json").read_text()), values)
        report.update(plan_sha256=hashlib.sha256(Path("data.tfplan").read_bytes()).hexdigest(),
                      cost_review_sha256=review["sha256"], source_commit=os.environ["GITHUB_SHA"], inputs_sha256=digest(values),
                      session_policy_arn=os.environ["DATA_SESSION_POLICY_ARN"],
                      session_policy_sha256=os.environ["DATA_SESSION_POLICY_SHA256"])
        Path("data-plan-review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
