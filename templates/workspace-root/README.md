# {{LOGIN}}-wip

**{{LOGIN}}'s workspace repository** — the `<user>-wip` form of the naming
policy in [{{SHAPE_REPOSITORY}}](https://github.com/{{SHAPE_REPOSITORY}})
(classified as the `workspace` family in `contracts/repository-naming.yaml`,
added by openRepoShape#81). **One repository per person, private, org-owned**
rather than personal-account so the index survives offboarding — **with team
read**, so a lane can read another lane's handoffs, while each person writes
only their own.

**It holds no code and it confers nothing.** Membership of nothing, election
of nothing, no gate, no floor, no grant, no clearance eligibility. It is one
person's index of their own unfinished work, plus the estate's live-lane
register — data, and nothing else. The tooling that reads and writes these
files — `lanes-edit.sh`, `lane-start`, `lane-end`, `link-estates` — is
`opensoft/openRepoTools`'s, not this repository's own; nothing in this
standard creates one of these repositories either, a person makes their own
by hand (or by `openRepoTools wip init`) and names it once.

## Layout

```text
workspaces/   one YAML manifest per family or standalone project — what
              `park` writes and `resume` reads. Never hand-edited.
handoffs/     session-handoff documents, one directory per estate
              (`handoffs/<estate>/session-handoff-<date>-lane-<name>.md`).
lanes/        LANES.md — the estate lane register (lane-collision-protocol
              Rule 9) — its data shape described by README-lanes in
              opensoft/openRepoTools, and the per-lane object logs under
              lanes/log/ (Amendment 7).
```

## How it is found

Named **once**, in `~/.agents/workspace.yaml` — not in a `project.yaml`, not
in an assembly root, not in a `family.yaml`:

```yaml
repository: {{ORG}}/{{LOGIN}}-wip
path: ~/projects/{{LOGIN}}-wip
```

`park` and `resume` read that file; so does every lane looking for
where a handoff goes. By default this one repository, in this
person's home organisation, indexes work in every organisation they touch,
a folder per org inside it (`workspaces/<org>/…`, `handoffs/<estate>/…`); an
organisation whose work must not be indexed outside it — even by name — is
pointed at its own `<org>/{{LOGIN}}-wip` instead, by the same file's `orgs:`
map (openRepoShape#81, Addendum to Amendment 4 of the lane-collision
protocol).

## The link targets

Every path an estate already uses keeps resolving, through symlinks placed
idempotently by `opensoft/openRepoTools`'s `link-estates`:

| the live path a lane already uses | points at |
|---|---|
| `~/projects/<estate>/handoffs` | `~/projects/{{LOGIN}}-wip/handoffs/<estate>` |
| `~/projects/<estate>/LANES.md` | `~/projects/{{LOGIN}}-wip/lanes/LANES.md` |

A handoffs link is placed for every `handoffs/<estate>/` directory here whose
`~/projects/<estate>` exists on the workstation, and skipped for the rest.
`link-estates` never deletes a real file — it moves one aside with a stamped
suffix — and rehearses with `--dry-run`.

## Adopting it on a second workstation

Clone `{{ORG}}/{{LOGIN}}-wip`, write the same two lines shown above into
`~/.agents/workspace.yaml` on that workstation (`path:` set to wherever the
clone lives there), and run the installed `link-estates` to place this
workstation's symlinks. Both steps are idempotent: run again, they change
nothing that is already correct.

## Direct commits to `main`

When the organisation's PR-only ruleset excludes this repository, direct
commits to `main` are deliberate: the register writes **one commit per
edit** (lane-collision-protocol Rule 9), from many concurrent lanes on more
than one workstation, and a pull request per registry edit is not a workable
shape for data that no review gate protects. Where no such exclusion is
configured, write through that organisation's approved PR flow instead.
