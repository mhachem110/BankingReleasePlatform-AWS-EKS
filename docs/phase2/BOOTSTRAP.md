# Phase 2 bootstrap execution plan

> Historical operational record. The dated [completion report](COMPLETION.md) is the authority for the Phase 2 result. This document includes early, superseded setup and failure notes; do not use it to infer current IAM, repository variables, or AWS resource state. Do not repeat initialization or change AWS based on this archived record.

Phase 2 uses the reusable `bootstrap` branch and PRs into `dev`. PRs #1–#6 have merged; their history is preserved. No Phase 3 infrastructure is included.

On 2026-10-11, [connectivity run 38170564614](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38170564614) succeeded using the existing role. The run recorded the provider audience and reviewed trust/policy state at that time. No further Retail policy changes were authorized. Later run results and the dedicated Banking bucket state are summarized in [COMPLETION.md](COMPLETION.md); the historical approval described here does not authorize a new operation.

[Initialization run 38172077514](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38172077514) created the dedicated bucket and imported all seven identities into remote state. Its first strict plan check failed on a lifecycle filter representation difference. The subsequent protected recovery run is recorded in [COMPLETION.md](COMPLETION.md) and supersedes this intermediate failure; use that report for the outcome.

## Components and state

Terraform describes seven dedicated-bucket resources under `infra/modules/state-bucket`: the bucket, ownership controls, public-access blocks, versioning, AES256 encryption, TLS-only policy and lifecycle configuration. `infra/bootstrap` manages those resources. `infra/environments/dev` records the development foundation and identity; it contains no VPC/EKS resources.

S3 is not inside a VPC. It stores the shared Terraform record. Versioning retains history, encryption protects stored objects, public-access blocks/disabled ACLs prevent public exposure, and the policy rejects insecure transport. S3-native `.tflock` objects prevent overlapping Terraform writes; no DynamoDB locking table is required. Only the default Terraform workspace is supported.

| Root | State key |
| --- | --- |
| Bootstrap | banking-release-platform/bootstrap/terraform.tfstate |
| Development foundation | banking-release-platform/dev/foundation/terraform.tfstate |

Each state key has its own `.tflock`. The workspace listing prefix is `banking-release-platform/_workspaces`. Future infrastructure roots require separately approved state paths. State, real inputs, plans and provider downloads remain ignored by Git.

## Current proposed configuration

The owner-approved Region is us-east-2 and dedicated bucket is mhachem-banking-tfstate-866934333672. The initialization operation checks availability and ownership; no existing bucket is assumed. Runtime values come from protected GitHub environment settings, not hardcoded provider credentials/account IDs.

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

These environment settings, the role ARN secret and variables are configured and were verified by the successful protected connectivity run. Keep Actions token defaults read-only and do not configure long-lived AWS access keys. The preflight checks fail closed unless the existing environment has the verified reviewer, only dev allowed, and no administrator bypass.

## Approval and execution sequence

1. Review the complete trust and separate Banking state policy, role-reuse authorization, provider/audience and any SCP restrictions. Preserve the existing Retail policy and trust. Approve the manual IAM/GitHub setup separately from code merges.
2. After the Phase 2 workflow is reviewed and merged into default dev, explicitly authorize a **connectivity-only** test. Enable the repository switch for that approved test. Actions > Controlled Terraform operations > Run workflow > Branch `dev` > action `connectivity`. Approve its bootstrap environment job. The session permits only caller identity and exact-provider reads: no S3 writes, Terraform initialization or bucket creation. Expected result: the correct account/assumed role and existing GitHub provider URL/audience. Stop if authorization/provider verification fails.
3. Bucket creation is a DIFFERENT authorization. Before approving it, review the proposed exact name/account/us-east-2, all seven security settings, S3 costs and policy scope. Only after approval set `DEDICATED_BUCKET_MANAGEMENT_APPROVED=true`. Dispatch action `initialize`, resume=false, approval `CREATE-APPROVED-STATE-BUCKET`; approve its environment job.
4. The initializer checks the expected bucket owner. A 403/ambiguous result stops; a successful existing-bucket check also stops in normal mode. A 404 is not a reservation: CreateBucket must actually succeed, and a race/existing-name error stops without adopting/configuring that bucket.
5. This deliberate initial seed uses AWS CLI with temporary OIDC credentials to create and secure the bucket BEFORE Terraform uses it. It then verifies owner/Region, versioning, encryption, public blocking, disabled ACLs and TLS. The seven settings match the Terraform module. There is no local AWS credential requirement or local Terraform state transfer between runners.
6. Terraform initializes the secured S3 backend and imports the seven exact resources directly into the bootstrap state. Each import persists state remotely under Terraform locking. Partial import failure leaves durable remote state; nothing publishes state as a GitHub artifact. The initializer additionally checks the remote state object's AES256 encryption/version ID and initializes both approved roots. It exercises live lock contention and generates a plan for each root. Both plans must have zero managed resource changes; output-only changes are acceptable and are not applied. Text plans are retained for one day as `phase2-verification`; no state or binary plan is uploaded by initialization. Set `BOOTSTRAP_STATE_READY=true` only after the entire run succeeds.
7. The live locking test conditionally creates an absent `.tflock` object at the exact approved key and requires Terraform to reject a competing plan with that lock's UUID. It reads the UUID and ETag back, then deletes only its owned lock using an ETag precondition. An existing/replaced/ambiguous lock is never overwritten, blindly deleted or force-unlocked. A normal successful plan afterward proves the lock can be released and reacquired. The foundation path is initialized/planned separately; an output-only plan does not persist its outputs as a new development state object. Plans can write locks and incur S3 request charges; they are not credential-free tests.
8. Only with a separately approved exact plan, dispatch action `apply` for that target and enter `APPLY-REVIEWED-PLAN`. Review/approve planning first, inspect its `plan.txt`, then review/approve the apply environment job. Apply uses the saved plan/backend from the SAME run and same immutable code commit; it does not recalculate a plan. A changed state invalidates a stale plan. No destroy workflow is provided.

