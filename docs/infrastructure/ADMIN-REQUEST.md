# Consolidated Phase 3 administrator request — proposed, not applied

Account: `866934333672`. Region: `us-east-2`. Project: `BankingReleasePlatform`, environment: `dev`, cluster: `banking-dev`. GitHub repository: `mhachem110/BankingReleasePlatform-AWS-EKS`.

Please review this request together with the infrastructure PR and cost estimate. **Do not create the chargeable encryption key or deploy infrastructure until the owner approves that expense.** The operator cannot create IAM roles. Terraform contains no IAM role or identity-provider creation resources.

## Required identities

Create or explicitly authorize these distinct project roles; return their complete actual ARNs, including paths:

| Role name | Trusted service | Permission policy |
| --- | --- | --- |
| cloudbatch818-mahmoud-banking-eks-cluster | eks.amazonaws.com | AWS managed AmazonEKSClusterPolicy |
| cloudbatch818-mahmoud-banking-eks-nodes | ec2.amazonaws.com | AmazonEKSWorkerNodePolicy, AmazonEC2ContainerRegistryPullOnly, AmazonEKS_CNI_Policy |
| cloudbatch818-mahmoud-banking-flow-logs | vpc-flow-logs.amazonaws.com | Generated BankingFlowLogs.json, exact Banking log group |
| cloudbatch818-mahmoud-banking-alb-controller | pods.eks.amazonaws.com | Reviewed AWS controller policy in iam/phase3/aws-load-balancer-controller-v2.14.1.json |

The node's CNI policy deliberately supports first boot with AWS default add-ons, preventing a circular dependency between node readiness and managed add-on installation. Pods cannot inherit IMDS credentials because worker metadata requires IMDSv2 and hop limit 1. Migrate CNI permissions to a dedicated workload role in Phase 6 after validating that bootstrap path; do not remove them prematurely. The existing bootstrap role must never serve as the cluster or node role.

