# Reviewed service templates and historical administrator proposals

The three service trust templates and BankingFlowLogs.json are consumed unchanged by the new Terraform IAM prerequisite root. [The current provisioning proposals](../../provisioning/README.md) supersede manual service-role creation and the broad legacy BankingReleasePlatformPhase3 wildcard review template, which has been removed. Other conditional proposals below remain subject to their own future scope/authorization review.

No policy here has been applied. Use the single request in
the reviewed [administrator handoff](../../../ADMIN-HANDOFF.md) after owner authorization.

BankingObservedMetadataReads.json contains only the three denied read actions
observed in run 38318982706. It is an additive administrator proposal for the
existing bootstrap role, not authorization to modify it. The quota diagnostic
identifies a missing identity allow; generic Organizations denials still need
administrator diagnosis. This allow cannot override explicit denies. Provide
an authoritative organization review instead where these reads are unavailable.

- Three service trusts: only new dedicated identities with the exact names.
- BankingFlowLogs: inline permissions only on the dedicated flow role.
- BankingAppDev-new-role-trust and BankingAppDev-permissions: only a new approved
  Banking app deployment role, not a replacement shared-role trust.
- BankingOperatorDiscovery: additive discovery permission for an approved
  existing human-assumable operator; no human trust is guessed.
- BankingKeyPolicy: complete policy for a **new dedicated key only**. Shared keys
  require preservation and an additive owner review. Creation is paid/approval-gated.
- The legacy broad review template was removed; render narrowly scoped exact-key
  JSON using `scripts/infra/prepare-admin-request.py` with approved identifiers.
- BankingAdministratorTags: ManagedBy=Administrator for administrator-owned roles/key (organizational approval required), not instructions to retag
  shared identities/keys. Optional CostCenter is omitted until assigned.

Preserve CloudOpsTrackerBootstrap, BankingReleasePlatformState and both current
Retail/Banking bootstrap trust statements. The controller trust is exported only
after the real Banking EKS issuer exists; never fabricate an issuer or key ARN.

BankingAppProd-new-role-trust/permissions are conditional NEW-role proposals when
full audit shows the retained CloudOps production identity is too broad. Pull and
banking-dev discovery only; no publication, IAM or cluster administration. Shared
role trusts and original CloudOps policies must remain intact.
