# Proposed Ohio lab costs — 11 October 2026

These are planning estimates, not an actual bill or a deployment authorization. No paid Phase 3 resources were created. Recheck the Ohio AWS Pricing Calculator and the real Terraform plan before approval. Shared-account charges from existing projects are outside this estimate; filter future cost evidence using Project=BankingReleasePlatform and Environment=dev.

## Initial platform baseline

Assume 730 running hours/month, two Linux On-Demand t3.medium nodes, one zonal NAT Gateway, one NAT public IPv4, 40 GiB total gp3 and one dedicated administrator-managed KMS key:

| Component | Assumed unit price | Monthly estimate |
| --- | --- | ---: |
| EKS standard-support control plane | $0.10/hour | $73.00 |
| Two t3.medium workers | 2 × $0.0416/hour | $60.74 |
| One NAT Gateway | $0.045/hour | $32.85 |
| NAT public IPv4 | $0.005/address-hour | $3.65 |
| Two encrypted 20 GiB gp3 disks | 40 × $0.08/GiB-month | $3.20 |
| Dedicated symmetric KMS key, if needed | $1/key-month before rotation storage increments | $1.00 |
| **Subtotal before usage and telemetry** | | **$174.44/month** |

Budget approximately **$180–195/month for a small continuously running lab**, with logs/metrics and light traffic. This is not a hard cap. EC2 detailed monitoring is enabled; allow approximately $4.20/month for fourteen custom-priced detailed metrics at $0.30/metric-month, then remeasure actual emitted metric count/free-tier eligibility. Add NAT processing ($0.045/GB), cross-AZ transfer, Internet egress, CloudWatch control-plane/vended flow log ingestion and storage, ECR image storage/scanning, S3 state versions/requests and KMS requests. T3 Unlimited CPU credit surcharges can apply under sustained CPU load. No free tier, training credits, discounts or tax reduction are assumed.

**Source precision:** AWS's [Ohio NAT example and public IPv4 pricing](https://aws.amazon.com/vpc/pricing/) verify the NAT/IPv4 rates. [EKS pricing](https://aws.amazon.com/eks/pricing/) gives standard $0.10 and extended $0.60 per cluster-hour. [AWS gp3 volume information](https://aws.amazon.com/ebs/volume-types/) lists $0.08/GiB-month. The EC2 $0.0416/hour is an **estimate using AWS's published t3.medium reference rate in us-east-1**, not a claim that Ohio's current SKU price was retrieved; confirm Linux/Shared tenancy/us-east-2 in the [EC2 pricing calculator](https://calculator.aws/) before authorizing costs. [KMS](https://aws.amazon.com/kms/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/) and [ECR](https://aws.amazon.com/ecr/pricing/) usage charges must be added for the final selected options.

An approximately 40-hour temporary lab followed by approved teardown would cost roughly **$11 plus usage**, under the same compute rates with prorated storage/metrics and one retained monthly KMS key. Leaving EKS/NAT/EIP running while scaling workers down still incurs their hourly charges. EKS does not have a stop button. This estimate assumes approved teardown, not a scheduling mechanism that exists today.

## Choices and evidence plan

1. **One NAT instead of two:** avoids a second $32.85/month NAT and $3.65 IPv4 address, about $36.50/month before data transfer. Tradeoff: outbound Internet availability depends on one AZ; the second AZ may incur cross-AZ charges. This is a development lab tradeoff, not a production HA claim.
2. **Free S3 Gateway Endpoint:** routes S3 and ECR layer downloads around NAT. Measure bytes from flow logs and NAT metrics; 10 GiB avoided saves about $0.45 processing before cross-AZ costs. Private ECR API/auth HTTPS still uses NAT because interface endpoints are not included.
3. **gp3 instead of gp2:** at illustrative $0.08 versus $0.10/GiB-month, 40 GiB saves about $0.80/month while retaining baseline gp3 performance. Verify the actual selected regional rates and disk metrics.
4. **Standard-support EKS 1.36:** avoids the $0.50/hour extended-support increment, approximately $365/month. AWS currently lists 1.36 in standard support through 2 August 2027. Revisit before that date; upgrade_policy STANDARD avoids opting into extended support. Checkov 3.3.17 and current 3.3.27 still enumerate only through 1.35, so this exact version check has a documented scoped exception backed by [AWS's current version table](https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html), while Terraform restricts the baseline to 1.36.
5. **Bounded logs and untagged images:** 30-day log retention and seven-day untagged ECR cleanup reduce unused storage; tagged images remain for rollback. Capture inventory/byte counts and before/after billing in Phase 6 instead of claiming measured savings now.

These are modeled savings. The final assignment requires at least three evidence-supported optimizations; collect actual cost/usage measurements in Phase 6. Do not represent this table as achieved cost reductions.

## Later phases excluded

No ALB, RDS/Aurora, SQS/EventBridge, Secrets Manager, managed Prometheus/Grafana, Inspector/GuardDuty/Security Hub expansion or paid CI runner is deployed here. An internet-facing ALB later adds hourly/LCU charges and at least two charged public IPv4 addresses; estimate those separately after the approved HTTPS design. RDS and managed observability can materially increase the bill and need their own reviewed plans. Nothing here deploys separate stage/uat/prod clusters.
