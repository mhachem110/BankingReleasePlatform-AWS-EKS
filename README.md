# Banking Release Platform

AWS Week 4 Financial Services CI/CD and Kubernetes Release Platform, by Mahmoud Hachem. Phase 1 implements two ASP.NET Core APIs using .NET 10 LTS and local Docker containers. All customers and payments are fictional.

The current folder was empty and was not a Git repository at the initial inspection. This implementation initializes local Git with `main` and the feature branch `feature/phase1-banking-apis`. No remote repository is configured; the new GitHub repository URL must be confirmed by the owner. The earlier CloudOpsTracker repository is a read-only reference, not this project's remote.

Only Phase 1 is implemented. AWS provisioning, IAM changes, Terraform, Helm and CI/CD workflows require approval of their respective phases. See [requirements mapping](docs/assignment-requirements.md), [architecture and repository layout](docs/architecture.md), [reference review](docs/reference-project-review.md) and [Phase 1 report](docs/phase-1-report.md).

## Prerequisites

- .NET SDK 10.0.400 or a newer patch in the 10.0.4xx feature band. `global.json` chooses the installed compatible patch.
- Docker Desktop with Linux containers and Docker Compose v2 or later.
- PowerShell 5.1 or later for the included smoke scripts. `test-local.ps1` uses Windows process and port APIs.
- Free local ports 5101 and 5102. Compose binds these to loopback on your computer.

.NET 10 is a supported LTS release through November 14, 2028. .NET 8 reaches end of support on November 10, 2026. ([Microsoft support policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core))

## Run both services with Docker Compose

From the repository root:

```powershell
docker compose config --quiet
docker compose up --build -d
./scripts/smoke-test.ps1
docker compose ps
docker compose logs --tail 50
```

Account API is at `http://localhost:5101`; Payment API is at `http://localhost:5102`. `/health` on each should return `Healthy` with HTTP 200. The smoke script waits for startup and verifies real HTTP communication between the containers. Compose dependency ordering alone does not guarantee readiness.

```powershell
docker compose down
```

This stops and removes only this Compose project's containers and network. The two local images remain available. No AWS resources are involved.

Build images separately if needed (use the repository root as the build context):

```powershell
docker build -f apps/Account.Api/Dockerfile -t banking-week4/account-api:local .
docker build -f apps/Payment.Api/Dockerfile -t banking-week4/payment-api:local .
```

## Run without Docker

Restore and run Account API in one PowerShell terminal:

```powershell
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet run --project apps/Account.Api -- --urls http://localhost:5101
```

Run Payment API in a second terminal:

```powershell
dotnet run --project apps/Payment.Api -- --urls http://localhost:5102 --AccountApi:BaseUrl http://localhost:5101/
```

Run `./scripts/smoke-test.ps1` in a third terminal. Stop the APIs with Ctrl+C. An alternative is `./scripts/test-local.ps1`, which builds, starts the two APIs, runs smoke checks, and stops the processes it started. It refuses to use occupied ports. For alternate ports: `./scripts/test-local.ps1 -AccountPort 5201 -PaymentPort 5202`.

## Automated tests and formatting

```powershell
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet test BankingReleasePlatform.sln -c Release --no-restore
dotnet format BankingReleasePlatform.sln --verify-no-changes --no-restore
```

The xUnit tests exercise account endpoints, business decisions, payment request validation, HTTP client contracts, malformed JSON, network errors, timeouts and unexpected dependency responses. Payment tests substitute Account HTTP responses for deterministic failure cases; the smoke script additionally exercises the two real running services. NuGet lock files are committed. Docker restores in locked mode. Test outputs and process logs belong under ignored `artifacts/`.

## Try a payment

```powershell
Invoke-RestMethod -Uri http://localhost:5101/api/accounts
Invoke-RestMethod -Uri http://localhost:5101/api/accounts/ACC1001

$request = @{ accountId = 'ACC1001'; amount = 25; currency = 'USD' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5102/api/payments -ContentType application/json -Body $request
```

Expected result: HTTP 200, `status: simulated`, `code: payment_approved`, and a generated `paymentId`. No funds move, no balances change, and no payment is stored. Repeated requests are independent simulations; there is no durable ledger or idempotency guarantee in this phase.

| Sample account | Fictional customer | Balance | Active |
| --- | --- | ---: | --- |
| ACC1001 | Alex Example | 1500.50 USD | Yes |
| ACC1002 | Sam Sample | 75.00 USD | Yes |
| ACC1003 | Taylor Fiction | 400.00 USD | No |
| ACC1004 | Jordan Demo | 0.00 USD | Yes |

| API | Operation | Result |
| --- | --- | --- |
| Account | `GET /api/accounts` | List sample accounts |
| Account | `GET /api/accounts/{id}` | Account with balance/activity; 404 if missing |
| Account | `POST /api/accounts/{id}/validate` | Body: `{"amount":25,"currency":"USD"}`; validation decision |
| Both | `GET /health` | Process health, HTTP 200 `Healthy` |
| Payment | `POST /api/payments` | Body: `{"accountId":"ACC1001","amount":25,"currency":"USD"}`; simulation decision |

Validation decisions from Account use HTTP 200 for known accounts, including negative business decisions. A missing account uses 404. Payment maps negative business decisions to 422, missing accounts to 404, invalid inputs to 400, and dependency failure to 503. Invalid JSON also returns 400. Amounts must be positive, at most 1,000,000, and have at most two decimal places; use three uppercase currency letters. Payment IDs allow at most 64 ASCII letters/digits/hyphens. The sample accounts support USD.

Payment uses a three-second outbound timeout and approves only a consistent validation response. `/health` confirms the API process is alive; it does not claim its dependencies are available. A payment request verifies the actual Account dependency path.

## Configuration and boundaries

Payment reads `AccountApi:BaseUrl`, with `http://localhost:5101/` as the local default. In Compose, `AccountApi__BaseUrl=http://account-api:8080/` uses Docker's service name resolution. `localhost` inside the payment container refers to that container itself, so it cannot be used to reach Account API.

Each Dockerfile builds with the SDK in one stage and copies only published output into an ASP.NET runtime stage. The runtime runs as the image's unprivileged application user. Compose uses a read-only filesystem, temporary `/tmp`, no Linux capabilities, and no privilege escalation. The initial image tags are local development tags; immutable release tagging is deferred to Phase 5.

`IAccountRepository` isolates data access so an RDS-backed implementation can replace `SampleAccountRepository` later. `IAccountClient` isolates Payment's HTTP dependency. Authentication, durable storage, ledger operations, secrets integration, cloud telemetry and release scanning are later phase work. Local HTTP endpoints are intended for a fictional lab demonstration.

## Local dependency failure demonstration

With Compose running:

```powershell
docker compose stop account-api
./scripts/smoke-test.ps1 -ExpectAccountUnavailable
docker compose start account-api
./scripts/smoke-test.ps1
```

While Account API is stopped, Payment's `/health` stays healthy but payment requests return 503 with `account_service_unavailable` and no payment reference. After Account restarts, the ordinary checks should pass again. This is a local dependency check; the assignment's controlled EKS release failure and rollback demonstration remains Phase 7 work.

## Feature branch and pull request

The implementation is on `feature/phase1-banking-apis`. The initial `main` commit provides a local base for review. Confirm the destination GitHub repository before setting `origin` or publishing. The exact GitHub steps and prepared PR description are in [the Phase 1 report](docs/phase-1-report.md). No GitHub Actions workflow or AWS secret is needed in this phase.
