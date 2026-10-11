param([int]$AccountPort = 5101, [int]$PaymentPort = 5102)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($AccountPort -eq $PaymentPort) { throw 'Choose different ports for the two APIs.' }
foreach ($port in @($AccountPort, $PaymentPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is in use. Stop the local Compose project or choose different ports."
    }
}
Push-Location $projectRoot
$processes = @()
try {
    dotnet build BankingReleasePlatform.sln -c Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Build failed. Run dotnet restore --locked-mode first.' }
    $logs = Join-Path $projectRoot 'artifacts/local'
    $null = New-Item -ItemType Directory -Path $logs -Force
    $dotnetPath = (Get-Command dotnet -ErrorAction Stop).Source
    $accountDll = Join-Path $projectRoot 'apps/Account.Api/bin/Release/net10.0/Account.Api.dll'
    $paymentDll = Join-Path $projectRoot 'apps/Payment.Api/bin/Release/net10.0/Payment.Api.dll'
    $processes += Start-Process -FilePath $dotnetPath -ArgumentList @(('"' + $accountDll + '"'), '--urls', "http://127.0.0.1:$AccountPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/account.stdout.log" -RedirectStandardError "$logs/account.stderr.log"
    $processes += Start-Process -FilePath $dotnetPath -ArgumentList @(('"' + $paymentDll + '"'), '--urls', "http://127.0.0.1:$PaymentPort", '--AccountApi:BaseUrl', "http://127.0.0.1:$AccountPort/") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/payment.stdout.log" -RedirectStandardError "$logs/payment.stderr.log"
    & "$PSScriptRoot/smoke-test.ps1" -AccountBaseUrl "http://127.0.0.1:$AccountPort" -PaymentBaseUrl "http://127.0.0.1:$PaymentPort"
} finally {
    foreach ($process in $processes) {
        if (!$process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    }
    Pop-Location
}
