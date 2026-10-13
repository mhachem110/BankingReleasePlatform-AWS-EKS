"""Report inspection findings without turning collection success into plan approval.

Reads saved metadata only. No AWS/GitHub calls, credentials, mutations or tfvars.
The protected live preflight and owner approval remain separate requirements.
"""
import argparse
import json
import os
from pathlib import Path
import re

ACCOUNT = "866934333672"
ROLE_NAMES = (
    "cloudbatch818-mahmoud-banking-eks-cluster",
    "cloudbatch818-mahmoud-banking-fargate-execution",
    "cloudbatch818-mahmoud-banking-flow-logs",
)
ACTIONS = {
    "organizations:list-policies-for-target": "organizations:ListPoliciesForTarget",
    "organizations:list-parents": "organizations:ListParents",
    "organizations:describe-policy": "organizations:DescribePolicy",
}


def error_kind(value):
    message = value.get("inspectionError", "")
    if not message:
        return "OBSERVED"
    if re.search(r"\b(AccessDenied|AccessDeniedException|UnauthorizedOperation)\b", message):
        return "DENIED"
    if re.search(r"\b(NoSuchEntity|ResourceNotFoundException)\b", message):
        return "ABSENT"
    return "UNVERIFIED"


def errors(value, path=""):
    if isinstance(value, dict):
        if "inspectionError" in value:
            yield path, value
        for key, item in value.items():
            yield from errors(item, path + "/" + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from errors(item, path + "/" + str(index))


def reconcile(audit, prerequisites):
    for identity in (audit.get("identity", {}), prerequisites.get("checks", {}).get("identity", {})):
        if identity.get("Account") != ACCOUNT:
            raise ValueError("Both evidence files must prove the approved AWS account")
    checks = prerequisites.get("checks", {})
    diagnostic = []
    permissions = set()
    for scope, source in (("roles", audit), ("prerequisites", prerequisites)):
        for path, value in errors(source):
            kind = error_kind(value)
            action = ACTIONS.get(value.get("operation"))
            if kind == "DENIED":
                found = re.search(r"(?:perform:\s*|AccessDenied:\s*)([a-z0-9-]+:[A-Za-z]+)", value["inspectionError"])
                action = found.group(1) if found else action
                if path.endswith("Quota"):
                    action = "servicequotas:ListServiceQuotas"
                if action:
                    permissions.add(action)
            diagnostic.append({"scope": scope, "path": path, "status": kind,
                               "readAction": action, "diagnostic": value["inspectionError"]})
    roles = {}
    for name in ROLE_NAMES:
        result = audit.get("prerequisiteRoles", {}).get(name, {}).get("role", {})
        role = result.get("Role", {})
        roles[name] = {"status": error_kind(result) if result else "UNVERIFIED",
                       "arn": role.get("Arn")}
        if not role and roles[name]["status"] == "OBSERVED":
            roles[name]["status"] = "UNVERIFIED"
    deployment = {}
    for environment in ("dev", "prod"):
        result = audit.get("roles", {}).get(environment, {})
        review = result.get("review", {})
        findings = review.get("reviewFindings", [])
        deployment[environment] = {
            "arn": result.get("role", {}).get("Arn"),
            "bankingTrustObserved": review.get("exactBankingTrustFound") is True,
            "bankingInlinePolicyObserved": "BankingReleasePlatform" + environment.title() + "Deploy" in result.get("inlinePolicies", {}),
            "documentsComplete": review.get("documentsComplete") is True,
            "permissionsBoundary": review.get("permissionsBoundary"),
            "broadPermissionFindings": len(findings),
            "administratorScopeReviewRequired": True,
            "liveEnvironmentOidcAndRbacVerified": False,
        }
    clusters = checks.get("clusters", {})
    cluster_status = error_kind(clusters)
    if cluster_status == "OBSERVED":
        cluster_status = ("PRESENT_REQUIRES_STATE_RECONCILIATION" if "banking-dev" in clusters.get("clusters", [])
                          else "ABSENT" if "clusters" in clusters else "UNVERIFIED")
    addon_candidates = {}
    for name in ("coredns", "metrics-server"):
        catalog = checks.get(name + "Catalog", {})
        defaults = [v["addonVersion"] for addon in catalog.get("addons", [])
                    if addon.get("addonName") == name for v in addon.get("addonVersions", [])
                    if "amd64" in v.get("architecture", []) and "fargate" in v.get("computeTypes", [])
                    and any(c.get("clusterVersion") == "1.36" and c.get("defaultVersion") for c in v.get("compatibilities", []))]
        selected = prerequisites.get("addonCandidates", {}).get(name, {}).get("version")
        version = selected or (defaults[0] if len(set(defaults)) == 1 else None)
        schema = checks.get(name + "Schema", {})
        addon_candidates[name] = {"catalogCandidate": version,
                                  "schemaCollected": bool(schema.get("configurationSchema")) and schema.get("addonVersion") == version,
                                  "administratorApproved": False}
    return {
        "account": ACCOUNT, "region": "us-east-2", "observedAt": prerequisites.get("observedAt"),
        "inspectionCollection": "COMPLETED_WITH_FINDINGS",
        "livePlanReadiness": "BLOCKED", "authorizesAwsOperations": False,
        "bootstrapOidcAccountVerified": True,
        "bankingCluster": cluster_status, "serviceRoles": roles, "deploymentRoles": deployment,
        "missingReadPermissions": sorted(permissions), "diagnostics": diagnostic,
        "addonCandidates": addon_candidates,
        "outstanding": ["Administrator role scope review and actual operator/KMS nominations",
                        "Approved service roles, key policy/grants and additive platform permissions",
                        "Quota AND actual utilization/headroom review within 24 hours",
                        "Approved CIDR/AZs and stable operator/deployment-runner network access",
                        "Exact add-on schema validation and administrator-approved pins",
                        "Complete platform inputs and explicit protected live-plan authorization"],
    }


def markdown(report):
    rows = ["# Banking AWS inspection readiness", "",
            "**Live plan readiness: BLOCKED.** Collection success does not authorize provisioning.", "",
            f"Account {report['account']}, Region {report['region']}; observed {report['observedAt']}.", "",
            f"Banking cluster: {report['bankingCluster']}.", "",
            "| Service role | Inspection result |", "| --- | --- |"]
    rows += [f"| {name} | {result['status']} |" for name, result in report["serviceRoles"].items()]
    rows += ["", "| Deployment role | Banking trust | Inline policy | Broad permission findings |",
             "| --- | --- | --- | --- |"]
    rows += [f"| {env} | {v['bankingTrustObserved']} | {v['bankingInlinePolicyObserved']} | {v['broadPermissionFindings']} |"
             for env, v in report["deploymentRoles"].items()]
    rows += ["", "Denied metadata read actions (administrator review required):", ""]
    rows += ["- " + action for action in report["missingReadPermissions"]] or ["- None observed; absence of a denial is not proof of effective authorization."]
    rows += ["", "NoSuchEntity is reported as ABSENT; AccessDenied is DENIED and never proves absence.", "",
             "Outstanding gates:", ""]
    rows += ["- " + item for item in report["outstanding"]]
    rows += ["", "See aws-role-audit.json and aws-prerequisites.json for full diagnostics. Existing Banking trusts/policies should not be recreated when already observed.", ""]
    return "\n".join(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="artifacts/final-execution")
    args = parser.parse_args()
    directory = Path(args.directory)
    audit = json.loads((directory / "aws-role-audit.json").read_text(encoding="utf-8"))
    prerequisites = json.loads((directory / "aws-prerequisites.json").read_text(encoding="utf-8"))
    report = reconcile(audit, prerequisites)
    (directory / "readiness.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = markdown(report)
    (directory / "READINESS.md").write_text(summary, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(summary)
    print("Metadata collected; live deployment readiness is BLOCKED. Read READINESS.md for exact findings.")
