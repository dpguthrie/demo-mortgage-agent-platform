# Keystone Agent Platform

Shared kit and CI for every agent team at Keystone Home Lending. Agents are built with the
[Strands Agents SDK](https://strandsagents.com) and run on AWS; evals, tracing and online scoring
run on Braintrust (data plane in our AWS account).

```
keystone_agents/          the platform kit
  tracing.py              init_tracing(): every Strands agent, model and tool span → Braintrust
  models.py               model per agent: Bedrock in AWS, or an OpenAI-compatible gateway
  prompts.py, variants.py what an experiment can swap: prompt, model, tool descriptions, code
  scorers.py              platform-standard scorers (e.g. numbers_grounded)
  evals/harness.py        agent_eval(): one call runs a team's agent on its dataset as an experiment
  evals/gate.py           the release gate (score ≥ threshold, no case at 0, every case scored)
apps/clearpath/           borrower document assistant (chat → document review pipeline)
apps/escrow_desk/         escrow questions
evals/eval_<agent>.py     each team's eval: their task + their scorers
.github/workflows/
  agent-eval.yml          reusable: eval → gate → PR comment (OIDC to AWS, BYOC URL, self-hosted runner)
  clearpath.yml           Clearpath's PR check (calls agent-eval.yml)
  escrow-desk.yml         Escrow Desk's PR check
  push-scorers.yml        on merge to main: bt functions push (online scoring = the code in git)
```

## Onboard a new agent

1. Instrument once: `from keystone_agents.tracing import init_tracing; init_tracing()`.
2. Create a reference dataset in your Braintrust project.
3. Add `evals/eval_<agent>.py`: `agent_eval("<agent>", task=..., scorers=[...])`.
4. Add `.github/workflows/<agent>.yml` calling `agent-eval.yml` with your dataset and gate score.

## Run locally

```
pip install -r requirements.txt
EVAL_DATASET=golden-clearpath braintrust eval evals/eval_clearpath.py --no-send-logs
```