The controller role uses EKS Pod Identity, restricted to cluster `banking-dev`, namespace `kube-system`, service account `aws-load-balancer-controller`. This avoids creating another IAM OIDC identity provider for the EKS issuer. Its AWS permissions are needed when the controller is installed in Phase 4; the association itself creates no ALB. The official v2.14.1 policy is taken from [AWS's documented release](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html); review its service-linked-role allowance and tag conditions. Do not attach it to the GitHub or node role.

Also return the actual existing same-account **operator IAM role ARN** and a **different application deployment IAM role ARN** approved for this project. The role names seen in the Console (`cloudbatch818-mahmoud-cloudops-deploy-dev`, stage/uat/prod) are observations, not authorization to reuse them. Existing trusts/permissions for those roles were not reviewed. If reuse is unsuitable, an administrator must supply a separate role. Do not give implicit cluster admin to the GitHub bootstrap role: Terraform grants the operator explicit cluster administration and the application deployer edit access only in `banking-dev`.

## Encryption key

Provide an enabled same-account, same-Region symmetric KMS encryption key, with automatic rotation, approved for EKS secret encryption and the two Banking CloudWatch log groups. Prefer an approved existing key if its owner authorizes additive access; preserve its complete current policy. Otherwise a dedicated key costs approximately $1/month plus API usage and needs owner approval before creation. `BankingKeyPolicy.json` is a full template **for a new dedicated key only**, not a replacement for an existing shared key policy.

## Additive permissions for the existing GitHub bootstrap role

Keep `CloudOpsTrackerBootstrap` and `BankingReleasePlatformState` unchanged. Add a separate inline policy named **BankingReleasePlatformPhase3**, rendered by:

```powershell
python scripts/infra/prepare-admin-request.py --account 866934333672 --region us-east-2 --bucket mhachem-banking-tfstate-866934333672 --kms-key-arn ACTUAL_APPROVED_KEY_ARN --output artifacts/phase3-admin
```

This produces complete JSON trust files for the four service roles, `BankingFlowLogs.json`, the separate `BankingReleasePlatformPhase3.json`, and a new-key policy template. The script is local only. It does not call AWS. Default role ARNs assume no IAM path; if the administrator uses paths, update the rendered exact ARNs to the returned values before approval. Never guess a KMS key ARN or reuse another project's roles to satisfy a validation check.

The separate inline policy grants only:

- `iam:PassRole` on the four exact Banking roles, each restricted to its intended service.
- Read/write of new platform state `banking-release-platform/dev/platform/terraform.tfstate` and read/write/delete of its separate `.tflock`; no state-object delete or bucket configuration permissions.
- Prefix-scoped listing for this backend and Terraform's unused workspace discovery path.
- Describe/list-grants and AWS-resource-conditioned CreateGrant on the exact approved key.

The original inline policy already grants EC2/EKS/ECR/CloudWatch Logs management and IAM reads broadly. Despite Retail statement names, most of those grants are `Resource: *`; they are not limited to Retail resources. This request does not expand those services or claim that role is least privilege. The Phase 3 workflow caps temporary sessions to Ohio EC2/EKS/ECR/log operations, IAM reads/exact PassRole, the exact key and exact platform state path. Some EC2 create/manage actions require wildcard resources; saved-plan scope validation and protected reviews are additional controls, not substitutes for an administrator-approved permission boundary or dedicated role.

## Console actions after authorization

1. **IAM → Roles → each new approved service role → Trust relationships → Edit trust policy:** paste its complete rendered trust JSON. On Permissions attach the exact managed policies listed above, or use Add permissions → Create inline policy → JSON for flow logs. These actions are for the administrator after authorization.
2. **IAM → Policies → Create policy → JSON:** paste the complete checked-in controller policy; attach only to the approved controller role. It is a workload policy, not a GitHub trust policy.
3. **KMS → Customer managed keys → approved key → Key policy:** review existing policy and approve additive Banking use. For a new dedicated key only, review generated BankingKeyPolicy.json and automatic rotation. Preserve all existing administrators/users for shared keys.
4. **IAM → Roles → cloudbatch818-mahmoud-cloudops-bootstrap → Permissions → Add permissions → Create inline policy → JSON:** paste generated BankingReleasePlatformPhase3.json; name it exactly. Leave both existing inline policies untouched. Verify policy count/names and exact role/key/state resources before saving.
5. **GitHub → Settings → Environments → bootstrap:** retain existing dev-only branch, owner review and no admin bypass; retain existing AWS_ROLE_ARN secret. Add non-secret `PLATFORM_INPUTS_JSON` using the full reviewed inputs described in DEPLOYMENT.md. No GitHub trust change is required for this infrastructure workflow because it still uses the verified bootstrap environment.

## Effective permission and quota review

Confirm permission to reuse the existing role, add the separate inline policy, pass the exact service roles, create EKS access entries and create KMS grants. Confirm no SCP/permission boundary/resource policy denies the proposed actions, chosen Region, public HTTPS endpoint with narrow CIDRs, NAT/EIP, encryption or service-linked-role operations. Absence of a boundary on the bootstrap role and successful S3 operations do not prove Phase 3 permissions.

Confirm `AWSServiceRoleForAmazonEKS`, `AWSServiceRoleForAmazonEKSNodegroup`, Auto Scaling and ELB service-linked roles exist or may be created by the services under approved permissions. Do not grant general role creation to the training user. Check Ohio VPC, NAT/EIP, EC2 On-Demand vCPU, EKS cluster, node group and network-interface quotas against the shared account's existing usage. Provide an approved operator/runner IPv4 CIDR (/24 or narrower); do not substitute `0.0.0.0/0`. Ordinary GitHub-hosted runners are not guaranteed to be within that CIDR, so later Helm deployment needs an approved runner network or operator connection.

Return approved ARNs, policy confirmations, effective SCP/quotas findings and endpoint CIDRs together. No AWS deployment can run until these prerequisites and the paid plan are approved.
