"""Блок cib — корпоратив и бизнес-логика банка команды.

Каталог продуктов и (в рамках задачи) логика кредитного решения.
За данными клиента ходит в backend по BACKEND_URL. Логику решения
(POST /credit/decide) и кредитный продукт добавляет владелец блока.
Хелпер src/llm.py — для человеческого объяснения решения.
"""
from __future__ import annotations

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
]


class CreditDecisionRequest(BaseModel):
    customer_id: str


class SuitabilityRequest(BaseModel):
    customer_id: str

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


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    rows = "".join(
        f"<tr><td>{p['id']}</td><td>{p['kind']}</td><td>{p['name']}</td></tr>"
        for p in PRODUCTS
    )
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>cib · Райффайзен</title><style>"
        "body{font-family:system-ui;background:#0c0d10;color:#e8e9ec;padding:32px}"
        "h1{font-weight:500}table{border-collapse:collapse;margin-top:16px}"
        "td,th{border:1px solid #23262f;padding:8px 14px;text-align:left}"
        "</style></head><body>"
        "<h1>cib — корпоратив и бизнес-логика</h1>"
        f"<p>Команда: {TEAM_NAME}. Каталог продуктов:</p>"
        f"<table><tr><th>id</th><th>вид</th><th>название</th></tr>{rows}</table>"
        "</body></html>"
    )
