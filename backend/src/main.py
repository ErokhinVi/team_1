"""Блок backend — ядро данных банка команды.

Хранит клиентов, транзакции, балансы; отдаёт базовый API. UI нет.
Данные in-memory из seed/*.jsonl, включая кредитную историю клиентов.
Кредитное хранилище: заявки (/credit-applications) и кредитная история
(/credit-history/{client_id}); при одобрении заявки кредит зачисляется на счёт.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query

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
_credit_history: list[dict[str, Any]] = []
_credit_by_client: dict[str, list[dict[str, Any]]] = {}
_applications: dict[str, dict[str, Any]] = {}


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


def _load_seed() -> None:
    if not SEED_DIR:
        return
    clients = _load_jsonl(SEED_DIR / "clients.jsonl")
    _clients.extend(clients)
    _clients_by_id.update({c["id"]: c for c in clients})
    _transactions.extend(_load_jsonl(SEED_DIR / "transactions.jsonl"))
    for rec in _load_jsonl(SEED_DIR / "credit_history.jsonl"):
        _add_credit_record(rec)


def _add_credit_record(rec: dict[str, Any]) -> None:
    _credit_history.append(rec)
    _credit_by_client.setdefault(rec["client_id"], []).append(rec)


_load_seed()

app = FastAPI(title="backend — ядро данных", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "team": TEAM_NAME, "block": "backend",
            "commit": COMMIT, "clients_loaded": len(_clients),
            "transactions_loaded": len(_transactions),
            "credit_history_loaded": len(_credit_history),
            "credit_applications": len(_applications)}


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
    return {
        "status": "ok", "kind": kind, "amount_rub": amount, "to": label,
        "from_client_id": from_id, "new_balance_rub": sender["balance_rub"],
        "tx_id": out_tx["id"], "ts": now_iso,
    }


# ---------------------------------------------------------------------------
# Credits: credit history and credit applications
# ---------------------------------------------------------------------------

CREDIT_PRODUCTS = {"consumer_credit", "auto_credit", "mortgage", "credit_card"}
APPLICATION_STATUSES = {"pending", "approved", "rejected"}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _annuity_payment(principal: float, rate_pct: float, months: int) -> int:
    """Monthly annuity payment, rounded to whole roubles."""
    r = rate_pct / 1200
    if r <= 0:
        return round(principal / months)
    return round(principal * r / (1 - (1 + r) ** -months))


def _credit_summary(client_id: str) -> dict[str, Any]:
    items = sorted(_credit_by_client.get(client_id, []),
                   key=lambda r: r.get("opened_at", ""), reverse=True)
    active = [r for r in items if r.get("status") == "active"]
    max_overdue = max((r.get("overdue_days_max", 0) for r in items), default=0)
    return {
        "client_id": client_id,
        "total": len(items),
        "active_count": len(active),
        "active_principal_rub": sum(r.get("principal_rub", 0) for r in active),
        "active_monthly_payment_rub": sum(
            _annuity_payment(r["principal_rub"], r["rate_pct"], r["term_months"])
            for r in active),
        "closed_clean_count": sum(1 for r in items if r.get("status") == "closed_clean"),
        "closed_with_overdue_count": sum(
            1 for r in items if r.get("status") == "closed_with_overdue"),
        "max_overdue_days": max_overdue,
        "has_overdue": max_overdue > 0,
        "items": items,
    }


@app.get("/credit-history/{client_id}")
async def get_credit_history(client_id: str) -> dict:
    """Client's credit history (seed + credits issued here) with a summary for scoring."""
    if client_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    return _credit_summary(client_id)


