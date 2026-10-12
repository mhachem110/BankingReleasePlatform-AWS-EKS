# Banking naming, ownership and cost tags

The approved convention lives in `infra/environments/dev/platform/main.tf`:
`local.common_tags` supplies AWS provider `default_tags` and each child module's
`tags` input. Modules merge only `Component`, unique meaningful `Name`, and subnet
discovery tags. No tag contains secrets or customer information.

| Key | Approved value / handling |
| --- | --- |
| Project | BankingReleasePlatform |
| Environment | dev |
| ManagedBy | Terraform |
| Owner | MahmoudHachem; configurable only with an approved owner |
| Purpose | CloudEngineerTraining |
| CostCenter | Optional `cost_center`; absent when null. Never an invented billing code. |
| Component | network, eks, fargate, registry, security, logging |
| Name | banking-dev plus a resource role/tier/index; logs also have meaningful AWS group names |

The exact inventory has **31 explicitly managed taggable resources**. Routes,
route-table associations, ECR lifecycle policies and EKS access-policy
associations do not expose independent tags in the pinned provider. The local
`terraform_data` prerequisite is not an AWS resource. Their owning resources are
tagged. AWS creates cluster security groups, ENIs, default network ACLs/main route
tables and Fargate host resources; provider defaults do not propagate to them.
Do not claim all automatic resources receive this convention. Terraform closes
and tags only the default security group of its new VPC; it adopts no shared VPC.

Both explicit `tags` and effective `tags_all` are checked by the protected saved
plan audit. Terraform mock providers leave `tags_all` unknown: offline tests
verify the explicit maps and that the **live** guard rejects unknown or conflicting
effective tags. There is no live bypass flag. Actual live compliance remains
pending administrator inputs and a protected plan.

Dedicated administrator-provided IAM roles/key use the reviewed tag maps in
`iam/phase3/proposed/BankingAdministratorTags.json`. Despite this requested project
taxonomy, these resources remain externally administrator-owned and outside
Terraform state. `ManagedBy=Terraform` is not permission to alter/destroy them.
Shared identities/keys keep their tags unless their owner separately authorizes
an additive change. Effective account tag-policy requirements, including a
mandatory CostCenter if imposed, are an administrator prerequisite; no value is
guessed to get around one.

## Kubernetes metadata is different

Helm adds app.kubernetes.io name, instance, part-of, component, managed-by and
version labels; environment comes from the actual banking namespace. A 12-hex
image digest prefix fits Kubernetes label limits. The complete digest and
approved owner are annotations. Stable Service/Deployment selectors retain
their existing `app` label so changing a version does not break communication.
These are Kubernetes metadata, **not AWS cost allocation tags**.

[AWS documents](https://docs.aws.amazon.com/eks/latest/userguide/eks-using-tags.html)
that Fargate profile tags do not propagate to Pods. Project-tag filtering alone
must not be represented as complete attribution of all Fargate Pod charges.
Record Pod billed capacity, cluster/namespace workload inventory and actual
billing usage alongside the tagged resource report; investigate unallocated
Fargate/network charges separately in the shared account.

## Billing administrator proposal only

AWS Billing and Cost Management -> Cost allocation tags -> User-defined tags:
after resource tags appear, activate Project, Environment, Owner, Purpose,
ManagedBy and Component; activate CostCenter only once actually assigned/used.
Name is optional for detailed resource attribution. Activation may take up to
24 hours to appear and another 24 hours to become active; confirm actual status.
Then Cost Explorer -> filter Tag Project=BankingReleasePlatform -> group by
Service/Environment/Component and reconcile unallocated usage. This is a proposal,
not an organization-wide billing change performed by this project.
[AWS activation instructions](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html)
