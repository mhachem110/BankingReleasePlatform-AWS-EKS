# Week 4 assignment requirements and acceptance

The attached Week 4 CI/CD Engineering assignment is the source of acceptance criteria. This page consolidates the assignment mapping and later acceptance matrix. A passing offline test, Terraform mock, source review or historical run proves only its own scope; it does not prove a live deployment or production readiness.

| Area | Required final evidence |
| --- | --- |
| Application and containers | Account and Payment APIs, deterministic tests, Docker builds, internal service communication, health/readiness behavior and safe synthetic data boundaries. |
| CI/CD and promotion | PR validation, .NET/build/test, Helm and IaC checks, Checkov/Trivy security gates, immutable ECR digest provenance, protected dev release, same-digest promotion and namespace-specific approval. |
| AWS foundation | OIDC short-lived credentials, protected Terraform backend and locking, tagged two-AZ VPC, EKS Fargate profiles, ECR, CoreDNS, metrics, access entries and both isolated namespaces. |
| Data and events | Private encrypted PostgreSQL, TLS, approved Secrets Manager delivery, forward-only migrations, payment replay protection, transactional outbox, SQS retry/visibility behavior, receipt and DLQ evidence. |
| Security and governance | Least privilege, OIDC subject restrictions, workload identity separation, namespace RBAC, secret protection, dependency/container/IaC scanning and documented critical/high finding ownership/remediation. Assess CloudTrail, GuardDuty, Inspector and Security Hub only within approved account scope and cost. |
| Observability and availability | CloudWatch logs and metrics, application and Kubernetes health, request/error/latency/resource dashboards, actionable owned alerts, bounded timeouts, readiness behavior, scaling/replacement and evidence of the chosen availability tradeoffs. |
| Recovery | Controlled failed release, investigation, Helm rollback to a verified healthy image pair, database-safe recovery, SQS/DLQ handling, before/after health and a timed recovery record. |
| Cost and migration | Review EKS/Fargate, NAT/IP, RDS/snapshots, ECR, transfer, logs/metrics and runner costs. Show a baseline and at least three evidence-supported optimizations; document migration waves, validation, rollback and residual risks. |
| Presentation | A 15-minute evidence-led walkthrough: 2 min business/architecture, 4 min app/EKS, 3 min CI/CD, 3 min security/recovery, 2 min migration/cost, 1 min risks/next steps. |

## Completion evidence

For each live claim, record UTC time, AWS account and Region, reviewed source commit, GitHub run/approval, Terraform state and output, immutable image digests, namespace, health/metrics/log evidence and cost source. Keep failed or blocked checks visible. A plan is not an apply; an apply is not workload health; a dashboard configuration is not delivered alert evidence. See [historical checkpoint links](PROJECT-HISTORY.md) and update them only from actual runs.

The shared Fargate design has explicit limitations: a single NAT/data-AZ choice trades availability for training cost, and Fargate does not provide DaemonSets, node-based agents, topology-spread guarantees or AWS VPC CNI NetworkPolicy enforcement. Demonstrate those limits accurately and do not claim unverified HA or security findings.
