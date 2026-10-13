# Verified Banking deployment readiness

The project is **40% complete against the twenty acceptance milestones below**:
eight implemented and evidenced milestones, twelve mandatory live milestones
still blocked. Each milestone counts equally at five percentage points. This
is a progress estimate; offline tests do not prove cloud operation.

The owner-approved [read-only AWS run 38318982706](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS/actions/runs/38318982706)
succeeded on 12 October 2026 at 8:06 PM Eastern, from reviewed dev commit
8cba32d125a9d5c9f1c1230c9d4b7f628924c78b. Its artifact SHA256 is
d4a2eda93989b9bbde6c3c42b8c798c0029ea8edb2bb7aa509a7796e7067b821.
Both files were downloaded and inspected; the ZIP hash matches GitHub's digest.
AWS account 866934333672 and Ohio us-east-2 are verified through bootstrap OIDC.
Collection success does not mean provisioning readiness.

| Acceptance milestone | Verified status |
| --- | --- |
| Account and Payment implementation and API tests | PASS, 70 tests on integrated dev |
| Docker packaging and local service communication/recovery | PASS, container regression |
| Terraform modules, state separation and offline validation | PASS, ten roots and 29 mock tests |
| Helm workloads, probes, resources/RBAC and release safeguards | PASS, Helm/schema tests |
| PR test/build/security/IaC/Helm checks | PASS, nine integrated-dev checks |
| Protected Terraform backend and lock/recovery baseline | PASS, recorded Phase 2 live evidence |
| Protected bootstrap OIDC into the approved AWS account | PASS, current read-only session |
| Dev/prod GitHub branch/reviewer environment configuration | PASS, recorded API audit |
| Healthy shared EKS Fargate cluster and namespaces | BLOCKED, banking-dev absent |
| Dev/prod workloads, Services/DNS and probes | BLOCKED, cluster absent |
| Actual immutable ECR publication and Helm deployment | BLOCKED |
| Same-digest protected dev-to-prod promotion | BLOCKED |
| Runtime namespace denials, scoped identities and secrets/KMS | BLOCKED |
| ALB/controller and HTTPS request path | BLOCKED |
| Private RDS persistence, TLS and replacement durability | BLOCKED |
| Actual SQS outbox dispatch, retry and DLQ | BLOCKED |
| Operational dashboards, logs, metrics and delivered alert | BLOCKED |
| Failed release detection, rollback and live scaling | BLOCKED |
| Live security findings and measured cost baseline | BLOCKED |
| Final migration/recovery evidence and trainer demonstration | BLOCKED |

Persistence, messaging, monitoring, promotion and rollback code have local
regression evidence. The blocked rows require actual AWS results.

## Actual AWS findings

- Both deployment roles have the exact immutable Banking dev/prod subjects and
  audience, and their Banking inline policies are present. All six retained
  managed policies were read: core/iam at v1 and services at v2 for each role.
  Do not request these additions again.
- Each deployment role retains broad CloudOps permissions, with no permissions
  boundary and sixteen audit scope findings. Workflow session caps restrict the
  prepared releases, but not other sessions using the shared roles. Current
  trusts contain only Banking; earlier trust preservation requires an owner
  baseline and cannot be proved from this snapshot.
- The three dedicated cluster, Fargate execution and Flow Logs roles return
  NoSuchEntity. Both EKS/Fargate service-linked roles already exist.
- EKS lists two unrelated clusters and no banking-dev. The four regional VPC
  CIDRs are 10.20.0.0/16, 10.50.0.0/16, 10.60.0.0/16 and 172.31.0.0/16.
  Proposed 10.70.0.0/16 does not overlap this snapshot; approval and fresh
  preflight are still required. All three Ohio AZs are available.
- EKS 1.36 is in STANDARD_SUPPORT. Default compatible amd64/Fargate candidates
  are CoreDNS v1.14.7-eksbuild.10 and Metrics Server v0.9.0-eksbuild.11. Schema
  reads did not run without platform inputs; the updated inspector collects
  candidate schemas without inventing complete or approved platform settings.
- servicequotas:ListServiceQuotas is denied because no identity policy allows
  it. organizations:ListPoliciesForTarget and organizations:ListParents are
  generically denied; this does not prove an empty organization policy set.
  No operator or KMS key was nominated, so their absence is not asserted.
- GitHub currently has zero registered deployment runners, no
  PLATFORM_INPUTS_JSON/CAPACITY_REVIEW_JSON and all AWS/application/data
  switches false. BOOTSTRAP_STATE_READY remains true.

## One administrator return

Use [the consolidated request](ADMIN-REQUEST.md), prioritizing these blockers:

1. Create the three confirmed missing roles from the complete
   [service trusts and Flow Logs policy](../../iam/phase3/proposed/README.md).
   Return actual ARNs. Existing service-linked roles need no recreation.
2. Nominate an actual human-assumable operator and approved enabled symmetric
   Ohio KMS key/policy/grants. Render exact-key additive platform permissions
   after receiving real values. New paid key creation requires separate approval.
3. Review retained deployment privileges. Prefer prepared new dedicated Banking
   dev/prod roles or explicitly approve shared-role reuse under release session
   caps. Preserve shared policies/trusts; no automatic detachment is proposed.
4. Review [the three observed denied reads](../../iam/phase3/proposed/BankingObservedMetadataReads.json)
   or provide authoritative organization/deny evidence. Return quota AND actual
   usage/headroom with 7.0 available Fargate vCPU and EKS/NAT/EIP/ENI/IP approval,
   observed within 24 hours. An identity allow cannot override an explicit deny.
5. Approve VPC CIDR/AZs, stable narrow endpoint CIDRs and a disposable Linux x64
   deployment host/network path. Runner registration needs actual host approval.
6. Approve add-on pins after schema validation. Assemble complete platform/capacity
   inputs from verified values; the next gate is the protected live PLAN.

Apply follows a separate review of that actual saved plan and cost exposure.
The existing cost model is a sensitivity, not an approved spending cap. No live
Terraform, IAM/KMS change, paid resource creation or cleanup occurred in this audit.
The project's mandatory live acceptance is incomplete.
