# AGENTS-shape.md — the rules of this repository's shape

COPIED from openRepoShape and DIGEST-PINNED in `contracts/shape-pin.yaml`, so
it says the same thing in every project carrying the shape. It describes the
MECHANICS of this repository, not this project's work: the project's own
instructions are in `AGENTS.md` beside it, and that file is not pinned.

## What this repository is

The ASSEMBLY ROOT of a project that spans three repositories. It holds no
product code of its own. It holds `project.yaml` — the manifest, and the
SOURCE of what this project is — the two legs as submodules at the paths
`project.yaml` names, `spec/` and `code/` by default, the pins that say which
commit of each leg this project currently IS, and the gate that checks them.

**Work from here, not from a leg clone.** An agent standing in a leg clone can
see neither the manifest nor the other leg, so it is reading half a project and
cannot advance it at all. `git clone --recurse-submodules` this repository and
run `make bootstrap`.

## Advancing a leg is ONE commit here

Commit in the leg, push it, then ONE commit in THIS repository moving all
three of these together:

1. the **gitlink** — the `160000` entry recorded at the leg's path,
2. **`commit:`** in `contracts/<role>-pin.yaml`,
3. every **`.github/workflows/*.yml` `@<sha>`** reference naming that leg.

Never a bare `git submodule update` followed by a commit: that moves the
gitlink alone. `make pins` (`scripts/validate-pins.py`, and the `validate`
check on every pull request) refuses when the three disagree, and it is right
to — seven consecutive pin-syncs in the xFactory aggregation moved the gitlink
alone and left `validate` red for a day, unnoticed because the check runs on
pull requests only.

## Never edit a file that has a row in `contracts/shape-pin.yaml`

Those rows are the copies of openRepoShape this project carries — the
validators, `scripts/bootstrap.py`, the Makefile, the `validate` workflow, this
file — and every sha256 is recomputed on every pull request. An edit in place
is reported as DRIFT and refused.

The exit is UPSTREAM: change it in `opensoft/openRepoShape`, then run that
repository's `update-shape.py` against this project FROM a checkout of the
standard, and land the result as a pull request. **Never update a digest in
place.** That records this copy as the standard and makes the drift the
validator reports today invisible tomorrow.

`AGENTS.md`, `CLAUDE.md`, `README.md`, `project.yaml` and the leg pins have no
row: they are this project's own content, and yours to edit.

## What goes where

| | |
|---|---|
| the spec leg | requirements, decisions, acceptance criteria, the contracts |
| the code leg | the implementation and its tests |
| this root | `project.yaml`, the pins, the gate, the assistant instructions, the front door |

A contract the code READS but does not OWN lives in the SPEC leg. That was
ruled and measured on the MedxEHR conversion: `contracts/` moved to the spec
leg, and the code leg's tooling now takes `CONTRACTS_DIR` from the environment
— the root Makefile exports `$(CURDIR)/spec/contracts` once — rather than each
script guessing at `../`.

## The three commands

```
make bootstrap   the legs onto their tracking branch AT the pinned commit,
                 then the validators, then the review-authority readout
make validate    naming + manifest + lockstep pins (what CI runs)
make pins        the lockstep pin validator alone
```

`make bootstrap` places each leg on the tracking branch AT its pinned commit —
not a detached HEAD, and not somebody's newer tip. The line `authority is not
wallet-carried in this org` is a report, not a fault.

## The refusals to respect

* **Never `--admin`**, and never suggest it. A ruleset that refuses a direct
  push is doing its job.
* **Never a direct push to the default branch.** These organisations are
  pull-request only; every change here arrives as a pull request.
* **Never `--allow-upstream-org`, `--yes` or `--accept-local` on your own
  initiative.** Each stands in for a human's judgement — scaffolding into the
  upstream's own namespace, consenting to a re-pin, keeping a local edit that
  hides drift. Pass one only when a human has asked for it, in those words.

## This layout confers NOTHING

`role:` and every other manifest field confer NOTHING — no gate, no floor, no
grant, no clearance eligibility; a consumer deriving permission from them is
defective. A one-repository project is reviewed identically, because the
authority travels in the grants rather than in the layout. Asked to make
`role: spec` mean "spec authority lives here", say no: that turns a layout into
a governance boundary, which is the one thing this standard exists to prevent.

## Declaring descent

A `<Domainx><Product>` name is a CLAIM of descent, and a claim needs a
REFERENT: this project descends from a neutral product only if it PINS one.
The declaration is `neutral_product_pins:` in `project.yaml` plus
`contracts/<product>-pin.yaml` beside it, in ONE commit — the classification
changes WITH the pin, never before it. Declare one only when the human asked
for it: an invented pin puts a false fact about this project's ancestry in
their tree.

`shape:` records which openRepoShape this project was cut from, by commit and
tree digest. `reference:` records the document the human's election followed —
a claim about what that human read, and not yours to change.

## In a family

A FAMILY holder pins assembly roots — repositories like this one — as
submodules under `members/<Project>`, and never legs. The member pin moves from
the HOLDER's side: openRepoShape's `scripts/family.py bump`, one commit,
landed as a pull request. Nothing here changes and nothing here is
subordinate: membership is navigation, confers nothing, and this is a whole
project whether or not any family names it.
