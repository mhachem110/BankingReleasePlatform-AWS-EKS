# Fargate deployment and verification procedure

Status: source prepared, not deployed. Phase 2 is complete and unchanged. Use only infra/environments/dev/platform with platform key banking-release-platform/dev/platform/terraform.tfstate in the existing approved bucket. There is no bucket resource, import, state migration or initialization retry in this workflow.

## One reviewed infrastructure operation

1. PRs #8/#9/#10/#11 are integrated in dev; final preparation merged as 85a7b1d. Review the current consolidated administrator request, actual inputs, tags and costs. Future changes still require reviewed PRs and separate owner merge approval. Working branches are retained and synchronized with dev before later work. See RECONCILIATION.md for current evidence and access limits.
2. Obtain administrator-approved prerequisite roles, existing service-linked roles, actual KMS key, operator/deployer identities, quotas/SCP review and endpoint source CIDRs. Paid key creation requires owner approval. Follow ADMIN-REQUEST.md; neither Codex nor Terraform creates roles.
3. GitHub -> Settings -> Environments -> bootstrap: retain its dev-only branch restriction, required owner review, no admin bypass, verified immutable OIDC subject and AWS_ROLE_ARN secret. Preserve AWS_REGION=us-east-2, AWS_EXPECTED_ACCOUNT_ID and TF_STATE_BUCKET, and BOOTSTRAP_STATE_READY=true. AWS_OPERATIONS_ENABLED stays false until the owner authorizes a live plan.
4. Add bootstrap environment variable PLATFORM_INPUTS_JSON with this COMPLETE shape. Replace placeholders with actual administrator-approved values; never put credentials in it.

```json
{
  "availability_zones": ["us-east-2a", "us-east-2b"],
  "vpc_cidr": "10.70.0.0/16",
  "owner": "MahmoudHachem",
  "endpoint_cidrs": ["APPROVED_OPERATOR_OR_RUNNER_IPV4_CIDR"],
  "cluster_role_arn": "ACTUAL_APPROVED_CLUSTER_ROLE_ARN",
  "fargate_execution_role_arn": "ACTUAL_APPROVED_PATHLESS_FARGATE_EXECUTION_ROLE_ARN",
  "flow_log_role_arn": "ACTUAL_APPROVED_FLOW_LOG_ROLE_ARN",
  "operator_role_arn": "ACTUAL_APPROVED_OPERATOR_ROLE_ARN",
  "deployer_role_arn": "ACTUAL_APPROVED_DEV_APPLICATION_DEPLOY_ROLE_ARN",
  "prod_deployer_role_arn": "ACTUAL_APPROVED_PROD_APPLICATION_DEPLOY_ROLE_ARN",
  "kms_key_arn": "ACTUAL_APPROVED_SYMMETRIC_KEY_ARN",
  "kubernetes_version": "1.36",
  "addon_versions": {
    "coredns": "REVIEWED_COMPATIBLE_FARGATE_VERSION",
    "metrics-server": "REVIEWED_COMPATIBLE_FARGATE_VERSION"
  }
}
```

Exact pins are intentionally not guessed. Read them using approved temporary OIDC credentials: `aws eks describe-addon-versions --region us-east-2 --kubernetes-version 1.36 --addon-name coredns` and the same for metrics-server. Each selected version must list amd64, Fargate compute support and cluster compatibility. Run `aws eks describe-addon-configuration --region us-east-2 --addon-name NAME --addon-version EXACT_VERSION` to inspect its JSON schema. The workflow validates the checked-in addon-configuration.json against that exact schema before planning. Unsupported settings fail; they are not silently ignored. No node AMI/SSM release pin is needed.

CostCenter is optional: omit cost_center or use null until an actual approved value is assigned. Effective tag policy may require a real code before plan; no code is invented. Central tags and limitations are documented in TAGGING.md.

Before execution, bootstrap CAPACITY_REVIEW_JSON must contain the complete actual administrator-reviewed quota/utilization evidence from ADMIN-REQUEST.md, observed within 24 hours. It reserves 7.0 available vCPU for the prepared maximum/rollout envelope and confirms other infrastructure limits. This is human evidence, not an automated AWS quota measurement. Preflight reruns before apply.

