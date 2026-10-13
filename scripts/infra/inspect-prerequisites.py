"""Read-only metadata discovery; does not select/approve infrastructure inputs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

OPERATIONS = {("sts", "get-caller-identity"), ("eks", "list-clusters"), ("eks", "describe-cluster"),
              ("eks", "describe-cluster-versions"), ("eks", "describe-addon-versions"),
              ("eks", "describe-addon-configuration"), ("ec2", "describe-vpcs"),
              ("ec2", "describe-availability-zones"), ("service-quotas", "list-service-quotas"),
              ("kms", "describe-key"), ("kms", "get-key-policy"), ("kms", "list-grants")}


def inspect(profile=None, *, reader=None, inputs=None):
    report = {"readOnly": True, "observedAt": datetime.now(timezone.utc).isoformat(), "checks": {}}
    def call(label, service, operation, *args):
        if (service, operation) not in OPERATIONS:
            raise ValueError("Mutation is outside this inspector")
        if reader is not None:
            value = reader(service, operation, *args)
            report["checks"][label] = value
            return value
        command = ["aws", service, operation, *args, "--region", "us-east-2", "--output", "json", "--no-cli-pager"]
        if profile:
            command += ["--profile", profile]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=90)
        value = json.loads(result.stdout) if result.returncode == 0 else {"inspectionError":result.stderr.strip()}
        report["checks"][label] = value
        return value
    identity = call("identity", "sts", "get-caller-identity")
    if identity.get("Account") != "866934333672":
        raise ValueError("Approved read-only account access is unavailable")
    clusters = call("clusters", "eks", "list-clusters")
    if "banking-dev" in clusters.get("clusters", []):
        call("existingBankingCluster", "eks", "describe-cluster", "--name", "banking-dev")
        report["initialPlanBlocked"] = "Existing Banking cluster detected: inspect state/recovery instead of recreating it"
    call("vpcAssociations", "ec2", "describe-vpcs")
    call("availableZones", "ec2", "describe-availability-zones")
    call("clusterCatalog", "eks", "describe-cluster-versions", "--cluster-versions", "1.36")
    inputs = inputs if inputs is not None else json.loads(os.environ.get("PLATFORM_INPUTS_JSON") or "{}")
    report["addonCandidates"] = {}
    for name in ("coredns", "metrics-server"):
        catalog = call(name+"Catalog", "eks", "describe-addon-versions", "--addon-name", name, "--kubernetes-version", "1.36")
        pinned = inputs.get("addon_versions", {}).get(name)
        candidates = [v["addonVersion"] for addon in catalog.get("addons", [])
                      if addon.get("addonName") == name for v in addon.get("addonVersions", [])
                      if "amd64" in v.get("architecture", []) and "fargate" in v.get("computeTypes", [])
                      and any(c.get("clusterVersion") == "1.36" and (pinned or c.get("defaultVersion"))
                              for c in v.get("compatibilities", []))
                      and (not pinned or v["addonVersion"] == pinned)]
        if len(set(candidates)) == 1:
            candidate = candidates[0]
            report["addonCandidates"][name] = {"version": candidate, "administratorApproved": False}
            call(name+"Schema", "eks", "describe-addon-configuration", "--addon-name", name, "--addon-version", candidate)
        else:
            report["addonCandidates"][name] = {"inspectionError": "No unique compatible amd64/Fargate catalog candidate; do not guess a version"}
    for service in ("eks", "fargate", "ec2", "vpc"):
        call(service+"Quota", "service-quotas", "list-service-quotas", "--service-code", service)
    if inputs.get("kms_key_arn"):
        for operation in ("describe-key", "get-key-policy", "list-grants"):
            args = ["--key-id", inputs["kms_key_arn"]]
            if operation == "get-key-policy":
                args += ["--policy-name", "default"]
            call(operation, "kms", operation, *args)
    else:
        report["keyInspectionBlocked"] = "No administrator-approved KMS ARN supplied; no key selected or created"
    report["capacityUtilizationVerified"] = False
    report["capacityNote"] = "Quota catalog is insufficient: actual shared-account Fargate utilization/ENI/IP headroom and approval are still required"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile")
    parser.add_argument("--output", default="artifacts/final-execution/aws-prerequisites.json")
    args = parser.parse_args()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(inspect(args.profile), indent=2)+"\n", encoding="utf-8")
    print("Read-only metadata evidence saved; no Terraform, IAM mutations or resource creation.")
