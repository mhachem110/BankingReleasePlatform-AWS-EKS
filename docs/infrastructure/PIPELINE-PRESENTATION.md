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
| Terraform Destroy | Deliberate cleanup | Creation/cleanup mutually exclusive, same lifecycle lock, selected native state and ownership inventory, dependency checks, separately approved saved destroy binary |
| App Rollback | Restore an earlier successful Helm revision | Same deployment lock/environment gate, successful deployment receipt, exact published digests, Trivy rescan, namespace RBAC and bounded rollout wait |

`app-validation.yml` and `app-publish.yml` are reusable application implementations.
Foundation, network, platform caps, platform and data implementations are reusable
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

## Actual readiness

These source changes are not evidence of a completed live project. The runtime
foundation and platform session-cap publisher are coded; the full project entry
is still a draft. Runtime IAM and alert prerequisites, production data wiring,
private deployment runner registration, Kubernetes bootstrap and full paid
platform/data teardown must be finished before the final deployment.

Destroy currently supports unused prerequisite resources only. It deliberately
does not advertise complete EKS/RDS teardown. RDS final snapshots and retained
encrypted data require an explicit retention decision before key deletion.

No additional tests, AWS apply or AWS destroy runs were launched for this code
checkpoint after the owner's instruction to stop testing. Existing repository
checks and native deployment approvals have not been weakened.
