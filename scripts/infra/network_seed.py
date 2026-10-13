"""Protected VPC-only seed and read-only verification of its native platform state."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, digest, require
from guard import STATE_KEY

ADDRESSES = {"terraform_data.prerequisites", "module.network.aws_vpc.this"}


def inputs(env):
    require(env.get("GITHUB_REF") == "refs/heads/dev" and env.get("AWS_OPERATIONS_ENABLED") == "true", "Run only authorized reviewed dev")
    require(env.get("NETWORK_SEED_ENABLED") == "true", "VPC seed needs separate authorization")
    require(env.get("BOOTSTRAP_STATE_READY") == "true", "Verified backend required")
    require(env.get("ROLE_ARN") == BOOTSTRAP, "Use the single exact bootstrap identity")
    require(env.get("AWS_REGION") == REGION and env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and env.get("TF_STATE_BUCKET") == BUCKET, "Wrong account/Region/backend")
    require(env.get("OPERATION") in {"plan", "apply"}, "No destroy, import or state repair")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "APPLY-REVIEWED-BANKING-VPC-SEED", "Separate VPC apply approval required")
    values = json.loads(env.get("VPC_SEED_INPUTS_JSON") or "{}")
    require(isinstance(values, dict) and not set(values) - {"vpc_cidr", "owner", "cost_center"}, "Only VPC CIDR and ownership tags belong in this stage")
    values.setdefault("vpc_cidr", "10.70.0.0/16")
    values.setdefault("owner", "MahmoudHachem")
    require(values["vpc_cidr"] == "10.70.0.0/16", "Use the reviewed Banking CIDR")
    for field in ("owner", "cost_center"):
        value = values.get(field)
        require(value is None and field == "cost_center" or isinstance(value, str) and 0 < len(value.strip()) <= 128 and value == value.strip() and "REPLACE" not in value.upper(), "Use actual ownership tags")
    return dict(values, aws_region=REGION, expected_account_id=ACCOUNT, state_bucket_name=BUCKET)


def session_policy(write=True):
    """A restrictive inline cap, not an underlying role permission addition."""
    bucket = "arn:aws:s3:::" + BUCKET
    vpc = f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/*"
    rows = [
        {"Effect": "Allow", "Action": ["sts:GetCallerIdentity", "ec2:DescribeVpcs", "ec2:DescribeVpcAttribute", "ec2:DescribeSecurityGroups", "ec2:DescribeNetworkAcls", "ec2:DescribeRouteTables", "ec2:DescribeTags"], "Resource": "*"},
        {"Effect": "Allow", "Action": "ec2:CreateVpc", "Resource": vpc,
         "Condition": {"StringEquals": {"aws:RequestedRegion": REGION, "aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Environment": "dev", "aws:RequestTag/ManagedBy": "Terraform", "aws:RequestTag/Name": "banking-dev-vpc"}}},
        {"Effect": "Allow", "Action": "ec2:CreateTags", "Resource": vpc,
         "Condition": {"StringEquals": {"ec2:CreateAction": "CreateVpc", "aws:RequestedRegion": REGION}}},
        {"Effect": "Allow", "Action": "ec2:ModifyVpcAttribute", "Resource": vpc,
         "Condition": {"StringEquals": {"aws:RequestedRegion": REGION, "aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Name": "banking-dev-vpc"}}},
        {"Effect": "Allow", "Action": ["s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration", "s3:GetBucketPublicAccessBlock", "s3:GetBucketPolicy", "s3:GetBucketOwnershipControls", "s3:GetLifecycleConfiguration"], "Resource": bucket},
        {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": bucket,
         "Condition": {"StringLike": {"s3:prefix": ["banking-release-platform/dev/platform/*", "banking-release-platform/_workspaces/*"]}}},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": bucket + "/" + STATE_KEY},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": bucket + "/" + STATE_KEY + ".tflock"},
    ]
    if not write:
        rows = [r for r in rows if not str(r['Action']).startswith('ec2:Create') and r['Action'] != 'ec2:ModifyVpcAttribute']
        for row in rows:
            if row['Resource'] == bucket + '/' + STATE_KEY:
                row['Action'] = ['s3:GetObject']
    value = json.dumps({"Version": "2012-10-17", "Statement": rows}, separators=(",", ":"))
    require(len(value) <= 2048, "VPC-only inline STS cap exceeds AWS limit")
    return value


def interface(env):
    info = json.loads(env.get("NETWORK_SEED_REVIEW_JSON") or "{}")
    import re
    require(info.get("account") == ACCOUNT and info.get("region") == REGION and info.get("state_key") == STATE_KEY,
            "Review the verified Banking VPC seed interface")
    for field, prefix in (("vpc_id", "vpc"), ("default_security_group_id", "sg")):
        require(re.fullmatch(prefix + r"-[a-f0-9]{17}", info.get(field, "")), "Invalid verified seed resource ID")
    return info


def plan_review(plan, values, effective_tags=True):
    require(plan.get("applyable") and plan.get("complete") is True and not plan.get("errored") and not plan.get("deferred_changes"), "Complete VPC-only seed plan required")
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
    require(operation in {"get-caller-identity", "describe-vpcs", "describe-vpc-attribute", "describe-security-groups"}, "Outside read-only seed inspection")
    run = subprocess.run(["aws", service, operation, *args, "--region", REGION, "--output", "json"], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(run.stdout)


def policy_check(values, call=aws):
    identity = call("sts", "get-caller-identity")
    require(identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/"), "Wrong OIDC seed identity")
    doc = json.loads(session_policy(os.environ.get('WRITE_PROBE') == 'true'))
    Path("seed-policy-review.json").write_text(json.dumps({"roleArn": BOOTSTRAP, "sha256": digest(doc), "document": doc, "capOnly": True}, indent=2))
    Path("seed-oidc-identity.json").write_text(json.dumps(identity, indent=2))


def creation_probe(values, run=subprocess.run):
    tags = {"Project": "BankingReleasePlatform", "Environment": "dev", "ManagedBy": "Terraform", "Owner": values["owner"], "Purpose": "CloudEngineerTraining", "Component": "network", "Name": "banking-dev-vpc"}
    if values.get("cost_center") is not None:
        tags["CostCenter"] = values["cost_center"]
    specification = [{"ResourceType": "vpc", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}]
    command = ["aws", "ec2", "create-vpc", "--dry-run", "--cidr-block", values["vpc_cidr"], "--instance-tenancy", "default",
               "--tag-specifications", json.dumps(specification), "--region", REGION, "--output", "json", "--no-cli-pager"]
    result = run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
    require(result.returncode != 0 and "(DryRunOperation)" in result.stderr,
            "VPC creation authorization dry-run failed; nothing was provisioned by this probe: " + result.stderr.strip())
    return {"api": "ec2:CreateVpc", "dryRun": True, "authorized": True, "resourcesCreated": 0}


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
        result = subprocess.run(["aws", "s3api", "get-object", "--bucket", BUCKET, "--key", STATE_KEY,
                        "--expected-bucket-owner", ACCOUNT, "--region", REGION, str(target)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            require('(NoSuchKey)' in result.stderr, 'Cannot read platform state: ' + result.stderr.strip())
            return {}
        return json.loads(target.read_text())
    finally:
        if target.exists(): target.unlink()


def existing_seed(state, values, call=aws):
    """Reuse the owned VPC without ever planning the smaller seed root over EKS."""
    from cleanup_guard import rows, inventory
    managed = rows(state)
    if not managed:
        return None
    addresses = {r['address'] for r in managed}
    require(ADDRESSES <= addresses <= inventory('platform'), 'Unknown or incomplete VPC state; no automatic adoption or recreation')
    vpc = next(r['values'] for r in managed if r['address'] == 'module.network.aws_vpc.this')
    info = dict(account=ACCOUNT, region=REGION, state_key=STATE_KEY, vpc_id=vpc['id'],
                default_security_group_id=vpc['default_security_group_id'])
    # Inspect only the seed resources; the full platform stage checks the rest.
    seed_state = dict(state, resources=[r for r in state['resources'] if r.get('mode')=='managed' and
        ((r.get('module','')+'.' if r.get('module') else '')+r['type']+'.'+r['name']) in ADDRESSES])
    verify_seed({'NETWORK_SEED_REVIEW_JSON':json.dumps(info)}, values, seed_state, call)
    for attribute, key in [('enableDnsSupport','EnableDnsSupport'),('enableDnsHostnames','EnableDnsHostnames')]:
        require(call('ec2','describe-vpc-attribute','--vpc-id',vpc['id'],'--attribute',attribute).get(key,{}).get('Value') is True, 'Live VPC DNS drift')
    return dict(info, verified=True, dns_support=True, dns_hostnames=True, tags=vpc['tags'])


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
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["inputs", "preflight", "plan", "verify", "status", "write-cap"])
    args = parser.parse_args()
    values = inputs(os.environ)
    if args.command == "inputs":
        Path("platform.tfvars.json").write_text(json.dumps(values, indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy=" + session_policy(False) + "\n")
    elif args.command == 'write-cap':
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('session_policy='+session_policy(True)+'\n')
    elif args.command == 'status':
        report = existing_seed(load_state(), values)
        if report:Path('seed-verification.json').write_text(json.dumps(report,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('existing='+str(report is not None).lower()+'\n')
            out.write('interface_json='+json.dumps(report or {},separators=(',',':'))+'\n')
    elif args.command == "preflight":
        policy_check(values)
        from preflight import overlaps
        vpcs = aws("ec2", "describe-vpcs")["Vpcs"]
        overlaps(values["vpc_cidr"], vpcs)
        require(not any(any(t.get("Key") == "Name" and t.get("Value") == "banking-dev-vpc" for t in v.get("Tags", [])) for v in vpcs), "Banking VPC name already exists; stop without adoption or repair")
        probe = creation_probe(values) if os.environ.get('WRITE_PROBE') == 'true' else {'api':'ec2:CreateVpc','dryRun':False,'resourcesCreated':0,'status':'Not called from read-only planning session'}
        Path("seed-preflight.json").write_text(json.dumps({"vpcCountBefore": len(vpcs), "cidr": values["vpc_cidr"], "creationAuthorization": probe}, indent=2))
        print(json.dumps(probe))
    elif args.command == "plan":
        report = plan_review(json.loads(Path("platform-plan.json").read_text()), values)
        report["savedPlanSha256"] = hashlib.sha256(Path("platform.tfplan").read_bytes()).hexdigest()
        print(json.dumps(report, indent=2))
    else:
        state = load_state()
        vpc = state_vpc(state)
        info = {"account": ACCOUNT, "region": REGION, "state_key": STATE_KEY, "vpc_id": vpc["id"], "default_security_group_id": vpc["default_security_group_id"]}
        env = dict(os.environ, NETWORK_SEED_REVIEW_JSON=json.dumps(info))
        report = verify_seed(env, values, state)
        for attribute, key in (("enableDnsSupport", "EnableDnsSupport"), ("enableDnsHostnames", "EnableDnsHostnames")):
            require(aws("ec2", "describe-vpc-attribute", "--vpc-id", vpc["id"], "--attribute", attribute).get(key, {}).get("Value") is True, "Live VPC DNS attribute differs from plan")
        Path("seed-verification.json").write_text(json.dumps(dict(report, dns_support=True, dns_hostnames=True, tags=vpc["tags"], verified=True), indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('interface_json='+json.dumps(dict(report,verified=True),separators=(',',':'))+'\n')
