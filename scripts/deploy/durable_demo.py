"""Synthetic payment assertions for an already authorized Kubernetes demonstration."""
import json
import urllib.error
import urllib.request
import uuid
from smoke import request, wait_health


def post(base, body, key, expected=200):
    req = urllib.request.Request(base + "/api/payments", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Idempotency-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            status, value = response.status, json.load(response)
    except urllib.error.HTTPError as error:
        status, value = error.code, json.load(error)
    if status != expected:
        raise AssertionError(f"Durable payment: expected {expected}, got {status}")
    return value


def create(base):
    wait_health(base)
    request(base, "/ready")
    body = {"accountId": "ACC1001", "amount": 25, "currency": "USD"}
    key = "kube-demo-" + uuid.uuid4().hex
    result = post(base, body, key)
    if result.get("code") != "payment_approved":
        raise AssertionError("Synthetic payment was not approved")
    return {"key": key, "body": body, "paymentId": result["paymentId"]}


def verify(base, proof):
    wait_health(base)
    request(base, "/ready")
    payment_id = proof["paymentId"]
    stored = request(base, "/api/payments/" + payment_id)
    if (uuid.UUID(stored["paymentId"]) != uuid.UUID(payment_id) or
            stored["accountId"] != proof["body"]["accountId"] or
            stored["amount"] != proof["body"]["amount"] or
            stored["currency"] != proof["body"]["currency"]):
        raise AssertionError("Recovered payment does not match its durable record")
    replay = post(base, proof["body"], proof["key"])
    if replay.get("paymentId") != payment_id:
        raise AssertionError("Recovery duplicated the idempotent payment")
    post(base, {**proof["body"], "amount": 26}, proof["key"], expected=409)
