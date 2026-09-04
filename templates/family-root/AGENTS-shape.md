# AGENTS-shape.md — the rules of this family holder's shape

COPIED from openRepoShape and DIGEST-PINNED in `contracts/shape-pin.yaml`, so
it says the same thing in every holder carrying the shape. It describes the
MECHANICS of this repository; the family's own instructions are in `AGENTS.md`
beside it, and that file is not pinned.

## What this repository is

A FAMILY HOLDER, and **not a project**. It has no spec leg, no code leg and no
`project.yaml`. It pins other projects' ASSEMBLY ROOTS as submodules under
`members/<Project>` and carries the utilities to fetch and bootstrap them
together, for parts that DEPLOY SEPARATELY — parts that ship together are one
project already.

**Members are assembly roots, never legs.** A leg has no `project.yaml` and
belongs to its own root; `scripts/family.py` refuses one, and the refusal is
correct. Each member is a whole project — its own three repositories, its own
gate, its own release — and stays one whether or not this repository names it.

## Adding, bumping and removing a member

Run openRepoShape's `scripts/family.py` FROM a checkout of the standard,
against this holder:

```sh
python3 scripts/family.py add    --family-root <path> --member <org>/<Project>
python3 scripts/family.py bump   --family-root <path> --member <Project> --to <40 hex>
python3 scripts/family.py remove --family-root <path> --member <Project>
```

Each writes ONE commit moving the **gitlink** for `members/<Project>` and that
row's **`members[].pin`** in `family.yaml` together. `make pins`
(`scripts/validate-family.py`) refuses when the two disagree, and it is right
to: a gitlink moved alone is a pin that names a commit the tree is not at. Do
not hand-edit the `members:` block — the tool rewrites it wholesale. Land the
commit as a pull request; the member must already be scaffolded or adopted,
because a family cannot make a project out of a repository.

## The three commands

```
make bootstrap   every member and its legs, then each member's own bootstrap
make validate    the family validator, then each member's `make validate`
make pins        the family's lockstep check alone
```

`make bootstrap` puts each member's legs on their tracking branch AT their
pinned commits, by running the member's own bootstrap rather than
reimplementing it.

## Never edit a file that has a row in `contracts/shape-pin.yaml`

Those rows are the copies of openRepoShape this holder carries — the family
validator, `scripts/bootstrap.py`, the Makefile, the `validate` workflow, this
file — and every sha256 is recomputed on every pull request. An edit in place
is reported as DRIFT and refused.

The exit is UPSTREAM: change it in `opensoft/openRepoShape`, then run that
repository's `update-shape.py` against this holder FROM a checkout of the
standard, and land the result as a pull request. **Never update a digest in
place.** That records this copy as the standard and makes the drift the
validator reports today invisible tomorrow.

`AGENTS.md`, `CLAUDE.md`, `README.md` and `family.yaml` have no row: they are
this family's own content.

## The refusals to respect

* **Never `--admin`**, and never suggest it. A ruleset that refuses a direct
  push is doing its job.
* **Never a direct push to the default branch.** Every change here arrives as
  a pull request.
* **Never `--allow-upstream-org`, `--yes` or `--accept-local` on your own
  initiative.** Each stands in for a human's judgement — scaffolding into the
  upstream's own namespace, consenting to a re-pin, keeping a local edit that
  hides drift. Pass one only when a human has asked for it, in those words.
* `scripts/family.py init` creates a repository and has NO prompt of its own,
  which makes getting the human's explicit yes your job.

## Membership confers NOTHING

No row in `family.yaml` and no field in it grants review authority, clearance
eligibility, gate standing or lifecycle state over anything it names; a
consumer deriving permission from them is defective. A project in no family is
reviewed identically to one in this family. Membership is navigation, exactly
as the three legs are.
