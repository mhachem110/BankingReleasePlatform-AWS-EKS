# Persistent payments and event handling

The Account and Payment APIs remain synthetic; no funds move and account balances do not change. Memory mode is the default. PostgreSQL and messaging are opt-in through separately approved configuration and protected data operations.

## PostgreSQL and migrations

The dev and production-demo databases are isolated through separate state/configuration, namespaces, credentials and workload identities. RDS is private, encrypted and accepts traffic only from the approved cluster security group. Runtime connection strings and CA material come from operator-managed Secrets Manager delivery; the Helm chart does not create credentials. Verify PostgreSQL TLS with the approved root certificate and hostname. Never place a database password, master secret or access token in source, Helm values, logs or test artifacts.

The runtime database identity has only the permissions required for its schema operations and does not own the database or run DDL. API startup does not create schemas. An authorized operator applies the exact reviewed, checksum-verified additive migration. Seed data is inserted once and must never overwrite existing accounts. Connection pools are bounded per Pod. Rotate secrets through the approved secret workflow and a controlled rolling restart.

Schema changes are forward-only and must work with both the current and previous application image. Rollback restores the application release only; it does not undo a migration or restore database data. Before any RDS deletion, decide whether to retain a final snapshot, verify its name and KMS key, and review snapshot/storage charges.

## Payment replay and transactional outbox

In PostgreSQL mode, idempotency key/body validation, payment row and outbox row are committed in one transaction. The event contains a stable event/payment ID, schema version, event type, amount/currency and UTC timestamp, but no customer name or credentials. The API returns an approved response only after commit. Replaying the same key and body returns the recorded result; changing the body under an existing key is rejected.

The dispatcher claims outbox rows with `SKIP LOCKED` and a time-bounded token lease. Delivery is at least once: a crash after SQS send but before marking the row sent can produce a duplicate. A consumer validates the event against the stored synthetic payment and writes a unique hashed receipt before deleting the message. This receipt makes replay safe; it is not an exactly-once SQS guarantee or a distributed transaction with Account API.

Send retries use bounded backoff; exhausted work remains as a dead outbox row for operator recovery. SQS consumer failures remain unacknowledged and use visibility backoff and the configured redrive policy to a DLQ. Verify source/DLQ identity, visibility, retention and `maxReceiveCount` before enabling messaging. Misconfiguration blocks sending. Do not acknowledge poison payloads or delete them without preserving evidence.

## Runtime IAM and release integration

Only the Payment ServiceAccount may receive its separately approved IRSA role and web identity token when messaging is enabled. Account API remains token-free. The Payment role is restricted to the approved dev/prod queue pair and required KMS actions; it is separate from GitHub deployment, Fargate execution, migration/operator and controller identities. The app chart references existing secrets, CA ConfigMaps, role annotations and queue URLs; it does not create cloud resources or IAM policies.

Data operations have their own Terraform state, protected switch, saved-plan hash and cost receipt. An approved apply must match the inspected account/Region, cluster/VPC/security group, key, engine version, instance class, monitoring role and alert destination. Plan and review each environment independently. Verify TLS, runtime least privilege, replay behavior, persistence after Pod replacement, SQS receipt/retry and DLQ handling before claiming data acceptance.

For incidents, preserve the payment ID, event ID, idempotency-key hash, outbox state/attempts, SQS message ID, payload hash and receipt. Recover only the specifically authorized row or message after resolving its cause. Never perform a broad table reset, destructive down migration, queue purge or unreviewed DLQ redrive.
