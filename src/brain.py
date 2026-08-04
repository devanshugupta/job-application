"""Brain  pluggable judgment layer, so the pipeline runs with or without an API key.

Every step that needs *judgment* (writing a tailoring patch, scoring a resume) goes
through a Brain with one method:

    brain.structured(name, system=..., user=..., schema=...) -> dict

Two implementations:

ApiBrain     calls Anthropic/OpenAI via tools/llm.py (per-task provider routing,
             structured outputs). The normal mode.

ManualBrain  needs NO key. It writes a self-contained prompt packet to
             data/brain/<id>.prompt.md and looks for data/brain/<id>.response.json.
             Any LLM can be the operator  paste the packet into a chat UI, or let
             Claude Code (or another agent) read the packet and write the response
             file, then re-run the same command. Pending packets raise BrainPending,
             which the pipeline treats as "come back later", not an error.

This is what makes the system API-optional: discovery, patch application, lint,
rendering, final checks, tracking, and the dashboard are all deterministic Python
the Brain seam is the ONLY place intelligence enters the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re

from . import config
from .tools import llm


class BrainPending(Exception):
    """ManualBrain: the prompt packet is written but no response exists yet."""

    def __init__(self, packet_path, response_path):
        self.packet_path = packet_path
        self.response_path = response_path
        super().__init__(
            f"Awaiting response: answer {packet_path.name} by writing "
            f"{response_path.name} in the same folder, then re-run the command."
        )


class ApiBrain:
    """Routes structured calls through the multi-provider LLM shim."""

    def structured(self, name: str, *, system: str, user: str, schema: dict,
                   max_tokens: int = 3000, cache_blocks: list[str] | None = None) -> dict:
        provider = llm.provider_for(name)
        model = llm.model_for(provider)
        parsed, _usage = llm.structured(provider=provider, model=model, system=system,
                                        user=user, schema=schema, max_tokens=max_tokens,
                                        cache_blocks=cache_blocks)
        return parsed


class ManualBrain:
    """File-based prompt/response exchange  zero API usage.

    Packet id is a hash of the call's content, so re-running the same pipeline
    finds the previously written response instead of asking again.
    """

    def __init__(self, base_dir=None):
        self.base = base_dir or config.BRAIN_DIR
        self.base.mkdir(parents=True, exist_ok=True)

    def _id(self, name: str, system: str, user: str) -> str:
        h = hashlib.sha256(f"{name}|{system}|{user}".encode()).hexdigest()[:10]
        return f"{name}-{h}"

    def structured(self, name: str, *, system: str, user: str, schema: dict,
                   max_tokens: int = 3000, cache_blocks: list[str] | None = None) -> dict:
        # Manual mode has no caching concept  fold cache_blocks back into the packet text.
        if cache_blocks:
            user = "\n\n".join([*cache_blocks, user])
        pid = self._id(name, system, user)
        prompt_path = self.base / f"{pid}.prompt.md"
        response_path = self.base / f"{pid}.response.json"

        if response_path.exists():
            parsed = self._parse_response(response_path)
            missing = [k for k in schema.get("required", []) if k not in parsed]
            if missing:
                raise ValueError(
                    f"{response_path.name} is missing required keys {missing}; "
                    f"fix the response file and re-run.")
            return parsed

        prompt_path.write_text(
            f"# Brain packet: {name}\n\n"
            f"Respond by writing ONLY a JSON object matching the schema below to\n"
            f"`{response_path}`. No prose, no markdown fences.\n\n"
            f"## System\n\n{system}\n\n"
            f"## Input\n\n{user}\n\n"
            f"## Required JSON schema\n\n```json\n{json.dumps(schema, indent=2)}\n```\n"
        )
        raise BrainPending(prompt_path, response_path)

    @staticmethod
    def _parse_response(path) -> dict:
        text = path.read_text().strip()
        # tolerate an operator pasting a ```json fenced block
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
        if m:
            text = m.group(1)
        return json.loads(text)


def get_brain(mode: str = "api"):
    if mode == "manual":
        return ManualBrain()
    return ApiBrain()


def pending_packets() -> list[str]:
    """List manual-brain packets that still lack a response (for CLI status)."""
    if not config.BRAIN_DIR.exists():
        return []
    out = []
    for p in sorted(config.BRAIN_DIR.glob("*.prompt.md")):
        if not p.with_name(p.name.replace(".prompt.md", ".response.json")).exists():
            out.append(p.name)
    return out
