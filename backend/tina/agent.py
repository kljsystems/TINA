import sys
import os
import asyncio
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import anthropic
from config import ANTHROPIC_API_KEY, SYSTEM_PROMPT, MODEL, ORCHESTRATOR_MODEL
from tools import weather, vault, calendar_tool
from tina.agents.research import ResearchAgent
from tina.agents.coding   import CodingAgent

# ── Specialist agent registry ─────────────────────────────────────────────────
_AGENTS: dict[str, type] = {
    "research": ResearchAgent,
    "coding":   CodingAgent,
}

# ── Direct tools (Tina handles herself without delegating) ────────────────────
_DIRECT_MODULES  = [weather, vault, calendar_tool]
_DIRECT_DEFS     = [d for m in _DIRECT_MODULES for d in m.DEFINITIONS]
_DIRECT_HANDLERS = {d["name"]: m.handle for m in _DIRECT_MODULES for d in m.DEFINITIONS}

# ── Delegation tool ───────────────────────────────────────────────────────────
_DELEGATE_TOOL = {
    "name":        "delegate_to_agent",
    "description": (
        "Delegate a task to a specialist agent and get back a detailed result. "
        "Use 'research' for web searches, news, Wikipedia lookups, or any fact-finding. "
        "Use 'coding' for writing code, debugging, code review, or technical explanations. "
        "Write a clear task brief — include all context the agent needs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent": {
                "type":        "string",
                "enum":        list(_AGENTS.keys()),
                "description": "Which specialist to delegate to.",
            },
            "task": {
                "type":        "string",
                "description": "Full task brief for the specialist, including relevant context.",
            },
        },
        "required": ["agent", "task"],
    },
}

_ALL_TOOLS = _DIRECT_DEFS + [_DELEGATE_TOOL]


class TinaAgent:
    def __init__(self):
        self.client  = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.history: list[dict] = []

    async def chat(self, message: str, on_tool=None, on_agent_done=None) -> str:
        self.history.append({"role": "user", "content": message})

        while True:
            now = datetime.now()
            system = (
                f"Current date: {now.strftime('%A, %d %B %Y')}\n"
                f"Current time: {now.strftime('%I:%M %p')} (Sydney)\n\n"
            ) + SYSTEM_PROMPT

            response = await self.client.messages.create(
                model=ORCHESTRATOR_MODEL,
                max_tokens=1024,
                system=system,
                tools=_ALL_TOOLS,
                messages=self.history,
            )

            if response.stop_reason == "tool_use":
                self.history.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if on_tool:
                        await on_tool(block.name, block.input)
                    result = await self._dispatch(block.name, block.input, on_tool, on_agent_done)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

                self.history.append({"role": "user", "content": tool_results})

            else:
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")
                self.history.append({"role": "assistant", "content": response.content})
                return reply

    async def _dispatch(self, name: str, inputs: dict, on_tool=None, on_agent_done=None) -> str:
        if name == "delegate_to_agent":
            agent_key  = inputs.get("agent", "")
            task       = inputs.get("task", "")
            cls        = _AGENTS.get(agent_key)
            if not cls:
                return f"Unknown agent: {agent_key}"
            specialist = cls()
            result     = await specialist.run(task, on_tool=on_tool)
            if on_agent_done:
                await on_agent_done(agent_key)
            return result

        handler = _DIRECT_HANDLERS.get(name)
        if handler:
            return await asyncio.to_thread(handler, name, inputs)

        return f"Unknown tool: {name}"

    def reset(self):
        self.history = []
