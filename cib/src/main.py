"""Блок cib — корпоратив и бизнес-логика банка команды.

Каталог продуктов и (в рамках задачи) логика кредитного решения.
За данными клиента ходит в backend по BACKEND_URL. Логику решения
(POST /credit/decide) и кредитный продукт добавляет владелец блока.
Хелпер src/llm.py — для человеческого объяснения решения.
"""
from __future__ import annotations

import asyncio
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

TEAM_NAME = os.environ.get("TEAM_NAME", "team")
COMMIT = os.environ.get("RENDER_GIT_COMMIT", "local")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://raif-a-backend.onrender.com").rstrip("/")

PRODUCTS = [
    {"id": "card-debit", "kind": "card", "name": "Дебетовая карта", "segment": "mass"},
    {"id": "deposit-base", "kind": "deposit", "name": "Срочный депозит", "rate_pct": 14.0},
    {"id": "card-credit", "kind": "card", "name": "Кредитная карта", "segment": "mass"},
    {"id": "brokerage-standard", "kind": "brokerage", "name": "Брокерский счёт", "segment": "mass"},
    {"id": "brokerage-premium", "kind": "brokerage", "name": "Брокерский счёт Премиум", "segment": "premium"},
    {"id": "corp-current-account", "kind": "corporate", "name": "Corporate Current Account", "segment": "sme"},
    {"id": "corp-payments", "kind": "corporate", "name": "Corporate Payments Service", "segment": "sme"},
]


class CreditDecisionRequest(BaseModel):
    customer_id: str


class SuitabilityRequest(BaseModel):
    customer_id: str


class CorpPaymentAuthRequest(BaseModel):
    corporate_client_id: str
    amount_rub: float
    counterparty: str
    purpose: str = ""


class PayrollValidateRequest(BaseModel):
    employer_id: str

app = FastAPI(title="cib — корпоратив и бизнес-логика", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "team": TEAM_NAME, "block": "cib",
            "commit": COMMIT, "backend_url": BACKEND_URL, "products": len(PRODUCTS)}


@app.get("/products")
async def products() -> dict:
    return {"total": len(PRODUCTS), "items": PRODUCTS}


