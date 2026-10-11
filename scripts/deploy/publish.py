"""Publish exactly the scanned archives; the repositories must already exist."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from common import ROOT, config, json_run, required, run, save_json, validate_manifest

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="artifacts/application/scanned")
    p.add_argument("--output", default="release/release.json")
    args = p.parse_args()
    cfg = config("dev", publishing=True)
    identity = json_run(["aws", "sts", "get-caller-identity"])
    if identity["Account"] != cfg["account"]:
        raise ValueError("Unexpected AWS identity")
    directory = Path(args.input)
    records = json.loads((directory / "scanned.json").read_text())
    source = required("GITHUB_SHA")
    run_id = required("GITHUB_RUN_ID")
    manifest = {"version": 1, "sourceCommit": source, "publishRunId": run_id, "images": {}}
    # Verify both archives before allowing the first push.
    for service in ("account", "payment"):
        record = records[service]
        with (directory / (service + ".tar")).open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != record["archiveSha256"]:
                raise ValueError("Scanned archive changed")
        if record["sourceCommit"] != source:
            raise ValueError("Scanned image source does not match reviewed commit")
        run(["docker", "load", "-i", directory / (service + ".tar")])
        image = json_run(["docker", "image", "inspect", "banking-ci-" + service])[0]
        if image["Id"] != record["imageId"] or image["Config"]["Labels"]["org.opencontainers.image.revision"] != source:
            raise ValueError("Loaded image differs from scanned image")
        name = cfg["repos"][service].split("/", 1)[1]
        repo = json_run(["aws", "ecr", "describe-repositories", "--repository-names", name,
                         "--region", cfg["region"]])["repositories"][0]
        if repo["repositoryUri"] != cfg["repos"][service] or repo["imageTagMutability"] != "IMMUTABLE":
            raise ValueError("ECR repository must exist and enforce immutable tags")
    registry = cfg["repos"]["account"].split("/", 1)[0]
    password = run(["aws", "ecr", "get-login-password", "--region", cfg["region"]], capture=True)
    run(["docker", "login", "--username", "AWS", "--password-stdin", registry], input=password)
    try:
        for service in ("account", "payment"):
            tag = cfg["repos"][service] + ":" + source + "-" + run_id
            run(["docker", "tag", "banking-ci-" + service, tag])
            run(["docker", "push", tag])
            digests = json_run(["docker", "image", "inspect", tag])[0]["RepoDigests"]
            digest = next(d.split("@", 1)[1] for d in digests if d.startswith(cfg["repos"][service] + "@"))
            remote = json_run(["aws", "ecr", "describe-images", "--region", cfg["region"],
                "--repository-name", cfg["repos"][service].split("/", 1)[1],
                "--image-ids", "imageTag=" + source + "-" + run_id])["imageDetails"][0]["imageDigest"]
            if remote != digest:
                raise ValueError("Published and remote digests differ")
            manifest["images"][service] = {"repository": cfg["repos"][service], "digest": digest}
        validate_manifest(manifest, cfg["repos"])
        save_json(args.output, manifest)
        print("Published the scanned image pair by immutable digest.")
    finally:
        run(["docker", "logout", registry], check=False)
