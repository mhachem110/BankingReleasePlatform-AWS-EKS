import shutil
import subprocess
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[3]
HELM = shutil.which("helm")
FIXTURE = ["--set", "images.account.repository=123456789012.dkr.ecr.us-east-2.amazonaws.com/banking-dev-account",
           "--set", "images.payment.repository=123456789012.dkr.ecr.us-east-2.amazonaws.com/banking-dev-payment",
           "--set", "images.account.digest=sha256:" + "a" * 64,
           "--set", "images.payment.digest=sha256:" + "b" * 64]


def render(*extra):
    if not HELM:
        raise RuntimeError("Helm is required; install the documented pinned version before testing.")
    result = subprocess.run([HELM, "template", "banking", str(ROOT / "helm/banking"), "--namespace", "banking-dev", *FIXTURE, *extra], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr)
    return [item for item in yaml.safe_load_all(result.stdout) if item]


class HelmTests(unittest.TestCase):
    def test_lint(self):
        subprocess.run([HELM, "lint", str(ROOT / "helm/banking"), "--strict", *FIXTURE], check=True, capture_output=True)

    def test_api_contract_and_security(self):
        workloads = [item for item in render() if item["kind"] == "Deployment"]
        self.assertEqual(len(workloads), 2)
        for workload in workloads:
            pod = workload["spec"]["template"]["spec"]
            self.assertFalse(pod["automountServiceAccountToken"])
            container = pod["containers"][0]
            self.assertIn("@sha256:", container["image"])
            self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            for probe in ["startupProbe", "readinessProbe", "livenessProbe"]:
                self.assertEqual(container[probe]["httpGet"]["path"], "/health")
                self.assertEqual(container[probe]["httpGet"]["port"], "http")
            self.assertEqual(container["ports"][0]["containerPort"], 8080)
            self.assertIn("requests", container["resources"])
        payment = next(item for item in workloads if item["metadata"]["name"] == "banking-payment")
        env = payment["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertIn({"name": "AccountApi__BaseUrl", "value": "http://banking-account:8080/"}, env)

    def test_no_paid_ingress_by_default(self):
        self.assertNotIn("Ingress", [item["kind"] for item in render()])
        self.assertTrue(all(item["spec"]["type"] == "ClusterIP" for item in render() if item["kind"] == "Service"))

    def test_hpa_render(self):
        resources = render("--set", "autoscaling.enabled=true")
        self.assertEqual(len([item for item in resources if item["kind"] == "HorizontalPodAutoscaler"]), 2)
        self.assertTrue(all("replicas" not in item["spec"] for item in resources if item["kind"] == "Deployment"))

    def test_latest_and_missing_digest_rejected(self):
        for override in ["images.account.digest=latest", "images.account.digest=", "replicaCount=1"]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                render("--set", override)

    def test_payment_only_calls_account(self):
        policies = {item["metadata"]["name"]: item for item in render() if item["kind"] == "NetworkPolicy"}
        self.assertEqual(policies["banking-payment-ingress"]["spec"]["ingress"], [])
        self.assertEqual(policies["banking-account-ingress"]["spec"]["ingress"][0]["from"], [{"podSelector": {"matchLabels": {"app": "banking-payment"}}}])

    def test_ingress_requires_approved_configuration(self):
        with self.assertRaises(ValueError):
            render("--set", "ingress.enabled=true")
        resources = render("--set", "ingress.enabled=true", "--set", "ingressSourceCidrs[0]=10.70.0.0/24",
                           "--set", "ingress.host=banking.example.test", "--set", "ingress.certificateArn=arn:aws:acm:us-east-2:123456789012:certificate/test")
        ingress = next(item for item in resources if item["kind"] == "Ingress")
        self.assertEqual(ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/listen-ports"], '[{"HTTPS":443}]')


if __name__ == "__main__":
    unittest.main()
