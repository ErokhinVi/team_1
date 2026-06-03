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
- cib: `POST /credit-decision` — решение по кредитной заявке; `GET /products/brokerage` — список акций; `GET /brokerage/recommendation/{id}` — рекомендация по портфелю

## Где работает блок локально

`http://localhost:8001` (порт фиксируется docker-compose).
