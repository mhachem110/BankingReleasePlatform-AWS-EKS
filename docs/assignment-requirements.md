# Assignment requirements and phase mapping

The entire attached assignment was read before implementation: `Week4_Project_1_CI-CD_Engineering_Mahmoud_Hachem 1.docx`, including its mandatory coverage table, all twelve sections, presentation timing and footer. It is the requirements source. The user's master instructions authorize only Phase 1 now and govern approvals. This document records future requirements without implementing them.

The assignment describes an enterprise CI/CD platform. Our learning baseline starts with fictional services and grows into the required demonstration; Phase 1 alone does not meet final acceptance and carries no production-readiness claim.

| Assignment requirement | Phase(s) | Current disposition / required evidence |
| --- | --- | --- |
| Safe, repeatable account/payment releases; deeper CI/CD specialty | 1, 5, 7 | Local services now; final PR-to-release, gates and rollback demonstration later |
| Docker and working container implementation | 1 | Separate Dockerfiles, Compose and live smoke checks |
| ECR, EKS and operational evidence | 3–5, 7 | Pending approved infrastructure and running workload evidence |
| Helm, workloads, probes, resource controls and scaling | 4, 6 | Deployments/Services, readiness/liveness, replica scaling and autoscaling evidence |
| GitHub Actions PR test, lint/build, scan, IaC and Helm validation | 5 | Pending; a failing required check must block release |
| Immutable SHA/version container images and ECR publishing | 5 | Pending; local tags are only for Phase 1 |
| GitHub OIDC and short-lived AWS credentials | 2, 5 | Pending inspection of actual existing role and OIDC subject configuration |
| Helm deploy to EKS with protected environment approval | 4, 5 | Pending GitHub capability/protection check and authorized deployment |
| Staged promotion | 5–7 | Development first; stage/production promotion must be implemented or an explicit assignment exception obtained before final acceptance |
| Smoke/health tests and documented rollback | 1, 5, 7 | Local health/smoke checks now; EKS rollout and rollback evidence later |
| Terraform/IaC and repeatable infrastructure deployment | 2, 3, 7 | Pending; no infrastructure code or AWS application in Phase 1 |
| ALB | 4 | Pending controller IAM roles and externally routed traffic |
| RDS or Aurora | 6 | Required stack entry; add durable sample data through repository abstraction |
| SQS or EventBridge | 6 | Required stack entry; plan a concrete simulated payment-completed event and demonstrate delivery |
| Least-privilege IAM and Kubernetes RBAC | 2–6 | Pending additive scoped policies and RBAC evidence |
| No hardcoded credentials or long-lived CI AWS keys | All | No application secrets or AWS credentials added in Phase 1 |
| Secrets Manager and KMS | 6 | Pending sensitive configuration and encryption evidence |
| Trivy container/dependency and Checkov/IaC scanning | 5, 6 | Pending integrated scans and gate evidence |
| CloudTrail and CloudWatch logging | 6 | Pending approved setup and audit/application log evidence |
| GuardDuty, Inspector and Security Hub where applicable | 6 | Assess availability/permissions/cost; evidence findings or document justified applicability limitations |
| Critical/high finding ownership and remediation | 6, 7 | Required security report with finding, owner, remediation, status and validation |
| CloudWatch logs and AWS metrics | 6 | Pending operational evidence |
| Prometheus/Grafana or appropriate managed equivalent | 6 | Pending dashboards and collector evidence |
| Application and Kubernetes health checks | 1, 4, 6 | Local process health now; cluster probes/health evidence later |
| Latency, errors, throughput and resource utilization dashboards | 6 | Pending request/error/latency/CPU/memory evidence |
| Actionable alerts with severity and ownership | 6 | Pending alert thresholds, owner, severity and delivery evidence |
| Incident detection, investigation and recovery | 7 | Controlled failed release, investigation, rollback and verification |
| Before/after baseline and unused/oversized resource review | 6 | Pending observed usage and dated cost/size comparison |
| Autoscaling where appropriate | 4, 6 | Pending justification and scaling evidence |
| Review EKS/EC2, RDS, ECR, data transfer, logging and telemetry costs | 3, 6 | Pending estimates plus actual billed/usage evidence |
| Retention/lifecycle controls | 2, 6 | State version retention plan, image/log/telemetry retention evidence |
| At least three practical evidence-supported optimizations | 6, 7 | Pending each action's baseline, change/recommendation and measured or calculated benefit |
| Migration project current state, target, waves, validation and rollback | 6, 7 | Local-to-EKS transition plan; no legacy production migration claimed. Confirm applicability when writing final analysis |
| Architecture, working deployment, IaC, workflows, Helm artifacts | 1–5, 7 | Current local diagram/application; all cloud deliverables pending |
| Security report, dashboards, cost analysis and failure/recovery runbook | 6, 7 | Pending implementation and operational evidence |
| README and final presentation | 1, 7 | Phase 1 README now; final delivery later |
| All four topics in one solution, security integrated, actionable telemetry and reproducible recovery | 7 | Final acceptance audit required; not satisfied by Phase 1 |

## Differences and decisions

1. The assignment's five-day plan is a schedule, while the approved seven phases are implementation checkpoints. Preserve every requirement while using the user's phase and approval boundaries.
2. The assignment lists RDS/Aurora and SQS/EventBridge in its stack. Treat each slash pair as at least one required technology. SQS/EventBridge is not silently optional: its concrete event use case belongs in Phase 6.
3. Staged promotion cannot be indefinitely deferred past final delivery. One actual development environment is the first baseline. Protected stage/production promotion, GitHub plan restrictions and additional cloud cost approvals must be resolved later.
4. Security operations needs named finding ownership/remediation and alerts need severity/ownership. Dashboard screenshots and scan output alone are insufficient.
5. Cost work requires a before/after baseline and coverage of all named cost areas. Three unsupported suggestions do not satisfy acceptance.
6. The reference bootstrap creates IAM roles and broadly permits several services. The user cannot create IAM roles. Reuse an inspected authorized role; request distinct EKS/controller roles from an administrator as necessary. Never assume historical trust/policies represent current AWS state.
7. The user prefers .NET 8 or another supported LTS. .NET 10 LTS is installed and provides a longer remaining support period; it is selected for this baseline. ([Microsoft support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core))

## Required final presentation timing

| Time | Assignment segment |
| --- | --- |
| 2 minutes | Business problem and architecture |
| 4 minutes | Live application, container and EKS demonstration |
| 3 minutes | CI/CD specialty demonstration |
| 3 minutes | Security, observability and failure scenario |
| 2 minutes | Migration, cost and optimization results |
| 1 minute | Risks, lessons learned and next steps |

The assignment definition of done is deployment from code, security, observability, intentional failure testing, optimization and engineering/business explanation. Final verification remains Phase 7 work.
