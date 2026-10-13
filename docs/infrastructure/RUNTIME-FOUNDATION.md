# Project runtime foundation

The protected IAM run [38347553242](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38347553242)
created and verified the three Banking service roles, known attachments and flow
policy, followed by a zero-drift plan. Its creation window is now closed. This
proves service-role provisioning; the EKS cluster and application are still pending.

The next workflow creates a real project KMS key and a distinct operator identity.
It does not require invented existing key/operator ARNs. It runs from reviewed
`dev`, uses the existing bootstrap OIDC role and retains both native reviews.
Enable `RUNTIME_FOUNDATION_ENABLED=true` and `AWS_OPERATIONS_ENABLED=true`, keep
cleanup disabled, then dispatch `runtime-foundation.yml`, `operation=apply`,
`approval=APPLY-REVIEWED-BANKING-FOUNDATION`.

The saved plan must create exactly five resources: an account check, one symmetric
KMS key, its project alias, the operator role and its inline policy. The read-only
session cannot create resources. The reviewed write session names only the
operator, alias and tagged runtime keys. It cannot attach managed policies, change
bootstrap IAM or administer existing shared keys. Same-run binary/backend/document
checks precede apply; live key/trust/tags/policy/rotation checks and zero drift follow.

The key enables annual rotation and retains the account-root IAM delegation needed
for existing owner grants. It permits CloudWatch encryption only for Banking log
contexts and alarms in the project account/Region. This does not add rights to the
bootstrap role's identity policy. Runtime roles receive their own scoped IAM grants
later. The operator trusts only the verified repository's `bootstrap` environment,
can describe only `banking-dev` in AWS, and explicitly denies IAM administration and
role chaining. Its Kubernetes permissions are established by the separate platform
access entry. The application deployment identities remain distinct.

Pricing checked 13 October 2026 against [AWS KMS pricing](https://aws.amazon.com/kms/pricing/):
one customer managed key costs $1/month, prorated hourly, plus requests. Each of the
first two rotations adds $1/month. Using 730 hours/month for planning, key storage
alone is about $0.011/8 hours, $0.033/24 hours, $0.055/40 hours and $1/month before
rotation. This foundation plan includes no NAT, EKS, EC2 runner, ALB or RDS charges.
Those resources require their own actual saved plans and full cost estimates.

Cleanup uses the existing workflow with `target=runtime-foundation`,
`DESTROY-REVIEWED-BANKING-RUNTIME-FOUNDATION`, creation disabled and two bootstrap
reviews. It requires empty platform/data states and rejects live operator access,
unknown IAM attachments, altered policies/tags, key grants or use by clusters,
databases, retained snapshots, EBS, log groups or queues. It removes the exact alias
and operator, schedules only the actual project key for deletion after seven days,
and verifies the native state is empty, the operator/alias absent and key pending
deletion. Scheduled keys are not billed while pending deletion. Retained encrypted
data must be addressed before its key; this cannot substitute for full-project
platform/data teardown. The Phase 2 backend and shared resources are retained.

The owner requested pipeline consolidation after Terraform and Kubernetes work.
The intended presentation is App CI, App CD, Infra CI/CD, Destroy and Rollback, with
the mandatory repository policy gate preserved. That later change must retain the
existing protections and proven required check contexts. Include documented scans,
timeouts, readiness/availability checks and failed-release rollback; do not claim
an ATM/payment operation was cancelled or rolled back without an actual test.
