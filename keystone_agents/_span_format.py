"""Chat-format message spans for Braintrust's LLM and Thread views (Strands blocks → chat messages). See SDK-855."""
from __future__ import annotations

import json
from typing import Any

from braintrust.span_customizer import SpanCustomizer

_BLOCK_KEYS = {"text", "toolUse", "toolResult", "document", "image", "reasoningContent", "cachePoint"}


def _is_strands_message(m: Any) -> bool:
    return isinstance(m, dict) and "role" in m and isinstance(m.get("content"), list) and \
        all(isinstance(b, dict) and (set(b) & _BLOCK_KEYS) for b in m["content"])


def _tool_result_content(tr: dict) -> str:
    parts = []
    for c in tr.get("content") or []:
        if "text" in c:
            parts.append(c["text"])
        elif "json" in c:
            parts.append(json.dumps(c["json"]))
    return "\n".join(parts)


def to_chat(m: dict) -> list[dict]:
    """One Strands message → one or more chat messages."""
    role, blocks = m["role"], m["content"]
    out: list[dict] = []
    parts: list[Any] = []
    tool_calls: list[dict] = []
    for b in blocks:
        if "text" in b:
            parts.append({"type": "text", "text": b["text"]})
        elif "document" in b:
            d = b["document"]
            parts.append({"type": "file", "file": {"filename": f"{d.get('name', 'document')}.{d.get('format', 'pdf')}",
                                                   "file_data": (d.get("source") or {}).get("bytes")}})
        elif "image" in b:
            parts.append({"type": "image_url", "image_url": {"url": (b["image"].get("source") or {}).get("bytes")}})
        elif "toolUse" in b:
            tu = b["toolUse"]
            tool_calls.append({"id": tu.get("toolUseId"), "type": "function",
                               "function": {"name": tu.get("name"), "arguments": json.dumps(tu.get("input") or {})}})
        elif "toolResult" in b:
            tr = b["toolResult"]
            out.append({"role": "tool", "tool_call_id": tr.get("toolUseId"), "content": _tool_result_content(tr)})
    if parts or tool_calls:
        if all(p.get("type") == "text" for p in parts):
            content: Any = "\n".join(p["text"] for p in parts) if parts else None
        else:
            content = parts
        msg: dict = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        out.insert(0, msg)
    return out


def convert_record(data: dict) -> dict:
    """Convert one span record's input/output/metadata in place (safe on incremental records)."""
    inp, out, meta = data.get("input"), data.get("output"), data.get("metadata")
    if isinstance(inp, dict) and isinstance(inp.get("messages"), list) and inp["messages"] and all(_is_strands_message(m) for m in inp["messages"]):
        msgs = [c for m in inp["messages"] for c in to_chat(m)]
        if isinstance(meta, dict) and isinstance(meta.get("system_prompt"), str):
            msgs.insert(0, {"role": "system", "content": meta.pop("system_prompt")})
            meta.pop("system_prompt_content", None)
        data["input"] = msgs
    elif isinstance(inp, dict) and {"toolUseId", "name", "input"} <= set(inp):  # a tool call
        data["input"] = inp["input"]
    if isinstance(out, dict):
        if _is_strands_message(out.get("message")):
            res = to_chat(out["message"])
            if _is_strands_message(out.get("tool_result_message")):
                res += to_chat(out["tool_result_message"])
            data["output"] = res
        elif "toolUseId" in out and isinstance(out.get("content"), list):  # a tool result
            text = _tool_result_content(out)
            try:
                data["output"] = json.loads(text)
            except ValueError:
                data["output"] = text
    return data


class StrandsChatFormat(SpanCustomizer):
    def on_span_export(self, data):
        try:
            return convert_record(data)
        except Exception:
            return data
