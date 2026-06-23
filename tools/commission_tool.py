"""TINA Tool — Commission Agent (run a specialist synchronously, for Project Manager use)."""
import asyncio
import importlib
import sys
import threading

DEFINITIONS = [
    {
        "name": "commission_agent",
        "description": (
            "Run a specialist agent to completion and return their full result. "
            "Use this to coordinate work: 'research' (Charlie — web search, fact-finding, competitive research), "
            "'coding' (Sam — writing code, debugging, technical implementation), "
            "'email' (Tristan — composing, sending, triaging emails), "
            "'data' (Connor — CSV/Excel analysis, charts, financial reports), "
            "'marketing' (Wade — social posts, content strategy, trend research), "
            "'website' (Jamie — web design, HTML/CSS/JS, React, Next.js). "
            "Write task briefs that are specific: include file paths, expected output format, constraints. "
            "The agent runs to completion before you receive the result. "
            "After receiving the result, critically review it before proceeding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type":        "string",
                    "enum":        ["research", "coding", "email", "data", "marketing", "website"],
                    "description": "Which specialist to run.",
                },
                "task": {
                    "type":        "string",
                    "description": "Full task brief including all context, file paths, and expected output.",
                },
            },
            "required": ["agent", "task"],
        },
    }
]

_AGENT_MAP = {
    "research":  ("tina.agents.research",  "ResearchAgent"),
    "coding":    ("tina.agents.coding",    "CodingAgent"),
    "email":     ("tina.agents.email",     "EmailAgent"),
    "data":      ("tina.agents.data",      "DataAgent"),
    "marketing": ("tina.agents.marketing", "MarketingAgent"),
    "website":   ("tina.agents.website",   "WebsiteAgent"),
}


def _run_agent_sync(agent_key: str, task: str) -> str:
    """Run an agent in a fresh event loop (safe to call from asyncio.to_thread)."""
    entry = _AGENT_MAP.get(agent_key)
    if not entry:
        return f"Unknown agent: {agent_key}"

    module_path, cls_name = entry

    result_holder: list[str] = []
    error_holder:  list[str] = []

    def _thread_run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, cls_name)
            specialist = cls()
            result = loop.run_until_complete(specialist.run(task))
            result_holder.append(result)
        except Exception as exc:
            error_holder.append(str(exc))
        finally:
            loop.close()

    t = threading.Thread(target=_thread_run, daemon=True)
    t.start()
    t.join(timeout=600)  # 10-minute ceiling per sub-agent

    if t.is_alive():
        return f"Agent '{agent_key}' timed out after 10 minutes."
    if error_holder:
        return f"Agent '{agent_key}' failed: {error_holder[0]}"
    if result_holder:
        return result_holder[0]
    return f"Agent '{agent_key}' returned no result."


def handle(name: str, inputs: dict) -> str:
    if name == "commission_agent":
        return _run_agent_sync(
            inputs.get("agent", ""),
            inputs.get("task", ""),
        )
    return f"Unknown tool: {name}"
