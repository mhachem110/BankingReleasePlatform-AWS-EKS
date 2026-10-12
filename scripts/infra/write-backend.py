"""Generate the separate Phase 3 backend, never rewrite a Phase 2 state path."""
import json
import os
from pathlib import Path
from guard import STATE_KEY

Path("platform.tfbackend.json").write_text(json.dumps({
    "bucket": os.environ["TF_STATE_BUCKET"], "region": os.environ["AWS_REGION"],
    "key": STATE_KEY, "encrypt": True, "use_lockfile": True,
    "allowed_account_ids": [os.environ["AWS_EXPECTED_ACCOUNT_ID"]],
    "workspace_key_prefix": "banking-release-platform/_workspaces",
}, indent=2), encoding="utf-8")
