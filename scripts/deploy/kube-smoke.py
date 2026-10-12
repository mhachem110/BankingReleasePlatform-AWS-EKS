import argparse
import contextlib
import socket
import subprocess
import tempfile
from pathlib import Path
from smoke import smoke

@contextlib.contextmanager
def forwards(namespace, release):
    # Refuse occupied local ports before starting either forward, so HTTP evidence
    # cannot accidentally come from an unrelated process on this workstation.
    for port in (18081, 18082):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    processes = []
    with tempfile.TemporaryDirectory() as directory:
        logs = []
        try:
            for service, port in (("account", 18081), ("payment", 18082)):
                log = open(Path(directory) / (service + ".log"), "w+")
                logs.append(log)
                processes.append(subprocess.Popen(["kubectl", "-n", namespace, "port-forward",
                    "--address", "127.0.0.1", "service/" + release + "-" + service, f"{port}:8080"],
                    stdout=log, stderr=subprocess.STDOUT))
            yield "http://127.0.0.1:18081", "http://127.0.0.1:18082"
        except Exception:
            for log in logs:
                log.seek(0)
                print(log.read())
            raise
        finally:
            for process in processes:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            for log in logs:
                log.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--namespace", required=True)
    p.add_argument("--release", default="banking")
    args = p.parse_args()
    with forwards(args.namespace, args.release) as urls:
        smoke(*urls)
