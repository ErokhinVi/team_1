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
