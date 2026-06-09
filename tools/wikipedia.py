"""TINA Tool — Wikipedia"""

DEFINITIONS = [{
    "name": "wikipedia_search",
    "description": "Look up factual information on Wikipedia. Use for people, places, history, science, concepts.",
    "input_schema": {"type":"object","properties":{"query":{"type":"string","description":"Topic to look up."}},"required":["query"]}
}]

def handle(name: str, inputs: dict) -> str:
    query = inputs.get("query","")
    try:
        import wikipediaapi
        wiki = wikipediaapi.Wikipedia(language="en", user_agent="TINA-AI-Assistant/2.0")
        page = wiki.page(query)
        if page.exists():
            summary = page.summary[:1200] + ("..." if len(page.summary) > 1200 else "")
            return f"Wikipedia — {page.title}:\n{summary}"
        return f"No Wikipedia article found for '{query}'."
    except Exception as e:
        return f"Wikipedia lookup failed: {e}"