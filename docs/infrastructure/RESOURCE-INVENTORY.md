# Exact final source inventory (offline mock, not a live AWS plan)

45 Terraform managed entries: 44 AWS resources/configurations and one local prerequisite. They are not 44 separate billable services. Actual saved live-plan values, effective tags, real ARNs and approval remain pending. The mock provider leaves tags_all unresolved; the live guard rejects that condition. All 31 supported explicit tag maps were tested.

| Terraform address | Type | Name / Name tag | Tags supported |
| --- | --- | --- | --- |
| terraform_data.prerequisites | terraform_data | No independent name; linked configuration | No |
| module.eks.aws_cloudwatch_log_group.cluster | aws_cloudwatch_log_group | /aws/eks/banking-dev/cluster | Yes |
| module.eks.aws_eks_access_entry.deployer | aws_eks_access_entry | banking-dev-deployer-access | Yes |
| module.eks.aws_eks_access_entry.operator | aws_eks_access_entry | banking-dev-operator-access | Yes |
| module.eks.aws_eks_access_policy_association.deployer | aws_eks_access_policy_association | No independent name; linked configuration | No |
| module.eks.aws_eks_access_policy_association.operator | aws_eks_access_policy_association | No independent name; linked configuration | No |
| module.eks.aws_eks_addon.this["coredns"] | aws_eks_addon | banking-dev-coredns-addon | Yes |
| module.eks.aws_eks_addon.this["metrics-server"] | aws_eks_addon | banking-dev-metrics-server-addon | Yes |
| module.eks.aws_eks_cluster.this | aws_eks_cluster | banking-dev | Yes |
| module.eks.aws_eks_fargate_profile.banking | aws_eks_fargate_profile | banking-dev-app | Yes |
| module.eks.aws_eks_fargate_profile.controller | aws_eks_fargate_profile | banking-dev-controller | Yes |
| module.eks.aws_eks_fargate_profile.coredns | aws_eks_fargate_profile | banking-dev-coredns | Yes |
| module.eks.aws_iam_openid_connect_provider.cluster | aws_iam_openid_connect_provider | banking-dev-irsa | Yes |
| module.network.aws_cloudwatch_log_group.flow | aws_cloudwatch_log_group | /banking/banking-dev/vpc-flow | Yes |
| module.network.aws_default_security_group.closed | aws_default_security_group | banking-dev-default-deny | Yes |
| module.network.aws_eip.nat | aws_eip | banking-dev-nat-eip | Yes |
| module.network.aws_flow_log.this | aws_flow_log | banking-dev-vpc-flow | Yes |
| module.network.aws_internet_gateway.this | aws_internet_gateway | banking-dev-igw | Yes |
| module.network.aws_nat_gateway.this | aws_nat_gateway | banking-dev-nat | Yes |
| module.network.aws_route.internet | aws_route | No independent name; linked configuration | No |
| module.network.aws_route.nat["0"] | aws_route | No independent name; linked configuration | No |
| module.network.aws_route.nat["1"] | aws_route | No independent name; linked configuration | No |
| module.network.aws_route_table.application["0"] | aws_route_table | banking-dev-application-0 | Yes |
| module.network.aws_route_table.application["1"] | aws_route_table | banking-dev-application-1 | Yes |
| module.network.aws_route_table.database["0"] | aws_route_table | banking-dev-isolated-database-0 | Yes |
| module.network.aws_route_table.database["1"] | aws_route_table | banking-dev-isolated-database-1 | Yes |
| module.network.aws_route_table.public | aws_route_table | banking-dev-public | Yes |
| module.network.aws_route_table_association.application["0"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_route_table_association.application["1"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_route_table_association.database["0"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_route_table_association.database["1"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_route_table_association.public["0"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_route_table_association.public["1"] | aws_route_table_association | No independent name; linked configuration | No |
| module.network.aws_subnet.application["0"] | aws_subnet | banking-dev-application-0 | Yes |
| module.network.aws_subnet.application["1"] | aws_subnet | banking-dev-application-1 | Yes |
| module.network.aws_subnet.database["0"] | aws_subnet | banking-dev-database-0 | Yes |
| module.network.aws_subnet.database["1"] | aws_subnet | banking-dev-database-1 | Yes |
| module.network.aws_subnet.public["0"] | aws_subnet | banking-dev-public-0 | Yes |
| module.network.aws_subnet.public["1"] | aws_subnet | banking-dev-public-1 | Yes |
| module.network.aws_vpc.this | aws_vpc | banking-dev-vpc | Yes |
| module.network.aws_vpc_endpoint.s3 | aws_vpc_endpoint | banking-dev-s3 | Yes |
| module.registry.aws_ecr_lifecycle_policy.service["account"] | aws_ecr_lifecycle_policy | No independent name; linked configuration | No |
| module.registry.aws_ecr_lifecycle_policy.service["payment"] | aws_ecr_lifecycle_policy | No independent name; linked configuration | No |
| module.registry.aws_ecr_repository.service["account"] | aws_ecr_repository | banking-dev-account | Yes |
| module.registry.aws_ecr_repository.service["payment"] | aws_ecr_repository | banking-dev-payment | Yes |

## Proposed subnet layout

| Tier | AZ index 0 | AZ index 1 | Usable addresses each before allocations |
| --- | --- | --- | ---: |
| Public | 10.70.0.0/24 | 10.70.1.0/24 | 251 |
| Application | 10.70.32.0/20 | 10.70.48.0/20 | 4091 |
| Isolated database | 10.70.64.0/24 | 10.70.65.0/24 | 251 |

The approved AZ pair/CIDR and actual current account capacity remain prerequisites. Public tables route to IGW, application tables to the one NAT in AZ index 0, database tables have local routing only. Both application tables use the regional ECR-layer S3 gateway endpoint. Terraform mock-apply tests verify every association/gateway reference; no AWS apply ran.

Service-role ARNs, operator/deployer ARNs and KMS key are administrator-owned inputs, not managed creation entries. The new cluster issuer/provider is computed by EKS. No EC2 instance, launch template, node group, IAM role, RDS, ALB or new state bucket is permitted. AWS-created cluster SGs/ENIs/default network ACLs/main route tables/Fargate hosts are not additional explicitly tagged Terraform entries.

Control-plane/VPC logs: 30-day retention, actual approved KMS key; cluster secrets use that same approved key. ECR uses AES256, immutable tags, basic scan-on-push and seven-day untagged cleanup; tagged rollback releases are retained. EKS deletion protection and ECR force_delete=false require separately reviewed cleanup.
