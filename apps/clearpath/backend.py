"""Loan-file service and document store behind Clearpath's tools."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=1)
def _loan_files() -> dict[str, dict]:
    return {f["loan_id"]: f for f in json.loads((DATA / "loan_files.json").read_text())}


def loan_file(loan_id: str) -> dict:
    """The full loan file underwriting works from."""
    if loan_id not in _loan_files():
        raise KeyError(f"No loan file {loan_id}")
    return _loan_files()[loan_id]


def loan_summary(loan_id: str) -> dict:
    """What the borrower-facing assistant may see: program and open conditions."""
    f = loan_file(loan_id)
    return {"loan_id": f["loan_id"], "loan_program": f["loan_program"], "open_conditions": f["conditions"]}


def document_bytes(filename: str) -> bytes:
    """Bytes of an uploaded document from the document store."""
    return (DATA / "attachments" / Path(filename).name).read_bytes()


def all_loan_ids() -> list[str]:
    return list(_loan_files())
