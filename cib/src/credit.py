"""Deterministic rules for the workshop's preliminary consumer-credit offer."""

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

CENT = Decimal("0.01")
POLICY_VERSION = "workshop-credit-v1"
MAX_DEBT_SHARE = Decimal("0.40")
MIN_AMOUNT = Decimal("30000")
MAX_AMOUNT = Decimal("3000000")
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
DecisionName = Literal["approved", "rejected", "counteroffer"]

CREDIT_PRODUCT = {
    "id": "consumer_credit",
    "kind": "credit",
    "name": "Кредит наличными",
    "currency": "RUB",
    "rate_pct": 19.9,
    "rate_max_pct": 24.9,
    "min_amount_rub": 30000,
    "max_amount_rub": 3000000,
    "min_term_months": 6,
    "max_term_months": 60,
    "fees_rub": 0,
    "insurance_required": False,
    "decision_scope": "preliminary",
    "policy_version": POLICY_VERSION,
    "description": "Учебный продукт: предварительное решение без выдачи денег.",
}


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


class LoanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_rub: Decimal = Field(
        ge=MIN_AMOUNT, le=MAX_AMOUNT, max_digits=12, decimal_places=2, allow_inf_nan=False
    )
    term_months: int = Field(ge=6, le=60, strict=True)
    product: Literal["consumer_credit"] = "consumer_credit"

    @field_validator("amount_rub", mode="before")
    @classmethod
    def reject_boolean_amount(cls, value):
        if isinstance(value, bool):
            raise ValueError("Сумма должна быть числом")
        return value


class CreditRequest(LoanRequest):
    client_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    purpose: str | None = Field(default=None, max_length=200)


class ClientData(BaseModel):
    id: str
    age: int = Field(ge=0, le=130, strict=True)
    segment: str
    income_rub: Decimal = Field(ge=0, max_digits=16, decimal_places=2, allow_inf_nan=False)
    risk_score: Decimal = Field(ge=0, le=1, max_digits=8, decimal_places=6, allow_inf_nan=False)
    has_overdue_history: bool = Field(strict=True)

    @field_validator("income_rub", "risk_score", mode="before")
    @classmethod
    def reject_boolean_number(cls, value):
        if isinstance(value, bool):
            raise ValueError("Expected numeric financial data")
        return value


class HistorySummary(BaseModel):
    has_active_overdue: bool | None = Field(default=None, strict=True)


class HistoryData(BaseModel):
    client_id: str
    total: int = Field(ge=0, strict=True)
    active_count: int = Field(ge=0, strict=True)
    active_monthly_payment_rub: Decimal = Field(
        ge=0, max_digits=16, decimal_places=2, allow_inf_nan=False
    )
    max_overdue_days: int = Field(ge=0, strict=True)
    has_overdue: bool = Field(strict=True)
    summary: HistorySummary | None = None

    @field_validator("active_monthly_payment_rub", mode="before")
    @classmethod
    def reject_boolean_payment(cls, value):
        if isinstance(value, bool):
            raise ValueError("Expected a numeric debt payment")
        return value

    @model_validator(mode="after")
    def check_summary(self):
        if self.active_count > self.total:
            raise ValueError("Active count exceeds total history records")
        if (self.active_count == 0) != (self.active_monthly_payment_rub == 0):
            raise ValueError("Debt payment and active count are inconsistent")
        return self


class LoanQuote(BaseModel):
    amount_rub: Money
    term_months: int
    rate_pct: Money
    monthly_payment_rub: Money
    last_payment_rub: Money
    total_payment_rub: Money
    overpayment_rub: Money


class CreditDecision(LoanQuote):
    client_id: str
    product: str = "consumer_credit"
    decision: DecisionName
    status: DecisionName
    approved: bool
    reason_code: str
    reason: str
    counter_offer: LoanQuote | None = None
    income_rub: Money
    existing_monthly_payment_rub: Money
    available_monthly_payment_rub: Money
    debt_to_income_ratio: Money | None
    max_debt_to_income_ratio: Money = MAX_DEBT_SHARE
    decision_scope: str = "preliminary"
    can_disburse: bool = False
    policy_version: str = POLICY_VERSION
    warnings: list[str]


def payment_schedule(amount: Decimal, months: int, rate_pct: Decimal) -> list[dict]:
    """Round installments to kopeks and close any remainder in the last one."""
    if not amount.is_finite() or not rate_pct.is_finite():
        raise ValueError("Amount and rate must be finite")
    if amount <= 0 or months <= 0 or rate_pct < 0:
        raise ValueError("Invalid loan parameters")
    with localcontext() as context:
        context.prec = 32
        rate = rate_pct / Decimal(1200)
        regular = money(
            amount / months if not rate else amount * rate / (1 - (1 + rate) ** -months)
        )
        balance = money(amount)
        rows = []
        for month in range(1, months + 1):
            interest = money(balance * rate)
            installment = balance + interest if month == months else min(regular, balance + interest)
            principal = installment - interest
            balance = money(balance - principal)
            rows.append({
                "month": month, "payment_rub": installment, "interest_rub": interest,
                "principal_rub": principal, "balance_rub": balance,
            })
        return rows


