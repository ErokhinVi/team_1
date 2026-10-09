# Контракт блока backend

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Для cib — коротко (обновлено 9 октября, 12:35)

Чтобы принять решение по кредиту, cib нужен **один вызов** к backend:

`GET {BACKEND_URL}/credit-history/{client_id}` — таймаут 2 с.

Из ответа брать **поля в корне** (не из `summary`, не из `items`):

| Поле | Что значит | Как использовать в политике (ТЗ retail v2) |
|---|---|---|
| `active_monthly_payment_rub` | Сколько клиент уже платит в месяц по кредитам, срок которых ещё идёт | `debt` в шаге 6 (PTI) |
| `has_active_overdue` | Есть текущая просрочка по идущему кредиту | стоп-фактор → `declined` |
| `is_salary_client` | Получает зарплату в нашем банке | −1.0 п.п. к ставке |
| `avg_salary_rub` | Средняя зарплата (0, если не зарплатный) | для справки/объяснения |
| `active_count` | Число идущих кредитов | для объяснения клиенту |
| `max_overdue_days` | Худшая просрочка за всю историю | только для объяснения; прошлая просрочка сама по себе — не отказ |

Пример (c-01001, доход 73 118 ₽, risk 0.344):
```
{"client_id": "c-01001", "total": 3, "active_count": 1,
 "active_monthly_payment_rub": 10269, "has_active_overdue": false,
 "is_salary_client": false, "avg_salary_rub": 0, "max_overdue_days": 0, ...}
```
→ по политике: группа B, 20.0%, 150 000 ₽ на 24 мес → `approved`, 7 634 ₽/мес.

Важно:
- Уже закончившиеся по сроку «active» кредиты из seed backend в нагрузку
  **не считает** (374 из 629). Пересчитывать по `items` не нужно.
- Нет истории (`total: 0`) → все поля нулевые/false. Это **не отказ**.
- `404` — клиента нет; ошибка или таймаут → деградация из ТЗ:
  `debt = 0`, `has_active_overdue = false`, `is_salary_client = false`.
- cib **ничего не пишет в backend**: заявку и выдачу денег делает retail
  после согласия клиента (`POST /credit-applications` с `idempotency_key`).
- Retail зовёт `POST /api/decision` (запасной вариант `/credit/decide`) —
  лучше сделать `/api/decision`.
- Где посмотреть живьём: `https://team1-backend.erokhinva.workers.dev/docs`
  → `GET /credit-history/{client_id}` → Try it out.
