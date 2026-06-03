"""Tests for all backend API endpoints."""
import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import main
from main import app

client = TestClient(app)


def simulate_restart():
    """Wipe all in-memory state and reload it from disk, the way a fresh
    process does on startup. Used to prove persistence survives a restart."""
    main._clients.clear()
    main._clients_by_id.clear()
    main._transactions.clear()
    main._credit_cards.clear()
    main._credit_cards_by_id.clear()
    main._brokerage_accounts.clear()
    main._brokerage_orders.clear()
    main._corporate_accounts.clear()
    main._corporate_accounts_by_id.clear()
    main._corporate_payments.clear()
    main._loans.clear()
    main._deposits.clear()
    main._load_seed()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first_client_id():
    r = client.get("/clients?limit=1")
    return r.json()["items"][0]["id"]


def first_corporate_id():
    r = client.get("/corporate/accounts?limit=1")
    return r.json()["items"][0]["id"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["block"] == "backend"
    assert data["clients_loaded"] > 0


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def test_list_clients_default():
    r = client.get("/clients")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 500
    assert len(data["items"]) == 50  # default limit

def test_list_clients_limit():
    r = client.get("/clients?limit=5")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 5

def test_list_clients_segment_filter():
    r = client.get("/clients?segment=premium")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(c["segment"] == "premium" for c in items)

def test_list_clients_min_income():
    r = client.get("/clients?min_income=400000&limit=500")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(c["income_rub"] >= 400000 for c in items)

def test_get_client_found():
    cid = first_client_id()
    r = client.get(f"/clients/{cid}")
    assert r.status_code == 200
    assert r.json()["id"] == cid

def test_get_client_not_found():
    r = client.get("/clients/nonexistent-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def test_get_transactions():
    cid = first_client_id()
    r = client.get(f"/transactions/{cid}")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "items" in data

def test_get_transactions_not_found():
    r = client.get("/transactions/nonexistent-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

def test_transfer_internal():
    r = client.get("/clients?limit=2")
    items = r.json()["items"]
    sender, receiver = items[0], items[1]
    amount = 100
    r = client.post("/api/transfer", json={
        "from_client_id": sender["id"],
        "to": receiver["id"],
        "amount_rub": amount,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["kind"] == "internal"
    assert data["amount_rub"] == amount

def test_transfer_insufficient_funds():
    cid = first_client_id()
    r = client.post("/api/transfer", json={
        "from_client_id": cid,
        "to": "some-external",
        "amount_rub": 999_999_999,
    })
    assert r.status_code == 400

def test_transfer_sender_not_found():
    r = client.post("/api/transfer", json={
        "from_client_id": "bad-id",
        "to": "anyone",
        "amount_rub": 100,
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Credit cards
# ---------------------------------------------------------------------------

def test_create_credit_card():
    cid = first_client_id()
    r = client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 100000})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "approved"
    assert "card_id" in data
    assert "card_number" in data

def test_list_credit_cards():
    cid = first_client_id()
    client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 50000})
    r = client.get(f"/credit-cards?customer_id={cid}")
    assert r.status_code == 200
    assert r.json()["total"] >= 1

def test_activate_credit_card():
    cid = first_client_id()
    card_id = client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 50000}).json()["card_id"]
    r = client.post(f"/credit-cards/{card_id}/activate")
    assert r.status_code == 200
    assert r.json()["status"] == "active"

def test_activate_already_active_card():
    cid = first_client_id()
    card_id = client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 50000}).json()["card_id"]
    client.post(f"/credit-cards/{card_id}/activate")
    r = client.post(f"/credit-cards/{card_id}/activate")
    assert r.status_code == 400

def test_create_card_customer_not_found():
    r = client.post("/credit-cards", json={"customer_id": "bad-id", "credit_limit": 50000})
    assert r.status_code == 404

def test_create_card_zero_limit():
    cid = first_client_id()
    r = client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 0})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Brokerage
# ---------------------------------------------------------------------------

def test_create_brokerage_account():
    cid = first_client_id()
    # May already exist — both 200 and 400 are acceptable
    r = client.post("/brokerage/accounts", json={"customer_id": cid})
    assert r.status_code in (200, 400)

def test_brokerage_account_duplicate():
    cid = first_client_id()
    client.post("/brokerage/accounts", json={"customer_id": cid})
    r = client.post("/brokerage/accounts", json={"customer_id": cid})
    assert r.status_code == 400

def test_get_brokerage_account():
    cid = first_client_id()
    client.post("/brokerage/accounts", json={"customer_id": cid})
    r = client.get(f"/brokerage/accounts/{cid}")
    assert r.status_code == 200
    assert r.json()["customer_id"] == cid

def test_get_brokerage_account_not_found():
    r = client.get("/brokerage/accounts/nonexistent-id")
    assert r.status_code == 404

