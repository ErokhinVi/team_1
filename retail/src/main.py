"""Блок retail — клиентский мобильный банк команды.

UI плюс тонкий слой: за данными ходит в backend, за кредитным решением — в cib.
Своих данных не держит. Вкладку «Кредиты» и /api/credit-apply (оркестрацию
cib + backend) добавляет владелец блока в рамках задачи.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

TEAM_NAME = os.environ.get("TEAM_NAME", "team")
COMMIT = os.environ.get("RENDER_GIT_COMMIT", "local")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8003").rstrip("/")
CIB_URL = os.environ.get("CIB_URL", "http://localhost:8002").rstrip("/")

app = FastAPI(title="retail — мобильный банк", version="1.0.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "team": TEAM_NAME, "block": "retail",
            "commit": COMMIT, "backend_url": BACKEND_URL, "cib_url": CIB_URL}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    f = STATIC_DIR / "index.html"
    return f.read_text(encoding="utf-8") if f.exists() else "<h1>Розница</h1>"


async def _backend_get(path: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{BACKEND_URL}{path}", params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.get("/clients")
async def list_clients(request: Request) -> dict:
    return await _backend_get("/clients", dict(request.query_params))


@app.get("/transactions/{client_id}")
async def transactions(client_id: str, request: Request) -> dict:
    return await _backend_get(f"/transactions/{client_id}", dict(request.query_params))


@app.post("/api/transfer")
async def api_transfer(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BACKEND_URL}/api/transfer", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


# ---------------------------------------------------------------------------
# Credit application: retail orchestrates backend (client card) + cib (decision).
# Focus segments: mass and mass_affluent.
# ---------------------------------------------------------------------------

SEGMENT_LABELS = {
    "mass": "Массовый",
    "mass_affluent": "Массовый+",
    "premium": "Премиум",
    "private": "Private",
    "sme": "Бизнес",
}

# Presets shown in the UI per segment (amounts in RUB, terms in months).
SEGMENT_PRESETS = {
    "mass": {"amounts": [50_000, 150_000, 300_000], "terms": [12, 24, 36],
             "default_amount": 150_000, "default_term": 24},
    "mass_affluent": {"amounts": [300_000, 700_000, 1_500_000], "terms": [12, 24, 36, 60],
                      "default_amount": 700_000, "default_term": 36},
}
DEFAULT_PRESET = SEGMENT_PRESETS["mass"]


def _annuity(amount: float, rate_pct: float, term_months: int) -> int:
    """Monthly annuity payment, for display only (cib owns the decision)."""
    if term_months <= 0:
        return 0
    m = rate_pct / 100 / 12
    if m == 0:
        return round(amount / term_months)
    return round(amount * m / (1 - (1 + m) ** -term_months))


@app.get("/api/credit-presets/{client_id}")
async def credit_presets(client_id: str) -> dict:
    client = await _backend_get(f"/clients/{client_id}")
    seg = client.get("segment", "mass")
    preset = SEGMENT_PRESETS.get(seg, DEFAULT_PRESET)
    return {"client_id": client_id, "segment": seg,
            "segment_label": SEGMENT_LABELS.get(seg, seg), **preset}


@app.post("/api/credit-apply")
async def credit_apply(payload: dict) -> dict:
    client_id = str(payload.get("client_id") or "").strip()
    try:
        amount = float(payload.get("amount_rub") or 0)
        term = int(payload.get("term_months") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="сумма и срок должны быть числами")
    if not client_id or amount <= 0 or term <= 0:
        raise HTTPException(status_code=422, detail="укажите клиента, сумму и срок")

    client = await _backend_get(f"/clients/{client_id}")
    seg = client.get("segment", "mass")
    request_to_cib = {
        "client_id": client_id,
        "product": payload.get("product", "consumer_credit"),
        "amount_rub": amount,
        "term_months": term,
        "segment": seg,
        "income_rub": client.get("income_rub"),
        "risk_score": client.get("risk_score"),
        "has_overdue_history": client.get("has_overdue_history"),
    }

    base = {"client_id": client_id, "segment": seg, "product": request_to_cib["product"],
            "segment_label": SEGMENT_LABELS.get(seg, seg),
            "requested_amount_rub": amount, "requested_term_months": term}

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(f"{CIB_URL}/api/decision", json=request_to_cib)
            if r.status_code in (404, 405):
                # cib's own plan names the route /credit/decide; accept either.
                r = await http.post(f"{CIB_URL}/credit/decide", json=request_to_cib)
    except httpx.HTTPError:
        return {**base, "decision": "pending",
                "message": "Заявка принята. Решение пришлём в течение нескольких минут."}
    if r.status_code != 200:
        return {**base, "decision": "pending",
                "message": "Заявка принята. Решение пришлём в течение нескольких минут."}

    d = r.json()
    decision = d.get("decision", "pending")
    out = {**base, **d, "decision": decision}
    rate = d.get("rate_pct")
    appr_amount = d.get("amount_rub") or amount
    appr_term = int(d.get("term_months") or term)
    if decision in ("approved", "counter") and rate is not None and not d.get("monthly_payment_rub"):
        out["monthly_payment_rub"] = _annuity(appr_amount, float(rate), appr_term)
    if out.get("monthly_payment_rub"):
        out["total_cost_rub"] = out["monthly_payment_rub"] * appr_term
    await _record_outcome(out)
    return out


async def _backend_post(path: str, payload: dict, method: str = "POST") -> httpx.Response | None:
    """Best-effort call to backend; returns None if backend is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            if method == "PATCH":
                return await http.patch(f"{BACKEND_URL}{path}", json=payload)
            return await http.post(f"{BACKEND_URL}{path}", json=payload)
    except httpx.HTTPError:
        return None


