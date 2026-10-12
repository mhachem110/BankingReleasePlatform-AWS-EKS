# Governance verification evidence

> Historical checkpoint evidence/instructions. For current merged PRs, active
> controls and AWS evidence limits, read [the 12 October reconciliation](../infrastructure/RECONCILIATION.md).
> Earlier pending approvals and EC2 worker-role references below are superseded;
> the current approved compute is EKS Fargate. Do not repeat completed setup.

## Historical migration progress

PR #1 merged at e0beff1, PR #3 at ab58a7f, and PR #2 at 3db5bcc, each after individual owner approval. PR #4 is synchronized normally with dev and remains unmerged. The trusted governance workflow is installed in dev. [Run 38158307904](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38158307904) completed successfully on PR #4 head b67e38e: Branch promotion policy, File ownership and path validation, and Repository security policy all passed. GitHub Actions is the observed source (App ID 15368). Recheck the latest head after any additional commit. Required-status activation is still pending the owner's manual action using the instructions below. No AWS operation or GitHub environment configuration ran.

## Earlier preparation evidence (historical snapshot)

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

## Manual required-status activation

After a successful current PR #4 run, open Settings > Rules > Rulesets > banking-dev-governance. Keep enforcement Active, exact refs/heads/dev targeting and the empty bypass list. Enable Require status checks to pass and add exactly Repository security policy, choosing GitHub Actions as expected source. Leave Require branches to be up to date before merging unchecked for the documented promotion model. Retain PR, conversation-resolution, no-delete and no-force rules. Do not globally require the path-filtered Terraform validate job, or enable independent code-owner review while there is no second eligible reviewer. Save, reopen the ruleset and verify the entry. On PR #4 verify the aggregate is both successful and required. Do not merge until the owner separately approves PR #4. Add the check to stage, uat and main only after observing it on actual promotion PRs.
