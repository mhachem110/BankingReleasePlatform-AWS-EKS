# Pipeline walkthrough

The normal presentation has five entry points. Existing bootstrap/IAM setup and
read-only role audit workflows remain maintenance tools. Repository security
policy remains an independent required check. Historical Actions runs remain
available as evidence.

| Entry | Purpose | Controls implemented in source |
| --- | --- | --- |
| Application CI | Build and assess application changes | Locked NuGet restore with direct/transitive vulnerability audit, .NET checks, Helm safety, Trivy vulnerability/secret scans of saved container bytes; no AWS token |
| App CD | `publish` on dev; `deploy` the same digest pair through reviewed branches | Native environment approval, separate bounded OIDC role, scanned archive hashes, immutable ECR, trusted run receipts and branch ancestry, digest rescan, Helm timeout/readiness and failure rollback |
| Infra CI/CD | One ordered dependency run | Credential-free CI/Checkov, protected bootstrap jobs, actual dependency IDs, bounded session caps, reviewed binary plans, S3 locks, ownership checks, verified resource reuse |
| Terraform Destroy | Deliberate cleanup | Applications and exact ECR images first; RDS with explicit final snapshots; then runtime, runner, EKS/network and unused IAM. Selected native states, ownership checks and separately approved saved destroy binaries |
| App Rollback | Restore an earlier successful Helm revision | Same deployment lock/environment gate, successful deployment receipt, exact published digests, Trivy rescan, namespace RBAC and bounded rollout wait |

`app-validation.yml` and `app-publish.yml` are reusable application implementations.
Foundation, network, platform caps, platform, temporary runner and data implementations are reusable
stages behind Infra CI/CD. Keeping the code in small files makes its controls
readable while reducing separate deployment buttons. Existing CI check names are
preserved so current branch protections continue to recognize them.

## Availability example

The Account API dependency has a bounded timeout and cancellation. Payment code
uses a local database transaction, durable outbox and idempotency. A failed
dependency prevents the local operation from being committed. This demonstration
does not contact a real ATM or reverse an external bank debit.

Helm deployment waits for readiness and has a ten-minute operation timeout.
Failed upgrades/acceptance restore the prior revision. First-install failure is
cleaned up. Manual rollback selects a successful receipt and a matching retained
revision; it rejects arbitrary images and cross-environment receipts. Abrupt
runner loss or forced cancellation can interrupt recovery: the manual workflow
provides recovery after the runner is available. Application rollback does not
reverse database migrations or committed payments.

Two replicas, probes, disruption budgets and Fargate profiles provide the workload
availability controls. Two-AZ private subnets do not guarantee even Fargate Pod
placement. One NAT remains the documented training cost/availability tradeoff.

## Architecture and evidence to show

Draw GitHub-hosted CI and Terraform planning on the left; the protected CodeBuild
job in two private subnets on the right. The job obtains short-lived GitHub OIDC
credentials and uses namespace-specific EKS access entries. Show the same
scanned ECR digest pair promoted from banking-dev to banking-prod, the private
RDS and SQS/DLQ pair for each namespace, the transactional payment outbox, and
CloudWatch alarms to encrypted project alert queues. Explain that approval of a
Terraform saved plan, a GitHub environment and the AWS role are separate gates.

The current evidence is code and offline validation only. The CodeBuild GitHub
App connection, permission boundary for Fargate log shipping, live deployment,
production promotion, alert delivery and rollback demonstration need actual AWS
evidence before the trainer can present them as working. A final RDS snapshot
keeps the runtime KMS key in use; retirement must account for that dependency.
