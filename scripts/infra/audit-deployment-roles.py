"""Read-only collection of full IAM documents. Never assumes a deployment role.

Policy inspection is not effective authorization simulation. SCP visibility, the
current STS session policy and live OIDC tokens may remain unavailable.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

ACCOUNT = "866934333672"
REGION = "us-east-2"
PREFIX = "repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979:environment:"
ROLES = {env: "cloudbatch818-mahmoud-cloudops-deploy-" + env for env in ("dev", "prod")}


def read(service, operation, *args, profile=None):
    # The explicit operation list prevents accidental mutation as this grows.
    approved = {"get-caller-identity", "get-role", "list-role-policies", "get-role-policy",
                "list-attached-role-policies", "get-policy", "get-policy-version",
                "list-policies-for-target", "list-parents", "describe-policy"}
    if operation not in approved:
        raise ValueError("Operation is outside the read-only audit")
    command = ["aws", service, operation, *args, "--region", REGION,
               "--output", "json", "--no-cli-pager"]
    if profile:
        command += ["--profile", profile]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        return {"inspectionError": result.stderr.strip(), "operation": service + ":" + operation}
    return json.loads(result.stdout)


def statements(document):
    values = document.get("Statement", [])
    return values if isinstance(values, list) else [values]


def review_role(role, inline, managed, environment):
    subject = PREFIX + environment
    trust = statements(role.get("AssumeRolePolicyDocument", {}))
    matched = any(s.get("Effect") == "Allow" and s.get("Action") == "sts:AssumeRoleWithWebIdentity"
                  and s.get("Principal", {}).get("Federated") == f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
                  and s.get("Condition", {}).get("StringEquals", {}) == {
                      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                      "token.actions.githubusercontent.com:sub": subject} for s in trust)
    findings = []
    documents = [v.get("PolicyDocument", {}) for v in inline.values()]
    documents += [v.get("effectiveVersion", {}).get("PolicyVersion", {}).get("Document", {}) for v in managed.values()]
    approved = {"sts:GetCallerIdentity", "ecr:GetAuthorizationToken", "ecr:DescribeRepositories", "ecr:DescribeImages",
                "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "eks:DescribeCluster"}
    if environment == "dev":
        approved |= {"ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"}
    repositories = {f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/banking-dev-{s}" for s in ("account", "payment")}
    cluster = f"arn:aws:eks:{REGION}:{ACCOUNT}:cluster/banking-dev"
    for document in documents:
        for s in statements(document):
            if s.get("Effect") != "Allow":
                continue
            actions = s.get("Action", [])
            actions = [actions] if isinstance(actions, str) else actions
            # Conservative review flag; conditions require administrator interpretation.
            excessive = [a for a in actions if a not in approved]
            resources = s.get("Resource", [])
            resources = {resources} if isinstance(resources, str) else set(resources)
            broad = any((a.startswith("ecr:") and a != "ecr:GetAuthorizationToken" and not resources <= repositories)
                        or (a == "eks:DescribeCluster" and resources != {cluster}) for a in actions)
            if excessive or broad or "NotAction" in s or "NotResource" in s:
                findings.append({"reason": "Permission exceeds image publication/pull and cluster discovery",
                                 "actions": excessive, "statement": s})
    expected = {ROLES[environment] + "-" + suffix for suffix in ("core", "iam", "services")}
    actual = {v.get("metadata", {}).get("Policy", {}).get("PolicyName") for v in managed.values()}
    complete = not any("inspectionError" in json.dumps(v) for v in [role, inline, managed])
    return {"expectedSubject": subject, "exactBankingTrustFound": matched,
            "originalManagedPolicyNamesPresent": expected <= actual,
            "originalTrustPreservation": "Cannot prove without the original full trust baseline; all current statements are retained in this audit",
            "permissionsBoundary": role.get("PermissionsBoundary"), "reviewFindings": findings,
            "documentsComplete": complete,
            "bankingLeastPrivilegeEstablished": False,
            "verdict": "BLOCKED: administrator effective-policy/deny review and actual protected OIDC/RBAC tests required"}


def collect(profile=None, call=read):
    def aws(service, operation, *args):
        return call(service, operation, *args, profile=profile)
    identity = aws("sts", "get-caller-identity")
    if identity.get("Account") != ACCOUNT:
        raise ValueError("Read-only access is unavailable or belongs to the wrong account: " + json.dumps(identity))
    report = {"observedAt": datetime.now(timezone.utc).isoformat(), "account": ACCOUNT,
              "region": REGION, "identity": identity, "readOnly": True, "roles": {}}
    for env, name in ROLES.items():
        role_response = aws("iam", "get-role", "--role-name", name)
        role = role_response.get("Role", role_response)
        names = aws("iam", "list-role-policies", "--role-name", name)
        inline = {n: aws("iam", "get-role-policy", "--role-name", name, "--policy-name", n)
                  for n in names.get("PolicyNames", [])}
        attached = aws("iam", "list-attached-role-policies", "--role-name", name)
        managed = {}
        arns = {p["PolicyArn"] for p in attached.get("AttachedPolicies", [])}
        boundary = role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
        if boundary:
            arns.add(boundary)
        for arn in sorted(arns):
            metadata = aws("iam", "get-policy", "--policy-arn", arn)
            version = metadata.get("Policy", {}).get("DefaultVersionId")
            managed[arn] = {"metadata": metadata, "effectiveVersion": aws("iam", "get-policy-version", "--policy-arn", arn, "--version-id", version) if version else {"inspectionError": "Default policy version could not be read"}}
        review = review_role(role, inline, managed, env)
        if "inspectionError" in names or "inspectionError" in attached:
            review["documentsComplete"] = False
        report["roles"][env] = {"role": role, "inlinePolicies": inline, "attachedPolicies": attached,
                               "managedPolicies": managed, "inlineInventory": names,
                               "review": review}
    report["prerequisiteRoles"] = {}
    for name in [
        "cloudbatch818-mahmoud-banking-eks-cluster", "cloudbatch818-mahmoud-banking-fargate-execution",
        "cloudbatch818-mahmoud-banking-flow-logs", "AWSServiceRoleForAmazonEKS", "AWSServiceRoleForAmazonEKSForFargate"]:
        response = aws("iam", "get-role", "--role-name", name)
        names = aws("iam", "list-role-policies", "--role-name", name)
        attached = aws("iam", "list-attached-role-policies", "--role-name", name)
        managed = {}
        arns = {p["PolicyArn"] for p in attached.get("AttachedPolicies", [])}
        boundary = response.get("Role", {}).get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
        if boundary:
            arns.add(boundary)
        for arn in sorted(arns):
            metadata = aws("iam", "get-policy", "--policy-arn", arn)
            version = metadata.get("Policy", {}).get("DefaultVersionId")
            managed[arn] = {"metadata": metadata, "effectiveVersion": aws("iam", "get-policy-version", "--policy-arn", arn, "--version-id", version) if version else {"inspectionError": "Default policy version could not be read"}}
        report["prerequisiteRoles"][name] = {"role": response, "inlineInventory": names, "attachedPolicies": attached,
            "inlinePolicies": {n: aws("iam", "get-role-policy", "--role-name", name, "--policy-name", n) for n in names.get("PolicyNames", [])}, "managedPolicies": managed}
    report["organizationDenies"] = []
    target = ACCOUNT
    for _ in range(10):
        for kind in ("SERVICE_CONTROL_POLICY", "RESOURCE_CONTROL_POLICY"):
            policies = aws("organizations", "list-policies-for-target", "--target-id", target, "--filter", kind)
            report["organizationDenies"].append({"target": target, "type": kind, "inventory": policies,
                "documents": [aws("organizations", "describe-policy", "--policy-id", p["Id"]) for p in policies.get("Policies", [])]})
        parents = aws("organizations", "list-parents", "--child-id", target)
        if not parents.get("Parents"):
            report["organizationParentsInspection"] = parents
            break
        target = parents["Parents"][0]["Id"]
    report["sessionRestrictions"] = "STS does not expose the active session policy through GetCallerIdentity; workflow supplies a reviewed restrictive cap. Inspect any login/session constraints separately."
    report["liveOidcTokenVerified"] = False
    return report


def public_review(report):
    """Keep full effective policies and trust documents out of public job logs."""
    result = {}
    for env, item in report["roles"].items():
        review = item["review"]
        result[env] = {k: review[k] for k in (
            "exactBankingTrustFound", "originalManagedPolicyNamesPresent",
            "documentsComplete", "bankingLeastPrivilegeEstablished", "verdict")}
        result[env]["broadPermissionFindingCount"] = len(review["reviewFindings"])
        result[env]["originalTrustPreservation"] = review["originalTrustPreservation"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile")
    parser.add_argument("--output", default="artifacts/final-execution/aws-role-audit.json")
    args = parser.parse_args()
    report = collect(args.profile)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Full read-only role/policy evidence saved; no IAM changes or resource provisioning.")
    print(json.dumps(public_review(report), indent=2))
