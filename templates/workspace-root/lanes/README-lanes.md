# `lanes/LANES.md` — the estate lane register's data shape

`LANES.md` is the estate's live-lane register (lane-collision-protocol Rule
4): one row per lane, appended when a lane starts and updated when it stops.
It is tracked in git, on `main` of this repository, so every registry change
is a commit and attributable to a lane and a workstation (Rule 9, Amendment
3) — never a single untracked file an editor overwrites from memory.

An estate that predates this repository keeps its own
`~/projects/<estate>/LANES.md`, a symlink `opensoft/openRepoTools`'s
`link-estates` places to `~/projects/{{LOGIN}}-wip/lanes/LANES.md`, so the
path every lane already uses keeps resolving to the same file.

## The hazard

`LANES.md` carries a HAZARD comment at the top, read before writing it: GNU
`sed -i` writes a temp file and renames it over the path it is given, which —
run against a symlink that resolves here — replaces that symlink with a
regular file and silently detaches the register from git, with no error and
no `git status` entry in the estate that lost it. Write through
`lanes-edit.sh` (`opensoft/openRepoTools`), or with
`sed -i --follow-symlinks`, a `>` / `>>` redirect, or python's
`open(path,'w'|'a')` — never plain `sed -i` against a path that might be a
symlink to this file, and never the whole file from memory.

## The row format

One row per lane, seven columns:

| lane | session id | workstation / env / user | started (UTC) | objects owned | handoff path | state |

`lane` is the tmux-window/session/register name (`<repo>-<position across>`,
lane-collision-protocol, ruled 2026-09-10). `workstation / env / user` is
spelled exactly `<Workstation> / <env> / <user>` (Rule 10), because the same
window name can exist on more than one workstation, and a row whose
workstation is not yet established has its owner fill it in. `state` reads
`LANDING #<n>` from the moment a lane posts LANDING on a change-directory
pull request until it posts LANDED, or 30 minutes pass (Rule 6); other lanes
hold merges into that repository's `main` while any row reads `LANDING`.

## The log directory

`lanes/log/<lane>.md` — one append-only file per lane (Amendment 7). Line one
is `# lane <lane> — object log (lane-collision-protocol Amendment 7)`; every
other line is one event in the grammar:

```text
<VERB> — lane <lane>, session <transcript-uuid>@<workstation>, <UTC>, <object>[ → <payload> | ← <payload>][ — <free text>]
```

It says what a lane *claims*, *opens*, *lands* and *releases* — `LANES.md`
says only where a lane *is*. One file per lane is what makes concurrent
writes from more than one workstation safe: two lanes writing at the same
moment touch two different files, so what a shared file would turn into a
conflict is a fast-forward here. `lanes/log/README.md` names the one writer
(`lanes-edit.sh`) and the one reader (`who`); `lanes/repos.tsv`, the alias
table those events resolve an omitted owner through, ships with the lane
tooling in `opensoft/openRepoTools` — this repository may carry only an
override.
