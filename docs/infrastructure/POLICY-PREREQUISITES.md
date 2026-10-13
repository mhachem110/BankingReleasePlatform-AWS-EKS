# Project policy prerequisites

Protected read-only run [38342975527](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38342975527)
verified the owner's updated `terraform-policy`, repository-scoped immutable OIDC
trust and allowed service-role creation/pass-role simulations. The new contract
pins the observed permission document, trust, empty attached-policy inventory and
absent bootstrap boundary. It stops on subsequent drift and never changes this
shared role. Historical original-policy checks remain available in the audit;
the live owner-installed configuration supersedes that earlier baseline.

The boundary and IAM session policy were absent. The `Reviewed Banking policy
prerequisites` workflow publishes exactly these two reviewed documents with
Terraform in a separate native state:

- `cloudbatch818-mahmoud-banking-service-boundary`
- `BankingTerraformProvisioner-IamPrerequisites`

Set `POLICY_PUBLISH_ENABLED=true`, `AWS_OPERATIONS_ENABLED=true` and keep
`CLEANUP_ENABLED=false`. Dispatch `operation=apply` with
`APPLY-REVIEWED-BANKING-POLICIES`. Both plan and apply require bootstrap review.
The plan session has no IAM writes. The separately reviewed apply session can
only create/tag the exact two policies with project ownership tags. It cannot
attach policies or create/update/delete roles. Apply checks the same-run binary
hash, account, backend, documents and fresh owner authorization before execution.
Verification reads actual policy versions/tags and requires a zero-drift plan.

Managed STS session policies restrict the existing identity grant. They do not
need to be attached to the bootstrap role. The later three-role workflow checks
the verified owner grant and exact live session-cap document rather than requiring
an additional bootstrap policy attachment.

Close the publication window after verification and publish the actual boundary
digest to `IAM_BOUNDARY_POLICY_SHA256`. Enable the separately protected service-role
workflow only after successful policy verification. The policies themselves do
not prove that EKS, Kubernetes workloads, databases or application deployment works.

Execution checkpoint, 13 October 2026: [PR #19](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/pull/19)
merged with all eight checks passing. Protected destroy run
[38344028764](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38344028764)
removed test VPC `vpc-0d99a78bace47e05b`, verified AWS absence and zero managed
resources in the platform state. Its saved plan SHA256 was
`bfd20608665194e21d12be45b01399be8284799f40c8b25403ac8e234f4cbbea`.
Creation/cleanup are disabled and the stale seed interface was removed. The
dedicated backend/state history remains. Full-project live completion is pending.
