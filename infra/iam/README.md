# IAM and workload access

All AWS identity documents for this project live under `infra/iam/`. Terraform roots and scripts consume these paths directly. These policies and trust documents are reviewed inputs; a JSON file alone does not create or authorize an AWS identity.

- `phase3/` contains the pinned AWS Load Balancer Controller policy, its provenance and reviewed trust/policy proposals. Kubernetes RBAC is installed from [the Helm/Kubernetes path](../../helm/banking/rbac/deployer-verification-rbac.yaml).
- `provisioning/` contains split stage-specific Terraform provisioner policies, the service boundary, review manifest and AWS authorization metadata. Keep the split documents within AWS managed-policy size limits and use the manifest hashes. Finalize actual resource identifiers only from reviewed outputs.
- `runtime-foundation/` contains the dedicated operator/key documents consumed by the runtime foundation root.
- `additions/` contains bootstrap/runtime, CodeBuild and Fargate policy additions supplied for review; it does not imply the policies are attached.
- `evidence/` holds sanitized historical OIDC configuration evidence. Recheck live trust before use.

Preserve the existing CloudOpsTracker, bootstrap and state identities. Do not broaden OIDC trust, edit shared roles, attach all proposal templates, or treat Terraform plans/tests as IAM authorization. See [operations](../OPERATIONS.md) and [governance](../../.github/governance/security.md).
