"""One-command validation without AWS credentials or an EKS cluster."""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT, run, save_json

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skip-install", action="store_true")
    p.add_argument("--reuse-images", action="store_true")
    args = p.parse_args()
    output = ROOT / "artifacts/application"
    output.mkdir(parents=True, exist_ok=True)
    tools = output / "tools"
    if not args.skip_install:
        run([sys.executable, ROOT / "scripts/deploy/install-tools.py", "--directory", tools])
    os.environ["PATH"] = str(tools) + os.pathsep + os.environ["PATH"]
    commit = run(["git", "rev-parse", "HEAD"], capture=True, cwd=ROOT)
    commands = [
        ("restore", ["dotnet","restore","BankingReleasePlatform.sln","--locked-mode"]),
        ("build", ["dotnet","build","BankingReleasePlatform.sln","-c","Release","--no-restore"]),
        ("api-tests", ["dotnet","test","BankingReleasePlatform.sln","-c","Release","--no-build",
                       "--logger","trx","--results-directory",str(output/"test-results")]),
        ("helm-and-deployment-tests", [sys.executable,"-m","unittest","discover","-s","scripts/deploy/tests","-v"]),
        ("kubernetes-schemas", [sys.executable,"scripts/deploy/validate-chart.py"]),
        ("actionlint", ["actionlint", "-config-file", "scripts/deploy/actionlint.yaml", *[f".github/workflows/{name}" for name in
                       ["app-ci.yml","app-validation.yml","app-publish.yml","app-deploy.yml"]]]),
    ]
    if not args.reuse_images:
        commands.append(("docker-build", [sys.executable,"scripts/deploy/build.py","--commit",commit]))
    commands += [
        ("container-integration", [sys.executable,"scripts/deploy/docker-smoke.py"]),
        ("trivy", [sys.executable,"scripts/deploy/scan.py"]),
        ("live-checkpoint", [sys.executable,"scripts/deploy/demonstrate.py"]),
    ]
    results=[]
    for name, command in commands:
        print("RUN: " + name, flush=True)
        start=time.monotonic()
        result=subprocess.run([str(c) for c in command], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (output / (name + ".log")).write_text(result.stdout, encoding="utf-8")
        results.append({"check":name,"exitCode":result.returncode,
                        "seconds":round(time.monotonic()-start,2)})
        save_json(output / "offline-result.json", {"sourceCommit":commit,
            "atUTC":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "checks":results,"liveDeployment":"pending"})
        if result.returncode:
            print(result.stdout)
            sys.exit(result.returncode)
        print("PASS: " + name, flush=True)
    print("Offline validation passed. Live EKS deployment remains pending.")
