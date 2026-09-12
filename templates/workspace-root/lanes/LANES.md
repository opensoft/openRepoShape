<!-- HAZARD — READ BEFORE WRITING. A path elsewhere on the estate (e.g.
     `~/projects/<estate>/LANES.md`) may be a SYMLINK to this file. Plain
     `sed -i` REPLACES the symlink with a regular file and silently detaches
     the registry from git. Write with ./lanes-edit.sh, or with
     `sed -i --follow-symlinks`, or with a `>` / `>>` redirect. NEVER write
     this file whole from memory: that is the 2026-09-08T23:46Z incident in
     which two lanes' rows and a day of Rule 6 LANDED lines were lost. -->
# LANES.md — IN FORCE

**In force — ratified by Brett Heap 2026-09-03 (in session, lane
openxfactory-1d; agreed in principle 2026-09-02 "i agree. lets do that.";
ratified "take 2").** Seeded 2026-09-02T18:4xZ by lane `openxfactory-1d`
(session `60342fd2`) from the Part-A lane map in `inventory.md`. The protocol
that prescribes this file is in force too:
`~/.agents/protocols/lane-collision-protocol.md`
(`Status: in force`), as amended 2026-09-09 by **Amendment 3 — Rule 9
(registry in git) and Rule 10 (workstation designation)**.

This is the estate's permanent live-lane register, read at
`~/projects/xFactory/LANES.md`. Since 2026-09-09 that path is a **symlink** to
`.lanes/LANES.md`, the worktree of the **orphan `lanes` branch** of
`opensoft/xFactory`, and **every write is a commit** (Rule 9). It remains
operator-local working state: it is never committed to `main` of any repo,
never pinned, never swept. How the branch works, and how to adopt it on a
second workstation: `.lanes/README-lanes.md`.

Format (protocol Rule 4): one row per lane. A lane **appends its row when it
starts** and **updates that row when it stops**. This file is the first thing a
new lane reads and the last thing it writes. Under protocol Rule 6 a row's
`state` reads `LANDING #<n>` from the moment the lane posts LANDING on a
change-dir PR until it posts LANDED (or 30 minutes pass); other lanes hold
merges into that repository's `main` while any row reads `LANDING`.

**Workstation designation (Rule 10).** Two workstations run lanes — **Eagle**
and **Raven** — and the same window name (`opsXfactory-2`) can exist on both.
So column 3 is `workstation / env / user`, spelled exactly
`<Workstation> / <env> / <user>`, e.g. `Eagle / WSL2 / brett`. A row whose
workstation is not yet established reads
`<workstation? — owner fills> / WSL2 / brett` and its **owner fills it in**.
Rule 6 lines carry the workstation on the session id:
`LANDING — lane X, session <uuid>@Eagle, <UTC>, PR #n into <repo> main` — and
likewise LANDED, RESUMED and PAUSED.

**How to write to this file** (from `~/projects/xFactory`; details and the
`sed -i` hazard in `.lanes/README-lanes.md`):

```bash
./lanes-edit.sh verify-row        <lane>
./lanes-edit.sh append-row-status <lane> "<text>"        # appends to the state cell
./lanes-edit.sh replace-in-row    <lane> "<old>" "<new>" # must match exactly once
./lanes-edit.sh append-line       "LANDING — lane … @Eagle, …"
./lanes-edit.sh add-row           "| `<lane>` | … | Eagle / WSL2 / brett | … |"
LANES_LANE=<lane> ./lanes-edit.sh commit "<message>"     # commit a hand edit
```

| lane | session id | workstation / env / user | started (UTC) | objects owned | handoff path | state |
