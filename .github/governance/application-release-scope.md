# Reviewed application release scope

PR #10 approved the narrow release-path and verification-access contract; PR #9
application release code and PR #11 final infrastructure preparation are merged.
See [historical project checkpoints](../../infra/PROJECT-HISTORY.md) for recorded
GitHub controls and pending live execution. The original review history remains
available in the merged PRs.

The trusted metadata policy permits exactly helm/banking/**, scripts/deploy/**,
and four workflows: app-ci.yml, app-validation.yml,
app-publish.yml and app-deploy.yml under .github/workflows, alongside ordinary
application paths. Release-path changes require verified cloud-owner author ID
150286776. Terraform/HCL/backend files and CODEOWNERS remain forbidden to
feature/app even inside release directories. Renames check both paths;
artifact, repository identity, pagination and head-race checks remain strict.

CODEOWNERS, the six branch routes, native rulesets, required Repository security
policy, trusted pull_request_target execution and AWS/environment protections
remain separate controls. These paths grant no AWS role or deployment access.
Independent code-owner review requires a second eligible reviewer; no reviewer
identity is invented. Future policy changes require an infra/security PR.

The namespace-scoped application access entry also maps the approved deployer to
banking-release-verifier. The prepared RBAC grants get on Nodes and get on only
namespace banking-dev, with no node mutation or cluster administration. An
approved operator installs the binding after cluster creation; the group alone
grants nothing until that binding exists. Live access remains unverified.
