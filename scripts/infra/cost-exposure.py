"""Offline baseline and duration/scaling model. Usage assumptions are explicit."""
from decimal import Decimal
import copy
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("cost", Path(__file__).with_name("cost-estimate.py"))
cost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cost)


def scenarios(model):
    result = {}
    for name in ("initial_system", "four_apis", "four_apis_and_controller", "hpa_max", "hpa_max_all_rollouts"):
        scenario = copy.deepcopy(model)
        if name == "initial_system":
            scenario["pods"] = [p for p in model["pods"] if p["component"] in ("CoreDNS", "Metrics Server")]
        elif name == "four_apis":
            scenario["pods"] = model["pods"][:3]
        if name.startswith("hpa_max"):
            scenario["pods"][0]["replicas"] = 8
        if name == "hpa_max_all_rollouts":
            scenario["pods"][0]["replicas"] += 2
            for pod in scenario["pods"][1:]:
                pod["replicas"] += 1
        hourly = sum(Decimal(str(value)) / Decimal(str(model["hours_per_month"])) for value in model["fixed_monthly_usd"].values())
        for pod in scenario["pods"]:
            hourly += Decimal(pod["replicas"]) * (
                Decimal(pod["billed_vcpu"]) * Decimal(model["rates"]["fargate_vcpu_hour"]) +
                Decimal(pod["billed_gb"]) * Decimal(model["rates"]["fargate_gb_hour"]))
        result[name] = {"hourly_usd": str(hourly.quantize(Decimal('.0001'))),
            "duration_usd": {str(h): str((hourly * h).quantize(Decimal('.01'))) for h in (8, 24, 40, 730)},
            "steady_vcpu": str(sum(Decimal(p["billed_vcpu"])*p["replicas"] for p in scenario["pods"])),
            "pod_count": sum(p["replicas"] for p in scenario["pods"]),
            "monthly": cost.estimate(scenario)}
    return result


def usage_estimate(usage):
    """Optional Ohio planning unit rates; no free tiers or usage are assumed."""
    rates = {"nat_processed_gb": ".045", "logs_ingested_gb": ".50",
             "logs_stored_gb_month": ".03", "ecr_stored_gb_month": ".10",
             "s3_standard_gb_month": ".023", "s3_put_requests": ".000005",
             "s3_get_requests": ".0000004", "kms_symmetric_requests": ".000003",
             "alb_hours": ".0225", "alb_lcu_hours": ".008", "alb_public_ipv4_hours": ".005"}
    unknown = set(usage) - set(rates)
    if unknown:
        raise ValueError("Unsupported usage units: " + str(sorted(unknown)))
    rows = {key: Decimal(str(amount)) * Decimal(rates[key]) for key, amount in usage.items()}
    if any(Decimal(str(n)) < 0 for n in usage.values()):
        raise ValueError("Usage cannot be negative")
    return {"rates_usd_per_unit": rates, "assumed_usage": usage,
            "charges_usd": {key: str(amount.quantize(Decimal('.01'))) for key, amount in rows.items()},
            "total_usd": str(sum(rows.values(), Decimal(0)).quantize(Decimal('.01'))),
            "not_included": "Cross-AZ/Internet transfer depends on direction, service and volume; add the actual reviewed traffic estimate. No fabricated usage is a baseline."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--usage-json", help="Optional local JSON with actual approved usage assumptions")
    args = parser.parse_args()
    model = json.loads(Path("docs/infrastructure/cost-model.json").read_text())
    output = {"scenarios": scenarios(model), "variable_usage": usage_estimate(
        json.loads(Path(args.usage_json).read_text()) if args.usage_json else {})}
    print(json.dumps(output, indent=2))
