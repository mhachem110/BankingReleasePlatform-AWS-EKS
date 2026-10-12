"""Real HTTP contract checks; Payment calls Account through its configured DNS."""
import argparse
import json
import time
import urllib.error
import urllib.request

def request(base, path, status=200, body=None, code=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            actual, content = response.status, response.read()
    except urllib.error.HTTPError as error:
        actual, content = error.code, error.read()
    if actual != status:
        raise AssertionError(f"{path}: expected {status}, got {actual}: {content!r}")
    value = json.loads(content) if content and content[:1] in (b"{", b"[") else None
    if code and (value or {}).get("code") != code:
        raise AssertionError(f"{path}: wrong business result: {value}")
    return value

def wait_health(base):
    for _ in range(60):
        try:
            request(base, "/health")
            return
        except (OSError, AssertionError):
            time.sleep(1)
    raise AssertionError("Health timeout: " + base)

def smoke(account, payment, unavailable=False):
    wait_health(payment)
    if unavailable:
        request(payment, "/api/payments", 503,
                {"accountId": "ACC1001", "amount": 25, "currency": "USD"},
                "account_service_unavailable")
        return 2
    wait_health(account)
    accounts = request(account, "/api/accounts")
    assert len(accounts) == 4, "Expected four fictional sample accounts"
    before = request(account, "/api/accounts/ACC1001")
    request(account, "/api/accounts/ACC1001/validate", body={"amount":25,"currency":"USD"}, code="valid")
    cases = [
        ("ACC1001", 25, "USD", 200, "payment_approved"),
        ("ACC1002", 75, "USD", 200, "payment_approved"),
        ("ACC1002", 100, "USD", 422, "insufficient_funds"),
        ("ACC1003", 10, "USD", 422, "account_inactive"),
        ("ACC1004", 1, "USD", 422, "insufficient_funds"),
        ("UNKNOWN", 10, "USD", 404, "account_not_found"),
        ("ACC1001", 10, "EUR", 422, "currency_mismatch"),
        ("ACC1001", 0, "USD", 400, "invalid_request"),
        ("ACC1001", 1.001, "USD", 400, "invalid_request"),
    ]
    for ident, amount, currency, status, code in cases:
        result = request(payment, "/api/payments", status,
                         {"accountId": ident, "amount": amount, "currency": currency}, code)
        if status == 200:
            assert result["status"] == "simulated" and result["paymentId"]
    after = request(account, "/api/accounts/ACC1001")
    assert before["balance"] == after["balance"], "Simulation changed balance"
    print("PASS: 15 HTTP checks including Payment-to-Account communication")
    return 15

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--account", default="http://127.0.0.1:18081")
    p.add_argument("--payment", default="http://127.0.0.1:18082")
    p.add_argument("--unavailable", action="store_true")
    a = p.parse_args()
    smoke(a.account, a.payment, a.unavailable)
