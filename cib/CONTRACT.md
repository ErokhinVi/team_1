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
If approved: limit and rate by segment — mass/sme: 30% limit, 19–27% rate; mass_affluent: 40% limit, 18–26%; premium/private: 50% limit, 17–25%.
Returns 404 if customer not found.

### GET /products/brokerage
List of available stocks for trading. Returns `{"total": int, "items": [{"ticker", "company", "price_rub"}]}`.
Includes SBER, GAZP, LKOH, YNDX, MGNT with current mock prices in rubles.

### GET /brokerage/recommendation/{customer_id}
Personalised portfolio recommendation based on customer risk profile. Calls backend for customer data.
Returns `{"customer_id", "risk_score", "portfolio": [{"ticker", "allocation_pct"}], "note"}`.
Low risk score → more SBER and GAZP (defensive); high risk score → more YNDX (growth).
Returns 404 if customer not found.

### POST /brokerage/suitability
Brokerage suitability check. Accepts JSON `{"customer_id": "<id>"}`.
Returns `{"suitable": bool, "tier": "standard"|"premium"|null, "allowed_instruments": [...], "reason": "..."}`.
Rules: declined if income < 30,000 RUB/month or has overdue history.
Tiers by segment — standard (mass, sme): SBER, GAZP, LKOH, MGNT; mass_affluent: all 5 tickers; premium/private: full range + structured products.
Response includes allowed_tickers list.
Returns 404 if customer not found.

### POST /corporate/payment-auth
Corporate payment authorisation. Accepts JSON:
`{"corporate_client_id": "<id>", "amount_rub": float, "counterparty": "<name>", "purpose": "<optional>"}`.
Checks: sufficient balance, no overdue obligations, large payments (>5M RUB) require premium segment.
Returns `{"approved": bool, "reason": "...", "amount_rub"?, "counterparty"?}`.
Returns 404 if client not found.

## Corporate banking — agreed standards

These are the team agreements for the corporate feature. All three blocks follow these.

### Corporate client ID format
All corporate clients use the prefix `corp-` followed by a five-digit number, e.g. `corp-00001`.
This distinguishes corporate clients from personal clients (who use `c-` prefix) in every API call.

### Corporate account fields
A corporate client object must contain at minimum:
- `id` — e.g. `corp-00001`
- `name` — company name
- `sector` — e.g. `retail`, `manufacturing`, `energy`, `finance`
- `balance_rub` — current account balance in roubles
- `revenue_rub` — monthly revenue (equivalent of personal income)
- `has_overdue_history` — boolean, same flag as on personal side
- `segment` — `sme` for standard corporate clients, `premium` for large corporates

### Payment authorisation rules
Every corporate payment goes through `POST /corporate/payment-auth` before backend executes it.
Rules applied in order:
1. Decline if `amount_rub > balance_rub` (insufficient funds)
2. Decline if `has_overdue_history` is true (overdue obligations)
3. Decline if `amount_rub > 5,000,000` and segment is not `premium` (large payment limit)
4. Otherwise approve

### Integration flow
1. Retail fetches corporate account balance from backend `GET /clients/{corp_id}`
2. Company employee enters payment details in the corporate screen
3. Retail calls `POST /corporate/payment-auth` on cib
4. If approved, retail calls backend to execute the transfer
5. Retail shows confirmation to the employee

## Кого я зову у соседей

- backend: `GET /clients/{client_id}` — to fetch customer income for the credit decision
- retail: я никого не зову у retail — это retail зовёт меня

## Где работает блок локально

`http://localhost:8002` (порт фиксируется docker-compose).
