# Контракт блока cib

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, backend_url, products}`.

### GET /products
Каталог продуктов команды. Возвращает `{total, items: [продукты]}`. Каждый
продукт — объект как минимум с `{id, kind, name}`; депозитные/кредитные могут
иметь `rate_pct`.

### GET /
HTML с каталогом продуктов. Для человека, не для других блоков.

### POST /credit-decision
Credit card approval decision. Accepts JSON `{"customer_id": "<id>"}`.
Calls backend for customer data and returns:
`{"approved": bool, "credit_limit_rub": int, "rate_pct": float|null, "reason": "..."}`.
Rules: declined if no income or if customer has overdue payment history.
If approved: limit = 30% of annual income (50% for premium-segment customers); rate_pct between 19.0 and 27.0 based on risk score (17.0–25.0 for premium customers).
Returns 404 if customer not found.

### POST /brokerage/suitability
Brokerage suitability check. Accepts JSON `{"customer_id": "<id>"}`.
Returns `{"suitable": bool, "tier": "standard"|"premium"|null, "allowed_instruments": [...], "reason": "..."}`.
Rules: declined if income < 30,000 RUB/month or has overdue history.
Standard customers (mass segment): bonds and ETFs only.
Premium customers: full range — stocks, bonds, ETFs, structured products.
Returns 404 if customer not found.

## Кого я зову у соседей

- backend: `GET /clients/{client_id}` — to fetch customer income for the credit decision
- retail: я никого не зову у retail — это retail зовёт меня

## Где работает блок локально

`http://localhost:8002` (порт фиксируется docker-compose).
