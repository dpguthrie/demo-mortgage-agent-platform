"""Qualifying income and debt-to-income (DTI) for underwriting conditions."""
from __future__ import annotations

from datetime import date


# Pay periods per year for each pay frequency printed on a paystub:
# weekly = every week, biweekly = every two weeks, semimonthly = twice a month, monthly = once a month.
PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 24, "semimonthly": 24, "monthly": 12}


def periods_per_year(frequency: str) -> int:
    """Number of paychecks a year for the stub's pay frequency."""
    periods = PERIODS_PER_YEAR[frequency.lower().replace("-", "")]
    return periods


def monthly_income(extraction: dict) -> float:
    """Gross monthly qualifying income from the document: the period's gross pay annualized, or W-2 box 1."""
    if extraction.get("doc_type") == "w2":
        return round(float(extraction.get("w2_wages") or 0) / 12, 2)
    gross = float(extraction.get("gross_this_period") or 0)
    return round(gross * periods_per_year(extraction.get("pay_frequency") or "monthly") / 12, 2)


def income_check(extraction: dict, loan: dict, condition: dict, as_of: date) -> dict:
    """The facts the condition assessor decides on."""
    income = monthly_income(extraction)
    obligations = float(loan["monthly_debts"]) + float(loan["proposed_housing_payment"])
    age = None
    if extraction.get("pay_date"):
        try:
            age = (as_of - date.fromisoformat(extraction["pay_date"])).days
        except ValueError:
            age = None
    return {
        "doc_type_matches": extraction.get("doc_type") == condition["type"],
        "name_match": (extraction.get("employee_name") or "").strip().lower() == loan["borrower"]["name"].lower(),
        "monthly_income": income,
        "monthly_obligations": obligations,
        "dti": round(obligations / income, 4) if income else None,
        "max_dti": loan["max_dti"],
        "doc_age_days": age,
        "tax_year": extraction.get("tax_year"),
    }
