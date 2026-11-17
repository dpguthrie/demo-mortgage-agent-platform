"""Platform-standard scorers any agent team can add to its eval with one import."""
from __future__ import annotations

import json
import re
from typing import Any

_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)")


def numbers_grounded(input: Any = None, output: Any = None, expected: Any = None, metadata: Any = None, **_: Any) -> dict:
    """Every dollar amount in the answer must appear in the tool results the agent saw.
    Expects output = {"answer": str, "tool_results": [...]} (the harness convention)."""
    name = "Numbers grounded"
    answer = (output or {}).get("answer") or ""
    seen = json.dumps((output or {}).get("tool_results") or [])
    amounts = [float(m.replace(",", "")) for m in _MONEY.findall(answer)]
    if not amounts:
        return {"name": name, "score": None}
    known = {round(float(x), 2) for x in re.findall(r"-?\d+(?:\.\d+)?", seen)}
    missing = [a for a in amounts if round(a, 2) not in known]
    return {"name": name, "score": 0 if missing else 1,
            "metadata": {"amounts": amounts, "not_in_tool_results": missing}}
