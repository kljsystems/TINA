"""
TINA Command — Memory (remember / recall)
"""

TRIGGERS = [
    "remember that", "remember this", "make a note", "don't forget",
    "note that", "keep in mind", "save that",
    "what do you remember", "what have you remembered",
    "show me your memory", "what do you know about me", "what did we talk about",
]

def handle(text: str, ctx: dict) -> str:
    from core import memory
    t = text.lower()

    if memory.is_recall(t):
        mem  = memory.load()
        sums = memory.load_summaries()
        recall = memory.get_recall_response(mem, sums) if hasattr(memory, 'get_recall_response') else memory.build_context()
        chat = ctx.get("chat")
        if chat:
            return chat(f"Here is what I remember:\n{recall}\n\nPresent this conversationally and concisely.")
        return recall

    if memory.is_remember(t):
        saved = memory.handle_remember(text)
        # Refresh memory context in brain
        brain = ctx.get("brain")
        if brain:
            brain.set_memory_context(memory.build_context())
        # Update dashboard
        dash = ctx.get("dash")
        if dash:
            try:
                mem = memory.load()
                sums = memory.load_summaries()
                dash.init_from_memory(mem, sums)
            except: pass
        chat = ctx.get("chat")
        if chat:
            return chat(text)
        return "Got it, I'll remember that."

    return ""