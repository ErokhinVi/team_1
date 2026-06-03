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

### POST /api/deposit/terms
Условия вклада (прокси к cib `POST /deposit/terms`).
Принимает `{customer_id, amount_rub, term_months}`.
Возвращает `{approved, reason, rate_pct, term_months, amount_rub}`.

### POST /api/deposit/open
Открытие вклада (прокси к backend `POST /deposits`).
Принимает `{customer_id, amount_rub, term_months}`. Ставку, ранее полученную от cib
через `/api/deposit/terms`, retail передаёт в backend как `rate_pct`, чтобы итоговая
ставка совпадала с показанной клиенту.
Возвращает `{deposit_id, customer_id, amount_rub, term_months, rate_pct, maturity_date, new_balance_rub}`.

### POST /api/loan/decision
Решение по потребительскому кредиту (прокси к cib `POST /loan/decision`).
Принимает `{customer_id, amount_rub, term_months}`.
Возвращает `{approved, reason, amount_rub, term_months, rate_pct, monthly_payment_rub}`.

### POST /api/loan/disburse
Выдача кредита (прокси к backend `POST /loans`).
Принимает `{customer_id, amount_rub, term_months, rate_pct}`.
Возвращает `{loan_id, customer_id, amount_rub, term_months, rate_pct, monthly_payment_rub, new_balance_rub}`.

### GET /api/deposit-product
Данные о вкладе (прокси к cib `GET /products`, фильтр по id `deposit-base`).
Возвращает `{id, name, rate_pct, ...}`. Используется для отображения баннера на главной.

### POST /api/payroll/validate
Проверка возможности выплаты зарплаты (прокси к cib `POST /payroll/validate`).
Принимает `{employer_id}`. Возвращает `{eligible, reason, total_payroll_rub, employees_count}`.
Валидный пример для seeded corporate employer: `{"employer_id": "corp-001"}`.
Используй именно `corp-*` ids; персональные `c-*` ids для payroll не подходят.

### POST /api/payroll/run
Выплата зарплат сотрудникам (прокси к backend `POST /payroll/run`).
Принимает `{employer_id}`. Возвращает `{status, employees_paid, total_paid_rub, new_employer_balance_rub, payments}`.
Валидный пример: `{"employer_id": "corp-001"}`.

### GET /api/corporate/account/{account_id}
Данные корпоративного счёта (прокси к backend `GET /corporate/accounts/{account_id}`).
Возвращает `{company_name, industry, balance_rub, account_id, ...}`.
Реальные seeded account ids: `corp-001`, `corp-002`, `corp-003`.

### POST /api/corporate/payments
Корпоративный платёж с авторизацией. Принимает `{from_account_id, to_account_id, amount_rub, purpose}`, где `from_account_id`/`to_account_id` — корпоративные счета (например `corp-001`, `corp-002`). Пример: `{"from_account_id": "corp-001", "to_account_id": "corp-002", "amount_rub": 1000, "purpose": "оплата услуг"}`.
Сначала вызывает cib `POST /corporate/payment-auth` для авторизации, затем backend `POST /corporate/payments` для исполнения.
Возвращает `{approved, reason?, payment_id?, new_balance_rub?, ...}`.
Валидный пример для проверки:
`{"from_account_id": "corp-001", "to_account_id": "corp-002", "amount_rub": 1000, "purpose": "Supplier payment"}`.
Это корпоративная ручка: personal ids вида `c-01394` не являются счетами компаний
и вернут ошибку.

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
Принимает `{customer_id, ticker, quantity, direction}`, где `ticker` — один из доступных: `SBER`, `GAZP`, `LKOH`, `YNDX`, `MGNT`; `direction` — `buy` или `sell`; `quantity` — целое > 0. Брокерский счёт создаётся автоматически при первой заявке.
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

- backend: `GET /clients`, `GET /transactions/{id}`, `POST /api/transfer`, `POST /credit-cards`, `GET /credit-cards`, `POST /credit-cards/{id}/activate`, `GET /brokerage/accounts/{id}`, `POST /brokerage/accounts`, `POST /brokerage/orders`, `GET /corporate/accounts/{id}`, `POST /corporate/payments`, `POST /payroll/run`, `POST /loans`
- cib: `POST /credit-decision`; `GET /products/brokerage`; `GET /brokerage/recommendation/{id}`; `POST /corporate/payment-auth`; `POST /payroll/validate`; `POST /loan/decision`

## Где работает блок локально

`http://localhost:8001` (порт фиксируется docker-compose).
