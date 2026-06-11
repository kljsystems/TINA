"""
project_tool.py — Create and register new projects.
Creates the folder on disk, registers it for nightly indexing, sets up vault notes.
"""
import os
import sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import VAULT_DIR, KLJ_BASE

DEFINITIONS = [
    {
        "name": "create_project",
        "description": (
            "Create a new project: makes the project folder on disk, registers it so Sam "
            "will index and maintain it nightly, and sets up vault notes. "
            "Use when Ky asks to start a new project or add an existing folder to the system."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type":        "string",
                    "description": "Project name, lowercase, no spaces (e.g. 'myapp')",
                },
                "path": {
                    "type":        "string",
                    "description": (
                        f"Full path for the project folder. "
                        f"Defaults to {KLJ_BASE}\\<NAME> if omitted."
                    ),
                },
                "description": {
                    "type":        "string",
                    "description": "What this project is for.",
                },
            },
            "required": ["name"],
        },
    }
]


def handle(name: str, inputs: dict) -> str:
    if name == "create_project":
        return _create_project(
            inputs.get("name", "").lower().strip(),
            inputs.get("path", ""),
            inputs.get("description", ""),
        )
    return f"Unknown tool: {name}"


def _create_project(name: str, path: str, description: str) -> str:
    if not name:
        return "Project name is required."

    if not path:
        path = os.path.join(KLJ_BASE, name.upper())

    # Create project folder
    os.makedirs(path, exist_ok=True)

    # Register in persistent registry
    from config import register_project
    register_project(name, path)

    # Create vault project folder
    vault_dir = os.path.join(VAULT_DIR, "01-Projects", name)
    os.makedirs(vault_dir, exist_ok=True)

    # Create CLAUDE.md if not already present
    claude_md = os.path.join(vault_dir, "CLAUDE.md")
    if not os.path.exists(claude_md):
        with open(claude_md, "w", encoding="utf-8") as f:
            f.write(f"""---
tags: [{name}, project, claude-context]
date: {date.today().isoformat()}
---

# {name.capitalize()} — Project CLAUDE.md

## What This Project Is

{description or f'{name.capitalize()} project.'}

## Code Location

```
{path}
```

## Status

New project — Sam will generate the codebase index on the next nightly run, or ask him to index it now.
""")

    return (
        f"Project '{name}' created at {path}. "
        f"Registered for nightly indexing. "
        f"Vault notes at 01-Projects/{name}/. "
        f"Sam will index the codebase tonight — or ask him to do it now if you need it sooner."
    )
