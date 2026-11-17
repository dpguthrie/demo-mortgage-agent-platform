"""What a team changes between releases: prompt, model, tool descriptions, code.

Agents read every knob through these helpers, so the same code serves production (nothing set)
and every experiment (set by the eval run):
  PROMPT_OVERRIDES="assessor=clearpath-assessor-v2"   prompt slug per agent
  MODEL_OVERRIDES="doc_reviewer=gpt-5-mini"           model per agent
  TOOLS_VARIANT="<variant>"                           tool descriptions registered by the eval
  CODE_FIXES="<change-id>"                            code changes under test
"""
from __future__ import annotations

import os
from typing import Any


def _pairs(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (raw or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def prompt_slug(agent: str, slug: str) -> str:
    return _pairs(os.environ.get("PROMPT_OVERRIDES")).get(agent, slug)


def model_for(agent: str, model: str) -> str:
    return _pairs(os.environ.get("MODEL_OVERRIDES")).get(agent, model)


def code_fix(change_id: str) -> bool:
    return change_id in [c.strip() for c in os.environ.get("CODE_FIXES", "").split(",") if c.strip()]


_tool_variants: dict[str, dict[str, str]] = {}


def register_tool_variants(variants: dict[str, dict[str, str]]) -> None:
    _tool_variants.update(variants)


def tool_description(tool: str, default: str) -> str:
    variant = os.environ.get("TOOLS_VARIANT")
    if not variant:
        return default
    if variant not in _tool_variants:
        raise ValueError(f"Unknown TOOLS_VARIANT {variant!r}")
    return _tool_variants[variant].get(tool, default)


def variant_meta() -> dict[str, Any]:
    prompts, models = _pairs(os.environ.get("PROMPT_OVERRIDES")), _pairs(os.environ.get("MODEL_OVERRIDES"))
    tools = os.environ.get("TOOLS_VARIANT") or None
    code = [c for c in os.environ.get("CODE_FIXES", "").split(",") if c]
    change = [n for n, on in (("prompt", prompts), ("tools", tools), ("model", models), ("code", code)) if on]
    return {"change": "+".join(change) or "baseline", "prompt_overrides": prompts, "model_overrides": models,
            "tools_variant": tools, "code_fixes": code}
