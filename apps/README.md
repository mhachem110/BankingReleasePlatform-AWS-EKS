# Banking APIs

The solution contains the Account API, Payment API and their .NET tests under `apps/`. Account serves fictional sample account data and validation decisions. Payment validates through Account's HTTP contract, validates request shape and records only a synthetic payment simulation; it does not debit balances or move money.

## Local development

From the repository root:

```powershell
dotnet restore BankingReleasePlatform.sln --locked-mode
dotnet test BankingReleasePlatform.sln -c Release --no-restore
dotnet format BankingReleasePlatform.sln --verify-no-changes --no-restore
docker compose config --quiet
docker compose up --build -d
./scripts/smoke-test.ps1
```

Compose exposes Account on `http://localhost:5101` and Payment on `http://localhost:5102`; both `/health` endpoints should return HTTP 200. Payment uses `http://account-api:8080/` inside Compose. Build images from the repository root so the Dockerfiles can copy the shared solution and locked dependency files.

| API | Request | Purpose |
| --- | --- | --- |
| Account | `GET /api/accounts` | List fictional sample accounts. |
| Account | `GET /api/accounts/{id}` | Read one sample account. |
| Account | `POST /api/accounts/{id}/validate` | Return the synthetic payment eligibility decision. |
| Payment | `POST /api/payments` | Validate and record a simulation; accepts `Idempotency-Key`. |
| Payment | `GET /api/payments/{id}` | Read the recorded simulation. |
| Both | `GET /health`, `GET /ready`, `GET /metrics` | Process health, dependency readiness and private Prometheus metrics. |

Payment uses a bounded outbound timeout for Account validation. The same idempotency key and body replays the original result; a changed body is rejected. Invalid requests return 400, missing accounts 404, negative payment decisions 422, and dependency/storage failure 503. `health` reports the process; `ready` reports dependency readiness. Memory-mode records do not survive an API restart.

Test projects are in `apps/tests/Account.Api.Tests`, `apps/tests/Payment.Api.Tests` and `apps/tests/Banking.Integration`. Keep project references and the solution file synchronized when adding a project. Integration fixtures are local and do not use AWS credentials or provision resources.

## Runtime boundaries

The default is memory mode. Explicit PostgreSQL mode uses TLS and an operator-managed connection secret; migrations are forward-only. Messaging is opt-in and requires the protected data workflow, transactional outbox, SQS/DLQ settings and Payment-only workload identity. Database and queue data are never rolled back by Helm. API health, readiness and metrics have different meanings; see [infrastructure operations](../infra/OPERATIONS.md) and [data behavior](../infra/DATA.md).
