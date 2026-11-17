"""Runtime entrypoint (AgentCore / container): one borrower message in, Clearpath's reply out.
Sessions are keyed by session_id; the platform's session store keeps them between messages."""
from __future__ import annotations

from keystone_agents.tracing import init_tracing

from .conversation import ClearpathSession

init_tracing()
_sessions: dict[str, ClearpathSession] = {}


def invoke(payload: dict) -> dict:
    """payload: {session_id?, loan_id, message, attach?}"""
    sid = payload.get("session_id")
    s = _sessions.get(sid) if sid else None
    if s is None:
        s = ClearpathSession(payload["loan_id"], channel=payload.get("channel", "web"))
        _sessions[s.session_id] = s
    reply = s.turn(payload["message"], attach=bool(payload.get("attach")))
    return {"session_id": s.session_id, "reply": reply}
