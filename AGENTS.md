# Repository working rules

## Reuse these branches

- `feature/app`: Account/Payment APIs, tests, Docker and application documentation. Owner-authored application releases may also change helm/banking/**, scripts/deploy/** and exactly app-ci.yml, app-validation.yml, app-publish.yml, app-deploy.yml under .github/workflows. No Terraform/HCL, CODEOWNERS, IAM, shared infrastructure, governance or other GitHub configuration. These release exceptions retain cloud ownership and require the verified cloud-owner author.
- `bootstrap`: Terraform backend, S3 state, GitHub OIDC connectivity and bootstrap configuration.
- `infra`: Terraform AWS networking, VPC, EKS, ECR, RDS and monitoring; Helm, GitHub workflows, IAM artifacts and shared repository governance. Cloud engineers may make reviewed cross-cutting application changes here alongside cloud changes.

All three submit PRs into `dev`. Do not create per-phase branches or other feature branches. Use one active PR per working branch and complete one approved workstream before starting another on that branch.

Promotion PRs are only `dev -> stage`, `stage -> uat`, and `uat -> main`. `dev` is the default branch; `main` is production-approved code. Never push development changes directly to these environment branches.

After a PR merge and before the next change, fetch origin, synchronize the working branch with its matching remote, then merge the latest `origin/dev` using ordinary Git merges. Stop on conflicts or command failures; preserve commits. No force pushes, history-rewriting rebases, destructive resets, or deletion of reusable branches. Keep automatic branch deletion disabled.

The original Phase 1, governance and Phase 2 PRs (#1, #2, and #3) are merged; their temporary source branches were retired after ancestry verification and explicit user approval. Preserve their PR records. Use only `feature/app`, `bootstrap`, and `infra` for new work. See `.github/governance/reusable-branches.md` for synchronization and promotion rules. This file is not approval to merge a PR or perform AWS operations.

## Keep authorization separate

Branch names select the workstream, not an AWS role or deployment environment. Preserve environment branch protections and existing required checks; add checks only after real runs prove they are available. Never weaken a gate to make a PR mergeable.

The cloud owner is currently only the verified GitHub user mhachem110 (ID 150286776). Separate update-only rulesets authorize that user to maintain bootstrap/infra and merge protected refs through PRs; they do not bypass the original protection rulesets. Do not add blanket administrator bypasses. Required independent code-owner approval stays pending a second eligible reviewer. The trusted metadata policy in governance PR #2 rejects application changes to sensitive/unknown files and validates only the six approved routes; its aggregate becomes mandatory only after observed execution. Never check out or execute PR-provided code in pull_request_target jobs or grant those jobs AWS secrets/OIDC tokens.

Bootstrap scope and shared exceptions are defined by scripts/governance/validate_pr_paths.py after its reviewed merge. Changing that policy, CODEOWNERS or generic workflows requires an infra/security PR. Maintain only real verified owners; do not invent teams or usernames.

GitHub environment reviewer approvals, OIDC trust conditions and IAM resource permissions are separate controls. The working branch named `bootstrap` is not the GitHub environment named `bootstrap`. Follow the existing manually approved deployment workflow from reviewed `dev`; do not expand AWS trust to working branches merely because they exist.

Work only within the approved project phase and stop at its checkpoint. No PR merging, AWS resource provisioning, IAM changes or charge-incurring AWS operations without explicit user approval. Code review or a GitHub PR merge does not authorize AWS operations.
