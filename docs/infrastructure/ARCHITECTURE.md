# Phase 3 architecture and shared-account boundaries

```mermaid
flowchart TD
  PR[infra PR into dev] --> CI[Credential-free Terraform / Checkov / Helm CI]
  DEV[Reviewed dev commit] --> REVIEW[Protected bootstrap review]
  REVIEW --> OIDC[GitHub OIDC temporary session]
  OIDC --> PLAN[Read-only prerequisites and saved platform plan]
  PLAN --> APPROVE[Owner reviews exact resource plan and costs]
  APPROVE --> APPLY[Protected saved-plan apply]
  APPLY --> STATE[S3 existing Banking bucket / separate platform key + lock]
  APPLY --> ECR[Immutable Account and Payment ECR repositories]
  APPLY --> EKS[EKS 1.36 control plane / explicit access entries]
  subgraph VPC[New Banking VPC across two AZs]
    PUBLIC[Two public subnets / IGW / one NAT]
    PRIVATE[Two private application subnets / two managed workers]
    DB[Two isolated database subnets / future RDS]
    S3EP[Free S3 Gateway Endpoint]
    PRIVATE --> PUBLIC
    PRIVATE --> S3EP
  end
  EKS --> PRIVATE
  ECR --> PRIVATE
  PRIVATE -. Phase 4 Helm .-> PAYMENT[Payment API]
  PAYMENT --> ACCOUNT[Account API via private Kubernetes Service]
  EKS --> LOGS[KMS-encrypted control-plane and flow logs]
  PUBLIC -. Phase 4 approved HTTPS ingress .-> ALB[Future ALB]
  ALB -.-> PAYMENT
```

The state bucket is outside the VPC. Database subnets are reserved only; no database is provisioned. The dotted application/ALB paths are prepared future deployments, not running resources.

Read-only AWS Console inventory on 11 October 2026 found four existing Ohio VPCs with primary CIDRs `10.20.0.0/16`, `10.50.0.0/16`, `10.60.0.0/16` and `172.31.0.0/16`; two active EKS clusters (`cloudbatch818-zein-hcsecops`, `guduf-retail-eks-dev`); eighteen ECR repositories, none with either proposed Banking name. IAM role prefix search `cloudbatch818-mahmoud` returned the bootstrap and four CloudOps deploy roles, with no Banking cluster/node/flow/controller roles. These observations do not establish authorization to reuse other projects or prove quotas/SCPs permit a new cluster.

Proposed CIDR `10.70.0.0/16` does not overlap those observed primary ranges. The runtime preflight checks all primary/secondary CIDR associations and available AZs again before a live plan. It refuses to adopt existing Banking names, shared resources or unknown IAM identities. State, names and tags are project specific.

The previous CloudOpsTracker OIDC/S3 pattern informed protected workflows and backend separation. The read-only healthcare example informed separate AWS/Helm stages, digest releases and explicit role prerequisites, but its Fargate/DynamoDB design and resource names are not used. Banking uses two ASP.NET APIs, managed EC2 nodes and future relational storage.
