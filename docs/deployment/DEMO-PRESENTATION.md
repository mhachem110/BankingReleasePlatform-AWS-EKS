# Fifteen-minute trainer demonstration

Preparation draft. Replace pending live evidence only after actual acceptance;
never narrate a local emulator or Terraform mock as an AWS deployment.

| Timing | Segment | Demonstration / required evidence |
| --- | --- | --- |
| 0:00–2:00 | Business and architecture | Safe release objective, synthetic API/data boundary, Fargate/DNS/outbox diagram and actual approval controls |
| 2:00–6:00 | Application, containers and EKS | Local persistence/message evidence now; later actual Ready Pods, Fargate nodes, private DNS, durable payment after Pod replacement and real SQS receipt |
| 6:00–9:00 | CI/CD specialty | Exact-commit CI, immutable scanned pair, protected publication/deploy, sequential digest promotion and failed job with verified rollback |
| 9:00–12:00 | Security, telemetry and incident | Separate identities, verified database TLS/DDL denial, fresh per-Pod graphs/logs, real alert delivery, detection/investigation/recovery timeline |
| 12:00–14:00 | Migration and cost | Wave evidence, measured baseline/before-after outcomes, three supported optimization comparisons and residual charges |
| 14:00–15:00 | Risks and next steps | One-AZ database/one-NAT tradeoffs, unverified HA/backup restore, remaining live gates and authorized cleanup |

## Evidence-led migration waves

1. Preserve the working memory-mode release and its exact digests/health evidence.
2. Deploy only the approved private database/queues/logging resources through a
   separate protected data plan/apply after Phase 3 live verification/cost approval.
3. Run explicit additive migrations, verify runtime user TLS/permissions, seed only
   synthetic rows and retain the old image/schema compatibility check.
4. Authorize database mode with messaging initially disabled; verify durable payment
   lookup, replay/conflict, Pod replacement and database readiness/recovery.
5. Authorize exact runtime IRSA/queue settings; verify actual event/receipt/retry/DLQ.
6. Authorize collectors/logging/receiver; verify every Pod's fresh metrics, dashboard,
   log ingestion, alert delivery and live failed-release recovery.

At each wave record UTC times, source/image digests, operator approval, accepted
checks and rollback/forward-repair decision. Roll back application mode/configuration
without destroying the private database or losing records. Do not call memory mode a
durable fallback; preserve access to stored records and explicitly report read-only or
degraded operation if database access is unavailable.

## Three optimization evidence worksheets

| Experiment | Baseline and change | Proof needed / tradeoff |
| --- | --- | --- |
| API resource right-sizing | Record process metrics, kubectl top and actual Fargate rounding before/after equal request/limit changes | Compare measured p95/errors and allocation/cost units; process memory alone is insufficient |
| Idle replicas/HPA envelope | Record approved replica baseline, peak/surge use and controlled scaling | Calculate task-hours saved from actual durations; preserve readiness and minimum demonstration capacity |
| Retention/traffic choices | Record untagged ECR bytes, log/state retention and S3 endpoint vs NAT bytes | Show measured or calculated savings from dated quantities/prices; preserve tagged releases, current state and required evidence |

These are experiment plans, not three achieved cloud savings. Use actual dated
billing/usage evidence and current Ohio prices after approval. Explain EKS/system
Pods/NAT/public-IP/key/log/snapshot charges that persist when API Pods stop. No
automatic destroy or account-wide security/billing change is part of the demo.

## Final live acceptance checklist

Actual cluster/profiles/add-ons/access healthy; both API Pods Ready on Fargate;
internal DNS and approved HTTPS access; real scanned ECR images and protected
Helm deployment/promotion; persistence/TLS/secrets/runtime permissions; real
SQS receipt/retry/DLQ; fresh metrics/logs/dashboards and delivered owned alert;
scaling/replacement and failed-release rollback; backup/recovery/migration wave
evidence; three optimization outcomes; retained cleanup plan and presentation.
The project remains incomplete until all mandatory live checks pass.
