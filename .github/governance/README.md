# Repository governance

`AGENTS.md` defines work branches, ownership and authorization rules. This directory records the branch promotion and trusted path-policy controls; `.github/rulesets/` contains reviewed ruleset import JSON. These files document repository protections and do not grant AWS permissions or replace GitHub's active protection settings.

- [Branch workflow](reusable-branches.md) defines the reusable branches and promotion sequence.
- [Security and path policy](security.md) documents independent controls and trusted workflow limits.
- [Application release scope](application-release-scope.md) records the approved application release exception.
- Historical PR and run references are summarized in [project history](../../infra/PROJECT-HISTORY.md).

Change CODEOWNERS, path validation, shared workflows or ruleset templates only in an owner-reviewed `infra` PR. Keep required checks, protected environment approvals, no-bypass rules and OIDC restrictions intact.
