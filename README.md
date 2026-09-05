# openRepoShape

**Status: ratified standard.** The mechanics of a project that spans several
repositories: what they are called, how they are pinned to each other, how one
clone brings the whole project down, and what an AI assistant does when a human
says "scaffold a new project with this shape".

GitHub has no folder that groups repositories, so a project spanning several of
them is held together by convention or by nothing. This repository is the
convention, as data and as running code.

Ruled by **Brett Heap on 2026-09-02**: the name `openRepoShape`, PUBLIC
visibility, Apache-2.0; and that the ASSEMBLY leg **is** the per-project root
repository — the one an engineer clones. The doctrine it serves was ratified
by Brett Heap on 2026-09-02 and lives in `opensoft/openxFactory` at
`docs/project-repo-schema.md`, which is what a project's `project.yaml`
records as the `reference:` the election followed; a project elected before
that date recorded the staged fragment's path, and that is a valid reference
for it. `scaffold-project.py` and `adopt-project.py` pick that default FROM
`--elected-on` — the staged path for an election dated before 2026-09-02, the
ratified one from that day on — so a back-dated project does not claim its
election followed a document that did not yet exist; `--reference` overrides
both.

**The shape is elective and confers nothing.** Electing it changes no gate, no
floor, no grant and no clearance eligibility. A one-repository project and a
three-repository project are reviewed identically, because the authority
travels in the grants rather than in the layout. Review lanes and
wallet-carried authority are OVERLAYS an org adds later; a project with no
overlays is fully conformant.

## Starting a project in a new organisation

No fork, no manual clone — one command:

```sh
curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup.sh \
    | bash -s -- --org <your-org> --project Atlas
```

An organisation whose policy blocks raw GitHub downloads can fetch the same
bytes through the API instead:

```sh
gh api repos/opensoft/openRepoShape/contents/setup.sh --jq .content \
    | base64 -d | bash -s -- --org <your-org> --project Atlas
```

The script clones this standard into a temporary directory (self-bootstrap:
see below), checks your machine, checks the three names, shows the plan and
asks once — then creates the three repositories, clones the assembly root and
bootstraps it, and removes the temporary directory. `--yes` skips the
question, and it REFUSES `--org opensoft` without `--allow-upstream-org`,
because that would scaffold three repositories into opensoft's own namespace.

Every scaffolded project pins `opensoft/openRepoShape` directly — the
**shape pin**, `contracts/shape-pin.yaml` — and `update-shape.py` reads
straight from upstream, so no per-organisation fork is needed to run this or
to stay current: a fork is only for contributing changes to the standard
itself.

### From a checkout (the developer path)

```sh
git clone https://github.com/opensoft/openRepoShape.git
cd openRepoShape
./setup.sh --project Atlas --org <your-org>
```

`setup.sh` behaves identically from here: preflight, naming, plan, one yes.
Run this way it also detects the organisation from a fork's `origin` remote,
if you have one; a plain clone of `opensoft/openRepoShape` itself is its own
`origin`, so that still needs an explicit `--org`.

### What setup.sh does

The same commands, in order, with no behaviour of its own (the first line
only runs in self-bootstrap mode, from the one-liner above):

