# Security and path governance

GitHub protections, trusted path classification, CODEOWNERS, environment approvals, OIDC trust and AWS IAM permissions are independent controls. Preserve each one; passing one does not authorize another.

## Workstream scope

The trusted metadata validator is `scripts/governance/validate_pr_paths.py`. It accepts only `feature/app`, `bootstrap` and `infra` into `dev`, and the approved promotion routes `dev` to `stage`, `stage` to `uat`, and `uat` to `main`. It evaluates both current and previous names for renames, rejects generated/private artifacts, and fails closed on truncated or changing GitHub metadata.

- `feature/app` may change application source, tests under `apps/tests/`, Docker/Compose and app files. Cloud-owned Helm release paths and named app workflows retain their verified cloud-owner restriction.
- `bootstrap` is limited to backend/OIDC/state-bucket foundations, `scripts/bootstrap/` and their explicitly listed workflow/root exceptions. It does not authorize EKS, shared infrastructure or arbitrary IAM changes.
- `infra` is cloud-owner authored and must contain at least one cloud-owned path. It can include reviewed cross-cutting application changes but cannot change branch routing outside this policy.

Sensitive and shared changes include `.github/`, all Terraform/HCL/backend files, `infra/iam/`, Helm, governance, bootstrap/infra/deploy automation and `CODEOWNERS`. The metadata check validates paths and trusted GitHub metadata; it does not review file contents or replace tests/scanners. Never execute PR-provided code in `pull_request_target` or grant untrusted PR workflows AWS credentials/OIDC.

## Authorization and review

Use only verified maintainers in CODEOWNERS. Do not invent teams, add blanket bypass actors, weaken branch protections, change required checks to hide a failure, or enable automatic branch deletion. Required independent code-owner review remains subject to an eligible second reviewer. Work branches are not GitHub environments and do not grant AWS access. Keep OIDC audience/subject restrictions and protected environment branch/reviewer rules exact. Only approved jobs receive `id-token: write`; use temporary credentials and least-privilege roles.

Ruleset import examples live in [`.github/rulesets/`](../rulesets/). Active repository settings in GitHub remain authoritative; these JSON files do not apply themselves. See [branch workflow](reusable-branches.md), [application release scope](application-release-scope.md), and root [AGENTS.md](../../AGENTS.md).
