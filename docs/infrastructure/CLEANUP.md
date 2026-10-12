# Reviewed Banking teardown and residual charges

No destroy workflow or deletion authorization is supplied. EKS deletion protection
is enabled. A separately approved Banking-only update must disable it before a
reviewed destroy plan; the initial creation-only workflow cannot perform that
update. Never change Retail/CloudOps, state or shared IAM/key resources to unblock it.

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
