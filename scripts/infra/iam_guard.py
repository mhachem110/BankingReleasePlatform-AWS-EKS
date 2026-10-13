"""Separate first-creation IAM stage; exact inventory and saved-plan checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BOUNDARY, BUCKET, STATE_KEY, ROLE_NAMES, ROLE_ARNS, ATTACHMENTS, TAGS, PROPOSALS, digest, flow_policy, trust, require, verify_live_roles

POLICY_ARN = f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-IamPrerequisites"
POLICY_FOLDER = PROPOSALS.parents[1] / "provisioning/proposed"


def configuration(env):
    require(env.get("GITHUB_REF") == "refs/heads/dev", "Run only reviewed dev")
    require(env.get("IAM_PREREQUISITES_ENABLED") == "true", "IAM stage needs the explicit owner-authorized deployment window")
    require(env.get("BOOTSTRAP_STATE_READY") == "true", "Verified backend required")
    require(env.get("ROLE_ARN") == BOOTSTRAP, "Use the single exact bootstrap identity")
    require(env.get("AWS_REGION") == REGION and env.get("AWS_EXPECTED_ACCOUNT_ID") == ACCOUNT and env.get("TF_STATE_BUCKET") == BUCKET, "Wrong account/Region/backend")
    require(env.get("OPERATION") in {"plan", "apply"}, "No import, destroy or repair")
    if env["OPERATION"] == "apply":
        require(env.get("APPROVAL") == "APPLY-REVIEWED-BANKING-IAM-PLAN", "Separate exact IAM apply approval required")
    boundary = json.loads((POLICY_FOLDER / "BankingServicePermissionsBoundary.json").read_text())
    require(env.get("IAM_BOUNDARY_POLICY_SHA256") == digest(boundary), "Pin the verified Terraform-published project boundary")
    return {"permissions_boundary_arn": BOUNDARY, "boundary_policy_sha256": digest(boundary)}


def verify_plan(plan, inputs, effective_tags=True):
    require(plan.get("applyable") and plan.get("complete") is True and not plan.get("errored") and not plan.get("deferred_changes"), "Complete applyable plan required")
    items = [r for r in plan.get("resource_changes", []) if r.get("mode") == "managed"]
    expected = {f'aws_iam_role.service["{k}"]' for k in ROLE_NAMES} | {"aws_iam_role_policy_attachment.cluster", "aws_iam_role_policy_attachment.fargate", "aws_iam_role_policy.flow", "terraform_data.authorization"}
    require(len(items) == len(expected) and {r["address"] for r in items} == expected, "Only the exact three-role inventory is permitted")
    roles = []
    for item in items:
        change = item["change"]
        require(change["actions"] == ["create"] and not change.get("importing") and not item.get("previous_address"), "Only first creation; no existing-role adoption, replacement or mutation")
        after = change.get("after") or {}
        if item["address"].startswith("aws_iam_role.service["):
            key = item["address"].split('"')[1]
            require(item["type"] == "aws_iam_role", "Wrong resource type")
            require(after.get("name") == ROLE_NAMES[key] and after.get("path") == "/", "Role name/path changed")
            require(after.get("permissions_boundary") == inputs["permissions_boundary_arn"] == BOUNDARY, "Boundary changed or omitted")
            require(json.loads(after.get("assume_role_policy", "null")) == trust(key), "Only reviewed service trust is permitted")
            require(after.get("max_session_duration") == 3600 and after.get("force_detach_policies") is False, "Role lifecycle/session drift")
            for field in (["tags", "tags_all"] if effective_tags else ["tags"]):
                require(after.get(field) == dict(TAGS, Name=ROLE_NAMES[key]), "Unknown/incorrect role tags")
            roles.append({"name": ROLE_NAMES[key], "arn": ROLE_ARNS[key], "trust": trust(key), "permissionsBoundary": BOUNDARY})
        elif item["type"] == "aws_iam_role_policy_attachment":
            key = item["address"].split(".")[-1]
            require(after.get("role") == ROLE_NAMES[key] and after.get("policy_arn") == ATTACHMENTS[key], "Unapproved role/policy attachment")
        elif item["address"] == "aws_iam_role_policy.flow":
            require(item["type"] == "aws_iam_role_policy" and after.get("role") == ROLE_NAMES["flow"] and after.get("name") == "BankingFlowLogs" and json.loads(after.get("policy", "null")) == flow_policy(), "Unapproved inline policy")
        else:
            require(item["type"] == "terraform_data", "Wrong authorization resource type")
    return {"managed_creates": 7, "iam_roles": roles, "managed_policy_attachments": ATTACHMENTS, "inline_policy": flow_policy(), "boundarySha256": inputs["boundary_policy_sha256"], "updates": 0, "deletes": 0}


def read(service, operation, *args):
    require(operation in {"get-caller-identity", "get-role", "get-policy", "get-policy-version", "list-attached-role-policies", "list-role-policies", "get-role-policy", "simulate-principal-policy"}, "Outside read-only preflight")
    result = subprocess.run(["aws", service, operation, *args, "--region", REGION, "--output", "json", "--no-cli-pager"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        if operation == "get-role" and "NoSuchEntity" in result.stderr:
            return {"absent": True}
        raise ValueError(f"AWS blocked {service}:{operation}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def permission_simulations(call=read):
    reports = {}
    for key, arn in ROLE_ARNS.items():
        actions = ["iam:CreateRole", "iam:TagRole", "iam:AttachRolePolicy" if key in ATTACHMENTS else "iam:PutRolePolicy"]
        # IAM is a global service: its endpoint uses us-east-1. Do not model
        # an Ohio context and accidentally hide an applicable Region deny.
        context = [{"ContextKeyName": "aws:RequestedRegion", "ContextKeyValues": ["us-east-1"], "ContextKeyType": "string"},
                   {"ContextKeyName": "iam:PermissionsBoundary", "ContextKeyValues": [BOUNDARY], "ContextKeyType": "string"}]
        context += [{"ContextKeyName": "aws:RequestTag/" + k, "ContextKeyValues": [v], "ContextKeyType": "string"} for k, v in dict(TAGS, Name=ROLE_NAMES[key]).items()]
        context += [{"ContextKeyName": "aws:ResourceTag/Project", "ContextKeyValues": ["BankingReleasePlatform"], "ContextKeyType": "string"}, {"ContextKeyName": "aws:ResourceTag/Environment", "ContextKeyValues": ["shared"], "ContextKeyType": "string"}]
        if key in ATTACHMENTS:
            context.append({"ContextKeyName": "iam:PolicyARN", "ContextKeyValues": [ATTACHMENTS[key]], "ContextKeyType": "string"})
        response = call("iam", "simulate-principal-policy", "--policy-source-arn", BOOTSTRAP, "--action-names", *actions, "--resource-arns", arn, "--context-entries", json.dumps(context))
        results = response.get("EvaluationResults", [])
        require(len(results) == len(actions) and {r.get("EvalActionName") for r in results} == set(actions), "Permission simulation denied/unavailable/incomplete: " + json.dumps(response))
        require(all(r.get("EvalDecision") == "allowed" and r.get("EvalResourceName") == arn and not r.get("MissingContextValues") for r in results), "AWS policy evaluation blocks proposed IAM creation: " + json.dumps(response))
        reports[key] = response
    return reports


def preflight(inputs, call=read):
    identity = call("sts", "get-caller-identity")
    require(identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/cloudbatch818-mahmoud-cloudops-bootstrap/"), "Wrong assumed identity")
    for name in ROLE_NAMES.values():
        require(call("iam", "get-role", "--role-name", name).get("absent") is True, "Role already exists; stop for review without import or repair: " + name)
    name = BOOTSTRAP.split("/")[-1]
    bootstrap = call("iam", "get-role", "--role-name", name)["Role"]
    require(bootstrap.get("Arn") == BOOTSTRAP, "Bootstrap role identity changed")
    from bootstrap_authorization import verify as verify_authorization
    authorization = verify_authorization(call)
    docs = {}
    for arn in [BOUNDARY, POLICY_ARN, *ATTACHMENTS.values()]:
        meta = call("iam", "get-policy", "--policy-arn", arn)["Policy"]
        version = call("iam", "get-policy-version", "--policy-arn", arn, "--version-id", meta["DefaultVersionId"])["PolicyVersion"]
        docs[arn] = {"version": meta["DefaultVersionId"], "sha256": digest(version["Document"]), "document": version["Document"]}
    require(docs[BOUNDARY]["sha256"] == inputs["boundary_policy_sha256"], "Live boundary differs from approved source")
    expected = json.loads((POLICY_FOLDER / "BankingTerraformProvisioner-IamPrerequisites.json").read_text())
    require(docs[POLICY_ARN]["sha256"] == digest(expected), "Live IAM provisioning cap differs from reviewed proposal")
    docs["bootstrapAuthorization"] = dict(authorization, simulations=permission_simulations(call),
        advisoryOnly="Session caps restrict the owner-installed grant and are not role attachments. Simulation does not prove every resource/SCP/RCP context; the protected saved-plan apply must succeed.")
    return docs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inputs", "preflight", "plan", "verify"])
    parser.add_argument("--path", default="iam-plan.json")
    args = parser.parse_args()
    values = configuration(os.environ)
    if args.command == "inputs":
        Path("iam.tfvars.json").write_text(json.dumps(values, indent=2))
        Path("iam.tfbackend.json").write_text(json.dumps({"bucket": BUCKET, "key": STATE_KEY, "region": REGION, "encrypt": True, "use_lockfile": True, "allowed_account_ids": [ACCOUNT], "workspace_key_prefix": "banking-release-platform/_workspaces"}, indent=2))
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write("session_policy_arn=" + POLICY_ARN + "\n")
    elif args.command == "preflight":
        Path("iam-policy-review.json").write_text(json.dumps(preflight(values), indent=2))
    elif args.command == "verify":
        print(json.dumps(verify_live_roles(read, values["boundary_policy_sha256"]), indent=2))
    else:
        result = verify_plan(json.loads(Path(args.path).read_text()), values)
        result["savedPlanSha256"] = hashlib.sha256(Path("iam.tfplan").read_bytes()).hexdigest()
        print(json.dumps(result, indent=2))
