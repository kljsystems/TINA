"""TINA Tool — GitHub (repos, issues, PRs, file reading)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import GITHUB_TOKEN
except Exception:
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DEFINITIONS = [
    {
        "name": "github_list_repos",
        "description": "List Kai's GitHub repositories. Use to see what repos exist, find a repo by name, or get an overview of active projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "enum": ["all", "owner", "member"],
                    "description": "Which repos to show. Defaults to 'owner' (repos Kai owns).",
                },
                "sort": {
                    "type": "string",
                    "enum": ["updated", "created", "pushed", "full_name"],
                    "description": "Sort order. Defaults to 'updated'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "github_get_repo",
        "description": "Get details about a specific GitHub repository — description, language, open issues, last push, default branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repo name (e.g. 'kaos') or full name (e.g. 'kljsystems/kaos').",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "github_list_issues",
        "description": "List open issues for a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repo name or full name.",
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue state. Defaults to 'open'.",
                },
                "label": {
                    "type": "string",
                    "description": "Filter by label name.",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "github_create_issue",
        "description": "Create a new issue on a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name or full name."},
                "title": {"type": "string", "description": "Issue title."},
                "body": {"type": "string", "description": "Issue body/description."},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of label names.",
                },
            },
            "required": ["repo", "title"],
        },
    },
    {
        "name": "github_list_prs",
        "description": "List pull requests for a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name or full name."},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "PR state. Defaults to 'open'.",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "github_read_file",
        "description": "Read the contents of a file from a GitHub repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo name or full name."},
                "path": {"type": "string", "description": "File path within the repo, e.g. 'README.md' or 'src/main.py'."},
                "branch": {"type": "string", "description": "Branch name. Defaults to the repo's default branch."},
            },
            "required": ["repo", "path"],
        },
    },
]


def _client():
    from github import Github, GithubException  # noqa: F401
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set in .env")
    return Github(GITHUB_TOKEN)


def _resolve_repo(gh, repo: str):
    """Accept 'kaos' or 'kljsystems/kaos' — try owner prefix if no slash."""
    if "/" in repo:
        return gh.get_repo(repo)
    user = gh.get_user()
    return gh.get_repo(f"{user.login}/{repo}")


def _fmt_repo(r) -> str:
    pushed = r.pushed_at.strftime("%Y-%m-%d") if r.pushed_at else "—"
    return (
        f"{r.full_name} [{r.language or 'unknown'}] "
        f"— {r.description or 'no description'} "
        f"| ⭐{r.stargazers_count} issues:{r.open_issues_count} pushed:{pushed}"
    )


def handle(name: str, inputs: dict) -> str:
    try:
        from github import GithubException
        gh = _client()

        if name == "github_list_repos":
            user   = gh.get_user()
            repos  = user.get_repos(
                type=inputs.get("filter", "owner"),
                sort=inputs.get("sort", "updated"),
            )
            lines  = [_fmt_repo(r) for r in repos][:30]
            return f"{len(lines)} repos:\n\n" + "\n".join(lines)

        elif name == "github_get_repo":
            r = _resolve_repo(gh, inputs["repo"])
            pushed  = r.pushed_at.strftime("%Y-%m-%d %H:%M") if r.pushed_at else "—"
            created = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
            return (
                f"Repo: {r.full_name}\n"
                f"Description: {r.description or '—'}\n"
                f"Language: {r.language or '—'}\n"
                f"Default branch: {r.default_branch}\n"
                f"Open issues/PRs: {r.open_issues_count}\n"
                f"Stars: {r.stargazers_count}\n"
                f"Created: {created}  Last push: {pushed}\n"
                f"URL: {r.html_url}"
            )

        elif name == "github_list_issues":
            r      = _resolve_repo(gh, inputs["repo"])
            state  = inputs.get("state", "open")
            kwargs = {"state": state}
            if inputs.get("label"):
                kwargs["labels"] = [inputs["label"]]
            issues = list(r.get_issues(**kwargs))[:20]
            if not issues:
                return f"No {state} issues in {r.full_name}."
            lines = [
                f"#{i.number} [{i.state}] {i.title} — {i.user.login} "
                f"({i.created_at.strftime('%Y-%m-%d')})"
                for i in issues
            ]
            return f"{len(lines)} issue(s) in {r.full_name}:\n\n" + "\n".join(lines)

        elif name == "github_create_issue":
            r      = _resolve_repo(gh, inputs["repo"])
            kwargs = {"title": inputs["title"]}
            if inputs.get("body"):
                kwargs["body"] = inputs["body"]
            if inputs.get("labels"):
                kwargs["labels"] = inputs["labels"]
            issue = r.create_issue(**kwargs)
            return f"Issue created: #{issue.number} — {issue.title}\n{issue.html_url}"

        elif name == "github_list_prs":
            r     = _resolve_repo(gh, inputs["repo"])
            state = inputs.get("state", "open")
            prs   = list(r.get_pulls(state=state))[:20]
            if not prs:
                return f"No {state} PRs in {r.full_name}."
            lines = [
                f"#{pr.number} [{pr.state}] {pr.title} ← {pr.head.ref} "
                f"— {pr.user.login} ({pr.created_at.strftime('%Y-%m-%d')})"
                for pr in prs
            ]
            return f"{len(lines)} PR(s) in {r.full_name}:\n\n" + "\n".join(lines)

        elif name == "github_read_file":
            r      = _resolve_repo(gh, inputs["repo"])
            kwargs = {"path": inputs["path"]}
            if inputs.get("branch"):
                kwargs["ref"] = inputs["branch"]
            contents = r.get_contents(**kwargs)
            text = contents.decoded_content.decode("utf-8", errors="replace")
            if len(text) > 6000:
                text = text[:6000] + "\n\n[... truncated ...]"
            return f"File: {contents.path} ({contents.size} bytes)\n\n{text}"

        return f"Unknown github tool: {name}"

    except Exception as e:
        return f"GitHub error: {e}"
