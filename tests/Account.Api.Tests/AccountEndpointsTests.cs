using System.Net;
using System.Net.Http.Json;
using Account.Api;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace Account.Api.Tests;

public sealed class AccountEndpointsTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;
    public AccountEndpointsTests(WebApplicationFactory<Program> factory) => _client = factory.CreateClient();

    [Fact]
    public async Task HealthIsHealthy() => Assert.Equal("Healthy", await _client.GetStringAsync("/health"));

    [Fact]
    public async Task ListsFictionalAccounts()
    {
        var accounts = await _client.GetFromJsonAsync<CustomerAccount[]>("/api/accounts");
        Assert.Equal(4, accounts!.Length);
        Assert.Contains(accounts, account => account.Id == "ACC1001" && account.Balance == 1500.50m);
    }

    [Fact]
    public async Task RetrievesBalanceAndActivity()
    {
        var account = await _client.GetFromJsonAsync<CustomerAccount>("/api/accounts/ACC1003");
        Assert.Equal(400m, account!.Balance);
        Assert.False(account.IsActive);
    }

    [Fact]
    public async Task UnknownAccountReturns404() => Assert.Equal(HttpStatusCode.NotFound,
        (await _client.GetAsync("/api/accounts/UNKNOWN")).StatusCode);

    [Theory]
    [InlineData("ACC1001", 25, "USD", true, "valid", HttpStatusCode.OK)]
    [InlineData("ACC1002", 75, "USD", true, "valid", HttpStatusCode.OK)]
    [InlineData("ACC1002", 76, "USD", false, "insufficient_funds", HttpStatusCode.OK)]
    [InlineData("ACC1003", 10, "USD", false, "account_inactive", HttpStatusCode.OK)]
    [InlineData("ACC1004", 1, "USD", false, "insufficient_funds", HttpStatusCode.OK)]
    [InlineData("ACC1001", 10, "EUR", false, "currency_mismatch", HttpStatusCode.OK)]
    [InlineData("UNKNOWN", 10, "USD", false, "account_not_found", HttpStatusCode.NotFound)]
    public async Task ValidatesAccount(string id, int amount, string currency, bool valid, string code, HttpStatusCode status)
    {
        var response = await _client.PostAsJsonAsync($"/api/accounts/{id}/validate", new ValidationRequest(amount, currency));
        Assert.Equal(status, response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<AccountValidation>();
        Assert.Equal(valid, result!.IsValid);
        Assert.Equal(code, result.Code);
    }

    [Theory]
    [InlineData(0, "USD")]
    [InlineData(-1, "USD")]
    [InlineData(1.001, "USD")]
    [InlineData(1000001, "USD")]
    [InlineData(1, "usd")]
    [InlineData(1, null)]
    public async Task RejectsInvalidValidationRequest(double amount, string? currency)
    {
        var response = await _client.PostAsJsonAsync("/api/accounts/ACC1001/validate", new ValidationRequest((decimal)amount, currency));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }
}
