# Phase 3 reviewed deployment procedure

Current status: code preparation only. No paid Phase 3 infrastructure exists. Both completed Phase 2 roots stay unchanged. The new root is `infra/environments/dev/platform`, with separate state key `banking-release-platform/dev/platform/terraform.tfstate` in the existing bucket. Nothing imports, recreates or manages that bucket.

## Review once, then deploy deliberately

1. Review and approve the `infra → dev` PR; merge only after green checks and owner approval. No working branch is deleted. Future work starts by fetching, synchronizing origin/infra and ordinarily merging origin/dev.
2. Review ADMIN-REQUEST.md and COSTS.md together. Confirm service roles, the approved encryption key, operator/deployer access, shared-account quotas/SCPs, selected AZs, CIDR and endpoint access. Administrator IAM changes and a new paid key need owner authorization. No local AWS access keys are required.
3. Retain the existing protected `bootstrap` environment with dev-only branch and owner review/no admin bypass. Keep `AWS_ROLE_ARN` and the verified immutable bootstrap OIDC subject. Working branch `infra` does not acquire AWS trust.
4. Add environment variable `PLATFORM_INPUTS_JSON`. Use this complete shape, replacing every placeholder with administrator-approved data. This is configuration, not a secret; never include credentials or passwords.

```json
{
  "availability_zones": ["us-east-2a", "us-east-2b"],
  "vpc_cidr": "10.70.0.0/16",
  "endpoint_cidrs": ["APPROVED_OPERATOR_OR_RUNNER_IPV4_CIDR"],
  "cluster_role_arn": "ACTUAL_APPROVED_CLUSTER_ROLE_ARN",
  "node_role_arn": "ACTUAL_APPROVED_NODE_ROLE_ARN",
  "flow_log_role_arn": "ACTUAL_APPROVED_FLOW_LOG_ROLE_ARN",
  "controller_role_arn": "ACTUAL_APPROVED_CONTROLLER_ROLE_ARN",
  "operator_role_arn": "ACTUAL_APPROVED_OPERATOR_ROLE_ARN",
  "deployer_role_arn": "ACTUAL_APPROVED_DISTINCT_APPLICATION_DEPLOY_ROLE_ARN",
  "kms_key_arn": "ACTUAL_APPROVED_SYMMETRIC_KEY_ARN",
  "kubernetes_version": "1.36",
  "node_release_version": "REVIEWED_AL2023_RELEASE_VERSION",
  "addon_versions": {
    "vpc-cni": "REVIEWED_COMPATIBLE_VERSION",
    "kube-proxy": "REVIEWED_COMPATIBLE_VERSION",
    "coredns": "REVIEWED_COMPATIBLE_VERSION",
    "metrics-server": "REVIEWED_COMPATIBLE_VERSION",
    "eks-pod-identity-agent": "REVIEWED_COMPATIBLE_VERSION"
  }
}
```

Get exact versions read-only in **EKS → Add-ons → select Kubernetes 1.36 compatibility**, or via approved temporary AWS credentials using `aws eks describe-addon-versions --kubernetes-version 1.36 --addon-name NAME`. Read AL2023 release from Systems Manager → Parameter Store → `/aws/service/eks/optimized-ami/1.36/amazon-linux-2023/x86_64/standard/recommended/release_version`. This parameter is public, non-secret. Terraform never silently selects `most_recent`; the preflight verifies supplied pins against AWS.

