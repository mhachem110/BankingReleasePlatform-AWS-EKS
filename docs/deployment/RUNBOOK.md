# Offline checks and pending live Kubernetes demonstration

## Offline validation

Windows or Linux requires git, .NET SDK satisfying global.json (10.0.400 latest patch),
Python 3.12 and Docker with a running Linux engine. Initial setup needs internet access
for packages, pinned tools, base images, Kubernetes schemas and Trivy's current database;
offline here means no AWS/EKS dependency. Warm caches retain tools/schema artifacts.

From the feature/app worktree:
```powershell
python -m pip install -r scripts/deploy/requirements.txt
python scripts/deploy/offline.py
```

Use --skip-install after verified tool installation, and --reuse-images only when the
application/Docker inputs have not changed. The runner restores/builds/tests .NET,
executes Helm/deployment safety tests, validates Kubernetes 1.36 schemas and workflows,
builds images once, exercises Docker DNS + HTTP integration + dependency recovery,
and scans those same saved image bytes. Output lives in git-ignored artifacts/application/.
offline-result.json contains exit status/duration and each check has its own log.

No AWS credentials or kubeconfig are required. Test image names are local banking-ci-*
references; fake ECR digests used by Helm fixtures must never be deployed.
Trivy uses no ignore-unfixed or exception flags. Resolve actual findings before publishing.

## Live prerequisites and deployment

Infrastructure/chart reconciliation and the approved governance change are complete.
Pending: separate application PR approval, explicit Phase 3 deployment, ACTIVE banking-dev,
healthy CoreDNS and Fargate profiles, approved runner,
namespace, separate app OIDC role/RBAC and protected dev environment variables.
Check ENVIRONMENT.md and CHAT1-REQUIREMENTS.md. No live checks have run.

After those approvals, use GitHub Actions:
1. Dispatch Publish approved application images from reviewed dev with authorization
   approved. Protected dev approval and APP_DEPLOYMENTS_ENABLED=true are both required.
2. Inspect the successful scan evidence and release-manifest artifact. Record its run ID.
3. Dispatch Deploy approved application digest from reviewed dev, environment dev, that
   publish_run_id and authorization approved. Approve its protected environment review.
4. Observe exact-digest/Fargate rollout checks and 15 HTTP integration checks.
   A failed deployment must remain failed even if rollback succeeds.
5. Preserve successful deployment evidence before promoting approved branch PRs.
   Dispatch stage from stage, UAT from uat, production/prod from main using the same
   publication run ID. Each requires predecessor success, its own existing infrastructure,
   environment variables/role and separate approval. Never rebuild the promoted images.

Default deployment always sets ingress off, resets demonstration flags, uses explicit
environment values, and keeps namespace ownership outside the release.

## Kubernetes demonstration after separate live-test approval

Read-only inspection commands on an already approved context:
```powershell
kubectl -n banking-dev get pods,services,deployments -o wide
kubectl -n banking-dev describe deployment banking-account
kubectl -n banking-dev describe deployment banking-payment
kubectl -n banking-dev get endpointslices
helm history banking -n banking-dev
kubectl -n banking-dev logs deployment/banking-account --tail=100
kubectl -n banking-dev logs deployment/banking-payment --tail=100
python scripts/deploy/kube-smoke.py --namespace banking-dev
```

For the automated mutation demonstration, use the approved banking-dev runner/context
and the same approved dev environment variables (GITHUB_REPOSITORY/GITHUB_REF also
identify repository and reviewed branch). Run only after explicit approval:
```powershell
python scripts/deploy/demonstrate.py --execute
```

Without --execute the script only states the pending live checkpoint and makes no AWS
or Kubernetes calls. With approval it validates the current API endpoint against
banking-dev, records Pods/Services, verifies Fargate nodes and DNS payment integration,
performs a rolling Payment Pod restart and verifies new Pod UIDs, scales both Deployments
to three through Helm, restores replicas, injects a failing Payment readiness path,
asserts upgrade failure, verifies automatic rollback restores digests/healthy probes,
reruns integration checks, and records release history and API logs. A finally block
restores the original release configuration and verifies health again.

Scaling and replacement create Fargate compute and require live-test/cost authorization.
With maxUnavailable=0, failed new Pods should leave old ready Pods serving.
The demonstration does not delete application data; sample data is fictional/in memory.
Success evidence goes to artifacts/application/demonstration/ only after verification.

## Recovery

On failure, inspect Actions diagnostics and Helm history; compare previous values/digests.
Do not clear history or delete namespaces. For an operator-approved recovery:
```powershell
helm rollback banking PREVIOUS_GOOD_REVISION -n banking-dev --wait --timeout 10m
kubectl -n banking-dev rollout status deployment/banking-account --timeout=600s
kubectl -n banking-dev rollout status deployment/banking-payment --timeout=600s
python scripts/deploy/kube-smoke.py --namespace banking-dev
```

If Pods are Pending, inspect events for profile selection/private IP/quota capacity.
If ImagePullBackOff, inspect immutable ECR digest existence, Pod execution permissions
and private subnet connectivity. If DNS fails, verify CoreDNS Fargate selection/health
and DNS routes/security-group rules. If the API runner cannot connect, review its
approved network path; do not widen endpoint access automatically.
An OIDC/RBAC denial requires the administrator's reviewed role/access setup, never
a bootstrap/infra role fallback. A namespace/Node get denial needs narrow read-only RBAC.
