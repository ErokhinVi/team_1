"""Блок backend — ядро данных банка команды.

Хранит клиентов, транзакции, балансы; отдаёт базовый API. UI нет.
Данные in-memory из seed/*.jsonl. Кредитное хранилище
(POST/GET /credit-applications) добавляет владелец блока в рамках задачи.
"""
from __future__ import annotations

import json
import math
import os
import random
import string
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

TEAM_NAME = os.environ.get("TEAM_NAME", "team")
COMMIT = os.environ.get("RENDER_GIT_COMMIT", "local")


def _find_seed_dir() -> Path | None:
    """Ищем seed/ — работает и в Docker (/app/seed), и локально."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "seed",
        here.parents[2] / "seed" if len(here.parents) >= 3 else None,
        here.parents[3] / "seed" if len(here.parents) >= 4 else None,
        here.parents[4] / "seed" if len(here.parents) >= 5 else None,
    ]
    for c in candidates:
        if c and c.exists():
            return c
    return None


SEED_DIR = _find_seed_dir()
_clients: list[dict[str, Any]] = []
_clients_by_id: dict[str, dict[str, Any]] = {}
_transactions: list[dict[str, Any]] = []
_credit_cards: list[dict[str, Any]] = []
_credit_cards_by_id: dict[str, dict[str, Any]] = {}
_brokerage_accounts: dict[str, dict[str, Any]] = {}
_brokerage_orders: list[dict[str, Any]] = []
_corporate_accounts: list[dict[str, Any]] = []
_corporate_accounts_by_id: dict[str, dict[str, Any]] = {}
_corporate_payments: list[dict[str, Any]] = []
_loans: list[dict[str, Any]] = []
_deposits: list[dict[str, Any]] = []
_mortgages: list[dict[str, Any]] = []

MOCK_PRICES: dict[str, float] = {
    "SBER": 312.5,
    "GAZP": 163.2,
    "LKOH": 7240.0,
    "YNDX": 4150.0,
    "MGNT": 5980.0,
}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _save_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _save_clients() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "clients.jsonl", _clients)


def _save_transactions() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "transactions.jsonl", _transactions)


def _save_credit_cards() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "credit_cards.jsonl", _credit_cards)


def _save_brokerage() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "brokerage_accounts.jsonl", list(_brokerage_accounts.values()))
        _save_jsonl(SEED_DIR / "brokerage_orders.jsonl", _brokerage_orders)


def _save_corporate() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "corporate_accounts.jsonl", _corporate_accounts)
        _save_jsonl(SEED_DIR / "corporate_payments.jsonl", _corporate_payments)


def _save_loans() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "loans.jsonl", _loans)


def _save_deposits() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "deposits.jsonl", _deposits)


def _save_mortgages() -> None:
    if SEED_DIR:
        _save_jsonl(SEED_DIR / "mortgages.jsonl", _mortgages)


def _load_seed() -> None:
    if not SEED_DIR:
        return
    clients = _load_jsonl(SEED_DIR / "clients.jsonl")
    _clients.extend(clients)
    _clients_by_id.update({c["id"]: c for c in clients})
    _transactions.extend(_load_jsonl(SEED_DIR / "transactions.jsonl"))
    for card in _load_jsonl(SEED_DIR / "credit_cards.jsonl"):
        _credit_cards.append(card)
        _credit_cards_by_id[card["card_id"]] = card
    for acc in _load_jsonl(SEED_DIR / "brokerage_accounts.jsonl"):
        _brokerage_accounts[acc["customer_id"]] = acc
    _brokerage_orders.extend(_load_jsonl(SEED_DIR / "brokerage_orders.jsonl"))
    corps = _load_jsonl(SEED_DIR / "corporate_accounts.jsonl")
    _corporate_accounts.extend(corps)
    _corporate_accounts_by_id.update({c["id"]: c for c in corps})
    _corporate_payments.extend(_load_jsonl(SEED_DIR / "corporate_payments.jsonl"))
    _loans.extend(_load_jsonl(SEED_DIR / "loans.jsonl"))
    _deposits.extend(_load_jsonl(SEED_DIR / "deposits.jsonl"))
    _mortgages.extend(_load_jsonl(SEED_DIR / "mortgages.jsonl"))


_load_seed()

app = FastAPI(title="backend — ядро данных", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "team": TEAM_NAME, "block": "backend",
            "commit": COMMIT, "clients_loaded": len(_clients),
            "transactions_loaded": len(_transactions)}


@app.get("/clients")
async def list_clients(
    segment: str | None = Query(default=None),
    has_overdue: bool | None = None,
    min_income: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    out = _clients
    if segment:
        out = [c for c in out if c.get("segment") == segment]
    if has_overdue is not None:
        out = [c for c in out if bool(c.get("has_overdue_history")) == has_overdue]
    if min_income is not None:
        out = [c for c in out if c.get("income_rub", 0) >= min_income]
    return {"total": len(out), "items": out[:limit]}


@app.get("/clients/{client_id}")
async def get_client(client_id: str) -> dict:
    c = _clients_by_id.get(client_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    return c


@app.get("/transactions/{client_id}")
async def get_transactions(
    client_id: str, limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    if client_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    txs = [t for t in _transactions if t["client_id"] == client_id]
    txs.sort(key=lambda t: t["ts"], reverse=True)
    return {"total": len(txs), "items": txs[:limit]}


@app.post("/api/transfer")
async def api_transfer(payload: dict) -> dict:
    from_id = payload.get("from_client_id")
    to_query = (payload.get("to") or "").strip()
    amount = int(payload.get("amount_rub") or 0)
    if from_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="отправитель не найден")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="укажи положительную сумму")
    if not to_query:
        raise HTTPException(status_code=400, detail="укажи получателя")
    sender = _clients_by_id[from_id]
    if amount > sender["balance_rub"]:
        raise HTTPException(
            status_code=400,
            detail=f"недостаточно средств: на счёте {sender['balance_rub']} ₽",
        )
    receiver: dict[str, Any] | None = None
    if to_query in _clients_by_id and to_query != from_id:
        receiver = _clients_by_id[to_query]
    else:
        tql = to_query.lower()
        for c in _clients:
            if c["id"] != from_id and (tql == c["name"].lower() or tql in c["name"].lower()):
                receiver = c
                break
    now_iso = datetime.now().replace(microsecond=0).isoformat()
    sender["balance_rub"] -= amount
    out_tx = {
        "id": f"t-{100000 + len(_transactions) + 1:08d}",
        "client_id": from_id, "type": "transfer_out", "amount_rub": -amount,
        "ts": now_iso, "counterparty": receiver["name"] if receiver else to_query,
    }
    _transactions.append(out_tx)
    if receiver:
        receiver["balance_rub"] += amount
        _transactions.append({
            "id": f"t-{100000 + len(_transactions) + 1:08d}",
            "client_id": receiver["id"], "type": "transfer_in", "amount_rub": amount,
            "ts": now_iso, "counterparty": sender["name"],
        })
        kind, label = "internal", receiver["name"]
    else:
        kind, label = "external", to_query
    _save_clients()
    _save_transactions()
    return {
        "status": "ok", "kind": kind, "amount_rub": amount, "to": label,
        "from_client_id": from_id, "new_balance_rub": sender["balance_rub"],
        "tx_id": out_tx["id"], "ts": now_iso,
    }


def _generate_card_number() -> str:
    return " ".join(
        "".join(random.choices(string.digits, k=4)) for _ in range(4)
    )


@app.post("/credit-cards")
async def create_credit_card(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    credit_limit = payload.get("credit_limit")
    if not customer_id or customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if not credit_limit or int(credit_limit) <= 0:
        raise HTTPException(status_code=400, detail="укажи положительный кредитный лимит")
    card_id = f"card-{len(_credit_cards) + 1:06d}"
    card = {
        "card_id": card_id,
        "customer_id": customer_id,
        "card_number": _generate_card_number(),
        "credit_limit_rub": int(credit_limit),
        "status": "approved",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    _credit_cards.append(card)
    _credit_cards_by_id[card_id] = card
    _save_credit_cards()
    return {"card_id": card["card_id"], "card_number": card["card_number"], "status": card["status"]}


@app.get("/credit-cards")
async def list_credit_cards(customer_id: str = Query(...)) -> dict:
    if customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    cards = [c for c in _credit_cards if c["customer_id"] == customer_id]
    return {"total": len(cards), "items": cards}


@app.post("/credit-cards/{card_id}/activate")
async def activate_credit_card(card_id: str) -> dict:
    card = _credit_cards_by_id.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="карта не найдена")
    if card["status"] != "approved":
        raise HTTPException(status_code=400, detail=f"карту нельзя активировать: статус '{card['status']}'")
    card["status"] = "active"
    _save_credit_cards()
    return {"card_id": card_id, "status": card["status"]}


@app.post("/brokerage/accounts")
async def create_brokerage_account(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id or customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if customer_id in _brokerage_accounts:
        raise HTTPException(status_code=400, detail="брокерский счёт уже существует")
    account = {
        "account_id": f"brok-{customer_id}",
        "customer_id": customer_id,
        "balance_rub": 0.0,
        "status": "active",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    _brokerage_accounts[customer_id] = account
    _save_brokerage()
    return {"account_id": account["account_id"], "status": account["status"]}


@app.get("/brokerage/accounts/{customer_id}")
async def get_brokerage_account(customer_id: str) -> dict:
    if customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    account = _brokerage_accounts.get(customer_id)
    if not account:
        raise HTTPException(status_code=404, detail="брокерский счёт не найден")
    return account


@app.post("/brokerage/orders")
async def create_brokerage_order(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    ticker = (payload.get("ticker") or "").upper()
    quantity = int(payload.get("quantity") or 0)
    direction = payload.get("direction")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id обязателен")
    if customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if ticker not in MOCK_PRICES:
        raise HTTPException(status_code=400, detail=f"неизвестный тикер; доступны: {', '.join(MOCK_PRICES)}")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="количество должно быть положительным")
    if direction not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="direction должен быть 'buy' или 'sell'")
    account = _brokerage_accounts.get(customer_id)
    if not account:
        account = {
            "account_id": f"brok-{customer_id}",
            "customer_id": customer_id,
            "balance_rub": 0.0,
            "status": "active",
            "created_at": datetime.now().replace(microsecond=0).isoformat(),
        }
        _brokerage_accounts[customer_id] = account
        _save_brokerage()
    price = MOCK_PRICES[ticker]
    total_rub = round(price * quantity, 2)
    if direction == "buy":
        client = _clients_by_id[customer_id]
        if client["balance_rub"] < total_rub:
            raise HTTPException(status_code=400, detail=f"недостаточно средств: на счёте {client['balance_rub']} ₽")
        client["balance_rub"] = round(client["balance_rub"] - total_rub, 2)
        account["balance_rub"] = round(account["balance_rub"] + total_rub, 2)
    else:
        if account["balance_rub"] < total_rub:
            raise HTTPException(status_code=400, detail="недостаточно активов для продажи")
        account["balance_rub"] = round(account["balance_rub"] - total_rub, 2)
        client = _clients_by_id[customer_id]
        client["balance_rub"] = round(client["balance_rub"] + total_rub, 2)
    order_id = f"ord-{len(_brokerage_orders) + 1:06d}"
    order = {
        "order_id": order_id,
        "customer_id": customer_id,
        "ticker": ticker,
        "quantity": quantity,
        "direction": direction,
        "price_rub": price,
        "total_rub": total_rub,
        "status": "executed",
        "ts": datetime.now().replace(microsecond=0).isoformat(),
    }
    _brokerage_orders.append(order)
    _save_clients()
    _save_brokerage()
    return {
        "order_id": order_id,
        "status": "executed",
        "ticker": ticker,
        "direction": direction,
        "total_rub": total_rub,
        "new_account_balance_rub": account["balance_rub"],
    }


@app.get("/corporate/accounts")
async def list_corporate_accounts(
    industry: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    out = _corporate_accounts
    if industry:
        out = [c for c in out if c.get("industry") == industry]
    return {"total": len(out), "items": out[:limit]}


@app.get("/corporate/accounts/{account_id}")
async def get_corporate_account(account_id: str) -> dict:
    corp = _corporate_accounts_by_id.get(account_id)
    if not corp:
        raise HTTPException(status_code=404, detail=f"корпоративный счёт {account_id} не найден")
    return corp


@app.post("/corporate/payment-auth")
async def corporate_payment_auth(payload: dict) -> dict:
    from_id = payload.get("from_account_id")
    to_id = payload.get("to_account_id")
    amount = int(payload.get("amount_rub") or 0)
    if not from_id or from_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=404, detail="счёт отправителя не найден")
    if not to_id or to_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=404, detail="счёт получателя не найден")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="сумма должна быть положительной")
    sender = _corporate_accounts_by_id[from_id]
    authorized = sender["balance_rub"] >= amount
    return {
        "authorized": authorized,
        "from_account_id": from_id,
        "from_name": sender["name"],
        "amount_rub": amount,
        "available_balance_rub": sender["balance_rub"],
        "reason": "OK" if authorized else "недостаточно средств на счёте",
    }


@app.post("/corporate/payments")
async def corporate_payment(payload: dict) -> dict:
    from_id = payload.get("from_account_id")
    to_id = payload.get("to_account_id")
    amount = int(payload.get("amount_rub") or 0)
    purpose = (payload.get("purpose") or "Перевод").strip()
    if not from_id or from_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=404, detail="счёт отправителя не найден")
    if not to_id or to_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=404, detail="счёт получателя не найден")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="отправитель и получатель совпадают")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="сумма должна быть положительной")
    sender = _corporate_accounts_by_id[from_id]
    receiver = _corporate_accounts_by_id[to_id]
    if sender["balance_rub"] < amount:
        raise HTTPException(status_code=400, detail=f"недостаточно средств: на счёте {sender['balance_rub']} ₽")
    sender["balance_rub"] -= amount
    receiver["balance_rub"] += amount
    payment_id = f"cpay-{len(_corporate_payments) + 1:06d}"
    now_iso = datetime.now().replace(microsecond=0).isoformat()
    payment = {
        "payment_id": payment_id,
        "from_account_id": from_id,
        "from_name": sender["name"],
        "to_account_id": to_id,
        "to_name": receiver["name"],
        "amount_rub": amount,
        "purpose": purpose,
        "ts": now_iso,
    }
    _corporate_payments.append(payment)
    _save_corporate()
    return {
        "payment_id": payment_id,
        "status": "executed",
        "from_name": sender["name"],
        "to_name": receiver["name"],
        "amount_rub": amount,
        "new_balance_rub": sender["balance_rub"],
        "ts": now_iso,
    }


@app.get("/corporate/{client_id}/employees")
async def get_corporate_employees(client_id: str) -> dict:
    if client_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=404, detail=f"корпоративный счёт {client_id} не найден")
    employees = [
        {"id": c["id"], "name": c["name"], "income_rub": c["income_rub"], "balance_rub": c["balance_rub"]}
        for c in _clients if c.get("employer_id") == client_id
    ]
    return {"total": len(employees), "items": employees}


@app.post("/payroll/run")
async def run_payroll(payload: dict) -> dict:
    employer_id = payload.get("employer_id")
    if not employer_id or employer_id not in _corporate_accounts_by_id:
        raise HTTPException(status_code=400, detail="корпоративный счёт работодателя не найден")
    employer = _corporate_accounts_by_id[employer_id]
    employees = [c for c in _clients if c.get("employer_id") == employer_id]
    if not employees:
        raise HTTPException(status_code=400, detail="у этой компании нет сотрудников в банке")
    total_payroll = sum(e["income_rub"] for e in employees)
    if employer["balance_rub"] < total_payroll:
        raise HTTPException(
            status_code=400,
            detail=f"недостаточно средств: нужно {total_payroll} ₽, на счёте {employer['balance_rub']} ₽",
        )
    payments = []
    for emp in employees:
        emp["balance_rub"] += emp["income_rub"]
        payments.append({"employee_id": emp["id"], "name": emp["name"], "amount_rub": emp["income_rub"]})
    employer["balance_rub"] -= total_payroll
    _save_clients()
    _save_corporate()
    return {
        "status": "ok",
        "employer_id": employer_id,
        "employees_paid": len(employees),
        "total_paid_rub": total_payroll,
        "new_employer_balance_rub": employer["balance_rub"],
        "payments": payments,
    }


_DEPOSIT_RATES = {3: 7.0, 6: 9.5, 12: 12.0, 24: 11.0, 36: 10.5}


def _deposit_rate(term_months: int) -> float:
    if term_months <= 3:
        return 7.0
    if term_months <= 6:
        return 9.5
    if term_months <= 12:
        return 12.0
    if term_months <= 24:
        return 11.0
    return 10.5


def _monthly_payment(amount: int, rate_pct: float, term_months: int) -> int:
    r = rate_pct / 12 / 100
    if r == 0:
        return round(amount / term_months)
    m = amount * r / (1 - (1 + r) ** (-term_months))
    return round(m / 100) * 100


@app.post("/loans")
async def create_loan(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    amount_rub = int(payload.get("amount_rub") or 0)
    term_months = int(payload.get("term_months") or 0)
    rate_pct = float(payload.get("rate_pct") or 0)
    if not customer_id or customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if amount_rub <= 0:
        raise HTTPException(status_code=400, detail="сумма должна быть положительной")
    if term_months <= 0:
        raise HTTPException(status_code=400, detail="срок должен быть положительным")
    if rate_pct <= 0:
        raise HTTPException(status_code=400, detail="ставка должна быть положительной")
    client = _clients_by_id[customer_id]
    loan_id = f"loan-{uuid.uuid4().hex[:8]}"
    monthly_payment_rub = _monthly_payment(amount_rub, rate_pct, term_months)
    client["balance_rub"] = round(client["balance_rub"] + amount_rub, 2)
    loan = {
        "loan_id": loan_id,
        "customer_id": customer_id,
        "amount_rub": amount_rub,
        "term_months": term_months,
        "rate_pct": rate_pct,
        "monthly_payment_rub": monthly_payment_rub,
        "status": "active",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    _loans.append(loan)
    _save_clients()
    _save_loans()
    return {
        "loan_id": loan_id,
        "customer_id": customer_id,
        "amount_rub": amount_rub,
        "term_months": term_months,
        "rate_pct": rate_pct,
        "monthly_payment_rub": monthly_payment_rub,
        "new_balance_rub": int(client["balance_rub"]),
    }


@app.post("/deposits")
async def create_deposit(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    amount_rub = int(payload.get("amount_rub") or 0)
    term_months = int(payload.get("term_months") or 0)
    if not customer_id or customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if amount_rub <= 0:
        raise HTTPException(status_code=400, detail="сумма должна быть положительной")
    if term_months <= 0:
        raise HTTPException(status_code=400, detail="срок должен быть положительным")
    client = _clients_by_id[customer_id]
    if client["balance_rub"] < amount_rub:
        raise HTTPException(status_code=400, detail=f"недостаточно средств: на счёте {client['balance_rub']} ₽")
    # Персональная ставка от cib имеет приоритет; иначе — наша таблица по сроку.
    if payload.get("rate_pct") is not None:
        rate_pct = float(payload["rate_pct"])
        if rate_pct <= 0:
            raise HTTPException(status_code=400, detail="ставка должна быть положительной")
    else:
        rate_pct = _deposit_rate(term_months)
    from datetime import timedelta
    maturity_date = (datetime.now() + timedelta(days=30 * term_months)).date().isoformat()
    deposit_id = f"dep-{uuid.uuid4().hex[:8]}"
    client["balance_rub"] = round(client["balance_rub"] - amount_rub, 2)
    deposit = {
        "deposit_id": deposit_id,
        "customer_id": customer_id,
        "amount_rub": amount_rub,
        "term_months": term_months,
        "rate_pct": rate_pct,
        "maturity_date": maturity_date,
        "status": "active",
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    _deposits.append(deposit)
    _save_clients()
    _save_deposits()
    return {
        "deposit_id": deposit_id,
        "customer_id": customer_id,
        "amount_rub": amount_rub,
        "term_months": term_months,
        "rate_pct": rate_pct,
        "maturity_date": maturity_date,
        "new_balance_rub": int(client["balance_rub"]),
    }


@app.post("/mortgages")
async def create_mortgage(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    property_price_rub = int(payload.get("property_price_rub") or 0)
    down_payment_rub = int(payload.get("down_payment_rub") or 0)
    loan_amount_rub = int(payload.get("loan_amount_rub") or 0)
    term_years = int(payload.get("term_years") or 0)
    rate_pct = float(payload.get("rate_pct") or 0)
    if not customer_id or customer_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail="клиент не найден")
    if loan_amount_rub <= 0:
        raise HTTPException(status_code=400, detail="сумма кредита должна быть положительной")
    if term_years <= 0:
        raise HTTPException(status_code=400, detail="срок должен быть положительным")
    if rate_pct <= 0:
        raise HTTPException(status_code=400, detail="ставка должна быть положительной")
    # Та же аннуитетная формула, что у cib — чтобы платёж всегда совпадал.
    monthly_payment_rub = _monthly_payment(loan_amount_rub, rate_pct, term_years * 12)
    mortgage_id = f"mort-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now().replace(microsecond=0).isoformat()
    mortgage = {
        "mortgage_id": mortgage_id,
        "customer_id": customer_id,
        "property_price_rub": property_price_rub,
        "down_payment_rub": down_payment_rub,
        "loan_amount_rub": loan_amount_rub,
        "term_years": term_years,
        "rate_pct": rate_pct,
        "monthly_payment_rub": monthly_payment_rub,
        "status": "active",
        "created_at": created_at,
    }
    _mortgages.append(mortgage)
    _save_mortgages()
    return mortgage
