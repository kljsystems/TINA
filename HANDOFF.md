# Session Handoff — laptop → desktop migration (2026-06-28)

You (Claude Code) are now running on the **desktop gaming PC**, taking over an
in-progress migration that was being guided from the laptop. This file + `MIGRATION.md`
+ the auto-memory carry the context. Read all of `MIGRATION.md` for the full runbook.

## What TINA is (quick pointer)
Personal multi-agent voice-orchestration system: FastAPI WebSocket backend
(`backend/main.py`) + React/Vite dashboard (`frontend/`), orchestrator "Tina" +
specialist agents (Sam/Charlie/Tristan/Connor/Wade/Jamie/Morgan), autonomous
schedulers, Obsidian-vault memory. See `Readme`. Legacy `core/`, `commands/`,
`dashboard/`, `tina.py` are dead CLI leftovers — do not use.

## Critical desktop-specific facts
- Repo lives at **`F:\TINA`** (the dedicated TINA drive), NOT `F:\KLJ\TINA`.
- Set **`KLJ_BASE=F:\`** in `.env` → vault `F:\Memory`, Generated Docs `F:\Generated Docs`, Sites `F:\Sites`.
- Use **Python 3.10** only (`py -3.10`). The box also has 3.14 — it has NO wheels for
  `faster-whisper`/`openwakeword`, so 3.10 is mandatory.
- venv already built at `F:\TINA\.venv` (Python 3.10.11). PowerShell script execution
  is blocked, so DON'T activate — call `.\.venv\Scripts\python.exe` directly.
- Never run the laptop and desktop TINA instances at the same time (duplicate Slack/
  email/monitor actions).

## Migration status
DONE:
- [x] Code pushed to GitHub and cloned to `F:\TINA`
- [x] Git logged in as kljsystems (KAOS is private — re-clone with that account)
- [x] Python 3.10.11 installed; venv created at `F:\TINA\.venv`
- [x] `pip install -r requirements.txt` (verify it finished cleanly)

REMAINING:
- [ ] KAOS clone (optional; private repo): `git clone https://github.com/kljsystems/kaos.git F:\KLJ\KAOS\kaos` — or wherever; not needed for TINA to run
- [ ] Copy hand-carried data from the USB into place:
      - `.env` + `credentials.json` → `F:\TINA\`
      - token/state files → `F:\TINA\data\`  (NOT `projects.json` — it rebuilds from KLJ_BASE)
      - `Memory\` → `F:\Memory`, `Generated Docs\` → `F:\Generated Docs`, `Sites\` → `F:\Sites`
- [ ] Add `KLJ_BASE=F:\` to `F:\TINA\.env`
- [ ] `npm install` in `F:\TINA\frontend` (npm.cmd is at `C:\Program Files\nodejs`; use a fresh shell or full path)
- [ ] Run: backend `.\.venv\Scripts\python.exe backend\main.py`; frontend `npm run dev`
- [ ] Verify: diagnostics pass; vault_search returns results (proves vault path); calendar/email (re-auth via `scripts\auth_calendar.py` / `auth_gmail.py` if needed); gaming-mode toggle
- [ ] After verified: stop TINA on the laptop; wipe USB secrets

## Auto-memory (do this for full continuity)
The laptop's memory files live at:
`C:\Users\nrlocal\.claude\projects\C--Users-nrlocal-desktop-klj-tina\memory\`
(MEMORY.md, project_tina_state.md, project_tina_roadmap.md, project_kaos.md, feedback_picovoice.md)
Copy them onto this machine's matching project-memory folder (run `claude` once in
`F:\TINA`, then find `%USERPROFILE%\.claude\projects\<key>\memory\` and drop them in).
Carry them via the USB. See `project-tina-roadmap` for the bigger plan (Tailscale next).

## This file is transient — delete it once the desktop is settled.
