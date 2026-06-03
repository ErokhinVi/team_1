"""Тесты блока retail.

retail — тонкий слой: своих данных нет, он зовёт backend и cib по HTTP.
Поэтому в тестах соседи «подменяются» (мокаются): мы не поднимаем настоящие
backend и cib, а перехватываем исходящие HTTP-вызовы и отдаём заранее
заданные ответы. Так мы проверяем именно поведение retail:
правильные ли запросы он шлёт соседям и правильно ли разбирает ответы.

Запуск (там, где установлены зависимости fastapi/httpx/pytest):
    cd retail && python -m pytest
"""
from __future__ import annotations

import json as _json
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Блок лежит в retail/src — добавим его в путь импорта.
SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import main as retail  # noqa: E402


# --------------------------------------------------------------------------
# Подмена соседей (backend и cib)
# --------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = _json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload

    def json(self):
        return self._payload


class Router:
    """Маршрутизатор фейковых ответов и журнал исходящих вызовов retail."""

    def __init__(self):
        self.routes = {}   # (METHOD, substring) -> [responses]
        self.calls = []    # список (method, url, json_body, params)

    def reset(self):
        self.routes = {}
        self.calls = []

    def add(self, method: str, match: str, status: int, payload):
        self.routes.setdefault((method, match), []).append((status, payload))

    def handle(self, method: str, url: str, json_body, params):
        self.calls.append((method, url, json_body, params))
        for (m, match), responses in self.routes.items():
            if m == method and match in url:
                status, payload = responses[0] if len(responses) == 1 else responses.pop(0)
                return FakeResponse(status, payload)
        raise AssertionError(f"Незаданный маршрут для {method} {url}")

    def last_body_to(self, match: str):
        """Тело последнего POST, ушедшего на URL, содержащий match."""
        for method, url, body, _params in reversed(self.calls):
            if method == "POST" and match in url:
                return body
        return None


ROUTER = Router()


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        return ROUTER.handle("GET", url, None, params)

    async def post(self, url, json=None):
        return ROUTER.handle("POST", url, json, None)


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    ROUTER.reset()
    monkeypatch.setattr(retail.httpx, "AsyncClient", FakeAsyncClient)
    yield
    ROUTER.reset()


@pytest.fixture
def client():
    return TestClient(retail.app)


# --------------------------------------------------------------------------
# Базовые ручки
# --------------------------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["block"] == "retail"


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<" in r.text  # отдаётся HTML страницы банка


def test_clients_proxies_to_backend(client):
    ROUTER.add("GET", "/clients", 200, {"total": 1, "items": [{"id": "c-1", "name": "Иван"}]})
    r = client.get("/clients?limit=10")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_transfer_proxies_to_backend(client):
    ROUTER.add("POST", "/api/transfer", 200,
               {"status": "ok", "amount_rub": 100, "new_balance_rub": 900})
    r = client.post("/api/transfer", json={"from_client_id": "c-1", "to": "c-2", "amount_rub": 100})
    assert r.status_code == 200
    assert r.json()["new_balance_rub"] == 900


