"""Clearpath release-gate eval: the real review pipeline (the same function the chat calls when a
borrower submits a document) on the reference cases, scored by Clearpath's own scorer functions.
CI sets BRAINTRUST_PROJECT, EVAL_DATASET and EXPERIMENT_NAME; run with `braintrust eval evals/eval_clearpath.py`.
"""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from braintrust.logger import ReadonlyAttachment  # noqa: E402

from apps.clearpath import backend  # noqa: E402
from apps.clearpath.judges import extraction_faithful  # noqa: E402
from apps.clearpath.review import review_document  # noqa: E402
from apps.clearpath.scorers import condition_decision, paystub_freshness  # noqa: E402
from keystone_agents.evals import agent_eval  # noqa: E402




def task(case: dict) -> dict:
    """One reference case: the borrower's stored document reviewed against the loan's condition."""
    loan = backend.loan_file(case["loan_id"])
    cond = next(c for c in loan["conditions"] if c["id"] == case["condition_id"])
    doc = case["attachments"][0]
    art = doc["artifact"]
    pdf = (art if hasattr(art, "data") else ReadonlyAttachment(art)).data  # the stored file, not a local copy
    r = review_document(loan, cond, {**loan["document"], "document_id": doc["document_id"], "filename": doc["filename"]},
                        pdf, date.fromisoformat(case["as_of"]))
    return {"decision": r["decision"], "review": {k: r[k] for k in ("extraction", "income_check", "condition", "loan", "document_id", "as_of")}}


agent_eval("clearpath", task=task, scorers=[condition_decision, paystub_freshness, extraction_faithful])
