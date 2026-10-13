# One infrastructure deployment entry

`project-deploy.yml` presents **Infra CI/CD**. It validates scope, runs the existing
credential-free Terraform/Helm/security CI, then calls the foundation, network,
platform and data workflows from the same Git commit. Native bootstrap environment
reviews, saved binary hashes, backend locks and live verification remain intact.
Destroy stays outside this entry. An apply cannot cancel an earlier project run.

Select `target=project`, `operation=apply` and
`APPLY-REVIEWED-BANKING-PROJECT` only after the complete deployment prerequisites
below are implemented and verified. This is a development change, not evidence of
a live cluster or a completed project. No project deployment has been dispatched
for this change.

The foundation returns its actual key/operator. The network returns its actual
owned VPC/default group. These outputs replace stale dependency IDs for the next
stage without modifying GitHub environment variables. The platform returns actual
subnets and cluster group only after live verification and a zero-drift plan;
the data stage consumes those outputs. Planned/computed identifiers cannot stand
in for an applied dependency. A first-time plan cannot resolve every later plan
until its dependencies exist; apply progresses through the saved-plan reviews in
the same run.

A complete unchanged foundation skips write credentials and apply. A verified VPC
is reused without initializing the smaller seed Terraform root over full platform
state. Unknown state, policy drift, key substitution or partial foundation state
stops without automatic destruction. CI reuses the checksum-verified provider
within its job, avoiding repeated large provider downloads across Terraform roots.
No states or credentials enter that cache.

The final job reports each real stage result and requires actual verification
outputs before calling an apply successful. A skipped or failed stage is never
deployment proof. Terraform success also does not prove Kubernetes readiness,
application behavior, production-data isolation or rollback.

The remaining work before dispatching the complete project is managed platform cap
publication from the actual new key/VPC, measured quota and cost evidence, runtime
IAM/alert prerequisites, production data orchestration, a private deployment
runner, full platform/data cleanup, Kubernetes bootstrap and end-to-end acceptance.
The App CI/CD and dedicated Rollback consolidation follows that resource work as
the owner requested. Existing required checks and protections stay in place.
