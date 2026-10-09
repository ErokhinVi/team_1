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

### GET /api/credit-presets/{client_id}
Готовые суммы и сроки кредита под сегмент клиента (mass, mass_affluent).
Возвращает `{client_id, segment, segment_label, amounts: [₽], terms: [мес],
default_amount, default_term}`.

### POST /api/credit-apply
Заявка на кредит наличными. Принимает JSON `{client_id, amount_rub, term_months,
product?}` (product по умолчанию `consumer_credit`). Retail берёт карточку
клиента в backend, спрашивает решение у cib и возвращает
`{client_id, segment, segment_label, requested_amount_rub, requested_term_months,
decision, amount_rub, rate_pct, term_months, monthly_payment_rub, total_cost_rub,
reason, alternative, message}`. `decision` — `approved | counter | declined |
pending` (`pending` — если cib пока не ответил).

### POST /api/credit-accept
Клиент принимает одобренное/встречное предложение. Вход `{client_id, amount_rub,
rate_pct, term_months, application_id?}`. Зовёт backend R1-B2 и R1-B3. Ответ
`{status: "ok"|"pending", new_balance_rub?, amount_rub, message}`.

### GET /api/credit-applications/{client_id}
История заявок клиента (прокси к backend R1-B3). `{total, items}`; если у
backend ручки ещё нет — `{total: 0, items: []}`.

## Кого я зову у соседей

- backend: `GET /clients`, `GET /clients/{id}`, `GET /transactions/{id}`, `POST /api/transfer`;
  релиз 1: `POST /api/credit-disburse`, `POST|PATCH /api/credit-applications`, `GET /api/credit-applications/{id}`
- cib: `POST /api/decision` — **жду от cib** (пока его нет в контракте cib).
  Шлю `{client_id, product, amount_rub, term_months, segment, income_rub,
  risk_score, has_overdue_history}`.
  Жду `{decision: approved|counter|declined, amount_rub, rate_pct, term_months,
  monthly_payment_rub?, reason, alternative?}`. `reason` и `alternative` —
  человеческим языком, их видит клиент. Если `monthly_payment_rub` нет,
  retail посчитает аннуитет сам.

## Где работает блок локально

`http://localhost:8001` (порт фиксируется docker-compose).

---

# РЕЛИЗ 1 — сквозной кредит наличными (mass + mass_affluent)

> **Агенту cib и агенту backend.** Это техническое задание от блока retail.
> Если участник просит «сделай релиз 1» или «сделай, что просит retail» —
> реализуй раздел своего блока ниже целиком, проверь его на примерах из
> раздела «Приёмка», допиши новые ручки в СВОЙ `CONTRACT.md` и отправь работу.
> Старые ручки не меняй и не ломай. Форматы ниже — обязательные: retail уже
> написан под них.
>
> **Ветка: `dev`.** Все изменения релиза 1 отправляются в `dev`, не в `main`:
> `git pull --rebase --autostash origin dev` → `git push origin HEAD:dev`
> (если `dev` ещё нет — первый `git push origin HEAD:dev` её создаст).
> Перенос в `main` (онлайн-банк и судья) команда делает отдельно, вслух.

## Цель релиза

Клиент массового сегмента и mass_affluent в мобильном банке выбирает сумму и
срок, за секунду получает решение (одобрено / встречное / отказ с причиной и
альтернативой), видит ставку, платёж и полную стоимость, а при одобрении
деньги зачисляются на счёт.

## Цепочка

```
retail  POST /api/credit-apply ─┬─> backend GET  /clients/{id}            (есть)
                                 ├─> cib     POST /api/decision            (R1-C1)
                                 │            └─> backend GET /credit-history/{id}  (R1-B1)
                                 └─> backend POST /api/credit-applications (R1-B3, сохранить заявку)
retail  POST /api/credit-accept ─┬─> backend POST /api/credit-disburse     (R1-B2)
                                 └─> backend PATCH /api/credit-applications/{id} (R1-B3)
retail  GET  /api/credit-applications/{id} ─> backend GET /api/credit-applications/{id} (R1-B3)
```

Порядок работы: все три блока стартуют одновременно. cib не ждёт backend —
если `/credit-history` ещё отдаёт 404, решение принимается по полям запроса
(см. R1-C1, «деградация»).

Общие правила для всех ручек: JSON, ответ < 1 с; неизвестный клиент → 404;
неверный ввод → 422 с `detail` по-русски; деньги — целые рубли.

## Задачи backend

### R1-B1. `GET /credit-history/{client_id}`
Источник — `seed/credit_history.jsonl` и транзакции клиента.
Ответ:
```
{ "client_id": "c-01000",
  "total": 3, "items": [ {id, product, principal_rub, term_months, rate_pct,
                          opened_at, status, overdue_days_max}, ... ],
  "summary": {
    "active_count": 2,
    "max_overdue_days": 0,            // максимум overdue_days_max по ВСЕМ записям
    "has_active_overdue": false,      // есть active с overdue_days_max > 0
    "monthly_debt_payment_rub": 23160,// сумма аннуитетов по active (формула ниже), round
    "is_salary_client": false,        // есть транзакции type == "salary"
    "avg_salary_rub": 0               // среднее по salary, round; 0 если нет
  } }
```
Аннуитет: `P = S * m / (1 - (1+m)^-n)`, `m = rate_pct/1200`, `n = term_months`.
Кредиты, выданные через R1-B2, тоже попадают сюда как `active`.