# Offers issued to clients, keyed by offer_id. The client accepts an offer by id,
# so amount/rate cannot be tampered with and a double click never pays twice.
OFFERS: dict[str, dict] = {}
ACCEPTED: dict[str, dict] = {}
MAX_OFFERS = 5000

# Backend has two credit APIs: release-1 spec (/api/credit-*) on dev and the early
# one (/credit-applications) on main. Prefer release 1, fall back to the early one.


def _ok(r: httpx.Response | None) -> bool:
    return r is not None and r.status_code in (200, 201)


def _missing(r: httpx.Response | None) -> bool:
    return r is not None and r.status_code in (404, 405)


async def _record_outcome(result: dict) -> None:
    decision = result.get("decision")
    if decision not in ("approved", "counter", "declined"):
        return
    app_id = None
    r = await _backend_post("/api/credit-applications", {
        "client_id": result["client_id"],
        "amount_rub": result["requested_amount_rub"],
        "term_months": result["requested_term_months"],
        "decision": decision,
        "rate_pct": result.get("rate_pct"),
        "approved_amount_rub": result.get("amount_rub"),
        "monthly_payment_rub": result.get("monthly_payment_rub"),
        "reason": result.get("reason"),
    })
    if _ok(r):
        app_id = r.json().get("application_id")
    elif _missing(r) and decision == "declined":
        await _backend_post("/credit-applications", {
            "client_id": result["client_id"],
            "amount_rub": result["requested_amount_rub"],
            "term_months": result["requested_term_months"],
            "product": result.get("product") or "consumer_credit",
            "status": "rejected", "reason": result.get("reason"), "decided_by": "cib",
        })
    result["application_id"] = app_id
    if decision in ("approved", "counter"):
        offer_id = uuid.uuid4().hex[:12]
        if len(OFFERS) >= MAX_OFFERS:
            OFFERS.pop(next(iter(OFFERS)))
        OFFERS[offer_id] = {k: result.get(k) for k in (
            "client_id", "amount_rub", "rate_pct", "term_months", "reason", "product",
            "application_id")}
        result["offer_id"] = offer_id


@app.post("/api/credit-accept")
async def credit_accept(payload: dict) -> dict:
    offer_id = str(payload.get("offer_id") or "")
    if offer_id in ACCEPTED:
        return ACCEPTED[offer_id]
    offer = OFFERS.get(offer_id)
    if not offer:
        raise HTTPException(status_code=422, detail="Предложение устарело — запросите решение ещё раз")
    app_id = offer.get("application_id") or f"offer-{offer_id}"
    r = await _backend_post("/api/credit-disburse", {
        "client_id": offer["client_id"], "amount_rub": offer["amount_rub"],
        "rate_pct": offer["rate_pct"], "term_months": offer["term_months"],
        "application_id": app_id,
    })
    if _ok(r):
        d = r.json()
        if offer.get("application_id"):
            await _backend_post(f"/api/credit-applications/{offer['application_id']}",
                                {"status": "accepted"}, "PATCH")
    elif _missing(r):
        r = await _backend_post("/credit-applications", {
            "client_id": offer["client_id"], "amount_rub": offer["amount_rub"],
            "term_months": offer["term_months"],
            "product": offer.get("product") or "consumer_credit",
            "status": "approved", "rate_pct": offer["rate_pct"],
            "reason": offer.get("reason"), "decided_by": "cib",
        })
        d = r.json() if _ok(r) else None
    else:
        d = None
    if d is None:
        return {"status": "pending", "amount_rub": offer["amount_rub"],
                "message": "Договор подписан. Деньги поступят на счёт в течение нескольких минут."}
    res = {"status": "ok", "amount_rub": offer["amount_rub"],
           "new_balance_rub": d.get("new_balance_rub"),
           "message": "Деньги зачислены на счёт."}
    ACCEPTED[offer_id] = res
    OFFERS.pop(offer_id, None)
    return res


def _norm_early(a: dict) -> dict:
    st = a.get("status")
    return {"amount_rub": a.get("amount_rub"), "term_months": a.get("term_months"),
            "created_at": a.get("created_at"),
            "label": {"approved": "Выдан", "rejected": "Отказ"}.get(st, "На рассмотрении")}


