"""Read-only provider verification, run only after authorized GitHub OIDC login."""
import json
import os
import subprocess


def verify(provider):
    if provider.get("Url", "").removeprefix("https://") != "token.actions.githubusercontent.com":
        raise RuntimeError("GitHub OIDC provider URL differs from the reviewed issuer.")
    if "sts.amazonaws.com" not in provider.get("ClientIDList", []):
        raise RuntimeError("GitHub OIDC provider must include audience sts.amazonaws.com.")


def main():
    arn = f"arn:aws:iam::{os.environ['AWS_EXPECTED_ACCOUNT_ID']}:oidc-provider/token.actions.githubusercontent.com"
    result = subprocess.run(["aws", "iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", arn, "--output", "json"],
                            capture_output=True, text=True, check=True)
    verify(json.loads(result.stdout))
    print("Verified GitHub provider URL and sts.amazonaws.com audience through authorized read-only IAM access.")


if __name__ == "__main__":
    main()
