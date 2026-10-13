"""Real AWS 6.68.0 regression using loopback S3 XML, synthetic local state and no AWS access.

Run after `terraform -chdir=infra/modules/state-bucket init -backend=false`.
The fixture denies writes; only the lifecycle resource extracted from the actual
module is imported into temporary LOCAL state. No real bucket or state is used.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[3]
XML = b'''<LifecycleConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<Rule><ID>retain-current-state-and-limit-old-versions</ID><Status>Enabled</Status><Filter/>
<NoncurrentVersionExpiration><NoncurrentDays>90</NoncurrentDays></NoncurrentVersionExpiration>
<AbortIncompleteMultipartUpload><DaysAfterInitiation>7</DaysAfterInitiation></AbortIncompleteMultipartUpload>
</Rule></LifecycleConfiguration>'''


class LifecycleProviderRegression(unittest.TestCase):
    def test_imported_empty_api_filter_plans_no_change_with_module_and_changes_with_old_config(self):
        requests = []

        class S3(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.command, self.path))
                parsed = urlsplit(self.path)
                if parsed.path.rstrip("/") != "/banking-offline-test-fixture" or parse_qs(parsed.query, keep_blank_values=True) != {"lifecycle": [""]}:
                    self.send_error(400)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("x-amz-transition-default-minimum-object-size", "all_storage_classes_128K")
                self.end_headers()
                self.wfile.write(XML)

            def do_PUT(self):
                requests.append((self.command, self.path))
                self.send_error(403)

            do_DELETE = do_POST = do_PUT

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), S3)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="banking-provider-regression-") as directory:
                path = Path(directory)
                module = (ROOT / "infra/modules/state-bucket/main.tf").read_text()
                resource = module.split('resource "aws_s3_bucket_lifecycle_configuration" "state" {', 1)[1]
                resource = 'resource "aws_s3_bucket_lifecycle_configuration" "state" {' + resource.split('output "bucket_name"', 1)[0]
                resource = resource.replace("aws_s3_bucket.state.id", "var.bucket_name")
                resource = resource.replace("depends_on = [aws_s3_bucket_versioning.state]", "")
                provider = '''terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "= 6.68.0" } }
}
variable "bucket_name" { default = "banking-offline-test-fixture" }
provider "aws" {
  region = "us-east-2"
  access_key = "synthetic-offline-fixture"
  secret_key = "synthetic-offline-fixture"
  skip_credentials_validation = true
  skip_requesting_account_id = true
  skip_metadata_api_check = true
  skip_region_validation = true
  s3_use_path_style = true
  endpoints { s3 = "ENDPOINT" }
}
'''.replace("ENDPOINT", f"http://127.0.0.1:{server.server_port}")
                mirror = (ROOT / "infra/modules/state-bucket/.terraform/providers").as_posix()
                self.assertTrue(Path(mirror).is_dir(), "Initialize the module provider before this test.")
                cli = path / "terraform.rc"
                cli.write_text('provider_installation { filesystem_mirror { path = "' + mirror + '" } }')
                # The fixture uses an explicit filesystem mirror. Terraform rejects
                # that combination when CI also exports a provider plugin cache.
                # Isolate only this subprocess so the real provider still executes.
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith(("AWS_", "TF_VAR_")) and k != "TF_PLUGIN_CACHE_DIR"}
                env.update(TF_CLI_CONFIG_FILE=str(cli), AWS_EC2_METADATA_DISABLED="true", AWS_SHARED_CREDENTIALS_FILE=str(path / "absent"),
                           AWS_CONFIG_FILE=str(path / "absent"), TF_IN_AUTOMATION="true")

                def tf(*args):
                    result = subprocess.run(["terraform", "-chdir=" + str(path), *args], env=env,
                                            capture_output=True, text=True, timeout=90)
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr + repr(requests))
                    return result.stdout

                config = path / "main.tf"
                config.write_text(provider + resource)
                tf("init", "-backend=false", "-input=false", "-no-color")
                tf("import", "-input=false", "-no-color", "aws_s3_bucket_lifecycle_configuration.state", "banking-offline-test-fixture")
                for label, old in [("original", True), ("corrected", False), ("repeated", False)]:
                    config.write_text(provider + (resource.replace('status = "Enabled"', 'status = "Enabled"\n    filter {}') if old else resource))
                    plan = str(path / (label + ".tfplan"))
                    tf("plan", "-input=false", "-no-color", "-out=" + plan)
                    change = json.loads(tf("show", "-json", plan))["resource_changes"][0]["change"]
                    self.assertEqual(["update"] if old else ["no-op"], change["actions"])
                    before, after = change["before"]["rule"][0], change["after"]["rule"][0]
                    self.assertEqual([], before["filter"])
                    self.assertEqual([{"and": [], "object_size_greater_than": None, "object_size_less_than": None,
                                       "prefix": "", "tag": []}] if old else [], after["filter"])
                    for rule in [before, after]:
                        self.assertEqual([], rule["expiration"])
                        self.assertEqual(90, rule["noncurrent_version_expiration"][0]["noncurrent_days"])
                        self.assertEqual(7, rule["abort_incomplete_multipart_upload"][0]["days_after_initiation"])
                    print(f"Offline real-provider {label}: {change['actions']}; filter before={before['filter']}, after={after['filter']}")
                self.assertTrue(requests)
                self.assertTrue(all(method == "GET" for method, _ in requests), requests)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
