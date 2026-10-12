# Ohio shared-cluster demonstration cost review

12 October 2026. One EKS Fargate cluster, two application namespaces. Source models
are not an actual plan, approved spend limit or measured bill. No new AWS resources
have been provisioned by this workstream. Preserve existing state/shared IAM resources.

Run python scripts/infra/cost-exposure.py and scripts/infra/shared-demo-cost.py.
cost-model.json and shared-demo-prices.json record assumptions, SKU/publication/
retrieval dates and public Ohio catalog sources. CPU $0.04048/vCPU-hour and memory
$0.004445/GB-hour use Linux/x86 Fargate. No Spot/ARM/free-tier/credits are assumed.

| Platform scenario | Monthly at 730h, USD | Scope |
| --- | ---: | --- |
| Initial system | 137.53 | One EKS, NAT/public IPv4, key, CoreDNS/Metrics |
| Dev APIs, without controller | 180.06 | Four API Pods plus system |
| Both namespaces, without controller | 222.59 | Eight API Pods plus system |
| Both namespaces plus two controller Pods | 240.61 | Thirteen Pods before variable usage/ALB/data |
| Four replicas/API plus controller | 325.67 | HPA disabled; sensitivity only |
| All rollout surges at maximum | 395.23 | Twenty-eight Pods / 7.0 vCPU capacity envelope |

Each 250m/512Mi API Pod bills 0.25 vCPU/1GB after Fargate overhead/rounding.
Each 250m/256Mi system/controller Pod bills 0.25 vCPU/0.5GB. Verify actual
CapacityProvisioned and task-hours. EKS standard support is $0.10/hour;
extended support is $0.60/hour and requires a separate cost/upgrade decision.
The one NAT/$0.045-hour and IPv4/$0.005-hour assumptions must be reviewed against
the actual plan and current [VPC prices](https://aws.amazon.com/vpc/pricing/).
See [Fargate sizing](https://docs.aws.amazon.com/eks/latest/userguide/fargate-pod-configuration.html)
and [EKS pricing](https://aws.amazon.com/eks/pricing/).

## Separately approved data and variable costs

Two isolated Single-AZ PostgreSQL databases are the prepared dev/prod design.
At 40GiB GP3 each, six Secrets Manager secrets (two managed master plus four
runtime design), two additional data CMKs, ten standard alarms and two HTTP
error metrics, modeled fixed/compute subtotals including the platform above are:

| Database class, two instances | Monthly subtotal, USD |
| --- | ---: |
| db.t4g.micro | 279.17 |
| db.t4g.small | 302.53 |
| db.t4g.medium | 350.71 |

These are sensitivity calculations, not a database recommendation or upper bound.
Storage/instance sizing, PostgreSQL engine version, backup retention and availability
need actual approved inputs/plans. RDS CPU credit charges, snapshots/backups,
SQS send/receive/delete/empty polls and KMS/API calls, CloudWatch ingestion/storage/
dashboards, ECR/S3 storage/requests, NAT/Internet/cross-AZ transfer, collector Pods,
ALB/LCU/public-address charges and taxes remain excluded until quantities are approved.

Representative current catalog rates: RDS t4g.micro $0.016/hour, GP3 $0.115/GB-month,
SQS standard $0.40/million requests, log ingestion $0.50/GB and storage $0.03/GB-month,
Secrets Manager $0.40/secret-month, KMS $1/key-month before requests/rotation,
ECR $0.10/GB-month, S3 standard $0.023/GB-month, ALB $0.0225/hour plus $0.008/LCU-hour.
See each exact official public source/SKU in shared-demo-prices.json. Account-specific
discounts and free-tier eligibility are not assumed. Additional keys/services/ALBs
still need specific administrator/resource and cost authorization.

## Three defensible optimization decisions

1. One cluster for two namespaces avoids a second standard-support EKS control plane:
   $73/month modeled. Tradeoff: shared cluster/network and no hard tenant isolation.
2. One NAT and public IPv4 avoids a second fixed gateway/address cost: $36.50/month
   before cross-AZ traffic offsets. Tradeoff: single outbound availability dependency.
3. Seven-day untagged ECR cleanup saves $0.10 per removed GB-month. Preserve tagged
   immutable releases required for rollback; measure removed bytes before claiming savings.

For the trainer, record dated task-hours, CapacityProvisioned, retained image/log
bytes and actual regional cost/usage data. Design savings are not achieved savings.
Use the S3 gateway endpoint to avoid NAT processing for layers/state and review
right-sizing from measured latency/error/CPU/memory. Do not enable HPA or destroy
the environment automatically. Forty platform hours with both namespaces/controller
are $13.18 before usage/data/retained resources; EKS cannot be stopped. Scaling APIs
down leaves EKS/NAT/system/storage charges. Cleanup needs explicit approval.
