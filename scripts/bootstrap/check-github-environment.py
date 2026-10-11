"""Fail closed unless the existing bootstrap environment requires review and only dev."""
import json
import os
import urllib.request

def get(path):
    request = urllib.request.Request("https://api.github.com/" + path, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json",
        "User-Agent": "BankingReleasePlatform-EnvironmentCheck",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)

def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    path = f"repos/{repo}/environments/bootstrap"
    env = get(path)
    review = next((r for r in env.get("protection_rules", []) if r["type"] == "required_reviewers"), None)
    if not review or not review.get("reviewers"):
        raise RuntimeError("bootstrap must have a required reviewer before AWS operations.")
    if any(r.get("type") != "User" or r.get("reviewer", {}).get("id") != 150286776 for r in review["reviewers"]):
        raise RuntimeError("Only the currently verified cloud owner may approve bootstrap; team changes need review.")
    restrictions = env.get("deployment_branch_policy") or {}
    if not restrictions.get("custom_branch_policies"):
        raise RuntimeError("bootstrap must use a custom dev-only deployment branch policy.")
    policies = get(path + "/deployment-branch-policies?per_page=100")
    branches = policies.get("branch_policies", [])
    if policies.get("total_count") != 1 or len(branches) != 1 or branches[0]["name"] != "dev" or branches[0].get("type", "branch") != "branch":
        raise RuntimeError("bootstrap must allow only the dev branch.")
    if env.get("can_admins_bypass") is not False:
        raise RuntimeError("Disable administrator bypass for bootstrap.")
    print("Verified existing bootstrap reviewers, dev-only branch policy, and disabled admin bypass.")

if __name__ == "__main__":
    main()