The bootstrap environment is reviewed independently for each eligible job. The owner's explicit end-to-end Phase 2 authorization covers the dedicated initialization and verification described above; it does not authorize other AWS resources. After the checkpoint set `AWS_OPERATIONS_ENABLED=false`. No VPC, EKS, ECR, RDS or other Phase 3 resource is created.

## Failure/recovery boundary

Never delete/recreate an existing bucket, overwrite foreign Terraform state or force-unlock an active operation. If first creation fails before ownership tags are recorded, stop and ask an administrator to verify the bucket/CloudTrail evidence; do not infer ownership from its name.

For this confirmed, fully imported dedicated bucket, use action initialize, resume=true, approval `RESUME-APPROVED-INITIALIZATION` and the required environment review. Resume verifies owner, Region and exact project tags without writing bucket configuration. All security settings are then checked read-only. The importer uses `--require-complete`: it requires all seven approved addresses/IDs already in remote state and never imports or writes state during recovery. Missing/wrong-marker buckets, missing identities, foreign resources and configuration drift fail closed. Investigate any such failure before a separately reviewed repair; never recreate the bucket or overwrite state.

The recovery STS session grants only bucket metadata/state reads plus Get/Put/Delete of the two exact `.tflock` keys. It cannot create/modify/delete the bucket, overwrite either state object, access Retail resources or write IAM. Terraform plans acquire/release their locks but are never applied. The live diagnostic replays the original failed module from pinned commit `f498e6a8ca0a5ee341db48e1ca047177a42d398d` in a temporary root against the same backend, examines plan JSON, and requires the sole difference to be the lifecycle filter. Full state and binary plans stay private on the temporary runner; only the lifecycle API/state/plan values and text verification plans are reported.

### Lifecycle representation correction

The seeder sends S3 `Filter: {}`. AWS provider 6.68.0 reads this as an absent Terraform filter (`filter = []` in plan JSON). An explicit HCL `filter {}` instead plans a filter with `prefix = ""`. This is equivalent all-object scope, but the provider represents the two forms differently. The module now omits both filter and prefix, matching the imported API representation. This is a documented provider configuration; it does not ignore drift or require an AWS lifecycle write. The enabled rule still has no current-version expiration, expires noncurrent versions after 90 days and aborts incomplete multipart uploads after seven days. `verify-bootstrap-plan.py` continues rejecting every managed-resource mutation, including filter-only updates.

The real-provider regression test imports a synthetic lifecycle rule through a read-only loopback S3 XML fixture into temporary **local** test state. It reproduces the original update, verifies the corrected plan is no-op twice, and checks retention in before/after plan JSON. It uses AWS 6.68.0 already initialized in the module, denies fixture writes, and uses no live AWS credentials, bucket or remote state.

A failure to read backend state is not treated as empty state. Credential denial, bucket ambiguity or backend drift requires investigation, not weakened gates. Historical-version restoration requires separately authorized operator access; no restoration test ran.

## Session permissions and preservation

The existing role has broad permissions for Retail and multiple AWS services, now verified against the supplied original JSON. Adding the separate exact-bucket policy does not narrow those old grants. Every AWS job requests a restrictive STS session policy: connectivity gets identity and exact-provider/role inspection reads only; first-time initialization/plan/apply get only the exact Banking bucket (and a separately approved KMS key if applicable); recovery gets the read/lock-only cap described above. Session policies restrict rather than grant permissions. IAM write permissions and Retail/Phase 3 service access are excluded from these temporary workflow sessions.

The bucket uses `prevent_destroy` and `force_destroy=false`; the Banking addition grants no DeleteBucket or current-state deletion. Current state never expires; noncurrent versions expire after 90 days, incomplete uploads after seven days. Ordinary later infrastructure destruction uses separate state and preserves this bucket. Removing safeguards or decommissioning it requires separate approval.

## Offline validation

Run Terraform formatting, init with `-backend=false` and validate for all three roots. Run `terraform -chdir=infra/modules/state-bucket test` (mock provider, command=plan only), `python -m unittest discover -s scripts/bootstrap/tests -v`, actionlint for both workflows and Checkov on infra. These do not initialize the real backend or call AWS.

Checkov has four explicit scoped exceptions: audit-log destination, cross-Region replication, customer KMS encryption and notifications are deferred to later approved requirements. Do not treat those exceptions as a production security claim. Credential-free Terraform validation remains path-filtered and must not be globally required on application-only PRs.

References: [S3 backend and locking](https://developer.hashicorp.com/terraform/language/backend/s3), [AWS credential/session action](https://github.com/aws-actions/configure-aws-credentials), [S3 CreateBucket](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html), [AWS provider 6.68.0 lifecycle configuration](https://github.com/hashicorp/terraform-provider-aws/blob/v6.68.0/website/docs/r/s3_bucket_lifecycle_configuration.html.markdown#with-neither-a-filter-nor-prefix-specified), [provider filter import/flatten logic](https://github.com/hashicorp/terraform-provider-aws/blob/v6.68.0/internal/service/s3/bucket_lifecycle_configuration.go#L882).
