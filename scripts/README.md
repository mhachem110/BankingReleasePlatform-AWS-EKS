# Automation and validation scripts

Scripts are grouped by the protected operation they support. Invoke them from the repository root unless a workflow explicitly changes directories.

- `scripts/bootstrap/` checks the GitHub/AWS bootstrap contract, backend bucket, lock and reviewed plans. Its tests protect state and IAM inspection behavior.
- `scripts/infra/` validates scoped inputs, identity/policy contracts, saved plans and outputs, estimates cost, prepares handoffs and verifies cleanup. Destructive checks remain separate because they validate different inventories and approval receipts.
- `scripts/deploy/` builds and scans images, validates Helm/monitoring, verifies immutable release provenance, deploys, performs smoke/integration checks and rolls back. The offline suite uses local fixtures and never substitutes for live acceptance.
- `scripts/governance/` validates trusted PR metadata and repository path ownership. It reads GitHub metadata; it must not execute PR-provided code.

Run the application offline suite with `python scripts/deploy/offline.py`, infrastructure Python tests with `python -m unittest discover -s scripts/infra/tests -v`, bootstrap tests with `python -m unittest discover -s scripts/bootstrap/tests -v`, and governance tests with `python -m unittest discover -s scripts/governance/tests -v`. See [infrastructure operations](../infra/OPERATIONS.md) before any protected deployment or cleanup workflow.
