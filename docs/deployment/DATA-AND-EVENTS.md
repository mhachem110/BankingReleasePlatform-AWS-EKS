# Persistent synthetic payments and asynchronous events

Status: implemented/tested offline; no RDS, SQS, IRSA or cloud release has run.
Memory mode remains the default, with no AWS calls. All accounts/payments are
fictional and approval never moves funds or changes balances. PostgreSQL mode
persists the simulation and a versioned PaymentCompleted event.

## Offline execution

```powershell
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet test BankingReleasePlatform.sln -c Release --no-restore
python scripts/deploy/data-integration.py
```

The driver starts only UUID-named disposable local Docker fixtures, binds host
ports to loopback, generates an ephemeral database password and local emulator
signatures, and removes only its own containers/network/anonymous volumes.
It requires Docker Linux containers, Python and the pinned .NET SDK. PostgreSQL
and LocalStack images are immutable digests. Missing fixtures fail; no integration
case is silently skipped. It never uses an AWS endpoint or provisions cloud resources.

The real PostgreSQL/SQS-compatible suite covers repeat migrations without reseeding,
concurrent idempotency, persistence, transactional rollback, dispatcher leases,
crash-after-send duplication, bounded send retries/dead outbox, consumer poison/DLQ
redrive, altered-migration rejection and runtime DDL denial. Actual container APIs
exercise migrations, full hosted-worker event flow, API replacement, replay/conflict,
database outage/readiness/liveness/recovery, metric cardinality and sanitized logs.
LocalStack verifies protocol/flow, not actual AWS IAM, KMS, IRSA or service guarantees.

## Storage and migrations

Set Persistence__Mode=Postgres and mount an operator-approved connectionString
secret using Persistence__ConnectionStringFile. Production requires SSL Mode=VerifyFull
and the approved root certificate. The Helm CA mount is /etc/banking/ca/root-ca.pem;
include that Root Certificate path in the secret's connection string. Never place
passwords in Helm values, GitHub variables, source, logs or Terraform state. The
explicit unencrypted option is accepted only in Development for the local fixture.

API startup performs no schema creation. An approved operator runs the exact reviewed
image with --migrate using separate migration credentials before enabling database
readiness. Migrations are embedded SQL, serialized by an advisory transaction lock,
tracked by SHA256 and applied atomically. Applied SQL cannot be edited; add a forward
migration. Initial seeding runs once and never overwrites existing accounts. A
failed migration rolls back its DDL/data/version record. No down/drop migration exists.

Account uses banking_account; Payment uses banking_payment. Runtime accounts need
USAGE and scoped SELECT/INSERT/UPDATE only as required, no table ownership/DDL:
Account SELECT on accounts and schema_migrations; Payment SELECT on schema_migrations,
SELECT/INSERT on payments and processed_events, SELECT/INSERT/UPDATE on outbox.
Do not give Pods the RDS master/migrator login. The proposed RDS-managed master secret
is for authorized operator use. Runtime user secrets, delivery from approved Secrets
Manager entries and rotation/injection need administrator/operator review. This release
reads mounted secrets; it does not install a secret controller or fetch a guessed ARN.
Connection pools cap at ten per Pod. Secret rotation requires an approved rolling
restart to replace the pool; the current code does not hot-reload rotated credentials.

GET /health remains process liveness. GET /ready checks migration metadata using the
runtime identity; missing schema or database failure returns 503. Helm switches
readiness to /ready when persistence is enabled; liveness stays /health. A transient
database failure should remove readiness, not create a restart storm.

## Payment and event semantics

POST /api/payments accepts an optional Idempotency-Key of at most 64 ASCII letters,
digits/hyphens. Repeating the same key/body returns the recorded payment ID, even
if Account is now unavailable; a different body returns 409. Without a key, each
request is a separate simulation. Invalid/unavailable Account validation records no
payment. If commit status is uncertain, retry the same key. GET /api/payments/{id}
reads the recorded simulation. Memory mode offers only process-local demonstration
state; PostgreSQL offers durable replay. This is not a financial ledger.

Migration checksums use canonical LF line endings across Windows/Linux builds;
other changes to an applied SQL migration fail closed and require a forward file.

The payment and outbox row commit in one transaction. No approved response is
returned before durable commit. The event contains schemaVersion=1, eventType,
stable eventId/paymentId, amount/currency and UTC occurrence time; it contains no
customer name, database password or access token. The consumer verifies the event
against the recorded synthetic payment and commits a unique, hashed receipt.
That receipt is the asynchronous PaymentCompleted audit projection.

Dispatchers use SKIP LOCKED and a 30-second token-protected lease. Sending then
crashing before mark-sent can duplicate delivery; the durable receipt handles replay.
Conflicting bodies under one event ID fail. Consumer deletion happens only after
receipt commit. A lost delete can replay safely. This is at-least-once processing,
not a claim of exactly-once SQS delivery or distributed account/payment transactions.

Send failures retry at 5, 10, 20, 40, 80, 160, 300, 300 seconds, then retain a dead
outbox row for operator recovery. Consumer failures are left in SQS, with bounded
visibility backoff, for the broker's configured DLQ redrive. Source/DLQ identity,
maxReceiveCount 3–10, visibility >=30 seconds and DLQ retention >=source are checked
at startup and each minute. Misconfiguration blocks sending rather than creating or
changing queues. Poison payloads are not acknowledged or recorded as processed.

## Reviewed Helm/release integration

Persistence references existing account/payment Secrets and a CA ConfigMap only.
The chart creates no database, credential secret, queue, role or logging daemon.
Messaging requires persistence, explicit approved configuration, distinct existing
dev queue URLs and the approved payment runtime role. IRSA/token mounting is enabled
only for the Payment ServiceAccount; Account stays token-free. No Fargate execution
or GitHub deployment identity is reused as runtime identity. No Pod Identity agent.

The protected app workflow accepts APP_RUNTIME_VALUES_JSON containing only
persistence, messaging and monitoring references. Unknown/duplicate keys and plaintext
credential fields fail. Enabling data requires APP_DATA_OPERATIONS_ENABLED=true and
dev, in addition to the existing APP_DEPLOYMENTS_ENABLED/protected review. Defaults
remain disabled. Helm lint/schema checks run before deployment; rollback restores the
exact previous Helm revision and image pair. Database schema/data are never reverted
by Helm rollback. Use additive migrations compatible with both old and new images.

Live RDS/queue/role/secret/logging changes and the data-enabled release still require
their own actual inventory/cost/access approval. The Phase 3 initial creation workflow
must not be expanded to deploy these services. No extra environment is provisioned.

Sources: [Npgsql transactions/TLS](https://www.npgsql.org/doc/security.html),
[SQS visibility and duplicate delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html).
