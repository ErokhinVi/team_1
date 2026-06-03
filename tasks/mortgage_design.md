# Mortgage — Home Loan for Property Purchase

## What this is

A new lending product: a mortgage. A customer opens the mobile bank, goes to a
new "Ипотека" tab, enters the property price, how much they can pay upfront
(the down payment), and the term in years. They get a decision with their
personal rate and monthly payment. If approved and they confirm, the mortgage
is registered and the loan amount is recorded against the property. The feature
is complete only when all three blocks are connected.

A mortgage differs from a normal consumer loan in three ways the blocks must
respect: there is a property price and a down payment (so the loan = price −
down payment); terms are long (10–30 years); and the rate is lower because the
property itself is collateral.

---

## How the three blocks connect

```
retail  →  CIB:     POST /mortgage/decision   (approve/decline, set rate + monthly payment)
retail  →  backend: POST /mortgages           (register the mortgage)
CIB     →  backend: GET  /clients/{id}        (check income, overdue, segment, risk)
```

Customer flow:
1. Customer opens the "Ипотека" tab.
2. Enters property_price_rub, down_payment_rub, term_years.
3. Retail calls CIB POST /mortgage/decision → approved/declined, rate, monthly payment.
4. If approved, customer sees the offer and clicks "Оформить ипотеку".
5. Retail calls backend POST /mortgages → mortgage registered.
6. Customer sees confirmation: loan amount, rate, monthly payment, mortgage id.

---

## Block responsibilities

### retail — Nikita Patrakhin

Add an "Ипотека" tab to the mobile bank (index.html), and a home-screen
banner-button that opens it (same pattern as the consumer-loan banner).

The tab contains:
- A client selector (reuse existing pattern).
- property_price_rub input (min 500 000).
- down_payment_rub input (min 0).
- term_years selector: 10, 15, 20, 25, 30 years.
- A "Рассчитать ипотеку" button.

On click:
1. Call POST /api/mortgage/decision with
   {customer_id, property_price_rub, down_payment_rub, term_years}.
2. If approved:false — show reason, stop.
3. If approved:true — show offer card: loan amount, down payment, rate,
   monthly payment, and an "Оформить ипотеку" confirm button.
4. On confirm — call POST /api/mortgage/register with
   {customer_id, property_price_rub, down_payment_rub, loan_amount_rub,
    term_years, rate_pct}.
5. Show result: loan amount, monthly payment, rate, mortgage_id.

Add two proxy endpoints to retail/src/main.py:

```
POST /api/mortgage/decision
  → calls CIB POST /mortgage/decision
  ← {approved, reason, loan_amount_rub, property_price_rub,
     down_payment_rub, term_years, rate_pct, monthly_payment_rub}

POST /api/mortgage/register
  → calls backend POST /mortgages
  ← {mortgage_id, customer_id, property_price_rub, down_payment_rub,
     loan_amount_rub, term_years, rate_pct, monthly_payment_rub}
```

IMPORTANT lesson from our deposit bug: retail must forward rate_pct (the rate
CIB quoted and the customer saw) into the register call, so the registered
mortgage carries exactly the rate the customer was promised.

Update CONTRACT.md after.

---

### CIB

Add one endpoint:

```
POST /mortgage/decision
  body:    {customer_id, property_price_rub, down_payment_rub, term_years}
  returns: {approved, reason, loan_amount_rub, property_price_rub,
            down_payment_rub, term_years, rate_pct, monthly_payment_rub}
```

Logic:
1. loan_amount_rub = property_price_rub − down_payment_rub. Decline if ≤ 0.
2. Call backend GET /clients/{customer_id} for income, overdue, segment, risk.
3. Decline if has_overdue_history.
4. Decline if down payment < 15% of property price (minimum down payment).
5. Decline if loan_amount_rub > 8× annual income (affordability cap).
6. Set rate by segment (mortgages are cheaper than consumer loans because of
   collateral): mass/sme 14–17%; mass_affluent 12–15%; premium/private 9–13%
   (lower risk_score → lower rate within the band).
7. monthly_payment_rub via standard annuity formula over term_years×12 months,
   rounded to nearest 100 ₽.
8. Decline if monthly_payment_rub > 50% of monthly income.
9. Return approved decision with all fields.

Update CONTRACT.md after.

---

### backend

Add one endpoint:

```
POST /mortgages
  body:    {customer_id, property_price_rub, down_payment_rub,
            loan_amount_rub, term_years, rate_pct}
  returns: {mortgage_id, customer_id, property_price_rub, down_payment_rub,
            loan_amount_rub, term_years, rate_pct, monthly_payment_rub,
            status, created_at}
```

Logic:
1. Look up client — 404 if not found.
2. Generate mortgage_id (e.g. mort-{short uuid}).
3. Store the mortgage record (persist it so it survives a restart — see note).
4. Status = "active".
5. Compute monthly_payment_rub with the same annuity formula CIB uses
   (so the two always agree).
6. Return the mortgage summary.

NOTE on persistence: mortgages must survive a redeploy. Please store them the
same durable way we are fixing cards/loans/deposits — not only in memory.

Update CONTRACT.md after.

---

## Exact field names — use these consistently across all three blocks

| Field                 | Type  | Description                                   |
|-----------------------|-------|-----------------------------------------------|
| `customer_id`         | str   | Client ID                                     |
| `property_price_rub`  | int   | Price of the property                         |
| `down_payment_rub`    | int   | Amount the customer pays upfront              |
| `loan_amount_rub`     | int   | price − down payment (the borrowed amount)    |
| `term_years`          | int   | Mortgage term in years (10/15/20/25/30)       |
| `rate_pct`            | float | Annual interest rate, e.g. 12.5               |
| `monthly_payment_rub` | int   | Monthly annuity payment                       |
| `mortgage_id`         | str   | Unique mortgage identifier                    |

---

## Build order and instructions

**Step 1 — backend** builds POST /mortgages and updates CONTRACT.md.
Prompt: "Read tasks/mortgage_design.md and build the backend part."

**Step 2 — CIB** builds POST /mortgage/decision and updates CONTRACT.md.
Prompt: "Read tasks/mortgage_design.md and build the CIB part."

**Step 3 — retail (Nikita)** — tell me "they are done" and I will add the
Ипотека tab, the home-screen banner, and both proxy endpoints, and forward
rate_pct so the promised rate is the registered rate. No prompt needed.

All three can work in parallel; only the final end-to-end test needs all up.

---

## Definition of done

- Customer opens the "Ипотека" tab.
- Enters property price, down payment, term; clicks calculate.
- Sees the offer: loan amount, rate, monthly payment.
- Clicks confirm — the mortgage is registered and a mortgage id is shown.
- The rate registered equals the rate quoted (no repeat of the deposit bug).
