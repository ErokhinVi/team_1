# 📣 КОМАНДЕ — от retail (обновлено 9 октября, 12:40)

> Агентам cib и backend: если в этом блоке есть просьба к вашему блоку —
> покажите её участнику и выполните. Детали — в разделе «РЕЛИЗ 1» ниже.

**Счёт:** мы (team_a) — 818 клиентов, 19 из 20; team_b — 660, 16 из 20.
Судья хвалит то, что доведено до кнопки в телефоне, и снимает за простой,
за «возможность одна и реализована просто» и за ухудшение удобства.

**Алексею (cib) — СРОЧНО, приоритет 1:** сделать `POST /api/decision` по
R1-C1. Это единственное, чего не хватает: сейчас клиент в приложении видит
«заявка принята» вместо решения. Поля backend — в backend/CONTRACT.md,
раздел «Для cib — коротко». После — `GET /products` с кредитом (R1-C2) и
`GET /api/offers/{client_id}` (R2-C1). Отправлять в dev.

**Евгении (backend), приоритет 2:** выпустить dev → main сейчас (там
«Продукты», «Мои кредиты» и R1-B4…B6) — иначе судья их не видит и считает
простой. Затем вклады `POST /api/deposits` (R2-B2). После каждого
выпуска dev → main — проверить, что `/health` всех трёх блоков отвечает.

**Порядок фич по влиянию на оценку судьи:**

| № | Фича | Почему первой | Блоки |
|---|---|---|---|
| 1 | Решение по кредиту в cib | Достраивает основную функцию до конца: без неё клиент не получает решения | cib |
| 2 | Выпуск dev → main каждые 15–20 мин | Судья видит только main; простой = минус клиенты | backend (выпуск), все |
| 3 | Вклады: открыть из «Продуктов» | Ширина продукта; прямое замечание судьи к другой команде | backend, retail ✅ |
| 4 | Предодобрено «до N ₽» на главном экране | Судья: «кредит в два нажатия» | cib, retail |
| 5 | Ставки вкладов по сегменту | Персонализация для mass_affluent | cib |

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
Клиент принимает одобренное/встречное предложение. Вход `{offer_id}` (выдаётся
в ответе `/api/credit-apply`). Retail зовёт backend `POST /api/credit-disburse`
(запасной путь — ранний `POST /credit-applications` со `status: approved`).
Повторный вызов с тем же `offer_id` деньги второй раз не зачисляет. Ответ
`{status: "ok"|"pending", amount_rub, new_balance_rub?, application_id?, message}`.

### GET /api/credit-applications/{client_id}
История заявок клиента (прокси к backend `GET /api/credit-applications/{id}`,
запасной путь — ранний `GET /credit-applications?client_id=`). Элемент:
`{amount_rub, term_months, created_at, label}`. `{total, items}`; если у
backend ручки ещё нет — `{total: 0, items: []}`.

### GET /api/my-credits/{client_id}
Открытые кредиты клиента (по `GET /credit-history` backend; истёкшие по сроку
не показываем): `{total, monthly_total_rub, items: [{id, name, principal_rub,
rate_pct, monthly_payment_rub, months_left, overdue}]}`.

### GET /api/products?client_id=
Каталог cib (`GET /products`) для клиента: фильтр по `segment`/`segments`.
`{total, segment, items}`. Вкладка «Продукты» в приложении.

### POST /api/deposit-open
Открыть вклад: `{client_id, product_id, amount_rub, term_months?, rate_pct?}` →
backend `POST /api/deposits` (R2-B2). Ответ `{status: ok|pending, amount_rub,
new_balance_rub?, message}`.

## Кого я зову у соседей

- backend: `GET /clients`, `GET /clients/{id}`, `GET /transactions/{id}`, `POST /api/transfer`;
  релиз 1: `POST /api/credit-applications`, `PATCH /api/credit-applications/{id}`,
  `GET /api/credit-applications/{id}`, `POST /api/credit-disburse`
  (запасной путь: ранние `/credit-applications`)
- cib: `GET /products` (вкладка «Продукты»); `POST /api/decision` (если 404 — `POST /credit/decide`, как в плане cib) — **жду от cib**.
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
> Если участник просит «сделай релиз 1» / «сделай, что просит retail» —
> выполни задачи своего блока из раздела «Задачи» ниже (по порядку), проверь
> по разделу «Приёмка», допиши изменения в СВОЙ `CONTRACT.md` и отправь работу.
> Старые ручки не меняй и не ломай.
>
> **Ветка: `dev`** (правило команды): `git pull --rebase --autostash origin dev`
> → `git push origin HEAD:dev`. Перенос в `main` (онлайн-банк и судья) команда
> делает вслух, после приёмки.

