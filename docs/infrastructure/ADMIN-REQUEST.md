# ONE Banking Fargate administrator request — proposals only

Account **866934333672**, Ohio **us-east-2**, cluster/namespace **banking-dev**.
Updated after normal code-only integration of PRs #13/#14 into dev `f3afff4`
on 12 October 2026. This remains the ONE administrator handoff for the project.
The first EKS/Fargate plan needs sections 1–5 and the bootstrap configuration;
controller/payment IRSA and the data rollout follow the actual cluster interface.
Do not delay the first platform plan waiting for a guessed future issuer or database.
Review the complete package together. It does not authorize live IAM changes,
paid key creation or Terraform apply. The owner cannot create IAM roles.
Obtain the owner's access-change approval before an administrator applies it;
paid infrastructure requires separate approval of the actual saved resource plan.

## Verified existing prerequisites

Read-only inspections on 11 October 2026 confirmed the existing Banking S3 state
bucket, SSE-S3, versioning, public-access blocking, owner-enforced ownership,
90-day noncurrent retention, seven-day multipart cleanup and no current expiry.
Successful Phase 2 recovery is the previous native-locking/both-roots no-change
evidence; no state operation was repeated. Preserve bucket and Phase 2 keys.

Existing bootstrap role:
arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-cloudops-bootstrap
Its exactly two inline policies are CloudOpsTrackerBootstrap and
BankingReleasePlatformState; no boundary. Preserve both and both current trusts:

```text
repo:mhachem110@150286776/E-CommerceAWS_Terraform@1399001550:environment:bootstrap
repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979:environment:bootstrap
Federated provider: arn:aws:iam::866934333672:oidc-provider/token.actions.githubusercontent.com
Action: sts:AssumeRoleWithWebIdentity
Audience: sts.amazonaws.com
```

GitHub immutable owner/repository IDs and the provider audience match. Protected
bootstrap retains owner review, dev-only selected branch, no admin bypass.
BOOTSTRAP_STATE_READY=true; AWS_OPERATIONS_ENABLED=false.

EKS/Fargate service-linked roles already exist:
AWSServiceRoleForAmazonEKS and AWSServiceRoleForAmazonEKSForFargate. The Fargate
service role trusts eks-fargate.amazonaws.com; Pod execution is a DIFFERENT role
that trusts eks-fargate-pods.amazonaws.com. ELB's service-linked role was observed
earlier; recheck at the later ALB gate. No recreation is requested.

Organizations identifies this as the organization's **management account**.
[SCPs do not restrict its users/roles](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html).
Do not request an SCP relaxation. Identity/session/boundary/key policies remain
relevant; S3 connectivity does not prove EKS permissions.

Fresh IAM inventory recheck found no cloudbatch818-mahmoud-banking roles. Existing
CloudOps deployment roles are not approved for Banking reuse. No actual approved
operator or KMS key ARN has been supplied. Earlier inspections found no banking-dev
cluster/ECR names and no primary VPC collision with 10.70.0.0/16. Preflight rechecks
all CIDR associations/AZs/collisions. Human quota Console inspection was denied
on servicequotas:ListAWSDefaultServiceQuotas; capacity remains unverified, not zero.
No self-hosted runner or application environment is configured.

## Complete proposed files and one administrator work package

All copy-and-paste JSON is in [iam/phase3/proposed](../../iam/phase3/proposed/README.md).
No new-role or new-key template may overwrite a shared resource's policy.

### 1. Three distinct service roles

IAM -> Roles -> Create role -> Custom trust policy: paste the named complete trust
below, use the exact name, attach the indicated managed/inline policy. Return full
actual ARNs and any boundaries. Fargate execution MUST have no IAM path.

| Exact role | Complete trust file | Permissions |
| --- | --- | --- |
| cloudbatch818-mahmoud-banking-eks-cluster | cloudbatch818-mahmoud-banking-eks-cluster-trust.json | AWS-managed AmazonEKSClusterPolicy |
| cloudbatch818-mahmoud-banking-fargate-execution | cloudbatch818-mahmoud-banking-fargate-execution-trust.json | AWS-managed AmazonEKSFargatePodExecutionRolePolicy |
| cloudbatch818-mahmoud-banking-flow-logs | cloudbatch818-mahmoud-banking-flow-logs-trust.json | BankingFlowLogs.json inline |

