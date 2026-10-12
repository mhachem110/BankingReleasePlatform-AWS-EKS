# Historical Fargate redesign checkpoint

> Historical checkpoint evidence/instructions. For current merged PRs, active
> controls and AWS evidence limits, read [the 12 October reconciliation](RECONCILIATION.md).
> Earlier pending approvals and EC2 worker-role references below are superseded;
> the current approved compute is EKS Fargate. Do not repeat completed setup.

This report records the earlier parallel-workstream preparation. PRs #8/#9/#10 have since merged. Current readiness, tests and approvals are in PREPARATION-REPORT.md and ADMIN-REQUEST.md; historical counts and pending-PR statements below are not current deployment evidence.

# Phase 3 Fargate implementation report

## A. Phase completed

**Fargate source preparation complete; paid deployment pending approval.** Existing PR #8, infra -> dev, is updated for a Fargate-only Banking platform. This redesign changes only the infrastructure owner's assigned paths. No PR merge, Terraform apply, IAM modification or Phase 3 AWS resource creation is authorized or performed by this checkpoint.

Phase 2 remains COMPLETE. Its verified recovery run is https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38175836629. Existing backend protections, state identities and both Phase 2 roots remain unchanged. Read-back at this checkpoint confirms bootstrap BOOTSTRAP_STATE_READY=true and repository AWS_OPERATIONS_ENABLED=false.

## B. What was built

- infra/modules/eks and infra/environments/dev/platform: EKS banking-dev, explicit API access, private/restricted public endpoint, KMS encryption, five control-plane log types, three sequential private-subnet Fargate profiles, two pinned Fargate-compatible managed add-ons and a new cluster-specific IAM OIDC provider.
- CoreDNS runs on Fargate explicitly. The controller profile also schedules Metrics Server; the namespace-wide banking-dev profile schedules both APIs. Managed EC2 workers, node launch templates/disks/AMI pins and Pod Identity association are removed from the AWS source.
- Existing network/registry modules retain six subnets across two AZs, single NAT/IGW, isolated database routes, S3 gateway endpoint, encrypted flow logs and two immutable/scanned ECR repositories.
- scripts/infra: strict protected input/saved-plan guards, role/service-linked-role/version/schema preflight, read-only post-apply verification, exact IRSA-trust export, additive administrator-policy generator and reproducible cost estimate.
- infra-operations.yml retains OIDC, two protected approvals, exact same-run saved-plan SHA256/configuration validation and native state locking. Terraform validation retains credential-free tests and Checkov.
- iam/phase3 records the reviewed upstream controller policy provenance. ADMIN-REQUEST.md, DEPLOYMENT.md, ARCHITECTURE.md, COSTS.md and INTERFACE.md document prerequisites and the Chat 2 handoff.

## C. How it works

EKS runs the Kubernetes control plane. Fargate profiles tell AWS which namespaces/labels should receive a private compute environment for each Pod. Fargate's execution role permits infrastructure image pulls; controller application AWS calls use a distinct IRSA workload role trusted through this cluster's actual issuer. GitHub job authentication still uses the existing GitHub provider and protected bootstrap environment, independently of cluster IRSA.

Payment calls Account through an internal Kubernetes Service on port 8080. A later authorized controller/ALB deployment uses IP targets; no ALB is created by these Terraform profiles. Chat 2 owns all chart/application/release changes. No file in Helm, apps, tests, scripts/deploy or application workflows is edited by this redesign. Earlier chart files remain in PR #8's existing history and need Chat 2's reviewed Fargate replacement.

One NAT is a development availability/cost tradeoff. Fargate does not enforce AWS VPC CNI NetworkPolicies or topology spread constraints. Its EKS-managed SG has self traffic and broad default outbound access. These limitations are explicitly documented; no production isolation or even-AZ-placement claim is made.

## D. Tests and results

Actually executed locally:
- Terraform fmt check and backend-disabled, read-only-lockfile init/validate for seven configurations: passed.
- 13 Terraform mock tests: 3 backend, 2 network, 1 registry, 5 Fargate EKS and 2 integrated platform tests: passed.
- 33 infrastructure Python regressions: passed (gates, exact policies, IRSA subject/audience, profile/selectors/health, schemas/compute compatibility, saved-plan scope and costs).
- 48 existing bootstrap Python regressions: passed, including the offline AWS 6.68.0 lifecycle representation regression. These tests make no AWS changes.
- 7 existing Helm tests: passed read-only against the retained chart baseline. They do not verify Chat 2's in-progress chart.
- 23 existing governance Python tests: passed unchanged.
- Actionlint for the two changed Terraform workflows and git diff whitespace validation: passed.
- Checkov 3.3.17: 43 passed, zero failed, 11 documented scoped exceptions, zero parsing errors on the local Fargate source. Exceptions retain backend lifecycle/log-retention, ECR CMK deferral and restricted public EKS/version-scanner limitations; no new broad scanner exclusion.
- Upstream controller v2.14.1 IAM JSON was fetched and compared semantically to the retained policy; match confirmed and SHA256 recorded.

PR #8's current GitHub check results must be inspected on the pushed Fargate commit; historical EC2-run success is not evidence for this redesign. The PR page carries current checks.

Not executed: live resource plan/apply, effective SCP/quota evaluation, actual add-on pins/schemas in Ohio, cluster/Pod health, controller IRSA token exchange, Helm releases or ALB traffic. Post-apply verifier tests use synthetic responses; they do not establish an existing live Banking cluster.

## E. What the owner/administrator must do

Review PR #8 and the consolidated ADMIN-REQUEST.md. Administrator supplies/authorizes the three prerequisite roles, required existing service-linked roles, actual key, operator/deployer identities and quotas/permissions. Add BankingReleasePlatformPhase3 separately; preserve both current inline policies and both GitHub trust relationships. No general IAM role-creation grant is requested for the training user.

The new EKS OIDC provider needs explicit creation/tagging approval; Terraform manages that provider only, not roles. Exact controller IRSA trust is exported after the real cluster issuer is verified, then applied by the administrator to the dedicated controller role before Chat 2 installs it.

Use the complete PLATFORM_INPUTS_JSON shape and Console paths in DEPLOYMENT.md. Confirm actual compatible Fargate add-on pins and approved Kubernetes API source addresses. Approve the live plan operation separately; then approve the ACTUAL saved resource plan and costs at the protected apply gate. Current AWS gate stays false.

Planning costs: infrastructure with CoreDNS/Metrics Server is about $137.53/month before usage. Full assumed nine-Pod release is $198.08/month before ALB, traffic and telemetry; $205–225 is a light-usage allowance excluding ALB, not a cap. API Pods at 250m/512Mi bill 1GB after overhead. COSTS.md cites regional SKUs and exclusions.

## F. Checkpoint

Review the Fargate commit's real PR checks, architecture, plan guard, administrator policy request and cost model together. Confirm no managed node group/launch template/Pod Identity association and three correct private profiles. Confirm deployment remains blocked until prerequisite identities, real plan/cost approval and protected GitHub reviews are present.

Before merging the app work, synchronize it with the approved infrastructure baseline and reconcile charts. The installed feature/app path policy blocks some newly assigned Helm/deploy/workflow paths; request a scoped owner-reviewed governance change rather than bypassing it. No governance setting is changed in this checkpoint.

## G. Next step

Owner review of PR #8, consolidated administrator response and authorized live resource plan. Chat 2 completes application/Helm CI/CD against INTERFACE.md. No paid deployment or merge proceeds automatically.
