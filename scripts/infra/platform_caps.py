"""Review exact administrator-published routine managed session caps."""
import json
import os
from pathlib import Path
import re
from iam_contract import ACCOUNT, digest, require


def review(env):
    rows = json.loads(env.get("PLATFORM_POLICY_REVIEW_JSON") or "[]")
    require(isinstance(rows, list) and len(rows) == 3, "Review all three exact platform cap documents")
    require({r.get("arn") for r in rows} == {f"arn:aws:iam::{ACCOUNT}:policy/BankingTerraformProvisioner-Platform-{i}" for i in (1, 2, 3)}, "Wrong managed platform cap inventory")
    require(all(re.fullmatch(r"[a-f0-9]{64}", r.get("sha256", "")) for r in rows), "Pin every approved live cap hash")
    return sorted(rows, key=lambda r: r["arn"])


def verify(env, call):
    from network_seed import interface
    from guard import configuration
    from provisioner_policies import generate
    seed = interface(env)
    values = configuration(env)
    expected = generate(key=values["kms_key_arn"], vpc=seed["vpc_id"], sg=seed["default_security_group_id"])
    docs = {}
    for row in review(env):
        meta = call("iam", "get-policy", "--policy-arn", row["arn"])["Policy"]
        version = call("iam", "get-policy-version", "--policy-arn", row["arn"], "--version-id", meta["DefaultVersionId"])["PolicyVersion"]
        require(digest(version["Document"]) == row["sha256"], "Live platform cap differs from approved document")
        name = row["arn"].split("/")[-1] + ".json"
        source = json.loads(json.dumps(expected[name]).replace(f"arn:aws:iam::{ACCOUNT}:role/__APPROVED_OPERATOR_ROLE__", values["operator_role_arn"]))
        require(digest(version["Document"]) == digest(source), "Live platform cap differs from the finalized bounded source/input proposal")
        require("__" not in json.dumps(version["Document"]), "Resolve every cap identifier before live planning")
        docs[row["arn"]] = {"sha256": row["sha256"], "version": meta["DefaultVersionId"], "document": version["Document"]}
    sg = f"arn:aws:ec2:us-east-2:{ACCOUNT}:security-group/{seed['default_security_group_id']}"
    statements = [s for d in docs.values() for s in d["document"]["Statement"]]
    principals = {s["Condition"]["StringEquals"]["eks:principalArn"] for s in statements if s.get("Action") == "eks:CreateAccessEntry"}
    require(principals == {values[k] for k in ("operator_role_arn", "deployer_role_arn", "prod_deployer_role_arn")}, "Platform cap access principals must match the exact Terraform inputs")
    require(any(s.get("Sid") == "ExactNewVpcDefaultGroupTagging" and s.get("Resource") == sg for s in statements), "Platform cap must name the verified seed default group exactly")
    return docs


if __name__ == "__main__":
    from preflight import aws
    Path("platform-policy-review.json").write_text(json.dumps(verify(os.environ, aws), indent=2))