def quote(amount: Decimal, months: int, rate_pct: Decimal) -> LoanQuote:
    rows = payment_schedule(amount, months, rate_pct)
    total = sum((row["payment_rub"] for row in rows), Decimal(0))
    return LoanQuote(
        amount_rub=money(amount), term_months=months, rate_pct=rate_pct,
        monthly_payment_rub=rows[0]["payment_rub"],
        last_payment_rub=rows[-1]["payment_rub"],
        total_payment_rub=money(total), overpayment_rub=money(total - amount),
    )


def rate_for(client: ClientData) -> Decimal:
    # Workshop policy, not an estimate of real default probability.
    return Decimal("19.9") if client.risk_score < Decimal("0.5") else Decimal("24.9")


def affordable_offer(request: CreditRequest, budget: Decimal, rate: Decimal) -> LoanQuote | None:
    """Search whole thousands; every returned installment must fit the budget."""
    low = int(MIN_AMOUNT / 1000)
    high = int((request.amount_rub / 1000).to_integral_value(rounding=ROUND_DOWN))
    result = None
    while low <= high:
        mid = (low + high) // 2
        candidate = quote(Decimal(mid * 1000), request.term_months, rate)
        if max(candidate.monthly_payment_rub, candidate.last_payment_rub) <= budget:
            result = candidate
            low = mid + 1
        else:
            high = mid - 1
    return result


def decide(request: CreditRequest, client: ClientData, history: HistoryData) -> CreditDecision:
    if client.id != request.client_id or history.client_id != request.client_id:
        raise ValueError("Client identities do not match")
    rate = rate_for(client)
    requested = quote(request.amount_rub, request.term_months, rate)
    # Round the budget down so rounding cannot increase the allowed debt share.
    budget = max(Decimal(0), client.income_rub * MAX_DEBT_SHARE - history.active_monthly_payment_rub)
    budget = budget.quantize(CENT, rounding=ROUND_DOWN)
    largest_payment = max(requested.monthly_payment_rub, requested.last_payment_rub)
    ratio = (
        (history.active_monthly_payment_rub + largest_payment) / client.income_rub
        if client.income_rub else None
    )
    warnings = ["Предварительное решение: заявка не сохранена, деньги не выданы."]
    if history.total == 0:
        warnings.append("Кредитной истории нет; это само по себе не является причиной отказа.")
    if client.has_overdue_history or history.has_overdue:
        warnings.append("Учтены сведения о прошлых просрочках.")
    current_overdue = history.summary.has_active_overdue if history.summary else None
    if current_overdue is None:
        warnings.append("Статус текущей просрочки не предоставлен блоком данных.")

    decision: DecisionName = "rejected"
    counter_offer = None
    if client.age < 18:
        code, reason = "age", "Учебный кредит доступен совершеннолетним клиентам."
    elif client.segment == "sme":
        code, reason = "product_scope", "Этот продукт предназначен для физических лиц."
    elif client.income_rub == 0:
        code, reason = "income", "Для расчёта доступной суммы нужен подтверждённый доход."
    elif current_overdue:
        code, reason = "current_overdue", "Блок данных сообщает о текущей просрочке по кредиту."
    elif client.risk_score >= Decimal("0.65"):
        code, reason = "risk", "Показатель риска превышает предел учебного продукта."
    elif history.max_overdue_days >= 60:
        code, reason = "overdue_history", "В кредитной истории есть просрочка от 60 дней."
    elif largest_payment <= budget:
        decision = "approved"
        code, reason = "affordable", "Предварительно одобрено: платежи по кредитам укладываются в 40% дохода."
    else:
        counter_offer = affordable_offer(request, budget, rate)
        if counter_offer:
            decision = "counteroffer"
            code, reason = "smaller_amount", "Запрошенная сумма слишком велика. Доступна меньшая сумма на тот же срок."
        else:
            code, reason = "debt_burden", "С учётом действующих платежей доступного дохода недостаточно для минимальной суммы."

    return CreditDecision(
        **requested.model_dump(), client_id=request.client_id,
        decision=decision, status=decision, approved=decision == "approved",
        reason_code=code, reason=reason, counter_offer=counter_offer,
        income_rub=client.income_rub,
        existing_monthly_payment_rub=history.active_monthly_payment_rub,
        available_monthly_payment_rub=budget,
        debt_to_income_ratio=ratio.quantize(Decimal("0.0001")) if ratio is not None else None,
        warnings=warnings,
    )
