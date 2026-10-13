# Terraform IAM authorization comparison

Read-only review on 12 October 2026 (Eastern). This comparison authorizes no merge,
IAM write, Terraform plan/apply or chargeable deployment. Banking live acceptance
remains 8/20 (40%); the next checkpoint is reviewed code followed by the protected
read-only bootstrap audit.

## Evidence inspected

All requested files were read at pinned source revisions:

- [AWS three-tier, 5618d6e](https://github.com/zeinhaidara/aws-3-tier-github-actions/tree/5618d6e47b26fff055af186810fc07242d27caea):
  infrastructure-bootstrap.yml, cd.yml, infra/terraform/bootstrap/main.tf,
  infra/terraform/main.tf and deploy/ecs/main.tf.
- [Healthcare EKS, 17a7b64](https://github.com/zeinhaidara/healthcare-eks-secops/tree/17a7b648fdcb84a8bf460a247f2d89a36abd3d1d):
  docs/bootstrap.md, bootstrap-policies README/apply-policy.json/plan-policy.json,
  terraform-apply.yml, EKS and IRSA modules, and terraform/main.tf.
- GitHub confirms the supplied [three-tier run 36371270668](https://github.com/zeinhaidara/aws-3-tier-github-actions/actions/runs/36371270668)
  and [healthcare run 38293352769](https://github.com/zeinhaidara/healthcare-eks-secops/actions/runs/38293352769)
  completed successfully. Their source heads are 2c1007c and dde3675 respectively;
  success alone does not identify every live policy attachment or prove that a
  particular role was first created in that run.
- Banking [protected audit 38318982706](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38318982706),
  its verified ZIP digest, the older protected bootstrap policy/trust snapshot,
  current GitHub settings and PR #17 source. The saved audit observes AWS at
  8:05-8:06 PM Eastern on 12 October; it does not collect the bootstrap's complete
  current IAM inventory. Local AWS CLI still returns NoCredentials.

## What permits Terraform role creation

| Control | AWS three-tier | Healthcare EKS Fargate | Banking |
| --- | --- | --- | --- |
| Terraform execution identity | Existing OIDC role supplied by AWS_ROLE_TO_ASSUME; actual ARN/live permissions are not documented in the requested files | Read-only plan role from AWS_PLAN_ROLE_ARN; apply identity from AWS_ROLE_ARN, documented as cloudbatch818-zein-hcsecops-gha-apply | Existing cloudbatch818-mahmoud-cloudops-bootstrap; retained as the sole infrastructure execution identity |
| Identity IAM grant | Actual role policies unavailable from repository source; do not infer their contents | Documented manually installed inline apply-policy; IamProjectOnly permits iam:* on project role/policy/instance-profile names and the Ohio cluster OIDC provider | Last verified CloudOpsTrackerBootstrap IAM writes match cloudbatch818-mahmoud-retail-* only; BankingReleasePlatformState grants backend access, not CreateRole |
| STS session cap | No inline-session-policy or managed-session-policies declared in the requested workflows | No extra STS session cap declared in terraform-apply.yml | Previous platform cap excludes role creation. PR #17 has a separate bounded IAM cap and retains routine platform IAM-administration restrictions |
| Service roles managed in Terraform | EC2 app role/instance profile and ECS execution/task roles | EKS cluster/Fargate roles and IRSA roles | PR #17 defines exactly three service roles in separate IAM state and exports their ARNs to the platform |
| PassRole | Required by referenced compute role/profile usage; actual grant unknown | iam:* includes PassRole on project role names; no separate PassedToService condition in that statement | Later platform proposals pass each exact cluster/Fargate/flow role only to its reviewed AWS service. Creating these roles alone needs no PassRole |
| Permissions boundary | None declared on the inspected Terraform roles; actual account mandates unknown | None declared on the inspected EKS/IRSA roles; actual account mandates unknown | Service boundary is a Banking project design choice. No current evidence establishes an AWS/account requirement; the extended audit reads its existence and default version explicitly |
| Service-linked roles | Actual prior existence and creation grants unknown from inspected files | Conditional CreateServiceLinkedRole includes eks.amazonaws.com and eks-fargate.amazonaws.com, alongside listed supporting services | Banking's saved audit confirms both EKS/Fargate service-linked roles already exist; no recreation is requested |
| Execution-role protection | Actual policy protection unknown | ProtectCiRoles explicitly denies iam:* on its gha-* role names | New IAM root never manages the bootstrap/deployment roles, original policies or GitHub OIDC trust |

The backend only stores state and locks. An identity allow on the requested role
ARN, a session that permits the operation, and applicable boundary/organization
controls must allow the API call. A new session allow cannot supply a missing
identity grant, and an allow does not override an explicit deny. See
[AWS policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html).
Repository source does not expose all actual session restrictions, attached
policy versions, boundaries or SCPs in either reference account.

## Smallest legitimate Banking capability

First collect the fresh bootstrap inventory and scoped simulation evidence.
If the last snapshot still represents its permissions, an authorized additive
grant needs CreateRole and TagRole on exactly the three requested Banking role
ARNs; AttachRolePolicy for the two exact AWS-managed policies on their matching
roles; and PutRolePolicy on the flow-log role. Read/refresh/verification APIs and
the new IAM backend state/lock objects must also be permitted. Preserve the
original Retail grants and both bootstrap trusts. Use the IAM-stage session cap;
leave role administration excluded from routine platform sessions.

The reviewed proposal permits first creation only. It grants no service-role
deletion/replacement, shared-role editing, unrestricted IAM, new GitHub identity,
or bootstrap trust expansion. Later PassRole, networking, EKS, KMS and data
grants are separate stages with their own review. Permission to write Terraform
state cannot replace any of these grants.

The mandatory named managed-policy attachment and fixed boundary in PR #17 are
project review controls; AWS does not require that particular policy name,
attachment mechanism, separate state or an administrator-owned boundary merely
to create a role. Keep the separate state and exact inventory for reviewability.
The boundary limits the service roles even if an attached or inline policy is
broader, particularly because PutRolePolicy cannot constrain its JSON content.
It adds administrator setup and can block required service operations if too
narrow. Without it, the grant can remain scoped to exact role names and managed
attachments, but the flow role's inline-policy content relies on trusted code,
review and the saved-plan guard. Removing the boundary would require a reviewed
change to the role, grant, guard and state contract together; no such change is
made here. If the audit finds no account mandate and no boundary, discuss this
tradeoff before requiring its creation or selecting the reviewed alternative.

## Deployment-role and remaining evidence

The saved AWS audit reads all six retained CloudOpsTracker managed policies and
both Banking inline policies. Each deployment role has sixteen scope findings
and no role boundary. Narrow Banking allows do not reduce the other allows.
Current trusts contain only their Banking environment subject; the original
CloudOpsTracker subject is absent. The historical original trust document is
needed to prove an overwrite and construct an exact approved restoration.
Do not guess a subject, detach shared policies or change trusts automatically.
The smallest reuse correction, if approved, is to preserve/reconcile the verified
original trust and retain the exact Banking release session caps, followed by
live OIDC and Kubernetes denial tests. Broader sessions remain a shared-role
risk; do not claim account-wide least privilege from workflow caps alone.

No Banking cluster or the three service roles existed in that audit. Existing
service-linked roles were verified. Organization/quota read denials do not prove
an SCP caused them. KMS/operator nominations, capacity evidence, deployment host,
live workloads, data, monitoring, promotion, rollback and trainer evidence remain
unverified. No AWS resource or permission was changed by this comparison.
