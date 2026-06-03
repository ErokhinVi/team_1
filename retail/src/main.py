"""Блок retail — клиентский мобильный банк команды.

UI плюс тонкий слой: за данными ходит в backend, за кредитным решением — в cib.
Своих данных не держит. Вкладку «Кредиты» и /api/credit-apply (оркестрацию
cib + backend) добавляет владелец блока в рамках задачи.
"""
from __future__ import annotations

import os
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


@app.get("/corporate", response_class=HTMLResponse)
async def corporate_page() -> str:
    f = STATIC_DIR / "corporate.html"
    return f.read_text(encoding="utf-8") if f.exists() else "<h1>Corporate Banking</h1>"


@app.get("/api/corporate/account/{account_id}")
async def corporate_account(account_id: str) -> dict:
    return await _backend_get(f"/corporate/accounts/{account_id}")


@app.post("/api/payroll/validate")
async def payroll_validate(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{CIB_URL}/payroll/validate", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/payroll/run")
async def payroll_run(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{BACKEND_URL}/payroll/run", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/corporate/payments")
async def corporate_payment(payload: dict) -> dict:
    from_account_id = payload.get("from_account_id") or payload.get("corporate_client_id")
    to_account_id = payload.get("to_account_id") or payload.get("counterparty")
    amount_rub = payload.get("amount_rub")
    purpose = payload.get("purpose")
    canonical_payload = {
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "amount_rub": amount_rub,
        "purpose": purpose,
    }
    auth_payload = {
        "corporate_client_id": from_account_id,
        "amount_rub": amount_rub,
        "counterparty": to_account_id,
        "purpose": purpose,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            auth_r = await client.post(f"{CIB_URL}/corporate/payment-auth",
                                       json=auth_payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if auth_r.status_code != 200:
        raise HTTPException(status_code=auth_r.status_code, detail=auth_r.text[:300])
    auth = auth_r.json()
    if not auth.get("approved"):
        return {"approved": False, "reason": auth.get("reason", "платёж не авторизован")}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            pay_r = await client.post(f"{BACKEND_URL}/corporate/payments", json=canonical_payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if pay_r.status_code != 200:
        raise HTTPException(status_code=pay_r.status_code, detail=pay_r.text[:300])
    return {**pay_r.json(), "approved": True}


@app.post("/api/loan/decision")
async def loan_decision(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{CIB_URL}/loan/decision", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/loan/disburse")
async def loan_disburse(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{BACKEND_URL}/loans", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/mortgage/decision")
async def mortgage_decision(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{CIB_URL}/mortgage/decision", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/mortgage/register")
async def mortgage_register(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{BACKEND_URL}/mortgages", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/deposit/terms")
async def deposit_terms(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{CIB_URL}/deposit/terms", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/deposit/open")
async def deposit_open(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{BACKEND_URL}/deposits", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.get("/api/deposit-product")
async def deposit_product() -> dict:
    try:
        data = await _cib_get("/products")
        items = data.get("items", [])
        product = next((p for p in items if p.get("id") == "deposit-base"), None)
        return product or {"id": "deposit-base", "name": "Вклад на срок", "rate_pct": 20.0}
    except Exception:
        return {"id": "deposit-base", "name": "Вклад на срок", "rate_pct": 20.0}


@app.get("/brokerage", response_class=HTMLResponse)
async def brokerage_page() -> str:
    f = STATIC_DIR / "brokerage.html"
    return f.read_text(encoding="utf-8") if f.exists() else "<h1>Brokerage</h1>"


@app.get("/bonds", response_class=HTMLResponse)
async def bonds_page() -> str:
    f = STATIC_DIR / "bonds.html"
    return f.read_text(encoding="utf-8") if f.exists() else "<h1>Bonds</h1>"


@app.get("/api/bonds/catalogue")
async def bonds_catalogue() -> dict:
    return await _cib_get("/products/bonds")


@app.get("/api/bonds/recommendation/{customer_id}")
async def bonds_recommendation(customer_id: str) -> dict:
    return await _cib_get(f"/bonds/recommendation/{customer_id}")


@app.get("/api/bonds/holdings/{customer_id}")
async def bonds_holdings(customer_id: str) -> dict:
    return await _backend_get(f"/bonds/holdings/{customer_id}")


@app.post("/api/bonds/orders")
async def bonds_order(payload: dict) -> dict:
    if not payload.get("customer_id"):
        raise HTTPException(status_code=400, detail="customer_id required")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{BACKEND_URL}/bonds/orders", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


async def _cib_get(path: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{CIB_URL}{path}", params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.get("/api/brokerage/stocks")
async def brokerage_stocks() -> dict:
    return await _cib_get("/products/brokerage")


@app.get("/api/brokerage/account/{customer_id}")
async def brokerage_account(customer_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{BACKEND_URL}/brokerage/accounts/{customer_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code == 404:
        # auto-open account
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r2 = await client.post(f"{BACKEND_URL}/brokerage/accounts",
                                       json={"customer_id": customer_id})
            if r2.status_code == 200:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(f"{BACKEND_URL}/brokerage/accounts/{customer_id}")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.get("/api/brokerage/recommendation/{customer_id}")
async def brokerage_recommendation(customer_id: str) -> dict:
    return await _cib_get(f"/brokerage/recommendation/{customer_id}")


@app.post("/api/brokerage/orders")
async def brokerage_order(payload: dict) -> dict:
    # Отсутствующий customer_id — это неверный запрос (400), а не «клиент не
    # найден» (404). Валидируем на входе, как в /api/credit-apply: иначе пустое
    # тело пробрасывалось в backend и возвращало 404, маскируя рабочую ручку.
    if not payload.get("customer_id"):
        raise HTTPException(status_code=400, detail="customer_id required")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{BACKEND_URL}/brokerage/orders", json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/api/credit-apply")
async def credit_apply(payload: dict) -> dict:
    customer_id = payload.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id required")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            cib_r = await client.post(f"{CIB_URL}/credit-decision",
                                      json={"customer_id": customer_id})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"cib недоступен: {exc}")
    if cib_r.status_code != 200:
        raise HTTPException(status_code=cib_r.status_code, detail=cib_r.text[:300])
    decision = cib_r.json()
    if not decision.get("approved"):
        return {"approved": False, "reason": decision.get("reason", "отказано")}
    credit_limit = decision.get("credit_limit_rub") or decision.get("limit", 0)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            card_r = await client.post(f"{BACKEND_URL}/credit-cards",
                                       json={"customer_id": customer_id,
                                             "credit_limit": credit_limit})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if card_r.status_code != 200:
        raise HTTPException(status_code=card_r.status_code, detail=card_r.text[:300])
    card = card_r.json()
    return {"approved": True, "reason": decision.get("reason", ""),
            "limit": credit_limit,
            "rate_pct": decision.get("rate_pct"),
            "card": card}


@app.get("/api/credit-cards")
async def get_credit_cards(customer_id: str) -> dict:
    return await _backend_get("/credit-cards", {"customer_id": customer_id})


@app.post("/api/credit-cards/{card_id}/activate")
async def activate_card(card_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{BACKEND_URL}/credit-cards/{card_id}/activate")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"backend недоступен: {exc}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()

# organizer re-eval trigger (no-op marker)