Flow role -> Permissions -> Add permissions -> Create inline policy -> JSON ->
paste BankingFlowLogs.json. Trusts scope execution to Banking profiles and flow
logs to this account/Region. No EC2 node role, instance profile, generic IAM admin
or bootstrap-role service reuse. The current guard expects these exact names;
different authorized reuse would require a reviewed input-contract change.

### 2. Existing approved operator and distinct application identity

First nominate an existing authorized human-assumable operator role; preserve
its trust. Confirm the actual human may assume it, add BankingOperatorDiscovery.json
only if needed, and return its approved ARN. Terraform assigns explicit cluster
admin through an access entry. No human trust or extra operator role is guessed.

Proposed new dedicated app role: cloudbatch818-mahmoud-banking-app-deploy-dev.
Use BankingAppDev-new-role-trust.json and BankingAppDev-permissions.json. Exact
immutable Banking/environment:dev GitHub subject, STS audience; ECR rights on
only two Banking repos plus cluster discovery, no state/IAM/EC2/ELB permissions.
Shared-role reuse needs complete policy review and additive full trust preserving
authorized relationships; do not replace CloudOps trust with the new-role template.
Terraform grants banking-dev namespace Edit plus banking-release-verifier mapping.
After cluster creation the approved operator creates the namespace and applies
iam/phase3/deployer-verification-rbac.yaml (Node get and banking-dev namespace get
only). App containers do not inherit the Fargate execution role.

### 3. Actual approved KMS key and resource tags

KMS -> Customer managed keys -> owner-authorized Ohio key: confirm Enabled,
Symmetric, ENCRYPT_DECRYPT, correct account. Preserve shared-key policy/tags and
add only reviewed Banking contexts/grant delegation. BankingKeyPolicy.json is a
COMPLETE policy for a NEW dedicated key only. New paid key creation still needs
owner approval. Do not select another project's key or fabricate an ARN.

IAM -> new role -> Tags / KMS -> new dedicated key -> Tags: use COMPLETE maps in
BankingAdministratorTags.json. Approved common values: Project=BankingReleasePlatform,
Environment=dev, ManagedBy=Administrator, Owner=MahmoudHachem,
Purpose=CloudEngineerTraining, plus file-specific Name/Component. Administrator
must confirm this manual-management designation against organizational tagging
requirements; another approved value can be supplied through
--administrator-managed-by (Terraform is rejected). Actual Terraform-owned
resources retain ManagedBy=Terraform. Administrator-owned roles/key stay outside
Terraform state; tags do not authorize alteration or teardown. Shared/bootstrap identities are not retagged. CostCenter
is absent until assigned; confirm whether effective tag policy requires a real code.
Cost allocation tag activation is a separate billing-admin proposal in TAGGING.md.

### 4. Separate additive bootstrap policy — actual key pending

CloudOpsTrackerBootstrap already grants broad EC2/EKS/ECR/Logs Resource=*; Retail
statement names do not scope them. Preserve these rights; do not claim the shared
role is least privilege. Add BankingReleasePlatformPhase3 only for missing exact
PassRole, new platform state, exact-key grants and new cluster OIDC creation.
Temporary session caps services to Ohio, state writes to platform key and PassRole
to three approved service roles. No IAM role creation or state-bucket write.

BankingReleasePlatformPhase3.REVIEW-TEMPLATE.json is the COMPLETE review shape
with an explicit inert key marker, NOT ready to paste. With the actual approved
ARN, generate the COMPLETE exact-key copy-and-paste policy locally (no AWS calls):

```powershell
$approvedBankingKeyArn = Read-Host 'Actual approved Ohio KMS key ARN'
python scripts/infra/prepare-admin-request.py --account 866934333672 --region us-east-2 --bucket mhachem-banking-tfstate-866934333672 --kms-key-arn $approvedBankingKeyArn --owner MahmoudHachem --output artifacts/phase3-admin
```

