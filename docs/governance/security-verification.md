# Governance verification evidence

Verified on 2026-10-11. This evidence describes repository governance, not an AWS authorization/deployment test.

| Check actually performed | Result |
| --- | --- |
| Python file-policy unit tests | 23 passed |
| Actual workflow Bash route step | 6 allowed routes accepted; 26 invalid combinations rejected |
| Actual aggregate Bash step | All 16 success/failure/cancelled/skipped result pairs behaved correctly; only success/success passes |
| Trusted workflow structural assertions | No PR-head checkout, AWS environment, AWS secrets or OIDC permissions; read-only file job; always-running aggregate; no path filter |
| actionlint 1.7.12, governance workflow | Passed |
| GitHub pinned checkout tag verification | v7.0.1 resolves to the configured immutable commit |
| GitHub CODEOWNERS validation on PR #2 branch | No errors |
| Local trusted validator against PR #4's live GitHub metadata | Passed, including current and previous filename handling |
| Complete ruleset readback vs before snapshot | Original five rulesets identical; two separate new Active update-only guards |
| Effective rules API, all seven branch refs | Expected PR/update/deletion/force protections on protected refs; cloud update restrictions only on bootstrap/infra |
| Authenticated actor authorization readback | Cloud guard: always; protected guard: pull_requests_only |
| Ordinary owner push to infra | Succeeded through the update-only authority guard; no force push |
| Actions default permissions | Read; Actions approval of PR reviews disabled, unchanged |
| Secret scanning / push protection | Already enabled, preserved |
| GitHub environment inventory | Empty; no environments/secrets/variables created by this task |
| History ancestry | Original application, bootstrap, governance and migration commits preserved |
| dev/stage/uat/main branch refs | Unchanged initial baseline 43a9ddba5b965b96fb9a5535cb67604e3b85ff1c |
| PR #1/#2/#3/#4 | Open into dev; #3 still draft; none merged |

GitHub REST reported `mergeable_state: blocked` for these PRs at the final read. The authority ruleset independently reports the authenticated owner as authorized **for pull requests only**. No merge was attempted to test that authorization. At an approved merge, inspect the owner-visible merge requirements; do not disable or bypass the separate original protections. A generic REST merge state is not evidence that all actors may merge, nor proof that a merge succeeded.

The policy workflow is not yet installed in the empty default dev, so its final jobs have not executed as required GitHub checks. Required-status activation must follow an actual successful current-PR run after the approved migration. CODEOWNERS review requests likewise need the file on each destination branch; independent required review needs another eligible reviewer. Tests were local, except for API readback, GitHub syntax validation and ordinary branch push.

Not performed: negative update attempt by another real identity, destructive push/deletion tests, PR merges, application/Helm CI implementation, environment creation, AWS calls, IAM changes, Terraform apply, deployment or charge-incurring infrastructure. The API snapshots and test harness remain in ignored artifacts; no credentials are written to evidence files or committed.
