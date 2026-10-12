# Week 4 acceptance matrix

As of 12 October 2026. PASS means evidence exists for the stated scope only.
Live rows remain BLOCKED pending AWS verification, reviewed plans/costs and approvals.
Official source: Week4_Project_1_CI-CD_Engineering_Mahmoud_Hachem 1.docx,
summarized in docs/assignment-requirements.md. See the source-linked run evidence
in docs/infrastructure/SHARED-CLUSTER.md and the current PR description.

| Official requirement / project acceptance | Status | Evidence and next required proof |
| --- | --- | --- |
| Existing repository, backend/OIDC foundation | PASS (recorded baseline) | Merged bootstrap history and backend-checkpoint records; preserve mhachem-banking-tfstate-866934333672. Reverify live identity/state before operations. |
| GitHub environments and OIDC configuration | PASS (GitHub settings) | Actual API audit: five environments; dev/main-only app branches, reviewer, no bypass, immutable repository subject. Both AWS role trusts/real OIDC sessions still BLOCKED. |
| .NET APIs and container packaging | PASS (offline) | 70 API tests, Docker/DNS/recovery checks and Trivy reports; actual ECR/EKS execution BLOCKED. |
| Terraform infrastructure and security validation | PASS (offline) | Backend-disabled validation, mocked tests, guards and Checkov. Actual saved live plan/apply/state/clean re-plan BLOCKED. |
| One healthy EKS Fargate cluster, two namespaces | BLOCKED | Four profiles and separate release groups prepared; actual ACTIVE status, Fargate placement and admission/access denial evidence missing. |
| Working service discovery, probes and API requests in both environments | BLOCKED | Local container communication and Helm/schema tests pass; actual cluster requests/DNS pending. |
| Dev ECR publication and immutable prod promotion | BLOCKED | Bound dev receipt/provenance tests and prod no-publish STS cap; real publication/deploy/prod approval links and same digest pair pending. |
| Namespace-scoped dev/prod deployment identities | BLOCKED | Custom least-privilege Banking RBAC prepared; full retained CloudOps IAM policy audit and actual cross-namespace denials pending. |
| Private PostgreSQL persistence and forward migration | BLOCKED | Local persistence, replay/concurrency, migration/TLS guards pass. Separate live resource plans, TLS/Secrets Manager, Pod-replacement durability pending. |
| Transactional outbox, SQS retries and DLQ | BLOCKED | Local integration/recovery checks pass. Actual per-environment SQS dispatch, poison redrive and durable receipt evidence pending. |
| Monitoring, alerts and CPU/memory visibility | BLOCKED | Structured logs/metrics, Prometheus rules and offline alert evaluation pass; live collection/dashboard, Metrics Server and delivered alert pending. |
| Controlled failed release, rollback and scaling | BLOCKED | Rollback safety unit/container checks pass; real pipeline failure, logs/events, prior Helm revision and healthy API restoration pending. |
| Security and governance controls | PASS (offline/GitHub scope) | CODEOWNERS/routes/protections preserved, scans and denied-operation guard tests. Actual AWS trust/permissions/IRSA/KMS/HTTPS controls pending. |
| Three defensible cost optimizations | PASS (design calculations) | Shared EKS, single NAT tradeoff and untagged ECR retention modeled from public prices; actual usage/savings evidence BLOCKED. |
| Cloud migration/recovery implementation | BLOCKED | Forward-only migration and incident runbooks prepared/tested offline; approved live waves and recovery timings pending. |
| Fifteen-minute trainer demonstration | BLOCKED | Updated draft, editable architecture and timed runbook prepared; mandatory live evidence has not been recorded. |
| Final complete project | BLOCKED | EKS/application/data/messaging/monitoring/promotion/rollback live acceptance is mandatory. No 100% completion claim. |

No live FAIL is asserted for a test that has never run. An authorization or access
block is not a passing test. Replace statuses only with timestamped account/Region,
exact commits/image digests/workflow links and actual command/log/metric evidence.
