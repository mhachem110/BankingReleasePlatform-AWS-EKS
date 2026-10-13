"""Offline action/resource validation against the AWS service authorization snapshot.
This validates policy structure, not effective AWS authorization or all dependencies.
"""
import fnmatch
import json
from pathlib import Path
import re
from iam_contract import PROPOSALS, require
from provisioner_policies import generate


def validate(documents, metadata):
    checked = 0
    for name, document in documents.items():
        require(len(json.dumps(document, separators=(",", ":"))) <= 6144, "Managed-policy quota exceeded: " + name)
        for row in document["Statement"]:
            if row["Effect"] != "Allow":
                continue
            actions = row["Action"] if isinstance(row["Action"], list) else [row["Action"]]
            resources = row["Resource"] if isinstance(row["Resource"], list) else [row["Resource"]]
            for action in actions:
                service, operation = action.split(":")
                require("*" not in action, "No wildcard action grants in proposals")
                meta = next((a for a in metadata[service]["actions"] if a["Name"] == operation), None)
                require(meta is not None, "Unknown AWS action: " + action)
                if not meta.get("Resources"):
                    require("*" in resources, "AWS requires Resource * for " + action)
                elif "*" not in resources:
                    kinds = {r["Name"] for r in meta["Resources"]}
                    patterns = [re.sub(r"\$\{[^}]+\}", "*", arn) for r in metadata[service]["resources"] if r["Name"] in kinds for arn in r.get("ARNFormats", [])]
                    matches = any(fnmatch.fnmatchcase(resource, pattern) for resource in resources for pattern in patterns)
                    if not matches:
                        # Check type prefixes after fixing the ARN partition,
                        # Region/account. Identifier wildcards may cover several
                        # path components (for example EKS access entries).
                        for resource in resources:
                            fields = resource.split(":", 5)
                            if len(fields) != 6:
                                continue
                            for kind in metadata[service]["resources"]:
                                if kind["Name"] not in kinds:
                                    continue
                                for arn in kind.get("ARNFormats", []):
                                    arn = arn.replace("${Partition}", fields[1]).replace("${Region}", fields[3]).replace("${Account}", fields[4])
                                    prefix = re.sub(r"\$\{[^}]+\}", "*", arn).split("*")[0]
                                    matches |= resource.startswith(prefix) or ("*" in resource and prefix.startswith(resource.split("*")[0]))
                    # A log group's :* suffix includes its qualified stream ARNs.
                    matches |= service == "logs" and "log-stream" in kinds and any(":log-group:" in r and r.endswith(":*") for r in resources)
                    require(matches, "No supported resource type for " + action + " in " + name)
                checked += 1
    return {"aws_actions_checked": checked, "policies_checked": len(documents), "effective_authorization_proven": False}


if __name__ == "__main__":
    source = PROPOSALS.parents[1] / "provisioning/service-authorization-reference.json"
    print(json.dumps(validate(generate(), json.loads(source.read_text())), indent=2))
