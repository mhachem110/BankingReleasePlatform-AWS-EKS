# Fifteen-minute project demonstration

Use actual workflow and AWS evidence only after it has been collected. Clearly label simulations, Terraform mocks and local fixtures; none is live deployment proof.

| Time | Segment | Evidence to show |
| --- | --- | --- |
| 0–2 min | Business problem and architecture | Synthetic API boundary, Fargate/VPC diagram, isolated namespaces and approvals. |
| 2–6 min | Application and EKS | Healthy Account/Payment services, service discovery, Fargate placement, durable payment after replacement and verified SQS receipt. |
| 6–9 min | CI/CD | Exact-commit CI, security scans, immutable image digests, protected deployment and same-digest promotion; demonstrate a failed rollout and recovery. |
| 9–12 min | Security and operations | OIDC, saved-plan review, dev/prod identities, TLS, logs, dashboards, delivered alert and incident timeline. |
| 12–14 min | Migration and cost | Approved migration waves, dated baseline and three measured or calculated optimization results with tradeoffs. |
| 14–15 min | Risks and next steps | Single-NAT/data-AZ tradeoff, unresolved risks, retained charges and approved cleanup plan. |

Do not describe cost estimates as savings or health checks as high availability. Capture run IDs, timestamps, commit, image digests, namespace, logs and outcomes before presenting.
