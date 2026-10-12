# Chat 1 / Chat 2 Fargate interface

Chat 1 owns infra, IAM, infrastructure docs/scripts, infra-operations.yml and Terraform validation. Chat 2 owns Helm, apps, deployment scripts and application CI/CD. Parallel work uses isolated checkouts; no branch rewrite or shared-index commits. PR #8 remains infra -> dev. This document records requirements, not permission to deploy or change another workstream.

| Interface | Value |
| --- | --- |
| Account / Region | Confirmed account supplied through variables; us-east-2 |
| Cluster / namespace | banking-dev / banking-dev |
| Application ports | Account 8080; Payment 8080 |
| Images | Outputs ecr_repositories.account/payment; immutable SHA tags and preferably digests |
| DNS | Payment calls Account's ClusterIP Service by Kubernetes DNS; no ALB hop |
| Fargate profiles | banking-dev-coredns, banking-dev-controller, banking-dev-app |
| CoreDNS selector | kube-system, k8s-app=kube-dns |
| Controller selector | kube-system, app.kubernetes.io/name=aws-load-balancer-controller |
| Metrics Server selector | kube-system, k8s-app=metrics-server (same controller profile) |
| Banking selector | Entire banking-dev namespace, no extra Pod labels required |
| Controller identity | IRSA: system:serviceaccount:kube-system:aws-load-balancer-controller |
| IRSA outputs | oidc_issuer_url and oidc_provider_arn; administrator approves final exact trust |
| Controller role | cloudbatch818-mahmoud-banking-alb-controller; administrator-created, not execution role |
| Networking outputs | vpc_id, application_subnet_ids, public_subnet_ids, cluster_security_group_id |
| ALB | IP targets; approved public subnets for internet-facing ALB; disabled until separately approved |
| Kubernetes access | Approved operator has cluster admin; separate application deployer edits banking-dev only |

## Helm and release requirements (Chat 2)

- Linux amd64 images; equal CPU/memory requests and limits on every container. App planning baseline is 250m/512Mi; Fargate allocates 0.25 vCPU/1GB after system memory overhead.
- Avoid DaemonSets, hostNetwork, hostPort, privileged containers, EC2 node selectors, topologySpreadConstraints and affinity-based availability claims. Fargate does not guarantee even placement across the two selected subnets.
- AWS VPC CNI NetworkPolicy enforcement is unavailable on Fargate. Do not claim an applied NetworkPolicy isolates these Pods. This lab initially uses private subnets, EKS-managed cluster SG and explicit Kubernetes access; stronger per-workload isolation needs a separately reviewed design.
- Controller Helm values must specify clusterName=banking-dev, region=us-east-2 and actual vpcId. IMDS is unavailable. Create its ServiceAccount with eks.amazonaws.com/role-arn set to the administrator-approved IRSA role ARN; projected service-account token must remain available to the controller. Banking API accounts do not inherit that role or the execution role.
- Install controller CRDs/RBAC/webhooks and the namespace using the approved operator, not the namespace-scoped app deployer. Admission webhook port 9443 and Metrics Server serving port 10251/kubelet port 10250 are covered by the EKS-managed SG self rule.
- Banking readiness/liveness use port 8080. Readiness gates may delay an IP-target ALB rollout until targets are registered and healthy. HPA requires healthy Metrics Server; it scales Pods, not an EC2 node group.
- The infrastructure workflow does not install the controller or applications. The live controller rollout and sts:AssumeRoleWithWebIdentity verification are a separate authorized operator deployment.
- GitHub OIDC/environment approval is distinct from Kubernetes IRSA. No AWS credentials in PR validation. Workflows execute paid changes only from reviewed environment branches and approved environments.

The installed governance policy currently classifies Helm/deploy workflows as infrastructure-owned and can block feature/app changes under the user's new split. Document that blocker in the application PR and request a scoped policy change; do not bypass or disable existing checks. README and application docs must be reconciled by Chat 2 after both PRs are reviewed.
