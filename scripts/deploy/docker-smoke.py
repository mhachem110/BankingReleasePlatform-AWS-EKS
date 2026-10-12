"""Disposable local Docker network; no Kubernetes or AWS resources."""
import argparse
import subprocess
import uuid
from common import json_run, run
from smoke import smoke

def container_args(name, network, image, env=()):
    return ["docker", "run", "-d", "--name", name, "--network", network,
            "--read-only", "--user", "1654:1654", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "512m", "--cpus", "0.25",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=67108864,uid=1654,gid=1654",
            "-p", "127.0.0.1::8080", *env, image]

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--account-image", default="banking-ci-account")
    p.add_argument("--payment-image", default="banking-ci-payment")
    a = p.parse_args()
    token = "banking-smoke-" + uuid.uuid4().hex[:10]
    account_name, payment_name = token + "-account", token + "-payment"
    try:
        run(["docker", "network", "create", token], capture=True)
        run(container_args(account_name, token, a.account_image), capture=True)
        run(container_args(payment_name, token, a.payment_image,
            ["-e", "AccountApi__BaseUrl=http://" + account_name + ":8080/"]), capture=True)
        def base(name):
            info = json_run(["docker", "inspect", name])[0]
            assert info["Config"]["User"] == "1654:1654"
            assert info["HostConfig"]["ReadonlyRootfs"]
            return "http://127.0.0.1:" + info["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
        account_url, payment_url = base(account_name), base(payment_name)
        smoke(account_url, payment_url)
        run(["docker", "stop", account_name], capture=True)
        smoke(account_url, payment_url, unavailable=True)
        run(["docker", "start", account_name], capture=True)
        account_url = base(account_name)
        smoke(account_url, payment_url)
        print("PASS: non-root read-only containers, DNS, dependency failure and restart recovery")
    except Exception:
        for name in (account_name, payment_name):
            run(["docker", "logs", "--tail", "60", name], check=False)
        raise
    finally:
        for name in (payment_name, account_name):
            run(["docker", "rm", "-f", name], check=False, capture=True)
        run(["docker", "network", "rm", token], check=False, capture=True)