@app.post("/credit-decision")
async def credit_decision(req: CreditDecisionRequest) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BACKEND_URL}/clients/{req.customer_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Customer not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Backend unavailable")
    customer = resp.json()
    income_rub = customer.get("income_rub", 0)
    has_overdue = customer.get("has_overdue_history", False)
    risk_score = customer.get("risk_score", 0.5)

    if income_rub <= 0:
        return {"approved": False, "credit_limit_rub": 0, "rate_pct": None,
                "reason": "No confirmed income on record"}

    if has_overdue:
        return {"approved": False, "credit_limit_rub": 0, "rate_pct": None,
                "reason": "Declined: history of overdue payments on record"}

    segment = customer.get("segment", "mass")
    if segment in ("premium", "private"):
        limit_multiplier, rate_base = 0.50, 17.0
    elif segment == "mass_affluent":
        limit_multiplier, rate_base = 0.40, 18.0
    else:
        limit_multiplier, rate_base = 0.30, 19.0
    limit = int(income_rub * 12 * limit_multiplier)
    rate_pct = round(rate_base + risk_score * 8.0, 1)

    return {"approved": True, "credit_limit_rub": limit, "rate_pct": rate_pct,
            "reason": f"Approved: income {income_rub} RUB/month, no overdue history; rate reflects individual risk profile"}


STOCKS = [
    {"ticker": "SBER", "company": "Сбербанк", "price_rub": 312.50},
    {"ticker": "GAZP", "company": "Газпром", "price_rub": 163.20},
    {"ticker": "LKOH", "company": "Лукойл", "price_rub": 7_450.00},
    {"ticker": "YNDX", "company": "Яндекс", "price_rub": 4_120.00},
    {"ticker": "MGNT", "company": "Магнит", "price_rub": 5_890.00},
]


@app.get("/products/brokerage")
async def brokerage_products() -> dict:
    return {"total": len(STOCKS), "items": STOCKS}


@app.get("/brokerage/recommendation/{customer_id}")
async def brokerage_recommendation(customer_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BACKEND_URL}/clients/{customer_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Customer not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Backend unavailable")
    customer = resp.json()
    risk_score = customer.get("risk_score", 0.5)

    # Low risk (score near 0) → defensive stocks; high risk (score near 1) → growth stocks
    sber = round(30 - risk_score * 15, 1)
    gazp = round(25 - risk_score * 10, 1)
    lkoh = round(20.0, 1)
    yndx = round(10 + risk_score * 20, 1)
    mgnt = round(100 - sber - gazp - lkoh - yndx, 1)

    return {
        "customer_id": customer_id,
        "risk_score": risk_score,
        "portfolio": [
            {"ticker": "SBER", "allocation_pct": sber},
            {"ticker": "GAZP", "allocation_pct": gazp},
            {"ticker": "LKOH", "allocation_pct": lkoh},
            {"ticker": "YNDX", "allocation_pct": yndx},
            {"ticker": "MGNT", "allocation_pct": mgnt},
        ],
        "note": "Allocation shifts from defensive (SBER, GAZP) to growth (YNDX) based on risk profile"
    }


@app.post("/brokerage/suitability")
async def brokerage_suitability(req: SuitabilityRequest) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BACKEND_URL}/clients/{req.customer_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Customer not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Backend unavailable")
    customer = resp.json()
    income_rub = customer.get("income_rub", 0)
    segment = customer.get("segment", "mass")
    has_overdue = customer.get("has_overdue_history", False)

    if income_rub < 30_000:
        return {"suitable": False, "tier": None,
                "allowed_instruments": [],
                "reason": "Minimum income of 30,000 RUB/month required to open a brokerage account"}

    if has_overdue:
        return {"suitable": False, "tier": None,
                "allowed_instruments": [],
                "reason": "Brokerage account unavailable: history of overdue payments on record"}

    if segment in ("premium", "private"):
        return {"suitable": True, "tier": "premium",
                "allowed_instruments": ["stocks", "bonds", "etf", "structured_products"],
                "allowed_tickers": ["SBER", "GAZP", "LKOH", "YNDX", "MGNT"],
                "reason": f"{segment.capitalize()} customer: full instrument range available"}

    if segment == "mass_affluent":
        return {"suitable": True, "tier": "mass_affluent",
                "allowed_instruments": ["stocks", "bonds", "etf"],
                "allowed_tickers": ["SBER", "GAZP", "LKOH", "YNDX", "MGNT"],
                "reason": "Mass affluent customer: full stock range available"}

    return {"suitable": True, "tier": "standard",
            "allowed_instruments": ["stocks", "bonds", "etf"],
            "allowed_tickers": ["SBER", "GAZP", "LKOH", "MGNT"],
            "reason": "Standard customer: defensive stocks (SBER, GAZP, LKOH, MGNT), bonds and ETFs available"}


@app.post("/corporate/payment-auth")
async def corporate_payment_auth(req: CorpPaymentAuthRequest) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BACKEND_URL}/corporate/accounts/{req.corporate_client_id}")

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Corporate client not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Backend unavailable")

    client_data = resp.json()
    balance_rub = client_data.get("balance_rub", 0)
    has_overdue = client_data.get("has_overdue_history", False)
    segment = client_data.get("segment", "sme")

    # Hard block: insufficient funds
    if req.amount_rub > balance_rub:
        return {"approved": False, "reason": f"Insufficient funds: balance {balance_rub:,.0f} RUB, requested {req.amount_rub:,.0f} RUB"}

    # Hard block: overdue obligations
    if has_overdue:
        return {"approved": False, "reason": "Payment blocked: client has overdue obligations on record"}

    # Large payment threshold — extra scrutiny above 5M RUB
    large_payment_threshold = 5_000_000
    if req.amount_rub > large_payment_threshold and segment not in ("premium", "private"):
        return {"approved": False, "reason": f"Payments above {large_payment_threshold:,} RUB require premium corporate status; please contact your relationship manager"}

    return {
        "approved": True,
        "corporate_client_id": req.corporate_client_id,
        "amount_rub": req.amount_rub,
        "counterparty": req.counterparty,
        "reason": "Payment authorised: funds available, no overdue obligations"
    }


@app.post("/payroll/validate")
async def payroll_validate(req: PayrollValidateRequest) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        employer_resp, employees_resp = await asyncio.gather(
            client.get(f"{BACKEND_URL}/clients/{req.employer_id}"),
            client.get(f"{BACKEND_URL}/corporate/{req.employer_id}/employees"),
        )

    if employer_resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Employer not found")
    if employer_resp.status_code != 200 or employees_resp.status_code not in (200, 404):
        raise HTTPException(status_code=502, detail="Backend unavailable")

    employer = employer_resp.json()
    balance_rub = employer.get("balance_rub", 0)
    has_overdue = employer.get("has_overdue_history", False)

    if has_overdue:
        return {"eligible": False, "reason": "Employer has overdue obligations on record", "total_payroll_rub": 0, "employees_count": 0}

    if employees_resp.status_code == 404:
        return {"eligible": False, "reason": "No employees found for this employer", "total_payroll_rub": 0, "employees_count": 0}

    employees = employees_resp.json().get("items", [])
    if not employees:
        return {"eligible": False, "reason": "No employees found for this employer", "total_payroll_rub": 0, "employees_count": 0}

    total_payroll_rub = sum(int(e.get("income_rub", 0)) for e in employees)

    if balance_rub < total_payroll_rub:
        return {"eligible": False,
                "reason": f"Insufficient funds: balance {balance_rub:,.0f} RUB, payroll {total_payroll_rub:,.0f} RUB",
                "total_payroll_rub": total_payroll_rub, "employees_count": len(employees)}

    return {"eligible": True, "reason": "Employer is eligible: sufficient funds and no overdue history",
            "total_payroll_rub": total_payroll_rub, "employees_count": len(employees)}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    kind_labels = {"card": "💳 Card", "deposit": "🏦 Deposit", "brokerage": "📈 Brokerage"}
    product_cards = ""
    for p in PRODUCTS:
        kind = kind_labels.get(p["kind"], p["kind"])
        extra = f'<p class="rate">Rate: {p["rate_pct"]}%</p>' if "rate_pct" in p else ""
        segment = f'<span class="badge">{p.get("segment","all")}</span>' if "segment" in p else ""
        product_cards += f"""
        <div class="card">
            <div class="card-top">{kind}{segment}</div>
            <div class="card-name">{p["name"]}</div>
            {extra}
            <div class="card-id">{p["id"]}</div>
        </div>"""

    stock_rows = "".join(
        f'<tr><td><strong>{s["ticker"]}</strong></td><td>{s["company"]}</td>'
        f'<td class="price">{s["price_rub"]:,.2f} ₽</td></tr>'
        for s in STOCKS
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CIB · Raiffeisen</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,-apple-system,sans-serif;background:#0c0d10;color:#e8e9ec;padding:40px 32px;max-width:960px;margin:0 auto}}
h1{{font-size:1.6rem;font-weight:600;margin-bottom:4px}}
.subtitle{{color:#888;font-size:.95rem;margin-bottom:40px}}
h2{{font-size:1.1rem;font-weight:500;margin-bottom:16px;color:#aaa;text-transform:uppercase;letter-spacing:.05em}}
.section{{margin-bottom:48px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}}
.card{{background:#16181f;border:1px solid #23262f;border-radius:12px;padding:20px}}
.card-top{{font-size:.8rem;color:#888;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}}
.card-name{{font-size:1rem;font-weight:500;margin-bottom:8px}}
.rate{{font-size:.85rem;color:#4ade80;margin-bottom:8px}}
.card-id{{font-size:.75rem;color:#555;font-family:monospace}}
.badge{{background:#1e2433;color:#7aa2f7;border-radius:4px;padding:2px 6px;font-size:.7rem}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #23262f;padding:10px 14px;text-align:left;font-size:.9rem}}
th{{background:#16181f;color:#888;font-weight:500}}
.price{{font-family:monospace;color:#4ade80}}
.api-list{{list-style:none;display:flex;flex-direction:column;gap:8px}}
.api-list li{{background:#16181f;border:1px solid #23262f;border-radius:8px;padding:12px 16px;font-size:.88rem;font-family:monospace}}
.method{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:.75rem;margin-right:8px;font-weight:600}}
.get{{background:#1a3a2a;color:#4ade80}}.post{{background:#2a1a3a;color:#c084fc}}
</style></head><body>
<h1>CIB — Business Logic & Products</h1>
<p class="subtitle">Team: {TEAM_NAME} &nbsp;·&nbsp; {len(PRODUCTS)} products &nbsp;·&nbsp; Decision engine for credit &amp; brokerage</p>

<div class="section">
<h2>Product Catalogue</h2>
<div class="grid">{product_cards}</div>
</div>

<div class="section">
<h2>Brokerage — Available Stocks</h2>
<table><tr><th>Ticker</th><th>Company</th><th>Price</th></tr>{stock_rows}</table>
</div>

<div class="section">
<h2>API Endpoints</h2>
<ul class="api-list">
<li><span class="method get">GET</span>/products — full product catalogue</li>
<li><span class="method get">GET</span>/products/brokerage — tradeable stocks</li>
<li><span class="method post">POST</span>/credit-decision — credit card approval (income + risk + segment)</li>
<li><span class="method post">POST</span>/brokerage/suitability — investor suitability check</li>
<li><span class="method get">GET</span>/brokerage/recommendation/{{customer_id}} — personalised portfolio</li>
</ul>
</div>
</body></html>"""
