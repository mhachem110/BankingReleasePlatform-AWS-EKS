# Phase 2 bootstrap execution plan

This prepares Phase 2 only. AWS operations have not run. Use the reusable `bootstrap` branch and existing PR #3 into dev; its legacy source is retained only to preserve the existing PR. PR #1 was merged with explicit owner approval; bootstrap was synchronized normally with dev. No new phase branch is created.

## Components and state

Terraform describes seven dedicated-bucket resources under `infra/modules/state-bucket`: the bucket, ownership controls, public-access blocks, versioning, AES256 encryption, TLS-only policy and lifecycle configuration. `infra/bootstrap` manages those resources. `infra/environments/dev` records the development foundation and identity; it contains no VPC/EKS resources.

S3 is not inside a VPC. It stores the shared Terraform record. Versioning retains history, encryption protects stored objects, public-access blocks/disabled ACLs prevent public exposure, and the policy rejects insecure transport. S3-native `.tflock` objects prevent overlapping Terraform writes; no DynamoDB locking table is required. Only the default Terraform workspace is supported.

| Root | State key |
| --- | --- |
| Bootstrap | banking-release-platform/bootstrap/terraform.tfstate |
| Development foundation | banking-release-platform/dev/foundation/terraform.tfstate |

Each state key has its own `.tflock`. The workspace listing prefix is `banking-release-platform/_workspaces`. Future infrastructure roots require separately approved state paths. State, real inputs, plans and provider downloads remain ignored by Git.

## Current proposed configuration

The owner's proposed Region is us-east-2 and the proposed dedicated bucket is mhachem-banking-tfstate-866934333672. Neither availability nor live ownership/settings were inspected. No existing bucket is assumed. Runtime values come from protected GitHub environment settings, not hardcoded provider credentials/account IDs.

Use SSE-S3 AES256 initially; no customer KMS key, IAM role or DynamoDB table is created. A different bucket, shared-bucket adoption or customer KMS key requires a separate review, not a silent variable change.

## GitHub setup, after authorization

Repository > Settings > Environments > New environment > `bootstrap`:

- Required reviewer: verified cloud owner `mhachem110` only.
- Selected branches and tags: one **Branch** rule `dev`; no tag/wildcard rules.
- Administrator bypass: disabled.
- Prevent self-review: unchecked for this single-person lab. This is owner approval, not independent second-person approval.
- Environment secret `AWS_ROLE_ARN`: copy the actual existing role ARN from IAM, including `:role/` and any actual path.
- Environment variables `AWS_REGION`, `AWS_EXPECTED_ACCOUNT_ID`, `TF_STATE_BUCKET`: the reviewed inputs. Optional `TF_STATE_KMS_KEY_ARN` stays unset for this dedicated AES256 bucket.
- `DEDICATED_BUCKET_MANAGEMENT_APPROVED=false`, `BOOTSTRAP_STATE_READY=false` initially.

Repository > Settings > Secrets and variables > Actions > Variables: keep repository variable `AWS_OPERATIONS_ENABLED=false` initially. It gates all live operations, including read-only connectivity. The old `BOOTSTRAP_STATE_MIGRATED` flag is superseded by `BOOTSTRAP_STATE_READY`; the new initializer does not migrate local state.

No environment, secret or variable was created during preparation. Keep Actions token defaults read-only and do not configure long-lived AWS access keys. The preflight checks fail closed unless the existing environment has the verified reviewer, only dev allowed, and no administrator bypass.

## Approval and execution sequence

