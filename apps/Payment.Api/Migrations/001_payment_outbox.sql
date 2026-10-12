CREATE TABLE banking_payment.payments (
    payment_id uuid PRIMARY KEY,
    idempotency_key varchar(64) NOT NULL UNIQUE,
    account_id varchar(64) NOT NULL,
    amount numeric(18,2) NOT NULL CHECK (amount > 0 AND amount <= 1000000),
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE banking_payment.outbox (
    event_id uuid PRIMARY KEY REFERENCES banking_payment.payments(payment_id),
    payload text NOT NULL,
    state varchar(10) NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','sent','dead')),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_id uuid,
    lease_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz
);
CREATE INDEX outbox_dispatch ON banking_payment.outbox(next_attempt_at) WHERE state='pending';
CREATE TABLE banking_payment.processed_events (
    event_id uuid PRIMARY KEY,
    payment_id uuid NOT NULL,
    payload_sha256 char(64) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);