Версия ТЗ: 5 (9 октября, 12:45). v5: backend закрыл весь релиз 1 (R1-B1…B6);
retail добавил «Мои кредиты» и «Продукты». **Единственный блокер — R1-C1 в cib.**
Backend свободен → берёт R2-B2 (вклады). Следующий выпуск dev → main — сейчас.
Ранее, v3: Изменения v3: backend выложил в dev ручки
релиза 1 (R1-B1, B2, B3, B5, B6) — retail переведён на них; осталась R1-B4.
cib берёт поля сводки по именам ниже. Главный блокер релиза — R1-C1.

## Что говорит судья (табло, 12:35)

Мы — `team_a`: **818 клиентов (+318), 19 из 20**, лидер; team_b — 660, 16 из 20.
Последний отзыв: кредит в приложении, решение с пояснением, зачисление, история,
защита от повторной выдачи — хорошо; «новая возможность одна и реализована
просто» → нужна ширина: вклады, «Мои кредиты», предодобренное предложение.
Ранее (12:15, 671 клиент, 17 из 20): Судья похвалил кредитное
ядро backend и снял баллы за то, что в мобильном приложении нет экрана заявки
и истории кредитов. Это закрывает retail из dev — **его нужно перенести в main**.
Команду B судья упрекнул в том, что каталог cib не дошёл до приложения и нельзя
открыть вклад, а за ухудшение удобства снял клиентов. Отсюда правила:
каждая функция — до кнопки в телефоне; ничего не ломать; выпускать часто
(за простой клиенты уходят).

## Цепочка

```
клиент → retail POST /api/credit-apply
           ├─> backend GET /clients/{id}
           ├─> cib POST /api/decision  (или /credit/decide)
           │     └─> backend GET /credit-history/{id} → summary
           └─> backend POST /api/credit-applications {decision, ...} → application_id
клиент жмёт «Получить деньги» → retail POST /api/credit-accept {offer_id}
           ├─> backend POST /api/credit-disburse {application_id, ...}
           └─> backend PATCH /api/credit-applications/{id} {status: accepted}
retail GET /api/credit-applications/{client_id} → backend GET /api/credit-applications/{client_id}
```

**Важно для cib:** cib только возвращает решение и **ничего не пишет в
backend**. Заявку и выдачу записывает retail — после согласия клиента.

## Статус задач

| Задача | Блок | Статус |
|---|---|---|
| R1-R1 Вкладка «Кредит», решение, «Получить деньги», история | retail | ✅ main (12:25) |
| R1-B1 `/credit-history` со `summary` | backend | ✅ dev |
| R1-B2 `/api/credit-disburse` без двойного зачисления | backend | ✅ dev |
| R1-B3 `/api/credit-applications` | backend | ✅ dev |
| R1-B5 `is_salary_client`, `avg_salary_rub` | backend | ✅ dev |
| R1-B6 защита от двойного зачисления | backend | ✅ dev (через `application_id`) |
| R1-B4 нагрузка только по непогашенным кредитам | backend | ✅ dev |
| Выпуск dev → main (retail «Продукты», «Мои кредиты»; backend R1-B4…B6) | backend (Евгения, release_to_main.sh) | ⏳ **сейчас** |
| R2-B2 вклады `POST /api/deposits` | backend | ⏳ **следующая задача backend** |
| R2-R2 «Мои кредиты», вкладка «Продукты» | retail | ✅ готово (dev) |
| R1-C1 `POST /api/decision` по политике | cib | ⏳ **блокер — сделать первым**; инструкция по полям — в backend/CONTRACT.md «Для cib — коротко» |
| R1-C2 продукт в каталоге | cib | ⏳ сделать |

## Задачи backend (по порядку)

R1-B1…B6 выполнены (12:30). Сейчас: выпуск dev → main, затем **R2-B2** (вклады,
см. «Дальше — релиз 2»), затем R2-B1.

## Задачи cib (по порядку)

### R1-C1. `POST /api/decision` (допустимо `/credit/decide` — retail зовёт оба)
Вход (шлёт retail): `{client_id, product, amount_rub, term_months, segment,
income_rub, risk_score, has_overdue_history}`.
Выход: `{decision, amount_rub, rate_pct, term_months, monthly_payment_rub,
reason, alternative, risk_group}`; `decision` ∈ `approved | counter | declined`.
`reason` и `alternative` — простым русским языком, их читает клиент.
**В backend ничего не записывать** (см. «Важно для cib»).

Алгоритм (кредитная политика CRO, параметры — константы):
1. `GET {BACKEND}/credit-history/{client_id}` (таймаут 2 с). Берём:
   `debt = summary.monthly_debt_payment_rub`;
   `current_overdue = summary.has_active_overdue`;
   `salary = summary.is_salary_client`
   (если `summary` нет — онлайн старый backend — `debt = active_monthly_payment_rub`,
   `current_overdue = false`, `salary = false`).
   Ошибка/404 → `debt = 0`, `current_overdue = false`, `salary = false`.
