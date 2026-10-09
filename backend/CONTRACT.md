# Контракт блока backend

Сюда вписывай ручки, которые твой блок отдаёт наружу. Соседи по команде
видят только этот файл — не код. Если ручка изменилась или появилась новая —
обнови этот файл, иначе сосед о ней не узнает.

## Для cib (Алексей) — данные для матрицы CRO (R1-C3), обновлено 9 октября, 12:58

Всё, что нужно матрице, отдаёт **один запрос**:

`GET {BACKEND_URL}/clients/{client_id}/profile` — таймаут 2 с.

(Запасной путь — два запроса: `GET /clients/{id}` + `GET /credit-history/{id}`;
блок `summary` в них тот же.)

### Какое поле — к какому шагу матрицы

| Шаг R1-C3 | Поле в ответе `/profile` |
|---|---|
| 1. Сегмент не из матрицы (`sme`) → `product_scope` | `segment` |
| 1. Доход 0 → `income` | `income_rub` |
| 1. Текущая просрочка → `current_overdue` | `summary.has_active_overdue` |
| 1. Риск ≥ 0.65 → `risk`; 2. риск-группа | `risk_score` |
| 1–2. Прошлая просрочка ≥ 60 дней | `summary.max_overdue_days` (худшая за всю историю) |
| 3. −0.5 / −1.0 / −1.5 по сегменту | `segment` |
| 3. −1.0 зарплатному | `summary.is_salary_client` |
| 5. Текущие платежи для PTI | `summary.monthly_debt_payment_rub` |
| 5. Порог PTI по доходу | `income_rub` |

`summary.monthly_debt_payment_rub` уже **без** кредитов с истёкшим сроком
(374 из 629 «active» в исходных данных) и **с** кредитами, выданными через
наш банк. Пересчитывать по `items` не нужно.

Признак `has_overdue_history` в карточке и `summary.max_overdue_days` —
разные источники и иногда не совпадают (например, c-01007: флаг есть,
а в кредитной истории просрочек нет). Для матрицы CRO нужен
`max_overdue_days`.

### Входные данные клиентов из приёмки R1-C3 (данные backend на 9 октября, до новых выдач)

| Клиент | segment | income_rub | risk_score | debt (`summary.monthly_debt_payment_rub`) | has_active_overdue | max_overdue_days | is_salary_client |
|---|---|---|---|---|---|---|---|
| c-01003 | mass | 63 526 | 0.315 | 0 | false | 0 | false |
| c-01002 | mass | 40 425 | 0.286 | 0 | false | 0 | true |
| c-01001 | mass | 73 118 | 0.344 | 10 269 | false | 0 | false |
| c-01000 | mass | 49 144 | 0.270 | 23 160 | false | 0 | false |
| c-01007 | mass | 42 103 | 0.573 | 0 | false | 0 | true |
| c-01017 | mass_affluent | 150 323 | 0.187 | 0 | false | 0 | true |
| c-01011 | mass_affluent | 179 174 | 0.265 | 0 | false | 0 | true |

**Проверено backend:** если применить матрицу R1-C3 к этим данным, получается
ровно таблица приёмки из `retail/CONTRACT.md` (все 7 строк: c-01003 approved
B 19.9% 7 627 ₽; c-01002 18.9% 7 554 ₽; c-01001 19.9% 7 627 ₽; c-01000
rejected debt_burden; c-01007 counteroffer D 25.9% 80 000 ₽ 4 306 ₽;
c-01017 A 16.4% 34 408 ₽; c-01011 B 18.4% 35 082 ₽). Если у cib не сходится —
дело в расчёте, не в данных. Аннуитет: `S*m/(1-(1+m)^-n)`, `m = ставка/1200`.

### Что уже решено (не нужно согласовывать)

- Формат `/credit/decide` (`approved / counteroffer / rejected`) retail принял
  как есть, `/api/decision` не нужен (см. `retail/CONTRACT.md`, 12:55).
- Согласие клиента и защита от повторной выдачи — на retail + backend:
  retail зовёт `POST /api/credit-disburse` с `application_id`, повтор деньги
  второй раз не зачисляет. cib в backend ничего не пишет.
- Нет истории (`total: 0`) → нули и `false`, это не отказ.
- Ошибка/таймаут backend — решение по ТЗ (у cib сейчас `503`, retail
  понимает его как техническую паузу).

