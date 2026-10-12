"""Dev rollout snapshots and authorized synthetic smoke around prod promotion."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from common import ROOT, json_run, save_json
from verify import verify


def summarize(deployments):
    result = {}
    for service in ("account", "payment"):
        item = deployments[service]
        replicas = item["spec"]["replicas"]
        image = item["spec"]["template"]["spec"]["containers"][0]["image"]
        if replicas < 1 or item["status"].get("readyReplicas") != replicas or "@sha256:" not in image:
            raise ValueError("Development is unhealthy or lacks an immutable image")
        result[service] = {"uid": item["metadata"]["uid"], "generation": item["metadata"]["generation"],
                           "replicas": replicas, "image": image}
    return result


def compare(before, after):
    for snapshot in (before, after):
        if snapshot.get("account") != "866934333672" or snapshot.get("region") != "us-east-2" or snapshot.get("cluster") != "banking-dev" or snapshot.get("namespace") != "banking-dev" or snapshot.get("verifiedFargateAndSmoke") is not True:
            raise ValueError("Require actual healthy dev snapshots from the approved cluster")
    if before["deployments"] != after["deployments"]:
        raise ValueError("Development deployments changed during production promotion")
    return {"developmentUnchangedAndHealthy": True, "beforeUTC": before["atUTC"], "afterUTC": after["atUTC"]}


def capture():
    identity = json_run(["aws", "sts", "get-caller-identity"])
    if identity.get("Account") != "866934333672":
        raise ValueError("Wrong AWS account")
    cluster = json_run(["aws", "eks", "describe-cluster", "--name", "banking-dev", "--region", "us-east-2"])["cluster"]
    context = json_run(["kubectl", "config", "view", "--minify", "-o", "json"])
    if cluster["status"] != "ACTIVE" or context["clusters"][0]["cluster"]["server"] != cluster["endpoint"]:
        raise ValueError("Current Kubernetes context must be the ACTIVE banking-dev cluster")
    deployments = {s: json_run(["kubectl", "-n", "banking-dev", "get", "deployment", "banking-"+s, "-o", "json"]) for s in ("account", "payment")}
    summary = summarize(deployments)
    manifest = {"images": {s: dict(zip(("repository", "digest"), d["image"].rsplit("@", 1))) for s, d in summary.items()}}
    verify("banking-dev", "banking", manifest)
    # Metadata is read-only; the approved smoke sends synthetic payment requests.
    from common import run
    import sys
    run([sys.executable, ROOT/"scripts/deploy/kube-smoke.py", "--namespace", "banking-dev"])
    return {"account": "866934333672", "region": "us-east-2", "cluster": "banking-dev", "namespace": "banking-dev",
            "atUTC": datetime.now(timezone.utc).isoformat(), "verifiedFargateAndSmoke": True,
            "deployments": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="Requires approved live API tests; sends synthetic payment requests")
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--output", default="artifacts/application/promotion-dev.json")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT/"artifacts"):
        raise ValueError("Evidence output must remain in ignored artifacts")
    if args.capture:
        if args.before or args.after:
            raise ValueError("Choose capture or comparison")
        save_json(output, capture())
    else:
        if not args.before or not args.after:
            parser.error("Supply --capture or both --before/--after")
        save_json(output, compare(json.loads(Path(args.before).read_text(encoding="utf-8")), json.loads(Path(args.after).read_text(encoding="utf-8"))))
