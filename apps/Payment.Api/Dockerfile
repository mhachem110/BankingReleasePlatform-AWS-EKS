FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props global.json ./
COPY apps/Payment.Api/Payment.Api.csproj apps/Payment.Api/packages.lock.json apps/Payment.Api/
RUN dotnet restore apps/Payment.Api/Payment.Api.csproj --locked-mode
COPY apps/Payment.Api/ apps/Payment.Api/
RUN dotnet publish apps/Payment.Api/Payment.Api.csproj -c Release --no-restore -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
COPY --from=build /app/publish .
USER $APP_UID
ENTRYPOINT ["dotnet", "Payment.Api.dll"]
