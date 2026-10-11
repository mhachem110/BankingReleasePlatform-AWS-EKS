# Phase 2 bootstrap and connectivity runbook

This is offline preparation on `feature/phase2-terraform-bootstrap`, with a PR into `dev` from the common initial baseline. It contains no Phase 1 application changes; the governance checkpoint supersedes the former merged-main prerequisite. Nothing here has been applied to AWS. AWS Region, bucket selection, complete inline permissions and role-reuse authorization are still required inputs.

## What the components do

Terraform records resource identities and configuration in state. S3 stores that state so authorized operators and CI can use the same record. Versioning retains older state versions for recovery; encryption protects stored objects; public access blocking prevents public access; a TLS-only policy rejects insecure transport. S3 is not inside a VPC.

S3-native locking uses a separate `.tflock` object. It prevents two Terraform operations from changing the same state concurrently. This uses `use_lockfile = true`; no DynamoDB table is needed. See [HashiCorp S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3).

The GitHub workflow exchanges its signed OIDC identity for short-lived credentials using the existing role. Trust decides who may assume that role; permission policies decide what AWS actions the session may perform.

## Layout

- `infra/modules/state-bucket`: reusable dedicated-bucket safeguards.
- `infra/bootstrap`: creates/manages ONLY an explicitly approved new dedicated state bucket.
- `infra/environments/dev`: separate S3-backed foundation root, with identity reads and no VPC/EKS resources. The workflow verifies the bucket using separate read-only metadata requests.
- `infra/backend/*.example`: partial S3 backend configuration without real resource/account values.
- `scripts/bootstrap`: read-only verification and local configuration/policy generation.
- `.github/workflows/terraform-validation.yml`: PR validation without AWS credentials.
- `.github/workflows/terraform-operations.yml`: disabled-by-default, dev-only, manually dispatched plan/apply.

Dedicated bootstrap state: `banking-release-platform/bootstrap/terraform.tfstate`.
Development foundation state: `banking-release-platform/dev/foundation/terraform.tfstate`.
Each has its own `.tflock`. Workspace listing is restricted to `banking-release-platform/_workspaces`; only the default workspace is supported. Future networking/platform roots get new project paths after Phase 3 approval.

## Bucket decision

Ask the owner or administrator for the exact approved bucket, owning account, Region, encryption, versioning, public access settings and existing bucket policy.

For an approved shared bucket, use the development foundation root. Do not import the shared bucket into the dedicated bootstrap root, change its policy, tags or lifecycle, or place it under a second Terraform owner. Backend access is additive and restricted to this project's state and lock objects.

For a new dedicated bucket, the owner must explicitly approve creation, security settings and cost before any live plan/apply. A globally unique approved name must be supplied; no name is assumed. AES256 (SSE-S3) is the initial dedicated-bucket configuration, with no customer KMS key creation. Existing SSE-KMS buckets require the exact approved key ARN and key-policy/IAM review; the backend and verifier support that input.

## Offline validation (safe to run now)

