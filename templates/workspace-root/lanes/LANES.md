<!-- HAZARD — READ BEFORE WRITING. A path elsewhere on the estate (e.g.
     `~/projects/<estate>/LANES.md`) may be a SYMLINK to this file. Plain
     `sed -i` REPLACES the symlink with a regular file and silently detaches
     the registry from git. Write with `lanes-edit.sh`, or with
     `sed -i --follow-symlinks`, or with a `>` / `>>` redirect. NEVER write
     this file whole from memory: that is the 2026-09-08T23:46Z incident in
     which two lanes' rows and a day of Rule 6 LANDED lines were lost. -->
# LANES.md — IN FORCE

This is the permanent live-lane register (lane-collision-protocol Rule 9):
tracked directly on `main` of this repository, and **every write is a
commit**. It is never pinned and never swept. The protocol that prescribes
it: `~/.agents/protocols/lane-collision-protocol.md` (`Status: in force`),
Rule 9 (registry in git) and Rule 10 (workstation designation), amended by
Amendment 3. An estate that predates this repository keeps its own
`~/projects/<estate>/LANES.md` resolving to this file through a symlink
`link-estates` places (this repository's `README.md`, "The link targets").
The row format and the `sed -i` hazard, in full: README-lanes in
`opensoft/openRepoTools`.

Format (protocol Rule 4): one row per lane. A lane **appends its row when it
starts** and **updates that row when it stops**. This file is the first thing a
new lane reads and the last thing it writes. Under protocol Rule 6 a row's
`state` reads `LANDING #<n>` from the moment the lane posts LANDING on a
change-dir PR until it posts LANDED (or 30 minutes pass); other lanes hold
merges into that repository's `main` while any row reads `LANDING`.

**Workstation designation (Rule 10).** More than one workstation may run
lanes, and the same window name can exist on more than one. So column 3 is
`workstation / env / user`, spelled exactly `<Workstation> / <env> / <user>`.
A row whose workstation is not yet established reads
`<workstation? — owner fills> / <env> / <user>` and its **owner fills it
in**. Rule 6 lines carry the workstation on the session id:
`LANDING — lane X, session <uuid>@<Workstation>, <UTC>, PR #n into <repo>
main` — and likewise LANDED, RESUMED and PAUSED.

**How to write to this file**, through the installed `lanes-edit.sh` (found
through `~/.agents/workspace.yaml`; the `sed -i` hazard in full, in
README-lanes in `opensoft/openRepoTools`):

```bash
lanes-edit.sh verify-row        <lane>
lanes-edit.sh append-row-status <lane> "<text>"        # appends to the state cell
lanes-edit.sh replace-in-row    <lane> "<old>" "<new>" # must match exactly once
lanes-edit.sh append-line       "LANDING — lane … @<Workstation>, …"
lanes-edit.sh add-row           "| `<lane>` | … | <Workstation> / <env> / <user> | … |"
LANES_LANE=<lane> lanes-edit.sh commit "<message>"     # commit a hand edit
```

| lane | session id | workstation / env / user | started (UTC) | objects owned | handoff path | state |
|---|---|---|---|---|---|---|
