# Banking release and operations architecture

Prepared target. Local API/PostgreSQL/SQS-compatible behavior is tested; dashed
cloud components remain pending approved deployment and live acceptance.

```mermaid
flowchart LR
  Commit[Reviewed environment commit] --> CI[Tests and Docker/Trivy/Helm/IaC checks]
  CI --> Publish[Protected immutable ECR publication]
  Publish --> Release[Same digest pair and protected Helm release]
  Release -.-> Fargate[EKS Fargate private Pods]
  Fargate -.-> Account[Account API]
  Fargate -.-> Payment[Payment API]
  Payment -->|Service DNS validation| Account
  Account -.-> Accounts[(Private PostgreSQL account schema)]
  Payment -.-> Transaction[(Payment and outbox transaction)]
  Transaction -.-> SQS[Encrypted SQS source]
  SQS -.-> Receipt[(Idempotent PaymentCompleted receipt)]
  SQS -.-> DLQ[Poison message DLQ]
  Transaction -.-> Dead[Retained dead outbox rows]
  Account --> Metrics[Private per-Pod metrics]
  Payment --> Metrics
  Metrics -.-> Prom[Approved Prometheus/Grafana Deployments]
  Fargate -.-> Router[Built-in Fargate log router]
  Router -.-> Logs[Encrypted CloudWatch logs]
  Logs -.-> Alarms[Owned alarms and approved receiver]
```

The Payment API validates an account through Kubernetes DNS, then records a
simulation and its outbox event atomically. It never debits accounts or moves funds.
The outbox worker sends to standard SQS, and the consumer commits a stable receipt
before deleting the message. Source/DLQ redrive and dead outbox recovery are distinct.

```mermaid
sequenceDiagram
  participant Client
  participant Payment
  participant Account
  participant DB as PostgreSQL
  participant Worker
  participant Queue as SQS
  Client->>Payment: Synthetic payment + Idempotency-Key
  Payment->>DB: Check prior key/body
  alt Existing identical request
    DB-->>Payment: Original payment ID
    Payment-->>Client: Same simulation result
  else New request
    Payment->>Account: Validate via Service DNS
    Account-->>Payment: Synthetic validation decision
    Payment->>DB: BEGIN / payment + outbox / COMMIT
    Payment-->>Client: Recorded simulation ID
  end
  Worker->>DB: Claim token lease (SKIP LOCKED)
  Worker->>Queue: Send stable PaymentCompleted event
  Worker->>DB: Mark sent only after success
  Queue-->>Worker: May deliver more than once
  Worker->>DB: Verify payment / commit unique hashed receipt
  Worker->>Queue: Delete only after receipt commit
```

GitHub deployer, Fargate execution, application runtime IRSA and human/migration
identities are separate. Runtime database identities have no DDL ownership.
Production PostgreSQL verifies TLS hostname/CA. Secrets are mounted from approved
operator-managed Secrets; the chart does not invent AWS identities or passwords.
Only Payment mounts a service-account token when separately approved messaging is
enabled. Prometheus has namespace-only read access for annotated Pod discovery.
No EC2 nodes, DaemonSets, Pod Identity or Fargate NetworkPolicy enforcement is assumed.

Rollout failure restores the prior Helm revision and digest pair. Schema migrations
are forward-only and must remain compatible with the prior image. Rollback never
deletes/reseeds durable payment data. External ALB/HTTPS, RDS/SQS/KMS/IAM, logging,
collector Pods, notification routing and all extra environment costs remain gated.
