# Application deployment: Phase 4 and Phase 5 checkpoint

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
which Chat 1 owns. Namespace creation is deliberately outside the Helm release:
helm/banking/namespaces/banking-dev.yaml is prepared for the infrastructure owner.
The deployer neither creates namespaces nor needs namespace-administration permissions.

ALB ingress defaults off. Rendering requires enabled=true, approved=true, host,
certificate ARN, subnet IDs and security-group IDs. It uses IP targets and HTTPS,
defaults to internal scheme and does not let the controller edit backend security-group
rules. Chart approval flags are configuration guards, not replacements for human approval.
No pipeline enables ingress. Controller/ACM/DNS/security-group setup and ALB expense
require separate approval through Chat 1.

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

The initial Helm baseline was copied exclusively from PR #8 commit
41fae7fdfa9c10bf95ff3f2f2e733e80a58b2d6e. No infra history was merged or modified.
The application chart retains baseline names/selectors so existing releases can upgrade.
The baseline's EC2 network policies/topology spreading were removed for Fargate.
Schema changes and the new 0.2.0 chart reject unknown legacy values; the deployment
uses --reset-values plus explicit environment/images files to avoid carrying EC2 values.

PR #8 is owned by Chat 1 and remains unmodified by this chat.
Before application merge: compare the final Fargate PR #8 Helm changes, reconcile in
feature/app, rerun offline checks, and wait for the infrastructure baseline's approved
merge. Then fetch, synchronize feature/app with origin/feature/app and merge origin/dev
using ordinary merges. Stop on conflicts or Git failures. No force pushes or rebases.

The installed scripts/governance/validate_pr_paths.py rejects helm/, scripts/deploy/,
.github/ and docs/deployment/ from feature/app. The owner's explicit Phase 4/5 assignment
authorizes preparing them here; it does not alter the installed gate.
The application PR must remain draft/blocked until a separate reviewed infra/security
decision resolves the ownership policy. No shared governance, CODEOWNERS or required
check was weakened. Do not request merge while this check fails.
Only add Application CI as a required check after observing actual successful runs.

Read ENVIRONMENT.md, CHAT1-REQUIREMENTS.md, RUNBOOK.md and REPORT.md for setup and evidence.
