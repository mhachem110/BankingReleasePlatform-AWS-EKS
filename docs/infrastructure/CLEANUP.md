# Reviewed test cleanup

The `Reviewed Banking test VPC destroy` workflow removes the verified VPC seed
from its native `dev/platform` state. It is enabled only on reviewed `dev`, with
`CLEANUP_ENABLED=true` and `AWS_OPERATIONS_ENABLED=false`. Creation is disabled
during cleanup. Both the plan and apply jobs retain the bootstrap reviewer gate.

Dispatch `operation=apply` with `DESTROY-REVIEWED-BANKING-VPC-SEED`. Review the
first deployment to permit read-only inspection and saved destroy-plan creation.
Before the second review, inspect the saved plan, SHA256, actual VPC ID, tags and
dependency checks. The apply job rechecks the state lineage, serial, inventory,
backend, interface, run attempt and binary digest. It applies that saved binary
and then confirms the state is empty and AWS reports the VPC absent.

The teardown root has no resource creation blocks. It uses the same pinned AWS
provider and exact backend key as the creation root; creation safeguards remain
in the creation configuration. The session allows deletion of only the verified
VPC with Banking/dev ownership tags, writes only its state, and deletes only its
state lock. It retains the backend, state history and all shared IAM resources.
No imports, state removal, force unlocks, targeted plans or forced deletes occur.

The current workflow refuses full platform states, populated VPCs and dependent
data states. Full platform/data teardown must be implemented and reviewed before
those deployments; Kubernetes ingress/controller cleanup, ECR image inventory,
EKS/RDS deletion protection and final snapshots require their own concrete
handling. This workflow alone does not establish full-project teardown readiness.

After a successful test destroy, set `CLEANUP_ENABLED=false` and remove the stale
`NETWORK_SEED_REVIEW_JSON`. A later creation run must publish a fresh verified
interface. Keep the final full deployment only after its acceptance tests pass,
as requested by the project owner.

# Reviewed Banking teardown and residual charges

The owner has authorized project cleanup. The protected test-VPC workflow above
is implemented; full platform/data teardown remains to be implemented and tested.
EKS deletion protection is enabled. A reviewed Banking-only update must disable it
before the saved destroy plan is applied; the initial creation-only workflow cannot
perform that update. Preserve Retail/CloudOps, state and shared IAM/key resources.

1. Obtain owner approval of exact cleanup inventory. Remove approved ingress while
   controller and IRSA still work, and confirm ALB, target groups, controller-created
   security groups/ENIs/public IPs are gone. Do not orphan the controller first.
2. Remove application/controller workloads and releases, then pinned system add-ons
   and Fargate profiles. Confirm Pods/ENIs have drained. Review immutable profile
   deletion impact and maintain approved operator access throughout.
3. After the approved deletion-protection update, destroy only the platform root's
   reviewed resources: access associations/entries, cluster, Banking OIDC provider,
   flow log, routes/endpoint/subnets/VPC, NAT and EIP. IAM OIDC deletion needs an
   additional separately scoped permission. Do not use the first-creation workflow
   for recovery or destruction; do not force-unlock or overwrite Terraform state.
4. ECR force_delete=false preserves releases: explicitly archive/delete authorized
   tagged images before approved repository removal. Tagged releases have no
   automatic expiry; untagged debris expires after seven days. Check storage costs.
5. Preserve Phase 2 bucket and bootstrap/foundation keys, Retail/CloudOps, existing
   GitHub provider, shared resources and administrator-owned roles/key. Retaining
   logs is an explicit owner decision; their 30-day event retention is not deletion
   of the log group or encryption key. Key deletion is a separate admin review.

After app Pods are removed, EKS control-plane hours, CoreDNS/Metrics/controller
Fargate Pods, NAT hours/data, allocated public IPv4, log ingestion/storage and KMS
key/requests may continue. ECR image storage, S3 current/noncurrent state versions
and requests remain until their own approved cleanup/retention actions. Any ALB,
approved runner or other later service has independent charges. The free S3 gateway
endpoint, routes and empty VPC/subnets do not themselves add hourly service fees.

Confirm actual post-cleanup EKS/profile/EC2 NAT/EIP/ELB/ECR/log inventory in Ohio,
verify state and unrelated resources are intact, restore AWS_OPERATIONS_ENABLED=false,
and check Cost Explorer after billing data catches up. Deleting APIs alone is not
teardown evidence. No orphan-resource deletion outside the reviewed inventory.