- Статус: `/credit-history` со всеми полями выше — в `dev`; в живом банке
  (main) поля `has_active_overdue`, `is_salary_client`, `avg_salary_rub` в
  корне и фильтр по сроку появятся после следующего выпуска dev → main.
  До этого они есть в `summary` (без фильтра по сроку).

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, clients_loaded,
transactions_loaded, credit_history_loaded, credit_applications}`
(`credit_applications` — заявки обоих вариантов).

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

## Релиз 1 — кредит наличными (по ТЗ retail, `retail/CONTRACT.md`)

Это основные кредитные ручки для retail и cib. Ошибки: неизвестный клиент или
заявка → `404`; неверный ввод → `422` с `detail` по-русски. Деньги — целые рубли.
Данные в памяти: после перезапуска backend заявки и выданные кредиты
обнуляются (seed на месте).

### R1-B1. GET /credit-history/{client_id}
`{client_id, total, items: [{id, product, principal_rub, term_months, rate_pct,
opened_at, status, overdue_days_max}], summary: {active_count, max_overdue_days,
has_active_overdue, monthly_debt_payment_rub, is_salary_client, avg_salary_rub}}`.
`max_overdue_days` — по всем записям; `has_active_overdue` — есть `active` с
просрочкой; `monthly_debt_payment_rub` — сумма аннуитетов по `active`
(`P = S*m/(1-(1+m)^-n)`, `m = rate_pct/1200`), округлена; `is_salary_client` —
есть транзакции `salary`; `avg_salary_rub` — средняя зарплата или 0.
Кредиты, выданные через R1-B2, попадают сюда как `active`.
Проверка: c-01000 → `2, 23160, false`; c-01002 → `0, 0, true, 40425`.

### R1-B2. POST /api/credit-disburse
Вход `{client_id, amount_rub, rate_pct, term_months, application_id?}`.
Зачисляет сумму на счёт, добавляет транзакцию `credit_disbursement` и запись
`consumer_credit / active` в кредитную историю. Ответ
`{status: "ok", client_id, credit_id, tx_id, amount_rub, new_balance_rub}`.
Повтор с тем же `application_id` деньги второй раз не зачисляет и возвращает
тот же ответ.

### R1-B3. Заявки
`POST /api/credit-applications` — вход `{client_id, amount_rub, term_months,
decision (approved|counter|declined|pending), rate_pct?, approved_amount_rub?,
monthly_payment_rub?, reason?}` (лишние поля сохраняются как есть). Ответ
`{application_id ("app-000001"), created_at, ...вход, status: null}`.

`GET /api/credit-applications/{client_id}` — заявки клиента, новые сверху:
`{total, items}`. После выдачи у заявки появляется `credit_id`.

`PATCH /api/credit-applications/{application_id}` — вход
`{status: "accepted"|"rejected_by_client"}`, ответ — обновлённая заявка
(+`updated_at`).

## Кредиты — основная схема (ТЗ retail v2)

По ТЗ retail v2 именно эти ручки — основные: retail записывает заявку в
`POST /credit-applications` после согласия клиента, cib читает
`GET /credit-history/{id}`. Ручки `/api/...` из раздела «Релиз 1» выше тоже
работают, но в v2 не используются.

Изменения v2:
- R1-B4: `active_count`, `active_principal_rub`, `active_monthly_payment_rub`
  считаются только по `status == "active"`, у которых `opened_at + term_months`
  ≥ сегодня (кредиты, выданные через заявки, — всегда). Добавлено
  `has_active_overdue` — есть ли среди них `overdue_days_max > 0`. Тот же
  фильтр — в `summary`.
- R1-B5: в корне ответа `/credit-history` есть `is_salary_client` и
  `avg_salary_rub`.
- R1-B6: `POST /credit-applications` принимает необязательный
  `idempotency_key`; повтор с тем же ключом возвращает ту же заявку, деньги
  второй раз не зачисляются.

Проверка: c-01000 → `2, 23160, false`; c-01001 → `1, 10269, false`;
c-01002 → `0, 0, true, avg_salary_rub 40425`; c-01016 → нагрузка 101 076 ₽/мес.

Как задумано: retail принимает заявку от клиента → cib решает (одобрить или
отказать, под какую ставку), беря данные клиента и кредитную историю у backend
→ решение записывается в backend. При одобрении backend сам зачисляет сумму
кредита на счёт клиента, добавляет операцию `loan_disbursement` и вносит новый
кредит в кредитную историю.

Записать решение можно двумя способами — выбирайте, кому удобнее:
- одним вызовом: `POST /credit-applications` сразу со `status` и `rate_pct`;
- в два шага: `POST /credit-applications` (заявка `pending`), потом
  `PATCH /credit-applications/{id}` с решением.

Продукты (`product`): `consumer_credit` (по умолчанию), `auto_credit`,
`mortgage`, `credit_card`. Статусы заявки: `pending`, `approved`, `rejected`.
Данные хранятся в памяти: после перезапуска backend заявки обнуляются,
кредитная история из seed — на месте.

### GET /credit-history/{client_id}
Кредитная история клиента + сводка для скоринга. Возвращает
`{client_id, total, active_count, active_principal_rub,
active_monthly_payment_rub, closed_clean_count, closed_with_overdue_count,
max_overdue_days, has_overdue, items: [кредиты]}`. Кредит —
`{id, client_id, product, principal_rub, term_months, rate_pct, opened_at,
status (active|closed_clean|closed_with_overdue), overdue_days_max}`; у
кредитов, выданных здесь, ещё `application_id`. Новые сверху. `404`, если
клиента нет.

### POST /credit-applications
Подать заявку. Принимает JSON:
`{client_id, amount_rub, term_months (1–360), product?, purpose?}` — заявка
создаётся в статусе `pending`. Если решение уже принято, можно сразу передать
`status: "approved"` + `rate_pct` (годовых, %) или `status: "rejected"`, а
также `reason?`, `decided_by?`, `idempotency_key?` (защита от повтора).

Ответ `201` — заявка:
`{id ("ca-000001"), client_id, client_name, product, amount_rub, term_months,
purpose, status, created_at, rate_pct, monthly_payment_rub, reason,
decided_by, decided_at}`; у одобренной ещё `credit_id, disbursement_tx_id,
new_balance_rub`. `monthly_payment_rub` — аннуитетный платёж, считает backend.
Ошибки: `404` — нет клиента; `400` — неверная сумма/срок/продукт/ставка.

### PATCH /credit-applications/{id}
Записать решение по заявке в статусе `pending`. Принимает
`{status: "approved"|"rejected", rate_pct (обязательна для approved),
reason?, decided_by?}`. Возвращает обновлённую заявку. `409`, если решение
уже было; `404`, если заявки нет.

### GET /credit-applications
Список заявок, новые сверху. Фильтры: `client_id`, `status`, `limit`
(по умолчанию 50). Возвращает `{total, items: [заявки]}`.

### GET /credit-applications/{id}
Одна заявка. `404`, если не найдена.

## Кого я зову у соседей

Никого. backend — это ядро данных, оно ничего не зовёт у retail и cib.

## Где работает блок локально

`http://localhost:8003` (порт фиксируется docker-compose).
