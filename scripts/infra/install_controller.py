"""Install the checksum-pinned AWS Load Balancer Controller with exact IRSA."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ACCOUNT = "866934333672"
REGION = "us-east-2"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/cloudbatch818-mahmoud-banking-alb-controller"
CHART_URL = "https://aws.github.io/eks-charts/aws-load-balancer-controller-3.6.0.tgz"
CHART_SHA256 = "ee0403fcd713d6f1d28b1ff17d0d6d47e011cc4dd727a0aed0d95ae46897226a"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(*args, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True,
                          check=True, timeout=900).stdout


def install():
    runtime = json.loads(os.environ.get("RUNTIME_INTERFACE_JSON") or "{}")
    platform = json.loads(os.environ.get("PLATFORM_INTERFACE_JSON") or "{}")
    require(runtime.get("verified") is True and platform.get("verified") is True,
            "Applied platform and runtime interfaces are required")
    require(runtime.get("outputs", {}).get("dev", {}).get("controller_role_arn") == ROLE and
            runtime.get("outputs", {}).get("prod", {}).get("controller_role_arn") == ROLE,
            "The exact dedicated controller role must be verified for both namespaces")
    outputs = platform["outputs"]
    require(outputs["cluster_name"]["value"] == "banking-dev" and
            os.environ.get("AWS_ACCOUNT_ID") == ACCOUNT and os.environ.get("AWS_REGION") == REGION,
            "Wrong cluster/account/Region")
    sa = {"apiVersion": "v1", "kind": "ServiceAccount",
          "metadata": {"name": "aws-load-balancer-controller", "namespace": "kube-system",
                       "annotations": {"eks.amazonaws.com/role-arn": ROLE},
                       "labels": {"app.kubernetes.io/name": "aws-load-balancer-controller"}}}
    with tempfile.TemporaryDirectory(prefix="banking-lbc-") as folder:
        chart = Path(folder) / "aws-load-balancer-controller-3.6.0.tgz"
        chart.write_bytes(urllib.request.urlopen(CHART_URL, timeout=60).read())
        require(hashlib.sha256(chart.read_bytes()).hexdigest() == CHART_SHA256,
                "Controller chart does not match the reviewed upstream digest")
        run("kubectl", "apply", "--server-side", "-f", "-", input=json.dumps(sa))
        run("helm", "upgrade", "--install", "aws-load-balancer-controller", str(chart),
            "--namespace", "kube-system", "--atomic", "--wait", "--timeout", "10m",
            "--history-max", "10", "--set-string", "clusterName=banking-dev",
            "--set-string", "region=" + REGION,
            "--set-string", "vpcId=" + outputs["vpc_id"]["value"],
            "--set", "serviceAccount.create=false",
            "--set-string", "serviceAccount.name=aws-load-balancer-controller",
            "--set", "replicaCount=2", "--set", "enableServiceMutatorWebhook=false")
    run("kubectl", "rollout", "status", "deployment/aws-load-balancer-controller",
        "--namespace", "kube-system", "--timeout=10m")
    live = json.loads(run("kubectl", "get", "serviceaccount", "aws-load-balancer-controller",
                          "--namespace", "kube-system", "-o", "json"))
    require(live["metadata"]["annotations"]["eks.amazonaws.com/role-arn"] == ROLE,
            "Controller service account lost its dedicated IRSA annotation")
    deployment = json.loads(run("kubectl", "get", "deployment", "aws-load-balancer-controller",
                                "--namespace", "kube-system", "-o", "json"))
    require(deployment["status"].get("availableReplicas", 0) >= 2,
            "Two controller replicas are not available")
    Path("controller-verification.json").write_text(json.dumps({
        "chartVersion": "3.6.0", "chartSha256": CHART_SHA256,
        "roleArn": ROLE, "cluster": "banking-dev", "availableReplicas": deployment["status"]["availableReplicas"],
        "verified": True}, indent=2))


if __name__ == "__main__":
    install()
