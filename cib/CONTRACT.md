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

### GET /products/bonds
Bond catalogue for retail customers. Returns `{total, items: [{bond_id, issuer, name, kind, coupon_pct, maturity_date, face_value_rub, price_rub}]}`.
`kind` is `government` (OFZ, safer, ~11–12% coupon) or `corporate` (Sber/Gazp/Lukoil, ~15–17% coupon).
Includes OFZ-26240, OFZ-26244, SBER-001P, GAZP-002P, LKOH-001.

### GET /bonds/recommendation/{customer_id}
Personalised bond mix based on customer risk profile. Calls backend `GET /clients/{id}`.
Returns `{customer_id, risk_score, recommendation: [{bond_id, allocation_pct}], note}`.
Low risk_score → mostly safe government OFZ; high risk_score → more higher-coupon corporate bonds.
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
Rules: minimum 10,000 RUB; term 3–36 months.
Rate = 20% base + segment bonus (mass/sme: +0%, mass_affluent: +1%, premium/private: +2%), so 20–22%.
Retail must forward this `rate_pct` to backend `POST /deposits` so the customer is actually paid the quoted rate.
Returns 404 if customer not found.

### POST /loan/decision
Consumer loan decision. Accepts JSON `{"customer_id": "<id>", "amount_rub": int, "term_months": int}`.
Returns `{"approved": bool, "reason": "...", "amount_rub": int, "term_months": int, "rate_pct": float|null, "monthly_payment_rub": int|null}`.
Rules (in order): minimum 10,000 RUB; term must be 6/12/24/36/60 months; no overdue history;
loan ≤ 3.3× annual income (5× for premium/private); monthly payment ≤ 40% of monthly income.
Rate by segment — mass/sme: 18–25%; mass_affluent: 15–22%; premium/private: 12–18% (adjusted by risk score).
Monthly payment uses standard annuity formula, rounded to nearest 100 RUB.
Returns 404 if customer not found.

### POST /mortgage/decision
Mortgage (home loan) decision. Accepts JSON `{"customer_id": "<id>", "property_price_rub": int, "down_payment_rub": int, "term_years": int}`.
Returns `{approved, reason, loan_amount_rub, property_price_rub, down_payment_rub, term_years, rate_pct, monthly_payment_rub}`.
Rules (in order): loan_amount = price − down payment, declined if ≤ 0; term must be 10/15/20/25/30 years;
no overdue history; down payment ≥ 15% of price; loan ≤ 8× annual income; monthly payment ≤ 50% of monthly income.
Rate by segment (cheaper than consumer loans — property is collateral): mass/sme 14–17%; mass_affluent 12–15%; premium/private 9–13% (adjusted by risk score).
Monthly payment uses the standard annuity formula over term_years×12 months, rounded to nearest 100 RUB.
Retail must forward this `rate_pct` to backend `POST /mortgages` so the registered rate matches the quoted one.
Returns 404 if customer not found.

### POST /payroll/validate
Payroll eligibility check for a corporate employer. Accepts JSON `{"employer_id": "<id>"}`.
Calls backend `GET /corporate/accounts/{employer_id}` for employer data and
`GET /corporate/{employer_id}/roster` for the FULL staff roster (including
employees who are not yet bank customers — payroll is an acquisition channel).
Sums all roster `income_rub` values into `total_payroll_rub`.
Returns `{"eligible": bool, "reason": "...", "total_payroll_rub": int, "employees_count": int}`.
Declined if: employer has overdue history, empty roster, or balance < total payroll.
Note: corporate accounts don't carry an overdue flag, so a missing flag is treated as "none on record"; the affordability check (balance ≥ payroll) is the effective gate.
Returns 404 if employer not found.
Example request with a real seeded employer: `{"employer_id": "corp-001"}`.

### POST /corporate/payment-auth
Corporate payment authorisation. Accepts JSON:
`{"corporate_client_id": "<id>", "amount_rub": float, "counterparty": "<name>", "purpose": "<optional>"}`.
Checks: sufficient balance; large payments (>5M RUB) are declined only when the amount also exceeds the company's monthly turnover (manual review needed).
Returns `{"approved": bool, "reason": "...", "amount_rub"?, "counterparty"?}`.
Returns 404 if client not found.
Example request with real seeded corporate account ids:
`{"corporate_client_id": "corp-001", "amount_rub": 1000, "counterparty": "corp-002", "purpose": "Supplier payment"}`.

## Corporate banking — agreed standards

These are the team agreements for the corporate feature. All three blocks follow these.

### Corporate client ID format
All corporate clients use the prefix `corp-` followed by a three-digit number,
e.g. `corp-001`, `corp-002`, `corp-003`. Personal customers use `c-` ids
like `c-01394`; those ids are invalid for corporate payments and payroll.

### Corporate account fields
A corporate client object must contain at minimum:
- `id` — e.g. `corp-001`
- `name` — company name
- `industry` — e.g. `retail`, `manufacturing`, `energy`, `finance`
- `balance_rub` — current account balance in roubles
- `monthly_turnover_rub` — monthly turnover
- `opened_at` — account opening date

### Payment authorisation rules
Every corporate payment goes through `POST /corporate/payment-auth` before backend executes it.
Rules applied in order:
1. Decline if `amount_rub > balance_rub` (insufficient funds)
2. Decline if `amount_rub > 5,000,000` and `amount_rub > monthly_turnover_rub` (large payment beyond turnover → manual review)
3. Otherwise approve

Note: backend's corporate accounts carry `id, name, industry, balance_rub, monthly_turnover_rub, opened_at` — they do not carry a `segment` or `has_overdue_history` field, so authorisation relies on balance and turnover only.

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
