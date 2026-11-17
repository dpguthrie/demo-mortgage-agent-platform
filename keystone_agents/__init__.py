"""Keystone Agent Platform: the shared kit every agent team builds on.

- ``tracing``: one call sends every Strands agent, model and tool span to Braintrust.
- ``models``: the model provider for each agent (Bedrock in AWS, or an OpenAI-compatible gateway).
- ``prompts``: managed prompts loaded by slug and environment, with the local text as fallback.
- ``variants``: the knobs an experiment can turn (prompt slug, model, tool descriptions, code changes).
- ``evals``: the eval harness and the release gate the platform's CI workflow runs on every PR.
"""
