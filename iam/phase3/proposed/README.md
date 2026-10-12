# Administrator proposals only

No policy here has been applied. Use the single request in
`docs/infrastructure/ADMIN-REQUEST.md` after owner authorization.

- Three service trusts: only new dedicated identities with the exact names.
- BankingFlowLogs: inline permissions only on the dedicated flow role.
- BankingAppDev-new-role-trust and BankingAppDev-permissions: only a new approved
  Banking app deployment role, not a replacement shared-role trust.
- BankingOperatorDiscovery: additive discovery permission for an approved
  existing human-assumable operator; no human trust is guessed.
- BankingKeyPolicy: complete policy for a **new dedicated key only**. Shared keys
  require preservation and an additive owner review. Creation is paid/approval-gated.
- BankingReleasePlatformPhase3.REVIEW-TEMPLATE: complete review shape with an
  inert key marker. **Do not paste it.** Render the final complete exact-key JSON
  using `scripts/infra/prepare-admin-request.py` with the actual approved KMS ARN.
- BankingAdministratorTags: ManagedBy=Administrator for administrator-owned roles/key (organizational approval required), not instructions to retag
  shared identities/keys. Optional CostCenter is omitted until assigned.

Preserve CloudOpsTrackerBootstrap, BankingReleasePlatformState and both current
Retail/Banking bootstrap trust statements. The controller trust is exported only
after the real Banking EKS issuer exists; never fabricate an issuer or key ARN.

BankingAppProd-new-role-trust/permissions are conditional NEW-role proposals when
full audit shows the retained CloudOps production identity is too broad. Pull and
banking-dev discovery only; no publication, IAM or cluster administration. Shared
role trusts and original CloudOps policies must remain intact.
