"""Clearpath borrower chat: one session per conversation, one Strands concierge agent per session.

Trace shape (Braintrust, via the platform's Strands integration):
    borrower_conversation ▸ Turn N ▸ clearpath_concierge.invoke ▸ model / get_loan_file / submit_document
                                     ▸ document_review ▸ doc_reviewer.invoke (reads the PDF) ▸ income_check
                                                        ▸ condition_assessor.invoke
Root input: the signed-in borrower, the first request, the transcript, the uploaded documents and
the evidence the decision used. Root output: the last reply and the condition decision.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import braintrust
from strands import Agent, tool

from keystone_agents.models import model_for
from keystone_agents.prompts import system_prompt
from keystone_agents.tracing import logger, trace_enabled

from . import backend, prompts
from .review import review_document

CONCIERGE_MODEL = "gpt-4.1-mini"
RELEASE = "clearpath-2026.11"


def descriptor(document: dict, ref: Any | None) -> dict:
    """How an uploaded file is recorded on the trace (the ref is the stored file)."""
    return {
        "artifact_id": document["document_id"], "role": "model_input", "provenance": "borrower_upload",
        "model_input": True, "consumer": "doc_reviewer", "source_product_capture": False,
        "document_id": document["document_id"], "revision": 1, "sha256": document["sha256"],
        "content_type": "application/pdf", "filename": document["filename"], "pages": document.get("pages", 1),
        "artifact": ref,
    }


class ClearpathSession:
    """A signed-in borrower's chat with Clearpath."""

    def __init__(self, loan_id: str, *, channel: str = "web", as_of: date | None = None,
                 overrides: dict[str, str] | None = None, attachment_ref=None):
        self.loan = backend.loan_file(loan_id)
        self.channel = channel
        self.as_of = as_of or date.today()
        self.overrides = overrides or {}
        self.attachment_ref = attachment_ref or (lambda doc, data: braintrust.Attachment(data=data, filename=doc["filename"], content_type="application/pdf"))
        self._refs: dict[str, Any] = {}
        self.session_id = str(uuid.uuid4())
        self.transcript: list[dict] = []
        self.uploads: dict[str, dict] = {}
        self.reviews: list[dict] = []
        self.turns = 0
        self.prompt = system_prompt("concierge", "clearpath-concierge", prompts.CONCIERGE,
                                    prompts.VERSIONS["clearpath-concierge"], self.overrides.get("concierge"))
        self.agent = Agent(model=model_for("concierge", CONCIERGE_MODEL, temperature=0.4),
                           system_prompt=self._system(), tools=self._tools(), name="clearpath_concierge",
                           callback_handler=None)
        self.root = logger().start_span(name="borrower_conversation", type="task") if trace_enabled() else braintrust.NOOP_SPAN
        self.feedback: int | None = None

    def _system(self) -> str:
        b = self.loan["borrower"]
        return (f"{self.prompt.text}\n\nToday is {self.as_of.strftime('%A, %B %-d, %Y')}. "
                f"Signed-in borrower: {b['name']} ({b['email']}), loan {self.loan['loan_id']}.")

    def _tools(self):
        session = self

        @tool
        def get_loan_file(loan_id: str) -> dict:
            """The borrower's loan program and open underwriting conditions.

            Args:
                loan_id: the borrower's loan number
            """
            if loan_id != session.loan["loan_id"]:
                return {"error": "You can only open the signed-in borrower's loan file."}
            return backend.loan_summary(loan_id)

        @tool
        def submit_document(condition_id: str, document_id: str) -> dict:
            """Submit an uploaded document to underwriting review for one open condition.

            Args:
                condition_id: the open condition the document satisfies, e.g. C-PAY
                document_id: the uploaded document's id from the attachment note
            """
            cond = next((c for c in session.loan["conditions"] if c["id"] == condition_id), None)
            if cond is None:
                return {"error": f"Condition {condition_id} is not open on this loan."}
            doc = session.uploads.get(document_id)
            if doc is None:
                return {"error": f"No uploaded document {document_id} in this conversation."}
            result = review_document(session.loan, cond, doc, backend.document_bytes(doc["filename"]),
                                     session.as_of, session.overrides)
            session.reviews.append(result)
            d = result["decision"] or {}
            return {"decision": d.get("decision"), "borrower_message": d.get("borrower_message"),
                    "document_summary": result["extraction"].get("summary")}

        return [get_loan_file, submit_document]

    def turn(self, message: str, attach: bool = False) -> str:
        """One borrower message (optionally with their document attached) → Clearpath's reply."""
        self.turns += 1
        text = message
        if attach:
            doc = self.loan["document"]
            self.uploads[doc["document_id"]] = doc
            text += f"\n\n[Attached: {doc['filename']} · document_id {doc['document_id']} · PDF, {doc.get('pages', 1)} page]"
        self.transcript.append({"role": "borrower", "content": message, **({"attachment": self.loan["document"]["filename"]} if attach else {})})
        with self.root.start_span(name=f"Turn {self.turns}", type="task", input={"message": text}) as span:
            result = self.agent(text)
            reply = str(result).strip()
            span.log(output={"reply": reply})
        self.transcript.append({"role": "clearpath", "content": reply})
        self._log_root(reply)
        return reply

    def _log_root(self, reply: str) -> None:
        b = self.loan["borrower"]
        review = self.reviews[-1] if self.reviews else None
        for d in self.uploads.values():
            if d["document_id"] not in self._refs:
                self._refs[d["document_id"]] = self.attachment_ref(d, backend.document_bytes(d["filename"]))
        docs = [descriptor(d, self._refs[d["document_id"]]) for d in self.uploads.values()]
        self.root.log(
            input={
                "member": {"name": b["name"], "email": b["email"], "loan_id": self.loan["loan_id"]},
                "request": self.transcript[0]["content"],
                "transcript": self.transcript,
                "attachments": docs,
                "evidence": {"loan": review["loan"] if review else None, "condition": review["condition"] if review else None},
            },
            output={
                "reply": reply,
                "decision": review["decision"] if review else None,
                "review": {k: review[k] for k in ("extraction", "income_check", "condition", "loan", "document_id", "as_of")} if review else None,
            },
            metadata={
                "session_id": self.session_id, "channel": self.channel, "loan_program": self.loan["loan_program"],
                "condition_type": self.loan["conditions"][0]["type"], "doc_type": self.loan["document"]["doc_type"],
                "agents_used": ["clearpath_concierge"] + (["doc_reviewer", "condition_assessor"] if review else []),
                "prompt_versions": {self.prompt.slug: self.prompt.version, **(review["prompt_versions"] if review else {})},
                "release": RELEASE, "turns": self.turns, "app": "clearpath",
            },
        )

    def end(self, thumbs: int | None = None) -> str:
        if thumbs is not None:
            self.root.log(scores={"Borrower thumbs": thumbs})
        self.root.end()
        return self.root.id if self.root is not braintrust.NOOP_SPAN else ""
