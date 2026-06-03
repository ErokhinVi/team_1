# Контракт блока cib

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, backend_url, products}`.

### GET /products
Каталог продуктов команды. Возвращает `{total, items: [продукты]}`. Каждый
продукт — объект как минимум с `{id, kind, name}`; депозитные/кредитные могут
иметь `rate_pct`.

### GET /
HTML с каталогом продуктов. Для человека, не для других блоков.

### POST /credit-decision
Credit card approval decision. Accepts JSON `{"customer_id": "<id>"}`.
Calls backend for customer data and returns:
`{"approved": bool, "credit_limit_rub": int, "reason": "..."}`.
Approved when income > 0; limit = 30% of annual income (monthly income × 12 × 0.30).
Returns 404 if customer not found.

## Кого я зову у соседей

- backend: `GET /clients/{client_id}` — to fetch customer income for the credit decision
- retail: я никого не зову у retail — это retail зовёт меня

## Где работает блок локально

`http://localhost:8002` (порт фиксируется docker-compose).
