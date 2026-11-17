"""Escrow Desk release-gate eval: onboarding onto the platform = a dataset + this file."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
import os  # noqa: E402


from apps.escrow_desk.agent import answer  # noqa: E402
from keystone_agents.evals import agent_eval  # noqa: E402
from keystone_agents.scorers import numbers_grounded  # noqa: E402

agent_eval("escrow-desk", task=lambda case: answer(case["loan_id"], case["question"]), scorers=[numbers_grounded])
