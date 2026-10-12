"""Two-namespace planning sensitivity. Unknown usage is excluded, never made zero."""
from decimal import Decimal
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def estimate(instance_class="db.t4g.micro", *, database_storage_gib=40):
    prices = json.loads((ROOT/"docs/infrastructure/shared-demo-prices.json").read_text())["rates"]
    suffix = instance_class.removeprefix("db.t4g.")
    if suffix not in {"micro", "small", "medium"} or instance_class != "db.t4g." + suffix or database_storage_gib not in {20, 40}:
        raise ValueError("Only reviewed design classes/storage envelopes are modeled")
    rates = {k: Decimal(v["usd_per_unit"]) for k,v in prices.items()}
    rows = {
        "one_eks_standard_control_plane": Decimal("73"),
        "one_nat_gateway_and_ipv4_planning_rates": Decimal("36.50"),
        "one_platform_kms_key": rates["kms_key_month"],
        "eight_api_pods": 730 * 8 * (Decimal(".25")*rates["fargate_vcpu_hour"] + rates["fargate_gb_hour"]),
        "three_system_and_two_controller_pods": 730 * 5 * (Decimal(".25")*rates["fargate_vcpu_hour"] + Decimal(".5")*rates["fargate_gb_hour"]),
        "two_separate_single_az_postgres_instances": 730 * 2 * rates["rds_" + suffix + "_hour"],
        "two_database_gp3_storage_envelopes": 2 * database_storage_gib * rates["rds_gp3_gb_month"],
        "two_master_and_four_runtime_secrets_design": 6 * rates["secret_month"],
        "two_data_kms_keys_design": 2 * rates["kms_key_month"],
        "ten_standard_alarm_metrics": 10 * rates["alarm_month"],
        "two_custom_http_error_metrics": 2 * rates["custom_metric_month"],
    }
    return {"classification":"Sensitivity, not an approved plan, cap or measured bill", "region":"us-east-2",
        "hours":730, "assumptions":{"namespaces":2,"clusters":1,"database_instances":2,
            "instance_class":instance_class,"database_storage_gib_each":database_storage_gib,
            "runtime_secrets":4,"data_keys":2,"controller_pods":2},
        "monthly_components_usd":{k:str(v.quantize(Decimal('.01'))) for k,v in rows.items()},
        "fixed_and_compute_subtotal_usd":str(sum(rows.values()).quantize(Decimal('.01'))),
        "excluded_requires_approved_usage":["NAT processing/cross-AZ/Internet transfer", "RDS CPU credits, backups/final snapshots",
            "SQS send/receive/delete/empty polls and KMS/API requests", "CloudWatch ingestion/storage/dashboards",
            "ECR image storage/scans and S3 state storage/requests", "ALB hours/LCUs/public IPv4 if approved",
            "Prometheus/Grafana or approved equivalent and migration surge", "taxes/credits"],
        "calculated_optimizations":{"avoid_second_eks_control_plane_usd_month":"73.00",
            "avoid_second_nat_and_ipv4_usd_month_before_cross_az_offset":"36.50",
            "untagged_ecr_storage_saved_per_removed_gb_month":str(rates["ecr_gb_month"])},
        "limitations":"Single cluster/network and single NAT are training cost tradeoffs; no production security/HA claim. Retained tagged digests preserve rollback. Live measurements required."}


if __name__ == "__main__":
    print(json.dumps({c:estimate(c) for c in ("db.t4g.micro","db.t4g.small","db.t4g.medium")},indent=2))
