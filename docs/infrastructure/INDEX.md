# Documentation guide

Start with the root [README](../../README.md) for local application setup, APIs, and the project overview. This page points to the main engineering guides; dated reports preserve their checkpoint evidence and should not be treated as current deployment status.

## Build and run

- [Local application and test instructions](../../README.md)
- [Deployment guide](../deployment/README.md)
- [Application architecture](../deployment/ARCHITECTURE.md)
- [Demo presentation and walkthrough](../deployment/DEMO-PRESENTATION.md)

## Cloud platform

- [Infrastructure architecture](ARCHITECTURE.md)
- [Provisioning workflow](DEPLOYMENT.md)
- [Infrastructure pipeline overview](PROJECT-PIPELINE.md)
- [Cost assumptions](COSTS.md)
- [Acceptance checklist](ACCEPTANCE.md)
- [Safe cleanup procedure](CLEANUP.md)
- [Operational runbook and incident recovery](../deployment/INCIDENTS.md)

## Security and governance

- [Branch workflow](../governance/reusable-branches.md)
- [Security policy](../governance/security.md)
- [Application release scope](../governance/application-release-scope.md)
- [Assignment requirements mapping](../assignment-requirements.md)

## Historical evidence

- [Phase 1 implementation and local test record](../phase-1-report.md)
- [Phase 2 preparation record](../phase2/REPORT.md)
- [Phase 2 completion evidence](../phase2/COMPLETION.md)
- [Infrastructure reconciliation](RECONCILIATION.md)
- [Phase 6 offline evidence](../deployment/PHASE6-OFFLINE-REPORT.md)
- [Governance verification snapshot](../governance/security-verification.md)

Use the date and linked GitHub run in each evidence report to determine what it proves. A local report, mock test, Terraform plan, or code merge alone does not prove that AWS workloads are currently deployed or healthy.
