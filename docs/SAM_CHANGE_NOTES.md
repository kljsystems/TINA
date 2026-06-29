# SAM_CHANGE_NOTES.md — Cross-Device Change Log

**Purpose:** Human-readable context for code changes Sam has made.
This is NOT a safety mechanism — `docs/RECENT_CHANGES.md` and git are the source of truth
for what actually changed. This file gives the *why* and *context* behind changes so the
next session on any device understands what happened beyond the bare git diff.

**Format:** Append-only running log. Sam calls `write_change_note` after completing tasks.
**Gitignored?** No — this file is committed and pushed so it's available on all devices.
**RECENT_CHANGES.md** is the per-machine startup snapshot (gitignored); this file is the
cross-device human-readable log.

---
