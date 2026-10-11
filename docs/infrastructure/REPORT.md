# Phase 3 implementation preparation report

## A. Phase Completed

Phase 2 is **COMPLETE**, with actual AWS evidence in [COMPLETION.md](../phase2/COMPLETION.md). Phase 3 **code preparation is complete; deployment is pending owner approval and administrator prerequisites**. Work uses existing `infra`, synchronized normally with reviewed dev. No additional feature branch or paid infrastructure was created.

## B. What You Built

- `infra/modules/network`: two-AZ VPC, six subnets across three tiers, Internet Gateway, one NAT/EIP, distinct public/private/isolated routes, closed new default security group, free S3 Gateway Endpoint and encrypted flow logs.
- `infra/modules/registry`: separate Account and Payment ECR repositories, immutable tags, push scanning, AES256 encryption, safe untagged cleanup and protected tagged releases.
- `infra/modules/eks`: EKS 1.36 with private/narrowly allowed public endpoint, KMS secret/log encryption, five control-plane log types, hardened managed AL2023 workers, dedicated security groups/rules, explicit operator and namespace deployer access, five pinned managed add-ons and controller Pod Identity association.
- `infra/environments/dev/platform`: composed platform root and prerequisites, separate platform S3 state path. Both existing Phase 2 roots remain unchanged.
- `.github/workflows/terraform-validation.yml`: expanded credential-free Terraform/Python/Checkov/Helm PR validation.
- `.github/workflows/infra-operations.yml`: disabled-by-default manual OIDC plan/apply with existing protected bootstrap reviews, exact saved-plan hash, unchanged inputs and strict creation-only scope.
- `helm/banking`: separate Kubernetes objects for both APIs, private service DNS, digest images, probes/limits, non-root/read-only containers, disruption budgets, optional HPA and HTTPS Ingress disabled by default.
- Administrator policy generator, pinned official controller policy, collision/prerequisite checks, cost estimate, architecture, cleanup/deployment procedure and remaining-assignment matrix.

## C. How It Works

The VPC separates public routing, private compute and isolated future databases. NAT permits outbound access for private workers without exposing those workers publicly. EKS runs the Kubernetes control plane; the managed worker group runs containers. ECR stores built images. Helm packages the two APIs and their Kubernetes traffic/health/scaling configuration.

IAM service/node/controller roles are distinct, administrator-provided inputs. EKS access entries grant Kubernetes authorization separately from AWS IAM. OIDC authenticates a reviewed GitHub job; the environment controls approval, while session caps and permission policies limit AWS actions. This workflow keeps the existing Banking bootstrap subject and Retail relationship intact.

## D. Tests and Results

Local actual checks:

- Seven Terraform configurations initialized/validated without AWS backends or credentials across preparation; formatting passes.
- Eight new mock Terraform tests pass: two network, one ECR, three EKS, two integrated platform. They create no AWS resources. Three existing state-module tests remain covered by CI.
- Thirteen infrastructure policy/workflow regression tests, seven Helm rendering/lint/safety tests and 48 existing bootstrap tests pass.
- Twenty-three existing governance tests pass. The branch/path policy is unchanged.
- actionlint passes both changed workflows.
- The initial GitHub run exposed missing Linux content checksums in the new Windows-generated provider locks. Terraform retrieved signed Windows/Linux packages to populate both verified platform hashes; a regression test checks all four new locks while CI keeps `-lockfile=readonly`.
- Checkov 3.3.17: 88 passed, zero failed, eleven explicit scoped exceptions; no parsing errors. Exceptions cover four existing state-bucket deferrals plus ECR customer-KMS deferral, two 30-day log-retention choices, controlled EKS public-access checks and stale scanner version enumeration, counted per module/root scan occurrence. No global check suppression is added.

Offline fixtures are fictional. Their EKS add-on/AMI versions are deliberately test-only and are never deployment defaults. Runtime versions must be obtained from AWS, pinned in approved inputs and checked for compatibility before a live plan.

Live Phase 3 Terraform plan/apply, effective service-role permissions, SCPs/quotas, node registration, add-on health, Kubernetes endpoint reachability, image publication and live Helm deployment are **unverified**. Those require the consolidated administrator response and an approved protected workflow execution. No success is implied by static checks.

## E. What I Must Do

Review the infra PR, [administrator request](ADMIN-REQUEST.md), [cost estimate](COSTS.md) and [exact deployment instructions](DEPLOYMENT.md) together. The administrator must supply four authorized service roles, an approved symmetric encryption key, distinct operator/deployer identities, effective-policy/quotas confirmation and operator/runner CIDRs. Keep both existing inline policies unchanged; the generated additional policy grants exact Banking PassRole/key/platform-state access only.

Supply `PLATFORM_INPUTS_JSON` only after actual values and compatible versions are known. Leave `AWS_OPERATIONS_ENABLED=false` until a specific plan is authorized. Review the resulting real creation plan and costs before approving apply. The prepared workflow creates no roles and never manages the S3 bucket.

## F. Checkpoint

The PR must show green real GitHub checks before merging. No nonexistent required status check has been activated. The active governance aggregate remains required; neither branch protections nor environment approvals were changed. The manual plan/apply workflow is not executed by CI or code merge.

After later approved deployment, its verification must show ACTIVE cluster/node group and all five add-ons, both ECR policies and a zero-change platform plan. The first-deployment workflow intentionally rejects mutation/deletion of existing resources, including partially deployed resources needing repair; such recovery needs a reviewed bounded update procedure rather than silently rerunning initialization.

## G. Next Phase

The next authorized action is review of this code/IAM/cost package, followed by administrator prerequisites and a protected live plan when approved. Paid deployment remains gated. Phase 4 will install the controller/applications and demonstrate healthy pods/internal communication/authorized HTTPS ingress. RDS, events, release scanning/CD/rollback, dashboards/security findings and measured cost evidence remain assigned to later phases in REQUIREMENTS.md.
