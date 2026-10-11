"""Read-only diagnosis of the failed import plan; never apply or publish full state.

Replay the exact failed module in a temporary root using the existing backend.
Only lifecycle API/state/plan values are reported; saved plans stay temporary.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BASELINE = "f498e6a8ca0a5ee341db48e1ca047177a42d398d"
ADDRESS = "module.state_bucket.aws_s3_bucket_lifecycle_configuration.state"


def filter_only_difference(change):
    if change["actions"] != ["update"]:
        raise RuntimeError("Original lifecycle diagnosis did not reproduce the expected update; investigate before proceeding.")
    before, after = json.loads(json.dumps(change["before"])), json.loads(json.dumps(change["after"]))
    if len(before["rule"]) != 1 or len(after["rule"]) != 1:
        raise RuntimeError("Unexpected rule count in lifecycle diagnosis.")
    old_filter = before["rule"][0].pop("filter")
    new_filter = after["rule"][0].pop("filter")
    if before != after or old_filter != [] or new_filter != [{"and": [], "object_size_greater_than": None,
            "object_size_less_than": None, "prefix": "", "tag": []}]:
        raise RuntimeError("Original lifecycle plan contains more than the empty-filter representation difference.")
    return {"actions": change["actions"], "before_rule": change["before"]["rule"][0],
            "after_rule": change["after"]["rule"][0], "only_difference": "filter [] -> empty-prefix filter"}


def diagnose(bucket, account, region, backend, output):
    def run(command):
        # State is captured in memory. Never print stdout from state pull or
        # terraform show -json, including when a subprocess fails.
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("Lifecycle diagnostic command failed: " + command[0] + " (output withheld; no state exposed).")
        return result.stdout

    api = json.loads(run(["aws", "s3api", "get-bucket-lifecycle-configuration", "--bucket", bucket,
                         "--expected-bucket-owner", account, "--region", region, "--output", "json"]))
    state = json.loads(run(["terraform", "-chdir=infra/bootstrap", "state", "pull"]))
    resources = [r for r in state["resources"] if r.get("module") == "module.state_bucket"
                 and r["type"] == "aws_s3_bucket_lifecycle_configuration" and r["name"] == "state"]
    if len(resources) != 1 or len(resources[0]["instances"]) != 1:
        raise RuntimeError("Expected exactly one imported lifecycle identity.")
    attributes = resources[0]["instances"][0]["attributes"]
    if attributes["id"] != bucket:
        raise RuntimeError("Imported lifecycle identity does not match the approved bucket.")
    with tempfile.TemporaryDirectory(prefix="banking-lifecycle-diagnosis-", dir=os.environ["RUNNER_TEMP"]) as temporary:
        root = Path(temporary) / "infra/bootstrap"
        module = Path(temporary) / "infra/modules/state-bucket"
        root.mkdir(parents=True)
        module.mkdir(parents=True)
        for filename in ["main.tf", ".terraform.lock.hcl"]:
            shutil.copyfile(Path("infra/bootstrap") / filename, root / filename)
        (module / "main.tf").write_text(run(["git", "show", BASELINE + ":infra/modules/state-bucket/main.tf"]), encoding="utf-8")
        command = ["terraform", "-chdir=" + str(root)]
        run(command + ["init", "-input=false", "-lockfile=readonly", "-backend-config=" + str(Path(backend).resolve())])
        if run(command + ["workspace", "show"]).strip() != "default":
            raise RuntimeError("Lifecycle diagnosis requires the default workspace.")
        plan_path = str(Path(temporary) / "original.tfplan")
        run(command + ["plan", "-input=false", "-lock-timeout=5m", "-out=" + plan_path])
        plan = json.loads(run(command + ["show", "-json", plan_path]))
        changed = [c for c in plan.get("resource_changes", []) if c.get("mode") == "managed"
                   and c["change"]["actions"] != ["no-op"]]
        if len(changed) != 1 or changed[0]["address"] != ADDRESS:
            raise RuntimeError("Original plan contains unexpected managed-resource changes; no changes applied.")
        difference = filter_only_difference(changed[0]["change"])
    report = {"baseline_commit": BASELINE, "provider": "hashicorp/aws 6.68.0", "api_lifecycle": api,
              "imported_state_rule": attributes["rule"], "original_plan": difference,
              "conclusion": "API Filter={} imports as absent filter; HCL filter {} plans prefix=empty string. Retention is unchanged."}
    Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ["bucket", "account", "region", "backend", "output"]:
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    diagnose(args.bucket, args.account, args.region, args.backend, args.output)
