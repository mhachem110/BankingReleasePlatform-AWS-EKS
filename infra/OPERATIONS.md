# Deployment and operations

## Deployment

Use the protected **Infra CI/CD** workflow from reviewed `dev` with `target=project`. Run `operation=plan` first. Review the actual inventory, Terraform plan, IAM/KMS changes, tags and current cost inputs. Apply requires its own explicit user authorization plus the existing protected environment reviews; the workflow validates and applies the exact saved plan. Resume is allowed only when the workflow verifies state and the real dependency outputs. A skipped or failed stage is not a successful deployment. Do not replace actual output values with guessed IDs or ARNs.

The project workflow keeps the infrastructure sequence resumable: IAM prerequisites, VPC seed, EKS/Fargate platform, runtime prerequisites, Kubernetes bootstrap, application image publication, dev deployment, data services, integration checks, and separately approved production promotion and monitoring/recovery verification. The separate workflows retain state boundaries, OIDC scopes, immutable artifact/digest checks, concurrency controls and reviewer gates. Application deployment runs on the temporary private CodeBuild runner; the EKS endpoint is not made unrestrictedly public.

Follow current workflow inputs and [assignment acceptance criteria](REQUIREMENTS.md). After each deployment stage, retain its run link and output artifact. Confirm a clean subsequent plan and live health evidence before marking the stage complete. Restore one-time operation switches to their disabled state as directed by workflow summaries.

## Application recovery

Use the protected App Rollback workflow against the intended GitHub environment and namespace. It verifies the requested healthy release and its immutable image digests, inspects Helm history, then rolls back to the known healthy revision and verifies rollout and service smoke checks. A successful rollback does not turn a failed deployment into a successful release. Preserve workflow logs, deployment history, image digests and health results. Never clear Helm history or delete a namespace to make a release appear healthy.

Database migrations are forward-only. Keep schema changes compatible with both current and prior images; Helm rollback does not reverse database state. For a database or SQS incident, preserve event/payment identifiers, payload hashes, timestamps, retry counts and receipts. Repair only the specifically reviewed row/message; never reset all records, reseed existing accounts, purge a queue or redrive invalid payloads indiscriminately. See [data and event handling](DATA.md).

## Monitoring and incident response

Use [monitoring configuration](monitoring/README.md) with the protected workload configuration. Alerts include a runbook link to this file. Investigate API availability, storage readiness, error ratio, p95 latency, outbox backlog, SQS delivery and DLQ depth. Compare readiness and liveness: dependency failure should make the service unready without masking a process failure. Check CloudWatch logs, pod events, rollout history, Fargate placement, database connectivity/TLS, queue redrive policy and the last successful receipt. Do not claim alert delivery or live telemetry until a real receiver and cloud evidence have been verified.

The existing CloudWatch alarm description retains its previously deployed runbook string. Changing that Terraform attribute would modify the live alarm on a later apply and invalidate the reviewed data-module source hash, so this documentation-only migration leaves it untouched. The current operator procedure is this file.

For a failed rollout, stop dependent promotion, preserve evidence, and use the approved rollback path. For database recovery, maintain forward-only compatibility and recover the smallest identified item. For poison messages, quarantine and investigate; redrive only after the payload is understood and an authorized correction is in place. Record detection time, impact, owner, action, validation, image digests and follow-up work.

## Protected cleanup

Cleanup is a separate, destructive workflow and is intentionally not run as part of deployment or this repository cleanup. Obtain specific approval of the exact inventory, database deletion/snapshot choice and cost exposure before dispatch. Review a fresh destroy plan and its SHA256, dependencies, state lineage/serial, tags, ownership and protected apply gate. Never force unlock, remove state manually, target resources outside the reviewed state or use a creation workflow to destroy resources.

The dependency order is:

1. `applications`: ingress, application/controller workloads and releases; verify load balancers and controller-created network attachments are gone.
2. `dev-data`, then `prod-data`: inspect final snapshot retention, names, encryption-key dependencies and deletion protection. Retained snapshots remain billable and keep their KMS key in use.
3. `runtime-prerequisites`: remove only verified unused runtime dependencies.
4. `runner`: remove the project-specific CodeBuild runner after no deployment job depends on it.
5. `platform`: remove EKS/Fargate and then platform networking/registry in the reviewed dependency order. Explicitly handle EKS deletion protection before the destroy plan.
6. `vpc-seed`, `policy-prerequisites`, `iam-prerequisites`, `runtime-foundation` and `platform-caps`: remove only verified project-owned prerequisites after all consumer states/resources are absent.

Retain the shared S3 Terraform state bucket, versions and locks. Preserve unrelated Retail, CloudOpsTracker, account-shared, administrator-owned and other-project resources. Do not delete a key while any retained cluster, database, snapshot, log or queue uses it. Confirm the actual post-cleanup inventory, state and unrelated-resource integrity. Deleting application Pods alone does not stop EKS, NAT, public IPv4, logs, snapshots, keys or ECR storage charges.

## Cost review

`infra/cost/cost-model.json` and `infra/cost/shared-demo-prices.json` feed the offline cost estimators. Run `python scripts/infra/cost-estimate.py` and `python scripts/infra/shared-demo-cost.py` for model outputs; `python scripts/infra/cost-exposure.py` reports persistent exposure. These are estimates, not approved spend limits or actual bills. Before apply or cleanup, review current Ohio prices and quantities for EKS, NAT/IPv4, CodeBuild minutes, RDS storage/compute/backup/snapshots, SQS/KMS, ECR, ALB/traffic, logs and metrics. Record actual billing evidence for any claimed savings.
