# Banking Release Platform

AWS Week 4 Financial Services CI/CD and Kubernetes Release Platform. The repository contains .NET Account and Payment APIs, container and Helm deployment code, Terraform AWS infrastructure, GitHub Actions workflows, security/governance controls, and operational runbooks. All sample customers and payments are fictional.

The development default is [`dev`](https://github.com/mhachem110/BankingReleasePlatform-AWS-EKS). Use the [documentation index](docs/infrastructure/INDEX.md) to find architecture, deployment, infrastructure, security, cleanup, and historical evidence guides. Deployment and AWS status are time-sensitive; check the dated [infrastructure reconciliation](docs/infrastructure/RECONCILIATION.md) and linked GitHub run records rather than inferring live state from source code or an old report.

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

Expected result: HTTP 200, `status: simulated`, `code: payment_approved`, and a generated `paymentId`. No funds move and no balances change. Default memory mode retains a bounded payment journal until the API restarts. Send the same `Idempotency-Key` header and body to replay one payment; a changed body with that key returns 409. Explicit PostgreSQL mode persists the journal and transactional outbox across restarts. This remains a simulation, not a financial ledger.

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
| Both | `GET /ready` | Storage/migration readiness; 503 during a PostgreSQL outage |
| Both | `GET /metrics` | Private Prometheus endpoint with bounded route labels |
| Payment | `POST /api/payments` | Body: `{"accountId":"ACC1001","amount":25,"currency":"USD"}`; simulation decision |
| Payment | `GET /api/payments/{id}` | Stored payment, using the returned compact UUID; 404 if missing |

Validation decisions from Account use HTTP 200 for known accounts, including negative business decisions. A missing account uses 404. Payment maps negative business decisions to 422, missing accounts to 404, invalid inputs to 400, and dependency failure to 503. Invalid JSON also returns 400. Amounts must be positive, at most 1,000,000, and have at most two decimal places; use three uppercase currency letters. Payment IDs allow at most 64 ASCII letters/digits/hyphens. The sample accounts support USD.

Payment uses a three-second outbound timeout and approves only a consistent validation response. `/health` confirms the API process is alive; it does not claim its dependencies are available. A payment request verifies the actual Account dependency path.

## Configuration and boundaries

Payment reads `AccountApi:BaseUrl`, with `http://localhost:5101/` as the local default. In Compose, `AccountApi__BaseUrl=http://account-api:8080/` uses Docker's service name resolution. `localhost` inside the payment container refers to that container itself, so it cannot be used to reach Account API.

Each Dockerfile builds with the SDK in one stage and copies only published output into an ASP.NET runtime stage. The runtime runs as the image's unprivileged application user. Compose uses a read-only filesystem, temporary `/tmp`, no Linux capabilities, and no privilege escalation. Compose tags remain local development tags. The merged publication/deployment workflows prepare immutable SHA/run tags and verified ECR digests; no cloud publication has run.

`IAccountRepository` selects sample memory data or explicit PostgreSQL storage. `IAccountClient` isolates Payment's HTTP dependency. PostgreSQL uses verified TLS in production, mounted connection files, explicit checksum-verified forward migrations and separate runtime/migration database privileges. Messaging is disabled by default; enabling it requires a durable outbox and approved SQS/IRSA references. Authentication and ledger operations remain outside this synthetic lab. Actual cloud secrets, telemetry, publication and deployment acceptance are pending.

## Phase 6 offline data and operational preparation

Run `python scripts/deploy/offline.py --skip-install` with the pinned tools already installed, or omit `--skip-install` for setup. The command runs API, Helm/Kubernetes, monitoring, container, PostgreSQL/SQS recovery and vulnerability checks without an AWS session. Run `python scripts/deploy/data-integration.py` for the isolated data suite; it starts only owned loopback Docker fixtures and cleans them up.

[Data and event operations](docs/deployment/DATA-AND-EVENTS.md), [incident recovery](docs/deployment/INCIDENTS.md), [monitoring configuration](docs/deployment/monitoring/README.md), [architecture](docs/deployment/ARCHITECTURE.md) and [the 15-minute demonstration](docs/deployment/DEMO-PRESENTATION.md) cover the prepared implementation and remaining evidence. The gated Kubernetes demonstration also checks one durable payment after restart, scaling and failed-upgrade rollback when persistent storage is explicitly authorized. Live EKS, application, database, messaging, monitoring and rollback acceptance remain incomplete; the project is not finished.

## Local dependency failure demonstration

With Compose running:

```powershell
docker compose stop account-api
./scripts/smoke-test.ps1 -ExpectAccountUnavailable
docker compose start account-api
./scripts/smoke-test.ps1
```

While Account API is stopped, Payment's `/health` stays healthy but payment requests return 503 with `account_service_unavailable` and no payment reference. After Account restarts, the ordinary checks should pass again. This is a local dependency check; the assignment's controlled EKS release failure and rollback demonstration remains Phase 7 work.

## Working branches

Reuse `feature/app` for application work, `bootstrap` for backend/OIDC work, and `infra` for infrastructure and governance. Each change goes through a PR into `dev`; environment promotion uses `dev` → `stage` → `uat` → `main`. The three historical phase branches have been retired after their PRs merged. See [branch workflow](docs/governance/reusable-branches.md) and [repository instructions](AGENTS.md).

## Infrastructure and operations

The repository includes Terraform roots and modules, the `helm/banking` chart, deployment and rollback workflows, monitoring configuration, and protected cleanup procedures. Find the canonical guides in the [documentation index](docs/infrastructure/INDEX.md). The [dated reconciliation](docs/infrastructure/RECONCILIATION.md) and actual GitHub Actions runs are the sources for time-sensitive deployment evidence; old phase reports are retained as historical records only.
