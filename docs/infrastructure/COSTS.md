# Ohio Fargate planning costs — 11 October 2026

No paid resources were created. These estimates are not a bill, cap or deployment authorization. Recheck the actual plan, resource requests, regional calculator and quota before approval. Costs from other projects are excluded.

## Reproducible baseline

Run `python scripts/infra/cost-estimate.py`. cost-model.json records rates, assumptions, source publication date and SKUs. The public [Ohio AWS price catalog](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/us-east-2/index.json), retrieved 11 October 2026 (publication 11 September), lists Linux/x86 Fargate CPU at $0.04048/vCPU-hour (UGSJ89BUWB7SMJ6A) and memory at $0.004445/GB-hour (HH5EE3ZFWSFKGKWM). EKS uses Fargate pricing; ARM/Windows/Spot rates are not used. [Fargate pricing](https://aws.amazon.com/fargate/pricing/)

Assume 730 hours, two replicas of each API at equal 250m/512Mi requests/limits, two CoreDNS Pods and one Metrics Server at equal 250m/256Mi, and two controller Pods at equal 250m/256Mi (controller sizing is a handoff assumption, not a deployed setting).

| Component | Billed capacity / assumption | Monthly USD |
| --- | --- | ---: |
| Four API Pods | Each 0.25 vCPU / 1GB | 42.53 |
| Two CoreDNS Pods | Each 0.25 vCPU / 0.5GB | 18.02 |
| One Metrics Server Pod | 0.25 vCPU / 0.5GB | 9.01 |
| Two controller Pods (later operator deployment) | Each 0.25 vCPU / 0.5GB | 18.02 |
| EKS standard support | $0.10/cluster-hour | 73.00 |
| One NAT Gateway | $0.045/hour | 32.85 |
| One NAT public IPv4 | $0.005/address-hour | 3.65 |
| One dedicated KMS key, if needed | Before requests/rotation increases | 1.00 |
| **Full release planning subtotal** | Before usage, ALB and telemetry | **198.08** |

**Infrastructure alone**, with CoreDNS and Metrics Server but no APIs/controller, is approximately **$137.53/month before usage**. Nine-Pod full release reserves 2.25 Fargate vCPU and 6.5GB. Initial three system Pods need 0.75 vCPU. Budget additional capacity for rollout surge and HPA, and allow approximately $205–225/month for light telemetry/traffic **excluding the later ALB**; this is an allowance, not a measured cost or upper bound.

Fargate adds 256MB per Pod for host components and rounds to a supported size. A 512Mi app request therefore bills 1GB, not 0.5GB. Pod CapacityProvisioned, rather than the apparent virtual node size, identifies billed capacity. [AWS sizing rules](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html) Each further 0.25vCPU/1GB app replica adds about $10.63/month. Default ephemeral storage is encrypted; there are no EC2 node disks or detailed EC2 metrics in this model. Extra ephemeral storage incurs usage charges.

[EKS pricing](https://aws.amazon.com/eks/pricing/) supplies the standard/extended-support rates. [VPC pricing](https://aws.amazon.com/vpc/pricing/) documents the Ohio $0.045 NAT example and $0.005 public IPv4 rate. [KMS pricing](https://aws.amazon.com/kms/pricing/) covers key and request/rotation costs. AWS catalog date is not a guarantee that a future deployment's rates remain the same.

Add NAT processing, cross-AZ transfer, CloudWatch flow/control log ingestion/storage, ECR image storage/scanning, S3 state versions/requests, KMS usage and Internet egress. App logging is a later Fargate log-router/observability configuration; these log resources do not prove app logs are collected. Controller installation alone does not create ALB, but approved ingress later adds ALB hours/LCUs and public addresses. RDS, messaging, managed observability/security services and paid runners remain excluded.

## Cost choices and evidence still needed

1. One NAT rather than two saves approximately $36.50/month in gateway/IP fixed cost, trading away independent-AZ outbound availability and potentially adding cross-AZ transfer.
2. The free S3 gateway endpoint avoids NAT processing for S3/ECR layers. Capture actual avoided bytes and NAT metrics; do not claim savings solely because the endpoint exists.
3. Fargate removes EC2 idle capacity and node management, but small always-on system Pods still have a minimum charge per Pod. Do not claim Fargate is automatically cheaper than EC2. Measure app utilization and CapacityProvisioned before tuning equal requests/limits.
4. Standard-support EKS and reviewed version upgrades avoid the $0.50/hour extended-support increment (~$365/month). Terraform requests STANDARD; verify current 1.36 support and future upgrade dates with the [AWS version table](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html).
5. Thirty-day logs and seven-day untagged ECR cleanup bound storage, preserving tagged releases for rollback. Measure actual bytes/billing.
6. Approved teardown after a short lab avoids ongoing EKS/NAT costs. EKS cannot be stopped; scaling apps down still leaves cluster/NAT and system Pod charges. A 40-hour full baseline is roughly $10.85 plus usage and retained-key/storage charges, assuming separately approved teardown.

These are modeled decisions. The assignment's three evidence-supported cost optimizations still require actual Phase 6 cost/usage measurements. No discounts, credits, free-tier eligibility or taxes are assumed.