5. After explicit live-plan authorization AND reviewed code merge, Settings -> Secrets and variables -> Actions -> Variables: set AWS_OPERATIONS_ENABLED=true. Actions -> Controlled Banking infrastructure -> Run workflow -> dev -> operation plan, approval blank. Personally approve bootstrap. The session checks identity, collisions, roles/trusts, service-linked roles, capacity evidence, add-on schema/version and existing bucket protections, then saves a native-locked creation-only plan. It cannot write bucket configuration or either Phase 2 state key.
6. Inspect plan.txt, plan-review.json, capacity-review.json, saved plan SHA256 and COSTS.md. The strict saved-plan audit requires exactly 46 managed entries (45 AWS plus a local prerequisite), all 33 supported explicit/effective tag maps, and the reviewed network/EKS/Fargate/access/encryption/log/ECR settings. Missing/additional resources, wrong settings or unknown effective tags fail. Expected types include new VPC/subnets/IGW/NAT/EIP/routes/S3 gateway endpoint/logs/flow log, two ECR repositories, EKS cluster, four Fargate profiles, two managed add-ons, explicit access entries/associations and the new cluster OIDC provider. Expect no EC2 workers, launch template, Pod Identity association, IAM role, bucket, database or ALB. The guard rejects updates/deletes/replacements to existing resources.
7. Only after owner approval of the ACTUAL resource plan and costs, dispatch operation apply with approval APPLY-REVIEWED-PHASE3-PLAN. Its plan job creates a fresh reviewed artifact and its apply job pauses at a second protected deployment. Review this same run's plan/hash before approving apply. The downloaded artifact's SHA256 and configuration must match; the exact binary plan is applied with Terraform state locking and stale-plan protection.
8. Verification reads ACTIVE cluster/profiles, zero managed node groups, pinned healthy CoreDNS/Metrics Server configuration, the actual cluster OIDC provider/audience/tags, explicit operator and namespace deployer access, encrypted retained logs and immutable ECR. A post-apply detailed-exitcode plan must be zero-change. Actual Kubernetes DNS/metrics and application/ALB traffic are verified during separately approved operator/application deployments; AWS profile ACTIVE alone does not prove application health.
9. Download banking-fargate-verified-interface (platform-outputs.json and controller-irsa-trust.json). Verify issuer/provider in EKS/IAM, then have the authorized administrator create/authorize the dedicated controller role using that complete trust and matching controller permissions. Chat 2 uses its actual ARN, service account, region and VPC outputs to install the controller with approved operator access.
10. Return AWS_OPERATIONS_ENABLED=false after any authorized operation, success or failure; leave BOOTSTRAP_STATE_READY=true. No PR validation or application release applies Terraform.

An incomplete apply or existing Banking name stops this first-creation workflow. Recovery needs a separately reviewed bounded update/recovery plan, preserving state. Do not reinitialize first-time state, overwrite state, force-unlock or remove safeguards to make recovery proceed.

## Network and compute tradeoffs

Two AZs each have public, private application and isolated database subnets. Fargate ENIs use only private application subnets and have no public IP. One NAT in AZ1 provides outbound AWS API/image access; S3/ECR layer downloads use the free S3 gateway endpoint restricted to GetObject on the documented regional ECR layer bucket. Future S3 use needs a reviewed additive policy; this endpoint does not grant IAM access. AZ2 cross-AZ NAT transfer and AZ1 outbound failure are explicit lab tradeoffs. No RDS is provisioned. Pods consume subnet IPs and Fargate quota; HPA scales Pods and bills additional capacity, without a node group.

The private EKS endpoint is enabled. Public HTTPS is restricted to approved IPv4 /24-or-narrower sources. GitHub-hosted runner addresses are dynamic; later Helm needs an approved network/operator path, not 0.0.0.0/0. No runner or VPN is deployed here.

EKS-managed cluster SG defaults attach to Fargate Pod ENIs, providing self-traffic for DNS, internal APIs and webhooks. Default broad outbound access and absence of Fargate NetworkPolicy enforcement are documented lab limitations, not production isolation. Equal CPU/memory requests and limits are required. Both subnets in one profile do not guarantee equal AZ placement; topologySpreadConstraints/affinity must not be used to promise availability.

No managed VPC CNI/kube-proxy/Pod Identity agent DaemonSets are installed. AWS provides Fargate host networking; CoreDNS is explicitly Fargate and Metrics Server uses the compatible community add-on on 10251. IRSA is used for controller AWS access. No EBS worker volume, AMI pin, SSH or IMDS access exists.

## Chat 2 handoff and later verification

See INTERFACE.md. Both workstreams are now integrated: PR #9 Fargate Helm/application workflows are in dev and approved PR #10 resolved the narrow release-path blocker. Final preparation adds ownership/environment/version metadata while preserving selectors, Services, image digests, port 8080 and safety gates.

An approved operator creates banking-dev and banking-prod, installs the namespace quotas/release RBAC, and installs controller CRDs/RBAC. App deployer scope cannot create namespaces or cluster-scoped resources. Later read-only verification includes `kubectl -n kube-system rollout status deployment/coredns`, Metrics Server rollout/APIService availability, `kubectl top pods -n banking-dev`, both API rollouts/health/payment checks and each Pod's CapacityProvisioned annotation. ALB IP target health and controller IRSA are verified only after separate authorized deployments. Do not use eksctl commands that create roles behind the scenes.

## Cleanup safety

No destroy workflow is provided. See CLEANUP.md. EKS deletion protection requires a separately approved platform-only update before destruction; the initial creation-only workflow cannot do that update. Owner must approve a separate platform-only destroy plan. Remove approved ingress first while controller IRSA still works, verify ALB/target groups/ENIs are cleaned, then remove workloads/profiles/add-ons/cluster/NAT/EIP/VPC and the Banking cluster OIDC provider. Fargate profiles are immutable; deleting one interrupts matching Pods. OIDC deletion needs separately approved IAM permission because the creation session does not grant it. ECR force_delete=false protects tagged releases; archive/delete only authorized images. Preserve the S3 bucket, both Phase 2 state paths, Retail resources, GitHub provider and administrator-owned roles/key. Retain encrypted logs/key as required; key deletion is a separate review.

## Approved shared-cluster demonstration update

PR #15 is integrated at d101fb7. The current reviewed target is one banking-dev
control plane and two application profiles/namespaces (banking-dev and banking-prod),
with distinct release identity groups and operator-installed namespace RBAC/quotas.
Apply both helm/banking/namespaces manifests and iam/phase3/deployer-verification-rbac.yaml
only after approved EKS creation. No application identity may install these controls.
The exact current platform inventory is 46 managed entries, 33 taggable.
See SHARED-CLUSTER.md and ADMIN-REQUEST.md for current architecture/access limits.
