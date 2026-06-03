# Payroll — Corporate Salary Payout Feature

## What this is

A new product for corporate clients of the bank. A company treasurer opens the
corporate internet bank, sees a "Payroll" button, clicks it, and the bank
automatically transfers this month's salary to every employee who has an
account at the bank. The feature is done when all three blocks have built and
connected their parts.

---

## How the three blocks connect

```
retail  →  CIB:     POST /payroll/validate   (is this employer eligible?)
retail  →  backend: POST /payroll/run        (execute the payout)
CIB     →  backend: GET  /clients/{id}       (fetch employer's data)
```

The customer flow is:
1. A corporate client opens the corporate banking page in retail.
2. They click "Run Payroll".
3. Retail calls CIB to check eligibility (sufficient balance, no overdue history).
4. If CIB says yes, retail calls backend to execute the payroll.
5. Backend debits the employer's account and credits each employee.
6. Retail shows the summary: how many employees were paid and the total amount.

---

## Block responsibilities

### retail — owner: Nikita Patrakhin

Build a corporate internet bank page at `GET /corporate`.

The page must:
- Show a dropdown of corporate clients (call `GET /clients?segment=corporate`
  on backend — these are the employers).
- Show the selected employer's account balance.
- Show a "Run Payroll" button.
- On click: call `POST /api/payroll/validate` (your own proxy to CIB) with
  `{employer_id}`. If not eligible, show the reason and stop.
- If eligible: call `POST /api/payroll/run` (your own proxy to backend) with
  `{employer_id}`. Show the result: total paid out, number of employees,
  employer's new balance.

Add two proxy endpoints to main.py:

```
POST /api/payroll/validate
  → calls CIB POST /payroll/validate with {employer_id}
  ← returns {eligible: bool, reason: str, total_payroll_rub: int}

POST /api/payroll/run
  → calls backend POST /payroll/run with {employer_id}
  ← returns {status, employer_id, employees_paid: int,
             total_paid_rub: int, new_employer_balance_rub: int,
             payments: [{employee_id, name, amount_rub}]}
```

Add a link to the corporate page from the main bank home screen (index.html).
Update CONTRACT.md after.

---

### CIB — validate employer eligibility

Add one endpoint:

```
POST /payroll/validate
  body:    {employer_id: str}
  returns: {eligible: bool, reason: str, total_payroll_rub: int}
```

Logic:
1. Call `GET /clients/{employer_id}` on backend to get employer data.
2. Call `GET /corporate/{employer_id}/employees` on backend to get the
   employee list and their salary amounts.
3. Sum up `income_rub` for all employees → that is `total_payroll_rub`.
4. Return `eligible: false` if:
   - employer has `has_overdue_history: true`, or
   - employer's `balance_rub` < `total_payroll_rub` (insufficient funds).
5. Otherwise return `eligible: true`.

Update CONTRACT.md after.

---

### backend — store employee links and execute payroll

**New endpoint 1 — get employees of a corporate client:**

```
GET /corporate/{client_id}/employees
  returns: {total: int, items: [{id, name, income_rub, balance_rub}]}
```

Implementation: in the seed data, some clients have an `employer_id` field
that points to a corporate client's id. Return all clients where
`employer_id == client_id`. If no such field exists in seed, add it to
`seed/clients.json` for at least 3–5 employees per corporate client.

**New endpoint 2 — execute payroll:**

```
POST /payroll/run
  body:    {employer_id: str}
  returns: {status: "ok", employer_id, employees_paid: int,
            total_paid_rub: int, new_employer_balance_rub: int,
            payments: [{employee_id, name, amount_rub}]}
```

Logic:
1. Fetch employer from clients, check balance is sufficient.
2. Fetch employees via the same logic as GET /corporate/{id}/employees.
3. For each employee: add `income_rub` to their `balance_rub`.
4. Deduct total from employer's `balance_rub`.
5. Return summary.

Return HTTP 400 with a clear message if employer not found, has no
employees, or has insufficient funds.

Update CONTRACT.md after.

---

## Shared API contract (agree on this before building)

All field names everyone must use consistently:

| Field | Type | Description |
|---|---|---|
| `employer_id` | string | ID of the corporate client running payroll |
| `employee_id` | string | ID of an individual employee client |
| `income_rub` | int | Monthly salary of an employee |
| `total_payroll_rub` | int | Sum of all salaries to be paid out |
| `employees_paid` | int | Number of employees who received salary |
| `new_employer_balance_rub` | int | Employer's balance after payout |

---

## Definition of done

The feature is complete when a corporate client can:
1. Open the corporate banking page in the retail block.
2. Click "Run Payroll".
3. See the payout summary with total paid and number of employees.
4. Their account balance visibly decreases by the total payroll amount.
5. Each employee's balance visibly increases by their salary.

---

## How to coordinate

1. Backend owner: start by checking whether `employer_id` exists in
   `seed/clients.json`. If not, add it first, then build the two endpoints.
2. CIB owner: build `/payroll/validate` — you only need backend's existing
   `GET /clients/{id}` and the new `GET /corporate/{id}/employees`.
3. Retail owner: build the corporate page and proxy endpoints — wire them
   up once CIB and backend confirm their endpoints are live in CONTRACT.md.
4. Test the full flow together: run payroll, check balances changed.
