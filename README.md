# Banking Release Platform on AWS EKS

This project demonstrates secure CI/CD for synthetic .NET Account and Payment APIs using Terraform, AWS EKS Fargate, ECR, Helm, PostgreSQL, SQS and GitHub Actions. It is a training platform, not a financial ledger. Live deployment, alerting and recovery claims require current AWS and workflow evidence.

## Repository map

| Directory | Contents |
| --- | --- |
| `apps/` | .NET APIs, tests, Dockerfiles and application design |
| `infra/` | Terraform roots/modules, IAM, monitoring, cost inputs and operations |
| `helm/` | Banking chart, namespace manifests and Kubernetes RBAC |
| `scripts/` | Protected deployment, infrastructure, governance and validation tools |
| `.github/` | GitHub Actions, CODEOWNERS, governance and ruleset templates |

See [application development](apps/README.md), [infrastructure architecture](infra/README.md), [operations and cleanup](infra/OPERATIONS.md), [assignment criteria](infra/REQUIREMENTS.md) and [repository governance](.github/governance/README.md).

## Local application workflow

Requirements: compatible .NET SDK 10.0.4xx from `global.json`, Docker Desktop with Linux containers and Compose v2, and PowerShell for the smoke scripts. No AWS credentials are needed for local development.

```powershell
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet test BankingReleasePlatform.sln -c Release --no-restore
docker compose config --quiet
docker compose up --build -d
./scripts/smoke-test.ps1
docker compose down
```

Account API listens on `http://localhost:5101`; Payment API listens on `http://localhost:5102`. Both expose `/health` and `/ready`. The services use fictional sample data and payment simulations; they do not move funds or change balances.

## Protected cloud operations

Infrastructure and app releases run through their protected GitHub workflows from reviewed branches. Terraform plans use isolated state, reviewed saved-plan digests and explicit environment approvals. App publication/deployment uses scanned immutable digests and separate dev/prod approvals. Cleanup is a separate destructive workflow requiring its own reviewed inventory and snapshot decision. Start with `target=project`, `operation=plan` and read [operations](infra/OPERATIONS.md) before requesting any apply approval. Never treat this README, a mock plan or an old run as live AWS authorization or health evidence.
