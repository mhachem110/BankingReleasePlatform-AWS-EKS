using Payment.Api;
using Banking.Platform;
using Npgsql;
using Amazon.SQS;

var migrate = args.Contains("--migrate", StringComparer.Ordinal);
var builder = WebApplication.CreateBuilder(args.Where(arg => arg != "--migrate").ToArray());
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole(options => options.IncludeScopes = true);
var databaseEnabled = Database.Enabled(builder.Configuration);
NpgsqlDataSource? database = databaseEnabled ? Database.Create(builder.Configuration, builder.Environment) : null;
if (migrate)
{
    if (database is null) throw new InvalidOperationException("Migration requires Postgres mode.");
    await using (database) await Database.MigrateAsync(database, typeof(Program).Assembly, "banking_payment");
    return;
}
builder.Services.AddSingleton<BankingTelemetry>();
if (database is not null)
{
    builder.Services.AddSingleton(database);
    builder.Services.AddSingleton<IPaymentJournal, PostgresPaymentJournal>();
    builder.Services.AddSingleton<Outbox>();
}
else builder.Services.AddSingleton<IPaymentJournal, MemoryPaymentJournal>();
if (builder.Configuration.GetValue<bool>("Messaging:Enabled"))
{
    if (database is null) throw new InvalidOperationException("Messaging requires a durable Postgres outbox.");
    builder.Services.AddSingleton(MessagingSettings.Read(builder.Configuration, builder.Environment));
    builder.Services.AddSingleton<IAmazonSQS>(_ => MessagingSettings.Client(builder.Configuration, builder.Environment));
    builder.Services.AddHostedService<SqsWorker>();
}
builder.Services.AddProblemDetails();
builder.Services.AddHealthChecks();
builder.Services.Configure<Microsoft.AspNetCore.Routing.RouteHandlerOptions>(options => options.ThrowOnBadRequest = false);
builder.Services.AddScoped<PaymentProcessor>();
var baseUrl = builder.Configuration["AccountApi:BaseUrl"] ?? "http://localhost:5101/";
if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var accountUri) || accountUri.Scheme is not ("http" or "https") ||
    !string.IsNullOrEmpty(accountUri.UserInfo) || !string.IsNullOrEmpty(accountUri.Query) || !string.IsNullOrEmpty(accountUri.Fragment))
    throw new InvalidOperationException("AccountApi:BaseUrl must be an absolute HTTP(S) URL without credentials, query, or fragment.");
builder.Services.AddHttpClient<IAccountClient, AccountClient>(client =>
{
    client.BaseAddress = new Uri(accountUri.AbsoluteUri.TrimEnd('/') + "/");
    client.Timeout = TimeSpan.FromSeconds(3);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });
var app = builder.Build();
app.UseExceptionHandler();
var telemetry = app.Services.GetRequiredService<BankingTelemetry>();
telemetry.StorageReady.Set(database is null ? 1 : 0);
telemetry.MessagingEnabled.Set(builder.Configuration.GetValue<bool>("Messaging:Enabled") ? 1 : 0);
telemetry.Use(app);
// Process health only: dependency failure is reported by payments, not by liveness restarts.
app.MapHealthChecks("/health");
app.MapGet("/ready", async (CancellationToken token) =>
{
    var ready = await Database.ReadyAsync(database, "banking_payment", token);
    telemetry.StorageReady.Set(ready ? 1 : 0);
    return ready ? Results.Ok(new { status = "ready" }) : Results.StatusCode(503);
});
app.MapGet("/api/payments/{id}", async (string id, IPaymentJournal journal, CancellationToken token) =>
{
    if (!Guid.TryParseExact(id, "N", out var paymentId)) return Results.BadRequest(new { code = "invalid_payment_id" });
    try
    {
        var payment = await journal.FindAsync(paymentId, token);
        return payment is null ? Results.NotFound() : Results.Ok(payment);
    }
    catch (Exception exception) when (exception is NpgsqlException or TimeoutException)
    {
        return Results.StatusCode(503);
    }
});
app.MapPost("/api/payments", async (PaymentRequest request, HttpContext context, PaymentProcessor processor, CancellationToken cancellationToken) =>
{
    var key = context.Request.Headers["Idempotency-Key"].ToString();
    if (context.Request.Headers["Idempotency-Key"].Count > 1) return Results.BadRequest(new { code = "invalid_idempotency_key" });
    if (!string.IsNullOrEmpty(key) && (key.Length > 64 || !key.All(c => char.IsAsciiLetterOrDigit(c) || c == '-')))
        return Results.BadRequest(new { code = "invalid_idempotency_key" });
    var outcome = await processor.ProcessAsync(request, cancellationToken, string.IsNullOrEmpty(key) ? Guid.NewGuid().ToString("N") : key);
    return Results.Json(outcome.Result, statusCode: outcome.StatusCode);
});
app.Run();

public partial class Program;
