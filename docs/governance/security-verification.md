# Governance verification evidence

This page preserves the 11 October 2026 migration validation. For current controls and project status, see the [dated infrastructure reconciliation](../infrastructure/RECONCILIATION.md) and [branch workflow](reusable-branches.md). The migration is complete; the instructions from that checkpoint are retired.

## Historical migration progress

PRs #1, #2, and #3 merged; their historical source branches were later retired after ancestry verification. PR #4 merged at `3dd4d7e` ([PR record](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/pull/4)). [Run 38158307904](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38158307904) passed the branch-promotion, path-validation, and repository-security checks on the PR #4 head. These are historical migration results, not evidence of current deployment or AWS state.

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
| PR #1/#2/#3/#4 | All merged into dev; see links above and the merge records |

The old readback and test snapshots are retained only as migration evidence. Do not follow the original manual activation steps below this checkpoint; current repository settings are controlled in GitHub and are not changed by these historical test results. No AWS deployment claim is made here.
