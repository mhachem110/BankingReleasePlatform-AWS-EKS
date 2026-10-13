# Administrator and deployment handoff

This checklist is a review aid. It does not authorize AWS changes or assert that any prerequisite is currently absent or present. Use a fresh protected read/plan and current owner-provided values before an operation.

- Confirm the exact AWS account, Ohio Region, protected GitHub environment, OIDC `aud` and immutable repository subject.
- Inspect existing identity policies, permissions boundary, SCP/RCP and resource policies. Preserve shared CloudOpsTracker, Retail, bootstrap and state roles, policies and trust.
- Verify only project-owned IAM roles, permissions boundaries, service-linked roles, KMS key policies/grants, CodeBuild connection, EKS access entries and workload identities needed by the reviewed plan.
- Provide actual role/key/cluster/network/alert identifiers and approved resource quotas; never infer values from templates or historical evidence.
- Review each saved plan and SHA256, exact resource inventory, tags, Terraform state lineage/serial, dependent state outputs, IAM changes and current cost exposure before approving apply.
- For RDS operations, decide database deletion protection, final snapshot retention/name/encryption, backup retention and deletion cost. Retain any KMS key required by a kept snapshot.
- For cleanup, confirm all project dependencies and unrelated/shared resources; retain the Terraform backend bucket and state history.

IAM proposals and additions remain under [`infra/iam/`](iam/README.md). Exact operations, approvals and dependency order are in [operations](OPERATIONS.md). Use [historical project checkpoints](PROJECT-HISTORY.md) only for context; they are not current inventory or approval.