def _decide(app_rec: dict[str, Any], status: str, rate_pct: Any,
            reason: str | None, decided_by: str | None) -> None:
    """Apply a decision to a pending application; approval disburses the loan."""
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400,
                            detail="решение: status должен быть approved или rejected")
    if app_rec["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"по заявке {app_rec['id']} уже есть решение: {app_rec['status']}")
    rate = 0.0
    if status == "approved":
        try:
            rate = float(rate_pct)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400,
                                detail="для одобрения укажи ставку rate_pct (годовых, %)")
        if not 0 <= rate <= 100:
            raise HTTPException(status_code=400,
                                detail="ставка rate_pct должна быть от 0 до 100")

    now = _now_iso()
    app_rec.update({"status": status, "reason": reason, "decided_by": decided_by,
                    "decided_at": now})
    if status == "rejected":
        return

    client = _clients_by_id[app_rec["client_id"]]
    amount, term = app_rec["amount_rub"], app_rec["term_months"]

    # Disburse: money lands on the client's account.
    client["balance_rub"] += amount
    tx = {
        "id": f"t-{100000 + len(_transactions) + 1:08d}",
        "client_id": client["id"], "type": "loan_disbursement", "amount_rub": amount,
        "ts": now, "counterparty": f"Кредит по заявке {app_rec['id']}",
    }
    _transactions.append(tx)

    # The new loan becomes part of the client's credit history.
    credit = {
        "id": f"ch-{len(_credit_history) + 1:06d}",
        "client_id": client["id"], "product": app_rec["product"],
        "principal_rub": amount, "term_months": term, "rate_pct": rate,
        "opened_at": now[:10], "status": "active", "overdue_days_max": 0,
        "application_id": app_rec["id"],
    }
    _add_credit_record(credit)
    products = client.setdefault("products", [])
    if app_rec["product"] not in products:
        products.append(app_rec["product"])

    app_rec.update({
        "rate_pct": rate,
        "monthly_payment_rub": _annuity_payment(amount, rate, term),
        "credit_id": credit["id"], "disbursement_tx_id": tx["id"],
        "new_balance_rub": client["balance_rub"],
    })


@app.post("/credit-applications", status_code=201)
async def create_credit_application(
    payload: dict = Body(..., examples=[{
        "client_id": "c-01000", "amount_rub": 300000, "term_months": 24,
        "product": "consumer_credit", "purpose": "ремонт",
    }, {
        "client_id": "c-01000", "amount_rub": 300000, "term_months": 24,
        "status": "approved", "rate_pct": 19.9, "reason": "хорошая история",
        "decided_by": "cib",
    }]),
) -> dict:
    """Create a credit application. Without a decision it stays `pending`;
    with status=approved (+rate_pct) the loan is issued right away."""
    client_id = payload.get("client_id")
    if client_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    try:
        amount = int(payload.get("amount_rub") or 0)
        term = int(payload.get("term_months") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400,
                            detail="amount_rub и term_months должны быть числами")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="укажи положительную сумму amount_rub")
    if not 1 <= term <= 360:
        raise HTTPException(status_code=400, detail="срок term_months — от 1 до 360 месяцев")
    product = payload.get("product") or "consumer_credit"
    if product not in CREDIT_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"неизвестный продукт {product}; доступны: {sorted(CREDIT_PRODUCTS)}")
    status = payload.get("status") or "pending"
    if status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status — одно из {sorted(APPLICATION_STATUSES)}")

    app_rec: dict[str, Any] = {
        "id": f"ca-{len(_applications) + 1:06d}",
        "client_id": client_id, "client_name": _clients_by_id[client_id]["name"],
        "product": product, "amount_rub": amount, "term_months": term,
        "purpose": payload.get("purpose"), "status": "pending",
        "created_at": _now_iso(),
        "rate_pct": None, "monthly_payment_rub": None, "reason": None,
        "decided_by": None, "decided_at": None,
    }
    if status != "pending":
        _decide(app_rec, status, payload.get("rate_pct"),
                payload.get("reason"), payload.get("decided_by"))
    _applications[app_rec["id"]] = app_rec
    return app_rec


@app.get("/credit-applications")
async def list_credit_applications(
    client_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Credit applications, newest first. Optional filters: client_id, status."""
    out = list(_applications.values())
    if client_id:
        out = [a for a in out if a["client_id"] == client_id]
    if status:
        out = [a for a in out if a["status"] == status]
    out.reverse()
    return {"total": len(out), "items": out[:limit]}


@app.get("/credit-applications/{application_id}")
async def get_credit_application(application_id: str) -> dict:
    a = _applications.get(application_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"заявка {application_id} не найдена")
    return a


@app.patch("/credit-applications/{application_id}")
async def decide_credit_application(
    application_id: str,
    payload: dict = Body(..., examples=[{
        "status": "approved", "rate_pct": 19.9, "reason": "хорошая история",
        "decided_by": "cib",
    }, {
        "status": "rejected", "reason": "высокая долговая нагрузка", "decided_by": "cib",
    }]),
) -> dict:
    """Record the decision on a pending application. Approval issues the loan."""
    a = _applications.get(application_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"заявка {application_id} не найдена")
    _decide(a, payload.get("status"), payload.get("rate_pct"),
            payload.get("reason"), payload.get("decided_by"))
    return a
