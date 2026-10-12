# Application deployment variables and authorization

Nothing in this document creates roles, trust, environments or resources.
APP_DEPLOYMENTS_ENABLED is absent/false by default. Do not change it until separate
deployment approval and verified Phase 3 readiness. Baseline reconciliation and the
owner-approved application governance change are complete.

Review the existing GitHub environments dev, stage, uat and prod through the
authorized infrastructure/security workstream. Require human reviewers for active deployments and restrict
deployment branches to dev/dev, stage/stage, uat/uat, prod/main respectively.
Prevent self-review where an eligible independent reviewer exists. A working branch
never grants environment access. No additional reviewer identity is invented.

| Environment variable (GitHub vars) | Required value/purpose |
| --- | --- |
| APP_DEPLOYMENTS_ENABLED | true only after explicit application publication/deployment approval |
| APP_DEPLOY_ROLE_ARN | Administrator-approved application role, separate from bootstrap/Terraform/controller/Pod execution roles |
| AWS_ACCOUNT_ID | Exact approved 12-digit account ID |
| AWS_REGION | us-east-2 for the prepared dev infrastructure |
| ECR_ACCOUNT_REPOSITORY | ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/banking-dev-account |
| ECR_PAYMENT_REPOSITORY | ACCOUNT.dkr.ecr.us-east-2.amazonaws.com/banking-dev-payment |
| EKS_CLUSTER_NAME | banking-dev for both dev/prod in shared-cluster-demo mode |
| K8S_NAMESPACE | banking-dev for dev, banking-prod for prod; namespaces differ from shared cluster |
| INFRA_ROLE_ARN / BOOTSTRAP_ROLE_ARN | Existing protected role ARNs, used to reject accidental application-role reuse |

GITHUB_REPOSITORY, GITHUB_REF, GITHUB_SHA, GITHUB_RUN_ID and GH_TOKEN are supplied by
Actions. GH_TOKEN is the short-lived read-only repository token for artifact/API access,
not an AWS credential. Inputs are passed through quoted environment variables, never
interpolated into command text.

Publication runs on a GitHub-hosted Linux runner and uses only ECR APIs.
Deployment runs on an approved dedicated self-hosted Linux x64 runner with label
banking-deployer, with Docker, Python 3.12, AWS CLI v2, gh CLI, git and approved EKS
API network access. Do not attach this runner to untrusted PR CI.
Use an existing approved runner; provisioning one is a separate owner decision.
The checksum installer supplies Helm/kubectl. No dynamic public-endpoint broadening
or per-run security-group edits occur. Deployment jobs serialize per environment and
never cancel a running rollout/rollback.

The administrator must review an OIDC role with audience sts.amazonaws.com and exact
subjects repo:mhachem110@150286776/BankingReleasePlatform-AWS-EKS@1413860979:environment:dev (and only
separately approved environment subjects for promotion). GitHub's environment branch
rules independently enforce the source ref; OIDC environment subjects do not encode it.
Do not trust feature/app, infra, bootstrap working branches or wildcard environment
subjects. No static AWS key secrets are used. Prefer environment-specific application
roles; dev's role is not authorized in the production namespace.

Minimum role permissions to review:
- ecr:GetAuthorizationToken on * (API requires it).
- ecr:DescribeRepositories, DescribeImages and pull/upload layer/PutImage APIs on
  exactly the two approved existing repository ARNs for dev publication. Prod gets
  approved image read operations only, with no upload/PutImage.
- eks:DescribeCluster on the exact approved environment cluster ARN.
- sts:GetCallerIdentity and OIDC AssumeRoleWithWebIdentity through the approved trust.

No IAM administration, EKS creation/update, Fargate profile creation, EC2 mutations,
Terraform state access, S3 writes, RDS, ELB or infrastructure apply permission is needed.
ECR push/storage itself requires explicit authorization; nothing was pushed offline.
The default memory-mode application ServiceAccounts need no AWS permissions.
Opt-in Phase 6 messaging requires the separately approved payment-only IRSA role
and exact queue/KMS permissions described in DATA-AND-EVENTS.md. Account still
needs no AWS API access. Pods must never receive the RDS managed master secret.
Fargate image pulls use the administrator's separate Pod execution role, not an app
ServiceAccount or GitHub role. Future controller AWS access uses the administrator-approved separate IRSA
role on kube-system/aws-load-balancer-controller.

EKS access entry/RBAC must map the approved application role to namespace-scoped
release resources: Deployments/ReplicaSets, Services, ServiceAccounts, PDBs, optional HPA,
Helm release Secrets, Pod get/list/watch and Pod logs/portforward subresources.
Grant get on the approved Namespace and get on Nodes for compute-type verification
without node mutation or cluster administration. Node get is cluster-scoped because
the verifier confirms actual eks.amazonaws.com/compute-type=fargate labels.
Default workflows keep Ingress off, so granting ingress writes is optional and should
wait for approval. The prepared release Role supplies no cluster mutation rights.
The approved infrastructure access entry maps the application role to the
banking-release-dev or banking-release-prod group. After cluster creation, an approved operator applies
iam/phase3/deployer-verification-rbac.yaml, granting Node get and get on only the
own banking-dev or banking-prod Namespace. This separate binding permits verification without cluster
administration or node mutation.

Role permission/trust, environment reviewer approval, Kubernetes RBAC and network access
are independent prerequisites. None has been installed by this application PR.

## Verified manual environment update and demonstration mode

On 12 October GitHub confirmed all five environments. Both dev and prod now require
owner review, no administrator bypass, exact dev/main branch restrictions and complete
non-secret variables. APP_RELEASE_MODE=shared-cluster-demo permits dev then prod
against banking-dev, retaining the source branch promotion routes dev/stage/uat/main.
Stage/UAT are available for branch governance and remain inactive as paid workloads.
Deployment/data switches remain false and prod runtime is explicitly memory mode.
Prod persistence/messaging cannot be enabled through the current dev-only workflow;
its isolated data design requires a separate actual resource/cost plan approval.

The existing CloudOps deployment role trusts/permissions are user-reported and await
full AWS audit. Workflow STS caps add no permission and constrain dev publication and
read-only prod ECR/cluster discovery. No production rebuild/push is permitted.
Successful version-2 dev deployment evidence binds cluster, namespace, run/commit and
both exact scanned digests before prod. Legacy/sequential evidence fails in demo mode.
EKS access uses only operator-installed namespace roles, with no managed Edit policy;
scripts/deploy/isolation.py verifies live cross-namespace/cluster denials before Helm.