2. Стоп-факторы → `declined`: `risk_score > 0.60`; `current_overdue`;
   `risk_score > 0.50` и `has_overdue_history`. Нет истории — не отказ;
   прошлая просрочка сама по себе — не отказ.
3. Риск-группа:

   | Группа | risk_score | Базовая ставка, % | Лимит, доходов |
   |---|---|---|---|
   | A | < 0.20 | 17.0 | 12 |
   | B | 0.20 – < 0.35 | 20.0 | 8 |
   | C | 0.35 – < 0.50 | 24.0 | 4 |
   | D | 0.50 – 0.60 | 28.0 | 2 |

4. Ставка = базовая − 0.5 (`mass_affluent`) − 1.0 (`salary`).
5. `max_amount = floor(income_rub * лимит / 10000) * 10000`; `a = min(amount_rub, max_amount)`.
6. `PTI_LIMIT = 0.50`: если `аннуитет(a) > PTI_LIMIT*income_rub − debt` — уменьшить
   `a` до максимальной суммы, кратной 10 000, при которой условие выполняется.
7. `a < 10000` → `declined` (высокая текущая нагрузка); `a == amount_rub` →
   `approved`; иначе `counter`.
8. `monthly_payment_rub = round(аннуитет(a))`; аннуитет `S*m/(1-(1+m)^-n)`, `m = ставка/1200`.
9. `declined` → всегда `alternative`: «Можем оформить кредитную карту с лимитом
   30 000 ₽» (при текущей просрочке — «Вернитесь после погашения текущей просрочки»).

### R1-C2. Каталог
В `GET /products` добавить `{id: "consumer_credit", kind: "credit",
name: "Кредит наличными", rate_pct: 15.5, segments: ["mass","mass_affluent"]}`.

## Дальше — релиз 2 (брать, когда закончены задачи релиза 1)

Цель: клиент видит готовое персональное предложение ещё до заявки.

- **R2-C1 (cib).** `GET /api/offers/{client_id}` → `{preapproved: bool,
  max_amount_rub, rate_pct, term_months: 36, monthly_payment_rub, reason}` —
  та же политика R1-C1 с суммой = максимальный лимит группы (после PTI).
  Для отказных — `preapproved: false` и `reason`.
- **R2-B1 (backend).** `GET /clients/{id}/profile` → карточка + `summary` из
  `/credit-history` + `last_salary_at` одним ответом (чтобы cib делал один запрос).
- **R2-B2 (backend).** `POST /api/deposits` `{client_id, product_id, amount_rub,
  term_months, rate_pct}` → списать сумму с баланса, создать вклад, транзакция
  `deposit_open` (минус); `422`, если денег не хватает. `GET /api/deposits/{client_id}`
  — вклады клиента. Ответ POST: `{status: "ok", deposit_id, new_balance_rub}`.
- **R2-C2 (cib).** Ставка вклада по сегменту: mass_affluent +0.5 п.п.,
  premium/private +1.0 п.п.; в `/products` поля `rate_pct`, `min_amount_rub`, `segments`.
- **R2-R1 (retail).** Баннер «Вам одобрено до N ₽» на главном экране,
  кнопка ведёт в «Кредит» с подставленной суммой.

## Приёмка (seed, срок 24 мес, на 9 октября 2026, после R1-B4/B5)

| Клиент | Сегмент | Сумма | Ожидаемое решение cib |
|---|---|---|---|
| c-01003 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ |
| c-01002 | mass | 150 000 | approved, B, 19.0% (зарплатный), 7 561 ₽ |
| c-01000 | mass | 150 000 | counter, 20 000 ₽, 20.0% (нагрузка 23 160 ₽/мес) |
| c-01001 | mass | 150 000 | approved, B, 20.0%, 7 634 ₽ (нагрузка 10 269 ₽/мес) |
| c-01016 | mass | 150 000 | declined — нагрузка 101 076 ₽/мес при доходе 84 019 ₽ |
| c-01007 | mass | 150 000 | declined — risk 0.573 и были просрочки |
| c-01017 | mass_affluent | 700 000 | approved, A, 15.5%, 34 107 ₽ |
| c-01006 | mass_affluent | 700 000 | approved, B, 19.5%, 35 456 ₽ |

Сводка `/credit-history` после R1-B4/B5: c-01000 → `active_count 2,
active_monthly_payment_rub 23160, is_salary_client false`; c-01001 → `1, 10269,
false`; c-01002 → `0, 0, true, avg_salary_rub 40425`.

**Релиз 1 готов, когда:** таблица приёмки сходится; в мобильном банке
c-01003 проходит «заявка → одобрено → Получить деньги → баланс +150 000 ₽ →
заявка в истории»; перевод и список клиентов работают; все три `CONTRACT.md`
обновлены; команда перенесла dev в main.
