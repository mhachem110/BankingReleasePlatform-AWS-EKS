using System.Text.Json;
using Amazon;
using Amazon.Runtime;
using Amazon.SQS;
using Amazon.SQS.Model;
using Banking.Platform;

namespace Payment.Api;

public sealed record MessagingSettings(string QueueUrl, string DeadLetterQueueUrl)
{
    public static IAmazonSQS Client(IConfiguration configuration, IHostEnvironment environment)
    {
        var config = new AmazonSQSConfig { RegionEndpoint = RegionEndpoint.USEast2, Timeout = TimeSpan.FromSeconds(10), MaxErrorRetry = 1 };
        var local = configuration["Messaging:LocalEndpoint"];
        if (!string.IsNullOrWhiteSpace(local))
        {
            if (!environment.IsDevelopment() || !Uri.TryCreate(local, UriKind.Absolute, out var uri) ||
                uri.Scheme != "http" || !(uri.IsLoopback || uri.Host is "sqs" or "elasticmq") ||
                !string.IsNullOrEmpty(uri.UserInfo) || uri.AbsolutePath != "/")
                throw new InvalidOperationException("SQS endpoint override is restricted to explicit local development.");
            config.ServiceURL = local;
            config.AuthenticationRegion = "us-east-2";
            // Ephemeral emulator-only signatures. These are not AWS access keys and are never persisted.
            return new AmazonSQSClient(new BasicAWSCredentials("local" + Guid.NewGuid().ToString("N"), Guid.NewGuid().ToString("N")), config);
        }
        // Default AWS credential chain: approved IRSA/temporary identity, never static keys in code.
        return new AmazonSQSClient(config);
    }

    public static MessagingSettings Read(IConfiguration configuration, IHostEnvironment environment)
    {
        var local = !string.IsNullOrWhiteSpace(configuration["Messaging:LocalEndpoint"]);
        var account = configuration["Messaging:ExpectedAccountId"];
        var queues = new[] { configuration["Messaging:QueueUrl"], configuration["Messaging:DeadLetterQueueUrl"] };
        foreach (var queue in queues)
        {
            if (!Uri.TryCreate(queue, UriKind.Absolute, out var uri) || !string.IsNullOrEmpty(uri.UserInfo) ||
                !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) || queue!.EndsWith(".fifo", StringComparison.Ordinal))
                throw new InvalidOperationException("Supply distinct approved standard SQS queue URLs.");
            if (local)
            {
                if (!environment.IsDevelopment() || !Uri.TryCreate(configuration["Messaging:LocalEndpoint"], UriKind.Absolute, out var endpoint) ||
                    uri.Scheme != "http" || uri.Authority != endpoint.Authority)
                    throw new InvalidOperationException("Local queues must use the explicit local endpoint.");
            }
            else if (account != "866934333672" || uri.Scheme != "https" || uri.Host != "sqs.us-east-2.amazonaws.com" ||
                     !uri.AbsolutePath.StartsWith("/" + account + "/banking-dev-", StringComparison.Ordinal))
                throw new InvalidOperationException("Queue must be an approved Banking/dev queue in the expected account and Region.");
        }
        if (queues[0] == queues[1]) throw new InvalidOperationException("Source queue and DLQ must be distinct.");
        return new(queues[0]!, queues[1]!);
    }
}

public sealed class SqsWorker(IAmazonSQS sqs, MessagingSettings settings, Outbox outbox,
    BankingTelemetry telemetry, ILogger<SqsWorker> logger) : BackgroundService
{
    public async Task VerifyQueuesAsync(CancellationToken token)
    {
        var source = await sqs.GetQueueAttributesAsync(new GetQueueAttributesRequest { QueueUrl = settings.QueueUrl, AttributeNames = ["All"] }, token);
        var dead = await sqs.GetQueueAttributesAsync(new GetQueueAttributesRequest { QueueUrl = settings.DeadLetterQueueUrl, AttributeNames = ["All"] }, token);
        using var policy = JsonDocument.Parse(source.Attributes["RedrivePolicy"]);
        var maxReceive = int.Parse(policy.RootElement.GetProperty("maxReceiveCount").ToString());
        if (policy.RootElement.GetProperty("deadLetterTargetArn").GetString() != dead.Attributes["QueueArn"] ||
            maxReceive is < 3 or > 10 || int.Parse(source.Attributes["VisibilityTimeout"]) < 30 ||
            int.Parse(dead.Attributes["MessageRetentionPeriod"]) < int.Parse(source.Attributes["MessageRetentionPeriod"]))
            throw new InvalidOperationException("SQS requires the approved DLQ, bounded receive count, visibility and retention.");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        DateTimeOffset? verifiedAt = null;
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (verifiedAt is null || DateTimeOffset.UtcNow - verifiedAt > TimeSpan.FromMinutes(1))
                {
                    await VerifyQueuesAsync(stoppingToken);
                    verifiedAt = DateTimeOffset.UtcNow;
                }
                await DispatchOneAsync(stoppingToken);
                await ReceiveOnceAsync(stoppingToken);
                await outbox.ObserveAsync(stoppingToken);
                telemetry.WorkerHealthy.Set(1);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception exception)
            {
                telemetry.Retries.WithLabels("worker").Inc();
                telemetry.WorkerHealthy.Set(0);
                logger.LogWarning("Event worker will retry. FailureType={FailureType}", exception.GetType().Name);
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
            }
        }
    }

    public async Task DispatchOneAsync(CancellationToken token)
    {
        var lease = await outbox.ClaimAsync(token);
        if (lease is null) return;
        try
        {
            await sqs.SendMessageAsync(new SendMessageRequest { QueueUrl = settings.QueueUrl, MessageBody = lease.Payload }, token);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch (Exception exception)
        {
            await outbox.CompleteAsync(lease, false, token);
            logger.LogWarning("Outbox delivery retry. Attempt={Attempt} FailureType={FailureType}", lease.Attempts, exception.GetType().Name);
            return;
        }
        // A crash here can deliver twice. Stable event IDs and the consumer's durable inbox handle it.
        await outbox.CompleteAsync(lease, true, token);
    }

    public async Task ReceiveOnceAsync(CancellationToken token)
    {
        var response = await sqs.ReceiveMessageAsync(new ReceiveMessageRequest
        {
            QueueUrl = settings.QueueUrl,
            MaxNumberOfMessages = 1,
            WaitTimeSeconds = 2,
            MessageSystemAttributeNames = ["ApproximateReceiveCount"]
        }, token);
        foreach (var message in response.Messages ?? [])
        {
            try
            {
                await outbox.ConsumeAsync(message.Body, token);
                // Delete only after committing the receipt. A lost delete is safe to retry.
                await sqs.DeleteMessageAsync(settings.QueueUrl, message.ReceiptHandle, token);
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
            catch (Exception exception)
            {
                var attempts = int.TryParse(message.Attributes?.GetValueOrDefault("ApproximateReceiveCount"), out var count) ? count : 1;
                telemetry.Retries.WithLabels("consumer").Inc();
                logger.LogWarning("Consumer left message for retry/redrive. Attempt={Attempt} FailureType={FailureType}", attempts, exception.GetType().Name);
                await sqs.ChangeMessageVisibilityAsync(settings.QueueUrl, message.ReceiptHandle, Outbox.BackoffSeconds(attempts), token);
            }
        }
    }
}
