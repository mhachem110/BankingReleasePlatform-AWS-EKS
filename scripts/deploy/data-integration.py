"""Disposable local PostgreSQL/SQS fixtures and API failure/restart evidence. Never calls AWS."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import durable_demo

ROOT = Path(__file__).resolve().parents[2]
POSTGRES = 'postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
SQS = 'localstack/localstack@sha256:a65ee2a9d45a7a34a1f1faae515d2e577ce11210312c077700ccc82daefec238'


def run(args, *, env=None, required=True):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env, text=True,
                            encoding="utf-8", capture_output=True)
    if required and result.returncode:
        # Never print command arguments/environment containing local fixture credentials.
        raise RuntimeError(result.stdout[-3000:] + result.stderr[-3000:])
    return result.stdout.strip()


def port(container, internal):
    info = json.loads(run(['docker', 'inspect', container]))[0]
    return int(info['NetworkSettings']['Ports'][str(internal)+'/tcp'][0]['HostPort'])


def request(base, path, body=None, key=None):
    headers = {'Content-Type': 'application/json'}
    if key: headers['Idempotency-Key'] = key
    req = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def await_ready(action, seconds=60):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        try:
            if action(): return
        except (OSError, RuntimeError, urllib.error.URLError): pass
        time.sleep(1)
    raise RuntimeError('Local fixture readiness timed out.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args()
    output = ROOT/'artifacts/application/data-integration'
    output.mkdir(parents=True, exist_ok=True)
    token = 'banking-data-'+uuid.uuid4().hex[:10]
    pg, sqs, account, payment = [token+'-'+s for s in ('pg', 'sqs', 'account', 'payment')]
    environment = dict(os.environ, POSTGRES_PASSWORD=secrets.token_urlsafe(24))
    checks = []
    def check(condition, label):
        if not condition: raise AssertionError(label)
        checks.append(label)
        print('PASS: '+label, flush=True)
    try:
        if not args.skip_build:
            run(['python', 'scripts/deploy/build.py', '--commit', run(['git', 'rev-parse', 'HEAD'])])
        run(['docker', 'network', 'create', token])
        run(['docker','run','-d','--name',pg,'--network',token,'--network-alias','postgres',
             '-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=banking','-p','127.0.0.1::5432',POSTGRES], env=environment)
        run(['docker','run','-d','--name',sqs,'--network',token,'--network-alias','sqs',
             '-e','SERVICES=sqs','-e','SQS_ENDPOINT_STRATEGY=dynamic','-e','SQS_DISABLE_CLOUDWATCH_METRICS=1',
             '-p','127.0.0.1::4566',SQS])
        await_ready(lambda: 'accepting connections' in run(['docker','exec',pg,'pg_isready','-U','postgres']))
        environment['BANKING_TEST_POSTGRES'] = f"Host=127.0.0.1;Port={port(pg,5432)};Database=banking;Username=postgres;Password={environment['POSTGRES_PASSWORD']};SSL Mode=Disable"
        environment['BANKING_TEST_SQS'] = f'http://127.0.0.1:{port(sqs,4566)}/'
        await_ready(lambda: request(environment['BANKING_TEST_SQS'].rstrip('/'),'/_localstack/health')[0] == 200)
        # The console suite cannot skip absent fixtures and rejects non-loopback destinations.
        suite = run(['dotnet','run','--project','apps/tests/Banking.Integration','-c','Release','--no-restore'], env=environment)
        (output/'database-messaging.log').write_text(suite, encoding='utf-8')
        print(suite, flush=True)
        suite_summary = json.loads(suite.splitlines()[-1])
        environment['ConnectionStrings__Banking'] = f"Host=postgres;Database=banking;Username=postgres;Password={environment['POSTGRES_PASSWORD']};SSL Mode=Disable"
        common = ['--network',token,'--read-only','--user','1654:1654','--cap-drop','ALL',
                  '--security-opt','no-new-privileges','--memory','512m','--cpus','0.25',
                  '--tmpfs','/tmp:rw,noexec,nosuid,size=67108864,uid=1654,gid=1654',
                  '-e','ASPNETCORE_ENVIRONMENT=Development','-e','Persistence__Mode=Postgres',
                  '-e','Persistence__AllowLocalUnencrypted=true','-e','ConnectionStrings__Banking']
        # Exercise the actual image's explicit migration entrypoint after migrations already exist.
        for service in ('account','payment'):
            run(['docker','run','--rm',*common,'banking-ci-'+service,'--migrate'], env=environment)
        check(True, 'Both image migration commands repeat safely')
        run(['docker','run','-d','--name',account,*common,'--network-alias','account',
             '-p','127.0.0.1::8080','banking-ci-account'], env=environment)
        run(['docker','run','-d','--name',payment,*common,'-e','AccountApi__BaseUrl=http://account:8080/',
             '-e','Messaging__Enabled=true','-e','Messaging__LocalEndpoint=http://sqs:4566/',
             '-e','Messaging__QueueUrl=http://sqs:4566'+suite_summary['queuePath'],
             '-e','Messaging__DeadLetterQueueUrl=http://sqs:4566'+suite_summary['deadLetterPath'],
             '-p','127.0.0.1::8080','banking-ci-payment'], env=environment)
        account_url, payment_url = f'http://127.0.0.1:{port(account,8080)}', f'http://127.0.0.1:{port(payment,8080)}'
        await_ready(lambda: request(account_url,'/ready')[0] == request(payment_url,'/ready')[0] == 200)
        body = {'accountId':'ACC1001','amount':25,'currency':'USD'}
        status, response = request(payment_url,'/api/payments',body,'durable-api-demo')
        check(status == 200, 'HTTP payment commits to PostgreSQL')
        payment_id = json.loads(response)['paymentId']
        # Exercise the same assertions used by the gated Kubernetes demonstration.
        proof = {'key':'durable-api-demo', 'body':body, 'paymentId':payment_id}
        durable_demo.verify(payment_url, proof)
        durable_demo.verify(payment_url, durable_demo.create(payment_url))
        valid_id = str(uuid.UUID(hex=payment_id))
        await_ready(lambda: run(['docker','exec',pg,'psql','-U','postgres','-d','banking','-At','-c',
            "SELECT count(*) FROM banking_payment.processed_events WHERE payment_id='"+valid_id+"'::uuid"]) == '1')
        check(True, 'Hosted API worker publishes and consumes the HTTP payment through local SQS')
        run(['docker','restart',payment])
        payment_url = f'http://127.0.0.1:{port(payment,8080)}'
        await_ready(lambda: request(payment_url,'/ready')[0] == 200)
        durable_demo.verify(payment_url, proof)
        check(request(payment_url,'/api/payments/'+payment_id)[0] == 200, 'HTTP payment survives API process replacement')
        status, replay = request(payment_url,'/api/payments',body,'durable-api-demo')
        check(status == 200 and json.loads(replay)['paymentId'] == payment_id, 'HTTP idempotent replay after restart')
        check(request(payment_url,'/api/payments',dict(body,amount=26),'durable-api-demo')[0] == 409, 'HTTP conflicting replay rejected')
        run(['docker','stop',pg])
        check(request(account_url,'/ready')[0] == request(payment_url,'/ready')[0] == 503, 'Database failure removes readiness from both APIs')
        check(request(account_url,'/health')[0] == request(payment_url,'/health')[0] == 200, 'Database outage does not trigger liveness restarts')
        run(['docker','start',pg])
        await_ready(lambda: request(account_url,'/ready')[0] == request(payment_url,'/ready')[0] == 200)
        check(request(payment_url,'/api/payments/'+payment_id)[0] == 200, 'Database restart restores readiness and durable data')
        metrics = request(payment_url,'/metrics')[1]
        check('banking_http_requests_total' in metrics and 'banking_http_request_duration_seconds_bucket' in metrics and 'banking_process_working_set_bytes' in metrics,
              'Prometheus exports requests, latency and process memory')
        check(payment_id not in metrics and 'durable-api-demo' not in metrics, 'Metrics avoid payment IDs and idempotency-key labels')
        logs = run(['docker','logs',payment])
        check('HTTP /api/payments/{id}' in logs and environment['POSTGRES_PASSWORD'] not in logs, 'Structured route logs exclude database credentials')
        (output/'api.log').write_text(logs, encoding='utf-8')
        (output/'result.json').write_text(json.dumps({'scope':'local Docker only','checks':checks,'databaseMessagingChecks':suite_summary['checks'],'liveAws':False,'images':{'postgres':POSTGRES,'sqs':SQS}},indent=2),encoding='utf-8')
        print('Offline data/messaging/API recovery evidence passed. AWS acceptance remains pending.', flush=True)
    except Exception:
        (output/'failure.json').write_text(json.dumps({'scope':'local Docker only','checksCompleted':checks,'liveAws':False}),encoding='utf-8')
        raise
    finally:
        for name in (payment,account,sqs,pg):
            run(['docker','rm','-f','-v',name], required=False)
        run(['docker','network','rm',token], required=False)
