# Payroll as an Acquisition Channel

## What this is

Turn payroll from a payout tool into a customer-acquisition engine. A company
has a full staff roster — some are our customers, most are not. When the company
runs payroll, we automatically open an account for every employee who doesn't yet
bank with us and pay their salary into it. They arrive as active customers. Win
the employer once → acquire its staff every payday.

## How the three blocks connect

```
retail → CIB:     POST /payroll/validate     (is this employer eligible to run payroll?)
retail → backend: POST /payroll/run          (execute: pay existing + acquire new)
CIB    → backend: GET  /corporate/{id}/roster (full staff list incl. non-customers)
```

## Exact field names

| Field | Type | Description |
|---|---|---|
| `employer_id` | str | Corporate client id |
| `roster` | list | All staff: `[{name, income_rub, client_id?}]` (no client_id = not yet a customer) |
| `employees_paid` | int | Total people paid this run |
| `new_customers_acquired` | int | How many had an account opened for them this run |
| `total_paid_rub` | int | Sum of all salaries paid |
| `new_employer_balance_rub` | int | Employer balance after payout |

## Block responsibilities

### backend (Sergey) — owns acquisition
1. Add a staff roster per company: `seed/company_roster.jsonl` —
   `{employer_id, name, income_rub, client_id (optional)}`. Some rostered staff
   are existing clients (have client_id), most are prospects (no client_id).
2. `GET /corporate/{employer_id}/roster` → `{total, items:[{name, income_rub, client_id}]}`.
3. Upgrade `POST /payroll/run`: for each rostered employee —
   - if they already have an account → pay salary into it (as today);
   - if not → create a new client (segment `mass`, balance 0, employer linked),
     then pay salary in. Count them as acquired.
4. Return `{status, employer_id, employees_paid, new_customers_acquired,
   total_paid_rub, new_employer_balance_rub, payments:[...]}`.
5. Persist new clients to disk (survive restart). Update CONTRACT.md.

### CIB — eligibility
`POST /payroll/validate {employer_id}` → `{eligible, reason, total_payroll_rub}`.
Call backend `GET /corporate/{id}/roster`, sum `income_rub`, decline if employer
has overdue history or balance < total payroll. Update CONTRACT.md.

### retail (Nikita) — the growth screen
On the corporate page add "Run Payroll". Call `/api/payroll/validate`; if eligible,
call `/api/payroll/run`. Show the result emphasising acquisition:
"Payroll complete — 23 paid, 9 became new customers." Update CONTRACT.md.

## Build order
1. backend: roster + upgraded payroll (no dependency — start now).
2. CIB: validate (needs backend roster endpoint in CONTRACT.md).
3. retail: screen + proxies (needs both in CONTRACT.md).

## Definition of done
Company runs payroll → existing staff paid, new staff get accounts opened and
funded → result screen shows new_customers_acquired → bank customer base grows
on the leaderboard.
