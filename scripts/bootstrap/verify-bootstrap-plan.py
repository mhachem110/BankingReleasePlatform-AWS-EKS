"""Fail closed if a Phase 2 verification plan proposes managed resource changes."""
import json
import subprocess
import sys


def verify(plan):
    unexpected = [change["address"] for change in plan.get("resource_changes", [])
                  if change.get("mode") == "managed" and change["change"]["actions"] != ["no-op"]]
    if unexpected:
        raise RuntimeError("Unexpected managed resource changes; do not apply: " + ", ".join(unexpected))
    print("Verified Phase 2 plan: zero managed resource changes. Output-only changes require no resource apply.")


if __name__ == "__main__":
    result = subprocess.run(["terraform", "-chdir=" + sys.argv[1], "show", "-json", sys.argv[2]],
                            check=True, capture_output=True, text=True)
    plan = json.loads(result.stdout)
    verify(plan)
    # Publish only known non-secret lifecycle values, never the full plan/state.
    for change in plan.get("resource_changes", []):
        if change.get("address") == "module.state_bucket.aws_s3_bucket_lifecycle_configuration.state":
            print(json.dumps({"lifecycle_actions": change["change"]["actions"],
                              "before_rule": change["change"]["before"]["rule"],
                              "after_rule": change["change"]["after"]["rule"]}, indent=2))