For approved cluster/flow IAM paths, also pass full --cluster-role-arn /
--flow-log-role-arn. Optional --cost-center is only a real approved value; --administrator-managed-by accepts an approved external-management designation.
IAM -> bootstrap role -> Permissions -> Add permissions -> Create inline policy
-> JSON -> generated BankingReleasePlatformPhase3.json; name BankingReleasePlatformPhase3.
Check aggregate inline-policy quota. It grants precisely three service-conditioned
PassRole ARNs, platform Get/Put and lock Get/Put/Delete, exact-key Describe/ListGrants/
AWS-resource CreateGrant, tagged NEW Ohio EKS OIDC create/tag/read. No old-state
write, state-object deletion, GitHub provider edit, role/trust change or OIDC delete.
Read back both ORIGINAL policies and both ORIGINAL trusts unchanged.

### 5. Network, versions, capacity and deployment runner

Return two available approved Ohio AZs, all-association CIDR approval for
10.70.0.0/16 and actual human/runner egress IPv4 /24-or-narrower CIDRs. Private API
enabled, public HTTPS restricted; no all-Internet exception. Each new private /20
has 4091 usable addresses before allocations; approve real ENI/subnet/account headroom.

Return exact EKS 1.36 CoreDNS/Metrics Server pins supporting amd64/Fargate and their
configuration schemas. Catalog Fargate support alone is not an exact pin. Preflight
checks the actual responses/schema. Metrics Server's managed add-on listens 10251;
collection still needs 10250. No VPC-CNI/kube-proxy/Pod Identity DaemonSets.

In an already authorized temporary session, obtain outputs TOGETHER:

```bash
aws sts get-caller-identity
aws ec2 describe-availability-zones --region us-east-2
aws ec2 describe-vpcs --region us-east-2
aws service-quotas list-service-quotas --service-code fargate --region us-east-2
aws eks describe-cluster-versions --region us-east-2 --cluster-versions 1.36
aws eks describe-addon-versions --region us-east-2 --kubernetes-version 1.36 --addon-name coredns
aws eks describe-addon-versions --region us-east-2 --kubernetes-version 1.36 --addon-name metrics-server
```

For each actual selected name/version, return describe-addon-configuration.
Return actual Fargate quota AND current utilization; approve EKS/NAT/EIP/ENI limits.
Reserve 4.5 available vCPU beyond other account usage for the prepared worst case:
8 API + 3 system + 2 controller Pods and 5 simultaneous surge Pods. Initially only
3 system Pods run (0.75 vCPU); 4.5 is conservative rollout/HPA capacity, not current
usage. Do not broaden the workflow role merely to browse the quota page. Its gate
uses recent administrator-reviewed evidence and explicitly labels that provenance.

Nominate an approved existing Linux x64 machine with private API access or fixed
approved IPv4 egress and HTTPS access to GitHub/AWS/ECR. Needs Docker Linux engine,
Python 3.12, AWS CLI v2, gh CLI, git. Before Helm, GitHub Settings -> Actions ->
Runners -> New self-hosted runner -> Linux x64 on that approved host, label
banking-deployer. Keep registration tokens private; no untrusted PR CI on it.
No paid runner/VPN is requested automatically. Network/CIDRs precede plan;
registration and operator namespace/RBAC setup precede Helm.

### 6. Controller IRSA AFTER real cluster issuer exists

Controller role is not required to create the initial cluster. Verified workflow
outputs export COMPLETE controller-irsa-trust.json using actual Banking issuer/
provider, STS audience and exact system:serviceaccount:kube-system:aws-load-balancer-controller
subject. Administrator verifies EKS banking-dev Overview and IAM Identity providers,
then supplies the dedicated role with that trust and reviewed versioned
iam/phase3/aws-load-balancer-controller-v2.14.1.json. No guessed issuer/GitHub
provider changes. Controller/ALB installation is later separately approved;
Ingress uses IP targets. No ALB is created by a profile or OIDC provider alone.

## GitHub protected configuration

bootstrap: preserve reviewer, dev-only branch, no admin bypass and AWS_ROLE_ARN
secret for the existing :role/ bootstrap ARN. Preserve AWS_REGION=us-east-2,
AWS_EXPECTED_ACCOUNT_ID=866934333672, TF_STATE_BUCKET=mhachem-banking-tfstate-866934333672,
BOOTSTRAP_STATE_READY=true. Repository AWS_OPERATIONS_ENABLED=false until explicit
live-plan authorization. No settings/approvals are changed by this packet.

