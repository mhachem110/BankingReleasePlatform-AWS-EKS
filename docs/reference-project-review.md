# Previous project reference review

The public repository [mhachem110/CloudOpsTracker-AWS-3Tier](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier) was accessed read-only through the GitHub API and raw files on October 10, 2026. Its default branch was `main`. No changes were made there.

All requested files were read:

| File | Useful pattern | Adaptation needed later |
| --- | --- | --- |
| [bootstrap.yml](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/.github/workflows/bootstrap.yml) | Manual plan/apply, OIDC with `AWS_ROLE_ARN`, protected environment, saved plan, concurrency | Separate validation from AWS-authorized jobs; never run bucket mutations implicitly before approval; inspect existing role |
| [network.yml](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/.github/workflows/network.yml) | Environment-specific state, plan on normal promotion, explicit apply/destroy | Start with dev, scope paths, approval gates and state prefixes to the new repository |
| [platform.yml](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/.github/workflows/platform.yml) | Separate platform lifecycle, saved apply/destroy plans, environment concurrency | App releases should not trigger Terraform apply; omit old EC2/AMI snapshot cleanup logic |
| [bootstrap/main.tf](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/infra/bootstrap/main.tf) | Existing bucket import, prevent_destroy, versioning, AES256 encryption, public block and TLS policy | Confirm bucket ownership/reuse approval, current backend locking support and deliberate bootstrap boundary; use unique state keys |
| [bootstrap/iam.tf](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/infra/bootstrap/iam.tf) | OIDC `aud`, scoped environment `sub`, separate trust and permissions | It creates deployment roles and grants broad service permissions; these cannot be copied under the user's IAM restriction |
| [project.env](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/infra/project.env) | Non-secret central configuration | Its OIDC repo segment includes owner/repository IDs; inspect actual customization for the new repo instead of guessing or reusing these IDs |
| [ensure-state-bucket.sh](https://github.com/mhachem110/CloudOpsTracker-AWS-3Tier/blob/main/scripts/bootstrap/ensure-state-bucket.sh) | Bucket-before-backend ordering, region handling, public block, versioning and encryption | Script performs AWS writes even on workflows labelled plan; new bootstrap must require deliberate approval and verify ownership. A failed HeadBucket can mean denied access, not necessarily absence |

No names, resource/state identifiers, owner/repository IDs, old permissions or role creation code were copied into the implementation. Phase 1 contains no Terraform or Actions workflow.

## Future connectivity inspection checklist

When Phase 2 is approved, inspect the existing `cloudbatch818-mahmoud-cloudops-bootstrap` role's current complete trust policy, attached/inline policies, boundary and user authorization to update it. Confirm the GitHub IAM OIDC provider, actual repository identity and subject customization. The reference indicates a customized subject pattern but does not prove how the new repository or current AWS role is configured.

Preserve authorized trust statements. Generate complete updated trust JSON and additive scoped permissions only after those inputs exist. Inspect Organizations SCPs, PassRole and service-linked-role limits, plus distinct EKS cluster/node/controller roles. Trust determines who can assume a role; permissions determine what it may do. No AWS policies were inspected or changed in Phase 1, so current AWS eligibility remains unverified.