```sh
git clone --depth 1 https://github.com/opensoft/openRepoShape.git <tmp-dir>
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

The five naming families live in `contracts/repository-naming.yaml`: neutral
products `open<Product>`, domain descendants `<Domainx><Product>`, installs
`<X>-Install`, project legs as above, and family holders (below). The leg suffixes are lowercase and
hyphenated precisely so they sit in a different visual class from every other
family, all of which are CamelCase words. Every repository of a project also
carries the GitHub topic `xf-project-<id>`.

### Reading private legs in CI: a GitHub App first, `SHAPE_LEGS_TOKEN` as fallback

The `validate` workflow's default `GITHUB_TOKEN` cannot clone a **private or
internal** leg as a submodule — this was the defect on the first real
adoption (MedxSoft/MedxEHR #7): `<Project>-spec`/`<Project>-code` were
private, and the required check was red on every pull request.

Ruled by **Brett Heap on 2026-09-04**: *move this to a GitHub App.* Preferred:
a dedicated App — owned by the estate's neutral organisation, permissions
**Contents: Read-only** and **Metadata: Read**, installed on each consuming
org with access to the leg repositories — mints a short-lived installation
token at run time instead of a standing PAT. Register it as two org secrets:

```sh
gh secret set SHAPE_LEGS_APP_ID --org <your-org> --body '<app id>'
gh secret set SHAPE_LEGS_APP_PRIVATE_KEY --org <your-org> < app-private-key.pem
```

Fallback, for an org without the App yet: a fine-grained **`SHAPE_LEGS_TOKEN`**
PAT, `contents:read` on the LEGS ONLY:

```sh
gh secret set SHAPE_LEGS_TOKEN --org <your-org> --body '<token>'
```

Both `scaffold-project.py` and `adopt-project.py execute` print a one-line
reminder — App first — when they create a private or internal leg.

**On the Free plan, use `--repo`, not `--org`.** GitHub delivers org secrets
only to PUBLIC repositories, so on a private one `secrets.SHAPE_LEGS_APP_ID`
is silently empty and `validate` goes GREEN with the pin check skipped. Set
both per repository, or upgrade to Team; the creating tools check and say so.

The root repository is always readable by the workflow's own default token,
so `actions/checkout` never carries a `token:` override. Putting a legs
credential there was itself the next defect, on the first real use of the PAT
(MedxSoft/MedxEHR and MedxSoft/MedxGlass, runs 33821509948 and 33821512605):
a token correctly scoped to `contents:read` on the legs alone cannot read
the root, so `actions/checkout` itself failed with a 403 before any check
ran. Whichever credential resolves is read only inside the guarded "fetch the
legs (submodules)" step, scoped to that step's `env:`, and used through a
`git -c url.<...>.insteadOf=<...>` rewrite covering both HTTPS and SSH leg
URLs — never persisted onto the root checkout.

`validate` tries the App first: a `mint a leg-reader token from the GitHub
App` step (`actions/create-github-app-token`, pinned by commit) runs when
both App secrets are present, scoped by `repositories:` to the legs
`.gitmodules` names that this repository's own owner also owns — an
installation token is per-owner, so a leg under a different owner is excluded
with a warning and can only be reached via `SHAPE_LEGS_TOKEN` — and falls back
to the PAT when the App is not configured. A configured App that fails to
mint is a misconfiguration, not a degrade, and fails the job outright, naming
both secrets and the required installation.

Without either credential the workflow still degrades instead of failing: it
checks out the root without submodules, attempts `git submodule update --init
--recursive` best-effort, and if that fails it still runs the naming and
manifest checks, skips `validate-pins.py` with a warning explaining why, and
fails outright only if a credential **is** configured (App or PAT) and the
fetch still failed — naming which source it used, meaning that credential
cannot read one of the LEG repositories, never the root, which no longer
depends on it — checked via job-level `env: SHAPE_LEGS_APP_SET` /
`SHAPE_LEGS_TOKEN_SET`, not `secrets` in the step `if:` (disallowed there;
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

**`validate-pins.py` rechecks the referent too, not only the declaration.**
Every `neutral_product_pins:` entry's `contracts/<product lowercased>-pin.yaml`
has its `commit`, `revision_kind` and `sorted-ls-tree-r-v1` digest recomputed
exactly the way `scaffold-project.py --pin` computed them: OFFLINE from a
local checkout when one can be found — `--pin-source [PRODUCT=]<path>`,
`SHAPE_PIN_SOURCE_<PRODUCT>` in the environment, or a checkout sitting beside
the assembly root and named for the pinned repository — else from `gh api`
when `gh` can read it. Neither answering is a named SKIP, never a finding and
never a failure: a project with no local checkout of its referent and no
network is not thereby lying about its descent. A digest that recomputes
differently, or a pin file the declaration names but that is not there, is
reported as drift like every other pin in this file.

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

### A leg with nothing in it is SEEDED, not extracted

A repository can honestly have nothing for one leg. Ruled by **Brett Heap on
2026-09-04**, of InkRouter's IRRS and IRSS: *"We do not have any code yet for
either service."* `git filter-repo` over an empty path list rewrites every
commit to nothing and leaves an empty HISTORY, which is not the same thing as
an empty repository, so a leg no plan entry assigns a path to is **seeded**
from `templates/<role>-root/` as one initial commit — the same bytes a fresh
scaffold writes — and the split mounts and pins it like an extracted one.

```sh
./adopt-project.py plan --source InkRouter/IRRS --project IRRS     --allow-empty-leg code
./adopt-project.py execute --plan adoption-plan.yaml --yes
```

The plan records `seeding.code.seeded_from_template: true` and the template it
would use; `check` WARNS and still passes, because a spec-only repository is a
legitimate thing to adopt; the verification table reads `code: 0 of N source
paths (seeded from template)` and still accounts for every source path by blob
sha. `execute` refuses without `--allow-empty-leg code`, in the plan or on its
own command line: a plan that lost its code paths to a bad edit looks
identical from here, so the consent is a human's word rather than an
inference. Where the recorded block and the entries disagree — somebody
answered an ambiguous path INTO the empty leg, which is the plan working — the
entries win and it is a note, not a refusal.

## Families: a holder for projects that ship separately

Ruled by **Brett Heap on 2026-09-04**, about InkRouter: *"InkRouter is a set of
microservices and they deploy separately as api's. so maybe they each need
their own assembly repo. So probably InkRouter is only something that can
download all the others easily? like a holder folder and some utilities for
the family of services. Then IRRS would be assembly and IRRS-spec and
IRRS-code."*

A **family** is a repository that pins other projects' **assembly roots** as
submodules under `members/` and carries the utilities to fetch and bootstrap
them all. It is **not a project**: no spec leg, no code leg, no `project.yaml`.
And, like everything else here, **it confers nothing** — a project in no family
is reviewed identically to one in this family.

| | one project | a family |
|---|---|---|
| ships as | one thing | several, separately |
| gate | one `validate` | one per member, plus the family's own |
| release | one | one per member |
| what the holder owns | the legs | nothing but pins and utilities |

**Use a family when the parts deploy separately.** Eight services that are
eight APIs are eight projects: folding them into one assembly root would give
them one gate, one release and one pin, which is the opposite of what "deploy
separately" means. **Use one project when the parts ship together** — that is
what the spec and code legs already are.

### The InkRouter example

Eight services, each its own project, one holder:

```
InkRouter/                      the family holder — family.yaml, members/, utilities
  members/IRRS   -> InkRouter/IRRS    assembly root, mounting IRRS-spec and IRRS-code
  members/IRSS   -> InkRouter/IRSS    assembly root, mounting IRSS-spec and IRSS-code
  …six more, added as they arrive
