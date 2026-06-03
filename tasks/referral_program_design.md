# Referral Program — "Bring a Friend, Both Get 20 000 ₽"

## What this is

An existing customer invites a friend. When the friend joins, the bank pays
**20 000 ₽ to both** — the referrer and the new customer. Advertised on the
mobile-bank front page to drive acquisition.

## How the three blocks connect

```
retail → CIB:     POST /referral/validate   (is this referral allowed?)
retail → backend: POST /referrals           (open friend's account, pay both bonuses)
```

## Exact field names

| Field | Type | Description |
|---|---|---|
| `referrer_id` | str | Existing customer who invites |
| `new_customer_name` | str | Name of the invited friend |
| `new_customer_id` | str | Account id created for the friend |
| `bonus_rub` | int | Bonus per person — fixed 20000 |
| `referral_id` | str | Unique referral id |

## Block responsibilities

### backend (Sergey)
- `POST /referrals {referrer_id, new_customer_name}`:
  1. 404 if referrer not found.
  2. Open a new client (segment `mass`, `acquired_via: "referral"`).
  3. Credit `bonus_rub` (20000) to BOTH the referrer and the new customer.
  4. Store the referral record; persist new client + balances (survive restart).
  5. Return `{referral_id, referrer_id, new_customer_id, new_customer_name, bonus_rub, referrer_new_balance_rub, new_customer_balance_rub}`.
- `GET /referrals/{referrer_id}` → `{total, items:[...]}` (how many they've referred).
- Update CONTRACT.md.

### CIB — eligibility / anti-abuse
`POST /referral/validate {referrer_id}` → `{eligible, reason}`.
Decline if referrer not a customer or has too many referrals (cap, e.g. 10).
Update CONTRACT.md.

### retail (Nikita) — front-page advertising
- Front-page banner: "Приведи друга — оба получите 20 000 ₽".
- A form: referrer (current client) + friend's name → call `/api/referral/validate`,
  then `/api/referrals`. Show "friend joined, you both got 20 000 ₽".
- Proxies: `POST /api/referral/validate` → CIB, `POST /api/referrals` → backend.
- Update CONTRACT.md.

## Build order
1. backend: POST /referrals + GET /referrals/{id} (start now).
2. CIB: /referral/validate (after backend in CONTRACT.md).
3. retail: banner + form + proxies (after both in CONTRACT.md).

## Definition of done
Customer refers a friend → friend gets an account → both balances rise by
20 000 ₽ → banner visible on front page → customer base grows on leaderboard.
