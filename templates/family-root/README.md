# {{FAMILY_NAME}}

The **family holder** for the `{{FAMILY_ID}}` family of projects in
`{{ORG}}`. It is not a project: it has no spec leg and no code leg. It pins
its members' **assembly roots** as submodules under `members/` and carries the
utilities to fetch and bootstrap them together.

```sh
git clone --recurse-submodules {{CLONE_URL}}
cd {{FAMILY_NAME}}
make bootstrap
```

`make bootstrap` initialises every member recursively — each member is itself
a superproject with two legs — and then runs each member's own
`make bootstrap`, which puts its legs on their tracking branches at their
pinned commits and runs its validators.

| target | what it does |
|---|---|
| `make bootstrap` | fetch every member and its legs, then each member's `make bootstrap` |
| `make siblings` | clone every member BESIDE this holder, on its tracking branch; fetch the ones already there |
| `make validate` | the family validator, then each member's `make validate` |
| `make pins` | the family's own lockstep check alone: gitlink == `members[].pin.commit` |
| `make park` | each member's own `make park`, in its WORKING CLONE beside this holder: the estate's in-flight work, committed, pushed and RECORDED for another workstation |
| `make resume` | the same with `make resume`: those records, recreated here. A member with no working clone is reported and SKIPPED (`make siblings` places one); the holder exits non-zero if any member was skipped or refused |

## Workstation layout

This holder lives inside a **plain folder named after the family** — not a
repository, not a submodule, just a directory — with the members' working
clones beside it:

```
{{FAMILY_NAME}}/                    a PLAIN FOLDER, not a git repository
  {{FAMILY_NAME}}/                  THE HOLDER (this repository)
    family.yaml                     the members and their pins
    members/<Project>               each member, PINNED and DETACHED
  <Project>/                        a WORKING clone, on its tracking branch
  <Project>/                        …one per row in family.yaml
  <Project>-worktrees/…             whatever the member's own work needs
  session-handoff-*.md              the estate's own files live in the folder
```

`make siblings` is what places it: for each row in `family.yaml` it clones the
member at `../<Project>` from the same url `make bootstrap` uses, then runs
that member's own `scripts/bootstrap.py` so its legs are on their tracking
branches at their pins. A member that is already there is **fetched and
nothing else** — no checkout, no reset, no pull — because somebody is working
in it. A directory that is a clone of a DIFFERENT repository is reported and
skipped, never written into. It is idempotent: a second run is all `present`.

**TWO COPIES OF EVERY MEMBER, on purpose.** `members/<Project>` inside this
holder is a pinned, detached checkout, and it is what `make bootstrap` and
`make validate` read — detached because a pin is a commit and not a branch.
The clone BESIDE the holder is **where you work**: its own tracking branch,
its own worktrees, its own pull requests. The family follows it afterwards
with `family.py bump`, which is the only thing that moves a pin.

**The doubled `{{FAMILY_NAME}}/{{FAMILY_NAME}}` is deliberate** (ruled
2026-09-09). The holder is a repository and keeps its own name; the folder is
named after the family because that is what the folder holds. `family.yaml`
is the only thing that tells the two apart, and it is inside the holder.

**Nothing ever moves a checkout.** When this holder's parent folder is not
named after the family, `make siblings` WARNS and prints the exact `mv` for a
human to run — it moves nothing itself. Relocating a directory out from under
a shell, an editor or an agent lane breaks linked worktrees, whose `.git`
files carry absolute paths, and this standard does not act by surprise.

From a checkout of `{{SHAPE_REPOSITORY}}` the same utility runs against a
holder anywhere on disk, which is what to use before this repository is
cloned twice:

```sh
python3 scripts/family.py siblings --family-root <path-to-this-holder>
```

## What a family is, and what it is not

Ruled by **Brett Heap on 2026-09-04**: *"InkRouter is a set of microservices
and they deploy separately as api's… So probably InkRouter is only something
that can download all the others easily? like a holder folder and some
utilities for the family of services."*

Each member is a whole project — its own assembly root, its own spec and code
legs, its own gate, its own release — and stays one whether or not this
repository names it. **Membership confers nothing.** No row in `family.yaml`
grants review authority, clearance eligibility, gate standing or lifecycle
state over anything; a project in no family is reviewed identically to one in
this family. Membership is navigation, exactly as the three legs are.

## The pins

Each member is pinned twice, in ONE commit: the **gitlink** git records for
`members/<Project>`, and `members[].pin` in `family.yaml` — the 40-hex commit
and a `sorted-ls-tree-r-v1` tree digest. A tag is never the referent, because
a tag can be moved and a commit cannot. `scripts/validate-family.py` refuses
when the two disagree, and `scripts/family.py bump` is what moves them
together.

`family.yaml` also records each member's own `project.yaml` `id`, so the
validator can check that the tree mounted at `members/<Project>` is the
project the row claims and not merely a repository at the right commit.

## Adding, removing and moving a member

From a checkout of `{{SHAPE_REPOSITORY}}`:

```sh
python3 scripts/family.py add    --family-root <path> --member {{ORG}}/<Project>
python3 scripts/family.py bump   --family-root <path> --member <Project> --to <40 hex>
python3 scripts/family.py remove --family-root <path> --member <Project>
```

Each writes ONE commit, with explicit pathspecs, moving the gitlink and the
pin together. Land it as a pull request.

## Private members in CI

The members are private assembly roots for most organisations, and the
`validate` workflow's default `GITHUB_TOKEN` cannot clone one as a submodule.
The same credentials the assembly roots use apply here, and are tried in the
same order: a GitHub App (`SHAPE_LEGS_APP_ID` + `SHAPE_LEGS_APP_PRIVATE_KEY`,
preferred, minted per run) then a fine-grained `SHAPE_LEGS_TOKEN` PAT with
`contents:read`. With neither, the workflow degrades: it still runs the checks
that do not need the members checked out.

**On the GitHub Free plan, set these as REPOSITORY secrets.** GitHub delivers
an ORGANISATION secret only to PUBLIC repositories on Free, so on a private
repository `secrets.SHAPE_LEGS_APP_ID` is the empty string — silently — the
App steps skip, and `validate` goes GREEN with the lockstep pin check degraded
away rather than red. Use `--repo <org>/<Repo>` in place of `--org <your-org>`
above, or upgrade the organisation to Team. (Measured on InkRouter,
2026-09-04.)

`scripts/bootstrap.py` reads the same two variables from the environment when
they are there and works without them when they are not.

Shape: `{{SHAPE_REPOSITORY}}` @ `{{SHAPE_COMMIT}}`.
