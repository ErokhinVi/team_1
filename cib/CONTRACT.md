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

### POST /deposit/terms
Personalised deposit offer. Accepts JSON `{"customer_id": "<id>", "amount_rub": int, "term_months": int}`.
Returns `{"approved": bool, "reason": "...", "rate_pct": float|null, "term_months": int, "amount_rub": int}`.
Rules: minimum 10,000 RUB; term 3–36 months; no overdue history.
Rate by segment — mass/sme: 20%; mass_affluent: 21%; premium/private: 22%.
Returns 404 if customer not found.

### POST /loan/decision
Consumer loan decision. Accepts JSON `{"customer_id": "<id>", "amount_rub": int, "term_months": int}`.
Returns `{"approved": bool, "reason": "...", "amount_rub": int, "term_months": int, "rate_pct": float|null, "monthly_payment_rub": int|null}`.
Rules (in order): minimum 10,000 RUB; term must be 6/12/24/36/60 months; no overdue history;
loan ≤ 3.3× annual income (5× for premium/private); monthly payment ≤ 40% of monthly income.
Rate by segment — mass/sme: 18–25%; mass_affluent: 15–22%; premium/private: 12–18% (adjusted by risk score).
Monthly payment uses standard annuity formula, rounded to nearest 100 RUB.
Returns 404 if customer not found.

### POST /payroll/validate
Payroll eligibility check for a corporate employer. Accepts JSON `{"employer_id": "<id>"}`.
Calls backend for employer data and employee list. Sums all employee `income_rub` values.
Returns `{"eligible": bool, "reason": "...", "total_payroll_rub": int, "employees_count": int}`.
Declined if: employer has overdue history, no employees found, or balance < total payroll.
Returns 404 if employer not found.

### POST /corporate/payment-auth
Corporate payment authorisation. Accepts JSON:
`{"corporate_client_id": "<id>", "amount_rub": float, "counterparty": "<name>", "purpose": "<optional>"}`.
Checks: sufficient balance, no overdue obligations, large payments (>5M RUB) require premium segment.
Returns `{"approved": bool, "reason": "...", "amount_rub"?, "counterparty"?}`.
Returns 404 if client not found.

## Corporate banking — agreed standards

These are the team agreements for the corporate feature. All three blocks follow these.

### Corporate client ID format
All corporate clients use the prefix `corp-` followed by a three-digit number, e.g. `corp-001` (seeded accounts: `corp-001`, `corp-002`, `corp-003`).
This distinguishes corporate clients from personal clients (who use `c-` prefix) in every API call.

### Corporate account fields
A corporate client object must contain at minimum:
- `id` — e.g. `corp-001`
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
1. Retail fetches corporate account balance from backend `GET /corporate/accounts/{corp_id}`
2. Company employee enters payment details in the corporate screen
3. Retail calls `POST /corporate/payment-auth` on cib
4. If approved, retail calls backend to execute the transfer
5. Retail shows confirmation to the employee

## Кого я зову у соседей

- backend: `GET /clients/{client_id}` — personal customer data for credit and brokerage decisions
- backend: `GET /corporate/accounts/{account_id}` — corporate account data for payment authorisation
- backend: `GET /corporate/{employer_id}/employees` — employee list for payroll validation
- retail: я никого не зову у retail — это retail зовёт меня

## Где работает блок локально

`http://localhost:8002` (порт фиксируется docker-compose).
