# Phase 2 IAM review and exact manual steps

> Historical checkpoint evidence/instructions. For current merged PRs, active
> controls and AWS evidence limits, read [the 12 October reconciliation](../infrastructure/RECONCILIATION.md).
> Earlier pending approvals and EC2 worker-role references below are superseded;
> the current approved compute is EKS Fargate. Do not repeat completed setup.

**Historical preparation instructions:** live connectivity and both installed policy/trust relationships have since been verified. The actual role ARN includes `:role/`. See [COMPLETION.md](COMPLETION.md) for current evidence. Do not repeat or replace policies based on the earlier unverified wording below.

The owner supplied the complete current trust policy and all 18 statements of the CloudOpsTrackerBootstrap inline policy. They were reviewed locally; AWS IAM was not inspected or changed. Boundary: none, attached policies: none, as reported. No existing grant or trust statement is removed.

## Verified GitHub identity

GitHub REST reverified repository ID 1413860979, owner ID 150286776, use_default=true, use_immutable_subject=true, and prefix `repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979`.

Banking bootstrap subject: `repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979:environment:bootstrap`.
Audience: `sts.amazonaws.com`. The default immutable subject format is enabled, not a custom name-only template. Do not use an old name-only subject or grant working-branch/wildcard trust. An environment subject replaces the branch component, so GitHub must restrict bootstrap to dev.

The supplied role ARN is still malformed: it omits `:role/`. Copy the actual existing role ARN from IAM, including any real role path. The no-path form is `arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-cloudops-bootstrap`. The account/name are supplied inputs, not proof that this no-path ARN was read from AWS.

## Existing policy findings

| Finding | Consequence |
| --- | --- |
| All S3 grants name mhachem-retail-* | Banking bucket/state access needs the separate addition |
| IAMRead grants iam:Get* / iam:List* | Provider verification is allowed by the supplied role policy, subject to SCP/other denies |
| Role writes/PassRole scoped to cloudbatch818-mahmoud-retail-* | The role cannot update its own bootstrap trust/policy from these grants; Banking EKS role PassRole is not authorized |
| Broad EC2/EKS/ECR/data/messaging/logging and other service grants | The role is not an overall least-privilege Banking role; old grants remain unchanged |
| Service-linked role allowlist includes EKS, node groups, ALB, Auto Scaling, RDS and ElastiCache | Documented IAM allow exists; actual SCP/service restrictions/role existence remain unverified |
| No explicit Deny in supplied inline policy | Does not rule out SCPs, bucket/key policies or other effective restrictions |

All AWS jobs request restrictive STS session policies. Connectivity permits only identity/exact OIDC-provider reads. Operational sessions are capped to the exact Banking bucket, excluding Retail/EC2/EKS/IAM writes. A session cap is an intersection with role grants, not a new grant. It secures these prepared runs; it does not globally narrow every session of the reused role.

## Complete proposed JSON

Account-specific complete JSON remains outside Git in ignored manual artifacts:

- artifacts/phase2-manual/updated-trust.json: complete replacement preserving the supplied Retail statement exactly and adding only Banking/bootstrap.
- artifacts/phase2-manual/BankingReleasePlatformState.json: complete NEW inline policy for the proposed dedicated bucket, creation restricted to us-east-2, required provider metadata/safeguard actions, state read/write at two exact keys and deletion only of their .tflock objects.
- artifacts/phase2-manual/current-CloudOpsTrackerBootstrap.json: unchanged policy values copied from the supplied JSON for comparison.

No IAM write, new role, PassRole, KMS creation, DeleteBucket or current-state deletion is added. Dedicated-bucket ListBucket is intentionally bucket-wide because Terraform's bucket resource uses HeadBucket; object writes stay on the two state keys/locks. Other state paths are not authorized. Current and additional compact inline policy sizes are checked against the 10,240-character aggregate role quota.

Regenerate locally (no AWS call) with the complete supplied policies and verified inputs:

```powershell
python scripts/bootstrap/prepare-iam-policies.py --current-trust artifacts/phase2-manual/current-trust.json --current-permissions artifacts/phase2-manual/current-CloudOpsTrackerBootstrap.json --oidc-settings docs/phase2/verified-github-oidc.json --account $env:AWS_EXPECTED_ACCOUNT_ID --bucket $env:TF_STATE_BUCKET --region $env:AWS_REGION --mode dedicated --output-dir artifacts/phase2-manual/final
```

The generator preserves current trust statements, rejects conflicting existing Banking trust and copies original permission-policy values unchanged. It never calls AWS.

## Console actions, only after approval

1. AWS Console > IAM > Identity providers > token.actions.githubusercontent.com. Confirm URL `https://token.actions.githubusercontent.com`, provider ARN in the target account and audience list containing `sts.amazonaws.com`. The old trust references this provider but does not prove current existence/configuration. If absent or wrong, STOP for administrator authorization. Preserve other audiences/trusts; do not create/edit it here.
2. IAM > Roles > cloudbatch818-mahmoud-cloudops-bootstrap > Summary: copy ARN and confirm actual path/account/name. Confirm authorization to reuse this role, update trust and add the proposed policy. Your human IAM editing authority is not established by this role's permissions.
3. Role > Trust relationships > Edit trust policy: first save/compare the CURRENT complete JSON. After authorization, paste the complete reviewed updated-trust.json. If statements changed since the supplied snapshot, regenerate while preserving those statements instead of overwriting them. Verify both exact Retail and Banking subjects and their sts.amazonaws.com audience remain.
4. Role > Permissions > Add permissions > Create inline policy > JSON: paste the complete BankingReleasePlatformState.json. Next, name it exactly `BankingReleasePlatformState`, then Create policy only after approval. Do not edit/replace CloudOpsTrackerBootstrap. Verify the original inline JSON remains identical and there are now the original and new policies. Recheck boundary/attached policies and policy quota.
5. Configure the GitHub bootstrap environment as documented in BOOTSTRAP.md. Only after separate authorization, run the connectivity action from dev with environment approval. Expected identity: target account and assumed existing role. The job verifies the provider/audience through read-only IAM. No bucket is required for this identity/provider test.

Trust determines WHO may assume the role. Permission policies determine WHAT the session may do. GitHub environment review determines WHEN the job starts. Neither a code merge nor an environment automatically grants AWS permissions.

## Exact administrator request

> Please authorize reuse of cloudbatch818-mahmoud-cloudops-bootstrap by the Banking repository's exact bootstrap OIDC subject. Confirm the provider URL/audience in account 866934333672, and authorize iam:UpdateAssumeRolePolicy and iam:PutRolePolicy on the existing role for the administrator/operator applying the reviewed JSON. Preserve all Retail trust and CloudOpsTrackerBootstrap grants. Add only BankingReleasePlatformState for mhachem-banking-tfstate-866934333672 in us-east-2. Confirm aggregate policy quota, attached policies/boundaries, role path and effective SCP/resource-policy restrictions, particularly sts:AssumeRoleWithWebIdentity, provider reads and the specified S3 actions. No new role or bucket creation is authorized by this request alone.
>
> Before a separately approved Phase 3, provide approved distinct EKS cluster and EC2 worker-node role ARNs. Existing PassRole grants apply only to cloudbatch818-mahmoud-retail-* and do not authorize Banking-named roles. Provide narrowly scoped PassRole permissions for the approved roles and appropriate iam:PassedToService conditions, confirm service-linked-role availability/SCP restrictions and cluster access administration. Later provide a separately approved ALB Controller workload identity role and any CNI/add-on identities. Do not use the GitHub bootstrap role as an EKS cluster/node/controller role.

Organizations SCPs were not provided or inspected; ask the account/organization administrator to review effective SCPs on the account, its parent OUs and root. An SCP/explicit resource-policy deny overrides an Allow. No claim is made that IAM edits or S3/EKS operations are authorized merely because the supplied policy allows some actions.

References: [AWS GitHub OIDC](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html), [STS session-policy intersection](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html), [IAM quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html), [S3 backend permissions](https://developer.hashicorp.com/terraform/language/backend/s3).
