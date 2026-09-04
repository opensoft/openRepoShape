# openRepoShape

**Status: staged standard.** The mechanics of a project that spans several
repositories: what they are called, how they are pinned to each other, how one
clone brings the whole project down, and what an AI assistant does when a human
says "scaffold a new project with this shape".

GitHub has no folder that groups repositories, so a project spanning several of
them is held together by convention or by nothing. This repository is the
convention, as data and as running code.

Ruled by **Brett Heap on 2026-09-02**: the name `openRepoShape`, PUBLIC
visibility, Apache-2.0; and that the ASSEMBLY leg **is** the per-project root
repository — the one an engineer clones. The doctrine it serves is staged, not
yet ratified, in `opensoft/openxFactory` at
`ideation/staging/project-repo-schema/project-repo-schema.md`; a project may
elect the shape now, provided its `project.yaml` records that staged fragment
as the `reference:` the election followed.

**The shape is elective and confers nothing.** Electing it changes no gate, no
floor, no grant and no clearance eligibility. A one-repository project and a
three-repository project are reviewed identically, because the authority
travels in the grants rather than in the layout. Review lanes and
wallet-carried authority are OVERLAYS an org adds later; a project with no
overlays is fully conformant.

## Starting a project in a new organisation

```sh
gh repo fork opensoft/openRepoShape --org <your-org> --clone   # a FORK, not a
cd openRepoShape                                               # template copy
./setup.sh --project Atlas
```

`setup.sh` checks your machine, detects your fork's organisation, checks the
three names, shows the plan and asks once — then creates the three
repositories, clones the assembly root beside the fork and bootstraps it.
`--yes` skips the question, `--org` overrides the detection, and it REFUSES to
scaffold into `opensoft` without `--allow-upstream-org`, because cloning the
upstream instead of forking it looks identical from inside the directory. A
fork rather than a template keeps the upstream link, so shape updates pull and
`contracts/shape-pin.yaml` names a commit that still means something.

### What setup.sh does

The same commands, in order, with no behaviour of its own:

```sh
python3 scripts/validate-repository-naming.py --explain Atlas Atlas-spec Atlas-code
python3 scaffold-project.py --org <your-org> --project Atlas --dry-run
python3 scaffold-project.py --org <your-org> --project Atlas \
    --visibility private --elected-by 'Your Name'   # or public / internal
git clone --recurse-submodules https://github.com/<your-org>/Atlas.git
cd Atlas && make bootstrap
```

## The three legs

| role | repository | holds |
|---|---|---|
| assembly | `<Project>` | `project.yaml`, the two legs as submodules, the pins, the gate |
| spec | `<Project>-spec` | requirements, decisions, acceptance criteria |
| code | `<Project>-code` | the implementation and its tests |

The four naming families live in `contracts/repository-naming.yaml`: neutral
products `open<Product>`, domain descendants `<Domainx><Product>`, installs
`<X>-Install`, and project legs as above. The leg suffixes are lowercase and
hyphenated precisely so they sit in a different visual class from every other
family, all of which are CamelCase words. Every repository of a project also
carries the GitHub topic `xf-project-<id>`.

### Private legs need `SHAPE_LEGS_TOKEN`; the root checkout never does

