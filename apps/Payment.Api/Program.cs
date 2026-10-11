using Payment.Api;

var builder = WebApplication.CreateBuilder(args);
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
// Process health only: dependency failure is reported by payments, not by liveness restarts.
app.MapHealthChecks("/health");
app.MapPost("/api/payments", async (PaymentRequest request, PaymentProcessor processor, CancellationToken cancellationToken) =>
{
    var outcome = await processor.ProcessAsync(request, cancellationToken);
    return Results.Json(outcome.Result, statusCode: outcome.StatusCode);
});
app.Run();

public partial class Program;
