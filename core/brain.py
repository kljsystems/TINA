"""
TINA Core — Brain (Claude API + tool routing)
"""

import json
import anthropic
from config import ANTHROPIC_API_KEY, MODEL, SYSTEM_PROMPT

conversation_history: list[dict] = []
memory_context: str = ""
_tool_registry: dict = {}   # name -> handler function
_tool_definitions: list = []

def register_tools(definitions: list, handler):
    """Register a set of tool definitions and their handler function."""
    global _tool_definitions
    _tool_definitions.extend(definitions)
    for defn in definitions:
        _tool_registry[defn["name"]] = handler

def clear_history():
    global conversation_history
    conversation_history = []

def set_memory_context(ctx: str):
    global memory_context
    memory_context = ctx

def chat(user_message: str, on_tool_call=None) -> str:
    """
    Send a message to Claude. Handles tool calls automatically.
    on_tool_call(name) is called whenever a tool fires — for dashboard updates.
    """
    conversation_history.append({"role": "user", "content": user_message})
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = list(conversation_history)

    system = SYSTEM_PROMPT
    if memory_context:
        system = SYSTEM_PROMPT + "\n\n" + memory_context

    for _ in range(5):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                tools=_tool_definitions,
                messages=messages,
            )
        except Exception as e:
            return f"I'm having a technical issue. {e}"

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [Tool] {block.name}({json.dumps(block.input)})")
                    if on_tool_call:
                        try: on_tool_call(block.name)
                        except: pass
                    handler = _tool_registry.get(block.name)
                    result = handler(block.name, block.input) if handler else f"Unknown tool: {block.name}"
                    print(f"  [Tool] ✓ {block.name} — {len(result)} chars")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        reply = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
        conversation_history.append({"role": "assistant", "content": reply})
        return reply

    return "Too many tool calls — please try again."