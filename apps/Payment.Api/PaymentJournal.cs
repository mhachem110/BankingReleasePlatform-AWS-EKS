using System.Collections.Concurrent;
using System.Text.Json;
using Npgsql;

namespace Payment.Api;

public sealed record StoredPayment(Guid PaymentId, string AccountId, decimal Amount, string Currency, DateTimeOffset CreatedAt);
public sealed record PaymentCompleted(Guid EventId, int SchemaVersion, string EventType, Guid PaymentId,
    decimal Amount, string Currency, DateTimeOffset OccurredAt);
public sealed class IdempotencyConflictException : Exception;
public interface IPaymentJournal
{
    Task<StoredPayment> SaveAsync(PaymentRequest request, string key, CancellationToken token);
    Task<StoredPayment?> FindAsync(Guid id, CancellationToken token);
    Task<StoredPayment?> FindByKeyAsync(string key, CancellationToken token);
}

public sealed class MemoryPaymentJournal : IPaymentJournal
{
    private readonly ConcurrentDictionary<string, StoredPayment> _payments = new();
    private readonly object _gate = new();
    public Task<StoredPayment> SaveAsync(PaymentRequest request, string key, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        lock (_gate)
        {
            if (_payments.TryGetValue(key, out var previous))
            {
                if (previous.AccountId != request.AccountId || previous.Amount != request.Amount || previous.Currency != request.Currency)
                    throw new IdempotencyConflictException();
                return Task.FromResult(previous);
            }
            if (_payments.Count >= 10000)
                throw new InvalidOperationException("Memory demonstration capacity exhausted.");
            var payment = new StoredPayment(Guid.NewGuid(), request.AccountId!, request.Amount, request.Currency!, DateTimeOffset.UtcNow);
            _payments[key] = payment;
            return Task.FromResult(payment);
        }
    }
    public Task<StoredPayment?> FindAsync(Guid id, CancellationToken token) =>
        Task.FromResult(_payments.Values.FirstOrDefault(p => p.PaymentId == id));
    public Task<StoredPayment?> FindByKeyAsync(string key, CancellationToken token) =>
        Task.FromResult(_payments.GetValueOrDefault(key));
}

public sealed class PostgresPaymentJournal(NpgsqlDataSource source) : IPaymentJournal
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow
    };

    public async Task<StoredPayment> SaveAsync(PaymentRequest request, string key, CancellationToken token)
    {
        await using var connection = await source.OpenConnectionAsync(token);
        await using var transaction = await connection.BeginTransactionAsync(token);
        var payment = new StoredPayment(Guid.NewGuid(), request.AccountId!, request.Amount, request.Currency!, DateTimeOffset.UtcNow);
        await using var insert = new NpgsqlCommand("""
            INSERT INTO banking_payment.payments(payment_id,idempotency_key,account_id,amount,currency,created_at)
            VALUES(@id,@key,@account,@amount,@currency,@created) ON CONFLICT(idempotency_key) DO NOTHING
            """, connection, transaction);
        insert.Parameters.AddWithValue("id", payment.PaymentId);
        insert.Parameters.AddWithValue("key", key);
        insert.Parameters.AddWithValue("account", payment.AccountId);
        insert.Parameters.AddWithValue("amount", payment.Amount);
        insert.Parameters.AddWithValue("currency", payment.Currency);
        insert.Parameters.AddWithValue("created", payment.CreatedAt);
        if (await insert.ExecuteNonQueryAsync(token) == 0)
        {
            await using var previous = new NpgsqlCommand("SELECT payment_id,account_id,amount,currency,created_at FROM banking_payment.payments WHERE idempotency_key=@key", connection, transaction);
            previous.Parameters.AddWithValue("key", key);
            await using var reader = await previous.ExecuteReaderAsync(token);
            if (!await reader.ReadAsync(token)) throw new InvalidOperationException("Idempotency record unavailable.");
            payment = Read(reader);
            if (payment.AccountId != request.AccountId || payment.Amount != request.Amount || payment.Currency != request.Currency)
                throw new IdempotencyConflictException();
            await reader.DisposeAsync();
        }
        else
        {
            var completed = new PaymentCompleted(payment.PaymentId, 1, "PaymentCompleted", payment.PaymentId,
                payment.Amount, payment.Currency, payment.CreatedAt);
            await using var outbox = new NpgsqlCommand("INSERT INTO banking_payment.outbox(event_id,payload) VALUES(@id,@payload)", connection, transaction);
            outbox.Parameters.AddWithValue("id", payment.PaymentId);
            outbox.Parameters.AddWithValue("payload", JsonSerializer.Serialize(completed, Json));
            await outbox.ExecuteNonQueryAsync(token);
        }
        await transaction.CommitAsync(token);
        return payment;
    }

    public async Task<StoredPayment?> FindAsync(Guid id, CancellationToken token)
    {
        await using var command = source.CreateCommand("SELECT payment_id,account_id,amount,currency,created_at FROM banking_payment.payments WHERE payment_id=@id");
        command.Parameters.AddWithValue("id", id);
        await using var reader = await command.ExecuteReaderAsync(token);
        return await reader.ReadAsync(token) ? Read(reader) : null;
    }

    public async Task<StoredPayment?> FindByKeyAsync(string key, CancellationToken token)
    {
        await using var command = source.CreateCommand("SELECT payment_id,account_id,amount,currency,created_at FROM banking_payment.payments WHERE idempotency_key=@key");
        command.Parameters.AddWithValue("key", key);
        await using var reader = await command.ExecuteReaderAsync(token);
        return await reader.ReadAsync(token) ? Read(reader) : null;
    }

    private static StoredPayment Read(NpgsqlDataReader reader) =>
        new(reader.GetGuid(0), reader.GetString(1), reader.GetDecimal(2), reader.GetString(3), reader.GetFieldValue<DateTimeOffset>(4));
}