```

```sh
python3 scripts/family.py init --org InkRouter --family InkRouter     --reuse-empty-repo
python3 scripts/family.py add  --family-root ../InkRouter     --member InkRouter/IRRS
python3 scripts/family.py bump --family-root ../InkRouter     --member IRRS --to <40 hex>
python3 scripts/family.py remove --family-root ../InkRouter --member IRRS
```

`add`, `bump` and `remove` each write ONE commit, with explicit pathspecs,
moving the gitlink and `members[].pin` together — the same lockstep rule an
assembly root applies to its legs, and `scripts/validate-family.py` refuses
when they disagree. Each row also records the member's own `project.yaml`
`id`, so the validator can check the tree mounted at `members/<Project>` is
the project the row claims rather than merely a repository at the right
commit. **A family pins assembly roots, never legs**: adding `<Project>-spec`
is refused, because a leg has no `project.yaml` and belongs to its own root.

`make bootstrap` in the holder fetches every member and its legs — resolving
the same GitHub App or `SHAPE_LEGS_TOKEN` credential the workflow does,
because a member is a private assembly root that mounts two private legs of
its own — and then runs each member's own `make bootstrap`. `make validate`
runs the family validator and then each member's `make validate`. A member
that could not be fetched is reported and skipped, never a failure.

The holder carries the same COPY pin an assembly root does, so
`update-shape.py` re-syncs it the same way; it mirrors into `family.yaml`
instead of `project.yaml` and must leave `validate-family.py` green.

The name is the `family` form in `contracts/repository-naming.yaml`: one
CamelCase token, exactly an assembly root's rule, with **precedence below**
it, and DECLARED-ONLY. `InkRouter` is spelled like an assembly root and
`family.yaml` is the only thing that tells them apart, so the classifier
reports the holder form only when it is asked for (`--role family`). That is
what let a fifth family be added to a policy two live projects already carry a
copy of without changing any existing name's answer.

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

### Advancing a leg: `scripts/bump-leg.py`

Moving those three facts by hand is how they come apart, so one command moves
them together, run from a checkout of this standard:

```sh
python3 scripts/bump-leg.py --root <path-to-the-project> --leg spec \
    --to <40 hex commit>       # --dry-run prints the move and writes nothing
