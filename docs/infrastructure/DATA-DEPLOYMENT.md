# Protected Phase 6 data plan/apply — prepared, disabled, never run live

Run Phase 3 first using its existing protected workflow, exact inventory and state.
This workflow creates neither EKS nor IAM roles/keys. It uses the verified existing
platform interface and a distinct native-locked data state key in the same protected
bucket. No infrastructure is rebuilt or adopted. There is no destroy/update/recovery
mode. Partial deployment requires a separately reviewed bounded recovery operation.

## Actual prerequisite interface

The single [administrator request](ADMIN-REQUEST.md) is authoritative. The data root
requires actual VPC ID, two isolated database subnet IDs, active cluster SG, data key,
PostgreSQL 17 patch/class, RDS monitoring role and approved existing SNS topic.
`scripts/infra/data_guard.py` rejects unknown/duplicate fields, credentials, wrong
account/Region, missing separate authorization and unsafe IDs/classes. Its exact
21-entry creation audit checks database/privacy/encryption/backup/deletion/size,
subnets/SG, parameters, queues/retry/retention, three logs, five alarms and tags.
Computed queue policies are bound to the reviewed module fingerprint and verified
against actual AWS attributes after apply. Module changes require contract review.

The preflight reads actual account, Phase 3 cluster, monitoring role/trust/managed
policy, RDS service-linked role, key, SNS destination, orderable engine/class and
name collisions. It compares the actual managed session-cap document with both its
approved digest and the locally rendered scope. It does not create/repair IAM, keys,
queues, secrets or topics and does not retrieve a credential value. A denied read is
a blocker with its original AWS diagnostic, not permission to broaden access.

## Protected variables and cost review

Use the existing `bootstrap` environment, preserving reviewer/dev-only restriction,
no admin bypass, AWS_ROLE_ARN, immutable OIDC trust and completed backend settings.
Both AWS_OPERATIONS_ENABLED and DATA_OPERATIONS_ENABLED must be explicitly true
for a specifically authorized data plan window; default/missing values disable it.
No working branch gains OIDC trust. These flags are configuration gates, not approval.

`DATA_INPUTS_JSON` contains exactly:

```json
{
  "vpc_id": "ACTUAL_PLATFORM_VPC_ID",
  "database_subnet_ids": ["ACTUAL_ISOLATED_SUBNET_1", "ACTUAL_ISOLATED_SUBNET_2"],
  "cluster_security_group_id": "ACTUAL_CLUSTER_SG_ID",
  "kms_key_arn": "ACTUAL_APPROVED_DATA_KEY_ARN",
  "engine_version": "ACTUAL_SUPPORTED_17_PATCH",
  "instance_class": "ACTUAL_APPROVED_CLASS",
  "monitoring_role_arn": "ACTUAL_APPROVED_MONITORING_ROLE_ARN",
  "alert_topic_arn": "ACTUAL_APPROVED_SNS_TOPIC_ARN"
}
```

Optional cost_center is only an actual assigned value. These markers are inert review
templates, not deployable values. DATA_SESSION_POLICY_ARN is the actual approved
`BankingReleasePlatformPhase6Session` managed policy; DATA_SESSION_POLICY_SHA256 is
the canonical digest printed in data_iam.py's review.json. The role's identity rights
and this restrictive session cap are separate controls. Policy creation is an
administrator operation outside this workflow and still requires specific approval.

`DATA_COST_REVIEW_JSON` needs actual account/Region, matching engine_version and
instance_class, reviewed_by, observed_at within 24 hours, pricing_evidence,
positive numeric monthly_usd_upper_bound/migration_usd_upper_bound, max_storage_gib=40,
capacity_and_connections_approved=true, key_policy_reviewed=true and
alert_delivery_approved=true. included_components must cover exactly:
rds, gp3_max_storage, backups_snapshots, cpu_credits, secrets, sqs, kms, logs,
metrics_alarms, monitoring_pods, data_transfer and migration_surge. These are reviewed
estimates, not observed spend. Stale/incomplete/changed review blocks apply. The
actual plan, retention, growth and usage assumptions still require personal review;
the receipt does not enforce a billing cap or guarantee those estimates.

## Authorized execution sequence — future only

1. Verify all actual prerequisites and recent cost evidence; merge reviewed workflow
   code. Request specific data-plan authorization separately from the first EKS plan.
2. Dispatch Protected Banking data services from reviewed dev, operation plan. The
   existing bootstrap protection requires owner review before OIDC authentication.
3. Inspect data-plan.txt, data-plan-review.json, data-prerequisites.json, cost receipt
   and the binary plan SHA256. Expect exactly 21 managed creates: prerequisite,
   SG/ingress, subnet/parameter groups, RDS, source/DLQ, redrive/allow/TLS policies,
   three logs, metric filter and five alarms. No IAM/key/SNS/bucket/EKS/ALB resources.
4. Only after approval of actual plan/costs, dispatch apply with
   APPLY-REVIEWED-PHASE6-PLAN. Its plan job generates a new same-run plan; inspect
   that actual artifact before approving the second protected apply deployment.
5. Apply compares plan digest, non-secret inputs, backend, cost receipt and audit
   (including source/module/session-policy hashes), rechecks live prerequisites and
   applies only the binary saved plan. It verifies actual database/queues/SG/logs/alarms
   and requires a subsequent zero-change Terraform plan. Expired artifact, changed
   state/policy/input/cost, name collision or failed verification stops the job.
6. Return both operation switches to false after the authorized window, including
   failure. Preserve native state/lock objects and retained snapshots/backups/key/logs.

Service verification is not application acceptance. Separately authorize runtime
users/secret injection, explicit forward migrations and data-enabled Helm release.
Run actual TLS/DDL denial, durable Pod replacement, idempotent payment/outbox/receipt,
SQS poison/redrive, Fargate log ingestion, per-Pod scrape/dashboards, delivered alerts
and exact rollback/recovery acceptance. The project remains unfinished until these
mandatory live tests pass. Cleanup, schema recovery and credential rotation have
their own explicit approval boundaries; never downgrade/drop schema during rollback.

Sources: [RDS-managed credential permissions](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html),
[Enhanced Monitoring trust/PassRole](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.Enabling.html),
[pinned credential action inputs](https://github.com/aws-actions/configure-aws-credentials/blob/e1253824e5c10ff9df46874f81ed3ec929e19cfd/action.yml).
