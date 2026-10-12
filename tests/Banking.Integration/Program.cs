using System.Text.Json;
using Account.Api;
using Amazon.Runtime;
using Amazon.SQS;
using Amazon.SQS.Model;
using Banking.Platform;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;
using Payment.Api;

namespace Banking.Integration;

internal static class Program
{
    private static int _checks;
    private static void Check(bool condition, string label)
    {
        if (!condition) throw new InvalidOperationException("FAIL: " + label);
        _checks++;
        Console.WriteLine("PASS: " + label);
    }

    private static async Task Scalar(NpgsqlDataSource db, string sql, long expected, string label)
    {
        await using var command = db.CreateCommand(sql);
        Check(Convert.ToInt64(await command.ExecuteScalarAsync()) == expected, label);
    }

    private static async Task Execute(NpgsqlDataSource db, string sql)
    {
        await using var command = db.CreateCommand(sql);
        await command.ExecuteNonQueryAsync();
    }

    public static async Task Main()
    {
        var connection = Environment.GetEnvironmentVariable("BANKING_TEST_POSTGRES") ?? throw new InvalidOperationException("Start the disposable offline fixture first.");
        var endpoint = Environment.GetEnvironmentVariable("BANKING_TEST_SQS") ?? throw new InvalidOperationException("Local SQS fixture is required.");
        var dbConfig = new NpgsqlConnectionStringBuilder(connection);
        if (dbConfig.Host is not ("localhost" or "127.0.0.1") || !Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || !uri.IsLoopback)
            throw new InvalidOperationException("Integration fixtures must be loopback-only, never AWS/shared databases.");
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        var token = timeout.Token;
        await using var db = NpgsqlDataSource.Create(connection);
        var accountAssembly = typeof(PostgresAccountRepository).Assembly;
        var paymentAssembly = typeof(PostgresPaymentJournal).Assembly;
        await Database.MigrateAsync(db, accountAssembly, "banking_account", token);
        await Database.MigrateAsync(db, paymentAssembly, "banking_payment", token);
        await Database.MigrateAsync(db, accountAssembly, "banking_account", token);
        await Database.MigrateAsync(db, paymentAssembly, "banking_payment", token);
        await Scalar(db, "SELECT count(*) FROM banking_account.schema_migrations", 1, "Account migration repeats without duplicate versions");
        await Scalar(db, "SELECT count(*) FROM banking_payment.schema_migrations", 1, "Payment migration repeats without duplicate versions");
        Check(new PostgresAccountRepository(db).GetAll().Count == 4, "Four synthetic PostgreSQL accounts");
        await Execute(db, "UPDATE banking_account.accounts SET balance=1499.50 WHERE id='ACC1001'");
        await Database.MigrateAsync(db, accountAssembly, "banking_account", token);
        Check(new PostgresAccountRepository(db).GetById("ACC1001")!.Balance == 1499.50m, "Migration rerun preserves existing data");

        var journal = new PostgresPaymentJournal(db);
        var request = new PaymentRequest("ACC1001", 25m, "USD");
        var payments = await Task.WhenAll(Enumerable.Range(0, 16).Select(_ => journal.SaveAsync(request, "concurrent-replay", token)));
        Check(payments.Select(p => p.PaymentId).Distinct().Count() == 1, "16 concurrent idempotent requests produce one payment");
        await Scalar(db, "SELECT count(*) FROM banking_payment.outbox", 1, "One transactionally committed outbox event");
        try { await journal.SaveAsync(request with { Amount = 26m }, "concurrent-replay", token); throw new InvalidOperationException("Conflict accepted."); }
        catch (IdempotencyConflictException) { Check(true, "Changed request with reused key is rejected"); }
        await using (var restarted = NpgsqlDataSource.Create(connection))
            Check(await new PostgresPaymentJournal(restarted).FindAsync(payments[0].PaymentId, token) is not null, "Payment survives connection-pool restart");

        await Execute(db, """
            CREATE FUNCTION banking_payment.reject_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture failure'; END $$;
            CREATE TRIGGER reject_outbox BEFORE INSERT ON banking_payment.outbox FOR EACH ROW EXECUTE FUNCTION banking_payment.reject_outbox();
            """);
        try { await journal.SaveAsync(request, "transaction-rollback", token); throw new InvalidOperationException("Failure accepted."); }
        catch (PostgresException) { Check(true, "Outbox insertion failure propagates"); }
        finally { await Execute(db, "DROP TRIGGER reject_outbox ON banking_payment.outbox; DROP FUNCTION banking_payment.reject_outbox();"); }
        await Scalar(db, "SELECT count(*) FROM banking_payment.payments WHERE idempotency_key='transaction-rollback'", 0, "Outbox failure rolls back the payment too");

        using var sqs = new AmazonSQSClient(new BasicAWSCredentials("local" + Guid.NewGuid().ToString("N"), Guid.NewGuid().ToString("N")), new AmazonSQSConfig
        { ServiceURL = endpoint, AuthenticationRegion = "us-east-2", Timeout = TimeSpan.FromSeconds(5), MaxErrorRetry = 0 });
        var dead = await sqs.CreateQueueAsync(new CreateQueueRequest { QueueName = "banking-local-dead", Attributes = new() { ["MessageRetentionPeriod"] = "1209600" } }, token);
        var deadAttributes = await sqs.GetQueueAttributesAsync(dead.QueueUrl, ["QueueArn"], token);
        var queue = await sqs.CreateQueueAsync(new CreateQueueRequest
        {
            QueueName = "banking-local-payments",
            Attributes = new()
            {
                ["VisibilityTimeout"] = "30",
                ["MessageRetentionPeriod"] = "86400",
                ["RedrivePolicy"] = JsonSerializer.Serialize(new { deadLetterTargetArn = deadAttributes.Attributes["QueueArn"], maxReceiveCount = 3 })
            }
        }, token);
        var telemetry = new BankingTelemetry();
        var outbox = new Outbox(db, telemetry);
        var settings = new MessagingSettings(queue.QueueUrl, dead.QueueUrl);
        var worker = new SqsWorker(sqs, settings, outbox, telemetry, NullLogger<SqsWorker>.Instance);
        await worker.VerifyQueuesAsync(token);
        Check(true, "Real SQS-compatible source/DLQ attributes verified");
        var lease = await outbox.ClaimAsync(token) ?? throw new InvalidOperationException("Expected outbox.");
        Check(await outbox.ClaimAsync(token) is null, "Active lease excludes a second dispatcher");
        // Simulate successful send followed by process crash before mark-sent.
        await sqs.SendMessageAsync(queue.QueueUrl, lease.Payload, token);
        await Execute(db, "UPDATE banking_payment.outbox SET lease_until=now()-interval '1 second'");
        await worker.DispatchOneAsync(token);
        await worker.ReceiveOnceAsync(token);
        await worker.ReceiveOnceAsync(token);
        await Scalar(db, "SELECT count(*) FROM banking_payment.processed_events", 1, "Crash after send is deduplicated by durable receipt");
        Check(telemetry.Duplicates.Value == 1, "Duplicate-delivery metric records the replay");
        await Scalar(db, "SELECT count(*) FROM banking_payment.outbox WHERE state='sent'", 1, "Outbox acknowledged only after successful delivery");

        var retryPayment = await journal.SaveAsync(request, "retry-dead-test", token);
        var badWorker = new SqsWorker(sqs, settings with { QueueUrl = endpoint.TrimEnd('/') + "/000000000000/queue-does-not-exist" }, outbox, telemetry, NullLogger<SqsWorker>.Instance);
        for (var i = 0; i < Outbox.MaximumAttempts; i++)
        {
            await badWorker.DispatchOneAsync(token);
            await Execute(db, "UPDATE banking_payment.outbox SET next_attempt_at=now() WHERE state='pending'");
        }
        await Scalar(db, "SELECT count(*) FROM banking_payment.outbox WHERE state='dead'", 1, "Eight real send failures retain a dead outbox row");
        Check(Outbox.BackoffSeconds(1) == 5 && Outbox.BackoffSeconds(8) == 300, "Retry schedule is bounded");
        await outbox.ObserveAsync(token);
        Check(telemetry.OutboxDead.Value == 1, "Dead-outbox gauge exposes operator recovery work");

        await sqs.SendMessageAsync(queue.QueueUrl, "{malformed-event", token);
        await worker.ReceiveOnceAsync(token);
        var poisoned = false;
        for (var i = 0; i < 15 && !poisoned; i++)
        {
            var invisible = await sqs.ReceiveMessageAsync(new ReceiveMessageRequest { QueueUrl = queue.QueueUrl, VisibilityTimeout = 0, MaxNumberOfMessages = 10, WaitTimeSeconds = 1 }, token);
            foreach (var message in invisible.Messages ?? []) await sqs.ChangeMessageVisibilityAsync(queue.QueueUrl, message.ReceiptHandle, 0, token);
            // Only the disposable local emulator is accelerated; production backoff stays unchanged.
            var deadResponse = await sqs.ReceiveMessageAsync(new ReceiveMessageRequest { QueueUrl = dead.QueueUrl, WaitTimeSeconds = 1 }, token);
            poisoned = (deadResponse.Messages ?? []).Any(m => m.Body == "{malformed-event");
        }
        Check(poisoned, "Poison event is redriven into the local DLQ");
        await Scalar(db, "SELECT count(*) FROM banking_payment.processed_events", 1, "Poison event never commits a consumer receipt");

        await using var migrationHash = db.CreateCommand("SELECT sha256 FROM banking_account.schema_migrations");
        var originalHash = (string)(await migrationHash.ExecuteScalarAsync())!;
        await Execute(db, "UPDATE banking_account.schema_migrations SET sha256='modified'");
        try { await Database.MigrateAsync(db, accountAssembly, "banking_account", token); throw new InvalidOperationException("Changed migration accepted."); }
        catch (InvalidOperationException exception) when (exception.Message.Contains("applied migration", StringComparison.Ordinal))
        { Check(true, "Migration checksum mismatch fails closed"); }
        await using var restoreHash = db.CreateCommand("UPDATE banking_account.schema_migrations SET sha256=@hash");
        restoreHash.Parameters.AddWithValue("hash", originalHash);
        await restoreHash.ExecuteNonQueryAsync(token);
        await Execute(db, """
            CREATE ROLE banking_fixture_runtime NOLOGIN;
            GRANT USAGE ON SCHEMA banking_account,banking_payment TO banking_fixture_runtime;
            GRANT SELECT ON banking_account.accounts,banking_account.schema_migrations,banking_payment.schema_migrations TO banking_fixture_runtime;
            GRANT SELECT,INSERT,UPDATE ON banking_payment.payments,banking_payment.outbox,banking_payment.processed_events TO banking_fixture_runtime;
            """);
        var runtimeConfig = new NpgsqlConnectionStringBuilder(connection) { Options = "-c role=banking_fixture_runtime" };
        await using (var runtime = NpgsqlDataSource.Create(runtimeConfig.ConnectionString))
        {
            var recorded = await new PostgresPaymentJournal(runtime).SaveAsync(request, "runtime-data-permissions", token);
            Check(await new PostgresPaymentJournal(runtime).FindAsync(recorded.PaymentId, token) is not null, "Runtime role can persist/read without table ownership");
            try
            {
                await Execute(runtime, "ALTER TABLE banking_payment.payments ADD COLUMN unauthorized text");
                throw new InvalidOperationException("Runtime DDL accepted.");
            }
            catch (PostgresException exception) when (exception.SqlState == PostgresErrorCodes.InsufficientPrivilege)
            { Check(true, "Runtime role cannot change the schema"); }
        }
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            checks = _checks,
            result = "passed",
            scope = "local PostgreSQL and SQS-compatible emulator",
            liveAws = false,
            queuePath = new Uri(queue.QueueUrl).AbsolutePath,
            deadLetterPath = new Uri(dead.QueueUrl).AbsolutePath
        }));
    }
}