### Для R2-C1 (`GET /api/offers/{client_id}`, баннер «Вам одобрено до N ₽»)
Тот же `/profile` — один запрос на клиента, данные те же.

Посмотреть руками: `https://team1-backend.erokhinva.workers.dev/docs` →
`GET /clients/{client_id}/profile` → Try it out (после выпуска dev → main).

## Что я отдаю наружу

### GET /health
Проверка живости. Возвращает `{status, team, block, commit, clients_loaded,
transactions_loaded, credit_history_loaded, credit_applications}`
(`credit_applications` — заявки обоих вариантов), `deposits`, `credit_payments`.

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

## Релиз 2 — вклады (R2-B2, по ТЗ retail)

### POST /api/deposits
Открыть вклад. Вход `{client_id, product_id, amount_rub, term_months?,
rate_pct?, idempotency_key?}` (`term_months` по умолчанию 12, 1–120;
`rate_pct` — ставка из каталога cib, необязательна). Списывает сумму со
счёта, создаёт вклад и транзакцию `deposit_open` (сумма с минусом).
Ответ `201`: `{status: "ok", deposit_id ("dep-000001"), new_balance_rub,
deposit: {deposit_id, client_id, product_id, amount_rub, term_months,
rate_pct, opened_at, maturity_date, expected_income_rub, status: "active",
tx_id}}`. `expected_income_rub` — простые проценты к концу срока (или
`null`, если ставка не передана).
Ошибки: `422` — денег на счёте не хватает (`detail` по-русски, с балансом),
нет `product_id`, неверная сумма/срок/ставка; `404` — клиента нет.
Повтор с тем же `idempotency_key` второй вклад не открывает.

### GET /api/deposits/{client_id}
Вклады клиента, новые сверху: `{total, total_amount_rub, items: [вклад]}`.
`404`, если клиента нет.

### R2-B1. GET /clients/{client_id}/profile
Всё для решения cib **одним запросом**: карточка клиента (те же поля, что
`GET /clients/{id}`: `id, name, age, segment, income_rub, balance_rub,
products, risk_score, has_overdue_history, ...`) плюс
`summary` (ровно тот же блок, что в `/credit-history`), `last_salary_at`
(дата последней зарплаты `YYYY-MM-DD` или `null`) и
`deposits: {count, total_amount_rub}`. `404`, если клиента нет.
Пример (c-01002): `segment "mass", income_rub 40425, risk_score 0.286,
summary {active_count 0, monthly_debt_payment_rub 0, is_salary_client true,
avg_salary_rub 40425, ...}, last_salary_at "2026-03-01"`.

## Релиз 3 — погашение кредита (R3-B1, по ТЗ retail)

### Остаток долга в `GET /credit-history/{client_id}`
У каждого кредита со `status: "active"` в `items` теперь есть
`outstanding_rub` (остаток долга) и `monthly_payment_rub` (аннуитетный платёж).
Остаток: для кредитов из исходных данных — по графику аннуитета на сегодня
(если срок истёк — 0); для выданных через наш банк — сумма кредита; в обоих
случаях минус платежи через `POST /api/credit-payments`.
Пример c-01000: `ch-000002` (149 669 ₽, 60 мес, 21.54%, с 2022-11-18) →
`outstanding_rub 50294, monthly_payment_rub 4095`.

### POST /api/credit-payments
Вход `{client_id, credit_id, amount_rub, idempotency_key?}`. Списывает
сумму со счёта, уменьшает остаток, добавляет транзакцию `credit_payment`
(с минусом). Если остаток стал 0 — кредит `closed_clean` (+`closed_at`) и
перестаёт учитываться в нагрузке (`summary.monthly_debt_payment_rub`).
Ответ `201`: `{status: "ok", payment_id ("pay-000001"), credit_id, amount_rub,
new_balance_rub, outstanding_rub, closed: bool, tx_id}`.
Ошибки: `404` — нет клиента или у клиента нет такого кредита; `422` — не
хватает денег, сумма больше остатка, кредит уже закрыт или выплачен по
графику, неверная сумма. Повтор с тем же `idempotency_key` второй раз не
списывает (возвращает тот же ответ).

### GET /api/credit-payments/{client_id}
Платежи клиента по кредитам, новые сверху: `{total, items: [ответ POST + ts]}`.

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
