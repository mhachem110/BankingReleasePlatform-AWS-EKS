using Account.Api;
using Banking.Platform;
using Npgsql;

var migrate = args.Contains("--migrate", StringComparer.Ordinal);
var builder = WebApplication.CreateBuilder(args.Where(arg => arg != "--migrate").ToArray());
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(options => options.IncludeScopes = true);
var databaseEnabled = Database.Enabled(builder.Configuration);
NpgsqlDataSource? database = databaseEnabled ? Database.Create(builder.Configuration, builder.Environment) : null;
if (migrate)
{
    if (database is null) throw new InvalidOperationException("Migration requires Postgres mode.");
    await using (database) await Database.MigrateAsync(database, typeof(Program).Assembly, "banking_account");
    return;
}
builder.Services.AddProblemDetails();
builder.Services.AddHealthChecks();
builder.Services.Configure<Microsoft.AspNetCore.Routing.RouteHandlerOptions>(options => options.ThrowOnBadRequest = false);
if (database is not null)
{
    builder.Services.AddSingleton(database);
    builder.Services.AddSingleton<IAccountRepository, PostgresAccountRepository>();
}
else builder.Services.AddSingleton<IAccountRepository, SampleAccountRepository>();
builder.Services.AddScoped<AccountValidator>();
builder.Services.AddSingleton<BankingTelemetry>();
var app = builder.Build();
app.UseExceptionHandler();
var telemetry = app.Services.GetRequiredService<BankingTelemetry>();
telemetry.StorageReady.Set(database is null ? 1 : 0);
telemetry.Use(app);
app.Use(async (context, next) =>
{
    try { await next(context); }
    catch (Exception exception) when (exception is NpgsqlException or TimeoutException)
    {
        app.Logger.LogWarning("Account storage unavailable. FailureType={FailureType}", exception.GetType().Name);
        context.Response.StatusCode = 503;
        await context.Response.WriteAsJsonAsync(new { code = "storage_unavailable", message = "Account storage is temporarily unavailable." });
    }
});

app.MapHealthChecks("/health");
app.MapGet("/ready", async (CancellationToken token) =>
{
    var ready = await Database.ReadyAsync(database, "banking_account", token);
    telemetry.StorageReady.Set(ready ? 1 : 0);
    return ready ? Results.Ok(new { status = "ready" }) : Results.StatusCode(503);
});
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
