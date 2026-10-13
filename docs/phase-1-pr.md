# Phase 1 pull request

Suggested title: Add Account and Payment APIs with local Docker demonstration

The repository was empty. This change adds two .NET 10 LTS APIs: Account API exposes fictional account data and balance validation; Payment API calls Account over HTTP and returns simulated approval or explicit rejection/unavailability results. Each API has its own non-root Docker image, and Compose configures their internal connection.

The change includes endpoint and dependency-failure tests, real-process/container smoke scripts, dependency lock files, local run instructions, an architecture diagram, the assignment-to-phase mapping and a read-only review of the previous project's patterns. Approved simulations do not transfer funds, update balances or persist payment records.

Validation results are recorded in `docs/phase-1-report.md`. Only Phase 1 is implemented. There are no AWS changes, Terraform resources, Helm charts or CI/CD workflows in this PR.
