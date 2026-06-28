"""
Provider-routing LLM client for TINA.

`RoutedLLM` is a drop-in for `anthropic.AsyncAnthropic`. It routes each
`messages.create()` call by its `model` string:

  - Anthropic ids ("claude-*")  -> the real AsyncAnthropic, kwargs passed through
    UNCHANGED. Prompt caching, extended thinking, and the exact tool_use protocol
    are preserved byte-for-byte.
  - Local ids ("ollama/<tag>")  -> local Ollama via its OpenAI-compatible endpoint,
    translating Anthropic <-> OpenAI request/response (incl. tool calls).

The Ollama path returns an Anthropic-SHAPED response object (`.stop_reason` and
`.content` blocks exposing `.type` / `.text` / `.name` / `.input` / `.id`) so the
existing agent loops in agent.py and base.py need no changes beyond the model id.

Anthropic-only features that local models can't honor (cache_control on
system/tools, the `thinking` kwarg, image content blocks) are stripped/placeholdered
on the local path.
"""
import json

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, OLLAMA_BASE_URL

_LOCAL_PREFIXES = ("ollama/", "ollama_chat/", "local/")


def is_local_model(model: str) -> bool:
    return bool(model) and model.startswith(_LOCAL_PREFIXES)


def _strip_prefix(model: str) -> str:
    for p in _LOCAL_PREFIXES:
        if model.startswith(p):
            return model[len(p):]
    return model


# ── Anthropic-shaped response objects ───────────────────────────────────────────
class _TextBlock:
    __slots__ = ("type", "text")

    def __init__(self, text):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    # No `text` attribute on purpose — callers use hasattr(b, "text") to find text blocks.
    __slots__ = ("type", "id", "name", "input")

    def __init__(self, id, name, input):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


class _Usage:
    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    __slots__ = ("stop_reason", "content", "usage", "role")

    def __init__(self, stop_reason, content, usage):
        self.stop_reason = stop_reason
        self.content = content
        self.usage = usage
        self.role = "assistant"


# ── Anthropic -> OpenAI translation ─────────────────────────────────────────────
def _block_to_dict(b):
    """Normalize a content block (dict, Anthropic SDK object, or our block) to a dict."""
    if isinstance(b, dict):
        return b
    t = getattr(b, "type", None)
    if t == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    if t == "tool_result":
        return {"type": "tool_result",
                "tool_use_id": getattr(b, "tool_use_id", None),
                "content": getattr(b, "content", "")}
    if hasattr(b, "text"):
        return {"type": "text", "text": b.text}
    return {"type": "text", "text": str(b)}


def _flatten_system(system):
    if not system:
        return None
    if isinstance(system, str):
        return system
    parts = []
    for blk in system:
        parts.append(blk.get("text", "") if isinstance(blk, dict) else getattr(blk, "text", ""))
    return "\n".join(p for p in parts if p)


def _content_to_text(content):
    """Flatten an Anthropic tool_result content into a string for an OpenAI 'tool' message."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for item in content:
            d = item if isinstance(item, dict) else _block_to_dict(item)
            out.append(d.get("text", "") if d.get("type") == "text"
                       else "[non-text content omitted for local model]")
        return "\n".join(out)
    return str(content)


def _tools_to_openai(tools):
    if not tools:
        return None
    out = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def _tool_choice_to_openai(tc):
    if not isinstance(tc, dict):
        return None
    t = tc.get("type")
    if t == "any":
        return "required"
    if t == "auto":
        return "auto"
    if t == "tool" and tc.get("name"):
        return {"type": "function", "function": {"name": tc["name"]}}
    return None


def _messages_to_openai(system, messages):
    out = []
    sys = _flatten_system(system)
    if sys:
        out.append({"role": "system", "content": sys})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        blocks = [_block_to_dict(b) for b in content]

        if role == "assistant":
            text = "\n".join(b["text"] for b in blocks if b.get("type") == "text")
            tool_calls = [
                {"id": b["id"], "type": "function",
                 "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                for b in blocks if b.get("type") == "tool_use"
            ]
            am = {"role": "assistant", "content": text}
            if tool_calls:
                am["tool_calls"] = tool_calls
            out.append(am)
        else:  # user message — may carry tool_result blocks and/or text
            tool_results = [b for b in blocks if b.get("type") == "tool_result"]
            text_parts = [b["text"] for b in blocks if b.get("type") == "text"]
            for tr in tool_results:
                out.append({"role": "tool",
                            "tool_call_id": tr.get("tool_use_id"),
                            "content": _content_to_text(tr.get("content"))})
            if text_parts:
                out.append({"role": "user", "content": "\n".join(text_parts)})
            if not tool_results and not text_parts:
                out.append({"role": "user", "content": "[non-text content omitted for local model]"})
    return out


def _openai_to_response(data):
    choice = data["choices"][0]
    msg = choice.get("message", {})
    finish = choice.get("finish_reason")

    blocks = []
    text = msg.get("content") or ""
    if text:
        blocks.append(_TextBlock(text))
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function", {})
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                args = {}
        blocks.append(_ToolUseBlock(tc.get("id") or f"call_{i}", fn.get("name", ""), args or {}))

    if any(b.type == "tool_use" for b in blocks):
        stop = "tool_use"
    elif finish == "length":
        stop = "max_tokens"
    else:
        stop = "end_turn"

    if not blocks:
        blocks.append(_TextBlock(""))

    usage = data.get("usage", {}) or {}
    return _Response(stop, blocks,
                     _Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)))


# ── Local (Ollama) endpoint ─────────────────────────────────────────────────────
class _OllamaMessages:
    def __init__(self, base_url):
        self._base = base_url.rstrip("/")

    async def create(self, *, model, messages, system=None, tools=None,
                     tool_choice=None, max_tokens=1024, temperature=0, **_ignored):
        payload = {
            "model": _strip_prefix(model),
            "messages": _messages_to_openai(system, messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        oai_tools = _tools_to_openai(tools)
        if oai_tools:
            payload["tools"] = oai_tools
            choice = _tool_choice_to_openai(tool_choice)
            if choice is not None:
                payload["tool_choice"] = choice

        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(f"{self._base}/chat/completions", json=payload)
            r.raise_for_status()
            return _openai_to_response(r.json())


# ── Router ──────────────────────────────────────────────────────────────────────
class _RoutedMessages:
    def __init__(self, anthropic_client, ollama):
        self._anthropic = anthropic_client
        self._ollama = ollama

    async def create(self, **kwargs):
        if is_local_model(kwargs.get("model", "")):
            return await self._ollama.create(**kwargs)
        # Claude path: untouched passthrough (caching, thinking, tool_use all preserved).
        return await self._anthropic.messages.create(**kwargs)


class RoutedLLM:
    """Drop-in for anthropic.AsyncAnthropic that routes messages.create() by model id."""

    def __init__(self, api_key=None, base_url=None):
        self._anthropic = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self._ollama = _OllamaMessages(base_url or OLLAMA_BASE_URL)
        self.messages = _RoutedMessages(self._anthropic, self._ollama)
