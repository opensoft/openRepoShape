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
| `make validate` | the family validator, then each member's `make validate` |
| `make pins` | the family's own lockstep check alone: gitlink == `members[].pin.commit` |

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

`scripts/bootstrap.py` reads the same two variables from the environment when
they are there and works without them when they are not.

Shape: `{{SHAPE_REPOSITORY}}` @ `{{SHAPE_COMMIT}}`.
