"""Блок backend — ядро данных банка команды.

Хранит клиентов, транзакции, балансы; отдаёт базовый API. UI нет.
Данные in-memory из seed/*.jsonl, включая кредитную историю клиентов.
Кредитное хранилище: заявки (/credit-applications) и кредитная история
(/credit-history/{client_id}); при одобрении заявки кредит зачисляется на счёт.
"""
from __future__ import annotations

import json
import os
import calendar
from datetime import date, datetime
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
_idempotency: dict[str, str] = {}  # idempotency_key -> application id


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
            "credit_applications": len(_applications) + len(_r1_applications)}


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


def _annuity_exact(principal: float, rate_pct: float, months: int) -> float:
    """Monthly annuity payment P = S*m / (1 - (1+m)^-n), m = rate/1200."""
    m = rate_pct / 1200
    if m <= 0:
        return principal / months
    return principal * m / (1 - (1 + m) ** -months)


def _annuity_payment(principal: float, rate_pct: float, months: int) -> int:
    """Monthly annuity payment, rounded to whole roubles."""
    return round(_annuity_exact(principal, rate_pct, months))


def _credit_end_date(rec: dict[str, Any]) -> date:
    """opened_at + term_months (day clamped to month length)."""
    y, m, d = map(int, rec["opened_at"][:10].split("-"))
    m += int(rec["term_months"])
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(d, calendar.monthrange(y, m)[1]))


def _is_current_credit(rec: dict[str, Any]) -> bool:
    """R1-B4: an `active` credit counts as debt only while its term is running.
    Credits issued through applications always count."""
    if rec.get("status") != "active":
        return False
    if rec.get("application_id"):
        return True
    try:
        return _credit_end_date(rec) >= date.today()
    except (KeyError, ValueError, TypeError):
        return True


def _credit_summary(client_id: str) -> dict[str, Any]:
    items = sorted(_credit_by_client.get(client_id, []),
                   key=lambda r: r.get("opened_at", ""), reverse=True)
    active = [r for r in items if _is_current_credit(r)]
    max_overdue = max((r.get("overdue_days_max", 0) for r in items), default=0)
    salaries = [t["amount_rub"] for t in _transactions
                if t["client_id"] == client_id and t.get("type") == "salary"]
    summary = {
        "active_count": len(active),
        "max_overdue_days": max_overdue,
        "has_active_overdue": any(r.get("overdue_days_max", 0) > 0 for r in active),
        "monthly_debt_payment_rub": round(sum(
            _annuity_exact(r["principal_rub"], r["rate_pct"], r["term_months"])
            for r in active)),
        "is_salary_client": bool(salaries),
        "avg_salary_rub": round(sum(salaries) / len(salaries)) if salaries else 0,
    }
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
        "has_active_overdue": summary["has_active_overdue"],
        "is_salary_client": summary["is_salary_client"],
        "avg_salary_rub": summary["avg_salary_rub"],
        "items": items,
        "summary": summary,
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
        "decided_by": "cib", "idempotency_key": "offer-123",
    }]),
) -> dict:
    """Create a credit application. Without a decision it stays `pending`;
    with status=approved (+rate_pct) the loan is issued right away."""
    client_id = payload.get("client_id")
    if client_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    idem_key = payload.get("idempotency_key")
    if idem_key is not None:
        idem_key = str(idem_key)
        if idem_key in _idempotency:
            return _applications[_idempotency[idem_key]]
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
        "idempotency_key": idem_key,
    }
    if status != "pending":
        _decide(app_rec, status, payload.get("rate_pct"),
                payload.get("reason"), payload.get("decided_by"))
    _applications[app_rec["id"]] = app_rec
    if idem_key is not None:
        _idempotency[idem_key] = app_rec["id"]
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


# ---------------------------------------------------------------------------
# Release 1 (spec from retail, retail/CONTRACT.md): /api/credit-disburse and
# /api/credit-applications. Invalid input -> 422 with a Russian `detail`.
# ---------------------------------------------------------------------------

R1_DECISIONS = {"approved", "counter", "declined", "pending"}
R1_CLIENT_STATUSES = {"accepted", "rejected_by_client"}
_r1_applications: dict[str, dict[str, Any]] = {}
_r1_disbursements: dict[str, dict[str, Any]] = {}  # application_id -> response


def _r1_int(payload: dict, key: str, lo: int, hi: int, label: str) -> int:
    try:
        v = int(payload.get(key))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{label} ({key}) должно быть целым числом")
    if not lo <= v <= hi:
        raise HTTPException(status_code=422, detail=f"{label} ({key}) — от {lo} до {hi}")
    return v


def _r1_rate(payload: dict, required: bool) -> float | None:
    raw = payload.get("rate_pct")
    if raw is None and not required:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="ставка rate_pct должна быть числом")
    if not 0 <= v <= 100:
        raise HTTPException(status_code=422, detail="ставка rate_pct — от 0 до 100")
    return v


