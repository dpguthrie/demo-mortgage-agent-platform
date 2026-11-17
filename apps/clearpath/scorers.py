"""Clearpath's scorers: plain functions, the single source of truth.

The release-gate eval imports them directly; .github/workflows/push-scorers.yml pushes the same
code to Braintrust (bt functions push apps/clearpath/braintrust_functions.py) for online scoring.
Self-contained on purpose (stdlib only), so the pushed bundle has no local imports.
"""
from __future__ import annotations

from typing import Any

PERIODS = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}
DTI_LIMIT = 0.45


def required_decision(review: dict) -> str:
    """Underwriting policy, applied to what the trace logged (extraction, income check, loan)."""
    x, c, loan, chk = review.get("extraction") or {}, review.get("condition") or {}, review.get("loan") or {}, review.get("income_check") or {}
    if x.get("doc_type") != c.get("type"):
        return "REQUEST_NEW_DOC"
    if c.get("type") == "paystub" and (chk.get("doc_age_days") is None or chk["doc_age_days"] > 30):
        return "REQUEST_NEW_DOC"
    if c.get("type") == "w2" and int(x.get("tax_year") or 0) != 2025:
        return "REQUEST_NEW_DOC"
    freq = str(x.get("pay_frequency") or "monthly").lower().replace("-", "")
    income = float(x.get("w2_wages") or 0) / 12 if c.get("type") == "w2" else float(x.get("gross_this_period") or 0) * PERIODS.get(freq, 12) / 12
    obligations = float(loan.get("monthly_debts") or 0) + float(loan.get("proposed_housing_payment") or 0)
    if not income or obligations / income > float(loan.get("max_dti") or DTI_LIMIT):
        return "ESCALATE_TO_UNDERWRITER"
    return "CLEAR"


def condition_decision(input: Any = None, output: Any = None, expected: Any = None, metadata: Any = None, **_: Any) -> dict:
    """1 when the decision is the one policy requires (the expected decision when the case has one)."""
    name = "Condition decision"
    drafted = ((output or {}).get("decision") or {}).get("decision")
    review = (output or {}).get("review")
    if not drafted or not review:
        return {"name": name, "score": None}
    want = expected.get("decision") if isinstance(expected, dict) else (expected if isinstance(expected, str) else None)
    source = "expected" if want else "policy"
    want = want or required_decision(review)
    ok = drafted == want
    return {"name": name, "score": 1 if ok else 0, "metadata": {
        "drafted": drafted, "required": want, "source": source,
        "rationale": f"Drafted {drafted}, as required." if ok else f"Drafted {drafted}; policy requires {want}."}}


def paystub_freshness(input: Any = None, output: Any = None, expected: Any = None, metadata: Any = None, **_: Any) -> dict:
    """Paystub reviews only: 0 when a stub dated more than 30 days before the review cleared the condition."""
    name = "Paystub freshness"
    review = (output or {}).get("review") or {}
    drafted = ((output or {}).get("decision") or {}).get("decision")
    if not drafted or (review.get("condition") or {}).get("type") != "paystub":
        return {"name": name, "score": None}
    age = (review.get("income_check") or {}).get("doc_age_days")
    stale = age is None or age > 30
    ok = not (stale and drafted == "CLEAR")
    return {"name": name, "score": 1 if ok else 0, "metadata": {
        "doc_age_days": age, "drafted": drafted,
        "rationale": (f"Stale stub ({age} days) not cleared." if stale else f"Stub is {age} days old.") if ok
        else f"Cleared a paystub dated {age} days before the review (limit 30)."}}


# The LLM judge that reads the borrower's PDF (pushed as a prompt-type scorer).
EXTRACTION_JUDGE_SYSTEM = ("You are a mortgage document QA analyst. You compare what an automated reviewer extracted from a "
                           "borrower's document with the document itself. Use only the attached document and the extraction; "
                           "do not judge the underwriting decision.")
EXTRACTION_JUDGE_USER = "\n".join([
    "The borrower's uploaded document is attached.", "", "Extraction recorded by the reviewer:", "{{output.review.extraction}}", "",
    "Check each extracted field against the document. For a paystub: gross_this_period must be the gross pay for THIS pay period "
    "(the Current / This period column), not a year-to-date amount; pay_date and pay_frequency must match what is printed. For a W-2: "
    "w2_wages must be box 1 and tax_year the form's year. Ignore formatting differences (capitalization, hyphens, semimonthly vs "
    "Semi-monthly, currency symbols, thousands separators), the summary's wording, and any field the document does not show.", "",
    "Labels:",
    "- faithful: every income figure, date and frequency matches the document",
    "- minor_slip: a non-income field (employer spelling, a rounding) is off, all income figures are right",
    "- wrong_figure: an income figure, the pay date or the pay frequency does not match the document (e.g. a year-to-date amount recorded as this period's gross)",
    "", 'Return exactly one of: "faithful", "minor_slip", "wrong_figure".'])
EXTRACTION_JUDGE_CHOICES = {"faithful": 1, "minor_slip": 0.5, "wrong_figure": 0}


def decision_matches_expected(input: Any = None, output: Any = None, expected: Any = None, metadata: Any = None, **_: Any) -> dict:
    """For a single assessor call (playground, prompt experiments): 1 when its decision equals the expected one."""
    import json as _json
    name = "Decision matches expected"
    out = output
    if isinstance(out, str):
        try:
            out = _json.loads(out[out.find("{"): out.rfind("}") + 1])
        except ValueError:
            out = {}
    got = (out or {}).get("decision")
    got = got.get("decision") if isinstance(got, dict) else got
    want = expected.get("decision") if isinstance(expected, dict) else expected
    if not want:
        return {"name": name, "score": None}
    return {"name": name, "score": 1 if got == want else 0, "metadata": {"drafted": got, "expected": want}}
