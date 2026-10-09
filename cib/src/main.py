"""Product catalog and preliminary credit decisions using backend data."""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .credit import (
    CREDIT_PRODUCT, POLICY_VERSION, ClientData, CreditDecision, CreditRequest,
    HistoryData, LoanQuote, LoanRequest, decide, quote,
)

TEAM_NAME = os.environ.get("TEAM_NAME", "team")
COMMIT = os.environ.get("RENDER_GIT_COMMIT", "local")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8003").rstrip("/")

# Keep existing products alongside the workshop consumer-credit product.
PRODUCTS = [
    {"id": "card-debit", "kind": "card", "name": "Дебетовая карта", "segment": "mass"},
    {"id": "deposit-base", "kind": "deposit", "name": "Срочный депозит", "rate_pct": 14.0},
    CREDIT_PRODUCT,
]

app = FastAPI(title="cib — корпоратив и бизнес-логика", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "team": TEAM_NAME, "block": "cib",
            "commit": COMMIT, "backend_url": BACKEND_URL, "products": len(PRODUCTS),
            "credit_policy_version": POLICY_VERSION}


@app.get("/products")
async def products() -> dict:
    return {"total": len(PRODUCTS), "items": PRODUCTS}


@app.get("/", response_class=FileResponse)
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/credit/calculate", response_model=LoanQuote)
async def calculate_credit(payload: LoanRequest):
    """Illustrative quote at the minimum rate; does not make a credit decision."""
    return quote(payload.amount_rub, payload.term_months, Decimal("19.9"))


async def load_credit_data(client_id: str) -> tuple[ClientData, HistoryData]:
    """Read published backend contracts. Never create applications or issue money."""
    try:
        async with asyncio.timeout(8), httpx.AsyncClient(
            timeout=httpx.Timeout(5.0), follow_redirects=False
        ) as client:
            # Reuse one connection and avoid a second read for unknown clients.
            person_response = await client.get(f"{BACKEND_URL}/clients/{client_id}")
            if person_response.status_code == 404:
                raise HTTPException(404, "Клиент не найден.")
            if person_response.status_code != 200:
                raise HTTPException(503, "Данные клиента временно недоступны.")
            history_response = await client.get(f"{BACKEND_URL}/credit-history/{client_id}")
    except (httpx.HTTPError, TimeoutError) as exc:
        raise HTTPException(503, "Данные банка временно недоступны. Попробуйте позже.") from exc

    if history_response.status_code != 200:
        raise HTTPException(503, "Не удалось получить полные данные для решения. Попробуйте позже.")
    try:
        person = ClientData.model_validate(person_response.json())
        history = HistoryData.model_validate(history_response.json())
        if person.id != client_id or history.client_id != client_id:
            raise ValueError("Upstream returned a different client")
    except (ValidationError, ValueError) as exc:
        raise HTTPException(503, "Данные для решения неполны или противоречивы. Нужна проверка банка.") from exc
    return person, history


@app.post("/credit/decide", response_model=CreditDecision)
async def decide_credit(payload: CreditRequest):
    """Preliminary decision from server-side client data and debt history."""
    person, history = await load_credit_data(payload.client_id)
    return decide(payload, person, history)