```

It fetches the commit into the leg, checks the leg out AT it, recomputes the
`sorted-ls-tree-r-v1` digest from the leg's own objects, rewrites `commit:`
and `digests.tree_sha256` in `contracts/<role>-pin.yaml`, rewrites every
`.github/workflows/*.yml` `@<sha>` naming THAT leg's repository — and none
naming anything else, `actions/checkout@<sha>` and the sibling leg included —
then runs the project's own `validate-pins.py` and `validate-manifest.py` and
commits ONCE with explicit pathspecs.

It REFUSES a `--to` that is not exactly 40 hex, a commit no branch of the
leg's remote contains (including one committed inside the mount and never
pushed — a pin the rest of the world cannot fetch is a root it cannot
bootstrap), a dirty root, a root standing on its own tracking branch (the next
step is a pull request, never a push to the default branch), and a validator
that goes red — rolling the pin, the workflow files, the leg's checkout and
the index back first, so a refusal leaves the tree exactly as it was found.
The leg is left DETACHED at the new commit; `make bootstrap` re-places it on
its tracking branch AT the new pin.

## Bootstrap is COPIED into the project, not fetched

`scripts/bootstrap.py`, the validators and `AGENTS-shape.md` are copied into the
assembly root by the scaffold, so a scaffolded project is **self-contained**:
it runs its own gate even though `setup.sh` only ever touched this standard
through a temporary directory it has since deleted. `contracts/shape-pin.yaml`
records the openRepoShape commit those copies came from AND a per-file sha256
of each copy, so "which openRepoShape is this?" and "has anyone edited it
since?" both have answers, and editing a copy in place is reported as drift
with the exit named (carry it upstream; do not update the digest).

**Why an agent file is one of the copies.** An agent working in a project
learns the shape's rules — advance a leg in ONE commit, never edit a pinned
file, never `--admin` — from a file that travels WITH the shape rather than
from whoever last remembered them. `AGENTS-shape.md` is therefore pinned like
the validators: "never edit a file with a row in `shape-pin.yaml`" is worthless
if the file carrying that rule can itself be edited. Being pinned is also why
it carries no project detail at all — one rendered byte and every project's
copy would digest differently. The project's own `AGENTS.md` and `CLAUDE.md`
are rendered and NOT pinned: the first line points at `AGENTS-shape.md`, and
the rest is the project's own, which an upstream fix must never overwrite.

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
finding into a digest that agrees with the project's own edited bytes, which
is the standard quietly recording someone's edit as if it were upstream's. A
file changed on **both** sides is refused outright: two
edits to one file is a merge, and a merge is a human's judgement. So is a copy
that was never verbatim — `adopt-project.py` appends a `CONTRACTS_DIR` block to
an adopted Makefile, and copying the upstream bytes over that would delete it
without saying so.

**Only the pin's own rows are RE-SYNCED.** The file list is read from
`contracts/shape-pin.yaml` and never re-derived from this repository's copy
lists. An in-place adoption collides on `Makefile`, `README.md` and
`.gitignore`; the shape's copies land under `shape/`, a human merges them and
usually drops the rows. A file with no row is not a shape copy, and re-deriving
the list would resurrect one the project deliberately merged away.

**A file the standard ADDS later is the other half, and it is named, never
assumed.** A pin can only record what existed the day it was written, so
`AGENTS-shape.md` — added to both root templates after MedxEHR, MedxGlass,
MedxScribe and the InkRouter members were cut — reached none of them. `check`
therefore also reports **`upstream-added`**: a path the UPSTREAM's copy lists
name AT THE TARGET COMMIT (read out of that commit's own
`shape_materialize.py`, so the answer is the target's lists and not this
checkout's) that the pin has no row for and the root has no file at. It counts
as something to do, so `check` still exits 1. `apply` writes NONE of them
unless `--add <path>` names one, per file: `apply --at <commit> --yes --add
AGENTS-shape.md` copies it, chmods it if the materializer would, appends its
`sha256` row and moves the pin, all inside the same transaction and rolled back
whole if a validator goes red. Without `--add` it says `not added; pass --add
<path>` and re-pins the rest. `--add` refuses a path that is already pinned,
one the target's lists do not name — and one the root ALREADY has a file at,
because two files with one name is a merge and this command copies bytes. A
project that declines an addition has no way to say so yet: it will be reported
by every `check` until it is taken or a file arrives at that path.

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
setup.sh                          self-bootstrap, scaffold, one command
scaffold-project.py               creates the three repositories and the pins
adopt-project.py                  converts an EXISTING repository in place
update-shape.py                   re-syncs a root's copies and re-pins
scripts/family.py                 creates a FAMILY holder and maintains its pins
scripts/bump-leg.py               advances ONE leg's pin, in one lockstep commit
bootstrap                         bootstrap a project that was never scaffolded
templates/assembly-root/          the skeleton materialized for <Project>
templates/family-root/            the skeleton for a FAMILY holder
templates/spec-root/              the skeleton for <Project>-spec
templates/code-root/              the skeleton for <Project>-code
templates/*/AGENTS-shape.md       the rules of the shape, for an agent (PINNED)
AGENTS.md                         the procedure an AI assistant follows
tests/                            pytest; scaffolds into bare repos in /tmp
```

**Python 3 standard library only.** No `pip`, no packaging, no
engineering-domain dependency — the shape must run where nothing can be
installed. `tests/test_repo_hygiene.py` enforces it.

## Licence

Apache-2.0. See `LICENSE`.
