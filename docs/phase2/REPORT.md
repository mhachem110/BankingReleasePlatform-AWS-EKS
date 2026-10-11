# Phase 2 preparation report

## A. Phase Completed

Phase 2 offline preparation is implemented and validated locally. The complete Phase 2 AWS connectivity checkpoint is NOT complete. Preparation is published on a separate feature branch with a PR into dev, following the governance checkpoint. PR #1 remains open; no merge is needed to keep this preparation separate. Final S3 permissions and AWS connectivity require the complete current inline policy, approved bucket/Region, provider confirmation and authorization to reuse/update the role.

Source is tracked on `feature/phase2-terraform-bootstrap`, based on the common initial dev baseline and separate from Phase 1 application files. No AWS API calls, live plans/applies, IAM updates or charge-incurring infrastructure operations were run. Phase 3 has not started.

## B. What You Built

- Reusable `infra/modules/state-bucket`: AES256 encryption, versioning, all public-access blocks, disabled ACLs, TLS-only policy, old-version retention, incomplete-upload cleanup, prevent_destroy and no force_destroy.
- `infra/bootstrap`: dedicated-bucket Terraform root with an S3 backend and a documented temporary local backend for the first approved bootstrap/migration.
- `infra/environments/dev`: separate S3-backed foundation with identity verification and no networking/EKS resources. Shared buckets are not Terraform-managed by this root.
- Separate state keys for bootstrap and development foundation, project-specific workspace listing prefix and S3-native `.tflock` locking.
- Credential-free PR validation workflow and disabled-by-default, protected-environment, dev-only plan/apply workflow. Apply uses the same run's reviewed plan and backend configuration; no destroy action or automatic push apply exists.
- Pinned AWS provider, Windows/Linux provider checksums, and verified full-SHA action pins.
- Read-only bucket/environment verifiers, backend configuration generator and additive IAM policy draft generator.
- `BOOTSTRAP.md` runbook, `IAM.md` manual steps and administrator request, plus verified GitHub OIDC metadata.

Complete proposed trust JSON is at `artifacts/phase2-manual/proposed-trust.json`, outside the tracked source tree. It preserves the supplied Retail trust statement and adds the exact Banking/bootstrap subject. Account-specific JSON is not committed.

## C. How It Works

S3 stores Terraform's shared state. Encryption protects stored objects, public access blocks prevent public exposure, versioning supports recovery, and a `.tflock` object coordinates concurrent operations. The bucket must exist first; an explicitly approved initial local bootstrap creates a dedicated bucket, after which state is migrated to S3. A pre-approved shared bucket can instead be reused without changing its configuration.

GitHub OIDC supplies a signed workflow identity. AWS trust allows only the verified Banking repository's bootstrap environment (and preserves Retail); a separate permission policy limits the actions the assumed role may perform. Validation jobs receive no AWS credentials. Live operations stay disabled until authorization, inputs and required environment reviewers exist. Planning may write S3 lock/state objects and incur request charges; it was not run here.

## D. Tests and Results

- Terraform 1.15.8: all three roots initialized with `-backend=false` and validated successfully.
- Terraform format check: passed.
- State-bucket mock-provider tests: 3 passed, 0 failed. All use `command = plan`; no provider calls to AWS.
- Python safety tests: 12 passed. They cover trust preservation/idempotence, wrong OIDC settings, shared-bucket write exclusion, lock-only deletion, state isolation, KMS/account mismatch, missing environment review, wildcard branch rejection and unsafe bucket settings.
- Actionlint 1.7.12: both workflows passed. All workflow run blocks separately passed Bash syntax validation. Shellcheck was disabled because a configured Shellcheck binary was unavailable.
- Checkov 3.3.17: 16 passed, 0 failed, 4 documented scoped skips (access logging, replication, customer KMS encryption and bucket notifications).
- Provider locks generated for Windows AMD64 and Linux AMD64; action release commits verified through GitHub REST.
- GitHub repository/owner IDs and immutable subject settings were independently verified. No live token exchange or AWS authorization was tested.

Unverified: actual backend ownership/settings, real IAM permission effectiveness, Organizations SCPs, role-edit authorization, GitHub environment configuration, real lock contention, migration, live plan/apply and AWS connectivity. No test success is claimed for these.

## E. What I Must Do

1. Review the separate governance and Phase 2 preparation PRs into dev. No PR is merged automatically. Before manual dispatch becomes available, promote the workflow through stage and uat to default branch main using reviewed PRs; execute the lab bootstrap only from dev after explicit AWS authorization.
2. Provide the complete CloudOpsTrackerBootstrap inline JSON, approved Region and exact approved bucket (or confirm none approved), and any existing KMS key/policy details.
3. Confirm the role ARN in IAM. The supplied ARN omitted `:role/`. Confirm you/your administrator may authorize reuse and modify trust/add an inline policy.
4. Confirm the GitHub IAM identity provider and audience under IAM  ->  Identity providers. Referencing it in trust does not verify current existence/configuration.
5. Review the complete proposed trust JSON. Only after authorization, IAM  ->  Roles  ->  existing role  ->  Trust relationships  ->  Edit trust policy. Preserve the original Retail statement and any subsequent additions.
6. Final permission JSON will be prepared after the missing inputs. Add it as a separate BankingReleasePlatformState inline policy through IAM  ->  Roles  ->  role  ->  Permissions  ->  Add permissions  ->  Create inline policy  ->  JSON. Leave CloudOpsTrackerBootstrap unchanged.
7. Before live workflow execution, configure GitHub's bootstrap environment with required reviewer(s), dev-only deployment branches and no admin bypass; supply approved environment inputs and AWS_ROLE_ARN. Keep AWS_OPERATIONS_ENABLED=false until explicit approval.

The runbook provides complete temporary backend configuration and plan/migration commands; IAM.md gives the exact administrator request for role reuse, SCPs, PassRole, EKS cluster/node roles and the later controller workload role. No new IAM roles are attempted by this code.

## F. Checkpoint

Run the offline validation commands in BOOTSTRAP.md from the repository root. Expect three valid roots, three mocked Terraform tests, twelve Python tests and clean workflow lint, with the documented Checkov exceptions. Inspect the two exact state paths, lock-file deletion scope, preserved Retail trust statement and disabled-by-default operations.

Publishing is prepared for review; final IAM policies and AWS connectivity remain gated by the identified inputs. Do not treat this as proven AWS connectivity or permission to run live operations.

## G. Next Phase

After completing and reviewing this checkpoint, Phase 3 would prepare VPC/ECR/EKS infrastructure using administrator-approved roles. No Phase 3 code or AWS resources were created. STOP at Phase 2; resolve missing inputs and review the preparation PR before considering Phase 3.
