"""Escrow Desk: answers a borrower's question about their annual escrow analysis (a Strands agent)."""
from __future__ import annotations

import json
from pathlib import Path

from strands import Agent, tool

from keystone_agents.models import model_for
from keystone_agents.prompts import system_prompt

DATA = Path(__file__).resolve().parents[2] / "data" / "escrow_accounts.json"
PROMPT = """You are Escrow Desk at Keystone Home Lending. Answer the borrower's question about their escrow account in at most 3 sentences.
Call get_escrow_analysis first. Quote dollar amounts exactly as the analysis shows them; never estimate or compute new amounts.
If the analysis doesn't answer the question, say an escrow specialist will follow up."""


def answer(loan_id: str, question: str) -> dict:
    results: list = []

    @tool
    def get_escrow_analysis(loan_id: str) -> dict:
        """The borrower's latest annual escrow analysis.

        Args:
            loan_id: the borrower's loan number
        """
        accounts = json.loads(DATA.read_text())
        r = accounts.get(loan_id) or {"error": "No escrow analysis on file"}
        results.append(r)
        return r

    p = system_prompt("escrow_desk", "escrow-desk", PROMPT, "v1.0")
    agent = Agent(model=model_for("escrow_desk", "gpt-4.1-mini", temperature=0), system_prompt=p.text,
                  tools=[get_escrow_analysis], name="escrow_desk", callback_handler=None)
    reply = str(agent(f"Loan {loan_id}. {question}")).strip()
    return {"answer": reply, "tool_results": results}
