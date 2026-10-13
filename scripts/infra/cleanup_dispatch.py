"""Keep one Terraform Destroy entry while retaining the original prerequisite guard."""
import os
from pathlib import Path
import sys

FULL = {"dev-data", "prod-data", "runtime-prerequisites", "runner", "platform"}

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "unlock" and os.environ.get("TARGET") not in FULL:
        sys.exit(0)
    script = "cleanup_full.py" if os.environ.get("TARGET") in FULL else "cleanup_guard.py"
    path = Path(__file__).with_name(script)
    os.execv(sys.executable, [sys.executable, str(path), command])
