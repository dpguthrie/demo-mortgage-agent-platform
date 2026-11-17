"""Document review pipeline: reviewer (reads the PDF) → income check (code) → condition assessor.

``review_document`` is the one entry point: the borrower chat calls it when a document is
submitted, and the release-gate eval calls the same function on the reference cases.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from strands import Agent, tool

from keystone_agents.models import model_for
from keystone_agents.prompts import system_prompt
from keystone_agents.tracing import child_span
from keystone_agents.variants import tool_description

from . import prompts
from .income import income_check

REVIEWER_MODEL = "gpt-4.1-mini"
ASSESSOR_MODEL = "gpt-4.1-mini"
DECISIONS = ("CLEAR", "REQUEST_NEW_DOC", "ESCALATE_TO_UNDERWRITER")


def _prompt(agent: str, slug: str, overrides: dict[str, str] | None):
    return system_prompt(agent, slug, prompts.PROMPTS[slug], prompts.VERSIONS[slug], (overrides or {}).get(agent))


def extract(pdf: bytes, filename: str, condition: dict, overrides: dict[str, str] | None = None) -> tuple[dict, Any]:
    """The doc reviewer reads the PDF and records its fields."""
    p = _prompt("doc_reviewer", "clearpath-doc-reviewer", overrides)
    captured: dict = {}

    @tool(description=tool_description("record_extraction", "Record the fields read from the borrower's document."))
    def record_extraction(doc_type: str, employee_name: str, employer: str, summary: str,
                          pay_date: str | None = None, pay_frequency: str | None = None,
                          gross_this_period: float | None = None, ytd_gross: float | None = None,
                          tax_year: int | None = None, w2_wages: float | None = None) -> dict:
        """Record the fields read from the borrower's document.

        Args:
            doc_type: paystub, w2 or other
            employee_name: employee name as printed
            employer: employer name as printed
            summary: one line with the identifying details on the document
            pay_date: paystub pay date, YYYY-MM-DD
            pay_frequency: weekly, biweekly, semimonthly or monthly
            gross_this_period: gross pay for this pay period
            ytd_gross: year-to-date gross pay
            tax_year: W-2 tax year
            w2_wages: W-2 box 1 wages
        """
        captured.update({k: v for k, v in dict(doc_type=doc_type, employee_name=employee_name, employer=employer,
                                                summary=summary, pay_date=pay_date, pay_frequency=pay_frequency,
                                                gross_this_period=gross_this_period, ytd_gross=ytd_gross,
                                                tax_year=tax_year, w2_wages=w2_wages).items() if v is not None})
        return {"recorded": True}

    agent = Agent(model=model_for("doc_reviewer", REVIEWER_MODEL, temperature=0), system_prompt=p.text,
                  tools=[record_extraction], name="doc_reviewer", callback_handler=None)
    agent([
        {"text": f"Condition {condition['id']}: {condition['text']}. Review the attached document."},
        {"document": {"format": "pdf", "name": filename.rsplit(".", 1)[0], "source": {"bytes": pdf}}},
    ])
    return captured, p


def assess(extraction: dict, check: dict, condition: dict, as_of: date, overrides: dict[str, str] | None = None) -> tuple[dict, Any]:
    """The condition assessor applies underwriting's rules to the extraction and the income check."""
    p = _prompt("assessor", "clearpath-assessor", overrides)
    captured: dict = {}

    @tool(description=tool_description("record_decision", "Record the condition decision."))
    def record_decision(decision: str, reason: str, borrower_message: str) -> dict:
        """Record the condition decision.

        Args:
            decision: CLEAR, REQUEST_NEW_DOC or ESCALATE_TO_UNDERWRITER
            reason: one sentence naming the rule that decided it
            borrower_message: two sentences for the borrower
        """
        if decision not in DECISIONS:
            return {"error": f"decision must be one of {', '.join(DECISIONS)}"}
        captured.update(decision=decision, reason=reason, borrower_message=borrower_message)
        return {"recorded": True}

    agent = Agent(model=model_for("assessor", ASSESSOR_MODEL, temperature=0), system_prompt=p.text,
                  tools=[record_decision], name="condition_assessor", callback_handler=None)
    agent(f"Today is {as_of.isoformat()}.\nCondition {condition['id']} ({condition['type']}): {condition['text']}\n"
          f"Extraction: {json.dumps(extraction)}\nIncome check: {json.dumps(check)}")
    return captured, p


def review_document(loan: dict, condition: dict, document: dict, pdf: bytes, as_of: date,
                    overrides: dict[str, str] | None = None) -> dict:
    """Review one submitted document against one condition; returns the decision and the evidence."""
    with child_span("document_review", input={"loan_id": loan["loan_id"], "condition": condition,
                                              "document_id": document["document_id"], "as_of": as_of.isoformat()}) as span:
        extraction, p_rev = extract(pdf, document["filename"], condition, overrides)
        with span.start_span(name="income_check", type="function", input={"extraction": extraction}) as s:
            check = income_check(extraction, loan, condition, as_of)
            s.log(output=check)
        decision, p_ass = assess(extraction, check, condition, as_of, overrides)
        result = {
            "decision": decision or None,
            "extraction": extraction,
            "income_check": check,
            "condition": condition,
            "loan": {"loan_id": loan["loan_id"], "monthly_debts": loan["monthly_debts"],
                     "proposed_housing_payment": loan["proposed_housing_payment"], "max_dti": loan["max_dti"]},
            "document_id": document["document_id"],
            "as_of": as_of.isoformat(),
            "prompt_versions": {p_rev.slug: p_rev.version, p_ass.slug: p_ass.version},
        }
        span.log(output={"decision": result["decision"], "income_check": check})
        return result
