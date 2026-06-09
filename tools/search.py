"""TINA Tool — Web Search (Tavily)"""
import os
from config import TAVILY_API_KEY

DEFINITIONS = [{
    "name": "web_search",
    "description": "Search the web for current information, facts, events, people, places, or anything else.",
    "input_schema": {"type":"object","properties":{"query":{"type":"string","description":"The search query."}},"required":["query"]}
}]

def handle(name: str, inputs: dict) -> str:
    if not TAVILY_API_KEY:
        return "Tavily search not configured."
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        r = client.search(inputs.get("query",""), search_depth="basic", max_results=5, include_answer=True)
        lines = []
        if r.get("answer"):
            lines.append(f"Summary: {r['answer']}\n")
        for i, item in enumerate(r.get("results",[]),1):
            lines.append(f"{i}. {item.get('title','')}\n   {item.get('content','')[:250]}")
        return "\n\n".join(lines) if lines else "No results found."
    except Exception as e:
        return f"Search failed: {e}"