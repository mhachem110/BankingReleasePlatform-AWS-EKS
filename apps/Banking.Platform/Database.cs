using System.Reflection;
using System.Security.Cryptography;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Npgsql;

namespace Banking.Platform;

public static class Database
{
    public static bool Enabled(IConfiguration configuration)
    {
        var mode = configuration["Persistence:Mode"] ?? "Memory";
        return mode switch
        {
            "Memory" => false,
            "Postgres" => true,
            _ => throw new InvalidOperationException("Persistence:Mode must be Memory or Postgres.")
        };
    }

    public static NpgsqlDataSource Create(IConfiguration configuration, IHostEnvironment environment)
    {
        var file = configuration["Persistence:ConnectionStringFile"];
        var connectionString = string.IsNullOrWhiteSpace(file)
            ? configuration["ConnectionStrings:Banking"] : File.ReadAllText(file).Trim();
        if (string.IsNullOrWhiteSpace(connectionString))
            throw new InvalidOperationException("Supply database configuration through an approved secret.");
        var settings = new NpgsqlConnectionStringBuilder(connectionString);
        if (settings.SslMode != SslMode.VerifyFull &&
            !(environment.IsDevelopment() && configuration.GetValue<bool>("Persistence:AllowLocalUnencrypted")))
            throw new InvalidOperationException("PostgreSQL requires VerifyFull TLS outside explicit local development.");
        settings.IncludeErrorDetail = false;
        settings.LogParameters = false;
        settings.Timeout = 5;
        settings.CommandTimeout = 10;
        settings.MaxPoolSize = 10;
        return NpgsqlDataSource.Create(settings.ConnectionString);
    }

    // Called only by the explicit --migrate command with operator/migration credentials.
    // The normal API startup never executes DDL or seeds/reset data.
    public static async Task MigrateAsync(NpgsqlDataSource source, Assembly assembly, string schema,
        CancellationToken cancellationToken = default)
    {
        if (schema is not ("banking_account" or "banking_payment"))
            throw new ArgumentException("Unknown migration schema.", nameof(schema));
        await using var connection = await source.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var setup = new NpgsqlCommand($"""
            SELECT pg_advisory_xact_lock(@lock);
            CREATE SCHEMA IF NOT EXISTS {schema};
            CREATE TABLE IF NOT EXISTS {schema}.schema_migrations
                (version text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now());
            """, connection, transaction))
        {
            setup.Parameters.AddWithValue("lock", schema == "banking_account" ? 8181001L : 8181002L);
            await setup.ExecuteNonQueryAsync(cancellationToken);
        }
        foreach (var name in assembly.GetManifestResourceNames().Where(n => n.Contains(".Migrations.") && n.EndsWith(".sql", StringComparison.Ordinal)).Order())
        {
            using var stream = assembly.GetManifestResourceStream(name)!;
            using var reader = new StreamReader(stream);
            // Git checkout line endings differ between Windows and Linux image builds.
            // Canonical LF keeps the same migration checksum across those builds.
            var sql = (await reader.ReadToEndAsync(cancellationToken)).Replace("\r\n", "\n", StringComparison.Ordinal);
            var hash = Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(sql)));
            await using var check = new NpgsqlCommand($"SELECT sha256 FROM {schema}.schema_migrations WHERE version=@version", connection, transaction);
            check.Parameters.AddWithValue("version", name);
            var existing = await check.ExecuteScalarAsync(cancellationToken) as string;
            if (existing is not null)
            {
                if (existing != hash)
                    throw new InvalidOperationException("An applied migration was changed. Add a forward migration.");
                continue;
            }
            await using var apply = new NpgsqlCommand(sql, connection, transaction);
            await apply.ExecuteNonQueryAsync(cancellationToken);
            await using var record = new NpgsqlCommand($"INSERT INTO {schema}.schema_migrations(version,sha256) VALUES(@version,@hash)", connection, transaction);
            record.Parameters.AddWithValue("version", name);
            record.Parameters.AddWithValue("hash", hash);
            await record.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
    }

    public static async Task<bool> ReadyAsync(NpgsqlDataSource? source, string schema, CancellationToken token)
    {
        if (source is null) return true;
        if (schema is not ("banking_account" or "banking_payment")) return false;
        try
        {
            await using var command = source.CreateCommand($"SELECT count(*) FROM {schema}.schema_migrations");
            return Convert.ToInt64(await command.ExecuteScalarAsync(token)) > 0;
        }
        catch (Exception exception) when (exception is NpgsqlException or TimeoutException)
        {
            return false;
        }
    }
}
