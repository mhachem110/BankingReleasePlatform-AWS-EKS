"""Protected VPC-only seed and read-only verification of its native platform state."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, digest, require
from guard import configuration, STATE_KEY
from provisioner_policies import vpc_seed

POLICY = f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-VpcSeed"
ADDRESSES = {"terraform_data.prerequisites", "module.network.aws_vpc.this"}


def inputs(env):
    require(env.get("NETWORK_SEED_ENABLED") == "true", "VPC seed needs separate authorization")
    changed = dict(env)
    if changed.get("OPERATION") == "apply":
        require(env.get("APPROVAL") == "APPLY-REVIEWED-BANKING-VPC-SEED", "Separate VPC apply approval required")
        changed["APPROVAL"] = "APPLY-REVIEWED-PHASE3-PLAN"
    return configuration(changed)


def interface(env):
    info = json.loads(env.get("NETWORK_SEED_REVIEW_JSON") or "{}")
    import re
    require(info.get("account") == ACCOUNT and info.get("region") == REGION and info.get("state_key") == STATE_KEY,
            "Review the verified Banking VPC seed interface")
    for field, prefix in (("vpc_id", "vpc"), ("default_security_group_id", "sg")):
        require(re.fullmatch(prefix + r"-[a-f0-9]{17}", info.get(field, "")), "Invalid verified seed resource ID")
    return info


def plan_review(plan, values, effective_tags=True):
    require(plan.get("applyable") and isinstance(plan.get("complete"), bool) and not plan.get("errored") and not plan.get("deferred_changes"), "Applicable targeted seed plan without deferred changes required")
    rows = [r for r in plan.get("resource_changes", []) if r.get("mode") == "managed"]
    require(len(rows) == 2 and {r["address"] for r in rows} == ADDRESSES, "Seed may create only the VPC and local prerequisite guard")
    require(all(r["change"]["actions"] == ["create"] and not r["change"].get("importing") and not r.get("previous_address") for r in rows), "No seed adoption, update or replacement")
    vpc = next(r for r in rows if r["address"] == "module.network.aws_vpc.this")
    require(vpc["type"] == "aws_vpc", "Wrong seed resource type")
    require(next(r for r in rows if r["address"] == "terraform_data.prerequisites")["type"] == "terraform_data", "Wrong local guard type")
    after = vpc["change"]["after"]
    require(after["cidr_block"] == values.get("vpc_cidr", "10.70.0.0/16") and after["enable_dns_support"] is True and after["enable_dns_hostnames"] is True, "Seed CIDR/DNS drift")
    tags = {"Project": "BankingReleasePlatform", "Environment": "dev", "ManagedBy": "Terraform", "Owner": values["owner"], "Purpose": "CloudEngineerTraining", "Component": "network", "Name": "banking-dev-vpc"}
    if values.get("cost_center") is not None:
        tags["CostCenter"] = values["cost_center"]
    for field in (["tags", "tags_all"] if effective_tags else ["tags"]):
        require(after.get(field) == tags, "Unknown/incorrect seed tags")
    return {"managed_creates": 2, "aws_vpcs": 1, "iam_changes": 0, "eks_nat_database_resources": 0, "inventory": sorted(ADDRESSES), "cidr": after["cidr_block"]}


def aws(service, operation, *args):
    require(operation in {"get-caller-identity", "describe-vpcs", "describe-security-groups", "get-policy", "get-policy-version"}, "Outside read-only seed inspection")
    run = subprocess.run(["aws", service, operation, *args, "--region", REGION, "--output", "json"], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(run.stdout)


def policy_check(values, call=aws):
    meta = call("iam", "get-policy", "--policy-arn", POLICY)["Policy"]
    doc = call("iam", "get-policy-version", "--policy-arn", POLICY, "--version-id", meta["DefaultVersionId"])["PolicyVersion"]["Document"]
    require(digest(doc) == digest(vpc_seed(values["kms_key_arn"])), "Seed session cap differs from the exact scoped source proposal")
    Path("seed-policy-review.json").write_text(json.dumps({"arn": POLICY, "sha256": digest(doc), "version": meta["DefaultVersionId"], "document": doc}, indent=2))


def state_vpc(state):
    managed = [r for r in state.get("resources", []) if r.get("mode") == "managed"]
    addresses = {(r.get("module", "") + "." if r.get("module") else "") + r["type"] + "." + r["name"] for r in managed}
    require(len(managed) == 2 and addresses == ADDRESSES, "Platform backend must contain exactly the reviewed seed, without unrelated resources")
    vpc = next(r for r in managed if r["type"] == "aws_vpc")
    require(all(len(r.get("instances", [])) == 1 for r in managed), "Exact singleton seed resources required")
    return vpc["instances"][0]["attributes"]


def load_state():
    # Only a temporary read of this project's exact state object, never credentials.
    folder = Path("artifacts/seed-state-read").resolve(); folder.mkdir(parents=True, exist_ok=True)
    target = folder / "state.json"
    try:
        subprocess.run(["aws", "s3api", "get-object", "--bucket", BUCKET, "--key", STATE_KEY,
                        "--expected-bucket-owner", ACCOUNT, "--region", REGION, str(target)], capture_output=True, text=True, check=True)
        return json.loads(target.read_text())
    finally:
        if target.exists(): target.unlink()


def verify_seed(env, values, state=None, call=aws):
    info = interface(env)
    attributes = state_vpc(load_state() if state is None else state)
    require(attributes["id"] == info["vpc_id"] and attributes["default_security_group_id"] == info["default_security_group_id"], "Seed interface does not match actual Terraform state")
    require(attributes["cidr_block"] == values.get("vpc_cidr", "10.70.0.0/16"), "Seed CIDR mismatch")
    expected_tags = {"Project": "BankingReleasePlatform", "Environment": "dev", "ManagedBy": "Terraform", "Owner": values["owner"], "Purpose": "CloudEngineerTraining", "Component": "network", "Name": "banking-dev-vpc"}
    if values.get("cost_center") is not None:
        expected_tags["CostCenter"] = values["cost_center"]
    require(attributes.get("tags") == expected_tags, "Seed state ownership tag drift")
    live = call("ec2", "describe-vpcs", "--vpc-ids", info["vpc_id"])["Vpcs"]
    require(len(live) == 1 and live[0]["VpcId"] == attributes["id"] and live[0]["CidrBlock"] == attributes["cidr_block"] and live[0].get("OwnerId") == ACCOUNT, "Wrong live seed VPC")
    tags = {t["Key"]: t["Value"] for t in live[0].get("Tags", [])}
    require(all(tags.get(k) == v for k, v in attributes["tags"].items()), "Seed live tag drift")
    groups = call("ec2", "describe-security-groups", "--group-ids", info["default_security_group_id"])["SecurityGroups"]
    require(len(groups) == 1 and groups[0]["GroupId"] == info["default_security_group_id"] and groups[0]["VpcId"] == info["vpc_id"] and groups[0]["GroupName"] == "default" and groups[0]["OwnerId"] == ACCOUNT, "Wrong live default group")
    return info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["inputs", "preflight", "plan", "verify"])
    args = parser.parse_args()
    values = inputs(os.environ)
    if args.command == "inputs":
        Path("platform.tfvars.json").write_text(json.dumps(values, indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy_arn=" + POLICY + "\n")
    elif args.command == "preflight":
        policy_check(values)
        require(aws("sts", "get-caller-identity").get("Arn", "").startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/"), "Wrong seed identity")
        from preflight import overlaps
        overlaps(values.get("vpc_cidr", "10.70.0.0/16"), aws("ec2", "describe-vpcs")["Vpcs"])
    elif args.command == "plan":
        report = plan_review(json.loads(Path("platform-plan.json").read_text()), values)
        report["savedPlanSha256"] = hashlib.sha256(Path("platform.tfplan").read_bytes()).hexdigest()
        print(json.dumps(report, indent=2))
    else:
        state = load_state()
        vpc = state_vpc(state)
        info = {"account": ACCOUNT, "region": REGION, "state_key": STATE_KEY, "vpc_id": vpc["id"], "default_security_group_id": vpc["default_security_group_id"]}
        env = dict(os.environ, NETWORK_SEED_REVIEW_JSON=json.dumps(info))
        Path("seed-verification.json").write_text(json.dumps(verify_seed(env, values, state), indent=2))
