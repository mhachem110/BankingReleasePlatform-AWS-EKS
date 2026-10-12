using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Banking.Platform;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Payment.Api;
using Xunit;

namespace Payment.Api.Tests;

public sealed class DataAndOperationsTests
{
    [Fact]
    public async Task ReplayingCommittedPaymentDoesNotNeedAccountDependency()
    {
        var dependency = new CountingAccount();
        var journal = new MemoryPaymentJournal();
        var processor = new PaymentProcessor(dependency, journal, new BankingTelemetry());
        var request = new PaymentRequest("ACC1001", 25m, "USD");
        var first = await processor.ProcessAsync(request, default, "same-key");
        dependency.Available = false;
        var second = await processor.ProcessAsync(request, default, "same-key");
        Assert.Equal(first.Result.PaymentId, second.Result.PaymentId);
        Assert.Equal(200, second.StatusCode);
        Assert.Equal(1, dependency.Calls);
        var conflict = await processor.ProcessAsync(request with { Amount = 26m }, default, "same-key");
        Assert.Equal(409, conflict.StatusCode);
    }

    [Fact]
    public async Task PaymentCanBeRetrievedAndMetricsUseRouteTemplates()
    {
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
            builder.ConfigureServices(services => Microsoft.Extensions.DependencyInjection.ServiceCollectionServiceExtensions.AddSingleton<IAccountClient>(services, new CountingAccount())));
        var client = factory.CreateClient();
        var response = await client.PostAsJsonAsync("/api/payments", new PaymentRequest("ACC1001", 25m, "USD"));
        var result = (await response.Content.ReadFromJsonAsync<PaymentResult>())!;
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/api/payments/" + result.PaymentId)).StatusCode);
        var metrics = await client.GetStringAsync("/metrics");
        Assert.Contains("banking_http_request_duration_seconds_bucket", metrics);
        Assert.Contains("route=\"/api/payments/{id}\"", metrics);
        Assert.DoesNotContain(result.PaymentId!, metrics);
        Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/ready")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await client.GetAsync("/api/payments/not-an-id")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await client.GetAsync("/api/payments/" + Guid.NewGuid().ToString("N"))).StatusCode);
    }

    [Theory]
    [InlineData("invalid key")]
    [InlineData("bad/key")]
    [InlineData("key,another-key")]
    public async Task InvalidIdempotencyHeaderCannotReachDependency(string key)
    {
        using var factory = new WebApplicationFactory<Program>();
        var client = factory.CreateClient();
        client.DefaultRequestHeaders.Add("Idempotency-Key", key);
        Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/api/payments", new PaymentRequest("ACC1001", 25m, "USD"))).StatusCode);
    }

    [Theory]
    [InlineData(0, 5)]
    [InlineData(1, 5)]
    [InlineData(2, 10)]
    [InlineData(8, 300)]
    [InlineData(100, 300)]
    public void RetryBackoffIsBounded(int attempt, int expected) => Assert.Equal(expected, Outbox.BackoffSeconds(attempt));

    [Fact]
    public void EventContractRejectsUnknownVersionMismatchAndInvalidAmounts()
    {
        var id = Guid.NewGuid();
        var valid = new PaymentCompleted(id, 1, "PaymentCompleted", id, 25m, "USD", DateTimeOffset.UtcNow);
        Assert.Equal(valid, Outbox.Parse(JsonSerializer.Serialize(valid, PostgresPaymentJournal.Json)));
        foreach (var invalid in new[] { valid with { SchemaVersion = 2 }, valid with { EventId = Guid.NewGuid() },
                     valid with { Currency = "usd" }, valid with { Amount = 1.001m }, valid with { OccurredAt = default } })
            Assert.Throws<JsonException>(() => Outbox.Parse(JsonSerializer.Serialize(invalid, PostgresPaymentJournal.Json)));
        Assert.Throws<JsonException>(() => Outbox.Parse("null"));
        Assert.Throws<JsonException>(() => Outbox.Parse("{}"));
        Assert.Throws<JsonException>(() => Outbox.Parse(JsonSerializer.Serialize(valid, PostgresPaymentJournal.Json).TrimEnd('}') + ",\"unexpected\":true}"));
    }

    [Theory]
    [InlineData("Production", false)]
    [InlineData("Production", true)]
    [InlineData("Development", false)]
    public void DatabaseRejectsUnverifiedTlsOutsideExplicitLocalFixture(string environment, bool allow)
    {
        var config = Config(new() { ["ConnectionStrings:Banking"] = "Host=localhost;Database=banking;SSL Mode=Disable", ["Persistence:AllowLocalUnencrypted"] = allow.ToString() });
        Assert.Throws<InvalidOperationException>(() => Database.Create(config, new TestEnvironment(environment)));
    }

    [Fact]
    public void DatabaseAllowsVerifyFullWithoutOpeningConnection()
    {
        using var source = Database.Create(Config(new() { ["ConnectionStrings:Banking"] = "Host=approved.example;Database=banking;SSL Mode=VerifyFull" }), new TestEnvironment("Production"));
        Assert.NotNull(source);
    }

    [Theory]
    [InlineData("https://sqs.us-east-2.amazonaws.com/866934333672/banking-dev-payments.fifo")]
    [InlineData("https://sqs.us-east-1.amazonaws.com/866934333672/banking-dev-payments")]
    [InlineData("https://sqs.us-east-2.amazonaws.com/123456789012/banking-dev-payments")]
    [InlineData("http://sqs.us-east-2.amazonaws.com/866934333672/banking-dev-payments")]
    public void QueueContractRejectsWrongScope(string queue)
    {
        Assert.Throws<InvalidOperationException>(() => MessagingSettings.Read(Config(new()
        {
            ["Messaging:ExpectedAccountId"] = "866934333672",
            ["Messaging:QueueUrl"] = queue,
            ["Messaging:DeadLetterQueueUrl"] = "https://sqs.us-east-2.amazonaws.com/866934333672/banking-dev-dead"
        }), new TestEnvironment("Production")));
    }

    [Theory]
    [InlineData("Production", "http://localhost:4566/")]
    [InlineData("Development", "https://outside.example/")]
    [InlineData("Development", "http://outside.example/")]
    public void LocalSqsOverrideCannotEscapeDevelopmentFixture(string environment, string endpoint) =>
        Assert.Throws<InvalidOperationException>(() => MessagingSettings.Client(Config(new() { ["Messaging:LocalEndpoint"] = endpoint }), new TestEnvironment(environment)));

    private static IConfiguration Config(Dictionary<string, string?> values) => new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    private sealed class CountingAccount : IAccountClient
    {
        public bool Available { get; set; } = true;
        public int Calls { get; private set; }
        public Task<AccountValidation> ValidateAsync(PaymentRequest request, CancellationToken cancellationToken)
        {
            Calls++;
            if (!Available) throw new HttpRequestException("Fixture unavailable.");
            return Task.FromResult(new AccountValidation(request.AccountId!, true, 1500m, "USD", "valid", "Synthetic decision."));
        }
    }
    private sealed class TestEnvironment(string name) : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = name;
        public string ApplicationName { get; set; } = "fixture";
        public string ContentRootPath { get; set; } = ".";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
