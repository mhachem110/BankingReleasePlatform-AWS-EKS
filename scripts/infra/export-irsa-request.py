"""Export exact controller trust from already verified outputs; no AWS writes."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("admin", Path(__file__).with_name("prepare-admin-request.py"))
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
values = json.loads(Path("platform.tfvars.json").read_text())
outputs = json.loads(Path("platform-outputs.json").read_text())
trust = admin.controller_trust(values["expected_account_id"], values["aws_region"], outputs["oidc_issuer_url"]["value"])
Path("controller-irsa-trust.json").write_text(json.dumps(trust, indent=2) + "\n")
print("Exact controller IRSA trust exported for administrator approval; no IAM change.")
