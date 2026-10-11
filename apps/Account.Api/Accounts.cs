namespace Account.Api;

public sealed record CustomerAccount(string Id, string CustomerName, decimal Balance, string Currency, bool IsActive);
public sealed record ValidationRequest(decimal Amount, string? Currency);
public sealed record AccountValidation(string AccountId, bool IsValid, decimal? Balance, string? Currency, string Code, string Message);

// Replace this implementation with a database repository in Phase 6.
public interface IAccountRepository
{
    IReadOnlyCollection<CustomerAccount> GetAll();
    CustomerAccount? GetById(string id);
}

public sealed class SampleAccountRepository : IAccountRepository
{
    private readonly CustomerAccount[] _accounts =
    [
        new("ACC1001", "Alex Example", 1500.50m, "USD", true),
        new("ACC1002", "Sam Sample", 75.00m, "USD", true),
        new("ACC1003", "Taylor Fiction", 400.00m, "USD", false),
        new("ACC1004", "Jordan Demo", 0.00m, "USD", true)
    ];

    public IReadOnlyCollection<CustomerAccount> GetAll() => Array.AsReadOnly(_accounts);
    public CustomerAccount? GetById(string id) => _accounts.FirstOrDefault(account => account.Id == id);
}

public sealed class AccountValidator(IAccountRepository repository)
{
    public AccountValidation Validate(string id, ValidationRequest request)
    {
        var account = repository.GetById(id);
        if (account is null)
            return new(id, false, null, null, "account_not_found", "The sample account does not exist.");
        if (!account.IsActive)
            return Result(false, "account_inactive", "The sample account is inactive.");
        if (request.Currency != account.Currency)
            return Result(false, "currency_mismatch", "The request currency does not match the account currency.");
        if (account.Balance < request.Amount)
            return Result(false, "insufficient_funds", "The sample balance is insufficient.");
        return Result(true, "valid", "The sample account can cover this simulated payment.");

        AccountValidation Result(bool valid, string code, string message) =>
            new(id, valid, account.Balance, account.Currency, code, message);
    }
}

public static class ValidationRules
{
    public static bool IsValid(ValidationRequest request) =>
        request.Amount > 0 && request.Amount <= 1_000_000m &&
        decimal.Round(request.Amount, 2) == request.Amount &&
        request.Currency is { Length: 3 } && request.Currency.All(c => c is >= 'A' and <= 'Z');
}
