# Payroll — Corporate Salary Payout Feature

## What this is

A "Run Payroll" button on the corporate banking page (`GET /corporate`).
A company treasurer opens the page, loads their corporate account, and clicks
"Run Payroll". The bank automatically transfers this month's salary to every
employee who has an account at the bank. The feature is complete when all
three blocks have built and connected their parts.

---

## How the three blocks connect

```
retail  →  CIB:     POST /payroll/validate    (is the employer eligible to run payroll?)
retail  →  backend: POST /payroll/run         (execute the payout)
CIB     →  backend: GET  /clients/{id}        (fetch employer's balance and overdue status)
CIB     →  backend: GET  /corporate/{id}/employees  (sum up total salary)
```

Customer flow:
1. Treasurer opens `GET /corporate`, loads their corporate account.
2. Clicks "Run Payroll".
3. Retail calls CIB `POST /payroll/validate` — CIB checks that the employer
   has enough balance and no overdue history.
4. If approved, retail calls backend `POST /payroll/run`.
5. Backend debits the employer's account and credits each employee's account
   with their `income_rub` as salary.
6. Retail shows the summary: total paid, number of employees, new balance.

---

## Block responsibilities

### retail — Nikita Patrakhin

The corporate page (`retail/src/static/corporate.html`) already exists.
Add a "Run Payroll" button below the account balance box.

On click:
1. Call `POST /api/payroll/validate` (new proxy endpoint, see below) with
   `{employer_id: currentAccountId}`.
2. If `eligible: false` — show the reason, stop.
3. If `eligible: true` — show "Total payroll: X ₽ for N employees. Confirm?"
   with a Confirm button.
4. On confirm — call `POST /api/payroll/run` with `{employer_id: currentAccountId}`.
5. Show result: total paid, number of employees, new balance. Update the
   displayed balance on the page.

Add two new proxy endpoints to `retail/src/main.py`:

```
POST /api/payroll/validate
  → calls CIB POST /payroll/validate with {employer_id}
  ← {eligible: bool, reason: str, total_payroll_rub: int, employees_count: int}

POST /api/payroll/run
  → calls backend POST /payroll/run with {employer_id}
  ← {status, employer_id, employees_paid: int,
     total_paid_rub: int, new_employer_balance_rub: int,
     payments: [{employee_id, name, amount_rub}]}
```

Update CONTRACT.md after.

---

### CIB

Add one endpoint:

```
POST /payroll/validate
  body:    {employer_id: str}
  returns: {eligible: bool, reason: str,
            total_payroll_rub: int, employees_count: int}
```

Logic:
1. Call backend `GET /clients/{employer_id}` → get `balance_rub`,
   `has_overdue_history`.
2. Call backend `GET /corporate/{employer_id}/employees` → get employee list,
   sum their `income_rub` → `total_payroll_rub`, count → `employees_count`.
3. Return `eligible: false` if:
   - `has_overdue_history` is true, OR
   - `balance_rub` < `total_payroll_rub`.
4. Otherwise return `eligible: true`.

Update CONTRACT.md after.

---

### backend

**Endpoint 1 — get employees of a corporate client:**

```
GET /corporate/{client_id}/employees
  returns: {total: int, items: [{id, name, income_rub, balance_rub}]}
```

Return all clients where `employer_id == client_id`.
If `employer_id` field does not exist in `seed/clients.json`, add it to
at least 3 corporate clients, each with 3–5 employee entries pointing to
individual clients. The `employer_id` value must equal one of the existing
corporate client IDs in the seed.

**Endpoint 2 — execute payroll:**

```
POST /payroll/run
  body:    {employer_id: str}
  returns: {status: "ok", employer_id,
            employees_paid: int, total_paid_rub: int,
            new_employer_balance_rub: int,
            payments: [{employee_id, name, amount_rub}]}
```

Logic:
1. Load employer — return 404 if not found.
2. Load employees via same logic as GET /corporate/{id}/employees.
3. Return 400 if no employees found.
4. Compute total = sum of all `income_rub`. Return 400 if employer balance
   < total.
5. Deduct total from employer `balance_rub`. Add `income_rub` to each
   employee's `balance_rub`. Return summary.

Update CONTRACT.md after.

---

## Exact field names — use these consistently across all three blocks

| Field                     | Type   | Description                              |
|---------------------------|--------|------------------------------------------|
| `employer_id`             | string | ID of the corporate client running payroll |
| `employee_id`             | string | ID of an individual employee client      |
| `income_rub`              | int    | Monthly salary stored on the employee    |
| `total_payroll_rub`       | int    | Sum of all employee salaries             |
| `employees_count`         | int    | Number of employees in the payroll run   |
| `employees_paid`          | int    | Number of employees who received salary  |
| `new_employer_balance_rub`| int    | Employer's balance after the payout      |

---

## Build order

1. **backend first** — add `employer_id` to seed data, build both endpoints.
   Confirm in CONTRACT.md when done.
2. **CIB second** — build `/payroll/validate` once backend's
   `GET /corporate/{id}/employees` is in CONTRACT.md.
3. **retail last** — add the button and proxy endpoints once CIB's
   `/payroll/validate` is in CONTRACT.md.

## Definition of done

- Corporate client loads their account on `/corporate`.
- Clicks "Run Payroll" — sees validation result (total and headcount).
- Confirms — sees success with list of payments.
- Their balance on screen decreases by the total payroll amount.
- Each employee's bank balance increases by their salary.