From the repository root on this feature branch:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra/modules/state-bucket init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/modules/state-bucket validate
terraform -chdir=infra/modules/state-bucket test
terraform -chdir=infra/bootstrap init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/bootstrap validate
terraform -chdir=infra/environments/dev init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/environments/dev validate
python -m unittest discover -s scripts/bootstrap/tests -v
checkov --directory infra --framework terraform --download-external-modules false --compact
```

Provider downloads contact the public Terraform registry. These commands do not configure an S3 backend or contact live AWS resources. All Terraform test runs use a mock provider and `command = plan`. Do not change them to real-provider tests without approval.

## First dedicated bucket bootstrap (future approval required)

This is a separate, deliberate operation on an authorized operator's machine, not an automatic step in a GitHub plan job.

1. Confirm role reuse and AWS credentials, approved Region/account/name and permission policy. Use short-lived credentials; do not put keys in files committed to Git.
2. Copy `terraform.tfvars.example` to ignored `terraform.tfvars` and replace every placeholder with the verified inputs. Confirm the account with `aws sts get-caller-identity`.
3. Confirm the dedicated name is approved and unused. A denied `HeadBucket` does not prove absence. If the name already exists, stop for ownership/state/import review.
4. Place this complete temporary file at ignored `infra/bootstrap/backend_override.tf`:

```hcl
# TEMPORARY: first approved dedicated-bucket creation only.
terraform {
  backend "local" {
    path = ".bootstrap-local/terraform.tfstate"
  }
}
```

5. With explicit permission to perform the live plan, run `terraform -chdir=infra/bootstrap init -input=false`, `validate`, then `plan -input=false -out=bootstrap.tfplan`. Review all seven bucket/safeguard resources and the account/Region/name. This does not create the bucket.
6. Obtain explicit approval for that exact plan before running `terraform -chdir=infra/bootstrap apply bootstrap.tfplan`. This creates AWS resources and incurs S3 request/storage charges. None of these commands was run in this checkpoint.
7. Back up the local state securely outside Git. Verify the actual bucket with the read-only verifier using the verified owner and Region.
8. After migration approval, remove ONLY the temporary override. Supply the approved S3 partial configuration (bootstrap key) and run `terraform -chdir=infra/bootstrap init -migrate-state -backend-config=../backend/bootstrap.s3.tfbackend`. Answer the migration prompt after checking the destination. Do not use `-reconfigure` for migration or force-copy blindly. Migration writes state and locking objects to S3.
9. Confirm state exists at the bootstrap key, versioning/encryption/public blocking are enabled, and a subsequent plan is a no-op. Retain the secure local backup until migration is verified. Set the GitHub migration flag only after successful verification.

The S3 backend cannot exist before its bucket. This temporary local override solves that ordering deliberately. See [Terraform backend overrides](https://developer.hashicorp.com/terraform/language/files/override).

## GitHub configuration (manual, only after authorization)

GitHub repository  ->  Settings  ->  Environments  ->  create or inspect `bootstrap`.
Add at least one required reviewer; restrict deployment branches to selected branch `dev` only, and disable administrator bypass. The preflight checker fails closed if the environment is absent, unreadable or missing these settings. If GitHub's token/plan cannot read or enforce these settings, stop and request administrator help; do not remove the gate.

GitHub  ->  Settings  ->  Secrets and variables  ->  Actions:
- Repository variable `AWS_OPERATIONS_ENABLED`: initially `false`; enable only after explicit authorization and all prerequisites.
- Environment secret `AWS_ROLE_ARN`: copy the verified existing role ARN from IAM (must include `:role/`).
- Environment variables `AWS_REGION`, `AWS_EXPECTED_ACCOUNT_ID`, `TF_STATE_BUCKET`: verified inputs.
- Optional `TF_STATE_KMS_KEY_ARN`: exact approved existing customer KMS key for a reused SSE-KMS bucket.
- `DEDICATED_BUCKET_MANAGEMENT_APPROVED` and `BOOTSTRAP_STATE_MIGRATED`: default absent/false. Set true only for an approved dedicated bucket and verified migration. Never enable them for a shared bucket.

The repository default is now dev. After reviewing and merging Phase 2 code manually into dev, GitHub can expose workflow_dispatch because the workflow exists on the default branch. No production promotion is needed to bootstrap the development environment. Only after all AWS prerequisites and explicit AWS operations authorization, Actions  ->  Controlled Terraform operations  ->  Run workflow  ->  branch `dev`.
A `plan` run authenticates after reviewer approval, verifies the existing bucket, initializes remote state, validates and saves a plan. It makes no bucket repairs. Backend initialization/locking may write S3 objects and incur request charges even for plan; do not run it without connectivity/backend authorization.

An `apply` run additionally needs `APPLY-REVIEWED-PLAN` and a second environment approval after planning. Review `plan.txt` and the backend before approving the apply job. Apply consumes that run's saved binary plan and exact backend configuration; it does not recalculate a plan. No automatic push/PR applies, no destroy workflow and no application release workflow are included.

Plan artifacts are retained one day. This phase's plans contain only bucket/foundation metadata; review visibility before adding sensitive resources or extending this workflow. State may contain secrets in later phases; never publish it as an artifact.

## Preservation and cleanup

The state bucket uses `prevent_destroy` and `force_destroy = false`. Current state never expires; noncurrent versions expire after 90 days and incomplete uploads after seven days. There is no state-bucket destroy operation. Normal future infrastructure destruction uses its separate root/state and preserves this bucket.

These guards do not prevent manual AWS deletion or deletion after removing Terraform protection. Administrator-approved state recovery/decommissioning remains a separate procedure. Do not delete current state/lock files or force-unlock active operations.

## Checkov exceptions requiring review

Four scoped skips are documented in the resource:
- S3 access-log destination deferred to approved Phase 6 audit design.
- Cross-Region replication deferred to an availability/cost decision.
- Customer KMS encryption deferred; AES256 encryption is enabled now.
- Bucket notifications deferred; they are not required for S3 backend locking.

These are limitations, not proof of a full security baseline. Reassess during Phase 6.

## Governance integration

The branch promotion workflow and live ruleset definitions are in the separate governance PR. Terraform validation remains path-filtered; do not require its status on application-only PRs. Only activate observed stable checks after their workflows can run for each destination. No GitHub environments or AWS variables/secrets were configured. The bootstrap environment is planned with selected branch dev, reviewers, no admin bypass, and single-person self-review allowed only for the current documented lab setup. Keep AWS_OPERATIONS_ENABLED false until explicit AWS approval.
