# Application deployment: Phase 4 and Phase 5 checkpoint

> Current handoff: the Banking platform, ephemeral CodeBuild runner, application
> publication/deployment, rollback, monitoring and protected cleanup source are
> integrated on the infrastructure workstream. The account owner reports the
> CodeBuild connection and bootstrap permissions are configured. The latest
> implementation changes have not been tested or deployed; live AWS and
> Kubernetes acceptance is the next jointly reviewed step. The phase notes below
> record the earlier application checkpoint and must not be read as current AWS
> deployment evidence. See [the current pipeline](../infrastructure/PROJECT-PIPELINE.md).

Prepared on the reusable feature/app branch in an independent worktree. No AWS calls,
ECR publication, Kubernetes deployment, IAM changes, ALBs or other paid resources were
performed. Live deployment remains pending Phase 3 and explicit approval.

## Helm resources

Release banking, development cluster banking-dev, namespace banking-dev, port 8080.
The chart contains Account/Payment Deployments, private ClusterIP Services,
non-token ServiceAccounts, three process-health probes, rolling upgrades with one surge
and zero unavailable Pods, five retained ReplicaSets, PDBs and configurable replicas.
Requests and limits are equal: 250m CPU / 512Mi memory per container. Containers use
UID/GID 1654, read-only roots, dropped capabilities, no privilege escalation and a
bounded writable /tmp. Default: two replicas per API; production values: three.

Payment validates accounts through
http://banking-account.banking-dev.svc.cluster.local:8080/.
The existing contract is Payment -> Account. Account does not depend on Payment.
No fixed application IP addresses or bidirectional dependency was introduced.
These are fictional in-memory accounts and simulated payments; storage is Phase 6.

