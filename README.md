# Keystone Agent Platform

The shared kit and CI that every agent team at Keystone Home Lending builds on. Teams build agents
with the [Strands Agents SDK](https://strandsagents.com) and run them on AWS; the platform gives
each team tracing, evals and a pre-deploy release gate on [Braintrust](https://www.braintrust.dev)
(data plane in our AWS account), without each team wiring it up themselves.

Two teams use it today: [Clearpath](apps/clearpath) (borrower document review) and
[Escrow Desk](apps/escrow_desk) (escrow questions).

---

## What the platform gives a team, most important first

### 1. Tracing in one line

```python
from keystone_agents.tracing import init_tracing
init_tracing()   # every Strands agent, model call and tool call is now traced
```

- Turns on Braintrust's native Strands integration (`setup_strands()`): each `Agent` call, model
  call, event-loop cycle and tool call becomes a span, nested under the request. Nothing else in
  the agent changes. Braintrust renders Strands’ native messages and tool calls directly.
  → [`init_tracing()`](keystone_agents/tracing.py#L29-L38)
- Where the data goes is set by environment only: one Braintrust project per team
  (`BRAINTRUST_PROJECT`), our BYOC data plane (`BRAINTRUST_API_URL`), the key from Secrets Manager.
  → [module docs](keystone_agents/tracing.py#L1-L14)
- `child_span()` nests work a tool starts (e.g. a sub-agent) under that tool call.
  → [`child_span()`](keystone_agents/tracing.py#L54-L58) · used in [Clearpath's review pipeline](apps/clearpath/review.py)
- Example: [Clearpath's runtime entrypoint](apps/clearpath/handler.py#L9)

### 2. The eval harness: one call per team

```python
from keystone_agents.evals import agent_eval
agent_eval("clearpath", task=run_one_case, scorers=[condition_decision, paystub_freshness])
```

- A team supplies two things: **a task** (run my real agent on one reference case) and **scorers**
  (plain Python functions). The harness does the rest, the same way for every team: loads the
  team's dataset, names the experiment, traces the agent's spans into it, and tags the run with what
  changed. → [`agent_eval()`](keystone_agents/evals/harness.py#L23-L44)
- The dataset and experiment name come from the environment (`EVAL_DATASET`, `EXPERIMENT_NAME`), so
  CI decides them and the same file runs locally.
- Examples: [Clearpath's eval](evals/eval_clearpath.py#L26-L38) (task + three scorers) ·
  [Escrow Desk's eval](evals/eval_escrow_desk.py) (16 lines, a platform scorer)

### 3. The release gate

```bash
python -m keystone_agents.evals.gate --experiment "clearpath · ci · PR #12" --score "Condition decision" --min 0.95 --no-zero
```

- One pass/fail rule for every team: the gate score is at or above the threshold, **no case scores
  0**, and **every case was scored** (an errored case can't slip through as "not counted").
  → [the rule](keystone_agents/evals/gate.py#L58-L59)
- Writes the verdict onto the experiment (`metadata.release_gate`), so Braintrust, and anyone asking
  Loop, see the gate's answer. → [write-back](keystone_agents/evals/gate.py#L63-L71)

### 4. Pre-deploy checks in GitHub Actions (with AWS)

One reusable workflow the platform owns; each team adds a ten-line caller.
→ [`agent-eval.yml`](.github/workflows/agent-eval.yml) · callers: [`clearpath.yml`](.github/workflows/clearpath.yml), [`escrow-desk.yml`](.github/workflows/escrow-desk.yml)

On every pull request that touches the team's agent, it runs the eval → the gate → posts the verdict
on the PR. How it fits our AWS setup:

| Concern | How | Where |
|---|---|---|
| AWS access without stored keys | OIDC role (`vars.AWS_EVAL_ROLE_ARN`), Bedrock models in our account | [lines 46-51](.github/workflows/agent-eval.yml#L46-L51) |
| Braintrust API key | org secret, or AWS Secrets Manager (`vars.BRAINTRUST_SECRET_ID`) | [lines 52-57](.github/workflows/agent-eval.yml#L52-L57) |
| Data stays in our account | `vars.BRAINTRUST_API_URL` → our BYOC data plane | [line 32](.github/workflows/agent-eval.yml#L32) |
| Runs on our compute | `vars.EVAL_RUNNER` → a self-hosted runner in our VPC | [line 28](.github/workflows/agent-eval.yml#L28) |
| Permissions | the caller grants `id-token` (OIDC) and `pull-requests` (the comment); the org default is read-only | [`clearpath.yml`](.github/workflows/clearpath.yml#L7-L12) |

### 5. Scorers live in git

- Each team's scorers are plain functions in its repo: the gate imports them directly
  ([Clearpath's scorers](apps/clearpath/scorers.py)), and a registration file publishes the same
  code to Braintrust ([`braintrust_functions.py`](apps/clearpath/braintrust_functions.py)).
- On merge to `main`, [`push-scorers.yml`](.github/workflows/push-scorers.yml#L36-L40) runs
  `bt functions push`, so online scoring on production traces runs the code the PR was gated on.
- One scorer reads the borrower's PDF itself (an LLM judge given the actual document):
  [extraction judge](apps/clearpath/judges.py).

### 6. Platform-standard scorers

Checks any team can add with one import. → [`keystone_agents/scorers.py`](keystone_agents/scorers.py)
- [`numbers_grounded`](keystone_agents/scorers.py#L11): every dollar amount in an answer must appear
  in the tool results the agent saw (used by Escrow Desk).

### 7. Model provider switch

`model_for(agent, model_id)` returns the Strands model for an agent: Bedrock in AWS
(`KEYSTONE_MODEL_PROVIDER=bedrock`, AgentCore and CI with the OIDC role) or an OpenAI-compatible
gateway elsewhere. → [`models.py`](keystone_agents/models.py#L16)

### 8. Experiment knobs

Agents read their prompt, model and tool descriptions through small helpers, so an eval can swap
one (`PROMPT_OVERRIDES`, `MODEL_OVERRIDES`, `TOOLS_VARIANT`) and the experiment records what changed.
→ [`variants.py`](keystone_agents/variants.py) · [`prompts.py`](keystone_agents/prompts.py#L28)

---

## Onboard a new agent

1. Call `init_tracing()` at startup ([example](apps/clearpath/handler.py#L9)).
2. Create a reference dataset in your team's Braintrust project.
3. Add `evals/eval_<agent>.py` with `agent_eval("<agent>", task=..., scorers=[...])`
   ([16-line example](evals/eval_escrow_desk.py)).
4. Add `.github/workflows/<agent>.yml` calling `agent-eval.yml` with your dataset and gate score
   ([example](.github/workflows/escrow-desk.yml)).

## Layout

```
keystone_agents/          the platform kit (tracing, models, prompts, variants, scorers, evals/)
apps/clearpath/           borrower document assistant: chat → document review pipeline
apps/escrow_desk/         escrow questions
evals/eval_<agent>.py     each team's eval: its task + its scorers
.github/workflows/        agent-eval.yml (reusable), one caller per team, push-scorers.yml
data/                     loan files, escrow accounts, sample borrower documents (fictional)
```

## Run locally

```bash
pip install -r requirements.txt
EVAL_DATASET=golden-clearpath braintrust eval evals/eval_clearpath.py --no-send-logs
```

Keystone Home Lending is a fictional company; the data is synthetic.
