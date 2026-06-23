import asyncio
from config import SUPABASE_URL, SUPABASE_KEY

_client = None


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


async def save_turn(agent: str, session_id: str, role: str, content: str) -> None:
    def _save():
        _get_client().table("conversations").insert({
            "agent":      agent,
            "session_id": session_id,
            "role":       role,
            "content":    content,
        }).execute()
    try:
        await asyncio.to_thread(_save)
    except Exception as e:
        print(f"[memory_db] save error ({agent}): {e}")


async def load_history(agent: str, limit: int = 40) -> list[dict]:
    """Load most recent turns for an agent as a list of {role, content} dicts."""
    def _load():
        result = (
            _get_client()
            .table("conversations")
            .select("role,content")
            .eq("agent", agent)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(result.data))
    try:
        rows = await asyncio.to_thread(_load)
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    except Exception as e:
        print(f"[memory_db] load error ({agent}): {e}")
        return []


async def search_history(query: str, agent: str = "tina", limit: int = 20) -> str:
    """
    Full-text search across all stored conversation turns for an agent.
    Returns a formatted summary of matching turns with dates.
    Used when something may have been discussed beyond the 40-turn window.
    """
    def _search():
        result = (
            _get_client()
            .table("conversations")
            .select("role,content,created_at,session_id")
            .eq("agent", agent)
            .ilike("content", f"%{query}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data
    try:
        rows = await asyncio.to_thread(_search)
        if not rows:
            return f"No matches found for '{query}' in conversation history."

        # Group into sessions to show paired turns together
        sessions: dict = {}
        order: list    = []
        for row in rows:
            sid = row["session_id"]
            if sid not in sessions:
                sessions[sid] = []
                order.append(sid)
            sessions[sid].append(row)

        lines = [f"Found {len(rows)} match(es) for '{query}' across {len(order)} session(s):\n"]
        for sid in order[:8]:  # cap at 8 sessions for readability
            session_rows = sessions[sid]
            date = session_rows[0].get("created_at", "")[:10]
            lines.append(f"— Session {date}")
            for row in session_rows[:3]:  # max 3 turns per session
                role    = "Ky" if row["role"] == "user" else "Tina"
                excerpt = row["content"][:300].replace("\n", " ")
                if len(row["content"]) > 300:
                    excerpt += "..."
                lines.append(f"  {role}: {excerpt}")
            lines.append("")

        return "\n".join(lines).strip()
    except Exception as e:
        print(f"[memory_db] search error ({agent}): {e}")
        return f"Search failed: {e}"


async def load_recent_tasks(agent: str, limit: int = 8) -> str:
    """
    Load recent task/result pairs for a specialist agent as a plain-text summary.
    Injected at the top of each new task so the agent remembers past work.
    """
    def _load():
        result = (
            _get_client()
            .table("conversations")
            .select("session_id,role,content,created_at")
            .eq("agent", agent)
            .order("created_at", desc=True)
            .limit(limit * 2)
            .execute()
        )
        return list(reversed(result.data))
    try:
        rows = await asyncio.to_thread(_load)
        if not rows:
            return ""

        sessions: dict[str, dict] = {}
        order: list[str] = []
        for row in rows:
            sid = row["session_id"]
            if sid not in sessions:
                sessions[sid] = {}
                order.append(sid)
            sessions[sid][row["role"]] = row["content"]

        summaries = []
        for sid in order[-limit:]:
            pair   = sessions[sid]
            task   = pair.get("user", "")
            result = pair.get("assistant", "")
            # Skip incomplete/failed runs — short results mean the agent crashed or
            # gave up, and injecting them as "completed work" poisons the next run.
            if task and result and len(result.strip()) >= 100:
                result_preview = result[:300] + "..." if len(result) > 300 else result
                summaries.append(f"Task: {task[:200]}\nResult: {result_preview}")

        if not summaries:
            return ""
        return "RECENT WORK YOU'VE COMPLETED:\n\n" + "\n\n---\n\n".join(summaries)
    except Exception as e:
        print(f"[memory_db] load_recent_tasks error ({agent}): {e}")
        return ""
