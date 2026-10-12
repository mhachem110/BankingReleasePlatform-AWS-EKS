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

## Final preparation duration, scaling and variable-usage model

Run `python scripts/infra/cost-exposure.py`; optionally add `--usage-json` pointing
to a local JSON of actual approved traffic/storage/request assumptions. No AWS
calls, credits/free tiers or invented usage are included. The underlying configuration
and Ohio Fargate rates are unchanged; this is a source model, not a live plan/bill.

| Scenario | Hourly | 8h | 24h | 40h | 730h/month |
| --- | ---: | ---: | ---: | ---: | ---: |
| initial system | $0.1884 | $1.51 | $4.52 | $7.54 | $137.53 |
| four apis | $0.2467 | $1.97 | $5.92 | $9.87 | $180.06 |
| four apis and controller | $0.2713 | $2.17 | $6.51 | $10.85 | $198.08 |
| hpa max | $0.3296 | $2.64 | $7.91 | $13.18 | $240.61 |
| hpa max all rollouts | $0.3958 | $3.17 | $9.50 | $15.83 | $288.90 |

Baseline excludes variable charges. HPA max means four replicas per API (currently
disabled). All-rollouts peak models two API surges plus one per CoreDNS/Metrics/
controller deployment: 18 Pods/4.5 vCPU. It is a capacity/cost envelope, not a
request to deploy them or a promise that autoscaling is enabled.

The optional usage model shows explicit planning unit assumptions: NAT data $0.045/GB;
standard logs ingestion $0.50/GB and archived storage $0.03/GB-month; ECR $0.10/GB-month;
S3 Standard $0.023/GB-month, PUT $0.005/1000 and GET $0.0004/1000; symmetric KMS
requests $0.03/10000. Actual log class/tiers/Region/operations must be rechecked in
the live cost review, with recorded usage quantities. For example, 10GB NAT,
2GB log ingestion, 1GB-month log storage, 2GB-month ECR, 0.1GB-month S3,
1000 PUT/5000 GET and 10000 symmetric KMS requests add about $1.72, before transfer.
That is an example ONLY, not measured Banking usage. Inspector enhanced ECR scanning
is not enabled; basic scan and CI Trivy are the prepared path.

Sources: [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/),
[ECR](https://aws.amazon.com/ecr/pricing/), [S3](https://aws.amazon.com/s3/pricing/),
[KMS](https://aws.amazon.com/kms/pricing/). Cross-AZ NAT traffic and Internet egress
are additional, direction/volume dependent; a zero-volume baseline is not a cap.

Phase 4 ALB estimate: $0.0225/ALB-hour + $0.008/LCU-hour;
internet-facing two-AZ ALB starts with at least two public addresses at $0.005/IP-hour.
An assumed constant one LCU plus two addresses adds $0.0405/hour ($29.57/month)
to the controller-inclusive scenario. Internal ALB has no public IPv4 assumption;
capacity scaling can add addresses/LCUs. No ALB is created by initial Terraform.
[ELB pricing](https://aws.amazon.com/elasticloadbalancing/pricing/)

KMS key/storage retained after a short run continue charging; the proportional
key assumption in this table does not promise a $1 key disappears on teardown.
Starting/stopping app Pods does not stop the EKS control plane or NAT Gateway.

## Proposed reporting and alert setup — approval needed

Billing administrator: activate approved cost allocation tags as TAGGING.md explains,
review Cost Explorer daily by Project/Environment/Service and reconcile unallocated
Fargate charges. Propose one monthly project budget (e.g. $250, owner must approve
the actual amount and recipient) with actual alerts at 50/80/100% and forecast at
100%; review shared-account coverage and ALB/usage allowance first. AWS Budgets,
notifications, billing settings and extra paid dashboards are NOT created here.
Use a scheduled manual end-of-lab inventory review before adopting automation.
