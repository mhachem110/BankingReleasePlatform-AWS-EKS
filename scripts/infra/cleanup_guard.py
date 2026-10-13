"""Reviewed teardown of an exact Banking state; never edits bootstrap IAM/state."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BUCKET, BOUNDARY, ROLE_ARNS, ATTACHMENTS, require, digest, trust, flow_policy
from network_seed import ADDRESSES as SEED_ADDRESSES, interface

KEYS = {"vpc-seed": "banking-release-platform/dev/platform/terraform.tfstate",
        "platform": "banking-release-platform/dev/platform/terraform.tfstate",
        "dev-data": "banking-release-platform/dev/data/terraform.tfstate",
        "prod-data": "banking-release-platform/prod/data/terraform.tfstate",
        "iam-prerequisites": "banking-release-platform/shared/iam-prerequisites/terraform.tfstate",
        "policy-prerequisites": "banking-release-platform/shared/policy-prerequisites/terraform.tfstate",
        "platform-caps": "banking-release-platform/shared/platform-caps/terraform.tfstate",
        "runtime-foundation": "banking-release-platform/shared/runtime-foundation/terraform.tfstate"}
LOCAL = {"terraform_data"}
UNTAGGABLE = LOCAL | {"aws_route", "aws_route_table_association", "aws_ecr_lifecycle_policy",
    "aws_eks_access_policy_association", "aws_iam_role_policy", "aws_iam_role_policy_attachment",
    "aws_sqs_queue_policy", "aws_sqs_queue_redrive_policy", "aws_sqs_queue_redrive_allow_policy", "aws_cloudwatch_log_metric_filter", "aws_kms_alias"}


def inputs(env):
    require(env.get("GITHUB_REPOSITORY") == "mhachem110/BankingReleasePlatform-AWS-EKS" and env.get("GITHUB_REF") == "refs/heads/dev", "Cleanup uses reviewed Banking/dev only")
    require(env.get("CLEANUP_ENABLED") == "true" and env.get("AWS_OPERATIONS_ENABLED") == "false", "Explicit cleanup window; creation must be disabled")
    require(env.get("ROLE_ARN") == BOOTSTRAP and env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and env.get("AWS_REGION") == REGION and env.get("TF_STATE_BUCKET") == BUCKET, "Wrong cleanup identity/account/Region/backend")
    target = env.get("TARGET")
    require(target in {"vpc-seed", "policy-prerequisites", "iam-prerequisites", "runtime-foundation", "platform-caps"} and env.get("OPERATION") in {"plan", "apply"}, "Only the verified project prerequisites are enabled")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "DESTROY-REVIEWED-BANKING-" + target.upper(), "Exact destroy phrase and separate environment review required")
    require(re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", "")) and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ATTEMPT", "")), "Use an actual workflow run")
    return {"target": target, "key": KEYS[target], "account": ACCOUNT, "region": REGION,
            "run": env["GITHUB_RUN_ID"], "attempt": env["GITHUB_RUN_ATTEMPT"],
            "seed_interface_sha256": digest(interface(env)) if target == "vpc-seed" else None}


def backend(config):
    return {"bucket": BUCKET, "region": REGION, "key": config["key"], "encrypt": True,
            "use_lockfile": True, "allowed_account_ids": [ACCOUNT], "workspace_key_prefix": "banking-release-platform/_workspaces"}


def read_policy(config):
    bucket = "arn:aws:s3:::" + BUCKET
    dependency_keys = {config["key"], KEYS["dev-data"], KEYS["prod-data"]}
    if config["target"] in {"policy-prerequisites", "platform-caps"}:
        dependency_keys.update({KEYS["platform"], KEYS["iam-prerequisites"]})
    # Compact read-only project scope leaves enough room for exact role deletes
    # in the STS 2,048-character inline cap. Writes still name one selected state.
    state_reads = (bucket + "/banking-release-platform/*/terraform.tfstate" if config["target"] in {"iam-prerequisites", "runtime-foundation"} else
                   [bucket + "/" + key for key in sorted(dependency_keys)])
    actions = (["sts:GetCallerIdentity", "ec2:Describe*"] if config["target"] == "vpc-seed" else
               ["sts:GetCallerIdentity", "iam:Get*", "iam:List*", "kms:DescribeKey", "kms:Get*", "kms:List*", "eks:Describe*", "eks:List*", "ec2:DescribeVolumes", "rds:Describe*", "logs:DescribeLogGroups", "sqs:ListQueues", "sqs:GetQueueAttributes"] if config["target"] == "runtime-foundation" else
               ["sts:GetCallerIdentity", "iam:Get*", "iam:List*", "eks:Describe*", "eks:List*", "ec2:DescribeFlowLogs"] if config["target"] == "iam-prerequisites" else
               ["sts:GetCallerIdentity", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions"])
    rows = [{"Effect": "Allow", "Action": actions, "Resource": "*"},
            {"Effect": "Allow", "Action": ["s3:Get*", "s3:ListBucket"], "Resource": bucket},
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": state_reads},
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], "Resource": bucket + "/" + config["key"] + ".tflock"}]
    result = json.dumps({"Version": "2012-10-17", "Statement": rows}, separators=(",", ":"))
    require(len(result) <= 2048, "Read-only cleanup STS cap exceeds limit")
    return result


def inventory(target):
    if target == "platform-caps":
        from publish_platform_caps import inventory as cap_inventory
        return cap_inventory()
    if target == "runtime-foundation":
        return {"terraform_data.authorization", "aws_kms_key.runtime", "aws_kms_alias.runtime", "aws_iam_role.operator", "aws_iam_role_policy.operator"}
    if target == "vpc-seed":
        return SEED_ADDRESSES
    if target == "policy-prerequisites":
        from policy_prerequisites import POLICIES
        return {"terraform_data.authorization"} | {f'aws_iam_policy.project["{key}"]' for key in POLICIES}
    if target == "platform":
        spec = importlib.util.spec_from_file_location("plan_audit", Path(__file__).with_name("plan-audit.py"))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module.inventory_addresses()
    if target in {"dev-data", "prod-data"}:
        from data_guard import inventory as data_inventory
        return data_inventory()
    return {f'aws_iam_role.service["{key}"]' for key in ROLE_ARNS} | {"terraform_data.authorization", "aws_iam_role_policy_attachment.cluster", "aws_iam_role_policy_attachment.fargate", "aws_iam_role_policy.flow"}


def rows(state):
    result = []
    for resource in state.get("resources", []):
        if resource.get("mode") != "managed":
            continue
        prefix = resource.get("module", "")
        prefix = prefix + "." if prefix else ""
        for instance in resource.get("instances", []):
            require(not instance.get("deposed"), "Deposed state needs a separately reviewed recovery")
            address = prefix + resource["type"] + "." + resource["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"]) + "]"
            result.append({"address": address, "type": resource["type"], "values": instance["attributes"]})
    return result


def state_review(state, config, env):
    managed = rows(state)
    require(managed and len({r["address"] for r in managed}) == len(managed), "Nonempty singleton state without duplicate/deposed entries required")
    addresses = {r["address"] for r in managed}
    require(addresses <= inventory(config["target"]), "Unrelated resource address in cleanup state")
    if config["target"] == "platform-caps":
        from publish_platform_caps import documents, canonical, KEY
        require(state.get('outputs',{}).get('state_key',{}).get('value') == KEY and
                state.get('outputs',{}).get('contract_version',{}).get('value') == 1, 'Cap state contract differs')
        cap_documents = documents(state['outputs']['bindings']['value'])
    if config["target"] == "vpc-seed":
        require(addresses == SEED_ADDRESSES, "VPC seed cleanup refuses a full/partial platform state")
    if config["target"] == "iam-prerequisites":
        for item in managed:
            if item["type"] in {"aws_iam_role_policy_attachment", "aws_iam_role_policy"}:
                key = item["address"].rsplit(".", 1)[1]
                require(f'aws_iam_role.service["{key}"]' in addresses, "Role policy cleanup requires its managed service role in the same state")
    if config["target"] == "runtime-foundation":
        require("aws_kms_alias.runtime" not in addresses or "aws_kms_key.runtime" in addresses, "Alias cleanup requires its managed key")
        require("aws_iam_role_policy.operator" not in addresses or "aws_iam_role.operator" in addresses, "Inline cleanup requires its managed operator")
    expected_env = "prod" if config["target"] == "prod-data" else "shared" if config["target"] in {"iam-prerequisites", "policy-prerequisites", "runtime-foundation", "platform-caps"} else "dev"
    seed = interface(env) if config["target"] in {"vpc-seed", "platform"} else None
    for item in managed:
        value, kind = item["values"], item["type"]
        require(item["address"].rsplit(".", 1)[0].rsplit(".", 1)[-1] == kind, "State address/type mismatch")
        require(value.get("id"), "Actual resource ID required")
        if kind not in UNTAGGABLE:
            tags = value.get("tags") or {}
            allowed_env = {"prod"} if item["address"] in {"module.eks.aws_eks_access_entry.prod_deployer", "module.eks.aws_eks_fargate_profile.production"} else {expected_env}
            require(tags.get("Project") == "BankingReleasePlatform" and tags.get("Environment") in allowed_env and tags.get("ManagedBy") == "Terraform", "Cleanup ownership tags differ: " + item["address"])
        arn = value.get("arn")
        if arn:
            require(isinstance(arn, str) and arn.split(":")[4] == ACCOUNT and arn.split(":")[3] in {"", REGION}, "Wrong resource account/Region")
        if kind == "aws_vpc":
            require(value["id"] == seed["vpc_id"] and value.get("cidr_block") == "10.70.0.0/16", "Wrong verified VPC")
        if kind == "aws_iam_role":
            if config["target"] == "runtime-foundation":
                from runtime_foundation import OPERATOR, document
                require(value.get("arn") == OPERATOR and not value.get("permissions_boundary") and json.loads(value.get("assume_role_policy") or "{}") == document("operator-trust"), "Only the reviewed project operator may be removed")
            else:
                key = item["address"].split('"')[1]
                require(value.get("arn") == ROLE_ARNS[key], "Never delete bootstrap/application/other service roles")
                require(value.get("permissions_boundary") == BOUNDARY and json.loads(value.get("assume_role_policy") or "{}") == trust(key), "Service role boundary/trust differs from the reviewed source")
        if kind == "aws_kms_key":
            from runtime_foundation import document
            require(value.get("arn") == f"arn:aws:kms:{REGION}:{ACCOUNT}:key/{value['id']}" and json.loads(value.get("policy") or "{}") == document("key-policy") and value.get("tags", {}).get("Name") == "banking-runtime" and value.get("deletion_window_in_days") == 7, "Never schedule an existing/shared/unknown key for deletion")
        if kind == "aws_kms_alias":
            from runtime_foundation import ALIAS
            key = next(r["values"]["id"] for r in managed if r["type"] == "aws_kms_key")
            require(value.get("name") == value["id"] == ALIAS and value.get("target_key_id") == key, "Only the reviewed runtime alias/key binding may be removed")
        if kind == "aws_iam_policy":
            key = item["address"].split('"')[1]
            if config['target'] == 'platform-caps':
                from publish_platform_caps import ARNS, TAGS
                require(value.get('arn') == value['id'] == ARNS[key] and value.get('tags') == dict(TAGS,Name=key)
                        and json.loads(value.get('policy') or '{}') == cap_documents[key], 'Only the source-generated platform caps may be removed')
            else:
                from policy_prerequisites import POLICIES, document
                require(value.get("arn") == value["id"] == POLICIES[key][0] and json.loads(value.get("policy") or "{}") == document(key), "Only the reviewed project policy documents may be removed")
        if kind == "aws_iam_role_policy_attachment":
            key = item["address"].rsplit(".", 1)[1]
            require(value.get("role") == ROLE_ARNS[key].split("/")[-1] and value.get("policy_arn") == ATTACHMENTS[key], "Unexpected role attachment")
        if kind == "aws_iam_role_policy":
            if config["target"] == "runtime-foundation":
                from runtime_foundation import OPERATOR, document
                require(value.get("role") == OPERATOR.split("/")[-1] and value.get("name") == "BankingOperator" and json.loads(value.get("policy") or "{}") == document("operator-policy"), "Unexpected operator inline policy")
            else:
                require(value.get("role") == ROLE_ARNS["flow"].split("/")[-1] and value.get("name") == "BankingFlowLogs", "Unexpected inline policy")
        if kind == "aws_iam_openid_connect_provider":
            require(re.fullmatch(r"https://oidc\.eks\.us-east-2\.amazonaws\.com/id/[A-Za-z0-9]+", value.get("url", "")), "Never delete GitHub or another cluster's OIDC provider")
        if kind == "aws_eks_cluster":
            require(value.get("name") == "banking-dev", "Wrong cluster")
        if kind == "aws_ecr_repository":
            require(value.get("name") in {"banking-dev-account", "banking-dev-payment"} and value.get("force_delete") is False, "Keep explicit image inventory cleanup and safe repository deletion")
        if kind == "aws_db_instance":
            require(value.get("identifier") == "banking-" + expected_env + "-postgres" and value.get("skip_final_snapshot") is False and value.get("final_snapshot_identifier") == "banking-" + expected_env + "-postgres-final-reviewed", "Preserve reviewed final-snapshot policy")
    return {"target": config["target"], "state_key": config["key"], "lineage": state["lineage"], "serial": state["serial"], "inventory": managed}


def plan_review(plan, state_report):
    require(plan.get("applyable") is True and plan.get("complete") is True and not plan.get("errored") and not plan.get("deferred_changes"), "Complete saved destroy plan required")
    planned = [item for item in plan.get("resource_changes", []) if item.get("mode") == "managed"]
    original = {item["address"]: item for item in state_report["inventory"]}
    require(len(planned) == len(original) and {r["address"] for r in planned} == set(original), "Destroy inventory changed during refresh; re-inspect rather than conceal drift")
    for item in planned:
        change = item["change"]
        require(change["actions"] == ["delete"] and change.get("after") is None and not change.get("importing") and not item.get("previous_address"), "No create/update/replacement/import/state move in cleanup")
        before = change.get("before") or {}
        require(item["type"] == original[item["address"]]["type"] and before.get("id") == original[item["address"]]["values"]["id"], "Resource identity changed during cleanup refresh")
    return {"target": state_report["target"], "state_key": state_report["state_key"], "managed_deletes": len(planned), "managed_creates": 0, "managed_updates": 0,
            "inventory": [{"address": r["address"], "type": r["type"], "id": r["change"]["before"]["id"]} for r in planned], "retains": ["Phase 2 backend/state versions", "shared administrator keys/roles", "RDS final snapshots when data is selected"]}


def aws(service, operation, *arguments, absent_codes=()):
    result = subprocess.run(["aws", service, operation, *arguments, "--region", REGION, "--output", "json", "--no-cli-pager"], capture_output=True, text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        if any("(" + code + ")" in result.stderr for code in absent_codes):
            return {"absent": True}
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def check_identity():
    identity = aws("sts", "get-caller-identity")
    require(identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/"), "Wrong cleanup OIDC session")
    return identity


def other_state_empty(key):
    target = Path("cleanup-dependency.json")
    try:
        result = aws("s3api", "get-object", "--bucket", BUCKET, "--key", key, "--expected-bucket-owner", ACCOUNT, str(target), absent_codes=("NoSuchKey",))
        require(result.get("absent") or not rows(json.loads(target.read_text())), "Dependent project state still has managed resources: " + key)
    finally:
        target.unlink(missing_ok=True)


def preflight(config, report, env):
    check_identity()
    if config["target"] == "runtime-foundation":
        foundation_preflight(report)
    if config["target"] in {"platform", "vpc-seed", "iam-prerequisites", "policy-prerequisites", "runtime-foundation", "platform-caps"}:
        for name in ["dev-data", "prod-data"]:
            other_state_empty(KEYS[name])
    if config["target"] in {"policy-prerequisites", "platform-caps"}:
        from policy_prerequisites import document
        for name in (["platform", "iam-prerequisites"] if config['target']=='policy-prerequisites' else ['platform']):
            other_state_empty(KEYS[name])
        for item in report["inventory"]:
            if item["type"] != "aws_iam_policy":
                continue
            arn = item["values"]["arn"]
            meta = aws("iam", "get-policy", "--policy-arn", arn)["Policy"]
            require(meta.get("Arn") == arn and meta.get("AttachmentCount") == 0 and meta.get("PermissionsBoundaryUsageCount") == 0, "Project policy is in use; do not delete it")
            tags = {r["Key"]: r["Value"] for r in meta.get("Tags", [])}
            require(all(tags.get(k) == v for k, v in {"Project": "BankingReleasePlatform", "Environment": "shared", "ManagedBy": "Terraform"}.items()), "Live policy ownership changed")
            versions = aws("iam", "list-policy-versions", "--policy-arn", arn)["Versions"]
            require(len(versions) == 1 and versions[0].get("IsDefaultVersion") is True, "Additional policy versions require a separate inventory review")
            version = aws("iam", "get-policy-version", "--policy-arn", arn, "--version-id", meta["DefaultVersionId"])["PolicyVersion"]
            key = item["address"].split('"')[1]
            expected = json.loads(item['values']['policy']) if config['target'] == 'platform-caps' else document(key)
            require(version["Document"] == expected, "Live project policy document changed")
    if config["target"] == "iam-prerequisites":
        other_state_empty(KEYS["platform"])
        require(aws("eks", "describe-cluster", "--name", "banking-dev", absent_codes=("ResourceNotFoundException",)).get("absent"), "Cluster must be absent before service-role teardown")
        names = aws("eks", "list-clusters")["clusters"]
        for name in names:
            cluster = aws("eks", "describe-cluster", "--name", name)["cluster"]
            require(cluster.get("roleArn") not in ROLE_ARNS.values(), "A live cluster still references a project service role")
            for profile in aws("eks", "list-fargate-profiles", "--cluster-name", name)["fargateProfileNames"]:
                value = aws("eks", "describe-fargate-profile", "--cluster-name", name, "--fargate-profile-name", profile)["fargateProfile"]
                require(value.get("podExecutionRoleArn") not in ROLE_ARNS.values(), "A live Fargate profile still references a project service role")
        require(not any(r.get("DeliverLogsPermissionArn") in ROLE_ARNS.values() for r in aws("ec2", "describe-flow-logs")["FlowLogs"]), "A live flow log still references a project service role")
        for item in report["inventory"]:
            if item["type"] != "aws_iam_role":
                continue
            key = item["address"].split('"')[1]; name = ROLE_ARNS[key].split("/")[-1]
            role = aws("iam", "get-role", "--role-name", name)["Role"]
            require(role.get("Arn") == ROLE_ARNS[key] and role.get("Path") == "/" and role.get("AssumeRolePolicyDocument") == trust(key) and role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == BOUNDARY, "Live service role identity/trust/boundary changed")
            tags = {r["Key"]: r["Value"] for r in role.get("Tags", [])}
            require(all(tags.get(k) == v for k, v in {"Project": "BankingReleasePlatform", "Environment": "shared", "ManagedBy": "Terraform"}.items()), "Live service-role ownership changed")
            expected_attached = {r["values"]["policy_arn"] for r in report["inventory"] if r["type"] == "aws_iam_role_policy_attachment" and r["values"]["role"] == name}
            actual = aws("iam", "list-attached-role-policies", "--role-name", name)["AttachedPolicies"]
            require({r["PolicyArn"] for r in actual} == expected_attached, "Role has policy attachments outside the reviewed state")
            expected_inline = {r["values"]["name"] for r in report["inventory"] if r["type"] == "aws_iam_role_policy" and r["values"]["role"] == name}
            require(set(aws("iam", "list-role-policies", "--role-name", name)["PolicyNames"]) == expected_inline, "Role has inline policies outside the reviewed state")
            if expected_inline:
                require(aws("iam", "get-role-policy", "--role-name", name, "--policy-name", "BankingFlowLogs")["PolicyDocument"] == flow_policy(), "Live flow policy changed")
            require(not aws("iam", "list-instance-profiles-for-role", "--role-name", name)["InstanceProfiles"], "A live instance profile still references a service role")
    if config["target"] in {"vpc-seed", "platform"}:
        seed = interface(env)
        live = aws("ec2", "describe-vpcs", "--vpc-ids", seed["vpc_id"])["Vpcs"]
        require(len(live) == 1 and live[0]["OwnerId"] == ACCOUNT and live[0]["CidrBlock"] == "10.70.0.0/16", "Wrong live VPC")
        require({t["Key"]: t["Value"] for t in live[0].get("Tags", [])}.get("Project") == "BankingReleasePlatform", "Live VPC ownership changed")
        if config["target"] == "vpc-seed":
            for operation, field in [("describe-subnets", "Subnets"), ("describe-network-interfaces", "NetworkInterfaces")]:
                require(not aws("ec2", operation, "--filters", "Name=vpc-id,Values=" + seed["vpc_id"])[field], "Test VPC has dependents; do not delete it")
    for item in report["inventory"]:
        if item["type"] == "aws_ecr_repository":
            require(not aws("ecr", "list-images", "--repository-name", item["values"]["name"])["imageIds"], "Archive/remove authorized project images before repository cleanup; no force-delete")
    if config["target"] == "platform" and any(i["type"] == "aws_eks_cluster" for i in report["inventory"]):
        receipt = json.loads(env.get("KUBERNETES_CLEANUP_REVIEW_JSON") or "{}")
        require(receipt.get("cluster") == "banking-dev" and receipt.get("account") == ACCOUNT and receipt.get("workloads_removed") is True and receipt.get("load_balancers_removed") is True, "Reviewed Kubernetes/controller cleanup receipt required before cluster teardown")
    return {"identity": check_identity(), "dependency_checks_passed": True}


def foundation_preflight(report):
    from runtime_foundation import OPERATOR, ALIAS, document
    other_state_empty(KEYS["platform"])
    names = aws("eks", "list-clusters")["clusters"]
    for name in names:
        require(OPERATOR not in aws("eks", "list-access-entries", "--cluster-name", name)["accessEntries"], "Live cluster access still references the operator")
    role = next((r for r in report["inventory"] if r["type"] == "aws_iam_role"), None)
    if role:
        name = OPERATOR.split("/")[-1]; live = aws("iam", "get-role", "--role-name", name)["Role"]
        require(live.get("Arn") == OPERATOR and live.get("Path") == "/" and live.get("AssumeRolePolicyDocument") == document("operator-trust") and not live.get("PermissionsBoundary"), "Operator identity/trust changed")
        require({t["Key"]:t["Value"] for t in live.get("Tags",[])} == role["values"]["tags"], "Operator tags changed")
        require(not aws("iam", "list-attached-role-policies", "--role-name", name)["AttachedPolicies"] and not aws("iam", "list-instance-profiles-for-role", "--role-name", name)["InstanceProfiles"], "Operator has unreviewed attachments/profile use")
        inline = [r for r in report["inventory"] if r["type"] == "aws_iam_role_policy"]
        require(set(aws("iam", "list-role-policies", "--role-name", name)["PolicyNames"]) == ({"BankingOperator"} if inline else set()), "Operator has unreviewed inline grants")
        if inline: require(aws("iam", "get-role-policy", "--role-name", name, "--policy-name", "BankingOperator")["PolicyDocument"] == document("operator-policy"), "Operator inline document changed")
    key = next((r for r in report["inventory"] if r["type"] == "aws_kms_key"), None)
    if not key: return
    arn = key["values"]["arn"]; meta = aws("kms", "describe-key", "--key-id", arn)["KeyMetadata"]
    require(meta.get("Arn") == arn and meta.get("KeyState") == "Enabled" and meta.get("KeySpec") == "SYMMETRIC_DEFAULT" and meta.get("KeyUsage") == "ENCRYPT_DECRYPT", "Runtime key identity/state changed")
    require(json.loads(aws("kms", "get-key-policy", "--key-id", arn, "--policy-name", "default")["Policy"]) == document("key-policy"), "Key policy changed")
    require({t["TagKey"]:t["TagValue"] for t in aws("kms", "list-resource-tags", "--key-id", arn)["Tags"]} == key["values"]["tags"], "Key tags changed")
    require(not aws("kms", "list-grants", "--key-id", arn)["Grants"], "Key still has grants; review their use before cleanup")
    aliases = aws("kms", "list-aliases", "--key-id", arn)["Aliases"]
    require({a["AliasName"] for a in aliases} == ({ALIAS} if any(r["type"] == "aws_kms_alias" for r in report["inventory"]) else set()), "Key has aliases outside the reviewed state")
    for name in names:
        cluster = aws("eks", "describe-cluster", "--name", name)["cluster"]
        require(not any(c.get("provider",{}).get("keyArn") == arn for c in cluster.get("encryptionConfig",[])), "Key is used by a live cluster")
    for operation, field in [("describe-db-instances","DBInstances"),("describe-db-snapshots","DBSnapshots")]:
        require(not any(r.get("KmsKeyId") == arn for r in aws("rds", operation)[field]), "Key is used by a database or retained snapshot")
    require(not any(r.get("KmsKeyId") == arn for r in aws("ec2", "describe-volumes")["Volumes"]), "Key is used by an EBS volume")
    require(not any(r.get("kmsKeyId") == arn for r in aws("logs", "describe-log-groups")["logGroups"]), "Key is used by retained log groups")
    identifiers = {arn, meta["KeyId"], ALIAS, f"arn:aws:kms:{REGION}:{ACCOUNT}:{ALIAS}"}
    for url in aws("sqs", "list-queues").get("QueueUrls",[]):
        require(aws("sqs", "get-queue-attributes", "--queue-url", url, "--attribute-names", "KmsMasterKeyId").get("Attributes",{}).get("KmsMasterKeyId") not in identifiers, "Key is used by a live queue")


def foundation_delete_cap(config, report):
    from runtime_foundation import OPERATOR
    doc = json.loads(read_policy(config)); bucket = "arn:aws:s3:::" + BUCKET
    doc["Statement"] += [{"Effect":"Allow", "Action":["iam:DeleteRole","iam:DeleteRolePolicy"], "Resource":OPERATOR, "Condition":{"StringEquals":{"aws:ResourceTag/Project":"BankingReleasePlatform","aws:ResourceTag/Environment":"shared"}}},
                         {"Effect":"Allow", "Action":"s3:PutObject", "Resource":bucket + "/" + config["key"]}]
    for item in report["inventory"]:
        if item["type"] == "aws_kms_key":
            doc["Statement"].append({"Effect":"Allow","Action":"kms:ScheduleKeyDeletion","Resource":item["values"]["arn"],"Condition":{"StringEquals":{"aws:ResourceTag/Project":"BankingReleasePlatform","aws:ResourceTag/Environment":"shared","aws:ResourceTag/Name":"banking-runtime"}}})
        if item["type"] == "aws_kms_alias":
            doc["Statement"].append({"Effect":"Allow","Action":"kms:DeleteAlias","Resource":item["values"]["arn"]})
    value = json.dumps(doc,separators=(",",":")); require(len(value) <= 2048, "Foundation cleanup cap exceeds STS limit"); return value


def vpc_delete_cap(config, env):
    doc = json.loads(read_policy(config)); seed = interface(env)
    doc["Statement"] += [{"Effect": "Allow", "Action": "ec2:DeleteVpc", "Resource": f"arn:aws:ec2:{REGION}:{ACCOUNT}:vpc/{seed['vpc_id']}", "Condition": {"StringEquals": {"aws:RequestedRegion": REGION, "aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Environment": "dev"}}},
                        {"Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::" + BUCKET + "/" + config["key"]}]
    value = json.dumps(doc, separators=(",", ":"))
    require(len(value) <= 2048, "VPC destroy cap exceeds STS inline limit")
    return value


def policy_delete_cap(config):
    from policy_prerequisites import POLICIES
    from publish_platform_caps import ARNS
    arns = sorted(ARNS.values()) if config['target'] == 'platform-caps' else [v[0] for v in POLICIES.values()]
    doc = json.loads(read_policy(config))
    doc["Statement"] += [{"Effect": "Allow", "Action": "iam:DeletePolicy", "Resource": arns,
                          "Condition": {"StringEquals": {"aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Environment": "shared"}}},
                         {"Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::" + BUCKET + "/" + config["key"]}]
    value = json.dumps(doc, separators=(",", ":"))
    require(len(value) <= 2048, "Policy destroy cap exceeds STS limit")
    return value


def role_delete_cap(config):
    doc = json.loads(read_policy(config))
    tagged = {"StringEquals": {"aws:ResourceTag/Project": "BankingReleasePlatform", "aws:ResourceTag/Environment": "shared"}}
    doc["Statement"] += [{"Effect": "Allow", "Action": "iam:DeleteRole", "Resource": list(ROLE_ARNS.values()), "Condition": tagged},
                         {"Effect": "Allow", "Action": "iam:DetachRolePolicy", "Resource": [ROLE_ARNS[k] for k in ATTACHMENTS], "Condition": dict(tagged, ArnEquals={"iam:PolicyARN": list(ATTACHMENTS.values())})},
                         {"Effect": "Allow", "Action": "iam:DeleteRolePolicy", "Resource": ROLE_ARNS["flow"], "Condition": tagged},
                         {"Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::" + BUCKET + "/" + config["key"]}]
    value = json.dumps(doc, separators=(",", ":"))
    require(len(value) <= 2048, "Service-role cleanup cap exceeds STS limit")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["inputs", "preflight", "plan", "verify", "delete-cap", "saved"])
    args = parser.parse_args(); config = inputs(os.environ)
    if args.command == "inputs":
        Path("cleanup-config.json").write_text(json.dumps(config, indent=2))
        Path("cleanup.tfbackend.json").write_text(json.dumps(backend(config), indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy=" + read_policy(config) + "\n")
    elif args.command == "delete-cap":
        cap = (vpc_delete_cap(config, os.environ) if config["target"] == "vpc-seed" else
               foundation_delete_cap(config, json.loads(Path("cleanup-state-review.json").read_text())) if config["target"] == "runtime-foundation" else
               role_delete_cap(config) if config["target"] == "iam-prerequisites" else policy_delete_cap(config))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy=" + cap + "\n")
    elif args.command == "preflight":
        report = state_review(json.loads(Path("cleanup-state.json").read_text()), config, os.environ)
        Path("cleanup-state-review.json").write_text(json.dumps(report, indent=2))
        Path("cleanup-preflight.json").write_text(json.dumps(preflight(config, report, os.environ), indent=2))
    elif args.command == "saved":
        previous = json.loads(Path("reviewed/cleanup-config.json").read_text())
        require(config == previous, "Reviewed run/attempt/target/interface changed; create a new reviewed plan")
        require(backend(config) == json.loads(Path("reviewed/cleanup.tfbackend.json").read_text()), "Reviewed backend changed")
        fresh = json.loads(Path("cleanup-state-review.json").read_text())
        reviewed = json.loads(Path("reviewed/cleanup-state-review.json").read_text())
        require(fresh == reviewed, "State lineage/serial/inventory changed since review; create a new reviewed plan")
        report = json.loads(Path("reviewed/cleanup-plan-review.json").read_text())
        binary = Path("reviewed/cleanup.tfplan")
        require(hashlib.sha256(binary.read_bytes()).hexdigest() == report["saved_plan_sha256"] == os.environ.get("REVIEWED_DIGEST"), "Saved binary digest differs")
        require(plan_review(json.loads(Path("cleanup-plan.json").read_text()), fresh) == {k: v for k, v in report.items() if k != "saved_plan_sha256"}, "Saved destroy plan differs from the review")
    elif args.command == "plan":
        report = plan_review(json.loads(Path("cleanup-plan.json").read_text()), json.loads(Path("cleanup-state-review.json").read_text()))
        report["saved_plan_sha256"] = hashlib.sha256(Path("cleanup.tfplan").read_bytes()).hexdigest()
        Path("cleanup-plan-review.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    elif args.command == "verify":
        require(not rows(json.loads(Path("cleanup-state.json").read_text())), "Project state is not empty after destroy")
        check_identity()
        if config["target"] == "vpc-seed":
            seed = interface(os.environ)
            require(aws("ec2", "describe-vpcs", "--vpc-ids", seed["vpc_id"], absent_codes=("InvalidVpcID.NotFound",)).get("absent"), "VPC still exists")
        elif config["target"] in {"policy-prerequisites", "platform-caps"}:
            from policy_prerequisites import POLICIES
            from publish_platform_caps import ARNS
            policy_arns = ARNS.values() if config['target'] == 'platform-caps' else [v[0] for v in POLICIES.values()]
            for arn in policy_arns:
                require(aws("iam", "get-policy", "--policy-arn", arn, absent_codes=("NoSuchEntity",)).get("absent"), "Project policy still exists")
        elif config["target"] == "runtime-foundation":
            from runtime_foundation import OPERATOR, ALIAS
            require(aws("iam", "get-role", "--role-name", OPERATOR.split("/")[-1], absent_codes=("NoSuchEntity",)).get("absent"), "Operator still exists")
            for item in json.loads(Path("cleanup-state-review.json").read_text())["inventory"]:
                if item["type"] == "aws_kms_key":
                    meta = aws("kms", "describe-key", "--key-id", item["values"]["arn"])["KeyMetadata"]
                    require(meta.get("KeyState") == "PendingDeletion" and meta.get("DeletionDate"), "Key was not scheduled for deletion")
            require(not any(r.get("AliasName") == ALIAS for r in aws("kms", "list-aliases")["Aliases"]), "Runtime alias still exists")
        else:
            for arn in ROLE_ARNS.values():
                require(aws("iam", "get-role", "--role-name", arn.split("/")[-1], absent_codes=("NoSuchEntity",)).get("absent"), "Project service role still exists")
        Path("cleanup-verification.json").write_text(json.dumps({"target": config["target"], "account": ACCOUNT, "region": REGION, "state_key": config["key"], "managed_resources_remaining": 0, "verified": True}, indent=2))