1. Review the complete trust and separate Banking state policy, role-reuse authorization, provider/audience and any SCP restrictions. Preserve the existing Retail policy and trust. Approve the manual IAM/GitHub setup separately from code merges.
2. After the Phase 2 workflow is reviewed and merged into default dev, explicitly authorize a **connectivity-only** test. Enable the repository switch for that approved test. Actions > Controlled Terraform operations > Run workflow > Branch `dev` > action `connectivity`. Approve its bootstrap environment job. The session permits only caller identity and exact-provider reads: no S3 writes, Terraform initialization or bucket creation. Expected result: the correct account/assumed role and existing GitHub provider URL/audience. Stop if authorization/provider verification fails.
3. Bucket creation is a DIFFERENT authorization. Before approving it, review the proposed exact name/account/us-east-2, all seven security settings, S3 costs and policy scope. Only after approval set `DEDICATED_BUCKET_MANAGEMENT_APPROVED=true`. Dispatch action `initialize`, resume=false, approval `CREATE-APPROVED-STATE-BUCKET`; approve its environment job.
4. The initializer checks the expected bucket owner. A 403/ambiguous result stops; a successful existing-bucket check also stops in normal mode. A 404 is not a reservation: CreateBucket must actually succeed, and a race/existing-name error stops without adopting/configuring that bucket.
5. This deliberate initial seed uses AWS CLI with temporary OIDC credentials to create and secure the bucket BEFORE Terraform uses it. It then verifies owner/Region, versioning, encryption, public blocking, disabled ACLs and TLS. The seven settings match the Terraform module. There is no local AWS credential requirement or local Terraform state transfer between runners.
6. Terraform initializes the secured S3 backend and imports the seven exact resources directly into the bootstrap state. Each import persists state remotely under Terraform locking. Partial import failure leaves durable remote state; nothing publishes state as a GitHub artifact. Verify the job and recorded resource identities before setting `BOOTSTRAP_STATE_READY=true`.
7. Separately authorize a `plan`, target `bootstrap`. Review resource changes, output changes and backend settings. Imports may leave output values pending; do not assume a zero-change plan before a real run. Then plan the foundation root separately if approved. Plans can write locks/state metadata and incur S3 request charges; they are not credential-free tests.
8. Only with a separately approved exact plan, dispatch action `apply` for that target and enter `APPLY-REVIEWED-PLAN`. Review/approve planning first, inspect its `plan.txt`, then review/approve the apply environment job. Apply uses the saved plan/backend from the SAME run and same immutable code commit; it does not recalculate a plan. A changed state invalidates a stale plan. No destroy workflow is provided.

The bootstrap environment is reviewed independently for each eligible job. No step here authorizes automatic AWS operations. The next checkpoint is manual AWS setup plus connectivity-only verification, not bucket creation.

## Failure/recovery boundary

Never delete/recreate an existing bucket, overwrite foreign Terraform state or force-unlock an active operation. If first creation fails before ownership tags are recorded, stop and ask an administrator to verify the bucket/CloudTrail evidence; do not infer ownership from its name.

For a confirmed previously seeded dedicated bucket, review its Region, exact project tags, configuration and any partial state BEFORE approving recovery. Resume is a distinct request: action initialize, resume=true, approval `RESUME-APPROVED-INITIALIZATION`, required environment approval. It refuses missing/wrong-marker buckets. Resume reapplies the approved seven settings, so review any live drift or added bucket-policy statements first. The importer rejects foreign resource addresses/IDs, skips the known already-imported identities, and imports only missing ones. It does not remove/replace remote state. No recovery was performed here.

A failure to read backend state is not treated as empty state. Credential denial, bucket ambiguity or backend drift requires investigation, not weakened gates. Historical-version restoration requires separately authorized operator access; no restoration test ran.

## Session permissions and preservation

The supplied existing role has broad permissions for Retail and multiple AWS services. Adding the new exact-bucket policy does not narrow those old grants. Every prepared AWS job therefore requests a restrictive STS session policy: connectivity gets identity/provider reads only; initialization/plan/apply get only the exact Banking bucket (and a separately approved KMS key if applicable). Session policies restrict rather than grant permissions. The shared role itself remains broad, so administrator approval of reuse is required.

The bucket uses `prevent_destroy` and `force_destroy=false`; the Banking addition grants no DeleteBucket or current-state deletion. Current state never expires; noncurrent versions expire after 90 days, incomplete uploads after seven days. Ordinary later infrastructure destruction uses separate state and preserves this bucket. Removing safeguards or decommissioning it requires separate approval.

## Offline validation

Run Terraform formatting, init with `-backend=false` and validate for all three roots. Run `terraform -chdir=infra/modules/state-bucket test` (mock provider, command=plan only), `python -m unittest discover -s scripts/bootstrap/tests -v`, actionlint for both workflows and Checkov on infra. These do not initialize the real backend or call AWS.

Checkov has four explicit scoped exceptions: audit-log destination, cross-Region replication, customer KMS encryption and notifications are deferred to later approved requirements. Do not treat those exceptions as a production security claim. Credential-free Terraform validation remains path-filtered and must not be globally required on application-only PRs.

References: [S3 backend and locking](https://developer.hashicorp.com/terraform/language/backend/s3), [AWS credential/session action](https://github.com/aws-actions/configure-aws-credentials), [S3 CreateBucket](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html).
