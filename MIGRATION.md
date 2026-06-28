# TINA — Machine Migration Runbook

How to move a running TINA install to a new machine. Written for the laptop → desktop
move (2026-06-28), but reusable for the eventual dedicated-PC move.

**The three things that travel:**
1. **Code** — comes from GitHub (`kljsystems/TINA`). Just clone it.
2. **Secrets + tokens** — gitignored, must be hand-carried (USB). `.env`, `credentials.json`, `data/*token*.json`, state files.
3. **External data** — lives *outside* the repo under `KLJ_BASE`: the Obsidian vault (`Memory/`), `Generated Docs/`, `Sites/`. Hand-carried.

KAOS is **not** copied — it's its own repo (`kljsystems/kaos`, ~6.7 GB locally is mostly `node_modules`/`.next`/`.git`). Re-clone it.

---

## Part A — On the OLD machine (assemble the USB bundle)

Plug in a USB (this move used `D:`). This stages everything that can't come from GitHub:

```powershell
$src = "C:\Users\nrlocal\desktop\klj\tina"   # the TINA repo
$klj = "C:\Users\nrlocal\Desktop\KLJ"        # KLJ_BASE on the old machine
$usb = "D:\tina-migration"

New-Item -ItemType Directory -Force "$usb\secrets\data" | Out-Null

Copy-Item "$src\.env"             "$usb\secrets\" -Force
Copy-Item "$src\credentials.json" "$usb\secrets\" -Force

# Tokens + state — NOT projects.json (it has old machine paths; let it rebuild)
foreach ($f in 'token.json','gmail_personal_token.json','gmail_business_token.json','ms_graph_token.json','voices.json','prefs.json','memory.json','tina_status.json') {
  if (Test-Path "$src\data\$f") { Copy-Item "$src\data\$f" "$usb\secrets\data\" -Force }
}

# External data — the vault is TINA's brain
Copy-Item "$klj\Memory"         "$usb\Memory"         -Recurse -Force
Copy-Item "$klj\Generated Docs" "$usb\Generated Docs" -Recurse -Force
Copy-Item "$klj\Sites"          "$usb\Sites"          -Recurse -Force
```

~70 MB total. Eject the USB safely.

---

## Part B — On the NEW machine (desktop, TINA's dedicated drive = `F:`)

Target layout: `KLJ_BASE = F:\KLJ`.

### 1. Install prerequisites (fresh machine)
- [Git for Windows](https://git-scm.com/download/win)
- **Python 3.10.x** (match the old machine; add to PATH)
- [Node.js LTS](https://nodejs.org/)

### 2. Clone the code
```powershell
New-Item -ItemType Directory -Force F:\KLJ | Out-Null
git clone https://github.com/kljsystems/TINA.git F:\KLJ\TINA
git clone https://github.com/kljsystems/kaos.git F:\KLJ\KAOS\kaos
```

### 3. Copy the USB bundle into place (USB as `E:` here — adjust to its letter)
```powershell
Copy-Item E:\tina-migration\secrets\.env             F:\KLJ\TINA\
Copy-Item E:\tina-migration\secrets\credentials.json F:\KLJ\TINA\
Copy-Item E:\tina-migration\secrets\data\*           F:\KLJ\TINA\data\ -Force
Copy-Item "E:\tina-migration\Memory"         F:\KLJ\Memory           -Recurse
Copy-Item "E:\tina-migration\Generated Docs" "F:\KLJ\Generated Docs" -Recurse
Copy-Item "E:\tina-migration\Sites"          F:\KLJ\Sites            -Recurse
```

### 4. Point the config at the new drive
Edit `F:\KLJ\TINA\.env` and add/change one line:
```
KLJ_BASE=F:\KLJ
```
This redirects the vault, Generated Docs, Sites, and project registry to F:.
(`data/projects.json` was intentionally not copied — TINA rebuilds it from `KLJ_BASE` on first run.)

### 5. Python environment
```powershell
cd F:\KLJ\TINA
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 6. Frontend
```powershell
cd F:\KLJ\TINA\frontend
npm install
```

### 7. Run
```powershell
# Terminal 1 — backend
cd F:\KLJ\TINA; .\.venv\Scripts\Activate.ps1; python backend\main.py
# Terminal 2 — frontend
cd F:\KLJ\TINA\frontend; npm run dev
```

### 8. Verify
- Diagnostics pass on the dashboard.
- Ask "what do you know about TINA" → if `vault_search` returns results, the vault path is correct.
- Calendar/Gmail work. If not, re-auth: `python scripts\auth_calendar.py` and `python scripts\auth_gmail.py` (OAuth refresh tokens usually transfer, but a new machine may need fresh consent).
- Toggle gaming mode.

---

## Warnings

1. **Never run two instances at once.** Both machines would fire schedulers, answer on Slack, and monitor KAOS/Stripe → duplicate emails, alerts, and actions. Verify the new machine, then stop running TINA on the old one.
2. **Wipe the USB secrets after.** `.env` holds all API keys — delete `tina-migration\secrets\` once the new machine is up.

---

## After migration
- Set up **Tailscale** (roadmap step 1) for remote dev from the laptop + multi-device access. See [TINA Roadmap].
