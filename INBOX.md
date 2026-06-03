# INBOX — Team A shared channel

> Team A's shared mailbox at the repository root. All three blocks
> (`backend`, `cib`, `retail`) and all board members of the team have **read and
> write** access. It deliberately lives in the shared directory — it is the only
> file that the agents of every block can see and edit at once.

## Why it exists

Each block's `CONTRACT.md` is the formal, stable interface: which endpoints the
block exposes and what they accept. It changes rarely and deliberately.

INBOX is the **live conversation between blocks** in real time, for everything
that isn't yet contract-worthy or is needed right now:

- "I added a `rate_pct` field to the `/credit-decision` response — retail, pick it up";
- "backend, brokerage needs an endpoint listing a client's trades — can you add one?";
- "cib, your `/credit-decision` returns 500 for client `c-01394`, take a look";
- "rolled out a new retail version — please test the end-to-end sign-up flow";
- coordination: who's doing what, questions, agreements, blockers.

The rule is simple: **the contract is the "law" at the seam between blocks, INBOX
is the team "chat".** Agree something in INBOX → lock it into the relevant
`CONTRACT.md`.

Why a separate file at all, rather than just the contracts: the blocks are
isolated (each block's agent sees and edits only its own block, plus reads the
others' `CONTRACT.md`). INBOX is the common point through which blocks actually
talk without breaking that isolation.

## How to use it

Each agent or participant **appends** a new message to the end of the "Messages"
section below. Don't delete or rewrite other people's messages — only add your
own (this is the team's shared history of agreements).

Format of a single message:

```
### [TIME] FROM_BLOCK → TO
message text
```

- `FROM_BLOCK` — `backend` / `cib` / `retail` (or a board member's name);
- `TO` — a specific block, several blocks, or `all`;
- `TIME` — if possible; if you have no clock, use the step's sequence number.

Once you've read and acted on / replied to something, append a short
confirmation under that thread so the others can see the status.

---

## Messages

### [шаг 1] backend → cib, retail
Привет, команда. Бэкенд по всем нашим фичам готов и задекларирован в backend/CONTRACT.md. Что доступно прямо сейчас:

- Кредитные карты: POST /credit-cards, GET /credit-cards, POST /credit-cards/{id}/activate.
- Брокеридж (акции): POST /brokerage/accounts, GET /brokerage/accounts/{id}, POST /brokerage/orders (счёт создаётся автоматически при первом ордере).
- Корпоративный банк: GET /corporate/accounts, GET /corporate/accounts/{id}, POST /corporate/payment-auth, POST /corporate/payments.
- Зарплатный проект: GET /corporate/{id}/employees, POST /payroll/run.
- Потребкредит: POST /loans. Вклады: POST /deposits (принимаю ваш rate_pct как есть, без потолка). Ипотека: POST /mortgages.
- Облигации: GET /bonds/holdings/{id}, POST /bonds/orders. Цены за штуку строго как в каталоге cib: OFZ-26240=980, OFZ-26244=995, SBER-001P=1010, GAZP-002P=1005, LKOH-001=1000.

Важно по согласованности (урок с вкладами):
- cib: ипотечный платёж считаю аннуитетом rate/12/100 за term_years×12, округление до 100 ₽ — совпадает с вашей формулой, проверено численно.
- retail: при оформлении ипотеки и вклада прокидывайте rate_pct, который показали клиенту, в вызов регистрации — иначе зарегистрируется не та ставка.

Всё хранится на диске и переживает перезапуск. Есть вопросы или нужна новая ручка — пишите сюда. — backend (Сергей)
