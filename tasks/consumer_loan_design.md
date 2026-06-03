# Consumer Loan — Personal Loan for Any Purpose

## What this is

A new lending product for individual clients. A customer opens the mobile bank,
goes to a new "Кредит" tab, fills in the amount they want and the term in months,
and gets an instant decision. If approved, the money lands in their account
immediately. The feature is complete when all three blocks are connected.

---

## How the three blocks connect

```
retail  →  CIB:     POST /loan/decision      (approve/decline, set rate and term)
retail  →  backend: POST /loans              (disburse the loan to the account)
CIB     →  backend: GET  /clients/{id}       (check income, overdue, risk score)
```

Customer flow:
1. Customer opens the "Кредит" tab in the mobile bank.
2. They enter the desired amount (e.g. 200 000 ₽) and term (e.g. 24 months).
3. Retail calls CIB `POST /loan/decision` → gets approved/declined, rate, monthly payment.
4. If approved, customer sees the offer and clicks "Получить деньги".
5. Retail calls backend `POST /loans` → loan is created, money credited to account.
6. Customer sees their new balance and loan summary.

---

## Block responsibilities

### retail — Nikita Patrakhin

Add a "Кредит" tab to the main mobile bank page (index.html), next to
"Кредитная карта".

The tab must contain:
- A dropdown to select the client (reuse the existing client selector logic).
- An amount input (min 10 000, max 5 000 000 ₽).
- A term selector: 6, 12, 24, 36, 60 months.
- A "Рассчитать и подать заявку" button.

On button click:
1. Call `POST /api/loan/decision` with `{customer_id, amount_rub, term_months}`.
2. If `approved: false` — show reason, stop.
3. If `approved: true` — show the offer card:
   - Approved amount
   - Monthly payment
   - Annual rate (%)
   - A "Получить деньги" confirm button
4. On confirm — call `POST /api/loan/disburse` with
   `{customer_id, amount_rub, term_months, rate_pct}`.
5. Show result: amount credited, new balance, loan ID.

Add two proxy endpoints to `retail/src/main.py`:

```
POST /api/loan/decision
  → calls CIB POST /loan/decision
     with {customer_id, amount_rub, term_months}
  ← {approved, reason, amount_rub, term_months,
     rate_pct, monthly_payment_rub}

POST /api/loan/disburse
  → calls backend POST /loans
     with {customer_id, amount_rub, term_months, rate_pct}
  ← {loan_id, customer_id, amount_rub, term_months,
     rate_pct, monthly_payment_rub, new_balance_rub}
```

Update CONTRACT.md after.

---

### CIB

Add one endpoint:

```
POST /loan/decision
  body:    {customer_id: str, amount_rub: int, term_months: int}
  returns: {approved: bool, reason: str,
            amount_rub: int, term_months: int,
            rate_pct: float, monthly_payment_rub: int}
```

Logic:
1. Call backend `GET /clients/{customer_id}` — get `income_rub`,
   `has_overdue_history`, `risk_score`, `segment`.
2. Decline if `has_overdue_history: true`.
3. Decline if `income_rub * 12 < amount_rub * 0.3`
   (loan must not exceed 3.3× annual income).
4. Set rate by segment and risk score:
   - mass / sme: 18–25% (lower risk_score → lower rate)
   - mass_affluent: 15–22%
   - premium / private: 12–18%
5. Compute `monthly_payment_rub` using standard annuity formula:
   `M = P * r / (1 - (1+r)^(-n))` where P=amount, r=rate/12/100, n=term_months.
   Round to nearest 100 ₽.
6. Decline if `monthly_payment_rub > income_rub * 0.4`
   (monthly payment must not exceed 40% of monthly income).
7. Return approved decision with all fields.

Update CONTRACT.md after.

---

### backend

Add one endpoint:

```
POST /loans
  body:    {customer_id: str, amount_rub: int,
            term_months: int, rate_pct: float}
  returns: {loan_id: str, customer_id, amount_rub, term_months,
            rate_pct, monthly_payment_rub: int, new_balance_rub: int}
```

Logic:
1. Look up client — return 404 if not found.
2. Generate `loan_id` (e.g. `loan-{uuid4_short}`).
3. Add `amount_rub` to client's `balance_rub`.
4. Store the loan record in memory (same pattern as credit cards).
5. Compute `monthly_payment_rub` same formula as CIB uses.
6. Return loan summary with `new_balance_rub`.

Update CONTRACT.md after.

---

## Exact field names — use these consistently

| Field                 | Type  | Description                              |
|-----------------------|-------|------------------------------------------|
| `customer_id`         | str   | Client ID                                |
| `amount_rub`          | int   | Loan amount in roubles                   |
| `term_months`         | int   | Loan term in months (6/12/24/36/60)      |
| `rate_pct`            | float | Annual interest rate, e.g. 19.5          |
| `monthly_payment_rub` | int   | Monthly annuity payment                  |
| `new_balance_rub`     | int   | Client balance after loan disbursement   |
| `loan_id`             | str   | Unique loan identifier                   |

---

## Build order and instructions

**Step 1 — backend** builds `POST /loans` and updates CONTRACT.md.
Prompt for backend: "Read tasks/consumer_loan_design.md and build the backend part."

**Step 2 — CIB** builds `POST /loan/decision` and updates CONTRACT.md.
Prompt for CIB: "Read tasks/consumer_loan_design.md and build the CIB part."

**Step 3 — retail (Nikita)** — tell me "they are done" and I will add the
loan tab to the mobile bank and wire up both proxy endpoints. No need to
write a prompt — I will read this file and build it myself.

All three steps can run in parallel since none depends on the other being
live — only the final end-to-end test needs all three up.

---

## Definition of done

- Customer opens the "Кредит" tab.
- Enters amount and term, clicks apply.
- Sees the offer: amount, rate, monthly payment.
- Clicks confirm — money appears in their account instantly.
- Balance on the main screen increases by the loan amount.
