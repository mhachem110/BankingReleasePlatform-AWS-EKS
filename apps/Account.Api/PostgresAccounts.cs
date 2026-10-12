using Npgsql;

namespace Account.Api;

public sealed class PostgresAccountRepository(NpgsqlDataSource source) : IAccountRepository
{
    public IReadOnlyCollection<CustomerAccount> GetAll()
    {
        using var command = source.CreateCommand("SELECT id,customer_name,balance,currency,active FROM banking_account.accounts ORDER BY id");
        using var reader = command.ExecuteReader();
        var accounts = new List<CustomerAccount>();
        while (reader.Read()) accounts.Add(Read(reader));
        return accounts.AsReadOnly();
    }

    public CustomerAccount? GetById(string id)
    {
        using var command = source.CreateCommand("SELECT id,customer_name,balance,currency,active FROM banking_account.accounts WHERE id=@id");
        command.Parameters.AddWithValue("id", id);
        using var reader = command.ExecuteReader();
        return reader.Read() ? Read(reader) : null;
    }

    private static CustomerAccount Read(NpgsqlDataReader reader) =>
        new(reader.GetString(0), reader.GetString(1), reader.GetDecimal(2), reader.GetString(3), reader.GetBoolean(4));
}
