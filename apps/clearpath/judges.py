"""The Extraction faithful judge, run locally inside the eval (same prompt and labels as the
pushed scorer in braintrust_functions.py): the judge reads the case's PDF itself."""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from braintrust.logger import ReadonlyAttachment
from openai import OpenAI

from .scorers import EXTRACTION_JUDGE_CHOICES, EXTRACTION_JUDGE_SYSTEM, EXTRACTION_JUDGE_USER

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-2.5-flash")
_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["BRAINTRUST_API_KEY"], base_url=os.environ.get("KEYSTONE_GATEWAY_URL", "https://api.braintrust.dev/v1/proxy"))
    return _client


def extraction_faithful(input: Any = None, output: Any = None, expected: Any = None, metadata: Any = None, **_: Any) -> dict:
    name = "Extraction faithful"
    review = (output or {}).get("review")
    atts = (input or {}).get("attachments") or []
    if not review or not atts:
        return {"name": name, "score": None}
    art = atts[0]["artifact"]
    pdf = (art if hasattr(art, "data") else ReadonlyAttachment(art)).data  # the stored file, not a local copy
    user = EXTRACTION_JUDGE_USER.replace("{{output.review.extraction}}", json.dumps(review.get("extraction")))
    labels = ", ".join(f'"{k}"' for k in EXTRACTION_JUDGE_CHOICES)
    r = _openai().chat.completions.create(model=JUDGE_MODEL, temperature=0, messages=[
        {"role": "system", "content": EXTRACTION_JUDGE_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": user + f"\n\nThink step by step in 1-3 sentences, then end with a final line: LABEL: one of {labels}."},
            {"type": "file", "file": {"filename": "borrower-document.pdf", "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode()}},
        ]}])
    text = r.choices[0].message.content or ""
    m = re.search(r"LABEL:\s*\"?([a-z_]+)", text)
    label = m.group(1) if m and m.group(1) in EXTRACTION_JUDGE_CHOICES else None
    return {"name": name, "score": EXTRACTION_JUDGE_CHOICES.get(label) if label else None,
            "metadata": {"choice": label, "rationale": text.split("LABEL:")[0].strip()}}
