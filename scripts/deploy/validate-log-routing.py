"""Exercise real Fluent Bit routing offline; never connects to AWS or Kubernetes."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
import yaml
from common import ROOT

# Ohio-independent public AWS image; resolved stable Linux/amd64 digest 12 Oct 2026.
IMAGE = "public.ecr.aws/aws-observability/aws-for-fluent-bit@sha256:32b8cbb1996d7f651d74d8970a0f7a74ddc207ac5d9ca902a4160de65fa38819"


def validate():
    source = ROOT/"docs/deployment/monitoring/aws-logging.yaml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))["data"]
    if sum(len(v) for v in data.values()) > 5300 or "${" in "".join(data.values()):
        raise ValueError("Invalid Fargate configuration size or environment expansion")
    # Real metadata-shaped records enter the actual grep/rewrite filters. The
    # metadata/enrichment and CloudWatch delivery are separate live acceptance.
    sections = ["[FILTER]"+s for s in data["filters.conf"].split("[FILTER]")[1:]]
    filters = "\n".join(s for s in sections if re.search(r"Name\s+(grep|rewrite_tag)\s", s))
    outputs = data["output.conf"].split("[OUTPUT]")[1:]
    if len(outputs) != 2:
        raise ValueError("Exactly two separately approved log destinations required")
    out = ROOT/"artifacts/application/log-routing"
    out.mkdir(parents=True, exist_ok=True)
    name = "banking-log-routing-"+uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory() as directory:
        destinations = Path(directory)/"destinations"
        destinations.mkdir()
        config = "[SERVICE]\n    Flush 1\n    Grace 1\n"
        for namespace in ("banking-dev", "banking-prod", "kube-system", "banking-stage"):
            record = json.dumps({"kubernetes":{"namespace_name":namespace}, "proof":namespace})
            config += f"[INPUT]\n    Name dummy\n    Tag kube.fixture.{namespace}\n    Samples 1\n    Dummy {record}\n"
        config += filters
        for env, output in zip(("dev","prod"), outputs):
            match = re.search(r"Match\s+(\S+)", output)[1]
            group = re.search(r"log_group_name\s+(\S+)", output)[1]
            if group != f"/banking/banking-{env}/application" or "auto_create_group false" not in output:
                raise ValueError("Unapproved group or implicit paid resource creation")
            # Independent files avoid interleaving from concurrent output threads.
            config += f"[OUTPUT]\n    Name file\n    Match {match}\n    Path /results\n    File {env}.jsonl\n    Format plain\n"
        path = Path(directory)/"routing.conf"
        path.write_text(config,encoding="utf-8")
        # Pull happens before the network-isolated process; no AWS credentials,
        # Docker socket or host credential directory is shared with the container.
        subprocess.run(["docker","pull",IMAGE],check=True)
        with (out/"fluent-bit.log").open("w",encoding="utf-8") as log:
            process = subprocess.Popen(["docker","run","--rm","--name",name,"--network","none",
                "--mount",f"type=bind,source={directory},target=/fixtures,readonly",
                "--mount",f"type=bind,source={destinations},target=/results",
                "--entrypoint","/fluent-bit/bin/fluent-bit",IMAGE,"-c","/fixtures/routing.conf"],
                stdout=log,stderr=subprocess.STDOUT,text=True)
            try:
                time.sleep(5)
            finally:
                subprocess.run(["docker","stop","--time","2",name],capture_output=True)
                process.wait(timeout=15)
        if process.returncode != 0:
            raise ValueError("Fluent Bit did not exit cleanly; inspect its preserved log")
        result = (out/"fluent-bit.log").read_text(encoding="utf-8")
        for env in ("dev", "prod"):
            namespace = "banking-"+env
            destination = destinations/(env+".jsonl")
            routed = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()] if destination.exists() else []
            if routed != [{"kubernetes":{"namespace_name":namespace}, "proof":namespace}]:
                raise ValueError("Namespace log was lost, duplicated or sent to the wrong destination: "+namespace)
            (out/(env+".jsonl")).write_bytes(destination.read_bytes())
        if "[error]" in result:
            raise ValueError("Fluent Bit emitted an error; inspect the preserved log")
        (out/"result.json").write_text(json.dumps({"image":IMAGE,"namespaceRouting":"passed",
            "checks":["dev/prod delivered once to their selected output","system/stage excluded","no emitter cycle"],
            "liveAWS":False,"fargateManagedRouterAcceptance":"pending"},indent=2),encoding="utf-8")
    print("PASS: native offline log routing separates dev/prod and excludes other namespaces")


if __name__ == "__main__":
    validate()
