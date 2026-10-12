# Application release scope — separate owner review required

PR #8 was merged through the normal merge API at 9ee705ef0993a38a1319646b797f75a3e8e6cc98 after all checks passed. PR #9 is retained and synchronized through an ordinary merge. The trusted dev policy currently rejects its application release paths; a PR cannot authorize itself by changing that policy.

This infra PR proposes exactly helm/banking/**, scripts/deploy/**, docs/deployment/** and four exact workflow files: .github/workflows/app-ci.yml, app-validation.yml, app-publish.yml, app-deploy.yml. Release-path changes additionally require verified cloud-owner author ID 150286776. Ordinary API/test paths retain their current author rules. Terraform/HCL/backend files and CODEOWNERS remain forbidden to feature/app even inside release directories. Renames validate both paths, artifacts remain blocked, and repository identity/pagination/head-race checks remain strict.

CODEOWNERS, branch routes, all native rulesets, mandatory Repository security policy, trusted pull_request_target execution and AWS/environment protections are unchanged. No AWS OIDC permission is derived from these paths. This does permit the owner to review privileged application deployment code, so this policy needs separate explicit approval before merge. A second eligible reviewer would enable independent code-owner review later; the current single-developer settings do not imply such a review occurred.

After this infra PR is approved and merged, synchronize feature/app with dev using an ordinary merge. The trusted governance check then evaluates PR #9 using the newly installed policy. Inspect all final checks and request separate approval before merging PR #9. Never bypass the current failing checks or require an unobserved check.
