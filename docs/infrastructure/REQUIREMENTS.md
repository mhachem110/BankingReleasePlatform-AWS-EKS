# Assignment coverage after Phase 3 preparation

The official Week 4 CI/CD Engineering assignment remains the deliverable source; these are implementation statuses, not completion claims for later phases.

| Requirement | Status / next evidence |
| --- | --- |
| Account/Payment application, Docker, local communication/tests | Phase 1 complete |
| OIDC, secure remote state, lifecycle, native locking | Phase 2 complete; COMPLETION.md has actual run evidence |
| Two-AZ VPC/public/private/isolated networking, ECR, EKS Fargate profiles | Phase 3 code prepared; administrator prerequisites/live plan/deployment pending |
| Kubernetes services, Helm, probes, limits, replicas/HPA, Ingress | PR #9 Fargate Helm/chart/runbooks merged; controller/application live deployment pending authorization |
| PR build/tests/static checks, Trivy, Terraform Checkov, Helm | Merged .NET/Docker/Trivy/Helm and Terraform/Checkov CI passes; live publication/deployment scans pending execution |
| OIDC SHA/digest image publication, approvals, smoke/rollback, separate infra workflow | Controlled infra and application publication/digest-promotion workflows merged; protected live execution pending |
| RDS/Aurora and migration of sample persistence | Mandatory Phase 6; isolated subnet outputs reserved, not omitted |
| SQS/EventBridge concrete asynchronous use case | Mandatory assignment coverage planned Phase 6 payment-completed event; not yet implemented |
| Secrets Manager/KMS, least privilege, Kubernetes RBAC | KMS key prerequisites/explicit EKS access prepared; secrets/workload IAM/full RBAC evidence Phase 6 |
| CloudWatch logs/alarms, Prometheus/Grafana or suitable equivalent | Encrypted flow/control logs prepared; application dashboards/alerts pending Phase 6 |
| Requests/errors/latency/CPU/memory, scaling/health evidence | Metrics-server/HPA prepared; collection/dashboard/test evidence pending Phase 6 |
| CloudTrail/security-service findings, retention/lifecycle | Existing account services must be inspected and administrator scope approved in Phase 6; no shared service changes now |
| At least three measured cost optimizations | Modeled choices in COSTS.md; actual baseline/before-after evidence required Phase 6 |
| Migration waves and controlled failure/recovery | Runbooks and actual Detection → Investigation → Recovery → Validation required final phases |
| Architecture/code/workflows/scans/dashboards/cost report/cleanup | Source organized; live final evidence and rehearsed cleanup pending |
| Fifteen-minute presentation | Final: 2 min business, 4 min apps, 3 min CI/CD, 3 min security/incident, 2 min costs/migration, 1 min lessons |

No production-readiness, availability, security-findings or live-deployment success is claimed by offline validation.

## Fargate redesign and remaining evidence

Fargate is the user-approved compute alternative; no managed node group is required. No DaemonSets, Pod Identity agent or VPC CNI policy enforcement are claimed. Metrics Server supports HPA/current utilization; historical monitoring, app metrics, Fargate logging, relational persistence and asynchronous events remain mandatory later-phase work. IRSA controller trust depends on the actual cluster issuer and administrator approval. Code preparation and mock plans do not fulfill live EKS/application acceptance criteria.

PR #10 resolved the narrow owner-authored application release-path blocker; PR #9 and PR #11 are merged. Infrastructure/IAM/governance ownership and all deployment approval gates remain. See INTERFACE.md and [the current reconciliation](RECONCILIATION.md).
