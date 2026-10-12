# Phase 6 data and operations infrastructure — offline preparation only

This is a separate future data-services root, not an extension of the protected
Phase 3 first-creation workflow. It has never been planned or applied against AWS.
The existing platform's 44-entry guard, state keys, IAM policy and workflow remain
unchanged. No paid service or notification is enabled by code review or merge.

`infra/environments/dev/data` proposes private PostgreSQL 17 RDS, encrypted standard
SQS and its DLQ, encrypted application/database logs, one HTTP-error metric filter
and five scoped alarms. It references actual verified Banking platform IDs and an
approved existing key/alert topic. It creates no IAM role, KMS key, SNS topic or
subscription. Separate native S3 locking uses the proposed new data state key;
access to that key is not yet authorized.

The database has no public access, accepts only TCP 5432 from the approved cluster
security group, requires TLS, retains seven days of backups, uses RDS-managed master
credentials in Secrets Manager and protects deletion/final snapshots. Single AZ is
an explicit development tradeoff. Storage starts at 20 GiB and can grow to 40 GiB;
both the initial and maximum costs must be approved. Neither exact engine patch
nor instance class is guessed: actual Ohio compatibility, quota and pricing evidence
must be supplied. The master login is for authorized schema/operator work, never
for API Pods. Application runtime users require only their own schema/data rights.
Each API Pod caps its connection pool at ten. The configured maximum eight API Pods
plus two API surge Pods can require up to 100 connections before migration/operator
headroom. Confirm the selected database's actual connection/memory capacity and
right-size the pools/class from measurements before any live data plan. Burstable
instance CPU credits, storage growth and retained snapshots may add charges.
Enhanced Monitoring runs every 60 seconds with an actual administrator-approved
dedicated service role; its log ingestion/retention belongs in the cost review.
Automatic minor security upgrades are enabled in the reviewed maintenance window.
Record engine_version_actual after maintenance and update the approved input before
future Terraform operations; never attempt a downgrade or ignore version drift.

Standard SQS is at-least-once. The source retains one day of events, the DLQ fourteen
days, visibility is 30 seconds, maxReceiveCount is five and the payload limit is
4 KiB. The DLQ allow policy names only this source. Application outbox failures are
retained as `dead` rows separately from consumer poison messages in SQS's DLQ.

The application log group is created with 30-day retention and KMS encryption.
An operator installs the reviewed Fargate built-in logging ConfigMap later; no
DaemonSet is used. HTTP 5xx filters expect merged JSON console logs under State.Status.
Alarms cover RDS CPU/free space, source age, DLQ depth and HTTP errors. Severity,
owner and runbook are recorded; an actual approved SNS destination is required.
Missing metrics are not proof of health, and notification delivery remains a live
acceptance test. Prometheus health/scrape alerts supplement these service alarms.

## New dependencies specific to this future phase

The existing Phase 3 administrator request is unchanged. Future data services add:
approved RDS/SQS/log/metric/alarm permissions and data-state access; key-policy contexts
for RDS, Secrets Manager, SQS and the new log groups; existing RDS service-linked-role
verification; approved Enhanced Monitoring role/trust and exact PassRole; exact
engine/class availability; real runtime database users and secret
rotation/injection; payment runtime IRSA for exact source/DLQ reads and source send/
receive/delete/visibility, plus exact-key decrypt/data-key permissions; and an approved
alert destination/delivery scope. No blanket IAM grant or shared-policy replacement.

## Required live sequence

1. Complete and verify separately authorized Phase 3 infrastructure first.
2. Inspect actual outputs, database subnet isolation/AZs, cluster SG, key/resource
   policies, quotas, current engine/class availability and naming collisions.
3. Review this separate resource inventory and current costs, including storage
   growth, backups/snapshots, secrets, SQS/KMS requests, logs/custom metrics/alarms,
   monitoring Pods and migration surge. There is no current spend estimate or cap.
4. Review the separate prepared data-operations.yml workflow and DATA-DEPLOYMENT.md,
   its exact creation inventory, own state, cost/session-policy receipts and two
   personal reviews. It remains disabled/unexecuted. The Phase 3 workflow is unchanged.
5. Obtain specific live-plan authorization, then approval of the actual saved plan
   and costs before apply. This source-only PR authorizes neither operation.
6. Install reviewed runtime secrets/RBAC/IRSA/logging, run explicit forward migrations
   with migration credentials, then authorize the data-enabled application release.
7. Verify TLS/least privilege, persistent data after Pod replacement, actual SQS/DLQ
   delivery, log ingestion, dashboards/alarms/notification and database recovery.

Cleanup needs separate approval: retained RDS final snapshots, backups, managed
secret, KMS/key requests, logs and alarm/custom metric charges can outlive API Pods.
Review deletion-protection updates and snapshot names/collisions without deleting
existing Phase 2/platform state or shared resources. Do not destroy demonstration data
automatically. No final project acceptance is claimed by these offline files.

## Offline validation evidence — 12 October 2026

All nine Terraform roots passed backend-disabled initialization with existing lock
files, validate and recursive formatting. All 23 provider-mocked tests passed,
including seven new data-module/root checks for private TLS/encrypted RDS, managed
master credentials, backup/deletion controls, exact active EKS cluster SG, isolated
database routes, wrong environment/key rejection, encrypted source/DLQ redrive and
five owned alarm actions. Mock plans/applies create no AWS resources.

The existing Python suites passed unchanged: bootstrap 48, governance 26,
infrastructure 45 and baseline deployment 24. All eight operational/validation
workflows passed actionlint. Checkov 3.3.17 reported 91 passed, zero failed, zero
parse errors and 16 explicit skips across 62 resources. New exceptions cover
development single-AZ RDS, separately cost-approved Performance/Database Insights
and 30-day log retention; existing platform exceptions are retained. No scanner
failure was suppressed and no required GitHub gate was weakened.

Ignored raw logs and scan JSON are under `artifacts/phase6-offline/full-validation/`.
PR CI must pass on the published head before a code-only merge approval request.