def test_brokerage_order_buy_auto_creates_account():
    # Use a client that likely has no brokerage account yet
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    r = client.post("/brokerage/orders", json={
        "customer_id": cid, "ticker": "SBER", "quantity": 1, "direction": "buy"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "executed"
    assert data["ticker"] == "SBER"
    assert data["total_rub"] == 312.5

def test_brokerage_order_invalid_ticker():
    cid = first_client_id()
    r = client.post("/brokerage/orders", json={
        "customer_id": cid, "ticker": "AAPL", "quantity": 1, "direction": "buy"
    })
    assert r.status_code == 400

def test_brokerage_order_invalid_direction():
    cid = first_client_id()
    r = client.post("/brokerage/orders", json={
        "customer_id": cid, "ticker": "SBER", "quantity": 1, "direction": "hold"
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Corporate accounts
# ---------------------------------------------------------------------------

def test_list_corporate_accounts():
    r = client.get("/corporate/accounts")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 12
    assert len(data["items"]) == 12

def test_list_corporate_accounts_industry_filter():
    r = client.get("/corporate/accounts?industry=it")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(c["industry"] == "it" for c in items)

def test_get_corporate_account():
    corp_id = first_corporate_id()
    r = client.get(f"/corporate/accounts/{corp_id}")
    assert r.status_code == 200
    assert r.json()["id"] == corp_id

def test_get_corporate_account_not_found():
    r = client.get("/corporate/accounts/corp-999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Corporate payment-auth
# ---------------------------------------------------------------------------

def test_payment_auth_sufficient():
    r = client.get("/corporate/accounts?limit=2")
    items = r.json()["items"]
    from_id, to_id = items[0]["id"], items[1]["id"]
    amount = 1000
    r = client.post("/corporate/payment-auth", json={
        "from_account_id": from_id, "to_account_id": to_id, "amount_rub": amount
    })
    assert r.status_code == 200
    assert r.json()["authorized"] is True

def test_payment_auth_insufficient():
    r = client.get("/corporate/accounts?limit=2")
    items = r.json()["items"]
    from_id, to_id = items[0]["id"], items[1]["id"]
    r = client.post("/corporate/payment-auth", json={
        "from_account_id": from_id, "to_account_id": to_id, "amount_rub": 999_999_999_999
    })
    assert r.status_code == 200
    assert r.json()["authorized"] is False

def test_payment_auth_not_found():
    r = client.post("/corporate/payment-auth", json={
        "from_account_id": "corp-999", "to_account_id": "corp-001", "amount_rub": 100
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Corporate payments
# ---------------------------------------------------------------------------

def test_corporate_payment():
    r = client.get("/corporate/accounts?limit=2")
    items = r.json()["items"]
    from_id, to_id = items[0]["id"], items[1]["id"]
    r = client.post("/corporate/payments", json={
        "from_account_id": from_id, "to_account_id": to_id,
        "amount_rub": 1000, "purpose": "Test payment"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "executed"
    assert data["amount_rub"] == 1000

def test_corporate_payment_same_account():
    corp_id = first_corporate_id()
    r = client.post("/corporate/payments", json={
        "from_account_id": corp_id, "to_account_id": corp_id, "amount_rub": 100
    })
    assert r.status_code == 400

def test_corporate_payment_insufficient():
    r = client.get("/corporate/accounts?limit=2")
    items = r.json()["items"]
    from_id, to_id = items[0]["id"], items[1]["id"]
    r = client.post("/corporate/payments", json={
        "from_account_id": from_id, "to_account_id": to_id, "amount_rub": 999_999_999_999
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Corporate employees
# ---------------------------------------------------------------------------

def test_get_employees():
    corp_id = first_corporate_id()
    r = client.get(f"/corporate/{corp_id}/employees")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 4
    emp = data["items"][0]
    assert "id" in emp and "name" in emp and "income_rub" in emp

def test_get_employees_not_found():
    r = client.get("/corporate/corp-999/employees")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Payroll
# ---------------------------------------------------------------------------

def test_payroll_run():
    corp_id = first_corporate_id()
    r = client.post("/payroll/run", json={"employer_id": corp_id})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["employees_paid"] >= 4
    assert data["total_paid_rub"] > 0
    assert len(data["payments"]) == data["employees_paid"]

def test_payroll_not_found():
    r = client.post("/payroll/run", json={"employer_id": "corp-999"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------

def test_create_loan():
    cid = first_client_id()
    r = client.post("/loans", json={
        "customer_id": cid, "amount_rub": 100000,
        "term_months": 12, "rate_pct": 19.5
    })
    assert r.status_code == 200
    data = r.json()
    assert "loan_id" in data
    assert data["amount_rub"] == 100000
    assert data["monthly_payment_rub"] > 0
    assert data["new_balance_rub"] > 0

def test_create_loan_not_found():
    r = client.post("/loans", json={
        "customer_id": "bad-id", "amount_rub": 100000,
        "term_months": 12, "rate_pct": 19.5
    })
    assert r.status_code == 404

def test_create_loan_balance_increases():
    cid = first_client_id()
    balance_before = client.get(f"/clients/{cid}").json()["balance_rub"]
    client.post("/loans", json={
        "customer_id": cid, "amount_rub": 50000,
        "term_months": 12, "rate_pct": 19.5
    })
    balance_after = client.get(f"/clients/{cid}").json()["balance_rub"]
    assert balance_after == balance_before + 50000


# ---------------------------------------------------------------------------
# Deposits
# ---------------------------------------------------------------------------

def test_create_deposit():
    # Use a client with high balance
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    r = client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 100000, "term_months": 12
    })
    assert r.status_code == 200
    data = r.json()
    assert "deposit_id" in data
    assert data["rate_pct"] == 12.0
    assert data["term_months"] == 12
    assert "maturity_date" in data

def test_create_deposit_balance_decreases():
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    balance_before = client.get(f"/clients/{cid}").json()["balance_rub"]
    client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 50000, "term_months": 6
    })
    balance_after = client.get(f"/clients/{cid}").json()["balance_rub"]
    assert round(balance_after) == round(balance_before - 50000)

def test_create_deposit_insufficient():
    cid = first_client_id()
    r = client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 999_999_999, "term_months": 12
    })
    assert r.status_code == 400

def test_create_deposit_not_found():
    r = client.post("/deposits", json={
        "customer_id": "bad-id", "amount_rub": 1000, "term_months": 6
    })
    assert r.status_code == 404

def test_create_deposit_custom_rate():
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    r = client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 10000, "term_months": 12, "rate_pct": 14.7
    })
    assert r.status_code == 200
    # Персональная ставка от cib имеет приоритет над таблицей по сроку
    assert r.json()["rate_pct"] == 14.7

def test_create_deposit_invalid_custom_rate():
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    r = client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 10000, "term_months": 12, "rate_pct": -5
    })
    assert r.status_code == 400

def test_deposit_rates_by_term():
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    expected = [(3, 7.0), (6, 9.5), (12, 12.0), (24, 11.0), (36, 10.5)]
    for term, rate in expected:
        r = client.post("/deposits", json={
            "customer_id": cid, "amount_rub": 10000, "term_months": term
        })
        assert r.status_code == 200, f"Failed for term={term}"
        assert r.json()["rate_pct"] == rate, f"Wrong rate for term={term}"


# ---------------------------------------------------------------------------
# Persistence — records and balances survive a data-layer reload (restart)
# ---------------------------------------------------------------------------

def test_records_survive_restart():
    """Create one of every kind of runtime record, then reload the data layer
    from disk as a fresh process would, and confirm everything is still there."""
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]

    card_id = client.post("/credit-cards", json={"customer_id": cid, "credit_limit": 70000}).json()["card_id"]
    loan_id = client.post("/loans", json={
        "customer_id": cid, "amount_rub": 100000, "term_months": 12, "rate_pct": 18.0
    }).json()["loan_id"]
    deposit_id = client.post("/deposits", json={
        "customer_id": cid, "amount_rub": 50000, "term_months": 12
    }).json()["deposit_id"]
    order = client.post("/brokerage/orders", json={
        "customer_id": cid, "ticker": "SBER", "quantity": 2, "direction": "buy"
    }).json()
    order_id = order["order_id"]

    # Simulate the Render process restarting and reloading state from disk.
    simulate_restart()

    assert any(c["card_id"] == card_id for c in main._credit_cards), "credit card lost on restart"
    assert any(l["loan_id"] == loan_id for l in main._loans), "loan lost on restart"
    assert any(d["deposit_id"] == deposit_id for d in main._deposits), "deposit lost on restart"
    assert any(o["order_id"] == order_id for o in main._brokerage_orders), "brokerage order lost on restart"
    assert cid in main._brokerage_accounts, "brokerage account lost on restart"


def test_balance_changes_survive_restart():
    """A balance change from a loan disbursement must persist across a reload."""
    r = client.get("/clients?segment=private&limit=1")
    cid = r.json()["items"][0]["id"]
    before = client.get(f"/clients/{cid}").json()["balance_rub"]

    client.post("/loans", json={
        "customer_id": cid, "amount_rub": 25000, "term_months": 12, "rate_pct": 18.0
    })
    expected = before + 25000

    simulate_restart()

    after = client.get(f"/clients/{cid}").json()["balance_rub"]
    assert round(after) == round(expected), "balance change did not survive restart"
