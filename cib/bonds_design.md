# Bonds — Fixed-Income Investing for Retail Customers

## What this is

A new product for individual customers: bonds (fixed-income securities).
A customer opens the mobile bank, goes to a new "Облигации" (Bonds) screen,
sees a catalogue of available bonds (government and corporate), gets a
personalised recommendation based on their risk profile, and can buy or sell
bonds. Buying debits their bank account; selling credits it back. The feature
is complete when all three blocks have built and connected their parts.

This mirrors the existing brokerage feature on purpose: catalogue and advice
live in CIB, execution and holdings live in backend, and retail provides the
screen and the proxy endpoints.

---

## How the three blocks connect

```
retail  →  CIB:     GET  /products/bonds                  (catalogue of bonds)
retail  →  CIB:     GET  /bonds/recommendation/{id}        (risk-based suggestion)
retail  →  backend: GET  /bonds/holdings/{id}              (what the customer owns)
retail  →  backend: POST /bonds/orders                     (buy / sell)
CIB     →  backend: GET  /clients/{id}                     (risk_score, segment)
```

Customer flow:
1. Customer opens the "Облигации" screen in the mobile bank.
2. Retail shows the bond catalogue (from CIB) and the customer's current
   holdings (from backend).
3. Retail shows a personalised recommendation from CIB.
4. Customer picks a bond, a quantity, and clicks buy (or sell).
5. Retail calls backend to execute; money moves between the bank account and
   the bond holding.
6. Customer sees the updated holdings and balance.

---

## Exact field names — use these consistently across all three blocks

| Field              | Type   | Description                                       |
|--------------------|--------|---------------------------------------------------|
| `bond_id`          | string | Unique bond id, e.g. `OFZ-26240`                  |
| `issuer`           | string | Who issued it, e.g. `Минфин РФ`, `Сбербанк`       |
| `name`             | string | Human-readable bond name                          |
| `kind`             | string | `government` or `corporate`                       |
| `coupon_pct`       | float  | Annual coupon (interest) rate, e.g. 12.5          |
| `maturity_date`    | string | Redemption date, e.g. `2027-05-15`                |
| `face_value_rub`   | int    | Nominal value per bond, e.g. 1000                 |
| `price_rub`        | int    | Current market price per bond                     |
| `customer_id`      | string | Personal client id, e.g. `c-01394`                |
| `quantity`         | int    | Number of bonds (> 0)                             |
| `direction`        | string | `buy` or `sell`                                   |
| `total_rub`        | int    | quantity × price_rub                              |
| `new_balance_rub`  | int    | Customer's bank balance after the order           |
| `order_id`         | string | Unique bond order id                              |

Suggested catalogue (CIB owns these numbers — pick what you like):
- `OFZ-26240` — Минфин РФ — government — coupon 12.0% — price 980 — face 1000
- `OFZ-26244` — Минфин РФ — government — coupon 11.5% — price 995 — face 1000
- `SBER-001P` — Сбербанк — corporate — coupon 15.5% — price 1010 — face 1000
- `GAZP-002P` — Газпром — corporate — coupon 16.5% — price 1005 — face 1000
- `LKOH-001` — Лукойл — corporate — coupon 16.0% — price 1000 — face 1000

---

## Block responsibilities

### CIB

Add two endpoints:

```
GET /products/bonds
  returns: {total: int, items: [{bond_id, issuer, name, kind,
            coupon_pct, maturity_date, face_value_rub, price_rub}]}

GET /bonds/recommendation/{customer_id}
  → calls backend GET /clients/{customer_id} for risk_score and segment
  returns: {customer_id, risk_score,
            recommendation: [{bond_id, allocation_pct}], note}
  Logic: low risk_score → mostly government OFZ bonds (safe);
         high risk_score → more corporate bonds (higher coupon, more risk).
  Returns 404 if customer not found.
```

Update CONTRACT.md after.

### backend

