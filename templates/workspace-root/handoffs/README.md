# handoffs/

This directory — `handoffs/` in `{{ORG}}/{{LOGIN}}-wip`, {{LOGIN}}'s
workspace repository — is the home of {{LOGIN}}'s session-handoff documents:
the files a lane writes before stopping, so a later session (on this
workstation or another one) can pick the work back up. It is the home
lane-collision-protocol Amendment 4 (handoffs in the workspace repository)
gives them.

## Layout

```text
handoffs/<estate>/session-handoff-<YYYY-MM-DD>-lane-<name>.md
```

One subdirectory per **estate** (a project or family folder on this person's
workstation), and inside it exactly the file-naming rule Rule 4 has always
used: named for the lane, never for the date alone, first line the lane
header.

## The `~/projects/<estate>/handoffs` symlink

`~/projects/<estate>/handoffs` is a **symlink** to
`~/projects/{{LOGIN}}-wip/handoffs/<estate>`, placed by
`opensoft/openRepoTools`'s `link-estates`, so the old path,
`~/projects/<estate>/handoffs/session-handoff-<date>-lane-<name>.md`, keeps
resolving to the same file under both spellings. `cat`, `grep`, `ls`, a `>>`
redirect, and a plain `open()` all keep working from the estate folder. The
estate folder itself is not a repository and does not become one.

An org placed under the `orgs:` override (Addendum to Amendment 4,
`openRepoShape#81`) keeps that estate's handoffs in that org's own
`<user>-wip` repository instead, and this same symlink points there.

## The symlink hazard (Amendment 4(c))

A handoff reached through `handoffs/` is an ordinary file inside this
checkout, so the risk is to the **directory link**: an `mv`, an `rm -rf`, or
any tool that rewrites `~/projects/<estate>/handoffs` as a real directory
silently detaches every handoff in that estate from git, with no error and no
`git status` entry. Never write to the link itself — write only to files
under it — and if `ls -la ~/projects/<estate>/handoffs` does not show a
symlink, stop and report before writing anything.

## One commit per write (Amendment 4(d))

When the organisation's PR-only ruleset excludes this repository, the lane
that writes a handoff commits it immediately and pushes:

```text
handoff(<lane>@<workstation>): <what>
```

Explicit pathspecs, never `git add -A`, never a bare `git commit`, never
`git stash`, never a force-push — a write left uncommitted is captured by
the next lane's commit and its attribution is lost. A Rule 3 `RESUMED by` /
`COMPLETED by` / `HANDED OFF to` stamp is a write like any other and is
committed the same way, in the same act. `git pull --rebase` precedes the
push; on a real conflict the writer aborts, leaves the checkout clean, and
reports. Where no such exclusion is configured, commit through that
organisation's approved PR flow instead.
