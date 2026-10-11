using System.Net;
using System.Text.Json;

namespace Payment.Api;

public sealed record PaymentRequest(string? AccountId, decimal Amount, string? Currency);
public sealed record PaymentResult(string Status, string Code, string Message, string? PaymentId = null);
public sealed record PaymentOutcome(int StatusCode, PaymentResult Result);
public sealed record AccountValidation(string AccountId, bool IsValid, decimal? Balance, string? Currency, string Code, string Message);

public interface IAccountClient
{
    Task<AccountValidation> ValidateAsync(PaymentRequest request, CancellationToken cancellationToken);
}

public sealed class AccountServiceException : Exception
{
    public AccountServiceException() : base("Account API returned an unexpected response.") { }
}

public sealed class AccountClient(HttpClient httpClient) : IAccountClient
{
    public async Task<AccountValidation> ValidateAsync(PaymentRequest request, CancellationToken cancellationToken)
    {
        var id = Uri.EscapeDataString(request.AccountId!);
        using var response = await httpClient.PostAsJsonAsync($"api/accounts/{id}/validate",
            new { request.Amount, request.Currency }, cancellationToken);
        if (response.StatusCode != HttpStatusCode.OK && response.StatusCode != HttpStatusCode.NotFound)
            throw new AccountServiceException();
        var result = await response.Content.ReadFromJsonAsync<AccountValidation>(cancellationToken);
        if (result is null || result.AccountId != request.AccountId ||
            string.IsNullOrWhiteSpace(result.Code) || string.IsNullOrWhiteSpace(result.Message))
            throw new AccountServiceException();

        // Fail closed if the dependency's status, decision, or balance contradicts its contract.
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            if (result.IsValid || result.Code != "account_not_found")
                throw new AccountServiceException();
        }
        else if (result.Currency is null || result.Balance is null ||
                 (result.IsValid && (result.Code != "valid" || result.Currency != request.Currency || result.Balance < request.Amount)) ||
                 (!result.IsValid && result.Code is not ("account_inactive" or "currency_mismatch" or "insufficient_funds")))
        {
            throw new AccountServiceException();
        }
        return result;
    }
}

public sealed class PaymentProcessor(IAccountClient accountClient)
{
    public async Task<PaymentOutcome> ProcessAsync(PaymentRequest request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.AccountId) || request.AccountId.Length > 64 ||
            !request.AccountId.All(c => char.IsAsciiLetterOrDigit(c) || c == '-') ||
            request.Amount <= 0 || request.Amount > 1_000_000m || decimal.Round(request.Amount, 2) != request.Amount ||
            request.Currency is not { Length: 3 } || !request.Currency.All(c => c is >= 'A' and <= 'Z'))
        {
            return new(400, new("rejected", "invalid_request", "Use an account ID of at most 64 ASCII letters/digits/hyphens, a positive amount up to 1000000 with at most two decimal places, and a three-letter uppercase currency."));
        }

        try
        {
            var validation = await accountClient.ValidateAsync(request, cancellationToken);
            if (!validation.IsValid)
                return new(validation.Code == "account_not_found" ? 404 : 422,
                    new("rejected", validation.Code, validation.Message));
            return new(200, new("simulated", "payment_approved", "Simulation approved. No funds were moved or balances changed.", Guid.NewGuid().ToString("N")));
        }
        catch (Exception exception) when (exception is HttpRequestException or JsonException or AccountServiceException ||
            (exception is OperationCanceledException && !cancellationToken.IsCancellationRequested))
        {
            return new(503, new("unavailable", "account_service_unavailable", "Account validation is temporarily unavailable. No payment was approved."));
        }
    }
}
