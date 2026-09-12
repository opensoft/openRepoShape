# workspaces/

This directory — `workspaces/` in `{{ORG}}/{{LOGIN}}-wip`, {{LOGIN}}'s
workspace repository — holds per-family and per-project **workspace
manifests**: the record of which Speckit features are parked, on which
branch, at which commit, in which leg, and pushed or not. It is the manifest
repository named by `~/.agents/workspace.yaml`, and this is where that
config's `path:` points.

## Naming, and the per-org override

This repository follows the `workspace` naming form in `opensoft/openRepoShape`'s
`contracts/repository-naming.yaml`: **`<user>-wip`** (`<user>` the lowercased
GitHub login), one per person, org-owned, private with team read. By default
a person's workspace repository lives in their **home org** and indexes work
in every org they touch — this directory's manifests as `workspaces/<org>/…`,
and the sibling `handoffs/<estate>/…` — but an org whose work must not be
indexed outside it can be pointed at its own `<org>/<user>-wip` instead, via
the `orgs:` map in `~/.agents/workspace.yaml`. See the lane-collision
protocol's Addendum to Amendment 4 and `openRepoShape#81` for the resolution
order and the full ruling.

## What lives here

One file per family, or one file per standalone project:

- `workspaces/<Family>.yaml` — one entry per member project of a family (the
  doubled `<Family>/<Family>` layout), so a family's whole set of parked
  features travels together.
- `workspaces/<Project>.yaml` — a standalone project not inside a family
  folder. It is named from the project's own `project.yaml`'s `id:` field;
  for a single-repository project (no `project.yaml`) it is named from the
  repository's directory name. A name outside `[A-Za-z0-9._-]+` is
  **refused**, never sanitised — `park` stops and reports rather than
  guessing a safe name.

## Who writes them

`speckit park` writes these files, and `speckit resume` reads them. **They
are never hand-edited.** A manifest is a record of git state (branches,
commits, whether a leg pushed cleanly); editing it by hand can only produce
a value that does not match reality, and `resume`'s refusals depend on the
recorded `parked_commit` being trustworthy. If a manifest is wrong, the fix
is to `park` again from a checkout that has the truth, not to edit the YAML.

## Schema

Fixed key order, written by `park` in one pass so that re-parking unchanged
state produces a byte-identical file (no empty commit). A standalone-project
example, one leg parked:

```yaml
schema_version: 1
kind: workspace-manifest
written_by: speckit park          # provenance, not authority
projects:
  - id: atlas
    repository: {{ORG}}/Atlas
    shape: single                  # three-leg | single
    root: Atlas                    # POSIX, RELATIVE to ~/projects
    tracking_branch: main
    parked_at: 2026-01-01T00:00:00Z
    parked_on: <workstation>
    parked_by_lane: <lane>
    active_feature: 001-example
    features:
      - branch: 001-example
        legs:
          - role: repo
            remote: origin
            parked_commit: <40-hex sha>
            wip: false
            wip_depth: 0
            pushed: true
```

A `shape: three-leg` entry carries one leg per role (`assembly`/`spec`/`code`)
and a `feature_directory`; `shape: single` carries one leg, `role: repo`, and
omits it.

## Invariants

- **No absolute path anywhere in a value.** A linked worktree's absolute path
  is machine plumbing; only branches, commits and a relative `root` are
  recorded.
- **`parked_commit` is always a full 40-hex sha** — never abbreviated.
- **`root` is POSIX and relative** — forward slashes, no drive letter, no
  leading `/` or `~`.
- **`wip_depth >= 1` if and only if `wip: true`.**
- **One `projects[]` entry per `id`.**

## Concurrency

`park` treats this directory the way the lane tooling treats the lane
register beside it, for the same reasons:

1. a mutex around the write, released on exit;
2. any pre-existing uncommitted change under `workspaces/` is committed
   first, as its own commit, so a peer's in-flight edit is never swept into
   yours;
3. only the one project's block is rewritten;
4. **one commit per park**, with an explicit pathspec — never `git add -A`,
   never a bare `git commit`;
5. `git pull --rebase` before the push, retried on a race, and aborted
   (leaving the checkout clean) on a real conflict.

Two workstations parking the same project: **last write wins**, in this
person's own repository, and the write that "lost" is still in `git log` —
nothing is deleted. That is safe because this repository belongs to one
person alone.
