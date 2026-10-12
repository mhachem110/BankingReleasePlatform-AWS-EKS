# Application deployment variables and authorization

Nothing in this document creates roles, trust, environments or resources.
APP_DEPLOYMENTS_ENABLED is absent/false by default. Do not change it until separate
deployment approval and verified Phase 3 readiness. Baseline reconciliation and the
owner-approved application governance change are complete.

Create/review protected GitHub environments dev, stage, uat and prod through the
authorized infrastructure/security workstream. Require human reviewers and restrict
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
| EKS_CLUSTER_NAME | banking-dev; later banking-stage, banking-uat, banking-prod only if separately provisioned |
| K8S_NAMESPACE | Same banking-ENV namespace as the target cluster |
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
roles; dev's role is not automatically authorized on later clusters.

Minimum role permissions to review:
- ecr:GetAuthorizationToken on * (API requires it).
- ecr:DescribeRepositories, DescribeImages and pull/upload layer/PutImage APIs on
  exactly the two approved existing repository ARNs.
- eks:DescribeCluster on the exact approved environment cluster ARN.
- sts:GetCallerIdentity and OIDC AssumeRoleWithWebIdentity through the approved trust.

No IAM administration, EKS creation/update, Fargate profile creation, EC2 mutations,
Terraform state access, S3 writes, RDS, ELB or infrastructure apply permission is needed.
ECR push/storage itself requires explicit authorization; nothing was pushed offline.
An application runtime ServiceAccount needs no AWS permissions for these APIs.
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
wait for approval. EKS namespace Edit alone might not supply Namespace/Node get.
The approved infrastructure access entry maps the application role to the
banking-release-verifier group. After cluster creation, an approved operator applies
iam/phase3/deployer-verification-rbac.yaml, granting Node get and get on only the
banking-dev Namespace. This separate binding permits verification without cluster
administration or node mutation.

Role permission/trust, environment reviewer approval, Kubernetes RBAC and network access
are independent prerequisites. None has been installed by this application PR.