Add bond holdings and order execution. Reuse the same account/balance the
customer already has (the same pattern as brokerage orders).

```
GET /bonds/holdings/{customer_id}
  returns: {customer_id, total: int,
            items: [{bond_id, quantity, avg_price_rub}]}

POST /bonds/orders
  body:    {customer_id, bond_id, quantity, direction}   (direction = buy|sell)
  Logic: buy → debit quantity × price_rub from the bank account, add to holding.
         sell → credit it back, reduce the holding (reject if not enough held).
         Reject buy if insufficient balance.
  returns: {order_id, status, bond_id, direction, quantity,
            total_rub, new_balance_rub}
  Returns 404 if customer not found, 400 on insufficient funds/holdings.
```

The bond prices used for execution should match CIB's catalogue numbers, so
copy the same `price_rub` values (or expose them from a shared place).
Update CONTRACT.md after.

### retail — Nikita Patrakhin

Add a "Облигации" (Bonds) screen, similar to the existing brokerage page.

The screen shows:
- The bond catalogue (from CIB).
- The customer's current bond holdings (from backend).
- A personalised recommendation (from CIB).
- A buy/sell form: pick a bond, enter quantity, choose buy or sell.

Add these proxy endpoints to `retail/src/main.py`:

```
GET  /api/bonds/catalogue            → CIB GET  /products/bonds
GET  /api/bonds/recommendation/{id}  → CIB GET  /bonds/recommendation/{id}
GET  /api/bonds/holdings/{id}        → backend GET /bonds/holdings/{id}
POST /api/bonds/orders               → backend POST /bonds/orders
                                       body {customer_id, bond_id, quantity, direction}
```

Update CONTRACT.md after.

---

## Build order

1. **CIB** builds `GET /products/bonds` and `GET /bonds/recommendation/{id}`,
   updates CONTRACT.md. (No dependency — can start immediately.)
2. **backend** builds `GET /bonds/holdings/{id}` and `POST /bonds/orders`,
   updates CONTRACT.md. (No dependency — can start immediately.)
3. **retail** builds the screen and the four proxy endpoints once CIB's
   catalogue and backend's order endpoint are in their CONTRACT.md files.

## Definition of done

- Customer opens the "Облигации" screen.
- Sees the catalogue, their holdings, and a recommendation.
- Buys a bond — money leaves their bank balance, the holding appears.
- Sells a bond — money returns to their balance, the holding shrinks.
- Balances stay consistent across the screen.

---

## Ready-to-paste prompts

### For CIB (Roland — that's me)
"Read cib/bonds_design.md and build the CIB part: add GET /products/bonds with
a catalogue of government and corporate bonds, and GET /bonds/recommendation/{customer_id}
that calls backend GET /clients/{id} and returns a risk-based mix (safe OFZ for
low risk_score, more corporate bonds for high risk_score). Use the exact field
names in the design file. Update CONTRACT.md and send it to the shared pile."

### For backend
"Read cib/bonds_design.md and build the backend part: add GET /bonds/holdings/{customer_id}
and POST /bonds/orders. Buying debits the customer's bank balance and adds to
their bond holding; selling credits it back and reduces the holding. Reject buys
with insufficient funds and sells of bonds not held. Use the same price_rub
values as CIB's catalogue and the exact field names in the design file. Return
404 for unknown customers, 400 for funds/holdings errors. Update CONTRACT.md."

### For retail (Nikita)
"Read cib/bonds_design.md and build the retail part: add a 'Облигации' screen
to the mobile bank (like the existing brokerage page) that shows the bond
catalogue from CIB, the customer's holdings from backend, a recommendation from
CIB, and a buy/sell form. Add four proxy endpoints — /api/bonds/catalogue,
/api/bonds/recommendation/{id}, /api/bonds/holdings/{id}, and POST /api/bonds/orders
— wiring to CIB and backend as described. Use the exact field names in the
design file. Update CONTRACT.md."
