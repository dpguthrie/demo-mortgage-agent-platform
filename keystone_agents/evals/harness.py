"""The platform's eval harness: one call per agent team.

    agent_eval("clearpath", task=..., scorers=[...])

- runs the team's real agent entry point on its reference dataset (EVAL_DATASET) as a
  Braintrust experiment (EXPERIMENT_NAME), with every Strands span traced into the experiment
- scorers are the team's own Python functions, called in-process (the same functions the team
  pushes for online scoring), plus any platform scorers they add
- logs what changed (prompt / model / tools / code) as experiment metadata, so runs group by change
CI runs `braintrust eval <file>` then `python -m keystone_agents.evals.gate` (see .github/workflows).
"""
from __future__ import annotations

import os
from typing import Any, Callable, Sequence

from braintrust import Eval, init_dataset

from ..tracing import instrument_strands
from ..variants import variant_meta


def agent_eval(agent: str, *, task: Callable[[Any], Any], scorers: Sequence[Callable[..., Any]],
               dataset: str | None = None, project: str | None = None, max_concurrency: int = 6,
               metadata: dict | None = None):
    project = project or os.environ["BRAINTRUST_PROJECT"]
    dataset = dataset or os.environ["EVAL_DATASET"]
    instrument_strands()
    meta = {**variant_meta(), "agent": agent, "dataset": dataset, **(metadata or {})}

    def run(input: Any, hooks: Any) -> Any:
        for k, v in meta.items():
            hooks.metadata[k] = v
        return task(input)

    return Eval(
        project,
        data=init_dataset(project=project, name=dataset),
        task=run,
        scores=list(scorers),
        experiment_name=os.environ.get("EXPERIMENT_NAME", f"{agent} · local"),
        metadata=meta,
        max_concurrency=max_concurrency,
    )
