"""Bind runtime IAM/alerts to actual platform outputs and a native state.

Only this project's names, policies, issuer and owned state are accepted. This
does not modify bootstrap or attach any session cap to its identity policy.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from data_iam import session_cap, monitoring_trust, payment_trust, payment_permissions
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, canonical, digest, require
from cleanup_guard import aws, rows

KEY = "banking-release-platform/shared/runtime-prerequisites/terraform.tfstate"
ROOT = "infra/runtime-prerequisites"
NAMES = {"dev": "BankingReleasePlatformPhase6Session", "prod": "BankingReleasePlatformPhase6ProdSession"}
TAGS = {"Project": "BankingReleasePlatform", "ManagedBy": "Terraform", "Owner": "MahmoudHachem"}


def role(env):
    return f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-rds-monitoring" + ("-prod" if env == "prod" else "")


def topic(env):
    return f"arn:aws:sns:{REGION}:{ACCOUNT}:banking-{env}-alerts"


def policy(env):
    return f"arn:aws:iam::{ACCOUNT}:policy/{NAMES[env]}"


def payment_role(env):
    return f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-payment-runtime-{env}"


def backend():
    return dict(bucket=BUCKET, region=REGION, key=KEY, encrypt=True, use_lockfile=True,
                allowed_account_ids=[ACCOUNT], workspace_key_prefix="banking-release-platform/_workspaces")


def configuration(env):
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and
            env.get("GITHUB_REF") == "refs/heads/dev" and env.get("AWS_OPERATIONS_ENABLED") == "true" and
            env.get("BOOTSTRAP_STATE_READY") == "true" and env.get("CLEANUP_ENABLED") != "true", "Reviewed creation only")
    require(env.get("ROLE_ARN") == BOOTSTRAP and env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and
            env.get("AWS_REGION") == REGION and env.get("TF_STATE_BUCKET") == BUCKET, "Wrong provisioning identity/backend")
    require(env.get("OPERATION") in {"plan", "apply"}, "Plan/apply only")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "APPLY-REVIEWED-BANKING-RUNTIME", "Saved runtime plan requires review")
    foundation = json.loads(env.get("FOUNDATION_INTERFACE_JSON") or "{}")
    platform = json.loads(env.get("PLATFORM_INTERFACE_JSON") or "{}")
    require(foundation.get("verified") is True and platform.get("verified") is True, "Use applied dependencies")
    key = foundation["kms_key_arn"]
    outputs = platform["outputs"]
    def actual(name):
        return outputs[name]["value"]
    require(re.fullmatch(f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}", key), "Wrong runtime key")
    issuer, provider = actual("oidc_issuer_url"), actual("oidc_provider_arn")
    require(re.fullmatch(r"https://oidc\.eks\.us-east-2\.amazonaws\.com/id/[A-Fa-f0-9]{32}", issuer) and
            provider == f"arn:aws:iam::{ACCOUNT}:oidc-provider/{issuer.removeprefix('https://')}", "Wrong cluster OIDC provider")
    require(actual("cluster_name") == "banking-dev" and re.fullmatch(r"vpc-[a-f0-9]{17}", actual("vpc_id")), "Wrong Banking cluster/VPC")
    subnets = actual("database_subnet_ids")
    require(len(subnets) == 2 and len(set(subnets)) == 2 and all(re.fullmatch(r"subnet-[a-f0-9]{17}", s) for s in subnets), "Wrong database subnets")
    sg = actual("cluster_security_group_id")
    require(re.fullmatch(r"sg-[a-f0-9]{17}", sg), "Wrong cluster group")
    documents, payments = {}, {}
    for target in NAMES:
        values = {"kms_key_arn": key, "vpc_id": actual("vpc_id"), "cluster_security_group_id": sg,
                  "database_subnet_ids": subnets, "monitoring_role_arn": role(target), "alert_topic_arn": topic(target)}
        documents[target] = canonical(session_cap(values, policy(target), target))
        payments[target] = canonical(payment_permissions(key, target))
    return {"kms_key_arn": key, "oidc_issuer_url": issuer, "oidc_provider_arn": provider,
            "data_session_policies": documents, "payment_permissions": payments,
            "vpc_id": actual("vpc_id"), "database_subnet_ids": subnets,
            "cluster_security_group_id": sg}


def inventory():
    addresses = {"terraform_data.authorization", "aws_kms_key.alerts", "aws_kms_alias.alerts"}
    for env in NAMES:
        for typ, name in (("aws_iam_role", "monitoring"), ("aws_iam_role_policy_attachment", "monitoring"),
                          ("aws_iam_role", "payment"), ("aws_iam_role_policy", "payment"),
                          ("aws_sqs_queue", "alerts"), ("aws_sns_topic", "alerts"),
                          ("aws_sqs_queue_policy", "alerts"), ("aws_sns_topic_subscription", "alerts"),
                          ("aws_iam_policy", "data_session")):
            addresses.add(f'{typ}.{name}["{env}"]')
    return addresses


def read_state():
    with tempfile.TemporaryDirectory() as folder:
        path = str(Path(folder) / "state.json")
        result = subprocess.run(["aws", "s3api", "get-object", "--bucket", BUCKET, "--key", KEY,
            "--expected-bucket-owner", ACCOUNT, "--region", REGION, "--output", "json", path],
            capture_output=True, text=True, timeout=60)
        if result.returncode:
            require("(NoSuchKey)" in result.stderr, "Runtime state is unreadable: " + result.stderr.strip())
            return {}
        return json.loads(Path(path).read_text())


def live(config):
    identity = aws("sts", "get-caller-identity")
    require(identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(
        f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/"), "Wrong OIDC session")
    from runtime_foundation import read_state as foundation_state, existing_outputs
    from network_seed import load_state as network_state, existing_seed
    actual_foundation = existing_outputs(foundation_state())
    require(actual_foundation and actual_foundation["kms_key_arn"]["value"] == config["kms_key_arn"], "Foundation changed")
    network = existing_seed(network_state(), {"owner": "MahmoudHachem", "vpc_cidr": "10.70.0.0/16"})
    require(network and network["vpc_id"] == config["vpc_id"], "Network changed")
    cluster = aws("eks", "describe-cluster", "--name", "banking-dev")["cluster"]
    require(cluster.get("status") == "ACTIVE" and cluster["resourcesVpcConfig"]["vpcId"] == config["vpc_id"] and
            cluster["identity"]["oidc"]["issuer"] == config["oidc_issuer_url"], "Cluster dependency changed")
    return identity


def preflight(config):
    live(config)
    state = read_state()
    managed = rows(state)
    if not managed:
        # A pre-existing same-name resource without our native state is never adopted.
        for env in NAMES:
            require(aws("iam", "get-role", "--role-name", role(env).split("/")[-1], absent_codes=("NoSuchEntity",)).get("absent"), "Monitoring role collision")
            require(aws("iam", "get-policy", "--policy-arn", policy(env), absent_codes=("NoSuchEntity",)).get("absent"), "Data policy collision")
            require(aws("iam", "get-role", "--role-name", payment_role(env).split("/")[-1], absent_codes=("NoSuchEntity",)).get("absent"), "Payment role collision")
            require(aws("sns", "get-topic-attributes", "--topic-arn", topic(env), absent_codes=("NotFound",)).get("absent"), "Alert topic collision")
            require(aws("sqs", "get-queue-url", "--queue-name", f"banking-{env}-alerts", absent_codes=("AWS.SimpleQueueService.NonExistentQueue",)).get("absent"), "Alert queue collision")
        require(aws("kms", "describe-key", "--key-id", "alias/banking-release-platform-alerts", absent_codes=("NotFoundException",)).get("absent"), "Alert key alias collision")
        return {"verified": True, "reuse": False}
    require({r["address"] for r in managed} == inventory(), "Partial/unknown runtime state requires reviewed recovery")
    require(state.get("outputs", {}).get("state_key", {}).get("value") == KEY and
            state.get("outputs", {}).get("contract_version", {}).get("value") == 1, "Runtime state contract changed")
    for env in NAMES:
        item = next(r for r in managed if r["address"] == f'aws_iam_role.monitoring["{env}"]')["values"]
        require(item["arn"] == role(env) and json.loads(item["assume_role_policy"]) == monitoring_trust(env), "Monitoring role state changed")
        actual = aws("iam", "get-role", "--role-name", item["name"])["Role"]
        require(actual["Arn"] == role(env) and actual["AssumeRolePolicyDocument"] == monitoring_trust(env), "Monitoring role drift")
        payment = next(r for r in managed if r["address"] == f'aws_iam_role.payment["{env}"]')["values"]
        require(payment["arn"] == payment_role(env) and json.loads(payment["assume_role_policy"]) == payment_trust(config["oidc_issuer_url"], env), "Payment role state changed")
        actual_payment = aws("iam", "get-role", "--role-name", payment["name"])["Role"]
        require(actual_payment["Arn"] == payment_role(env) and actual_payment["AssumeRolePolicyDocument"] == payment_trust(config["oidc_issuer_url"], env), "Payment role drift")
        require(not aws("iam", "list-attached-role-policies", "--role-name", payment["name"])["AttachedPolicies"] and
                aws("iam", "list-role-policies", "--role-name", payment["name"])["PolicyNames"] == ["BankingPaymentRuntime"],
                "Payment role gained an unreviewed policy")
        actual_policy = aws("iam", "get-role-policy", "--role-name", payment["name"], "--policy-name", "BankingPaymentRuntime")["PolicyDocument"]
        require(actual_policy == json.loads(config["payment_permissions"][env]), "Payment queue/KMS policy drift")
        meta = aws("iam", "get-policy", "--policy-arn", policy(env))["Policy"]
        document = aws("iam", "get-policy-version", "--policy-arn", policy(env), "--version-id", meta["DefaultVersionId"])["PolicyVersion"]["Document"]
        require(document == json.loads(config["data_session_policies"][env]) and meta["AttachmentCount"] == 0, "Data cap drift")
        require(aws("sns", "get-topic-attributes", "--topic-arn", topic(env))["Attributes"]["SubscriptionsConfirmed"] == "1", "Alert subscription not confirmed")
    return {"verified": True, "reuse": True, "interface": state["outputs"]["interface"]["value"]}


def plan_review(plan, config):
    require(plan.get("complete") is True and not plan.get("errored") and not plan.get("deferred_changes"), "Complete runtime plan required")
    changes = [r for r in plan.get("resource_changes", []) if r.get("mode") == "managed"]
    require(len(changes) == len(inventory()) and {r["address"] for r in changes} == inventory(), "Unexpected runtime resource inventory")
    require(all(r["change"]["actions"] == ["create"] and not r["change"].get("importing") and not r.get("previous_address") for r in changes), "Only first creation is allowed")
    for row in changes:
        if row["type"] == "aws_iam_policy":
            env = row["address"].split('"')[1]
            after = row["change"]["after"]
            require(after["name"] == NAMES[env] and json.loads(after["policy"]) == json.loads(config["data_session_policies"][env]), "Data cap source mismatch")
        if row["type"] == "aws_iam_role":
            env = row["address"].split('"')[1]
            after = row["change"]["after"]
            if row["name"] == "monitoring":
                require(after["name"] == role(env).split("/")[-1] and json.loads(after["assume_role_policy"]) == monitoring_trust(env), "Monitoring trust source mismatch")
            else:
                require(after["name"] == payment_role(env).split("/")[-1] and json.loads(after["assume_role_policy"]) == payment_trust(config["oidc_issuer_url"], env), "Payment trust source mismatch")
        if row["type"] == "aws_iam_role_policy":
            env = row["address"].split('"')[1]
            require(row["change"]["after"]["name"] == "BankingPaymentRuntime" and
                    json.loads(row["change"]["after"]["policy"]) == json.loads(config["payment_permissions"][env]), "Payment policy source mismatch")
    require(plan.get("applyable") is True, "Expected a complete creation plan")
    return {"creates": len(changes), "updates": 0, "deletes": 0,
            "policy_sha256": {env: digest(json.loads(config["data_session_policies"][env])) for env in NAMES}}


def session_policy(write=False):
    bucket = "arn:aws:s3:::" + BUCKET
    state = bucket + "/" + KEY
    rows = [dict(Effect="Allow", Action=["sts:GetCallerIdentity", "iam:Get*", "iam:List*", "kms:DescribeKey", "kms:Get*", "kms:List*", "sns:Get*", "sns:List*", "sqs:Get*", "sqs:List*", "eks:DescribeCluster", "ec2:Describe*"], Resource="*"),
            dict(Effect="Allow", Action=["s3:Get*", "s3:ListBucket"], Resource=bucket),
            dict(Effect="Allow", Action="s3:GetObject", Resource=bucket + "/banking-release-platform/*/terraform.tfstate"),
            dict(Effect="Allow", Action=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource=state + ".tflock")]
    if write:
        resources = [f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-rds-monitoring*",
                     f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-payment-runtime-*",
                     f"arn:aws:iam::{ACCOUNT}:policy/BankingReleasePlatformPhase6*Session",
                     f"arn:aws:sns:{REGION}:{ACCOUNT}:banking-*-alerts",
                     f"arn:aws:sqs:{REGION}:{ACCOUNT}:banking-*-alerts"]
        rows += [dict(Effect="Allow", Action=["iam:CreateRole", "iam:AttachRolePolicy", "iam:PutRolePolicy", "iam:TagRole", "iam:CreatePolicy", "iam:TagPolicy", "sns:CreateTopic", "sns:Subscribe", "sns:TagResource", "sqs:CreateQueue", "sqs:SetQueueAttributes", "sqs:TagQueue"], Resource=resources + ["arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"]),
                 dict(Effect="Allow", Action="kms:CreateKey", Resource="*", Condition={"StringEquals": {"aws:RequestTag/Project": "BankingReleasePlatform", "aws:RequestTag/Name": "banking-alert-delivery"}}),
                 dict(Effect="Allow", Action=["kms:CreateAlias", "kms:EnableKeyRotation", "kms:TagResource", "kms:PutKeyPolicy"], Resource=f"arn:aws:kms:{REGION}:{ACCOUNT}:key/*"),
                 dict(Effect="Allow", Action="kms:CreateAlias", Resource=f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/banking-release-platform-alerts"),
                 dict(Effect="Allow", Action="s3:PutObject", Resource=state)]
    result = canonical({"Version": "2012-10-17", "Statement": rows})
    require(len(result) <= 2048, "Runtime STS cap exceeds the inline limit")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inputs", "preflight", "plan", "saved", "write-cap", "verify"])
    args = parser.parse_args()
    config = configuration(os.environ)
    if args.command == "inputs":
        tfvars = {k: config[k] for k in ("kms_key_arn", "oidc_issuer_url", "oidc_provider_arn", "data_session_policies", "payment_permissions")}
        Path("runtime-config.json").write_text(json.dumps(config, indent=2))
        Path("runtime.tfvars.json").write_text(json.dumps(tfvars, indent=2))
        Path("runtime.tfbackend.json").write_text(json.dumps(backend(), indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out: out.write("session_policy=" + session_policy() + "\n")
    elif args.command == "preflight":
        report = preflight(config)
        Path("runtime-preflight.json").write_text(json.dumps(report, indent=2))
        if report.get("reuse"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as out: out.write("interface_json=" + json.dumps({"verified": True, "outputs": report["interface"]}, separators=(",", ":")) + "\n")
    elif args.command == "plan":
        report = plan_review(json.loads(Path("runtime-plan.json").read_text()), config)
        report["saved_plan_sha256"] = hashlib.sha256(Path("runtime.tfplan").read_bytes()).hexdigest()
        Path("runtime-plan-review.json").write_text(json.dumps(report, indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out: out.write("apply_required=true\n")
    elif args.command == "saved":
        require(config == json.loads(Path("reviewed/runtime-config.json").read_text()), "Reviewed dependency changed")
        require(backend() == json.loads(Path("reviewed/runtime.tfbackend.json").read_text()), "Reviewed backend changed")
        reviewed = json.loads(Path("reviewed/runtime-plan-review.json").read_text())
        require(hashlib.sha256(Path("reviewed/runtime.tfplan").read_bytes()).hexdigest() == reviewed["saved_plan_sha256"] == os.environ["REVIEWED_DIGEST"], "Saved plan changed")
        require(plan_review(json.loads(Path("runtime-plan.json").read_text()), config) == {k:v for k,v in reviewed.items() if k != "saved_plan_sha256"}, "Saved scope changed")
        live(config)
    elif args.command == "write-cap":
        with open(os.environ["GITHUB_OUTPUT"], "a") as out: out.write("session_policy=" + session_policy(True) + "\n")
    else:
        live(config)
        outputs = json.loads(Path("runtime-outputs.json").read_text())
        proof = preflight(config)
        require(proof.get("reuse") and outputs["state_key"]["value"] == KEY, "Runtime apply not verified")
        interface = {"verified": True, "outputs": outputs["interface"]["value"]}
        Path("runtime-verification.json").write_text(json.dumps(interface, indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out: out.write("interface_json=" + json.dumps(interface, separators=(",", ":")) + "\n")
