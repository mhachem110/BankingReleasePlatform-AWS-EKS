# One infrastructure deployment entry

`project-deploy.yml` presents **Infra CI/CD**. It validates scope, runs the existing
credential-free Terraform/Helm/security CI, then calls the foundation, network,
platform-cap publication, platform, an ephemeral private CodeBuild runner,
runtime IAM/alerts, dev/prod data and Kubernetes
bootstrap workflows from the same Git commit. Native bootstrap environment
reviews, saved binary hashes, backend locks and live verification remain intact.
Destroy stays outside this entry. An apply cannot cancel an earlier project run.

Select `target=project`, `operation=apply` and
`APPLY-REVIEWED-BANKING-PROJECT` only after the complete deployment prerequisites
below are implemented and verified. This is a development change, not evidence of
a live cluster or a completed project. No project deployment has been dispatched
for this change.

The foundation returns its actual key/operator. The network returns its actual
owned VPC/default group. These outputs replace stale dependency IDs for the next
stage without modifying GitHub environment variables. The platform returns actual
subnets and cluster group only after live verification and a zero-drift plan;
the data stages consume those outputs and the runtime stage supplies exact
monitoring roles, alert destinations and managed data-policy hashes. Planned/computed identifiers cannot stand
in for an applied dependency. A first-time plan cannot resolve every later plan
until its dependencies exist; apply progresses through the saved-plan reviews in
the same run.

A complete unchanged foundation skips write credentials and apply. A verified VPC
is reused without initializing the smaller seed Terraform root over full platform
state. Unknown state, policy drift, key substitution or partial foundation state
stops without automatic destruction. CI reuses the checksum-verified provider
within its job, avoiding repeated large provider downloads across Terraform roots.
No states or credentials enter that cache.

The final job reports each real stage result and requires actual verification
outputs before calling an apply successful. A skipped or failed stage is never
deployment proof. Terraform success also does not prove Kubernetes readiness,
application behavior, production-data isolation or rollback.

Platform-cap publication now generates the three policy documents from the actual
verified key, operator, VPC and default group. Their dedicated native state is
resumable; policies are session restrictions and are never attached to bootstrap.
Creation and cleanup retain separate saved-plan approvals and live identity checks.

The runner is a project-scoped CodeBuild job in two private application subnets.
It starts for one approved GitHub Actions deployment job, uses the same short-lived
OIDC role as the protected workflow, and exits when that job ends. There is no
permanent machine or static AWS access key. GitHub-hosted Ubuntu still runs CI,
Terraform and image publication. Only kubectl/Helm deployment and rollback use
the private runner; the EKS public endpoint stays restricted to its reviewed
operator CIDRs.

Before the first full run, the account owner must authorize a GitHub App
CodeConnections connection for this repository in us-east-2, set the actual
connection ARN as `CODEBUILD_GITHUB_CONNECTION_ARN`, and add the exact CodeBuild
bootstrap actions in `docs/deployment/codebuild-bootstrap-policy-additions.json`.
The protected runner stage fails before planning if that ARN is missing. The
CodeBuild uses small, non-privileged compute. Standard GitHub-hosted jobs rescan
the published digests with Docker/Trivy and pass the manifest hash to the private
deployment job. Each private job consumes build minutes, while the project
itself has no idle runner.
Review current Ohio build-minute pricing, NAT traffic, CloudWatch logs and
the EKS/RDS baseline in the saved plan approval. Do not infer a live cost from
the configuration alone.

Kubernetes bootstrap installs the pinned ALB controller with dedicated IRSA,
the Fargate log-router ConfigMap, and dev/prod TLS migrations and credentials
from verified RDS interfaces. The Fargate execution boundary needs the narrow
application-log statement in `docs/deployment/fargate-boundary-addition.json`
before CloudWatch application log delivery can work. No AWS deployment of these
new stages has been performed or claimed.

The final evidence job fails if the runner or Kubernetes stage is skipped.
Application publication, protected dev/prod rollout, integration and recovery
acceptance remain separate App CD/App Rollback operations after infrastructure.
Terraform Destroy now has separately reviewed targets in dependency order:
`applications` (Helm, namespaces, controller and exact ECR digests), `dev-data`
and `prod-data` (explicit final-snapshot retention), `runtime-prerequisites`,
`runner`, `platform`, then unused project IAM/key/policies. Each Terraform
target inventories one native state, saves a destroy-only plan and checks its
hash again after a second protected review. The applications target compares
the Kubernetes and ECR inventories before removal and publishes the cleanup
receipt required by later targets. The S3 state bucket is never deleted.
Retained encrypted RDS snapshots block the runtime KMS key retirement until
an additional explicit retention decision is made. No cleanup has been run.
App CD now combines publication/deployment, and App Rollback is a separate protected
recovery entry. See [the presentation walkthrough](PIPELINE-PRESENTATION.md) for
controls and the precise readiness limits. Existing required checks and protections
stay in place. The complete offline suite and PR checks validate code only;
no AWS apply or destroy has been dispatched for this change.
