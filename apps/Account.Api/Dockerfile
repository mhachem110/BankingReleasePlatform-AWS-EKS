FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props global.json ./
COPY apps/Account.Api/Account.Api.csproj apps/Account.Api/packages.lock.json apps/Account.Api/
RUN dotnet restore apps/Account.Api/Account.Api.csproj --locked-mode
COPY apps/Account.Api/ apps/Account.Api/
RUN dotnet publish apps/Account.Api/Account.Api.csproj -c Release --no-restore -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
COPY --from=build /app/publish .
USER $APP_UID
ENTRYPOINT ["dotnet", "Account.Api.dll"]
