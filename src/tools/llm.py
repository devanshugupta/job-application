"""LLM provider shim — route each task to Claude (Anthropic) or OpenAI.

Lets the resume-tailoring/agent loop run on Claude while other LLM tasks (e.g. the resume
scorer, the finder) run on OpenAI — or any mix — chosen per task via env vars. The
deterministic tools (edit_tex, ats, final_check, dedupe, render) need NO LLM at all.

Routing (env vars, default anthropic):
    JOB_AGENT_PROVIDER          global default ('anthropic' | 'openai')
    JOB_AGENT_TAILOR_PROVIDER   provider for the apply/tailor agent loop
    JOB_AGENT_SCORE_PROVIDER    provider for score_resume
    JOB_AGENT_FIND_PROVIDER     provider for the finder agent loop

Keys: ANTHROPIC_API_KEY and/or OPENAI_API_KEY. A task only needs the key for the provider
it's routed to. Models per provider via JOB_AGENT_<PROVIDER>_MODEL (sane defaults below).

Two call shapes are supported, both normalized so callers don't branch on provider:
  - run_turn(...)      one tool-use turn → {text, tool_calls[], usage}
  - structured(...)    a JSON-schema-constrained response → (parsed_dict, usage)
"""

from __future__ import annotations

import json
import os

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o",  # update to your preferred OpenAI model
}


def provider_for(task: str) -> str:
    """Resolve the provider for a task ('tailor'|'score'|'find'|...)."""
    return (os.environ.get(f"JOB_AGENT_{task.upper()}_PROVIDER")
            or os.environ.get("JOB_AGENT_PROVIDER")
            or "anthropic").lower()


def model_for(provider: str) -> str:
    return os.environ.get(f"JOB_AGENT_{provider.upper()}_MODEL", DEFAULT_MODELS[provider])


# --- normalized usage ---------------------------------------------------------

def _norm_usage(provider: str, raw) -> dict:
    """Return {input, output, cache_read, cache_write} for either provider."""
    g = (lambda k: getattr(raw, k, 0) or 0)
    if provider == "openai":
        return {"input": g("prompt_tokens"), "output": g("completion_tokens"),
                "cache_read": 0, "cache_write": 0}
    return {"input": g("input_tokens"), "output": g("output_tokens"),
            "cache_read": g("cache_read_input_tokens"),
            "cache_write": g("cache_creation_input_tokens")}


# --- tool-use turn (the agent loop) ------------------------------------------

def run_turn(*, provider: str, model: str, system: str, messages: list,
             tools: list, max_tokens: int = 8000):
    """Run ONE assistant turn with tool access. Returns a normalized dict:
        {text, tool_calls: [{id, name, input}], stop, usage, raw_assistant}
    `messages` uses the Anthropic shape; we translate for OpenAI internally.
    `raw_assistant` is the provider-native assistant message to append to history.
    """
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools, messages=messages,
        )
        calls = [{"id": b.id, "name": b.name, "input": b.input}
                 for b in resp.content if b.type == "tool_use"]
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return {"text": text, "tool_calls": calls, "stop": resp.stop_reason,
                "usage": _norm_usage("anthropic", resp.usage),
                "raw_assistant": {"role": "assistant", "content": resp.content}}

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        oai_tools = [{"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t["input_schema"]}} for t in tools]
        oai_msgs = _to_openai_messages(system, messages)
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens, tools=oai_tools or None, messages=oai_msgs)
        msg = resp.choices[0].message
        calls = [{"id": tc.id, "name": tc.function.name,
                  "input": json.loads(tc.function.arguments or "{}")}
                 for tc in (msg.tool_calls or [])]
        stop = "tool_use" if calls else "end_turn"
        return {"text": msg.content or "", "tool_calls": calls, "stop": stop,
                "usage": _norm_usage("openai", resp.usage),
                "raw_assistant": {"_openai_msg": msg}}

    raise ValueError(f"unknown provider {provider!r}")


def _to_openai_messages(system: str, messages: list) -> list:
    """Translate the Anthropic-shaped message list to OpenAI chat format."""
    out = [{"role": "system", "content": system}]
    for m in messages:
        if "_openai_msg" in m:                       # prior OpenAI assistant turn
            out.append(m["_openai_msg"]); continue
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content}); continue
        # content is a list of blocks (tool_result / text / tool_use)
        if role == "user":
            tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            if tool_results:
                for b in tool_results:
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                "content": b["content"] if isinstance(b["content"], str)
                                else json.dumps(b["content"])})
            else:
                txt = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                out.append({"role": "user", "content": txt})
        else:
            out.append({"role": role, "content": str(content)})
    return out


# --- structured (JSON-schema) call -------------------------------------------

def structured(*, provider: str, model: str, system: str, user: str,
               schema: dict, max_tokens: int = 2000):
    """Get a JSON object matching `schema`. Returns (parsed_dict, usage_dict)."""
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}})
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return json.loads(text), _norm_usage("anthropic", resp.usage)

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            response_format={"type": "json_schema", "json_schema":
                             {"name": "result", "schema": schema, "strict": False}},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return json.loads(resp.choices[0].message.content), _norm_usage("openai", resp.usage)

    raise ValueError(f"unknown provider {provider!r}")
