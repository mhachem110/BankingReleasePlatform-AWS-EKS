# Integrated Fargate application/infrastructure interface

PRs #8, #9 and #10 are merged in dev. One coordinator now owns integration. Reusable infra and feature/app branches remain separate workstreams with ordinary merges; no branch rewrite or shared-index commits. This document records interfaces, not AWS deployment authorization.

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
| Kubernetes access | Approved operator has cluster admin; separate dev/prod application groups have only their namespace release RBAC |

## Helm and release requirements

- Linux amd64 images; equal CPU/memory requests and limits on every container. App planning baseline is 250m/512Mi; Fargate allocates 0.25 vCPU/1GB after system memory overhead.
- Avoid DaemonSets, hostNetwork, hostPort, privileged containers, EC2 node selectors, topologySpreadConstraints and affinity-based availability claims. Fargate does not guarantee even placement across the two selected subnets.
- AWS VPC CNI NetworkPolicy enforcement is unavailable on Fargate. Do not claim an applied NetworkPolicy isolates these Pods. This lab initially uses private subnets, EKS-managed cluster SG and explicit Kubernetes access; stronger per-workload isolation needs a separately reviewed design.
- Controller Helm values must specify clusterName=banking-dev, region=us-east-2 and actual vpcId. IMDS is unavailable. Create its ServiceAccount with eks.amazonaws.com/role-arn set to the administrator-approved IRSA role ARN; projected service-account token must remain available to the controller. Banking API accounts do not inherit that role or the execution role.
- Install controller CRDs/RBAC/webhooks and the namespace using the approved operator, not the namespace-scoped app deployer. Admission webhook port 9443 and Metrics Server serving port 10251/kubelet port 10250 are covered by the EKS-managed SG self rule.
- Banking readiness/liveness use port 8080. Readiness gates may delay an IP-target ALB rollout until targets are registered and healthy. HPA requires healthy Metrics Server; it scales Pods, not an EC2 node group.
- The infrastructure workflow does not install the controller or applications. The live controller rollout and sts:AssumeRoleWithWebIdentity verification are a separate authorized operator deployment.
- GitHub OIDC/environment approval is distinct from Kubernetes IRSA. No AWS credentials in PR validation. Workflows execute paid changes only from reviewed environment branches and approved environments.

Approved PR #10 permits only the required owner-authored application release paths on feature/app while preserving infrastructure/IAM/governance ownership, CODEOWNERS, required security checks and the six branch routes. No bypass or missing-check requirement is introduced. Reviewed infrastructure preparation can update shared Helm metadata through infra.

## Approved shared-cluster demonstration update

PR #15 is integrated at d101fb7. The current reviewed target is one banking-dev
control plane and two application profiles/namespaces (banking-dev and banking-prod),
with distinct release identity groups and operator-installed namespace RBAC/quotas.
Apply both helm/banking/namespaces manifests and iam/phase3/deployer-verification-rbac.yaml
only after approved EKS creation. No application identity may install these controls.
The exact current platform inventory is 46 managed entries, 33 taggable.
See SHARED-CLUSTER.md and ADMIN-REQUEST.md for current architecture/access limits.
