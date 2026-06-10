import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import anthropic
from config import ANTHROPIC_API_KEY, MODEL

_QUESTION_RE = re.compile(r'\[QUESTION:\s*(.+?)\]', re.DOTALL | re.IGNORECASE)


class BaseAgent:
    """
    Specialist agent base class. Each subclass defines:
      - name:         display name broadcast to the dashboard
      - system:       system prompt
      - tool_modules: list of tool modules (each with DEFINITIONS + handle)
    """
    name:         str = "agent"
    system:       str = ""
    tool_modules: list = []

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self._definitions = [d for m in self.tool_modules for d in m.DEFINITIONS]
        self._handlers    = {d["name"]: m.handle for m in self.tool_modules for d in m.DEFINITIONS}

    async def run(self, task: str, on_tool=None, question_handler=None) -> str:
        """
        Run the agent on a task and return the result as a string.
        If question_handler is provided and the agent writes [QUESTION: ...],
        the handler is called and the answer is fed back before continuing.
        """
        import asyncio
        history   = [{"role": "user", "content": task}]
        qa_rounds = 0

        while True:
            kwargs = dict(
                model=MODEL,
                max_tokens=4096,
                system=self.system,
                messages=history,
            )
            if self._definitions:
                kwargs["tools"] = self._definitions

            response = await self.client.messages.create(**kwargs)

            if response.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    if on_tool:
                        await on_tool(block.name, block.input)
                    handler = self._handlers.get(block.name)
                    result  = (
                        await asyncio.to_thread(handler, block.name, block.input)
                        if handler else f"Unknown tool: {block.name}"
                    )
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
                history.append({"role": "user", "content": tool_results})

            else:
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")

                # Check if agent is asking a clarifying question
                if question_handler and qa_rounds < 5:
                    match = _QUESTION_RE.search(reply)
                    if match:
                        question = match.group(1).strip()
                        qa_rounds += 1
                        answer = await question_handler(question)
                        history.append({"role": "assistant", "content": response.content})
                        history.append({
                            "role":    "user",
                            "content": f"Tina's answer: {answer}\n\nContinue with the task.",
                        })
                        continue

                return reply
