"""TINA Tool — News (via Tavily)"""
from config import TAVILY_API_KEY

DEFINITIONS = [{
    "name": "get_news",
    "description": "Get latest news headlines, optionally filtered by topic.",
    "input_schema": {"type":"object","properties":{"topic":{"type":"string","description":"Optional topic e.g. 'sport', 'technology'. Leave empty for general news."}},"required":[]}
}]

def handle(name: str, inputs: dict) -> str:
    topic = inputs.get("topic","").strip()
    query = f"{topic} news today" if topic else "top news headlines Australia today"
    if not TAVILY_API_KEY:
        return "Tavily not configured."
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        r = client.search(query, topic="news", days=2, max_results=5, include_answer=True)
        lines = []
        if r.get("answer"):
            lines.append(f"Summary: {r['answer']}\n")
        for i, item in enumerate(r.get("results",[]),1):
            lines.append(f"{i}. {item.get('title','')}\n   {item.get('content','')[:200]}")
        return "\n\n".join(lines) if lines else "No news found."
    except Exception as e:
        return f"News fetch failed: {e}"