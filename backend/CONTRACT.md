# Контракт блока backend

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, clients_loaded,
transactions_loaded}`.

### GET /clients
Список клиентов команды. Параметры запроса (все опциональные):
- `segment` — строка, сегмент клиента;
- `has_overdue` — bool, был ли просрочен платёж;
- `min_income` — int, минимальный доход в рублях;
- `limit` — int, ограничение по числу записей (по умолчанию 50, максимум 500).

Возвращает `{total, items: [клиенты]}`. Клиент — JSON с полями из seed:
`id, name, segment, balance_rub, income_rub, has_overdue_history` и другими.

### GET /clients/{client_id}
Полная карточка одного клиента. Возвращает объект клиента. `404`, если не найден.

### GET /transactions/{client_id}
Транзакции клиента, новые сверху. Параметры: `limit` (по умолчанию 20).
Возвращает `{total, items: [транзакции]}`. Транзакция —
`{id, client_id, type, amount_rub, ts, counterparty}`.

### POST /api/transfer
Перевод средств между клиентами команды. Принимает JSON
`{from_client_id, to, amount_rub}`. `to` — это либо id клиента, либо часть
имени получателя (поиск по подстроке). Возвращает `{status, kind
(internal|external), amount_rub, to, from_client_id, new_balance_rub, tx_id, ts}`.

### POST /credit-cards
Выпустить кредитную карту клиенту. Принимает JSON `{customer_id, credit_limit}`.
Создаёт карту со статусом `approved` и сгенерированным номером.
Возвращает `{card_id, card_number, status}`.

### GET /credit-cards?customer_id=
Список кредитных карт клиента. Параметр `customer_id` обязателен.
Возвращает `{total, items: [карты]}`. Карта — `{card_id, customer_id, card_number,
credit_limit_rub, status, created_at}`.

### POST /credit-cards/{card_id}/activate
Активировать карту (перевести статус из `approved` в `active`).
Возвращает `{card_id, status}`. Ошибка `400`, если карта уже не в статусе `approved`.

### POST /brokerage/accounts
Открыть брокерский счёт клиенту. Принимает JSON `{customer_id}`.
Возвращает `{account_id, status}`. Ошибка `400`, если счёт уже существует.

### GET /brokerage/accounts/{customer_id}
Получить брокерский счёт клиента. Возвращает `{account_id, customer_id,
balance_rub, status, created_at}`. Ошибка `404`, если счёта нет.

### POST /brokerage/orders
Разместить биржевую заявку. Принимает JSON `{customer_id, ticker, quantity, direction}`.
`ticker` — один из: `SBER`, `GAZP`, `LKOH`, `YNDX`, `MGNT`.
`direction` — `buy` или `sell`.
При покупке деньги списываются с банковского счёта клиента, зачисляются на брокерский.
При продаже — обратно. Возвращает `{order_id, status, ticker, direction, total_rub, new_account_balance_rub}`.

### GET /corporate/accounts
Список корпоративных счетов. Параметры (опциональные): `industry` — фильтр по отрасли, `limit` (по умолчанию 50).
Возвращает `{total, items: [счета]}`. Счёт — `{id, name, industry, balance_rub, monthly_turnover_rub, opened_at}`.

### GET /corporate/accounts/{account_id}
Баланс и карточка одного корпоративного счёта. Возвращает объект счёта. `404`, если не найден.

### POST /corporate/payment-auth
Авторизация платежа без списания средств. Принимает JSON `{from_account_id, to_account_id, amount_rub}`.
Проверяет баланс отправителя и возвращает `{authorized: true/false, from_account_id, from_name, amount_rub, available_balance_rub, reason}`.
Используй перед `POST /corporate/payments`, чтобы убедиться что платёж пройдёт.

### GET /corporate/{client_id}/employees
Список сотрудников корпоративного клиента, у которых есть счёт в банке.
Возвращает `{total, items: [{id, name, income_rub, balance_rub}]}`.
`income_rub` — месячная зарплата сотрудника.

### POST /payroll/run
Выплата зарплаты всем сотрудникам компании. Принимает JSON `{employer_id}`.
Списывает сумму всех зарплат со счёта компании и зачисляет каждому сотруднику его `income_rub`.
Возвращает `{status, employer_id, employees_paid, total_paid_rub, new_employer_balance_rub, payments: [{employee_id, name, amount_rub}]}`.
Ошибка `400` если компания не найдена, нет сотрудников, или недостаточно средств.

### POST /corporate/payments
Платёж между двумя компаниями. Принимает JSON `{from_account_id, to_account_id, amount_rub, purpose}`.
`purpose` — назначение платежа (строка, опционально). Возвращает `{payment_id, status, from_name, to_name, amount_rub, new_balance_rub, ts}`.

## Рекомендуемый порядок вызовов для брокериджа

Для коллеги на **cib** — каталог акций и рекомендации:
1. Вызови `GET /clients/{customer_id}` — получи `risk_score` и `income_rub`.
2. На основе `risk_score` сформируй рекомендованный портфель и верни retail.
3. Доступные тикеры: `SBER`, `GAZP`, `LKOH`, `YNDX`, `MGNT`.

Для коллеги на **retail** — полный флоу:
1. Покажи каталог акций из cib (`GET /products/brokerage`).
2. Вызови `GET /brokerage/accounts/{customer_id}` — если `404`, сначала создай счёт через `POST /brokerage/accounts`.
3. Покажи баланс брокерского счёта и рекомендацию из cib.
4. При покупке/продаже вызови `POST /brokerage/orders` с `{customer_id, ticker, quantity, direction}`.

## Рекомендуемый порядок вызовов для кредитной карты

Для коллеги на **cib** — когда клиент подаёт заявку на карту:
1. Вызови `GET /clients/{customer_id}` — получи данные клиента, в том числе `risk_score` (0–1, чем меньше, тем надёжнее) и `income_rub`.
2. На основе этих данных прими решение: одобрить или отказать, и какой лимит предложить.
3. Верни retail своё решение: `{approved: true/false, credit_limit_rub, reason}`.

Для коллеги на **retail** — когда cib одобрил карту:
1. Вызови `POST /credit-cards` с `{customer_id, credit_limit}` — backend выпустит карту со статусом `approved` и вернёт `card_id` и `card_number`.
2. Покажи клиенту номер карты и кнопку "Активировать".
3. Когда клиент нажимает "Активировать" — вызови `POST /credit-cards/{card_id}/activate`.
4. Покажи клиенту, что карта активна.

## Кого я зову у соседей

Никого. backend — это ядро данных, оно ничего не зовёт у retail и cib.

## Где работает блок локально

`http://localhost:8003` (порт фиксируется docker-compose).
