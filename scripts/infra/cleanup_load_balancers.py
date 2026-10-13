"""Require AWS absence of project ALBs after reviewed ingress deletion."""
import json
import os
from pathlib import Path
from cleanup_images import aws, require

if __name__ == "__main__":
    require(os.environ.get("TARGET") == "applications" and os.environ.get("OPERATION") == "apply",
            "ALB absence check belongs to protected application cleanup")
    identity = aws("sts", "get-caller-identity")
    require(identity["Account"] == "866934333672" and
            "assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/" in identity["Arn"],
            "Only Banking bootstrap may inspect live project ALBs")
    for lb in aws("elbv2", "describe-load-balancers")["LoadBalancers"]:
        tags = aws("elbv2", "describe-tags", "--resource-arns", lb["LoadBalancerArn"])["TagDescriptions"][0]["Tags"]
        values = {item["Key"]: item["Value"] for item in tags}
        require(values.get("Project") != "BankingReleasePlatform" and
                values.get("elbv2.k8s.aws/cluster") != "banking-dev",
                "Banking load balancer remains after ingress cleanup")
    path = Path("kubernetes-cleanup-verification.json")
    record = json.loads(path.read_text())
    require(record["workloads_removed"] is True and record["account"] == "866934333672",
            "No verified Kubernetes cleanup receipt")
    record["load_balancers_removed"] = True
    record["verified"] = True
    path.write_text(json.dumps(record, indent=2))
