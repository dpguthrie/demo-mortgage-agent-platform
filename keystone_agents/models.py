"""Model provider for platform agents.

KEYSTONE_MODEL_PROVIDER=bedrock   Strands BedrockModel in our AWS account (AgentCore runtime, CI with an OIDC role)
KEYSTONE_MODEL_PROVIDER=gateway   Strands OpenAIModel through an OpenAI-compatible gateway (default here)
"""
from __future__ import annotations

import os

from . import variants

GATEWAY_URL = os.environ.get("KEYSTONE_GATEWAY_URL", "https://api.braintrust.dev/v1/proxy")
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def model_for(agent: str, model_id: str, temperature: float = 0.2, max_tokens: int = 1200):
    """The Strands model for one agent; experiments can swap the model id per agent."""
    model_id = variants.model_for(agent, model_id)
    provider = os.environ.get("KEYSTONE_MODEL_PROVIDER", "gateway")
    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel
        return BedrockModel(model_id=model_id, temperature=temperature, max_tokens=max_tokens)
    from strands.models.openai import OpenAIModel
    reasoning = model_id.startswith(REASONING_PREFIXES)
    params = {"max_completion_tokens": max_tokens * (4 if reasoning else 1)} if reasoning else {"temperature": temperature, "max_tokens": max_tokens}
    return OpenAIModel(
        client_args={"api_key": os.environ["BRAINTRUST_API_KEY"], "base_url": GATEWAY_URL},
        model_id=model_id,
        params=params,
    )
