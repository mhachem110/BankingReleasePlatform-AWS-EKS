# Data, messaging and recovery preparation — 12 October 2026

This is code and local execution evidence. No AWS publication, deployment, plan,
resource creation, IAM update or live acceptance is claimed. Reconciliation PR #12
was merged with explicit owner approval; feature/app synchronized normally with dev.
During final integration, infra PR #13 was merged first and its data root preserved
by an ordinary merge into feature/app. A Windows CP1252/UTF-8 Docker metadata
decoding failure was preserved and corrected with explicit UTF-8 subprocess I/O;
the PostgreSQL/SQS recovery suite then passed. PR #14 remains subject to final
current-head checks and the owner's approved normal integration sequence.

## Implemented behavior

- Explicit PostgreSQL mode for both APIs, mounted connection references, production
  VerifyFull TLS, bounded pools and operator-only transactional forward migrations.
- Durable synthetic payment lookup/idempotency, atomic payment/outbox writes, leased
  concurrent dispatch, duplicate-safe receipt commits, bounded send retries and SQS
  poison/DLQ behavior. Memory mode and messaging-disabled defaults remain available.
- JSON route logs, private bounded-label Prometheus metrics, per-Pod discovery,
  six alert rules, sample evaluation, nine-panel Grafana JSON and Fargate logging proposal.
- Strict opt-in Helm/runtime references and CI data tests. The separately authorized
  Kubernetes demonstration verifies the same durable payment after restart, scaling
  and failed-upgrade rollback. Its default invocation performs no live operation.
- Incident procedures, editable architecture diagrams and a 15-minute demonstration
  plan with migration waves, cost experiment worksheets and mandatory live acceptance.

## Executed checks

`python scripts/deploy/offline.py --skip-install` passed every offline step:

| Evidence | Result |
| --- | --- |
| Locked NuGet restore / Release build | Passed, zero warnings/errors |
| API tests | 70 passed: Account 17, Payment 53 |
| Real local PostgreSQL/SQS suite | 23 checks passed |
| Image/API persistence and failure suite | 12 checks passed; 35 data checks total |
| Helm/release safety unit tests | 28 passed, including exact revision rollback, data and occupied-forward-port guards |
| Kubernetes schema matrix | Every rendered resource valid, no errors/skips |
| Monitoring | Config/rules valid; six rules and sample alert evaluation passed |
| Container/DNS/dependency smoke | Passed for real built APIs |
| Trivy on both saved image archives | Zero HIGH/CRITICAL vulnerabilities and secrets |
| Four application workflows / actionlint | Passed |
| Live demonstration default | Reported approval checkpoint; no AWS/Kubernetes call |

The 23 data checks include repeated/checksum-locked migrations, preserved account
seed edits, 16 concurrent identical requests, conflicting replay, pool replacement,
forced outbox failure with transaction rollback, competing leases, send/mark crash
and duplicate delivery, actual local SQS send failures through eight attempts,
poison redrive, metric values and runtime-role DDL denial. The image suite confirms
the hosted worker path, process replacement, database stop/restore, readiness versus
liveness, durable lookup, replay/conflict and secret-free route logs. Fixture-only
visibility acceleration verifies broker redrive; it does not measure cloud recovery time.

Raw ignored evidence is in `artifacts/application/offline-result.json`, step logs,
`data-integration/`, TRX results and `scanned/reports/`. Before the source commit,
the local summary identifies the synchronized parent commit; PR CI checks the
published head. Local fixtures are digest-pinned, loopback-only and independently
owned/cleaned. No cloud credentials are needed and no fixture failure is skipped.

## Remaining acceptance and authorization

The existing administrator request remains outstanding. Data services additionally
need actual approved RDS/SQS/key/log/alert permissions, payment IRSA, runtime database
users/secret injection and rotation, TLS/CA verification and monitoring access.
Source infrastructure is a separate infra workstream. No existing protection,
OIDC trust, runtime role or deployment switch was changed by this work.

Do not mark the project finished until actual EKS/Fargate, HTTPS/application,
database durability/least privilege/recovery, messaging/DLQ, monitoring/notification
and rollback acceptance passes. Code-only merge approval does not authorize any
AWS operation. Live Terraform planning must be separately requested only after
the administrator prerequisites are verified.
