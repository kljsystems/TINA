"""
Sam Monitor — real-time terminal view of Sam's background activity.

Usage:
    python scripts/sam_monitor.py

Connects to the running TINA backend WebSocket and shows Sam's status,
current tool, files written, and activity log. Press Ctrl+C to exit.
"""
import asyncio
import json
import sys
from collections import deque
from datetime import datetime

try:
    import websockets
    from rich import box
    from rich.columns import Columns
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Missing dependencies. Run: pip install rich websockets")
    sys.exit(1)

WS_URL  = "ws://localhost:8000/ws"
console = Console()

state = {
    "status":       "WAITING",   # WAITING | IDLE | RUNNING | DONE | ERROR
    "task":         "",
    "current_tool": "",
    "files":        deque(maxlen=30),
    "log":          deque(maxlen=20),
}


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _add_log(msg: str):
    state["log"].append(f"[dim]{_ts()}[/dim]  {msg}")


def _render() -> Layout:
    status_style = {
        "WAITING": "dim",
        "IDLE":    "dim",
        "RUNNING": "bold green",
        "DONE":    "green",
        "ERROR":   "bold red",
    }.get(state["status"], "white")

    # ── Top info bar ──────────────────────────────────────────────────────────
    info = Table(box=None, show_header=False, padding=(0, 2), expand=True)
    info.add_column("k", style="dim",   width=12)
    info.add_column("v", no_wrap=False, ratio=1)

    info.add_row("Status",  f"[{status_style}]{state['status']}[/]")
    info.add_row("Tool",    state["current_tool"] or "[dim]—[/dim]")
    if state["task"]:
        info.add_row("Task", state["task"])

    top = Panel(info, title="[bold purple]SAM MONITOR[/bold purple]",
                subtitle=f"[dim]{_ts()}[/dim]", border_style="purple")

    # ── Files written ─────────────────────────────────────────────────────────
    files_lines = "\n".join(f"  [cyan]{f}[/cyan]" for f in state["files"]) \
                  or "  [dim]none yet[/dim]"
    files_panel = Panel(files_lines, title="Files Written",
                        border_style="cyan", padding=(0, 1))

    # ── Activity log ──────────────────────────────────────────────────────────
    log_lines = "\n".join(reversed(list(state["log"]))) or "[dim]waiting for activity…[/dim]"
    log_panel = Panel(log_lines, title="Activity Log",
                      border_style="dim", padding=(0, 1))

    layout = Layout()
    layout.split_column(
        Layout(top,  name="top",    size=7),
        Layout(name="bottom"),
    )
    layout["bottom"].split_row(
        Layout(files_panel, name="files", ratio=1),
        Layout(log_panel,   name="log",   ratio=2),
    )
    return layout


async def _monitor():
    with Live(_render(), refresh_per_second=4, screen=True) as live:
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    state["status"] = "IDLE"
                    _add_log("[green]Connected to backend[/green]")
                    live.update(_render())

                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue

                        t = data.get("type", "")

                        if t == "agent_background_start" and data.get("key") == "coding":
                            state["status"]       = "RUNNING"
                            state["task"]         = data.get("task", "")
                            state["current_tool"] = "STARTING…"
                            _add_log("[bold green]Sam started[/bold green]")

                        elif t == "agent_background_done" and data.get("agent", "").lower() == "coding":
                            state["status"]       = "DONE"
                            state["current_tool"] = ""
                            summary = data.get("summary", "")
                            _add_log(f"[bold green]Sam finished[/bold green]  {summary[:60]}")

                        elif t == "tool" and state["status"] == "RUNNING":
                            name = data.get("name", "")
                            state["current_tool"] = name.upper()
                            _add_log(f"[yellow]{name}[/yellow]")

                        elif t == "code_preview":
                            path = data.get("path", "")
                            fname = path.replace("\\", "/").split("/")[-1]
                            if fname and fname not in state["files"]:
                                state["files"].appendleft(fname)
                            _add_log(f"[cyan]wrote[/cyan]  {fname}")

                        elif t == "state":
                            s = data.get("state", "")
                            if s == "listening" and state["status"] not in ("RUNNING",):
                                state["status"]       = "IDLE"
                                state["current_tool"] = ""

                        live.update(_render())

            except (ConnectionRefusedError, OSError):
                state["status"] = "WAITING"
                _add_log("[dim]Backend offline — retrying in 3s…[/dim]")
                live.update(_render())
                await asyncio.sleep(3)
            except Exception:
                state["status"] = "WAITING"
                _add_log("[dim]Connection lost — retrying in 3s…[/dim]")
                live.update(_render())
                await asyncio.sleep(3)


def main():
    console.print("[bold purple]SAM MONITOR[/bold purple] — starting…\n")
    try:
        asyncio.run(_monitor())
    except KeyboardInterrupt:
        pass
    console.print("\n[dim]Monitor closed.[/dim]")


if __name__ == "__main__":
    main()
