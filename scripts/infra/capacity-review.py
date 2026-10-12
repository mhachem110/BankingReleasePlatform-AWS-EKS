"""Check administrator-reviewed quota evidence without claiming an AWS measurement."""
from datetime import datetime, timezone, timedelta
import math

# HPA max: 8 APIs + 3 system Pods + 2 controllers = 3.25 vCPU.
# Both API surges + one surge for each system/controller deployment = 1.25.
RECOMMENDED_HEADROOM_VCPU = 4.5


def verify(review, account, now=None):
    now = now or datetime.now(timezone.utc)
    if review.get("account") != account or review.get("region") != "us-east-2" or not review.get("reviewed_by"):
        raise ValueError("Return actual administrator-reviewed Ohio/account capacity evidence.")
    observed = datetime.fromisoformat(review["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None or not timedelta(0) <= now - observed <= timedelta(hours=24):
        raise ValueError("Capacity review must be timezone-aware and no more than 24 hours old.")
    limit, used = review["fargate_vcpu_limit"], review["current_vcpu_usage"]
    if any(isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or n < 0 for n in (limit, used)):
        raise ValueError("Actual numeric quota/utilization values are required.")
    if limit - used < RECOMMENDED_HEADROOM_VCPU:
        raise ValueError("Insufficient shared-account quota headroom for reviewed HPA/rollout capacity.")
    if review.get("other_platform_limits_approved") is not True:
        raise ValueError("Administrator must also approve EKS/NAT/EIP/ENI and private subnet IP headroom.")
    return {"evidence_source": "administrator-reviewed, not an automated AWS quota measurement",
            "available_vcpu": limit-used, "recommended_reserved_vcpu": RECOMMENDED_HEADROOM_VCPU}
