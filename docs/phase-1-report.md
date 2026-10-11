# Phase 1 implementation report

Review date: October 10, 2026, America/New_York. Project name: Banking Release Platform. Only Phase 1 was authorized and implemented.

## GitHub publishing checkpoint follow-up

The owner confirmed [mhachem110/BankingReleasePlatform-AWS-EKS](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS). It existed and was empty before publishing: the GitHub API reported size zero and `git ls-remote` returned no refs. `origin` now points to this repository. Both existing branches were pushed, and [PR #1](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/pull/1) is open from `feature/phase1-banking-apis` into `main`, using the prepared description plus verified test results and review guidance.

The committed history was checked for generated binaries/directories, credential files, recognized secret patterns and Terraform state/plan files; none were found. Ignore rules for binaries, build output, test artifacts, `.env` and Terraform state were verified. The publishing follow-up changes documentation only; application code and its previously recorded test results are unchanged. No GitHub CI workflow, Phase 2 implementation or AWS change was added. The PR has not been merged.

The A–G report below records the original local checkpoint. Its pending-repository notes and manual publishing instructions are historical; publishing is now complete. Do not rerun the original `git remote add origin` instructions.

## A. Phase Completed

Phase 1 — Banking Application and Docker: local implementation and Checkpoint 1 complete. Both APIs run natively and in their own Docker containers, real HTTP communication works, automated tests pass and run instructions are available. GitHub repository identity/publishing and the actual pull request remain pending the owner's repository URL. No remote was configured at initial inspection. No AWS infrastructure or IAM change was made.

The complete assignment was read before implementation. `assignment-requirements.md` maps its mandatory requirements to later phases. All seven requested files in the old CloudOpsTracker repository were reviewed read-only; no old resources or policies were changed.

## B. What You Built

| Location | Implementation |
| --- | --- |
| `apps/Account.Api/` | .NET 10 Web API, fictional accounts, list/retrieve/validate endpoints, health endpoint, replaceable repository abstraction and Dockerfile |
| `apps/Payment.Api/` | .NET 10 Web API, payment simulation endpoint, typed HTTP Account client, request validation, dependency timeout/error handling, health endpoint and Dockerfile |
| `tests/Account.Api.Tests/` | 17 automated endpoint/validation tests |
| `tests/Payment.Api.Tests/` | 31 automated endpoint, request-validation, HTTP contract and dependency failure tests |
| `compose.yaml` | Two services, distinct local images, internal service URL, host loopback ports and container restrictions |
| `scripts/smoke-test.ps1` | 17 ordinary live HTTP checks; two checks for dependency unavailability |
| `scripts/test-local.ps1` | Build/start/smoke/stop native API processes, without taking over occupied ports |
| `.github/PULL_REQUEST_TEMPLATE.md` | Review template; no Actions workflow yet |
| `docs/` | Current/future architecture, repository layout, requirement mapping, reference review, this report and prepared PR description |
| `README.md` | Complete local run, test, configuration and cleanup instructions |

Local Git has an initial `main` commit and the feature branch `feature/phase1-banking-apis`. NuGet dependency locks are committed with the implementation; generated binaries, logs, tests, Terraform state and common credential files are ignored. The directory had no useful existing code to preserve.

.NET 10 LTS was selected because it is installed and supported through November 2028. .NET 8's support ends in November 2026. ([Microsoft support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core))

## C. How It Works

The client sends a simulated payment to Payment API. Payment checks the request and calls Account API over HTTP. Account reads fictional sample data, checks account existence/activity, currency and balance, and returns a decision. Payment returns approval with a simulation reference or a meaningful rejection. Approval does not debit funds, alter balances or store a payment. There is no durable ledger or idempotency guarantee yet.

Docker images package the compiled APIs and their runtime. Multi-stage Dockerfiles use the SDK only for compilation, then copy published files into smaller runtime images. Both containers run as `app`, UID 1654, verified using `id`. Compose supplies an isolated project network; `account-api` resolves to the Account container. Payment calls `http://account-api:8080/`. Host ports 5101 and 5102 provide local access.

The runtime containers use a read-only filesystem with temporary `/tmp`, dropped capabilities and disabled privilege escalation. These are local container controls; a complete cloud security baseline remains later work.

Both `/health` endpoints indicate process health. They do not claim the Account dependency is available. Payment's outbound timeout is three seconds; an unreachable Account API returns HTTP 503 without approving the payment. Separate interfaces allow database storage and Account dependency handling to evolve without rewriting endpoint logic.

## D. Tests and Results

All checks below actually ran successfully on the local Windows host and Docker Desktop Linux engine.

| Check | Result |
| --- | --- |
| `dotnet restore BankingReleasePlatform.sln --locked-mode` | Passed for all four projects |
| Release build | Passed, zero warnings and errors |
| Release automated tests | 48 passed: 17 Account and 31 Payment; zero failed/skipped |
| `dotnet format ... --verify-no-changes --no-restore` | Passed |
| `scripts/test-local.ps1` | Both native APIs started, 17 live HTTP checks passed, owned processes stopped |
| `docker compose config --quiet` | Passed |
| `docker compose build` | Both independent Linux images built and published locally |
| `docker compose up -d` | Both containers started successfully |
| Ordinary Compose smoke test | 17 live checks passed, including Payment-to-Account communication |
| Runtime identity | Both containers verified UID/GID 1654, user `app` |
| Stop only Account container | Two outage checks passed: Payment health 200, payment 503 `account_service_unavailable` |
| Restart Account container | All 17 ordinary smoke checks passed again |

The first automated test run found malformed JSON returning 500 in the development test host. The endpoint configuration was corrected to return 400 consistently, and the final tests include malformed, null, array and invalid-number JSON bodies. There are no outstanding Phase 1 test failures.

The smoke tests cover approvals including an exact-balance request, unknown/inactive accounts, insufficient and zero balances, currency mismatch, invalid amounts, malformed JSON, unchanged balances and health. Automated tests additionally cover network failure, simulated timeout and malformed or contradictory upstream responses.

Raw test evidence is in ignored `artifacts/test-results/*.trx`, and native process logs are in `artifacts/local/`. Test runner outputs also appear in this chat. The final source and dependency locks are committed on the feature branch. The two Compose services are left running for review at ports 5101 and 5102.

Unverified/deferred: GitHub PR publication, AWS connectivity/IAM eligibility, ECR/EKS/Helm deployment, integrated Trivy/Checkov scans, database/event integration and cloud monitoring. Those are later phase requirements. No AWS deployment or security certification is claimed.

## E. What I Must Do

No AWS Console action, IAM policy, OIDC change, secret or charge approval is needed for Phase 1. Review the local APIs and confirm the intended GitHub repository URL. This is necessary because the original folder was empty and had no remote; guessing could publish to the wrong project.

To create a new destination manually in GitHub: **Repositories → New**. Choose the owner and agreed repository name, then create an empty repository without adding a README, license or gitignore. If the destination already has commits, inspect its history before pushing; do not force-push this local baseline over existing work.

Once an empty destination is confirmed, these PowerShell commands prompt for its actual URL and publish both branches:

```powershell
$repoUrl = Read-Host 'Paste the confirmed empty GitHub repository HTTPS URL'
if ($repoUrl -notmatch '^https://github\.com/[^/]+/[^/]+(?:\.git)?$') { throw 'Expected a GitHub repository HTTPS URL.' }
git remote add origin $repoUrl
if ($LASTEXITCODE -ne 0) { throw 'Could not add origin; inspect git remote -v.' }
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Publishing main failed; do not proceed until resolved.' }
git push -u origin feature/phase1-banking-apis
if ($LASTEXITCODE -ne 0) { throw 'Publishing the feature branch failed.' }
```

GitHub authentication may prompt through Git Credential Manager. No token should be placed in source code or the remote URL. In GitHub use **Pull requests → New pull request**; base `main`, compare `feature/phase1-banking-apis`. Use the title and description in `docs/phase-1-pr.md`. No pull request has been created yet. These commands are instructions, not operations already run.

An existing repository should instead be integrated deliberately after its identity and history are checked. If you provide its URL in chat, we can inspect and complete the GitHub steps before any later phase.

## F. Checkpoint

From the project root:

```powershell
docker compose up --build -d
./scripts/smoke-test.ps1
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet test BankingReleasePlatform.sln -c Release --no-restore
```

Expect 17 successful smoke checks and 48 passing automated tests. Open `http://localhost:5101/api/accounts` to see the four fictional accounts. Open `/health` on ports 5101 and 5102 to see `Healthy`. A POST payment for `ACC1001`, amount 25, currency USD returns `payment_approved`; `ACC1002` with amount 100 returns 422 `insufficient_funds`.

The README includes exact request examples and the local dependency failure demonstration. To stop this project's containers and network, run `docker compose down`. Local images remain; no cloud cleanup is required.

Assignment differences needing later attention: SQS/EventBridge is a required stack entry; staged promotion must be covered before final acceptance; security findings need owners/remediation; alerts need severity/ownership; optimization needs before/after evidence across named services. The old customized OIDC subject and role-creation logic require fresh inspection rather than reuse.

## G. Next Phase

Phase 2 will prepare the Terraform provider/backend foundation, approved bucket reuse or bootstrap, encryption, versioning, public access controls, state locking, project-specific state paths and controlled validation/operations workflows. It will inspect existing IAM/OIDC constraints and produce exact additive policies from verified inputs. It will not apply AWS changes without explicit approval.

STOP: Phase 2 has not started. Await questions or approval of the next phase. GitHub identity/publishing can be completed separately once the destination is confirmed.
