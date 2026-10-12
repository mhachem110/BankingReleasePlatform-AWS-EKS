# Infrastructure/application interface and deployment prerequisites

This is the shared application/infrastructure interface. PR #8 and PR #10 are merged;
feature/app has synchronized with their approved dev history through ordinary merges.
The application PR does not modify infrastructure or IAM files.

Confirmed interface:
- Cluster and namespace banking-dev, Region us-east-2, port 8080.
- Fargate profile selects every banking-dev Pod in both private application subnets.
- CoreDNS profile selects kube-system / k8s-app=kube-dns.
- Controller profile selects kube-system / app.kubernetes.io/name=aws-load-balancer-controller.
- Metrics Server profile selects kube-system / k8s-app=metrics-server.
- Future controller uses IRSA ServiceAccount kube-system/aws-load-balancer-controller,
  explicit region=us-east-2 and VPC ID. No Pod Identity/IMDS assumption.
- No topology spreading or VPC CNI NetworkPolicy enforcement assumption on Fargate.
- App container 250m/512Mi equal requests/limits; budget 0.25vCPU/1GB task per Pod.

Remaining infrastructure/admin dependencies:
1. Healthy CoreDNS on Fargate, private Pod routing on TCP 8080, DNS TCP/UDP 53,
   HTTPS image-pull/AWS connectivity, free subnet IPs including two rolling-update surge
   Pods, and Fargate Pod execution role authorized for the exact ECR repositories.
2. Existing immutable banking-dev-account/payment ECR repositories. Application
   publishing verifies mutability and fails instead of changing it.
3. Approved dedicated banking-deployer runner reaching the EKS API through the planned
   narrow endpoint allowlist/private network. No public 0.0.0.0/0 exception.
4. Administrator-provided application OIDC role and EKS access entry/RBAC, including
   namespace release permissions and Namespace/Node get for verification.
   See ENVIRONMENT.md. Keep bootstrap/Terraform permissions separate.
5. Namespace banking-dev created once with the prepared restricted Pod-security labels,
   outside the app Helm release; keep environment-specific namespaces/clusters isolated.
6. Protected dev environment and approval controls before enabling manual app actions.
7. The approved governance change now authorizes only the required owner-authored
   application release paths. Required security checks, restricted infrastructure/IAM
   ownership and branch/environment protection remain active. PR #9 still needs its
   own merge approval after current checks pass.
8. The final Fargate interface from approved PR #8 is reconciled with the newer chart.
   Preserve that interface and use ordinary merges for future synchronization.

CoreDNS and Metrics Server add-ons are prepared in the infrastructure code; their actual
versions, Fargate scheduling and runtime health require protected AWS preflight/deployment
verification. Optional HPA and ALB ingress remain disabled. The controller/IRSA role,
approved ACM host/certificate, selected ALB subnets/security groups and backend rules
need separate approval. Application workflows do not create ALBs or enable ingress.

Prepared later stage/UAT/prod targets do not request provisioning those environments.
This interface conveys no approval to merge PR #9, provision infrastructure, change IAM
or incur cloud costs.
