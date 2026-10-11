# IAM review and manual change instructions

No AWS configuration was inspected or changed by the implementation. The owner supplied a complete trust policy and permission summaries; summaries do not establish effective permissions.

## Verified GitHub identity

GitHub REST verified repository ID `1413860979`, owner ID `150286776`, `use_default: true`, `use_immutable_subject: true` and prefix:

```text
repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979
```

For the workflow's `bootstrap` environment, the proposed exact subject appends `:environment:bootstrap`. The AWS audience is `sts.amazonaws.com`. The repository's immutable format is a default setting, not evidence of a custom claim template. A name-only subject will not match. See [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc).

The supplied role ARN omitted the IAM resource separator/type. Copy the actual ARN from IAM → Roles → `cloudbatch818-mahmoud-cloudops-bootstrap`; the canonical structure is `arn:aws:iam::<verified-account>:role/<optional-role-path>cloudbatch818-mahmoud-cloudops-bootstrap`. The workflow validates the account, IAM role resource type and role name while permitting the actual IAM path, without a hardcoded account ID.

## Inputs required before final permissions

AWS Console → IAM → Roles → `cloudbatch818-mahmoud-cloudops-bootstrap`:
1. Trust relationships → complete current JSON (supplied; recheck immediately before updating).
2. Permissions → `CloudOpsTrackerBootstrap` inline policy → JSON: supply the COMPLETE policy. Do not replace it with summaries.
3. Confirm no attached policy, boundary or new inline policy has appeared. Owner reports one inline policy, no attached policies and no boundary.
4. Confirm that the human/operator is authorized to update trust and add policy; current authorization is unconfirmed.
5. IAM → Identity providers → `token.actions.githubusercontent.com`: verify provider ARN and `sts.amazonaws.com` audience. A reference in trust JSON does not independently verify the provider exists/is configured.

Obtain approved bucket name, owner, Region, policy and encryption details. An administrator must check Organizations SCPs, explicit denies and service-linked-role restrictions. Even an Allow in the role does not override an SCP, boundary or bucket/key-policy deny.

## Proposed trust change

A complete proposed replacement JSON is provided separately in the ignored manual artifact `artifacts/phase2-manual/proposed-trust.json`. It preserves `GitHubOIDCRetailBootstrap` exactly and adds a separate `GitHubOIDCBankingBootstrap` statement. It grants no AWS resource permissions. Do not remove or weaken the existing Retail statement or any statement added since the supplied snapshot.

When authorized, Console → IAM → Roles → role → Trust relationships → Edit trust policy. Save the current JSON securely. Paste the complete reviewed generated trust JSON only after comparison with the current policy and administrator approval. Verify both exact Retail and Banking subjects remain, with `sts:AssumeRoleWithWebIdentity` and `aud = sts.amazonaws.com`.

Trust alone does not authorize bucket operations or prove role reuse is permitted.

## Additional S3 permissions

Generate a NEW additive inline policy, tentatively named `BankingReleasePlatformState`, leaving `CloudOpsTrackerBootstrap` unchanged. Final JSON is intentionally withheld until the full policy, approved bucket/mode and any KMS key are supplied.

Required categories:
- Bucket metadata/safeguard reads scoped to the exact approved bucket ARN.
- ListBucket scoped to the banking state/workspace prefix for reuse. A dedicated managed bucket additionally needs bucket-wide ListBucket for Terraform's HeadBucket refresh, scoped to that one dedicated bucket.
- GetObject/PutObject on the two exact state keys.
- GetObject/PutObject/DeleteObject on their exact `.tflock` objects.
- No DeleteObject on current state, no DeleteBucket and no IAM role operations.
- For an approved NEW dedicated bucket only: CreateBucket and the necessary tagging, versioning, encryption, ownership, public-block, TLS-policy and lifecycle writes on that one bucket.
- For an approved existing customer KMS key: scoped encryption/decryption/data-key permissions, plus a compatible key policy. No KMS key creation.

The old summary names `mhachem-retail-*` bucket resources; that does not prove the new banking bucket is covered. It also does not prove there is no wider Allow or explicit Deny. The full JSON must be reviewed for actions, resources and conditions, and aggregate inline policy size must be checked against IAM quotas.

The policy preparation script REQUIRES the complete current permission JSON, trusts verified OIDC settings, emits a complete proposed trust and complete separate addition, and writes an unchanged permission-policy copy for comparison. It never calls AWS:

```powershell
python scripts/bootstrap/prepare-iam-policies.py --current-trust artifacts/iam/current-trust.json --current-permissions artifacts/iam/current-permissions.json --oidc-settings docs/phase2/verified-github-oidc.json --account $env:AWS_EXPECTED_ACCOUNT_ID --bucket $env:TF_STATE_BUCKET --mode reuse --output-dir artifacts/iam/proposed
```

Use `--mode dedicated` only with approval for a new dedicated bucket. Actual input files and generated account/resource-specific JSON remain ignored. After review, IAM → Roles → role → Permissions → Add permissions → Create inline policy → JSON. Paste the complete approved ADDITION and name it `BankingReleasePlatformState`. Do not edit or replace the Retail inline policy. If size limits or authorization block this, request administrator assistance instead of removing old permissions.

## Verification after future authorized changes

Recheck both trust statements and original inline JSON unchanged. A protected, dev-only, manually approved plan verifies `aws sts get-caller-identity`, expected account and read-only bucket safeguards. Success must be demonstrated by an actual run; none has run. A permission simulation alone does not prove the GitHub token or SCP/bucket/KMS context is authorized.

## Phase 3 restrictions and administrator request

No EKS or IAM-role creation code is included now. The `ManageRetailRoles` scope described by the owner is limited to `cloudbatch818-mahmoud-retail-*`; it must not be assumed to cover Banking role names. `iam:PassRole` action/resources/conditions have not been verified.

Send this request to your AWS administrator:

> Please confirm whether the existing cloudbatch818-mahmoud-cloudops-bootstrap role may be reused by mhachem110/BankingReleasePlatform-AWS-EKS. Approve the additive Banking OIDC trust statement while preserving all existing statements, and the exact-bucket Banking state policy while preserving CloudOpsTrackerBootstrap. Confirm the GitHub OIDC provider/audience, effective SCP restrictions, policy quotas and the operator's authorization to make these changes.
>
> Before Phase 3, please provide approved, pre-created, DISTINCT EKS cluster and worker-node role ARNs with appropriate service trust and permissions, plus exact PassRole authorization for those roles during the intended EKS API operations. Cluster trust is for EKS; node trust is for EC2. Please also confirm permission to create EKS/node groups, VPC networking and ECR resources, service-linked-role availability, cluster access administration, and any naming/tag conditions.
>
> Before ALB deployment, provide an approved AWS Load Balancer Controller workload role/policy and its IRSA or EKS Pod Identity trust/association. Its workload identity differs from GitHub OIDC. Confirm VPC CNI and other add-on workload identity requirements. Do not use the GitHub bootstrap role as a cluster, node or controller role.

References: [EKS cluster role](https://docs.aws.amazon.com/eks/latest/userguide/cluster-iam-role.html), [EKS node role](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html).

Do not create new roles or remove old project access. Phase 3 permissions must be designed from the verified policies and supplied role ARNs after its approval.
