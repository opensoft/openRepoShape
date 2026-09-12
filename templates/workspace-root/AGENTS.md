# AGENTS.md — {{LOGIN}}-wip

{{LOGIN}}'s workspace repository. Read `README.md` for what it is; this file
is what you must and must not do inside it.

## The rules

1. **Never write `lanes/LANES.md` whole.** Every write goes through the lane
   tooling's `lanes-edit.sh` — `append-row-status`, `replace-in-row`,
   `append-line`, `add-row`, `log`, `claim`, `release`, or `commit` for a hand
   edit made with an allowed tool. The helper takes a mutex, edits exactly one
   line, refuses if more than one line moved, commits, and pulls-rebases-pushes.
   `log`, `claim` and `release` are Amendment 7's, and the same helper is also
   the only writer of the per-lane object logs under `lanes/log/` that those
   three append to: a `LANDING` or `LANDED` writes the register and the log in
   ONE commit, so the two can never disagree about a merge hold, and `who` is
   the read of both. A whole-file write from memory has, elsewhere in this
   protocol's history, deleted other lanes' rows and a day of Rule 6 lines in
   one act; if you find yourself about to emit the whole file, the rows you
   did not read are the rows you are about to delete. `git add -A`, a bare
   `git commit`, `git stash` and any force-push are forbidden here for the
   same reason.
2. **Reach the register through the installed command, not a raw edit of a
   symlink.** `lanes-edit.sh` finds this register through
   `~/.agents/workspace.yaml`, wherever it is run from. An estate that
   predates this repository keeps a `~/projects/<estate>/LANES.md` symlink to
   `lanes/LANES.md` here, placed by `link-estates`. Plain `sed -i` REPLACES a
   symlink with a regular file and silently detaches the register from git;
   `sed -i --follow-symlinks`, a `>` or `>>` redirect, `cat tmp > LANES.md`
   and python's `open(path,'w'|'a')` all preserve it. See
   README-lanes in `opensoft/openRepoTools`.
3. **Handoffs are named for the lane**, never for the date alone:
   `handoffs/<estate>/session-handoff-<YYYY-MM-DD>-lane-<name>.md`, first
   line the lane header. One directory per estate. A bare
   `session-handoff-<date>.md` is forbidden (lane-collision-protocol Rule 4,
   Amendment 4). Write to files UNDER `~/projects/<estate>/handoffs`, never
   to the link itself: an `mv` or `rm -rf` that rewrites it as a real
   directory detaches every handoff in that estate from git with no error.
4. **Never hand-edit anything under `workspaces/`.** Those manifests are
   `park`'s record of git state; a hand-edited value can only fail to
   match reality, and `resume`'s refusals depend on `parked_commit` being
   true. If a manifest is wrong, `park` again from a checkout that has the
   truth.
5. **Every commit carries a `Lane:` trailer** — `Lane: <lane> (<Window>)` —
   and an explicit pathspec. Registry commits are subject-formatted by the
   helper (`LANES(<lane>@<workstation>): <what>`); a handoff commit reads
   `handoff(<lane>@<workstation>): <what>`. One commit per write, pushed in
   the same act: a write left uncommitted is captured by the next lane's
   commit and its attribution is lost.
6. **Direct commits to `main` are the norm here, when the organisation's
   PR-only ruleset excludes this repository.** That exclusion is what lets
   a per-edit registry commit land at all; where it does not exist, write
   through that organisation's approved PR flow instead, and never bypass
   a ruleset that refuses a direct push. Where it does: pull with
   `--rebase`, push; on a real conflict abort, leave the checkout clean,
   and report. Never force-push and never delete a remote branch.
7. **The first act of a lane is `lane-start`; the last is `lane-end`.**
   `lane-start <repo> <n>`, run in the tmux window that will carry the lane,
   is what makes the window name, the session name and the row say the same
   thing: it refuses outside tmux, refuses a name a live session still holds
   in another window, renames the window, writes the row through
   `lanes-edit.sh`, and then `exec`s `claude --resume` or `--name` under that
   name. `lane-end <lane> [--retire]` closes the row and refuses while it
   still shows an open `LANDING` or `CLAIMED` — Rule 6 holds other lanes'
   merges while it does. Both are boundary acts: do NOT run them mid-session,
   because renaming a running session into a title that is still held is
   exactly what mints `<lane> (2)` and costs the lane its address. Neither
   ever writes `LANES.md` directly; both go through rule 1's writer.
8. **No secrets, no code, no exceptions: the lane tooling lives in
   `opensoft/openRepoTools`.** No tokens, keys, `.env` files or credentials —
   private is not a vault. No product code, no build, no CI. `lanes-edit.sh`,
   `lane-start`, `lane-end`, `test_lane_helpers.sh` and `link-estates` were
   this repository's one exception until lane-collision-protocol Amendment 9;
   they are installed commands from `opensoft/openRepoTools` now, and are not
   carried here. `lanes/repos.tsv`'s base alias table ships with that tool
   too — this repository may carry only an override. This repository holds a
   person's index of their own work, the lane register, and nothing else. It
   elects nothing and confers nothing; do not let anyone tell you otherwise.

## Governing documents

- `~/.agents/protocols/lane-collision-protocol.md` — Rule 4 and Amendment 4
  (handoffs), Rules 9 and 10 and Amendment 3 (the register in git, the
  workstation column), Amendment 5 (the register lives in the workspace
  repository), Amendment 9 (the lane tooling moves out of it).
- `opensoft/openRepoShape` — the naming policy that classifies `<user>-wip`
  (#81, the `workspace` family in `contracts/repository-naming.yaml`) and the
  workspace-manifest ruling (#77). `templates/workspace-root/` there is what
  this repository was made from.
- `opensoft/openRepoTools` — the lane tooling: `lanes-edit.sh`, `lane-start`,
  `lane-end`, `test_lane_helpers.sh`, `link-estates`, and `wip init` (what
  makes a repository like this one). Its own `AGENTS.md` is the operating
  manual; README-lanes there describes the register's data shape.
