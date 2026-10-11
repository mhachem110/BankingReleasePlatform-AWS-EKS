using Account.Api;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddProblemDetails();
builder.Services.AddHealthChecks();
builder.Services.Configure<Microsoft.AspNetCore.Routing.RouteHandlerOptions>(options => options.ThrowOnBadRequest = false);
builder.Services.AddSingleton<IAccountRepository, SampleAccountRepository>();
builder.Services.AddScoped<AccountValidator>();
var app = builder.Build();
app.UseExceptionHandler();

app.MapHealthChecks("/health");
app.MapGet("/api/accounts", (IAccountRepository repository) => Results.Ok(repository.GetAll()));
app.MapGet("/api/accounts/{id}", (string id, IAccountRepository repository) =>
    repository.GetById(id) is { } account
        ? Results.Ok(account)
        : Results.NotFound(new { code = "account_not_found", message = "The sample account does not exist." }));
app.MapPost("/api/accounts/{id}/validate", (string id, ValidationRequest request, AccountValidator validator) =>
{
    if (!ValidationRules.IsValid(request))
        return Results.BadRequest(new { code = "invalid_request", message = "Amount must be positive, at most 1000000, with at most two decimal places. Currency must be three uppercase letters." });
    var result = validator.Validate(id, request);
    return result.Code == "account_not_found" ? Results.NotFound(result) : Results.Ok(result);
});
app.Run();

public partial class Program;
