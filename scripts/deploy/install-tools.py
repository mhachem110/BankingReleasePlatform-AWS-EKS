"""Install only checksum-pinned tools into an explicit local tool directory."""
import argparse
import hashlib
import io
import json
import os
import platform
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", default="artifacts/application/tools")
    args = p.parse_args()
    destination = Path(args.directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    system = platform.system().lower()
    if system not in ("linux", "windows") or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("This tool lock supports Linux/Windows amd64")
    lock = json.loads(Path(__file__).with_name("tools.json").read_text())
    for name, options in lock.items():
        entry = options[system]
        binary = name + (".exe" if system == "windows" else "")
        target = destination / binary
        payload = urllib.request.urlopen(entry["url"], timeout=60).read()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("Checksum mismatch for " + name)
        if entry["url"].endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                member = next(n for n in archive.namelist() if Path(n).name == binary)
                target.write_bytes(archive.read(member))
        elif entry["url"].endswith(".tar.gz"):
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
                member = next(n for n in archive.getmembers() if n.isfile() and Path(n.name).name == binary)
                target.write_bytes(archive.extractfile(member).read())
        else:
            target.write_bytes(payload)
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        print("Verified and installed " + binary)
    if os.environ.get("GITHUB_PATH"):
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as output:
            output.write(str(destination) + "\n")
