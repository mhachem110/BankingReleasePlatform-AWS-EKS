using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Logging;
using Prometheus;
using System.Diagnostics;

namespace Banking.Platform;

public sealed class BankingTelemetry
{
    public CollectorRegistry Registry { get; } = Metrics.NewCustomRegistry();
    private readonly Counter _requests;
    private readonly Histogram _duration;
    public Counter PaymentDecisions { get; }
    public Counter Published { get; }
    public Counter Retries { get; }
    public Counter Received { get; }
    public Counter Duplicates { get; }
    public Gauge OutboxPending { get; }
    public Gauge OutboxDead { get; }
    public Gauge OldestOutboxSeconds { get; }
    public Gauge StorageReady { get; }
    public Gauge MessagingEnabled { get; }
    public Gauge WorkerHealthy { get; }
    private readonly Gauge _memory;
    private readonly Counter _cpu;

    public BankingTelemetry()
    {
        var factory = Metrics.WithCustomRegistry(Registry);
        _requests = factory.CreateCounter("banking_http_requests_total", "Completed HTTP requests.", "route", "method", "status");
        _duration = factory.CreateHistogram("banking_http_request_duration_seconds", "HTTP latency in seconds.",
            new HistogramConfiguration { LabelNames = ["route", "method"], Buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5] });
        PaymentDecisions = factory.CreateCounter("banking_payment_decisions_total", "Payment decisions.", "code");
        Published = factory.CreateCounter("banking_events_published_total", "Successful outbox sends.");
        Retries = factory.CreateCounter("banking_event_retries_total", "Event retries.", "stage");
        Received = factory.CreateCounter("banking_events_processed_total", "Committed consumer events.");
        Duplicates = factory.CreateCounter("banking_event_duplicates_total", "Duplicate consumer events.");
        OutboxPending = factory.CreateGauge("banking_outbox_pending", "Pending outbox rows.");
        OutboxDead = factory.CreateGauge("banking_outbox_dead", "Outbox rows needing operator recovery.");
        OldestOutboxSeconds = factory.CreateGauge("banking_outbox_oldest_seconds", "Age of the oldest pending event.");
        StorageReady = factory.CreateGauge("banking_storage_ready", "Last readiness check: 1 ready, 0 unavailable.");
        MessagingEnabled = factory.CreateGauge("banking_messaging_enabled", "Messaging explicitly configured: 1 enabled, 0 disabled.");
        WorkerHealthy = factory.CreateGauge("banking_event_worker_healthy", "Most recent event-worker cycle: 1 healthy, 0 failed or not started.");
        _memory = factory.CreateGauge("banking_process_working_set_bytes", "Process working set, not Fargate capacity.");
        _cpu = factory.CreateCounter("banking_process_cpu_seconds_total", "Total process CPU seconds, not Pod allocation.");
    }

    public void Use(WebApplication app)
    {
        app.Use(async (context, next) =>
        {
            if (context.Request.Path == "/metrics") { await next(context); return; }
            var started = Stopwatch.GetTimestamp();
            var failed = false;
            try { await next(context); }
            catch { failed = true; throw; }
            finally
            {
                var route = (context.GetEndpoint() as RouteEndpoint)?.RoutePattern.RawText ?? "unmatched";
                var method = context.Request.Method is "GET" or "POST" ? context.Request.Method : "other";
                var seconds = Stopwatch.GetElapsedTime(started).TotalSeconds;
                var status = failed ? 500 : context.Response.StatusCode;
                _requests.WithLabels(route, method, status.ToString()).Inc();
                _duration.WithLabels(route, method).Observe(seconds);
                // Route templates avoid account/payment IDs, query strings, request bodies and credentials.
                app.Logger.LogInformation("HTTP {Route} {Method} {Status} {ElapsedMilliseconds}ms TraceId={TraceId}",
                    route, method, status, Math.Round(seconds * 1000, 2), context.TraceIdentifier);
            }
        });
        app.MapGet("/metrics", async context =>
        {
            using var process = Process.GetCurrentProcess();
            _memory.Set(process.WorkingSet64);
            lock (_cpu) _cpu.Inc(Math.Max(0, process.TotalProcessorTime.TotalSeconds - _cpu.Value));
            context.Response.ContentType = "text/plain; version=0.0.4; charset=utf-8";
            await Registry.CollectAndExportAsTextAsync(context.Response.Body, context.RequestAborted);
        });
    }
}
