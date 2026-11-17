"""Registers Clearpath's scorers with Braintrust. Pushed from CI on every merge to main:
    bt functions push apps/clearpath/braintrust_functions.py --if-exists replace --language python
Online scoring rules point at these slugs, so production traces are scored by the code in git.
"""
import os
from typing import Any

import braintrust
from pydantic import BaseModel

from scorers import (EXTRACTION_JUDGE_CHOICES, EXTRACTION_JUDGE_SYSTEM, EXTRACTION_JUDGE_USER,
                     condition_decision, decision_matches_expected, paystub_freshness)

project = braintrust.projects.create(name=os.environ.get("BRAINTRUST_PROJECT", "clearpath"))


class ScorerArgs(BaseModel):
    input: Any = None
    output: Any = None
    expected: Any = None
    metadata: Any = None


project.scorers.create(
    name="Condition decision", slug="clearpath-condition-decision",
    description="1 when the assessor's decision is the one underwriting policy requires.",
    handler=condition_decision, parameters=ScorerArgs,
)
project.scorers.create(
    name="Paystub freshness", slug="clearpath-paystub-freshness",
    description="Paystub reviews only: 0 when a paystub dated more than 30 days before the review cleared the condition.",
    handler=paystub_freshness, parameters=ScorerArgs,
)
project.scorers.create(
    name="Decision matches expected", slug="clearpath-decision-matches-expected",
    description="One assessor call (playground): 1 when its decision equals the expected decision.",
    handler=decision_matches_expected, parameters=ScorerArgs,
)
project.scorers.create(
    name="Extraction faithful", slug="clearpath-extraction-faithful",
    description="Reads the uploaded PDF: 1 when every extracted field matches, 0.5 minor slip, 0 when an income figure, date or frequency is wrong.",
    messages=[
        {"role": "system", "content": EXTRACTION_JUDGE_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": EXTRACTION_JUDGE_USER},
            {"type": "file", "file": {"file_data": "{{input.attachments.0.artifact}}", "filename": "borrower-document.pdf"}},
        ]},
    ],
    # Gemini reads the PDF natively through the gateway (OpenAI Chat Completions rejects a PDF file part from a ref).
    model=os.environ.get("JUDGE_MODEL", "gemini-2.5-flash"),
    use_cot=True,
    choice_scores=EXTRACTION_JUDGE_CHOICES,
)
