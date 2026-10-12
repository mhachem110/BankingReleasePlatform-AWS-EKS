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
    def test_metadata_tracks_environment_owner_component_and_digest(self):
        for item in render():
            meta = item["metadata"]
            self.assertEqual(meta["labels"]["banking.example/environment"], "dev")
            self.assertEqual(meta["annotations"]["banking.example/owner"], "MahmoudHachem")
            self.assertIn(meta["labels"]["app.kubernetes.io/component"], ["account", "payment"])
            self.assertEqual(len(meta["labels"]["app.kubernetes.io/version"]), 12)
            self.assertTrue(meta["annotations"]["banking.example/image-digest"].startswith("sha256:"))
            if item["kind"] == "Deployment":
                self.assertEqual(item["spec"]["template"]["metadata"]["labels"]["banking.example/environment"], "dev")

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
        self.assertIn({"name": "AccountApi__BaseUrl", "value": "http://banking-account.banking-dev.svc.cluster.local:8080/"}, env)

    def test_no_paid_ingress_by_default(self):
        self.assertNotIn("Ingress", [item["kind"] for item in render()])
        self.assertTrue(all(item["spec"]["type"] == "ClusterIP" for item in render() if item["kind"] == "Service"))

    def test_hpa_render(self):
        resources = render("--set", "autoscaling.enabled=true")
        self.assertEqual(len([item for item in resources if item["kind"] == "HorizontalPodAutoscaler"]), 2)
        self.assertTrue(all("replicas" not in item["spec"] for item in resources if item["kind"] == "Deployment"))

    def test_latest_and_missing_digest_rejected(self):
        for override in ["images.account.digest=latest", "images.account.digest=", "replicaCount=0", "replicaCount=11"]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                render("--set", override)

    def test_no_unsupported_fargate_resources(self):
        resources = render()
        self.assertFalse(any(item["kind"] in ["DaemonSet", "NetworkPolicy", "PersistentVolumeClaim"] for item in resources))
        for item in resources:
            self.assertEqual(item["metadata"]["namespace"], "banking-dev")
            if item["kind"] == "Deployment":
                pod = item["spec"]["template"]["spec"]
                self.assertNotIn("topologySpreadConstraints", pod)
                self.assertNotIn("hostNetwork", pod)
                self.assertEqual(pod["containers"][0]["resources"]["requests"], pod["containers"][0]["resources"]["limits"])

    def test_resource_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            render("--set", "resources.limits.cpu=500m")

    def test_invalid_hpa_bounds_rejected(self):
        with self.assertRaises(ValueError):
            render("--set", "autoscaling.minReplicas=5", "--set", "autoscaling.maxReplicas=2")

    def test_replicas_independently_configurable(self):
        resources = render("--set", "replicas.account=1", "--set", "replicas.payment=3")
        replicas = {item["metadata"]["name"]: item["spec"]["replicas"] for item in resources if item["kind"] == "Deployment"}
        self.assertEqual(replicas, {"banking-account": 1, "banking-payment": 3})

    def test_fault_injection_is_explicit_and_dev_only(self):
        with self.assertRaises(ValueError):
            render("--set", "demonstration.failPaymentReadiness=true")
        resources = render("--set", "demonstration.enabled=true", "--set", "demonstration.failPaymentReadiness=true")
        payment = next(item for item in resources if item["kind"] == "Deployment" and item["metadata"]["name"] == "banking-payment")
        self.assertEqual(payment["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["httpGet"]["path"], "/demonstration-not-found")
        with self.assertRaises(ValueError):
            render("--namespace", "banking-prod", "--set", "demonstration.enabled=true", "--set", "demonstration.failPaymentReadiness=true")

    def test_ingress_requires_approved_configuration(self):
        with self.assertRaises(ValueError):
            render("--set", "ingress.enabled=true")
        resources = render("--set", "ingress.enabled=true", "--set", "ingress.approved=true", "--set", "ingress.subnets[0]=subnet-0123456789abcdef0", "--set", "ingress.securityGroups[0]=sg-0123456789abcdef0",
                           "--set", "ingress.host=banking.example.test", "--set", "ingress.certificateArn=arn:aws:acm:us-east-2:123456789012:certificate/test")
        ingress = next(item for item in resources if item["kind"] == "Ingress")
        self.assertEqual(ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/listen-ports"], '[{"HTTPS":443}]')
        self.assertEqual(ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/target-type"], "ip")


if __name__ == "__main__":
    unittest.main()