Populate complete PLATFORM_INPUTS_JSON from DEPLOYMENT.md using actual approved
values; owner=MahmoudHachem, cost_center absent/null unless assigned. Add protected
bootstrap CAPACITY_REVIEW_JSON, with real numbers and a timezone-aware timestamp
no more than 24 hours old. This COMPLETE shape is a REVIEW TEMPLATE:

```json
{
  "account": "866934333672",
  "region": "us-east-2",
  "reviewed_by": "ACTUAL_AUTHORIZED_ADMINISTRATOR",
  "observed_at": "ACTUAL_ISO8601_TIMESTAMP_WITH_TIMEZONE",
  "fargate_vcpu_limit": "REPLACE_WITH_ACTUAL_JSON_NUMBER",
  "current_vcpu_usage": "REPLACE_WITH_ACTUAL_JSON_NUMBER",
  "other_platform_limits_approved": true
}
```

Replace numeric string markers with actual JSON numbers. Missing/stale/future,
wrong-account/Region, invalid or insufficient evidence fails. No claimed automated
quota measurement. Owner deployment review remains mandatory.

Before app publication/deployment, create protected dev environment: owner reviewer,
dev-only branch, no admin bypass, APP_DEPLOYMENTS_ENABLED=false until separate approval.
Its COMPLETE variable set:

```text
APP_DEPLOYMENTS_ENABLED=false
AWS_ACCOUNT_ID=866934333672
AWS_REGION=us-east-2
EKS_CLUSTER_NAME=banking-dev
K8S_NAMESPACE=banking-dev
ECR_ACCOUNT_REPOSITORY=866934333672.dkr.ecr.us-east-2.amazonaws.com/banking-dev-account
ECR_PAYMENT_REPOSITORY=866934333672.dkr.ecr.us-east-2.amazonaws.com/banking-dev-payment
APP_DEPLOY_ROLE_ARN=ACTUAL_APPROVED_DISTINCT_APP_ROLE_ARN
INFRA_ROLE_ARN=arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-cloudops-bootstrap
BOOTSTRAP_ROLE_ARN=arn:aws:iam::866934333672:role/cloudbatch818-mahmoud-cloudops-bootstrap
```

No long-lived credentials. Branch routing and environment/OIDC authorization stay
separate; working branch names never become new AWS trust subjects.

### 7. Phase 6 data services, credentials and monitoring — after verified Phase 3

The merged data root is `infra/environments/dev/data`; its separate state key is
`banking-release-platform/dev/data/terraform.tfstate`. The original Phase 3
resource inventory and plan/apply workflow stay unchanged. Review the new
[protected data procedure](DATA-DEPLOYMENT.md) with this same handoff.