No DaemonSet, host networking, host ports, topology spread constraint or NetworkPolicy
is installed. Amazon VPC CNI network policy does not enforce isolation on Fargate:
the infrastructure owner must approve the security-group and subnet boundary.
See [AWS networking limitations](https://docs.aws.amazon.com/eks/latest/userguide/cni-network-policy.html).
Guaranteed resources and task rounding follow
[AWS Pod sizing](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html).
At the defaults, the extra platform memory rounds each Pod to a 0.25vCPU/1GB Fargate task;
validate actual CapacityProvisioned annotations during the live demonstration.

HPA is optional and disabled. It requires a working Fargate-compatible Metrics Server,
which the infrastructure workstream owns. Namespace creation is deliberately outside the Helm release:
helm/banking/namespaces/banking-dev.yaml is prepared for the infrastructure owner.
The deployer neither creates namespaces nor needs namespace-administration permissions.

ALB ingress defaults off. Rendering requires enabled=true, approved=true, host,
certificate ARN, subnet IDs and security-group IDs. It uses IP targets and HTTPS,
defaults to internal scheme and does not let the controller edit backend security-group
rules. Chart approval flags are configuration guards, not replacements for human approval.
No pipeline enables ingress. Controller/ACM/DNS/security-group setup and ALB expense
require separate approval through the infrastructure operator.

## Workflows

| File | Trigger and scope |
| --- | --- |
| app-ci.yml | PRs into all environment branches and pushes to approved application/environment branches; no AWS credentials |
| app-validation.yml | Reusable .NET locked restore/build/tests, container build/DNS integration, Trivy scans, Helm lint/tests, Kubernetes schemas and actionlint |
| app-publish.yml | Manual reviewed-dev dispatch, explicit approval input, protected dev environment, disabled switch; publishes previously scanned archives to existing immutable ECR repositories |
| app-deploy.yml | Manual dispatch from matching environment branch; protected environment, disabled switch, exact artifact provenance, predecessor deployment evidence, digest rescan, Helm rollout/smoke/rollback |

All third-party actions use verified commit SHAs. Tool archives are checksum-pinned:
Helm 4.3.0, kubectl 1.36.0, kubeconform 0.8.0 and actionlint 1.7.12.
Trivy 0.75.0 uses a pinned ghcr.io container digest without the Docker socket or registry
credentials mounted into the scanner. HIGH/CRITICAL vulnerabilities and secrets block
publication/deployment; unfixed findings are not ignored.

A credential-free validation job builds once and scans the saved image archives.
The protected publication job loads those exact archives, verifies their hashes,
image IDs and source labels, then pushes unique immutable commit/run tags.
It records ECR digests in release.json. Deployment accepts only a successful
workflow_dispatch run of app-publish.yml from reviewed dev, with its commit already
an ancestor of the target environment branch. It pulls/rescans the same two digests
and deploys those digests; it never rebuilds during promotion.

Dev -> stage -> uat -> main PRs remain the only promotion routes.
Deploy environment prod maps to main, cluster/namespace banking-prod.
Each later deployment requires successful predecessor-environment evidence for the exact
same manifest hash/publication run. Evidence artifacts expire after 90 days; missing,
expired or older-than-the-100-run search window evidence blocks deployment.
A new approved dev publication/deployment is needed if evidence is no longer retained.

The same approved dev ECR repositories hold the promoted pair; later clusters/namespaces
and permissions must be independently approved before enabling those environments.
Stage/UAT/production are prepared designs, not provisioned environments.

Helm 4 uses --rollback-on-failure and explicit --wait=watcher. A rollout or integration
failure collects events/history/logs and restores the exact pre-upgrade revision,
then verifies readiness and reruns smoke tests. Failed first installation removes the
application release, preserving the separately owned namespace. A rollback failure
remains a failed job requiring operator recovery. Failure never generates promotion
evidence. See [Helm upgrade](https://helm.sh/docs/helm/helm_upgrade/).

## Integration and governance checkpoint

PR #8's approved Fargate infrastructure and PR #10's approved governance/access
contract are now merged into dev. feature/app synchronized with that history through
ordinary merges, preserving the newer application chart and all infrastructure code.
The application chart retains baseline names/selectors so existing releases can upgrade.
EC2 network policies/topology spreading were removed for Fargate. Strict values schemas
and chart 0.2.0 reject unknown legacy values; deployment uses --reset-values plus
explicit environment/image files to avoid carrying old settings.

The installed trusted ownership policy permits owner-authored feature/app changes only
in helm/banking/**, scripts/deploy/**, docs/deployment/** and the four named application
workflows, alongside the existing application scope. Terraform/HCL/backend inputs,
CODEOWNERS, IAM, infrastructure, governance and unrelated workflows remain restricted.
The required Repository security policy passes; all existing protection rules remain.
PR #9 is merged, followed by final infrastructure preparation PR #11. Live publication
and application/infrastructure deployment remain separately authorized operations.
See [the current reconciliation](../infrastructure/RECONCILIATION.md). Only add Application CI as a required check after its trusted
workflow is installed in dev and successful execution is observed.

Read ENVIRONMENT.md, CHAT1-REQUIREMENTS.md, RUNBOOK.md and REPORT.md for setup and evidence.

## Prepared persistence, messaging and monitoring

Chart 0.3.0 adds opt-in PostgreSQL connection/CA references, payment-only IRSA/SQS
references, dependency readiness and per-Pod metric discovery. Defaults keep memory
mode and messaging disabled. `APP_DATA_OPERATIONS_ENABLED=true` and validated
`APP_RUNTIME_VALUES_JSON` require separate explicit dev authorization; no credentials
belong in those values. Existing digest provenance, environment reviews and rollback
gates still apply. See [data and events](DATA-AND-EVENTS.md),
[incident recovery](INCIDENTS.md), [monitoring](monitoring/README.md),
[architecture](ARCHITECTURE.md) and [demonstration material](DEMO-PRESENTATION.md).
The new offline data suite uses only isolated local Docker fixtures. Live acceptance
and alert delivery remain pending.
