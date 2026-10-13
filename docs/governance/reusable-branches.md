# Branch workflow

The repository uses three reusable work branches. Changes go to `dev` through a pull request; environment promotion uses `dev` → `stage` → `uat` → `main`.

| Branch | Scope |
| --- | --- |
| `feature/app` | Account and Payment APIs, tests, Docker, application documentation, and the owner-authorized release paths listed in [AGENTS.md](../../AGENTS.md) |
| `bootstrap` | Terraform backend, S3 state, GitHub OIDC, and bootstrap configuration |
| `infra` | AWS infrastructure, Terraform, IAM artifacts, Helm, workflows, and shared governance |

`dev` is the development default. `stage`, `uat`, and `main` are protected promotion branches. Branch names select a code workstream; they do not select a GitHub environment or grant AWS access. Keep the protected deployment approvals, OIDC trust conditions, IAM policies, and required checks unchanged.

After a workstream PR merges, fetch `origin`, fast-forward the matching work branch to its remote, then merge the latest `origin/dev` with a normal merge. Resolve conflicts deliberately and preserve history. Do not force-push, rebase shared history, push development changes directly to an environment branch, or delete a reusable branch.

## Retired migration branches

The historical branches `feature/phase1-banking-apis`, `feature/phase2-terraform-bootstrap`, and `feature/repository-governance` were deleted after their PRs #1, #3, and #2 were confirmed merged and every branch commit was found in `dev`. Their commits and PR review records remain in repository history. Do not recreate these branches; use the reusable work branches above.

## Current controls

Repository rulesets remain authoritative. The `banking-working-branches` ruleset targets `feature/app`, `bootstrap`, and `infra`; protected environment branches have separate governance rules. Do not weaken a ruleset or add bypass actors to make a change easier to merge. See [security governance](security.md) and the root [AGENTS.md](../../AGENTS.md) for ownership boundaries and workflow rules.