| Requirement | Administrator/operator return |
| --- | --- |
| Data infrastructure permissions | Additive RDS/SQS/log/alarm/SG and exact data-state permissions; preserve both original bootstrap policies and trusts plus the Phase 3 addition. Review policy size, boundaries and service API dependencies. No role/key creation by Terraform. |
| Managed session cap | Actual same-account `BankingReleasePlatformPhase6Session` policy ARN/default-version document and canonical SHA256. Render the complete proposal with `scripts/infra/data_iam.py`; use it as the separately reviewed data session cap and add required missing identity permissions without replacing shared policies. It permits no role/key creation, database deletion, message sending or other state-object writes. |
| RDS monitoring | Dedicated `cloudbatch818-mahmoud-banking-rds-monitoring`, `monitoring.rds.amazonaws.com` trust with exact banking-dev-postgres SourceArn/account, AWS-managed `service-role/AmazonRDSEnhancedMonitoringRole`, actual ARN/boundary and exact service-conditioned PassRole. Confirm existing RDS service-linked role; do not let Terraform create it. |
| Encryption | Actual enabled symmetric Ohio data key; reviewed RDS/Secrets Manager service grants, exact SQS runtime key access and CloudWatch contexts for `/banking/banking-dev/application` and `/aws/rds/instance/banking-dev-postgres/{postgresql,upgrade}`. Preserve all existing shared-key statements. A new paid key still requires separate owner approval. |
| Engine/capacity/cost | Exact current orderable PostgreSQL 17 patch and approved db.t4g class supporting gp3/encryption/Enhanced Monitoring; RDS/storage/backups/secrets/SQS/CloudWatch quotas and isolated subnet/AZ headroom. Approve single AZ, 20→40 GiB maximum growth, connection capacity up to 100 plus operator headroom, CPU credits and retained snapshots. Return dated actual pricing evidence and all data cost components, not guessed numbers. |
| Payment runtime IRSA | `cloudbatch818-mahmoud-banking-payment-runtime-dev`, actual Banking EKS issuer/provider, exact `system:serviceaccount:banking-dev:banking-payment` subject and STS audience. Source queue send/receive/delete/visibility/attributes; DLQ attributes only; approved key decrypt/data-key via SQS. No GitHub/deployer/Fargate role reuse. Render trust only after the actual issuer exists. |
| PostgreSQL identities | Authorized migration operator can retrieve the actual RDS-managed master secret; APIs must use separate runtime logins with the schema rights in DATA-AND-EVENTS.md, no DDL/ownership and VerifyFull hostname/CA verification. Return secret ARNs/reference names and delivery/rotation ownership; never passwords/session tokens. |
| Fargate-compatible secret delivery | Approved operator retrieves only the scoped runtime secrets into namespace Kubernetes Secrets through a protected runner, with no console/command-line/log/plaintext artifact exposure. Account/payment use mounted `connectionString`; mount reviewed RDS CA in `root-ca.pem`. Review Kubernetes Secret RBAC and etcd encryption. No DaemonSet/CSI dependency is assumed on Fargate. Rotation includes an approved rolling restart and replay verification. |
| Logs and collection | Scoped Pod execution log-stream/event permission to the precreated application group; reviewed `aws-observability/aws-logging` configuration; per-Pod Prometheus/Grafana namespace RBAC, Fargate-compatible placement, resources, persistence/access and costs. No logging DaemonSet and no public `/metrics`. |
| Alert destination | Existing approved Ohio `banking-dev-*` SNS topic ARN, confirmed recipients, CloudWatch publish authorization/topic policy and explicit notification approval. Five service alarms plus six Prometheus alerts require actual delivery/incident verification. No subscriber or SNS topic is invented. |

`scripts/infra/data_iam.py --inputs ACTUAL_DATA_INPUT_FILE --policy-arn ACTUAL_APPROVED_POLICY_ARN --output artifacts/data-admin`
renders complete additive proposals and a digest locally. Add `--issuer` only for
the actual verified cluster issuer. Inputs contain IDs/ARNs, never credentials.
Treat generated documents as proposals until explicitly authorized and read back.
The managed cap avoids STS's 2,048-character inline-policy limit; generation checks
the 6,144-character managed-policy limit. Default-version drift fails preflight.

Keep protected bootstrap `DATA_OPERATIONS_ENABLED=false` until a separate data-plan
approval. Later populate actual DATA_INPUTS_JSON, DATA_COST_REVIEW_JSON,
DATA_SESSION_POLICY_ARN and DATA_SESSION_POLICY_SHA256. Existing AWS_ROLE_ARN and
immutable bootstrap OIDC subject stay unchanged. Data plan/apply each require
personal bootstrap review; apply uses the exact same-run saved plan and cost receipt.
Do not run this workflow while obtaining the first platform prerequisites.

## Return ONE administrator bundle, in deployment order

Owner-authorized actual service/operator/app ARNs and trusts/policies/boundaries,
actual approved KMS ARN/key policy, rendered additional Phase3 policy, unchanged
original policies/trust confirmation, AZs/all-CIDR/endpoint approvals, actual add-on
pins/schemas, recent capacity report and runner/network arrangement. Confirm
optional CostCenter is accepted or supply the actually required approved code.
Do not return credentials/session tokens.

Include section 7 approvals/owners and known actual ARNs in the same bundle; mark
post-EKS issuer/DB/runtime values as pending until generated and verified. Later
return those actual interfaces as one update to this handoff, not a new unrelated
administrator request. Actual absence/authorization is rechecked; source proposals
and successful offline tests do not satisfy live IAM/key/secret requirements.

After prerequisites AND reviewed code merge, the owner authorizes the protected
live plan window. Present actual inventory/effective tags/hash and costs before
requesting paid apply approval. No paid deployment is authorized here.
