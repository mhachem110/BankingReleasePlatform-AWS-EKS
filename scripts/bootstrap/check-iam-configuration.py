"""Inspect the existing role/provider; never change IAM or grant permissions."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

POLICIES = {
    "CloudOpsTrackerBootstrap": "78c12672b53ed0365036c5f65ca2d1fd1151d8f51417cc468611c7fe8ad1d076",
    "BankingReleasePlatformState": "ec727a3eb94b54085034192764bd015c7aaf97a2be66b9de8df6294ab92f6150",
}
TRUST = {
    "GitHubOIDCRetailBootstrap": "834e6a92b1e204f695a9f0abe9e9dbba46e24377de7d844afbc05dd0827e23bb",
    "GitHubOIDCBankingBootstrap": "6405bb4174b22353c79094bb1f61b222213dfc2336c91f4fa1d89a04bcba0ce8",
}

def fingerprint(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def read(operation, *arguments):
    result = subprocess.run(["aws", "iam", operation, *arguments, "--output", "json"], capture_output=True, text=True)
    if result.returncode:
        # IAM read errors contain operation/authorization diagnostics, not tokens.
        print(f"IAM READ FAILED: {operation}: {result.stderr.strip()}", flush=True)
        return None
    return json.loads(result.stdout)

def main():
    account, arn = os.environ["AWS_EXPECTED_ACCOUNT_ID"], os.environ["ROLE_ARN"]
    role_name = "cloudbatch818-mahmoud-cloudops-bootstrap"
    problems = []
    provider = read("get-open-id-connect-provider", "--open-id-connect-provider-arn",
                    f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com")
    if provider is None:
        problems.append("Cannot inspect existing OIDC provider; see AWS diagnostic above.")
    else:
        spec = importlib.util.spec_from_file_location("oidc", Path(__file__).with_name("check-oidc-provider.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.verify(provider)
            print("Verified GitHub OIDC issuer and sts.amazonaws.com audience.")
        except RuntimeError as error:
            problems.append(str(error))
    role = read("get-role", "--role-name", role_name)
    if role is None:
        problems.append("Cannot inspect existing role/trust/boundary.")
    else:
        role = role["Role"]
        if role["Arn"] != arn:
            problems.append("Actual role ARN differs from the configured existing role.")
        if role.get("PermissionsBoundary"):
            problems.append("Live permissions boundary differs from the supplied no-boundary inventory.")
        trust = role["AssumeRolePolicyDocument"]["Statement"]
        for sid, expected in TRUST.items():
            statements = [s for s in trust if s.get("Sid") == sid]
            if len(statements) != 1 or fingerprint(statements[0]) != expected:
                problems.append(f"{sid} differs from the reviewed trust statement; preserve other statements.")
            else:
                print(f"Verified reviewed trust statement: {sid}.")
    names = read("list-role-policies", "--role-name", role_name)
    if names is None:
        problems.append("Cannot inspect inline-policy inventory.")
    else:
        print("Live inline policy names: " + ", ".join(names["PolicyNames"]))
        if set(names["PolicyNames"]) != set(POLICIES):
            problems.append("Inline-policy inventory differs from the reviewed original plus Banking addition.")
    attached = read("list-attached-role-policies", "--role-name", role_name)
    if attached is None:
        problems.append("Cannot inspect attached-policy inventory.")
    elif attached["AttachedPolicies"]:
        problems.append("Attached policies differ from the supplied empty inventory; no changes made.")
    for name, expected in POLICIES.items():
        policy = read("get-role-policy", "--role-name", role_name, "--policy-name", name)
        if policy is None:
            problems.append(f"Cannot inspect {name}; missing policy or IAM read authorization.")
        elif fingerprint(policy["PolicyDocument"]) != expected:
            problems.append(f"{name} does not match the complete reviewed policy; no policy was changed.")
        else:
            print(f"Verified complete reviewed inline policy unchanged: {name}.")
    if problems:
        print(json.dumps({"iam_blockers": problems}, indent=2))
        raise RuntimeError("IAM verification incomplete; do not initialize the bucket until resolved.")
    print("Verified existing role ARN, Retail/Banking trust, both reviewed inline policies, no boundary and no attached policies.")

if __name__ == "__main__":
    main()
