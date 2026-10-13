"""TLS-only dev/prod database setup from same-run verified RDS interfaces.

RDS keeps the master credential in Secrets Manager. This operator job reads it
only in memory, creates independent API users, and stores their connection
strings in their own encrypted Kubernetes namespaces. No password is logged or
written to Terraform state or a GitHub artifact.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import urllib.request

import psycopg
from psycopg import sql as pgsql

ACCOUNT = "866934333672"
REGION = "us-east-2"
CA_URL = "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
CA_SHA256 = "fe45bbebf92ad3e27a583bbb2ddd1553c521ed4d49af5514dc0a40372ea5395c"
ROOT = Path(__file__).resolve().parents[2]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(*args, payload=None, missing=False):
    result = subprocess.run(args, input=payload, text=True, capture_output=True, timeout=90)
    if result.returncode:
        if missing and "NotFound" in result.stderr:
            return None
        # Arguments, stdin and service output may contain credentials.
        raise RuntimeError("Protected database bootstrap command failed: " + args[0])
    return result.stdout


def interface(environment):
    value = json.loads(os.environ.get(environment.upper() + "_DATA_INTERFACE_JSON") or "{}")
    outputs = value.get("outputs", {})
    require(value.get("verified") is True and value.get("environment") == environment,
            "Data must be verified for this exact environment")
    require(re.fullmatch(r"banking-" + environment + r"-postgres\.[a-z0-9.-]+\.rds\.amazonaws\.com",
                         outputs.get("database_endpoint", "")), "Unexpected RDS endpoint")
    require(re.fullmatch(r"arn:aws:secretsmanager:us-east-2:" + ACCOUNT + r":secret:rds!db-[A-Za-z0-9/_+=.@!-]+",
                         outputs.get("master_secret_arn", "")), "Unexpected RDS-managed secret ARN")
    require(outputs.get("payment_queue_url") ==
            f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/banking-{environment}-payments",
            "Unexpected payment queue")
    return outputs


def current_password(namespace, service, host):
    name = f"banking-{service}-db"
    data = command("kubectl", "get", "secret", name, "-n", namespace, "-o", "json", missing=True)
    if data is None:
        return secrets.token_urlsafe(36)
    item = json.loads(data)
    require(item["metadata"].get("namespace") == namespace and item["type"] == "Opaque",
            "Existing application credential has unexpected ownership")
    value = base64.b64decode(item["data"]["connectionString"]).decode()
    expected = f"Host={host};Port=5432;Database=banking;Username=banking_{service}_app;Password="
    require(value.startswith(expected) and ";SSL Mode=VerifyFull;Root Certificate=/etc/banking/ca/root-ca.pem" in value,
            "Existing application credential is not the reviewed TLS connection")
    password = value.removeprefix(expected).split(";", 1)[0]
    require(re.fullmatch(r"[A-Za-z0-9_-]{30,}", password), "Existing credential is malformed")
    return password


def migrate(connection, schema, service):
    name = "001_accounts.sql" if service == "account" else "001_payment_outbox.sql"
    source = ROOT / "apps" / ("Account.Api" if service == "account" else "Payment.Api") / "Migrations" / name
    statement = source.read_text(encoding="utf-8").replace("\r\n", "\n")
    digest = hashlib.sha256(statement.encode()).hexdigest()
    version = ("Account.Api" if service == "account" else "Payment.Api") + ".Migrations." + name
    lock = 8181001 if service == "account" else 8181002
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
        cur.execute(pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(pgsql.Identifier(schema)))
        cur.execute(pgsql.SQL("CREATE TABLE IF NOT EXISTS {}.schema_migrations "
                              "(version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
                    .format(pgsql.Identifier(schema)))
        cur.execute(pgsql.SQL("SELECT sha256 FROM {}.schema_migrations WHERE version=%s")
                    .format(pgsql.Identifier(schema)), (version,))
        existing = cur.fetchone()
        if existing:
            require(existing[0] == digest, "A deployed database migration changed")
            return
        cur.execute(statement)
        cur.execute(pgsql.SQL("INSERT INTO {}.schema_migrations(version,sha256) VALUES(%s,%s)")
                    .format(pgsql.Identifier(schema)), (version, digest))


def role(connection, service, password):
    name = "banking_" + service + "_app"
    schema = "banking_" + service
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,))
        if cur.fetchone():
            cur.execute(pgsql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}")
                        .format(pgsql.Identifier(name), pgsql.Literal(password)))
        else:
            cur.execute(pgsql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}")
                        .format(pgsql.Identifier(name), pgsql.Literal(password)))
        cur.execute(pgsql.SQL("GRANT CONNECT ON DATABASE banking TO {}")
                    .format(pgsql.Identifier(name)))
        cur.execute(pgsql.SQL("GRANT USAGE ON SCHEMA {} TO {}")
                    .format(pgsql.Identifier(schema), pgsql.Identifier(name)))
        permissions = "SELECT" if service == "account" else "SELECT, INSERT, UPDATE"
        cur.execute(pgsql.SQL("GRANT " + permissions + " ON ALL TABLES IN SCHEMA {} TO {}")
                    .format(pgsql.Identifier(schema), pgsql.Identifier(name)))


def apply_object(value):
    command("kubectl", "apply", "--server-side", "--field-manager=banking-data-bootstrap",
            "-f", "-", payload=json.dumps(value))


def main():
    require(os.environ.get("AWS_ACCOUNT_ID") == ACCOUNT and os.environ.get("AWS_REGION") == REGION,
            "Wrong database bootstrap account/Region")
    runtime = json.loads(os.environ.get("RUNTIME_INTERFACE_JSON") or "{}")
    require(runtime.get("verified") is True, "Runtime roles must be verified")
    ca = urllib.request.urlopen(CA_URL, timeout=60).read()
    require(hashlib.sha256(ca).hexdigest() == CA_SHA256, "RDS CA bundle digest changed")
    evidence = {"account": ACCOUNT, "region": REGION, "environments": {}, "caSha256": CA_SHA256}
    with tempfile.TemporaryDirectory(prefix="banking-rds-ca-") as folder:
        ca_path = Path(folder) / "root-ca.pem"
        ca_path.write_bytes(ca)
        for environment in ("dev", "prod"):
            namespace = "banking-" + environment
            item = interface(environment)
            secret = json.loads(command("aws", "secretsmanager", "get-secret-value", "--secret-id",
                                        item["master_secret_arn"], "--region", REGION))
            master = json.loads(secret["SecretString"])
            require(master.get("username") == "banking_migrator" and master.get("password"),
                    "RDS master secret is not the reviewed managed credential")
            host = item["database_endpoint"]
            apply_object({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
                "name": "banking-rds-ca", "namespace": namespace,
                "labels": {"app.kubernetes.io/part-of": "banking", "banking.example/environment": environment}},
                "data": {"root-ca.pem": ca.decode()}})
            passwords = {service: current_password(namespace, service, host)
                         for service in ("account", "payment")}
            with psycopg.connect(host=host, port=5432, dbname="banking",
                                 user=master["username"], password=master["password"],
                                 sslmode="verify-full", sslrootcert=str(ca_path),
                                 connect_timeout=15) as conn:
                for service in ("account", "payment"):
                    migrate(conn, "banking_" + service, service)
                    role(conn, service, passwords[service])
            for service in ("account", "payment"):
                value = (f"Host={host};Port=5432;Database=banking;Username=banking_{service}_app;"
                         f"Password={passwords[service]};SSL Mode=VerifyFull;"
                         "Root Certificate=/etc/banking/ca/root-ca.pem")
                apply_object({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                              "metadata": {"name": f"banking-{service}-db", "namespace": namespace,
                                           "labels": {"app.kubernetes.io/part-of": "banking", "banking.example/environment": environment}},
                              "data": {"connectionString": base64.b64encode(value.encode()).decode()}})
            evidence["environments"][environment] = {"namespace": namespace,
                "databaseIdentifier": item["database_identifier"], "migratedSchemas": ["banking_account", "banking_payment"],
                "applicationSecrets": ["banking-account-db", "banking-payment-db"]}
    evidence["verified"] = True
    Path("database-bootstrap-verification.json").write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
