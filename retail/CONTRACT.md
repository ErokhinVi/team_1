# Контракт блока retail

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, backend_url, cib_url}`.

### GET /
HTML мобильного банка. Для человека, не для других блоков.

### GET /clients
Список клиентов команды (прокси к backend). Параметры запроса передаются как есть.
Возвращает `{total, items: [клиенты]}`.

### GET /transactions/{client_id}
Транзакции клиента (прокси к backend). Возвращает `{total, items: [транзакции]}`.

### POST /api/transfer
Перевод средств между клиентами команды. Принимает JSON
`{from_client_id, to, amount_rub}`. Возвращает `{status, kind, amount_rub, to,
from_client_id, new_balance_rub, tx_id, ts}`.

### GET /corporate
HTML-страница корпоративного банкинга. Сотрудник компании вводит ID корпоративного счёта, видит баланс и реквизиты компании, заполняет форму платежа. Для человека, не для других блоков.

### POST /api/payroll/validate
Проверка возможности выплаты зарплаты (прокси к cib `POST /payroll/validate`).
Принимает `{employer_id}`. Возвращает `{eligible, reason, total_payroll_rub, employees_count}`.

### POST /api/payroll/run
Выплата зарплат сотрудникам (прокси к backend `POST /payroll/run`).
Принимает `{employer_id}`. Возвращает `{status, employees_paid, total_paid_rub, new_employer_balance_rub, payments}`.

### GET /api/corporate/account/{account_id}
Данные корпоративного счёта (прокси к backend `GET /corporate/accounts/{account_id}`).
Возвращает `{company_name, industry, balance_rub, account_id, ...}`.

### POST /api/corporate/payments
Корпоративный платёж с авторизацией. Принимает `{from_account_id, to_account_id, amount_rub, purpose}`.
Сначала вызывает cib `POST /corporate/payment-auth` для авторизации, затем backend `POST /corporate/payments` для исполнения.
Возвращает `{approved, reason?, payment_id?, new_balance_rub?, ...}`.

### GET /brokerage
HTML-страница брокериджа. Показывает список доступных акций, баланс брокерского счёта клиента, персональную рекомендацию по портфелю и форму для покупки/продажи. Для человека, не для других блоков.

### GET /api/brokerage/stocks
Список доступных акций (прокси к cib `GET /products/brokerage`).
Возвращает `{total, items: [{ticker, company, price_rub}]}`.

### GET /api/brokerage/account/{customer_id}
Брокерский счёт клиента (прокси к backend). Если счёта нет — создаёт автоматически.
Возвращает `{account_id, customer_id, balance_rub, status, created_at}`.

### GET /api/brokerage/recommendation/{customer_id}
Рекомендация по портфелю (прокси к cib `GET /brokerage/recommendation/{customer_id}`).
Возвращает `{customer_id, risk_score, portfolio: [{ticker, allocation_pct}], note}`.

### POST /api/brokerage/orders
Размещение заявки на покупку/продажу акций (прокси к backend).
Принимает `{customer_id, ticker, quantity, direction}`.
Возвращает `{order_id, status, ticker, direction, total_rub, new_account_balance_rub}`.

### POST /api/credit-apply
Подача заявки на кредитную карту. Принимает `{customer_id}`.
Обращается к cib `/credit-decision` за решением, затем к backend `/credit-cards` для создания карты.
Возвращает `{approved, reason, limit?, card?}`.

### GET /api/credit-cards?customer_id=...
Список кредитных карт клиента (прокси к backend `/credit-cards`).
Возвращает `{items: [{card_id, card_number, status, limit}]}`.

### POST /api/credit-cards/{card_id}/activate
Активация кредитной карты (прокси к backend). Возвращает обновлённый статус карты.

## Кого я зову у соседей

- backend: `GET /clients`, `GET /transactions/{id}`, `POST /api/transfer`, `POST /credit-cards`, `GET /credit-cards`, `POST /credit-cards/{id}/activate`, `GET /brokerage/accounts/{id}`, `POST /brokerage/accounts`, `POST /brokerage/orders`
- cib: `POST /credit-decision`; `GET /products/brokerage`; `GET /brokerage/recommendation/{id}`; `POST /corporate/payment-auth` — авторизация корпоративного платежа

## Где работает блок локально

`http://localhost:8001` (порт фиксируется docker-compose).