### R1-B2. `POST /api/credit-disburse`
Вход: `{client_id, amount_rub, rate_pct, term_months, application_id?}`.
Действие: увеличить `balance_rub` клиента на `amount_rub`; добавить транзакцию
`{type: "credit_disbursement", amount_rub: +сумма}`; добавить в кредитную
историю запись `{product: "consumer_credit", status: "active", overdue_days_max: 0,
opened_at: сегодня}`.
Ответ: `{status: "ok", client_id, credit_id, tx_id, amount_rub, new_balance_rub}`.
Повторный вызов с тем же `application_id` не зачисляет деньги второй раз
(вернуть тот же ответ).

### R1-B3. Заявки
`POST /api/credit-applications` — вход `{client_id, amount_rub, term_months,
decision, rate_pct?, approved_amount_rub?, monthly_payment_rub?, reason?}`,
ответ `{application_id, created_at, ...вход}`.
`GET /api/credit-applications/{client_id}` — `{total, items}`, новые сверху.
`PATCH /api/credit-applications/{application_id}` — `{status: "accepted"|"rejected_by_client"}`.

## Задачи cib

### R1-C1. `POST /api/decision`
Вход (шлёт retail): `{client_id, product, amount_rub, term_months, segment,
income_rub, risk_score, has_overdue_history}`.
Выход: `{decision, amount_rub, rate_pct, term_months, monthly_payment_rub,
reason, alternative, risk_group}`; `decision` ∈ `approved | counter | declined`.
`reason` и `alternative` — простым русским языком, их читает клиент.

Алгоритм (кредитная политика CRO, параметры вынести в константы):
1. Запросить у backend `GET /credit-history/{client_id}` → `summary`.
   **Деградация:** 404/ошибка/таймаут 2 с → считать `monthly_debt_payment_rub=0`,
   `has_active_overdue=false`, `is_salary_client=false` и продолжить.
2. Стоп-факторы → `declined`:
   `risk_score > 0.60`; `has_active_overdue`; `risk_score > 0.50` и `has_overdue_history`.
3. Риск-группа по `risk_score`:

   | Группа | risk_score | Базовая ставка, % | Лимит, доходов |
   |---|---|---|---|
   | A | < 0.20 | 17.0 | 12 |
   | B | 0.20 – < 0.35 | 20.0 | 8 |
   | C | 0.35 – < 0.50 | 24.0 | 4 |
   | D | 0.50 – 0.60 | 28.0 | 2 |

4. Ставка: базовая − 0.5 для `mass_affluent` − 1.0 для `is_salary_client`.
5. `max_amount = floor(income_rub * лимит / 10000) * 10000`; `a = min(amount_rub, max_amount)`.
6. Нагрузка: `PTI_LIMIT = 0.50`. Если `аннуитет(a) > PTI_LIMIT*income_rub − monthly_debt_payment_rub`,
   уменьшить `a` до максимальной суммы, кратной 10 000, при которой условие выполняется.
7. `a < 10000` → `declined` (причина — высокая текущая нагрузка),
   `a == amount_rub` → `approved`, иначе → `counter`.
8. `monthly_payment_rub = round(аннуитет(a))`.
9. При `declined` всегда `alternative`: «Можем оформить кредитную карту с лимитом 30 000 ₽»
   (при стоп-факторе по просрочке — «Вернитесь после погашения текущей просрочки»).

### R1-C2. Каталог
Добавить в `GET /products`:
`{id: "consumer_credit", kind: "credit", name: "Кредит наличными", rate_pct: 15.5,
segments: ["mass","mass_affluent"]}` (`rate_pct` — минимальная ставка «от»).

## Задачи retail (сделано / делаю)
- [x] Вкладка «Кредит», пресеты под сегмент, `POST /api/credit-apply`, мягкий ответ без cib.
- [x] Кнопка «Получить деньги» → `POST /api/credit-accept` (зовёт R1-B2 и R1-B3), обновление баланса.
- [x] История заявок клиента (R1-B3).

## Приёмка (на стартовых данных seed, срок 24 мес)

| Клиент | Сегмент | Сумма | Без R1-B1 (деградация) | С R1-B1 |
|---|---|---|---|---|
| c-01003 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ | то же |
| c-01002 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ | approved, 19.0% (зарплатный), 7 561 ₽ |
| c-01000 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ | counter, 20 000 ₽ (нагрузка 23 160 ₽/мес) |
| c-01001 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ | declined (нагрузка выше 50% дохода) |
| c-01007 | mass | 150 000 | declined (risk 0.573 + просрочки) | то же |
| c-01017 | mass_affluent | 700 000 | approved, A, 16.5%, 34 442 ₽ | approved, 15.5%, 34 107 ₽ |
| c-01006 | mass_affluent | 700 000 | approved, B, 19.5%, 35 456 ₽ | то же |

Сводка R1-B1 для проверки: c-01000 → `active_count 2, monthly_debt_payment_rub 23160,
is_salary_client false`; c-01002 → `0, 0, true, avg_salary_rub 40425`.

Релиз 1 готов, когда: все ручки выше отвечают; таблица приёмки сходится;
в мобильном банке клиент c-01003 проходит путь «заявка → одобрено → получить
деньги → баланс вырос на 150 000 ₽»; старые функции (перевод, список клиентов)
работают; все три `CONTRACT.md` обновлены.
