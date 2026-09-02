# {{PROJECT_NAME}}

The ASSEMBLY ROOT of the `{{PROJECT_ID}}` project — the repository you clone.
It holds no product code of its own: it holds the manifest that says what this
project IS, the two legs as submodules, and the pins that say which commit of
each leg this project is.

Scaffolded from [{{SHAPE_REPOSITORY}}](https://github.com/{{SHAPE_REPOSITORY}})
at `{{SHAPE_COMMIT}}`. Elected by {{ELECTED_BY}} on {{ELECTED_ON}}, against
`{{REFERENCE}}`.

## Get started

```sh
git clone --recurse-submodules {{CLONE_URL}}
cd {{PROJECT}}
make bootstrap
```

`make bootstrap` puts each leg on the `{{TRACKING_BRANCH}}` branch **at its
pinned commit** (so you are not staring at a detached HEAD), runs the three
neutral validators, and prints whatever review authority a wallet register
names for this project — or says plainly that authority is not wallet-carried
here, and continues.

## The three legs

| role | repository | path | holds |
|---|---|---|---|
| assembly | `{{ASSEMBLY_REPOSITORY}}` | `.` | this manifest, the pins, the gate |
| spec | `{{SPEC_REPOSITORY}}` | `{{SPEC_PATH}}/` | requirements, decisions, acceptance |
| code | `{{CODE_REPOSITORY}}` | `{{CODE_PATH}}/` | the implementation and its tests |

All three carry the GitHub topic `{{TOPIC}}`, so the organisation's own search
surfaces the group without a checkout.

## The lockstep invariant

For each leg, THREE things name the same commit and they move in ONE commit:

1. the **gitlink** — the `160000` entry recorded at the leg's path
2. **`commit:`** in `contracts/<role>-pin.yaml`
3. every **`.github/workflows/*.yml` `@<sha>`** reference naming that leg

`python3 scripts/validate-pins.py` (also `make pins`, also the `validate` check
on every pull request) refuses if they disagree, and recomputes the leg's tree
digest on top. Advancing a pin is therefore one commit that touches the
submodule, the pin file, and any workflow ref — never a bare `git submodule
update` followed by a commit.

This is written down because the family learned it the expensive way: seven
consecutive pin-syncs in the xFactory aggregation moved the gitlink alone and
left `validate` red on every pull request for a day, unnoticed because the
check runs on pull requests only.

## What the election confers

Nothing. Electing this shape changes no gate, no floor, no grant and no
clearance eligibility; a one-repository project is reviewed identically,
because the authority travels in the grants rather than in the layout. The
`role:` fields in `project.yaml` are navigation. A tool that reads `role: spec`
as "spec authority lives here" has quietly turned a layout into a governance
boundary, and is defective.

## Layout

```
project.yaml                     the manifest — the SOURCE of this group
contracts/repository-naming.yaml the four naming families (copied from the shape)
contracts/spec-pin.yaml          the spec leg's commit + tree digest
contracts/code-pin.yaml          the code leg's commit + tree digest
contracts/shape-pin.yaml         the openRepoShape revision + per-file digests
scripts/bootstrap.py             the one command after a recursive clone
scripts/validate-manifest.py     project.yaml, and the legs' names
scripts/validate-pins.py         THE LOCKSTEP VALIDATOR
scripts/validate-repository-naming.py
scripts/repo_shape.py            shared helpers, standard library only
.github/workflows/validate.yml   the neutral gate, on pull_request
```

Everything under `scripts/` and `contracts/repository-naming.yaml` is a COPY
from `{{SHAPE_REPOSITORY}}`, digest-pinned in `contracts/shape-pin.yaml`. Edit
them upstream, not here — a local edit is reported as drift.
