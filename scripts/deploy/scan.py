"""Scan saved container bytes without sharing Docker credentials or its socket."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from common import ROOT, json_run, run, save_json

TRIVY = "ghcr.io/aquasecurity/trivy@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"

def scan_archive(path, reports, cache, service):
    return run(["docker", "run", "--rm",
        "--mount", f"type=bind,source={path.parent.resolve()},target=/input,readonly",
        "--mount", f"type=bind,source={reports.resolve()},target=/reports",
        "--mount", f"type=bind,source={cache.resolve()},target=/cache",
        TRIVY, "image", "--input", "/input/" + path.name,
        "--cache-dir", "/cache", "--scanners", "vuln,secret",
        "--severity", "HIGH,CRITICAL", "--exit-code", "1",
        "--format", "json", "--output", "/reports/" + service + ".json"],
        check=False).returncode

def scan(images, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    reports = directory / "reports"
    reports.mkdir(exist_ok=True)
    cache = ROOT / "artifacts/application/cache" / "trivy"
    cache.mkdir(parents=True, exist_ok=True)
    records, failures = {}, []
    for service, image in images.items():
        archive = directory / (service + ".tar")
        run(["docker", "save", "-o", archive, image])
        info = json_run(["docker", "image", "inspect", image])[0]
        code = scan_archive(archive, reports, cache, service)
        with archive.open("rb") as handle:
            archive_hash = hashlib.file_digest(handle, "sha256").hexdigest()
        records[service] = {"imageId": info["Id"], "archiveSha256": archive_hash,
                            "sourceCommit": info["Config"].get("Labels", {}).get("org.opencontainers.image.revision")}
        if code != 0:
            failures.append(service)
    if failures:
        for service in failures:
            report = reports / (service + ".json")
            if report.exists():
                data = json.loads(report.read_text())
                for result in data.get("Results", []):
                    for vuln in result.get("Vulnerabilities", []):
                        print(service, vuln["VulnerabilityID"], vuln["PkgName"], vuln["InstalledVersion"],
                              "fixed:", vuln.get("FixedVersion", "unavailable"), vuln["Severity"])
                    for secret in result.get("Secrets", []):
                        print(service, "secret finding:", secret.get("RuleID"))
        raise RuntimeError("Security gate failed: " + ", ".join(failures))
    save_json(directory / "scanned.json", records)
    print("PASS: both container archives scanned; zero HIGH/CRITICAL vulnerabilities or secrets")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--manifest")
    p.add_argument("--output", default="artifacts/application/scanned")
    args = p.parse_args()
    images = {s: "banking-ci-" + s for s in ("account", "payment")}
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text())
        images = {s: i["repository"] + "@" + i["digest"] for s, i in manifest["images"].items()}
        for image in images.values():
            run(["docker", "pull", "--platform", "linux/amd64", image])
    scan(images, args.output)