The `validate` workflow's default `GITHUB_TOKEN` cannot clone a **private or
internal** leg as a submodule — this was the defect on the first real
adoption (MedxSoft/MedxEHR #7): `<Project>-spec`/`<Project>-code` were
private, and the required check was red on every pull request. Add a
**`SHAPE_LEGS_TOKEN`** repository or organisation secret — a fine-grained PAT
or GitHub App installation token with `contents:read` on the LEGS ONLY — on
the assembly root. Both `scaffold-project.py` and `adopt-project.py execute`
print a one-line reminder when they create a private or internal leg.

The root repository is always readable by the workflow's own default token,
so `actions/checkout` never carries a `token:` override. Putting the legs
token there was itself the next defect, on the first real use of the secret
(MedxSoft/MedxEHR and MedxSoft/MedxGlass, runs 33821509948 and 33821512605):
a token correctly scoped to `contents:read` on the legs alone cannot read
the root, so `actions/checkout` itself failed with a 403 before any check
ran. `SHAPE_LEGS_TOKEN` is now read only inside the guarded "fetch the legs
(submodules)" step, scoped to that step's `env:`, and used through a
`git -c url.<...>.insteadOf=<...>` rewrite covering both HTTPS and SSH leg
URLs — never persisted onto the root checkout.

Without the secret the workflow degrades instead of failing: it checks out
the root without submodules, attempts `git submodule update --init
--recursive` best-effort, and if that fails it still runs the naming and
manifest checks, skips `validate-pins.py` with a warning explaining why, and
fails outright only if `SHAPE_LEGS_TOKEN` **is** set and the fetch still
failed — meaning the token cannot read one of the LEG repositories, never
the root, which no longer depends on it — checked via a job-level `env:
SHAPE_LEGS_TOKEN_SET`, not `secrets` in the step `if:` (disallowed there;
MedxEHR PR #8, MedxGlass PR #1: zero-job push runs).

### A descendant form is a claim; a claim needs a referent

`open<Product>` and `<X>-Install` say what they are in their own characters and
win outright. `<Domainx><Product>` does not. Ruled by **Brett Heap on
2026-09-02**: *descendant only if it pins `open<Product>`*. `MedxChart` is a
domain descendant BECAUSE MedxChart pins `openChart`. `MedxScribe` in the same
organisation descends from nothing — no `openScribe` exists — so its DECLARED
ROLE wins and it is an ordinary assembly root. Read as a fact instead of a
claim, the form refused every project in a `<Domainx>` family org on the first
pilot.

A descendant MAY CARRY LEGS — the second half of the same day's ruling.
Descent and the three-repository shape are independent facts: `MedxGlass` pins
`openGlass` AND is the assembly root mounting `MedxGlass-spec` and
`MedxGlass-code`, so `form: domain-descendant, role: assembly,
referent_declared: true` is a valid classification for a root.
`scaffold-project.py --pin openGlass@<40 hex>` writes the pin and the manifest
entry together. The legs are not descendants of anything: `MedxGlass-spec`
carries the lowercase suffix and says so.

The declaration is `neutral_product_pins:` in `project.yaml`, a fact in the
project's own tree, so classification stays OFFLINE — it never asks GitHub
whether `open<Product>` exists. The overlap is not discarded either: each leg's
`naming:` block records `form`, `role` and `also_matches`, so a resolved
overlap stays visible to the next reader. `validate-repository-naming.py`
answers the same question for one name with `--role`, `--pins` and `--explain`.

## Adopting an existing repository

A repository that already exists is converted **in place**, by
`adopt-project.py`, and this is a ruling (**Brett Heap, 2026-09-02**): it KEEPS
ITS NAME, ITS IDENTITY AND ITS FULL HISTORY and becomes the assembly root, while
`<Project>-spec` and `<Project>-code` are NEW repositories extracted with
history-preserving filters. The source is never deleted, never renamed and
never force-pushed; the only change to it is ONE split commit, arriving on a
branch by pull request — the organisations this serves are pull-request only,
and a tool needing a bypass cannot be used where it is needed.

```sh
./adopt-project.py plan --source MedxSoft/MedxEHR --project MedxEHR
#   ... a human or an AI answers every `review_required` entry in the plan
./adopt-project.py check   --plan adoption-plan.yaml
./adopt-project.py execute --plan adoption-plan.yaml --yes
```

`git filter-repo` is a **hard dependency** — `pip install git-filter-repo`, or
the same name from apt or brew. It is deliberately not vendored: history
extraction has one correct implementation, and a copy is a second one that
drifts.

### The worked example: MedxEHR — 167 files, 25 commits, three arguments

| what | where | why |
|---|---|---|
| `contracts/*.yaml` | **spec** | the code READS them and still does not own them; from `code/` they are `../spec/contracts` |
| `medx_ehr/`, `tests/`, `scripts/`, `docker/`, `.github/workflows/` | **code** | the implementation, its tests, its build and its CI |
| `openspec/`, `specs/` | **spec** | what the project has decided |
| `.specify/`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, … , `.cursor/`, `.roo/` | **root** | project-level workflow tooling spanning both legs |
| `examples/golden-run/` | **asked** | acceptance evidence the spec cites, or a test fixture? |

The contracts decision costs something, and the plan says so instead of
letting it be discovered later: `scripts/validate.py` reads `contracts/*.yaml`
from beside it and must now read ACROSS the root. `plan` finds every such file
with `git grep` and writes it into `follow_ups:`; the root Makefile it
materializes exports `CONTRACTS_DIR ?= $(CURDIR)/spec/contracts`. The tool
does not make the edit — naming it is the honest half, making it silently
would be the dangerous one. And `.specify/` and the ten identical assistant
stubs stay at the root because an assistant reading `CLAUDE.md` from inside
the code leg would be told about specifications it cannot see.

### Ambiguous is an answer, and nothing is overwritten

`contracts/path-classification.yaml` maps path globs to `spec | code | root |
ambiguous`, first match wins, each with a reason. The fourth class is not a
failure: a classifier that guessed at `examples/golden-run/` would be wrong
about half the time and silent about it. Those entries get `leg: null`,
`review_required: true` and the QUESTION; `execute` refuses while any remain,
because an unanswered question is never an implicit `root`.

A shape file whose name the source already holds — `README.md`, `Makefile`,
`.gitignore` — is written under `shape/` and the collision becomes a follow-up
for a human to merge. Then `execute` VERIFIES: every source path at the source
commit is in exactly one of {spec leg, code leg, root tree after the split}
**by blob sha**, or listed as `drop`. Counting paths would pass a split that
truncated a file; blob shas cannot, and a path in two places is as much a
finding as a path in none.

An empty repository is not a live one: `scaffold-project.py --reuse-empty-repo`
uses a zero-commit `<org>/<Project>` as the assembly root, and refuses one with
commits by naming `adopt-project.py` instead.

## The double pin, and the lockstep invariant

Each leg is pinned TWICE, in the same commit: by the **gitlink** git records
for the submodule, and by **`contracts/<role>-pin.yaml`** carrying
`revision_kind: commit`, the 40-hex commit, and a sha256 digest. A tag is never
the referent — a tag can be moved and a commit cannot — and a pin never
expresses a range.

Three things therefore move together, in ONE commit:

1. the gitlink,
2. `commit:` in `contracts/<role>-pin.yaml`,
3. every `.github/workflows/*.yml` `<org>/<leg>/…@<sha>` reference to that leg.

`scripts/validate-pins.py` refuses if they disagree. This is a measured cost,
not a hypothesis: in the xFactory aggregation the same invariant went unwritten
for months, seven consecutive pin-syncs from 2026-08-25 moved the gitlink
alone, and `validate` was red on every pull request for a day — unnoticed
because the check runs on pull requests only, so `main` never reports it.

**What is digested.** `sorted-ls-tree-r-v1`: the sha256 of the sorted
`git ls-tree -r -z <commit>` listing — each record `<mode> SP <type> SP <oid>
TAB <path>` with the path unquoted, sorted bytewise, joined with LF. Not
`git archive`: its tar bytes carry a pax header naming the commit, uname/gname,
an mtime, and `export-ignore` handling from `.gitattributes`, so the same
commit can digest differently across git versions and platforms — which is
disqualifying for a number two machines must agree on. The `ls-tree` listing is
a complete content address (mode catches permission changes, oid catches
content, `160000 commit <oid>` catches a nested pin moving) and reproduces from
nothing but git's plumbing.

## Bootstrap is COPIED into the project, not fetched

`scripts/bootstrap.py` and the validators are copied into the assembly root by
the scaffold, so a scaffolded project is **self-contained**: it runs its own
gate in an organisation that forked this repository once and may never speak to
the upstream again. `contracts/shape-pin.yaml` records the openRepoShape commit
those copies came from AND a per-file sha256 of each copy, so "which
openRepoShape is this?" and "has anyone edited it since?" both have answers,
and editing a copy in place is reported as drift with the exit named (carry it
upstream; do not update the digest).

## Keeping a project's shape current

The copies are the trade: a project runs its own gate offline, and an upstream
FIX to a copied file reaches it never. On 2026-09-03 that bill came due — one
change to the assembly-root `validate.yml`, and both projects carrying the
shape were updated BY HAND: re-copy, recompute the file's `sha256` row, move
`commit` and `digests.tree_sha256`, mirror both into `project.yaml`, re-run the
validators. `update-shape.py` is that, as one command:

```sh
./update-shape.py check --root ../MedxEHR          # writes nothing
./update-shape.py apply --root ../MedxEHR --at <commit> --yes \
    --branch shape/update-<sha>                    # then open a pull request
```

`check` prints one verdict per file the pin names, and the verdict is the
product: **`unchanged`**, **`upstream-changed`** (the bytes differ between the
pinned commit and the target), **`locally-modified`** (the project's bytes
differ from the pinned digest — drift it introduced) or **`both`**. It exits 1
when there is anything to do, so it can be a scheduled job.

`apply` copies the `upstream-changed` files, rewrites `contracts/shape-pin.yaml`
(`commit`, `digests.tree_sha256` recomputed over the upstream tree under the
same `sorted-ls-tree-r-v1` definition, and every per-file row) and mirrors the
two fields into `project.yaml`. Then it runs the project's OWN
`validate-pins.py` and `validate-manifest.py`, and rolls every byte back if
either goes red.

**What it refuses, and why the refusals are the feature.** A `locally-modified`
file keeps its bytes and is named in a refusal unless the human passes
`--accept-local <path>` — recomputing that row silently would turn a drift
finding into a digest that agrees with the fork, which is the standard
recording the fork. A file changed on **both** sides is refused outright: two
edits to one file is a merge, and a merge is a human's judgement. So is a copy
that was never verbatim — `adopt-project.py` appends a `CONTRACTS_DIR` block to
an adopted Makefile, and copying the upstream bytes over that would delete it
without saying so.

**Only the pin's own rows are considered.** The file list is read from
`contracts/shape-pin.yaml` and never re-derived from this repository's copy
lists. An in-place adoption collides on `Makefile`, `README.md` and
`.gitignore`; the shape's copies land under `shape/`, a human merges them and
usually drops the rows. A file with no row is not a shape copy, and re-deriving
the list would resurrect one the project deliberately merged away.

`--upstream` takes a path to a clone (offline, and what the tests use) or an
`owner/repo` it bare-clones itself; it defaults to the repository the pin
names. `make bootstrap` prints one line when the upstream has moved past the
pin AND this machine can already tell offline — `SHAPE_UPSTREAM_PATH` points at
a clone, or a `.shape-upstream-tip` file carries a commit. It adds no network
call: a bootstrap that paused to ask GitHub a question would have made the
shape a dependency again.

## The degrade rule

`make bootstrap` looks for a wallet review-authority register at
`governance/review-authority/register.yaml` in the assembly root or any leg. If
it finds one it prints the grants naming this project. If it finds none it
prints exactly

    authority is not wallet-carried in this org

and continues. It never fails on that. An organisation that has not adopted
wallet-carried authority is not misconfigured, and a bootstrap that refused
there would have made the layout load-bearing again. The readout is reporting
only: a required check in the repository that owns the object is what confers.

## Layout of this repository

```
contracts/repository-naming.yaml  the four naming families, as data
contracts/path-classification.yaml  which leg a path belongs in, as data
scripts/repo_shape.py             shared helpers: YAML subset reader, digests
scripts/path_classify.py          the classifier over the path policy
scripts/shape_materialize.py      the ONE materializer, used by both tools
scripts/validate-repository-naming.py
setup.sh                          fork, clone, run one command
scaffold-project.py               creates the three repositories and the pins
adopt-project.py                  converts an EXISTING repository in place
update-shape.py                   re-syncs a project's copies and re-pins
bootstrap                         bootstrap a project that was never scaffolded
templates/assembly-root/          the skeleton materialized for <Project>
templates/spec-root/              the skeleton for <Project>-spec
templates/code-root/              the skeleton for <Project>-code
AGENTS.md                         the procedure an AI assistant follows
tests/                            pytest; scaffolds into bare repos in /tmp
```

**Python 3 standard library only.** No `pip`, no packaging, no
engineering-domain dependency — the shape must run where nothing can be
installed. `tests/test_repo_hygiene.py` enforces it.

## Licence

Apache-2.0. See `LICENSE`.
