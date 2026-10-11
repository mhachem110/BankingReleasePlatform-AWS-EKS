# Interface requirements for Chat 1

This is the application-owner handoff document. No infrastructure file is changed.

Confirmed coordination message:
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
7. Review the feature/app path-policy conflict in a separate infra/security workstream.
   Do not bypass the mandatory aggregate or expand all application file privileges.
   The concrete paths are four new app workflows, helm/banking/**, scripts/deploy/**,
   and docs/deployment/**. No proposed governance patch is bundled here.
8. Preserve/reference the final Fargate chart interface from PR #8. Application PR must
   reconcile that final version and follow the infrastructure baseline merge.

Optional dependencies remain disabled: Metrics Server/HPA and ALB controller/IRSA,
approved ACM host/certificate, selected ALB subnets and security groups with approved
backend rules. Application workflows do not create ALBs or enable ingress.

Prepared later stage/UAT/prod targets do not request provisioning those environments.
No approval to merge PR #8, provision infrastructure, change IAM or incur cloud costs
is conveyed by this document.
