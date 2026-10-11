param(
    [string]$AccountBaseUrl = 'http://localhost:5101',
    [string]$PaymentBaseUrl = 'http://localhost:5102',
    [switch]$ExpectAccountUnavailable
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(6)
$checks = 0

function Invoke-ApiCheck {
    param([string]$Method, [string]$Url, [int]$ExpectedStatus, [string]$Body = '', [string]$ExpectedCode = '')
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Url)
    if ($Body) { $request.Content = [System.Net.Http.StringContent]::new($Body, [Text.Encoding]::UTF8, 'application/json') }
    try {
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        try {
            $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if ([int]$response.StatusCode -ne $ExpectedStatus) { throw "$Method $Url expected $ExpectedStatus, got $([int]$response.StatusCode): $content" }
            if ($ExpectedCode -and ($content | ConvertFrom-Json).code -ne $ExpectedCode) { throw "Unexpected business result: $content" }
            $script:checks++
            Write-Host "PASS $Method $Url -> $ExpectedStatus $ExpectedCode"
            return $content
        } finally { $response.Dispose() }
    } finally { $request.Dispose() }
}

function Wait-Healthy {
    param([string]$Url)
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = $client.GetAsync($Url).GetAwaiter().GetResult()
            try { if ($response.IsSuccessStatusCode) { return } } finally { $response.Dispose() }
        } catch { if ($attempt -eq 29) { throw } }
        Start-Sleep -Milliseconds 500
    }
    throw "Health endpoint did not become ready: $Url"
}

try {
    Wait-Healthy "$PaymentBaseUrl/health"
    $null = Invoke-ApiCheck GET "$PaymentBaseUrl/health" 200
    if ($ExpectAccountUnavailable) {
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 503 '{"accountId":"ACC1001","amount":25,"currency":"USD"}' 'account_service_unavailable'
    } else {
        Wait-Healthy "$AccountBaseUrl/health"
        $null = Invoke-ApiCheck GET "$AccountBaseUrl/health" 200
        $accounts = (Invoke-ApiCheck GET "$AccountBaseUrl/api/accounts" 200) | ConvertFrom-Json
        if ($accounts.Count -ne 4) { throw 'Expected four sample accounts.' }
        $before = (Invoke-ApiCheck GET "$AccountBaseUrl/api/accounts/ACC1001" 200) | ConvertFrom-Json
        $null = Invoke-ApiCheck GET "$AccountBaseUrl/api/accounts/UNKNOWN" 404 '' 'account_not_found'
        $null = Invoke-ApiCheck POST "$AccountBaseUrl/api/accounts/ACC1001/validate" 200 '{"amount":25,"currency":"USD"}' 'valid'
        $approved = (Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 200 '{"accountId":"ACC1001","amount":25,"currency":"USD"}' 'payment_approved') | ConvertFrom-Json
        if ($approved.status -ne 'simulated' -or !$approved.paymentId) { throw 'Expected a simulated payment reference.' }
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 200 '{"accountId":"ACC1002","amount":75,"currency":"USD"}' 'payment_approved'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 422 '{"accountId":"ACC1002","amount":100,"currency":"USD"}' 'insufficient_funds'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 422 '{"accountId":"ACC1003","amount":10,"currency":"USD"}' 'account_inactive'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 422 '{"accountId":"ACC1004","amount":1,"currency":"USD"}' 'insufficient_funds'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 404 '{"accountId":"UNKNOWN","amount":10,"currency":"USD"}' 'account_not_found'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 422 '{"accountId":"ACC1001","amount":10,"currency":"EUR"}' 'currency_mismatch'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 400 '{"accountId":"ACC1001","amount":0,"currency":"USD"}' 'invalid_request'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 400 '{"accountId":"ACC1001","amount":1.001,"currency":"USD"}' 'invalid_request'
        $null = Invoke-ApiCheck POST "$PaymentBaseUrl/api/payments" 400 '{'
        $after = (Invoke-ApiCheck GET "$AccountBaseUrl/api/accounts/ACC1001" 200) | ConvertFrom-Json
        if ($before.balance -ne $after.balance) { throw 'A simulation must not change the account balance.' }
    }
    Write-Host "Smoke checks passed: $checks"
} finally { $client.Dispose() }
