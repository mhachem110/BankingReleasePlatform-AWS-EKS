using System.Net;
using System.Net.Http.Json;
using System.Text;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Payment.Api;
using Xunit;

namespace Payment.Api.Tests;

public sealed class PaymentEndpointsTests
{
    [Fact]
    public async Task HealthIsHealthy()
    {
        using var factory = new WebApplicationFactory<Program>();
        Assert.Equal("Healthy", await factory.CreateClient().GetStringAsync("/health"));
    }

    [Theory]
    [InlineData(true, "valid", HttpStatusCode.OK, "payment_approved")]
    [InlineData(false, "account_inactive", HttpStatusCode.UnprocessableEntity, "account_inactive")]
    [InlineData(false, "insufficient_funds", HttpStatusCode.UnprocessableEntity, "insufficient_funds")]
    [InlineData(false, "currency_mismatch", HttpStatusCode.UnprocessableEntity, "currency_mismatch")]
    [InlineData(false, "account_not_found", HttpStatusCode.NotFound, "account_not_found")]
    public async Task MapsAccountDecision(bool valid, string code, HttpStatusCode expectedStatus, string expectedCode)
    {
        using var factory = Factory(new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage(
            code == "account_not_found" ? HttpStatusCode.NotFound : HttpStatusCode.OK)
        {
            Content = JsonContent.Create(new AccountValidation("ACC1001", valid, 1500.50m, "USD", code, "Sample decision."))
        })));
        var response = await factory.CreateClient().PostAsJsonAsync("/api/payments", new PaymentRequest("ACC1001", 25m, "USD"));
        Assert.Equal(expectedStatus, response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<PaymentResult>();
        Assert.Equal(expectedCode, result!.Code);
        Assert.Equal(valid, result.PaymentId is not null);
    }

    [Fact]
    public async Task CallsAccountUsingCorrectHttpContract()
    {
        using var factory = Factory(new StubHandler(async (request, token) =>
        {
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("/api/accounts/ACC1002/validate", request.RequestUri!.AbsolutePath);
            var json = await request.Content!.ReadAsStringAsync(token);
            Assert.Contains("\"amount\":25", json);
            Assert.Contains("\"currency\":\"USD\"", json);
            return new(HttpStatusCode.OK) { Content = JsonContent.Create(new AccountValidation("ACC1002", true, 75m, "USD", "valid", "Valid.")) };
        }));
        var response = await factory.CreateClient().PostAsJsonAsync("/api/payments", new PaymentRequest("ACC1002", 25m, "USD"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Theory]
    [InlineData(null, 25, "USD")]
    [InlineData("", 25, "USD")]
    [InlineData(" ", 25, "USD")]
    [InlineData("ACC/1001", 25, "USD")]
    [InlineData("ACC1001", 0, "USD")]
    [InlineData("ACC1001", -1, "USD")]
    [InlineData("ACC1001", 1.001, "USD")]
    [InlineData("ACC1001", 1000001, "USD")]
    [InlineData("ACC1001", 25, null)]
    [InlineData("ACC1001", 25, "usd")]
    public async Task RejectsInvalidInputWithoutCallingDependency(string? id, double amount, string? currency)
    {
        using var factory = Factory(new StubHandler((_, _) => throw new InvalidOperationException("Dependency must not be called.")));
        var response = await factory.CreateClient().PostAsJsonAsync("/api/payments", new PaymentRequest(id, (decimal)amount, currency));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Theory]
    [InlineData("{", HttpStatusCode.OK)]
    [InlineData("null", HttpStatusCode.OK)]
    [InlineData("{}", HttpStatusCode.OK)]
    [InlineData("{}", HttpStatusCode.InternalServerError)]
    [InlineData("{}", HttpStatusCode.Redirect)]
    [InlineData("{\"accountId\":\"ACC1001\",\"isValid\":true,\"balance\":1,\"currency\":\"USD\",\"code\":\"valid\",\"message\":\"ok\"}", HttpStatusCode.OK)]
    [InlineData("{\"accountId\":\"OTHER\",\"isValid\":true,\"balance\":100,\"currency\":\"USD\",\"code\":\"valid\",\"message\":\"ok\"}", HttpStatusCode.OK)]
    [InlineData("{\"accountId\":\"ACC1001\",\"isValid\":true,\"balance\":100,\"currency\":\"USD\",\"code\":\"valid\",\"message\":\"ok\"}", HttpStatusCode.NotFound)]
    public async Task RejectsUnexpectedUpstreamResponse(string json, HttpStatusCode upstreamStatus)
    {
        using var factory = Factory(new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage(upstreamStatus)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        })));
        await AssertUnavailable(factory.CreateClient());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HandlesNetworkFailureAndTimeout(bool timeout)
    {
        using var factory = Factory(new StubHandler((_, _) => timeout
            ? Task.FromException<HttpResponseMessage>(new TaskCanceledException("Timeout"))
            : Task.FromException<HttpResponseMessage>(new HttpRequestException("Connection refused"))));
        await AssertUnavailable(factory.CreateClient());
    }

    [Theory]
    [InlineData("{")]
    [InlineData("null")]
    [InlineData("[]")]
    [InlineData("{\"accountId\":\"ACC1001\",\"amount\":\"not-a-number\",\"currency\":\"USD\"}")]
    public async Task RejectsMalformedJson(string json)
    {
        using var factory = new WebApplicationFactory<Program>();
        var response = await factory.CreateClient().PostAsync("/api/payments", new StringContent(json, Encoding.UTF8, "application/json"));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    private static async Task AssertUnavailable(HttpClient client)
    {
        var response = await client.PostAsJsonAsync("/api/payments", new PaymentRequest("ACC1001", 25m, "USD"));
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<PaymentResult>();
        Assert.Equal("account_service_unavailable", result!.Code);
        Assert.Null(result.PaymentId);
    }

    private static WebApplicationFactory<Program> Factory(HttpMessageHandler handler) =>
        new WebApplicationFactory<Program>().WithWebHostBuilder(builder => builder.ConfigureServices(services =>
            services.AddHttpClient<IAccountClient, AccountClient>().ConfigurePrimaryHttpMessageHandler(() => handler)));

    private sealed class StubHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
    }
}
