"""Inspect the single existing bootstrap identity and simulate without AWS writes.
Simulation reports do not authorize IAM changes and do not probe by CreateRole.
"""
import argparse
from datetime import datetime, timezone
import fnmatch
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from iam_contract import ACCOUNT, REGION, BOOTSTRAP, BOUNDARY, ROLE_ARNS, ROLE_NAMES, ATTACHMENTS, TAGS, digest

BASELINE_POLICIES = {"CloudOpsTrackerBootstrap": "78c12672b53ed0365036c5f65ca2d1fd1151d8f51417cc468611c7fe8ad1d076", "BankingReleasePlatformState": "ec727a3eb94b54085034192764bd015c7aaf97a2be66b9de8df6294ab92f6150"}
BASELINE_TRUST = {"GitHubOIDCRetailBootstrap": "834e6a92b1e204f695a9f0abe9e9dbba46e24377de7d844afbc05dd0827e23bb", "GitHubOIDCBankingBootstrap": "6405bb4174b22353c79094bb1f61b222213dfc2336c91f4fa1d89a04bcba0ce8"}
READS = {"get-caller-identity", "get-role", "list-role-policies", "get-role-policy", "list-attached-role-policies", "get-policy", "get-policy-version", "simulate-principal-policy"}


def read(service, operation, *args):
    if operation not in READS:
        raise ValueError("Outside approved read-only audit")
    result = subprocess.run(["aws", service, operation, *args, "--region", REGION, "--output", "json", "--no-cli-pager"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if result.returncode:
        return {"operation": service + ":" + operation, "inspectionError": result.stderr.strip()}
    return json.loads(result.stdout)


def statements(doc):
    rows = doc.get("Statement", [])
    return rows if isinstance(rows, list) else [rows]


def inventory(call=read):
    name = BOOTSTRAP.split("/")[-1]
    identity = call("sts", "get-caller-identity")
    if identity.get("Account") != ACCOUNT or not identity.get("Arn", "").startswith(f"arn:aws:sts::{ACCOUNT}:assumed-role/{name}/"):
        raise ValueError("Audit must use the exact bootstrap identity")
    role = call("iam", "get-role", "--role-name", name)
    names = call("iam", "list-role-policies", "--role-name", name)
    inline = {n: call("iam", "get-role-policy", "--role-name", name, "--policy-name", n) for n in names.get("PolicyNames", [])}
    attached = call("iam", "list-attached-role-policies", "--role-name", name)
    arns = {p["PolicyArn"] for p in attached.get("AttachedPolicies", [])}
    boundary = role.get("Role", {}).get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
    if boundary:
        arns.add(boundary)
    managed = {}
    for arn in sorted(arns):
        meta = call("iam", "get-policy", "--policy-arn", arn)
        version = meta.get("Policy", {}).get("DefaultVersionId")
        managed[arn] = {"metadata": meta, "version": call("iam", "get-policy-version", "--policy-arn", arn, "--version-id", version) if version else {"inspectionError": "Version unreadable"}}
    trust = statements(role.get("Role", {}).get("AssumeRolePolicyDocument", {}))
    return {"observedAt": datetime.now(timezone.utc).isoformat(), "readOnly": True, "identity": identity, "role": role, "inlineInventory": names, "inlinePolicies": inline, "attachedInventory": attached, "managedPoliciesIncludingBoundary": managed,
        "baselineInlineDocumentsUnchanged": {n: digest(inline[n]["PolicyDocument"]) == h if n in inline and "PolicyDocument" in inline[n] else None for n, h in BASELINE_POLICIES.items()},
        "baselineTrustStatementsUnchanged": {sid: any(s.get("Sid") == sid and digest(s) == h for s in trust) if "Role" in role else None for sid, h in BASELINE_TRUST.items()},
        "bootstrapBoundary": boundary,
        "noMutationPerformed": True}


def candidate_grants(report, action, resource):
    """Only identify candidate statements. Conditions/denies require simulation."""
    documents = [p.get("PolicyDocument", {}) for p in report["inlinePolicies"].values()]
    documents += [p.get("version", {}).get("PolicyVersion", {}).get("Document", {}) for p in report["managedPoliciesIncludingBoundary"].values() if p.get("metadata", {}).get("Policy", {}).get("Arn") != report.get("bootstrapBoundary")]
    candidates = []
    for doc in documents:
        for s in statements(doc):
            actions = s.get("Action", []); resources = s.get("Resource", [])
            actions = [actions] if isinstance(actions, str) else actions
            resources = [resources] if isinstance(resources, str) else resources
            if s.get("Effect") == "Allow" and any(fnmatch.fnmatchcase(action.lower(), a.lower()) for a in actions) and any(fnmatch.fnmatchcase(resource, r) for r in resources):
                candidates.append(s)
    return {"matchingAllowStatements": candidates, "effectiveAuthorizationProven": False}


def simulations(report, call=read, key=None):
    probes = []
    for role, arn in ROLE_ARNS.items():
        service = {"cluster": "eks.amazonaws.com", "fargate": "eks-fargate-pods.amazonaws.com", "flow": "vpc-flow-logs.amazonaws.com"}[role]
        contexts = [{"ContextKeyName": "aws:RequestedRegion", "ContextKeyValues": ["us-east-1"], "ContextKeyType": "string"}, {"ContextKeyName": "iam:PermissionsBoundary", "ContextKeyValues": [BOUNDARY], "ContextKeyType": "string"}, {"ContextKeyName": "iam:PassedToService", "ContextKeyValues": [service], "ContextKeyType": "string"}]
        contexts += [{"ContextKeyName": "aws:RequestTag/" + k, "ContextKeyValues": [v], "ContextKeyType": "string"} for k, v in dict(TAGS, Name=ROLE_NAMES[role]).items()]
        contexts += [{"ContextKeyName": "aws:ResourceTag/Project", "ContextKeyValues": ["BankingReleasePlatform"], "ContextKeyType": "string"}, {"ContextKeyName": "aws:ResourceTag/Environment", "ContextKeyValues": ["shared"], "ContextKeyType": "string"}]
        actions = ["iam:CreateRole", "iam:TagRole", "iam:PassRole"]
        if role in ATTACHMENTS:
            actions += ["iam:AttachRolePolicy"]
            contexts.append({"ContextKeyName": "iam:PolicyARN", "ContextKeyValues": [ATTACHMENTS[role]], "ContextKeyType": "string"})
        else:
            actions += ["iam:PutRolePolicy"]
        response = call("iam", "simulate-principal-policy", "--policy-source-arn", BOOTSTRAP, "--action-names", *actions, "--resource-arns", arn, "--context-entries", json.dumps(contexts))
        probes.append({"resource": arn, "actions": actions, "context": contexts, "roleIdentityPolicyCandidates": {a: candidate_grants(report, a, arn) for a in actions}, "simulation": response})
    if key:
        import re
        if not re.fullmatch(f"arn:aws:kms:{REGION}:{ACCOUNT}:key/[a-f0-9-]{{36}}", key):
            raise ValueError("Only a nominated same-account/Region key may be simulated")
        probes.append({"resource": key, "simulation": call("iam", "simulate-principal-policy", "--policy-source-arn", BOOTSTRAP, "--action-names", "kms:DescribeKey", "kms:CreateGrant", "kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "--resource-arns", key, "--context-entries", json.dumps([{"ContextKeyName": "aws:RequestedRegion", "ContextKeyValues": [REGION], "ContextKeyType": "string"}, {"ContextKeyName": "kms:GrantIsForAWSResource", "ContextKeyValues": ["true"], "ContextKeyType": "boolean"}]))})
    return probes


def summarize(report):
    simulations = [r for p in report["simulations"] for r in p.get("simulation", {}).get("EvaluationResults", [])]
    denied = [r for r in simulations if r.get("EvalDecision") != "allowed"]
    return {"status": "BLOCKED" if denied else "UNVERIFIED", "originalInlinePolicies": report["baselineInlineDocumentsUnchanged"], "retailAndBankingTrusts": report["baselineTrustStatementsUnchanged"], "deniedOrIncompleteSimulations": denied, "simulationReadDenials": [p["simulation"] for p in report["simulations"] if "inspectionError" in p.get("simulation", {})],
        "authorization": "Simulation does not include this workflow STS cap and does not prove every SCP/RCP/resource policy context. No API write was attempted. An administrator must authorize the exact bounded proposals; fresh successful reads and the later approved saved-plan apply are required.",
        "firstLivePlan": "Controlled Banking IAM prerequisites / operation=plan / protected bootstrap environment; only after boundary and exact IAM-stage policy are authorized"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output", default="artifacts/final-execution/bootstrap-role-audit.json")
    args = parser.parse_args()
    report = inventory()
    values = json.loads(os.environ.get("PLATFORM_INPUTS_JSON") or "{}")
    report["simulations"] = simulations(report, key=values.get("kms_key_arn"))
    report["review"] = summarize(report)
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["review"], indent=2))