# --------------------------------------------------------------------------
# Кредитная карта — регрессия на имя поля credit_limit_rub
# --------------------------------------------------------------------------
def test_credit_apply_approved_forwards_limit(client):
    # cib одобряет и присылает лимит в поле credit_limit_rub
    ROUTER.add("POST", "/credit-decision", 200,
               {"approved": True, "credit_limit_rub": 150000, "rate_pct": 21.0, "reason": "ок"})
    ROUTER.add("POST", "/credit-cards", 200,
               {"card_id": "card-1", "card_number": "5536****1234", "status": "approved"})
    r = client.post("/api/credit-apply", json={"customer_id": "c-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert body["limit"] == 150000
    assert body["rate_pct"] == 21.0
    # retail должен передать лимит в backend как credit_limit
    sent = ROUTER.last_body_to("/credit-cards")
    assert sent["credit_limit"] == 150000


def test_credit_apply_declined_does_not_create_card(client):
    ROUTER.add("POST", "/credit-decision", 200,
               {"approved": False, "reason": "просрочки в прошлом"})
    r = client.post("/api/credit-apply", json={"customer_id": "c-1"})
    assert r.status_code == 200
    assert r.json()["approved"] is False
    # карта не должна выпускаться
    assert ROUTER.last_body_to("/credit-cards") is None


def test_credit_apply_requires_customer_id(client):
    r = client.post("/api/credit-apply", json={})
    assert r.status_code == 400


def test_activate_card(client):
    ROUTER.add("POST", "/credit-cards/card-1/activate", 200, {"card_id": "card-1", "status": "active"})
    r = client.post("/api/credit-cards/card-1/activate")
    assert r.status_code == 200
    assert r.json()["status"] == "active"


# --------------------------------------------------------------------------
# Брокеридж
# --------------------------------------------------------------------------
def test_brokerage_stocks(client):
    ROUTER.add("GET", "/products/brokerage", 200,
               {"total": 1, "items": [{"ticker": "SBER", "company": "Сбер", "price_rub": 300}]})
    r = client.get("/api/brokerage/stocks")
    assert r.status_code == 200
    assert r.json()["items"][0]["ticker"] == "SBER"


def test_brokerage_account_autocreate_on_404(client):
    # первый GET → 404, затем POST создаёт счёт, затем GET → 200
    ROUTER.add("GET", "/brokerage/accounts/c-1", 404, {"detail": "нет счёта"})
    ROUTER.add("POST", "/brokerage/accounts", 200, {"account_id": "acc-1", "status": "open"})
    ROUTER.add("GET", "/brokerage/accounts/c-1", 200,
               {"account_id": "acc-1", "customer_id": "c-1", "balance_rub": 0, "status": "open"})
    r = client.get("/api/brokerage/account/c-1")
    assert r.status_code == 200
    assert r.json()["account_id"] == "acc-1"


def test_brokerage_order_requires_customer_id(client):
    r = client.post("/api/brokerage/orders", json={"ticker": "SBER", "quantity": 1, "direction": "buy"})
    assert r.status_code == 400
    # без customer_id запрос в backend уходить не должен
    assert ROUTER.last_body_to("/brokerage/orders") is None


def test_brokerage_order_ok(client):
    ROUTER.add("POST", "/brokerage/orders", 200,
               {"order_id": "o-1", "status": "filled", "ticker": "SBER",
                "direction": "buy", "total_rub": 300, "new_account_balance_rub": 700})
    r = client.post("/api/brokerage/orders",
                    json={"customer_id": "c-1", "ticker": "SBER", "quantity": 1, "direction": "buy"})
    assert r.status_code == 200
    assert r.json()["new_account_balance_rub"] == 700


# --------------------------------------------------------------------------
# Кредит (потребительский)
# --------------------------------------------------------------------------
def test_loan_decision_proxies_to_cib(client):
    ROUTER.add("POST", "/loan/decision", 200,
               {"approved": True, "amount_rub": 200000, "term_months": 24,
                "rate_pct": 19.5, "monthly_payment_rub": 10100})
    r = client.post("/api/loan/decision",
                    json={"customer_id": "c-1", "amount_rub": 200000, "term_months": 24})
    assert r.status_code == 200
    assert r.json()["monthly_payment_rub"] == 10100


def test_loan_disburse_proxies_to_backend(client):
    ROUTER.add("POST", "/loans", 200,
               {"loan_id": "loan-1", "amount_rub": 200000, "new_balance_rub": 250000,
                "rate_pct": 19.5, "term_months": 24, "monthly_payment_rub": 10100})
    r = client.post("/api/loan/disburse",
                    json={"customer_id": "c-1", "amount_rub": 200000, "term_months": 24, "rate_pct": 19.5})
    assert r.status_code == 200
    assert r.json()["loan_id"] == "loan-1"


# --------------------------------------------------------------------------
# Вклад — регрессия: retail должен донести ставку cib до backend
# --------------------------------------------------------------------------
def test_deposit_terms_proxies_to_cib(client):
    ROUTER.add("POST", "/deposit/terms", 200,
               {"approved": True, "rate_pct": 20.0, "term_months": 12, "amount_rub": 100000})
    r = client.post("/api/deposit/terms",
                    json={"customer_id": "c-1", "amount_rub": 100000, "term_months": 12})
    assert r.status_code == 200
    assert r.json()["rate_pct"] == 20.0


def test_deposit_open_forwards_rate_to_backend(client):
    ROUTER.add("POST", "/deposits", 200,
               {"deposit_id": "dep-1", "amount_rub": 100000, "term_months": 12,
                "rate_pct": 20.0, "maturity_date": "2027-06-03", "new_balance_rub": 0})
    r = client.post("/api/deposit/open",
                    json={"customer_id": "c-1", "amount_rub": 100000, "term_months": 12, "rate_pct": 20.0})
    assert r.status_code == 200
    # ключевая проверка: ставка ушла в backend, итог совпадает с обещанным
    sent = ROUTER.last_body_to("/deposits")
    assert sent["rate_pct"] == 20.0
    assert r.json()["rate_pct"] == 20.0


def test_deposit_product_filters_deposit_base(client):
    ROUTER.add("GET", "/products", 200,
               {"total": 2, "items": [
                   {"id": "credit-base", "name": "Карта", "rate_pct": 25.0},
                   {"id": "deposit-base", "name": "Вклад на срок", "rate_pct": 20.0},
               ]})
    r = client.get("/api/deposit-product")
    assert r.status_code == 200
    assert r.json()["id"] == "deposit-base"
    assert r.json()["rate_pct"] == 20.0


# --------------------------------------------------------------------------
# Зарплатный проект
# --------------------------------------------------------------------------
def test_payroll_validate_proxies_to_cib(client):
    ROUTER.add("POST", "/payroll/validate", 200,
               {"eligible": True, "total_payroll_rub": 500000, "employees_count": 5, "reason": "ок"})
    r = client.post("/api/payroll/validate", json={"employer_id": "corp-001"})
    assert r.status_code == 200
    assert r.json()["employees_count"] == 5


def test_payroll_run_proxies_to_backend(client):
    ROUTER.add("POST", "/payroll/run", 200,
               {"status": "ok", "employees_paid": 5, "total_paid_rub": 500000,
                "new_employer_balance_rub": 1000000, "payments": []})
    r = client.post("/api/payroll/run", json={"employer_id": "corp-001"})
    assert r.status_code == 200
    assert r.json()["employees_paid"] == 5


# --------------------------------------------------------------------------
# Корпоративный банкинг — платёж с авторизацией в cib
# --------------------------------------------------------------------------
def test_corporate_payment_approved(client):
    ROUTER.add("POST", "/corporate/payment-auth", 200, {"approved": True})
    ROUTER.add("POST", "/corporate/payments", 200,
               {"payment_id": "p-1", "status": "ok", "amount_rub": 1000, "new_balance_rub": 9000})
    r = client.post("/api/corporate/payments",
                    json={"from_account_id": "corp-001", "to_account_id": "corp-002",
                          "amount_rub": 1000, "purpose": "услуги"})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert body["new_balance_rub"] == 9000


def test_corporate_payment_declined_not_executed(client):
    ROUTER.add("POST", "/corporate/payment-auth", 200,
               {"approved": False, "reason": "недостаточно средств"})
    r = client.post("/api/corporate/payments",
                    json={"from_account_id": "corp-001", "to_account_id": "corp-002",
                          "amount_rub": 99999999, "purpose": "услуги"})
    assert r.status_code == 200
    assert r.json()["approved"] is False
    # платёж не должен исполняться в backend, если cib не одобрил
    assert ROUTER.last_body_to("/corporate/payments") is None
