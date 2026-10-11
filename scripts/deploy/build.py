import argparse
from common import ROOT, SHA, run

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--commit", required=True)
    args = p.parse_args()
    if not SHA.fullmatch(args.commit):
        raise ValueError("Invalid commit")
    for service in ("account", "payment"):
        project = service.title() + ".Api"
        run(["docker", "build", "--pull", "--platform", "linux/amd64",
             "--label", "org.opencontainers.image.revision=" + args.commit,
             "-f", ROOT / "apps" / project / "Dockerfile",
             "-t", "banking-ci-" + service, ROOT])
