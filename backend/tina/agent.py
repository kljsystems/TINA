import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import anthropic
from config import ANTHROPIC_API_KEY, SYSTEM_PROMPT, MODEL


class TinaAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.history: list[dict] = []

    async def chat(self, message: str) -> str:
        self.history.append({"role": "user", "content": message})
        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=self.history,
        )
        reply = response.content[0].text
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def reset(self):
        self.history = []
