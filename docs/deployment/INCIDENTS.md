# Incident simulations and recovery

Prepared trainer runbook. Local Docker/database/message failure evidence is available;
live EKS/Helm, RDS restore, SQS redrive and notification delivery remain pending.
Owner: MahmoudHachem. Record severity, start/detection/recovery UTC timestamps,
affected release digests, symptom, cause, recovery action and post-recovery checks.

| Incident | Detection / severity | Investigation | Recovery and acceptance |
| --- | --- | --- | --- |
| Failed readiness release | Rollout deadline / critical | Deployment events, image digests, /ready, Helm history | Restore exact prior revision; verify both digests, readiness, payment/DNS and retained payment IDs |
| Database outage | Storage readiness=0, HTTP 503 / critical | Approved endpoint/TLS/secret, RDS health, pool limits; compare liveness | Restore connectivity/approved database operation; no schema reset; both APIs ready and existing payment readable |
| Outbox backlog | Oldest pending >120s, worker unhealthy / warning | IRSA, exact queue/KMS permissions, service reachability and configuration | Restore authorized access; backlog drains; receipt appears once; payment remained durable during outage |
| Dead outbox | Dead gauge >0 / critical | Failure type, attempts, exact retained payload and original payment | Owner-approved bounded requeue after cause is fixed; retain stable event ID; verify one receipt |
| Poison SQS event | DLQ depth >0 / critical | Schema version, payload hash/type, receive count; no credential/body logging | Quarantine and investigate; approved selective redrive only for corrected/replayable valid events |
| Missing monitoring | Scrape up=0 / warning | Targets, private DNS, /metrics, scraper identity/network and log-router permissions | Restore scrape/log ingestion; verify fresh timestamps and an actual delivered test alert |

Run `python scripts/deploy/data-integration.py` for automatic local migration,
message retry/DLQ, restart, database outage and recovery evidence. Only disposable
local fixtures are changed; cleanup targets this run's UUID names. Console/unit
results do not establish live AWS authorization, HA, backup restore or notifications.

For an already authorized live Kubernetes failure demonstration, use the existing
`python scripts/deploy/demonstrate.py --execute` from the approved runner/context.
Its default invocation does not execute Kubernetes/AWS calls. The execution flag
does not replace owner approval for rollout/scaling/Fargate costs. Existing tests
verify failed releases stay failed after rollback, exact previous revision recovery,
and visible rollback failure. Never clear Helm history or delete the namespace.

For database-enabled releases, first verify the old image supports the forward
schema. Rollback restores application configuration and images, not database DDL
or data. Never run a down migration or reseed to make a demo pass. An incompatible
migration needs operator investigation and a separately approved forward repair or
restoration to a new RDS target, with reviewed RPO/RTO and cutover evidence.

Outbox repair is a separately approved data mutation. After preserving evidence and
verifying cause resolution, an operator may requeue a specifically reviewed event:

```sql
BEGIN;
-- Bind the reviewed UUID as a parameter; do not concatenate untrusted IDs.
SELECT event_id,state,attempts FROM banking_payment.outbox
WHERE event_id = :approved_event_id FOR UPDATE;
UPDATE banking_payment.outbox SET state='pending',attempts=0,next_attempt_at=now(),
lease_id=NULL,lease_until=NULL WHERE event_id=:approved_event_id AND state='dead';
COMMIT;
```

Verify the affected-row count and stable event ID. Do not delete the original payment,
receipt or failed payload; never reset all rows. SQS DLQ redrive costs and changes
require separate approval. Do not purge queues or redrive invalid payloads indefinitely.

Final recovery evidence must include healthy service checks, matching image digests,
durable payment lookup, receipt/outbox status, fresh metrics/logs and actual alert
delivery. Show the failed job and successful recovery separately. Record measured
detection/recovery times rather than promising an untested SLA.
