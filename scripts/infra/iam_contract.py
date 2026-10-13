"""Fixed IAM prerequisite contract. No AWS writes or permission changes."""
import hashlib
import json
from pathlib import Path

ACCOUNT = "866934333672"
REGION = "us-east-2"
BOOTSTRAP = f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-cloudops-bootstrap"
BOUNDARY = f"arn:aws:iam::{ACCOUNT}:policy/cloudbatch818-mahmoud-banking-service-boundary"
BUCKET = f"mhachem-banking-tfstate-{ACCOUNT}"
STATE_KEY = "banking-release-platform/shared/iam-prerequisites/terraform.tfstate"
ROLE_NAMES = {"cluster": "cloudbatch818-mahmoud-banking-eks-cluster", "fargate": "cloudbatch818-mahmoud-banking-fargate-execution", "flow": "cloudbatch818-mahmoud-banking-flow-logs"}
ROLE_ARNS = {key: f"arn:aws:iam::{ACCOUNT}:role/{name}" for key, name in ROLE_NAMES.items()}
ATTACHMENTS = {"cluster": "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy", "fargate": "arn:aws:iam::aws:policy/AmazonEKSFargatePodExecutionRolePolicy"}
TAGS = {"Project": "BankingReleasePlatform", "Environment": "shared", "ManagedBy": "Terraform", "Owner": "MahmoudHachem", "Purpose": "CloudEngineerTraining", "Component": "service-iam"}
PROPOSALS = Path(__file__).resolve().parents[2] / "iam/phase3/proposed"


def canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(document):
    return hashlib.sha256(canonical(document).encode()).hexdigest()


def trust(key):
    return json.loads((PROPOSALS / (ROLE_NAMES[key] + "-trust.json")).read_text())


def flow_policy():
    return json.loads((PROPOSALS / "BankingFlowLogs.json").read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_live_roles(call, boundary_hash):
    """Read actual role/policy inventories; no simulation is treated as apply proof."""
    for key, name in ROLE_NAMES.items():
        response = call("iam", "get-role", "--role-name", name)
        role = response.get("Role", {})
        require(role.get("Arn") == ROLE_ARNS[key] and role.get("Path") == "/", "Wrong role identity/path: " + name)
        require(role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == BOUNDARY, "Wrong/missing boundary: " + name)
        require(role.get("AssumeRolePolicyDocument") == trust(key), "Trust drift: " + name)
        tags = {t["Key"]: t["Value"] for t in role.get("Tags", [])}
        require(all(tags.get(k) == v for k, v in dict(TAGS, Name=name).items()), "Tag drift: " + name)
        attached = call("iam", "list-attached-role-policies", "--role-name", name)
        require({p["PolicyArn"] for p in attached.get("AttachedPolicies", [])} == ({ATTACHMENTS[key]} if key in ATTACHMENTS else set()), "Managed policy inventory drift: " + name)
        inline = call("iam", "list-role-policies", "--role-name", name)
        require(set(inline.get("PolicyNames", [])) == ({"BankingFlowLogs"} if key == "flow" else set()), "Inline policy inventory drift: " + name)
        if key == "flow":
            actual = call("iam", "get-role-policy", "--role-name", name, "--policy-name", "BankingFlowLogs")
            require(actual.get("PolicyDocument") == flow_policy(), "Flow log policy drift")
    meta = call("iam", "get-policy", "--policy-arn", BOUNDARY)
    version = call("iam", "get-policy-version", "--policy-arn", BOUNDARY, "--version-id", meta["Policy"]["DefaultVersionId"])
    require(digest(version["PolicyVersion"]["Document"]) == boundary_hash, "Boundary changed after review")
    return {"verified": True, "service_roles": ROLE_ARNS, "boundarySha256": boundary_hash}
