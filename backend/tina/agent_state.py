"""
Shared state for tracking background agent progress.
Updated by main.py as tool calls arrive; read by TinaAgent via get_agent_status.
"""
from datetime import datetime

_progress: dict = {}


def start_task(agent_key: str, task: str):
    _progress[agent_key] = {
        "task":       task,
        "started_at": datetime.now(),
        "history":    [],
        "current":    None,
    }


def record_tool(agent_key: str, tool_name: str, input_summary: str):
    if agent_key not in _progress:
        return
    _progress[agent_key]["current"] = tool_name
    _progress[agent_key]["history"].append({
        "tool":    tool_name,
        "time":    datetime.now().strftime("%H:%M:%S"),
        "summary": input_summary,
    })


def end_task(agent_key: str):
    _progress.pop(agent_key, None)


def get_status(agent_key: str) -> str:
    info = _progress.get(agent_key)
    if not info:
        return f"No active task for {agent_key}."

    elapsed  = int((datetime.now() - info["started_at"]).total_seconds())
    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    current = info.get("current") or "thinking"
    history = info.get("history", [])
    recent  = history[-10:]

    lines = [
        f"Task: {info['task'][:200]}",
        f"Running for: {elapsed_str}",
        f"Currently: {current}",
    ]
    if recent:
        lines.append("Recent activity:")
        for entry in recent:
            lines.append(f"  [{entry['time']}] {entry['tool']} — {entry['summary']}")

    return "\n".join(lines)


def summarize_input(tool_name: str, inputs: dict) -> str:
    """Extract a human-readable one-liner from a tool call's inputs."""
    if not inputs:
        return ""
    mapping = {
        "fs_read":          lambda i: i.get("path", ""),
        "fs_write":         lambda i: i.get("path", ""),
        "fs_list":          lambda i: i.get("path", ""),
        "fs_mkdir":         lambda i: i.get("path", ""),
        "vault_search":     lambda i: f"'{i.get('query', '')}'",
        "vault_read":       lambda i: i.get("path", ""),
        "search":           lambda i: f"'{i.get('query', '')}'",
        "wikipedia":        lambda i: f"'{i.get('query', '')}'",
        "github_read_file": lambda i: f"{i.get('repo', '')}/{i.get('path', '')}",
        "github_list_repos":lambda i: "",
        "github_list_issues":lambda i: i.get("repo", ""),
        "get_weather":      lambda i: i.get("location", ""),
        "generate_document":lambda i: i.get("filename", ""),
        "request_agent":    lambda i: f"{i.get('agent', '')} — {i.get('task', '')[:60]}",
    }
    fn = mapping.get(tool_name)
    if fn:
        return fn(inputs)
    first_val = next(iter(inputs.values()), "")
    return str(first_val)[:80]