def _r1_client(payload: dict) -> dict[str, Any]:
    cid = payload.get("client_id")
    if not cid:
        raise HTTPException(status_code=422, detail="укажи client_id")
    c = _clients_by_id.get(cid)
    if not c:
        raise HTTPException(status_code=404, detail=f"клиент {cid} не найден")
    return c


@app.post("/api/credit-disburse")
async def r1_credit_disburse(
    payload: dict = Body(..., examples=[{
        "client_id": "c-01003", "amount_rub": 150000, "rate_pct": 20.0,
        "term_months": 24, "application_id": "app-000001",
    }]),
) -> dict:
    """R1-B2. Issue a cash loan: money to the account, a transaction, a new
    active credit. Idempotent per application_id."""
    client = _r1_client(payload)
    app_id = payload.get("application_id")
    if app_id and app_id in _r1_disbursements:
        return _r1_disbursements[app_id]
    amount = _r1_int(payload, "amount_rub", 1, 100_000_000, "сумма")
    term = _r1_int(payload, "term_months", 1, 360, "срок")
    rate = _r1_rate(payload, required=True)

    now = _now_iso()
    client["balance_rub"] += amount
    tx = {
        "id": f"t-{100000 + len(_transactions) + 1:08d}",
        "client_id": client["id"], "type": "credit_disbursement", "amount_rub": amount,
        "ts": now, "counterparty": "Кредит наличными",
    }
    _transactions.append(tx)
    credit = {
        "id": f"ch-{len(_credit_history) + 1:06d}",
        "client_id": client["id"], "product": "consumer_credit",
        "principal_rub": amount, "term_months": term, "rate_pct": rate,
        "opened_at": now[:10], "status": "active", "overdue_days_max": 0,
    }
    if app_id:
        credit["application_id"] = app_id
    _add_credit_record(credit)
    products = client.setdefault("products", [])
    if "consumer_credit" not in products:
        products.append("consumer_credit")

    resp = {"status": "ok", "client_id": client["id"], "credit_id": credit["id"],
            "tx_id": tx["id"], "amount_rub": amount, "new_balance_rub": client["balance_rub"]}
    if app_id:
        _r1_disbursements[app_id] = resp
        if app_id in _r1_applications:
            _r1_applications[app_id]["credit_id"] = credit["id"]
    return resp


@app.post("/api/credit-applications")
async def r1_create_application(
    payload: dict = Body(..., examples=[{
        "client_id": "c-01003", "amount_rub": 150000, "term_months": 24,
        "decision": "approved", "rate_pct": 20.0, "approved_amount_rub": 150000,
        "monthly_payment_rub": 7634, "reason": "Кредит одобрен",
    }]),
) -> dict:
    """R1-B3. Save an application together with cib's decision."""
    client = _r1_client(payload)
    amount = _r1_int(payload, "amount_rub", 1, 100_000_000, "сумма")
    term = _r1_int(payload, "term_months", 1, 360, "срок")
    decision = payload.get("decision")
    if decision not in R1_DECISIONS:
        raise HTTPException(status_code=422,
                            detail=f"decision — одно из {sorted(R1_DECISIONS)}")
    rec: dict[str, Any] = {
        "application_id": f"app-{len(_r1_applications) + 1:06d}",
        "created_at": _now_iso(),
        "client_id": client["id"], "amount_rub": amount, "term_months": term,
        "decision": decision, "rate_pct": _r1_rate(payload, required=False),
        "approved_amount_rub": payload.get("approved_amount_rub"),
        "monthly_payment_rub": payload.get("monthly_payment_rub"),
        "reason": payload.get("reason"),
        "status": None, "updated_at": None,
    }
    for k, v in payload.items():  # keep any extra fields retail sends (e.g. product)
        rec.setdefault(k, v)
    _r1_applications[rec["application_id"]] = rec
    return rec


@app.get("/api/credit-applications/{client_id}")
async def r1_list_applications(client_id: str) -> dict:
    """R1-B3. Client's applications, newest first."""
    if client_id not in _clients_by_id:
        raise HTTPException(status_code=404, detail=f"клиент {client_id} не найден")
    items = [a for a in _r1_applications.values() if a["client_id"] == client_id]
    items.reverse()
    return {"total": len(items), "items": items}


@app.patch("/api/credit-applications/{application_id}")
async def r1_update_application(
    application_id: str,
    payload: dict = Body(..., examples=[{"status": "accepted"}]),
) -> dict:
    """R1-B3. Client accepted or declined the offer."""
    a = _r1_applications.get(application_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"заявка {application_id} не найдена")
    status = payload.get("status")
    if status not in R1_CLIENT_STATUSES:
        raise HTTPException(status_code=422,
                            detail=f"status — одно из {sorted(R1_CLIENT_STATUSES)}")
    a["status"] = status
    a["updated_at"] = _now_iso()
    return a
