"""Prompts live in each app's code and ship through a pull request, like any other change, so
the release gate runs on every prompt edit.

Experiments swap a prompt for a registered variant by name (PROMPT_OVERRIDES, or an explicit
per-call override); the variant's text and version label are logged with every run.
"""
from __future__ import annotations

from dataclasses import dataclass

from .variants import prompt_slug

_variants: dict[str, tuple[str, str]] = {}


@dataclass
class LoadedPrompt:
    slug: str
    text: str
    version: str


def register_prompt_variants(variants: dict[str, tuple[str, str]]) -> None:
    """slug → (version label, text), registered by evals and experiments."""
    _variants.update(variants)


def system_prompt(agent: str, slug: str, text: str, version: str, override: str | None = None) -> LoadedPrompt:
    """The prompt an agent runs with: its own text, unless an experiment swapped in a variant."""
    chosen = override or prompt_slug(agent, slug)
    if chosen == slug:
        return LoadedPrompt(slug, text, version)
    if chosen not in _variants:
        raise KeyError(f"Prompt variant {chosen!r} is not registered")
    v, t = _variants[chosen]
    return LoadedPrompt(chosen.split("@")[0], t, v)  # "<slug>@<version>" = an earlier release of the same prompt
