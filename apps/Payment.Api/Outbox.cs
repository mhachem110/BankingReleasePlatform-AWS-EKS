using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Banking.Platform;
using Npgsql;

namespace Payment.Api;

public sealed record OutboxLease(Guid EventId, Guid LeaseId, string Payload, int Attempts);

public sealed class Outbox(NpgsqlDataSource source, BankingTelemetry telemetry)
{
    public const int MaximumAttempts = 8;
    public static int BackoffSeconds(int attempts) => Math.Min(300, 5 * (1 << Math.Clamp(attempts - 1, 0, 6)));

    public async Task<OutboxLease?> ClaimAsync(CancellationToken token)
    {
        var lease = Guid.NewGuid();
        await using var command = source.CreateCommand("""
            UPDATE banking_payment.outbox SET lease_id=@lease,lease_until=now()+interval '30 seconds',attempts=attempts+1
            WHERE event_id=(SELECT event_id FROM banking_payment.outbox
                WHERE state='pending' AND next_attempt_at<=now() AND (lease_until IS NULL OR lease_until<now())
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING event_id,payload,attempts
            """);
        command.Parameters.AddWithValue("lease", lease);
        await using var reader = await command.ExecuteReaderAsync(token);
        return await reader.ReadAsync(token) ? new(reader.GetGuid(0), lease, reader.GetString(1), reader.GetInt32(2)) : null;
    }

    public async Task CompleteAsync(OutboxLease lease, bool sent, CancellationToken token)
    {
        await using var command = source.CreateCommand("""
            UPDATE banking_payment.outbox SET state=@state,
                next_attempt_at=now()+make_interval(secs=>@delay),lease_id=NULL,lease_until=NULL,
                sent_at=CASE WHEN @sent THEN now() ELSE sent_at END
            WHERE event_id=@id AND lease_id=@lease AND state='pending'
            """);
        command.Parameters.AddWithValue("state", sent ? "sent" : lease.Attempts >= MaximumAttempts ? "dead" : "pending");
        command.Parameters.AddWithValue("delay", BackoffSeconds(lease.Attempts));
        command.Parameters.AddWithValue("sent", sent);
        command.Parameters.AddWithValue("id", lease.EventId);
        command.Parameters.AddWithValue("lease", lease.LeaseId);
        if (await command.ExecuteNonQueryAsync(token) != 1)
            throw new InvalidOperationException("Outbox lease was lost; delivery may be duplicated.");
        if (sent) telemetry.Published.Inc();
        else telemetry.Retries.WithLabels("outbox").Inc();
    }

    public static PaymentCompleted Parse(string payload)
    {
        var completed = JsonSerializer.Deserialize<PaymentCompleted>(payload, PostgresPaymentJournal.Json);
        if (completed is null || completed.SchemaVersion != 1 || completed.EventType != "PaymentCompleted" ||
            completed.EventId == Guid.Empty || completed.EventId != completed.PaymentId || completed.Amount <= 0 ||
            completed.Amount > 1000000 || decimal.Round(completed.Amount, 2) != completed.Amount ||
            completed.Currency is not { Length: 3 } || !completed.Currency.All(c => c is >= 'A' and <= 'Z') ||
            completed.OccurredAt == default || completed.OccurredAt.Offset != TimeSpan.Zero)
            throw new JsonException("Unsupported or invalid PaymentCompleted event.");
        return completed;
    }

    public async Task<bool> ConsumeAsync(string payload, CancellationToken token)
    {
        var completed = Parse(payload);
        var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(payload)));
        await using var connection = await source.OpenConnectionAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(token);
        await using var exists = new NpgsqlCommand("SELECT count(*) FROM banking_payment.payments WHERE payment_id=@id AND amount=@amount AND currency=@currency", connection, transaction);
        exists.Parameters.AddWithValue("id", completed.PaymentId);
        exists.Parameters.AddWithValue("amount", completed.Amount);
        exists.Parameters.AddWithValue("currency", completed.Currency);
        if (Convert.ToInt64(await exists.ExecuteScalarAsync(token)) != 1)
            throw new InvalidOperationException("Event does not match a recorded synthetic payment.");
        await using var insert = new NpgsqlCommand("""
            INSERT INTO banking_payment.processed_events(event_id,payment_id,payload_sha256)
            VALUES(@event,@payment,@hash) ON CONFLICT(event_id) DO NOTHING
            """, connection, transaction);
        insert.Parameters.AddWithValue("event", completed.EventId);
        insert.Parameters.AddWithValue("payment", completed.PaymentId);
        insert.Parameters.AddWithValue("hash", hash);
        var fresh = await insert.ExecuteNonQueryAsync(token) == 1;
        if (!fresh)
        {
            await using var previous = new NpgsqlCommand("SELECT payload_sha256 FROM banking_payment.processed_events WHERE event_id=@id", connection, transaction);
            previous.Parameters.AddWithValue("id", completed.EventId);
            if (await previous.ExecuteScalarAsync(token) as string != hash)
                throw new InvalidOperationException("Conflicting event ID.");
        }
        await transaction.CommitAsync(token);
        if (fresh) telemetry.Received.Inc();
        else telemetry.Duplicates.Inc();
        return fresh;
    }

    public async Task ObserveAsync(CancellationToken token)
    {
        await using var command = source.CreateCommand("""
            SELECT count(*) FILTER(WHERE state='pending'),count(*) FILTER(WHERE state='dead'),
                COALESCE(extract(epoch FROM now()-min(created_at) FILTER(WHERE state='pending')),0)::double precision
            FROM banking_payment.outbox
            """);
        await using var reader = await command.ExecuteReaderAsync(token);
        await reader.ReadAsync(token);
        telemetry.OutboxPending.Set(reader.GetInt64(0));
        telemetry.OutboxDead.Set(reader.GetInt64(1));
        telemetry.OldestOutboxSeconds.Set(reader.GetDouble(2));
    }
}