5. Only after plan execution is authorized, set repository variable `AWS_OPERATIONS_ENABLED=true` in Settings → Secrets and variables → Actions → Variables. Actions → **Controlled Banking infrastructure** → Run workflow → branch **dev**, operation **plan**, approval blank. Approve its protected bootstrap review. This reads prerequisites and plans only; it writes native Terraform locks and saves local plan artifacts, not infrastructure. The session cannot write the bucket configuration or Phase 2 state paths.
6. Review `plan.txt`, `plan-review.json`, saved-plan SHA256 and updated costs. The guard allows only creation of the reviewed platform resource types plus no-ops; no updates, replacements, deletion, IAM-role creation, RDS or bucket resources. It fails closed on existing Banking names or overlapping primary/secondary VPC CIDRs. Do not grant deployment approval merely because CI passed.
7. After owner approval of the real resource plan and costs, dispatch operation **apply**, approval **APPLY-REVIEWED-PHASE3-PLAN**. This produces a fresh plan and pauses again at the protected apply environment. Review that run's actual artifact/hash/costs before approving. Apply downloads only its same-run artifact, verifies SHA256 and unchanged inputs, and passes the exact binary saved plan to Terraform. Terraform also rejects stale state. No re-plan is silently applied.
8. Post-apply verification must show ACTIVE EKS and worker node group, healthy five add-ons, both immutable scan-on-push repositories and a zero-change Terraform plan. These checks have not run against live Phase 3 resources yet. A failed or partially completed apply needs an individually reviewed recovery/update workflow; this initial create-only workflow deliberately refuses automatic changes to existing resources.
9. Return `AWS_OPERATIONS_ENABLED=false` after the approved operation, success or failure. Leave `BOOTSTRAP_STATE_READY=true`. Neither CI nor an application release triggers Terraform apply.

## Networking and Kubernetes reachability

The proposed VPC spans two AZs. Each has public, private application and isolated database subnets. Nodes use only application subnets and no public IPv4. One public NAT Gateway supplies outbound HTTPS; it is a development availability tradeoff and can produce cross-AZ traffic charges. The free S3 Gateway Endpoint avoids NAT processing for S3/ECR image layers. Database subnets have local routes only; no RDS instance is created.

EKS enables its private API endpoint and permits public HTTPS only from explicitly approved IPv4 CIDRs (/24 or narrower). AWS Terraform operations use the AWS API and do not require Kubernetes endpoint access. Later `kubectl`/Helm operations do. Ordinary GitHub-hosted runner IPs are dynamic; do not widen access to all Internet addresses to make deployment work. Approve a runner network or use an authorized operator on an allowed address. No runner machine or VPN is created here.

The node group starts with two t3.medium On-Demand AL2023 workers (min 1/max 3), encrypted 20 GiB gp3 disks and IMDSv2/hop 1. Node-count scaling is manual until a separately reviewed autoscaler is installed. The Helm HPA scales pods only and needs metrics-server; it does not add EC2 nodes.

All five EKS control-plane log types and VPC flow logs use the approved KMS key and 30-day retention. The AWS-created cluster security group and project node group rules are separate from Kubernetes NetworkPolicy. Managed VPC CNI enables ingress policy enforcement for the future banking namespace. Initial CNI standard-mode startup behavior and fine-grained egress hardening remain Phase 6 limitations.

## Prepared Helm package

`helm/banking` renders a distinct Deployment, ClusterIP Service, service account, disruption budget and optional HPA for each API. Both use immutable image digests, resource requests/limits, startup/readiness/liveness probes, non-root/read-only containers, disabled service-account token mounting and temporary writable `/tmp`. Payment reaches Account through `http://RELEASE-account:8080/` Kubernetes DNS. Application liveness is process health, not a dependency check that restarts Payment when Account is unavailable.

Ingress defaults **off**. Enabling it requires an approved ACM certificate, host, controller installation and ALB source CIDRs; doing so creates a paid ALB and needs Phase 4 approval. Controller Pod Identity is prepared in Terraform; its Helm deployment is separate from the AWS root. Because node IMDS is restricted, later controller installation must explicitly supply `region=us-east-2`, `vpcId=actual-vpc-id`, `clusterName=banking-dev`, and service account `aws-load-balancer-controller` in `kube-system`, consistent with the approved role association. Pin and review chart/controller compatibility before installation. No ALB, application image publication or live Helm deployment ran during this preparation.

## Cleanup safety

No destroy workflow is provided. Later cleanup requires a separate owner-approved destroy plan targeting **only** the platform root/key. Remove approved application ingress first so its controller removes ALB/target resources. Review the node group, ENIs, NAT/EIP, VPC, ECR content and retained logs/key ownership. ECR `force_delete=false` prevents silent removal of tagged releases; archive/delete only approved images before an approved destroy. Never destroy `infra/bootstrap`, modify Retail resources, delete the state bucket or manually force-unlock. Keep the administrator-managed key while encrypted logs/secrets need it; destruction schedules require separate review.
