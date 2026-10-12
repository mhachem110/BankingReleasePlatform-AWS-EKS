"""Offline rendering and strict Kubernetes schema validation; never contacts EKS."""
import os
import subprocess
from pathlib import Path
from common import ROOT, run
from tests.test_helm import FIXTURE

if __name__ == "__main__":
    output = ROOT / "artifacts/application/chart"
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / "artifacts/application/cache/kubeconform"
    cache.mkdir(parents=True, exist_ok=True)
    for environment in ("dev", "stage", "uat", "prod"):
        namespace = "banking-" + environment
        args = ["helm", "template", "banking", ROOT / "helm/banking", "--namespace", namespace,
                "-f", ROOT / "helm/banking/environments" / (environment + ".yaml"), *FIXTURE]
        if environment == "dev":
            args += ["--set", "ingress.enabled=true", "--set", "ingress.approved=true",
                     "--set", "ingress.host=banking.example.test",
                     "--set", "ingress.certificateArn=arn:aws:acm:us-east-2:123456789012:certificate/example",
                     "--set", "ingress.subnets[0]=subnet-0123456789abcdef0",
                     "--set", "ingress.securityGroups[0]=sg-0123456789abcdef0",
                     "--set", "autoscaling.enabled=true"]
        rendered = output / (environment + ".yaml")
        rendered.write_text(run(args, capture=True), encoding="utf-8")
        run(["kubeconform", "-strict", "-summary", "-kubernetes-version", "1.36.0",
             "-cache", cache, rendered])
    run(["kubeconform", "-strict", "-summary", "-kubernetes-version", "1.36.0",
         "-cache", cache, *sorted((ROOT / "helm/banking/namespaces").glob("*.yaml")), ROOT / "iam/phase3/deployer-verification-rbac.yaml"])
