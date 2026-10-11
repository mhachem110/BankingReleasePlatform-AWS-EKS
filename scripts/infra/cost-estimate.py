"""Reproducible planning estimate, never an AWS bill or API call."""
from decimal import Decimal
import json
from pathlib import Path


def estimate(model):
    hours = Decimal(str(model["hours_per_month"]))
    cpu = Decimal(str(model["rates"]["fargate_vcpu_hour"]))
    ram = Decimal(str(model["rates"]["fargate_gb_hour"]))
    rows = []
    for pod in model["pods"]:
        monthly = hours * Decimal(pod["replicas"]) * (
            Decimal(str(pod["billed_vcpu"])) * cpu + Decimal(str(pod["billed_gb"])) * ram)
        rows.append({"component": pod["component"], "monthly_usd": str(monthly.quantize(Decimal(".01")))})
    fixed = sum(Decimal(str(v)) for v in model["fixed_monthly_usd"].values())
    total = fixed + sum(Decimal(r["monthly_usd"]) for r in rows)
    return {"pods": rows, "fixed_monthly_usd": str(fixed),
            "subtotal_monthly_usd": str(total.quantize(Decimal(".01"))),
            "excluded": model["excluded"]}


if __name__ == "__main__":
    print(json.dumps(estimate(json.loads(Path("docs/infrastructure/cost-model.json").read_text())), indent=2))