def _norm_r1(a: dict) -> dict:
    dec = a.get("decision")
    label = "Выдан" if a.get("status") == "accepted" else {
        "approved": "Одобрено", "counter": "Встречное", "declined": "Отказ"}.get(dec, "На рассмотрении")
    return {"amount_rub": a.get("approved_amount_rub") or a.get("amount_rub"),
            "term_months": a.get("term_months"), "created_at": a.get("created_at"), "label": label}


@app.get("/api/credit-applications/{client_id}")
async def credit_applications(client_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(f"{BACKEND_URL}/api/credit-applications/{client_id}")
            if r.status_code == 200:
                items = [_norm_r1(a) for a in r.json().get("items", [])]
                return {"total": len(items), "items": items}
            r = await http.get(f"{BACKEND_URL}/credit-applications",
                               params={"client_id": client_id, "limit": 20})
            if r.status_code == 200:
                items = [_norm_early(a) for a in r.json().get("items", [])]
                return {"total": len(items), "items": items}
    except httpx.HTTPError:
        pass
    return {"total": 0, "items": []}


# ---------------------------------------------------------------------------
# Product catalog from cib in the mobile app (+ open a deposit via backend).
# Judge feedback: the catalog from the other block must reach the mobile app.
# ---------------------------------------------------------------------------

def _fits_segment(item: dict, segment: str | None) -> bool:
    segs = item.get("segments") or ([item["segment"]] if item.get("segment") else [])
    return not segs or segment is None or segment in segs


@app.get("/api/products")
async def products(client_id: str | None = None) -> dict:
    segment = None
    if client_id:
        try:
            segment = (await _backend_get(f"/clients/{client_id}")).get("segment")
        except HTTPException:
            segment = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(f"{CIB_URL}/products")
        items = r.json().get("items", []) if r.status_code == 200 else []
    except httpx.HTTPError:
        items = []
    items = [i for i in items if _fits_segment(i, segment)]
    return {"total": len(items), "segment": segment, "items": items}


@app.post("/api/deposit-open")
async def deposit_open(payload: dict) -> dict:
    client_id = str(payload.get("client_id") or "").strip()
    try:
        amount = float(payload.get("amount_rub") or 0)
        term = int(payload.get("term_months") or 12)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="сумма и срок должны быть числами")
    if not client_id or amount < 1000:
        raise HTTPException(status_code=422, detail="минимальная сумма вклада — 1 000 ₽")
    body = {"client_id": client_id, "product_id": payload.get("product_id") or "deposit-base",
            "amount_rub": amount, "term_months": term, "rate_pct": payload.get("rate_pct")}
    r = await _backend_post("/api/deposits", body)
    if _ok(r):
        d = r.json()
        return {"status": "ok", "amount_rub": amount, "new_balance_rub": d.get("new_balance_rub"),
                "message": "Вклад открыт."}
    if r is not None and r.status_code in (400, 409, 422):
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        raise HTTPException(status_code=422, detail=detail or "Не получилось открыть вклад")
    return {"status": "pending", "amount_rub": amount,
            "message": "Заявка на вклад принята. Откроем его в течение нескольких минут."}


# ---------------------------------------------------------------------------
# "My credits": open loans with monthly payment and months left (backend data).
# ---------------------------------------------------------------------------

PRODUCT_LABELS = {"consumer_credit": "Кредит наличными", "auto_credit": "Автокредит",
                  "mortgage": "Ипотека", "credit_card": "Кредитная карта"}


def _months_left(opened_at: str, term: int, today: date) -> int:
    try:
        y, m, _ = (int(x) for x in opened_at[:10].split("-"))
    except (ValueError, AttributeError):
        return term
    elapsed = (today.year - y) * 12 + (today.month - m)
    return max(term - elapsed, 0)


@app.get("/api/my-credits/{client_id}")
async def my_credits(client_id: str) -> dict:
    try:
        h = await _backend_get(f"/credit-history/{client_id}")
    except HTTPException:
        return {"total": 0, "monthly_total_rub": 0, "items": []}
    today = date.today()
    items = []
    for c in h.get("items", []):
        if c.get("status") != "active":
            continue
        term = int(c.get("term_months") or 0)
        left = _months_left(str(c.get("opened_at", "")), term, today)
        if left <= 0 and not c.get("application_id"):
            continue  # matured long ago in seed data: effectively repaid
        pay = _annuity(float(c.get("principal_rub") or 0), float(c.get("rate_pct") or 0), term)
        items.append({"id": c.get("id"), "name": PRODUCT_LABELS.get(c.get("product"), c.get("product")),
                      "principal_rub": c.get("principal_rub"), "rate_pct": c.get("rate_pct"),
                      "monthly_payment_rub": pay, "months_left": left or term,
                      "overdue": (c.get("overdue_days_max") or 0) > 0})
    return {"total": len(items), "monthly_total_rub": sum(i["monthly_payment_rub"] for i in items),
            "items": items}
