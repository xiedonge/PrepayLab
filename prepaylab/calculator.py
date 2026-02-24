from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

CENTS = Decimal("0.01")
EPS = Decimal("0.00000001")


class InputError(ValueError):
    pass


def _to_decimal(value: Any, field: str) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise InputError(f"{field} must be a number, got bool")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        if text == "":
            raise InputError(f"{field} is empty")
        return Decimal(text)
    raise InputError(f"{field} must be a number")


def _to_int(value: Any, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise InputError(f"{field} must be an integer, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise InputError(f"{field} must be an integer")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise InputError(f"{field} is empty")
        return int(text)
    raise InputError(f"{field} must be an integer")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _clamp_zero(value: Decimal) -> Decimal:
    if abs(value) <= EPS:
        return Decimal("0")
    return value


def _monthly_rate(annual_rate_percent: Decimal) -> Decimal:
    if annual_rate_percent < 0:
        raise InputError("annual_rate must be >= 0")
    return (annual_rate_percent / Decimal("100")) / Decimal("12")


def _epi_payment(principal: Decimal, rate: Decimal, months: int) -> Decimal:
    if months <= 0:
        raise InputError("term_months must be > 0")
    if rate == 0:
        return principal / Decimal(months)
    factor = (Decimal("1") + rate) ** Decimal(months)
    return principal * (rate * factor) / (factor - Decimal("1"))


def _epi_remaining_principal(
    principal: Decimal, rate: Decimal, months: int, paid_months: int, payment: Decimal
) -> Decimal:
    if paid_months <= 0:
        return principal
    if paid_months >= months:
        return Decimal("0")
    if rate == 0:
        remaining = principal - payment * Decimal(paid_months)
        return _clamp_zero(remaining)
    factor = (Decimal("1") + rate) ** Decimal(paid_months)
    remaining = principal * factor - payment * (factor - Decimal("1")) / rate
    return _clamp_zero(remaining)


def _ep_principal_payment(principal: Decimal, months: int) -> Decimal:
    if months <= 0:
        raise InputError("term_months must be > 0")
    return principal / Decimal(months)


def _ep_remaining_principal(principal: Decimal, principal_payment: Decimal, paid_months: int) -> Decimal:
    if paid_months <= 0:
        return principal
    remaining = principal - principal_payment * Decimal(paid_months)
    return _clamp_zero(remaining)


def _ep_total_interest(principal: Decimal, rate: Decimal, months: int) -> Decimal:
    if rate == 0:
        return Decimal("0")
    p = _ep_principal_payment(principal, months)
    n = Decimal(months)
    sum_balances = n * principal - p * (n - Decimal("1")) * n / Decimal("2")
    return sum_balances * rate


def _calc_penalty(
    base: Decimal,
    penalty_rate_percent: Decimal,
    penalty_fixed: Decimal,
    paid_months: int,
    penalty_free_months: Optional[int],
) -> Decimal:
    if penalty_free_months is not None and paid_months >= penalty_free_months:
        return Decimal("0")
    rate = (penalty_rate_percent / Decimal("100")) if penalty_rate_percent > 0 else Decimal("0")
    by_rate = base * rate if rate > 0 else Decimal("0")
    by_fixed = penalty_fixed if penalty_fixed > 0 else Decimal("0")
    if by_rate == 0 and by_fixed == 0:
        return Decimal("0")
    return max(by_rate, by_fixed)


def _simulate_epi(
    balance: Decimal,
    rate: Decimal,
    payment: Decimal,
    term_months: Optional[int],
    build_schedule: bool,
) -> Tuple[int, Decimal, List[Dict[str, Decimal]]]:
    schedule: List[Dict[str, Decimal]] = []
    months = 0
    total_interest = Decimal("0")
    while balance > EPS and (term_months is None or months < term_months):
        interest = balance * rate
        principal_paid = payment - interest
        if principal_paid <= 0:
            raise InputError("monthly payment is not enough to cover interest")

        is_last = term_months is not None and (months + 1) >= term_months
        if principal_paid > balance or is_last:
            principal_paid = balance
            payment_this = principal_paid + interest
        else:
            payment_this = payment

        balance = _clamp_zero(balance - principal_paid)
        months += 1
        total_interest += interest

        if build_schedule:
            schedule.append(
                {
                    "period": months,
                    "payment": payment_this,
                    "principal_paid": principal_paid,
                    "interest_paid": interest,
                    "balance": balance,
                }
            )

        if term_months is None and balance <= EPS:
            break

    return months, total_interest, schedule


def _simulate_ep(
    balance: Decimal,
    rate: Decimal,
    principal_payment: Decimal,
    term_months: Optional[int],
    build_schedule: bool,
) -> Tuple[int, Decimal, List[Dict[str, Decimal]]]:
    schedule: List[Dict[str, Decimal]] = []
    months = 0
    total_interest = Decimal("0")
    while balance > EPS and (term_months is None or months < term_months):
        interest = balance * rate
        is_last = term_months is not None and (months + 1) >= term_months
        if principal_payment > balance or is_last:
            principal_paid = balance
        else:
            principal_paid = principal_payment

        payment_this = principal_paid + interest
        balance = _clamp_zero(balance - principal_paid)
        months += 1
        total_interest += interest

        if build_schedule:
            schedule.append(
                {
                    "period": months,
                    "payment": payment_this,
                    "principal_paid": principal_paid,
                    "interest_paid": interest,
                    "balance": balance,
                }
            )

        if term_months is None and balance <= EPS:
            break

    return months, total_interest, schedule


def normalize_inputs(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []

    if "principal" not in data:
        raise InputError("principal is required")
    if "annual_rate" not in data:
        raise InputError("annual_rate is required")
    if "term_months" not in data:
        raise InputError("term_months is required")

    principal = _to_decimal(data.get("principal"), "principal")
    annual_rate = _to_decimal(data.get("annual_rate"), "annual_rate")
    term_months = _to_int(data.get("term_months"), "term_months")

    repayment_type = str(data.get("repayment_type", "EPI")).upper()
    if repayment_type not in {"EPI", "EP"}:
        raise InputError("repayment_type must be 'EPI' or 'EP'")

    paid_months = _to_int(data.get("paid_months", data.get("prepay_month_index", 0)), "paid_months")
    prepay_month_index = _to_int(data.get("prepay_month_index", paid_months), "prepay_month_index")
    if prepay_month_index != paid_months:
        warnings.append("paid_months and prepay_month_index differ; using prepay_month_index")
        paid_months = prepay_month_index

    prepay_type = str(data.get("prepay_type", "partial")).lower()
    if prepay_type not in {"partial", "full"}:
        raise InputError("prepay_type must be 'partial' or 'full'")

    strategy = str(data.get("strategy", "reduce_term")).lower()
    if strategy not in {"reduce_term", "reduce_payment"}:
        raise InputError("strategy must be 'reduce_term' or 'reduce_payment'")

    prepay_amount = _to_decimal(data.get("prepay_amount", 0), "prepay_amount")

    penalty_rate = _to_decimal(data.get("penalty_rate", 0), "penalty_rate")
    penalty_fixed = _to_decimal(data.get("penalty_fixed", 0), "penalty_fixed")
    penalty_free_months_raw = data.get("penalty_free_months")
    penalty_free_months = None
    if penalty_free_months_raw is not None:
        penalty_free_months = _to_int(penalty_free_months_raw, "penalty_free_months")

    min_prepay_amount = data.get("min_prepay_amount")
    if min_prepay_amount is not None:
        min_prepay_amount = _to_decimal(min_prepay_amount, "min_prepay_amount")

    if principal <= 0:
        raise InputError("principal must be > 0")
    if term_months <= 0:
        raise InputError("term_months must be > 0")
    if paid_months < 0 or paid_months > term_months:
        raise InputError("paid_months must be between 0 and term_months")
    if annual_rate < 0:
        raise InputError("annual_rate must be >= 0")
    if prepay_amount < 0:
        raise InputError("prepay_amount must be >= 0")
    if penalty_rate < 0 or penalty_fixed < 0:
        raise InputError("penalty_rate/penalty_fixed must be >= 0")

    if min_prepay_amount is not None and prepay_amount > 0 and prepay_amount < min_prepay_amount:
        raise InputError("prepay_amount is below min_prepay_amount")

    if "as_of_date" in data or "first_payment_date" in data:
        warnings.append("Date-based calculation is not implemented; using paid_months only")

    normalized = {
        "principal": principal,
        "annual_rate": annual_rate,
        "term_months": term_months,
        "repayment_type": repayment_type,
        "paid_months": paid_months,
        "prepay_month_index": prepay_month_index,
        "prepay_amount": prepay_amount,
        "prepay_type": prepay_type,
        "strategy": strategy,
        "penalty_rate": penalty_rate,
        "penalty_fixed": penalty_fixed,
        "penalty_free_months": penalty_free_months,
        "min_prepay_amount": min_prepay_amount,
    }
    return normalized, warnings


def calculate(data: Dict[str, Any], include_schedule: bool = False) -> Dict[str, Any]:
    inputs, warnings = normalize_inputs(data)

    principal: Decimal = inputs["principal"]
    annual_rate: Decimal = inputs["annual_rate"]
    term_months: int = inputs["term_months"]
    repayment_type: str = inputs["repayment_type"]
    paid_months: int = inputs["paid_months"]
    prepay_amount: Decimal = inputs["prepay_amount"]
    prepay_type: str = inputs["prepay_type"]
    strategy: str = inputs["strategy"]

    rate = _monthly_rate(annual_rate)

    if repayment_type == "EPI":
        original_monthly_payment = _epi_payment(principal, rate, term_months)
        remaining_principal_before = _epi_remaining_principal(
            principal, rate, term_months, paid_months, original_monthly_payment
        )
        interest_remaining_before = (
            original_monthly_payment * Decimal(term_months - paid_months) - remaining_principal_before
        )
        original_total_interest = original_monthly_payment * Decimal(term_months) - principal
    else:
        principal_payment = _ep_principal_payment(principal, term_months)
        remaining_principal_before = _ep_remaining_principal(principal, principal_payment, paid_months)
        original_monthly_payment = principal_payment + principal * rate
        original_total_interest = _ep_total_interest(principal, rate, term_months)
        # remaining interest via simulation for consistency
        _, interest_remaining_before, _ = _simulate_ep(
            remaining_principal_before,
            rate,
            principal_payment,
            term_months - paid_months,
            False,
        )

    if remaining_principal_before <= 0:
        remaining_principal_before = Decimal("0")

    effective_prepay_type = prepay_type
    if prepay_type == "partial" and prepay_amount <= 0:
        raise InputError("prepay_amount must be > 0 for partial prepayment")

    if prepay_amount >= remaining_principal_before and remaining_principal_before > 0:
        effective_prepay_type = "full"
        warnings.append("prepay_amount >= remaining principal; treating as full settlement")

    if repayment_type == "EP" and strategy == "reduce_term":
        warnings.append("EP reduce_term assumes keeping the original principal-per-month amount")

    penalty = _calc_penalty(
        remaining_principal_before if effective_prepay_type == "full" else prepay_amount,
        inputs["penalty_rate"],
        inputs["penalty_fixed"],
        paid_months,
        inputs["penalty_free_months"],
    )

    schedule_after: List[Dict[str, Decimal]] = []

    if effective_prepay_type == "full":
        remaining_principal_after = Decimal("0")
        interest_remaining_after = Decimal("0")
        new_term_months_remaining = 0
        new_monthly_payment = Decimal("0")
        settlement_amount = remaining_principal_before
    else:
        remaining_principal_after = remaining_principal_before - prepay_amount
        remaining_principal_after = _clamp_zero(remaining_principal_after)
        settlement_amount = Decimal("0")

        if strategy == "reduce_payment":
            remaining_term = term_months - paid_months
            if repayment_type == "EPI":
                new_monthly_payment = _epi_payment(remaining_principal_after, rate, remaining_term)
                months, interest_remaining_after, schedule_after = _simulate_epi(
                    remaining_principal_after,
                    rate,
                    new_monthly_payment,
                    remaining_term,
                    include_schedule,
                )
                new_term_months_remaining = months
            else:
                new_principal_payment = remaining_principal_after / Decimal(remaining_term)
                months, interest_remaining_after, schedule_after = _simulate_ep(
                    remaining_principal_after,
                    rate,
                    new_principal_payment,
                    remaining_term,
                    include_schedule,
                )
                new_term_months_remaining = months
                if months > 0:
                    first = schedule_after[0] if schedule_after else None
                    if first:
                        new_monthly_payment = first["payment"]
                    else:
                        new_monthly_payment = new_principal_payment + remaining_principal_after * rate
                else:
                    new_monthly_payment = Decimal("0")
        else:  # reduce_term
            if repayment_type == "EPI":
                months, interest_remaining_after, schedule_after = _simulate_epi(
                    remaining_principal_after,
                    rate,
                    original_monthly_payment,
                    None,
                    include_schedule,
                )
                new_term_months_remaining = months
                new_monthly_payment = original_monthly_payment
            else:
                original_principal_payment = _ep_principal_payment(principal, term_months)
                months, interest_remaining_after, schedule_after = _simulate_ep(
                    remaining_principal_after,
                    rate,
                    original_principal_payment,
                    None,
                    include_schedule,
                )
                new_term_months_remaining = months
                if months > 0:
                    first = schedule_after[0] if schedule_after else None
                    if first:
                        new_monthly_payment = first["payment"]
                    else:
                        new_monthly_payment = original_principal_payment + remaining_principal_after * rate
                else:
                    new_monthly_payment = Decimal("0")

    interest_saved_gross = interest_remaining_before - interest_remaining_after
    interest_saved_net = interest_saved_gross - penalty

    result = {
        "inputs": inputs,
        "summary": {
            "original_monthly_payment": original_monthly_payment,
            "original_total_interest": original_total_interest,
            "remaining_principal_before": remaining_principal_before,
            "interest_remaining_before": interest_remaining_before,
            "prepay_penalty": penalty,
            "remaining_principal_after": remaining_principal_after,
            "new_monthly_payment": new_monthly_payment,
            "new_term_months_remaining": new_term_months_remaining,
            "interest_remaining_after": interest_remaining_after,
            "interest_saved_gross": interest_saved_gross,
            "interest_saved_net": interest_saved_net,
            "settlement_amount": settlement_amount,
            "effective_prepay_type": effective_prepay_type,
        },
        "warnings": warnings,
    }

    if include_schedule:
        result["schedule_after"] = schedule_after

    return result


def serialize_result(data: Dict[str, Any]) -> Dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, Decimal):
            return format(_q2(value), "f")
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value

    return convert(data)
