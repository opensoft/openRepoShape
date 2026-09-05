# AGENTS.md — scaffolding, adopting, updating, advancing a leg, families

You are an AI assistant a human has asked to "scaffold a new project with
this shape", or "convert this repository to it", or "put these services in a
family". This is the whole procedure; `README.md` says what the shape is.
Sections 1-3 scaffold a NEW project; the ones after them cover an EXISTING
repository (including one with no code yet), a project that declares descent
from a neutral product, a project whose copied shape files have fallen behind
the upstream, a leg that has moved on, and a FAMILY holder.

## The rules that outrank the rest

**Never create a repository without the human's explicit confirmation.** Run
`./setup.sh` (or the one-liner) WITHOUT `--yes` and let it ask. The human
types `yes` at its prompt; you never answer it for them.

**Never pass `--allow-upstream-org` on your own initiative.** It guards only
`--org opensoft` itself — scaffolding into opensoft's own namespace, the
upstream owner of openRepoShape. If setup.sh refuses because the organisation
you were given resolves to opensoft, STOP and relay what it said; the fix is
almost always an explicit `--org <their-org>`. Pass `--allow-upstream-org`
only if the human asks for it in those words.

**Never bypass an organisation ruleset.** A ruleset that refuses a direct push
to `main` is doing its job; the exits are in the scaffold's own failure message
(seed by pull request, or ask an operator with the bypass right). `--admin` is
not a remedy.

## 1. Confirm what you are about to do

| | | |
|---|---|---|
| `--org` | the organisation to scaffold into | REQUIRED — there is no fork `origin` to read it from |
| `--project` | the assembly-root name, ONE CamelCase token | e.g. `Atlas` |
| `--id` | the lowercase project id | defaults to the project lowercased |
| `--visibility` | `private`, `public` or `internal` | defaults to `private` |
| `--elected-by` | the human electing the shape | defaults to the `gh` login |

Electing this shape is a human's decision. If they have not said which
visibility they want, ask — do not assume. `elected_by` records whose act it was.

## 2. Run the one-liner, without `--yes`

```sh
curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup.sh \
    | bash -s -- --org <org> --project <Project> \
      --visibility <private|public|internal> --elected-by '<Name>'
```

`openRepoShape <Project> --org <org> --visibility <…> --elected-by '<Name>'`
is the same run through the installed command, still without `--yes`.

On Windows without WSL2, `Invoke-WebRequest https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup-project.py -OutFile setup-project.py`
then `py setup-project.py <Project> --org <org> --visibility <…> --elected-by '<Name>'`
is the same run again — two commands because a piped script cannot ask — still without `--yes`.

Already standing in a checkout of openRepoShape? Run `./setup.sh` the same
way, still with the explicit `--org` — there is no fork to detect one from.
Either form runs the preflight, checks the three names against the naming
policy, prints the scaffold plan, and then asks. Show the human its output
verbatim — the plan especially — and let them answer its prompt. "Go ahead"
about something else is not a yes about this.

If it refuses, read the refusal: each one names what to run instead. Do not
retry with `--force`; there is none, deliberately.

## 3. It finishes the job

It clones the new assembly root, runs `scripts/bootstrap.py` in it (what
`make bootstrap` runs), and prints the clone path, the three repository URLs
and the next commands. Relay that block. Say that bootstrap put each leg on
its tracking branch AT the pinned commit, and that the line `authority is not
wallet-carried in this org` is a report and not a fault. The new project
carries `AGENTS-shape.md` at its assembly root — the rules of its shape,
copied and digest-pinned — and you read that before touching the project.

## If setup.sh cannot be used

The same steps by hand, in order: `validate-repository-naming.py --explain` on
the three names, `scaffold-project.py --dry-run`, an explicit human yes,
`scaffold-project.py` for real, then `git clone --recurse-submodules` and
`make bootstrap`. README's "What setup.sh does" carries the exact commands.

## Adopting an existing repository

`adopt-project.py` converts a repository that already exists, IN PLACE: it
keeps its name, its identity and its full history and becomes the assembly
root, and the two legs are new repositories extracted with `git filter-repo`
(a hard dependency; the preflight prints the install command). Seven steps, in
order, and step 4 is the one you must not skip.

```sh
./adopt-project.py plan --source <org/repo|path> --project <Project>
# 2. answer every `review_required: true` entry IN THE PLAN
./adopt-project.py check --plan adoption-plan.yaml
# 4. show the human the plan and the follow-ups; get an explicit yes
./adopt-project.py execute --plan adoption-plan.yaml --yes
```

2. **You resolve the questions, in writing, in the plan.** Each unresolved
   entry carries a `question:`. Set `leg:` to `spec`, `code`, `root` or `drop`
   AND add a `resolution:` line saying why — read the repository to answer it
   (does the specification cite `examples/golden-run/`, or do the tests?). An
   answer with no reason beside it is a guess that will be read as a finding.
   Never delete an entry to make the question go away: `check` refuses a path
   that no entry covers, and it is right to.
4. **Show the human the plan and the follow-ups and let them say yes.** The
   follow-ups are code changes the split MAKES NECESSARY — the harness that
   reads `contracts/` from beside it will read it across the root mount — and
   `execute` does not make them. Do not pass `--yes` on your own initiative;
   it is the human's word, not your convenience.
7. **Read the verification table back to them.** It accounts for every source
   path at the source commit, by blob sha, in exactly one of {spec leg, code
   leg, root tree} or as `drop`. If it exits non-zero, STOP and relay it: the
   source is untouched — nothing is deleted, `main` is where it was, the split
   is on a branch — so the exit is to fix the plan and re-run into fresh legs.

`execute` opens a pull request, because these organisations are pull-request
only. Never suggest a direct push to the default branch, and never `--admin`.

### Adopting a repository that has NO code yet (or no spec)

A leg no plan entry assigns a path to is SEEDED from
`templates/<role>-root/`, not extracted — `git filter-repo` over an empty
path list yields an empty history, not an empty repository. `plan` and
`check` both WARN; `check` still passes, because a spec-only repository is a
legitimate thing to adopt.

```sh
./adopt-project.py plan --source <org>/<Repo> --project <Project> \
    --allow-empty-leg code
```

1. **Read the warning back to the human and get their word for the flag.**
   `execute` refuses without `--allow-empty-leg <leg>` and it is right to: a
   plan that lost its code paths to a bad edit is indistinguishable from a
   repository that has no code. Do not pass it because the tool asked for it;
   pass it because the human confirmed the repository genuinely has none.
2. Everything else is unchanged, step 7 included: the verification table
   reads `code: 0 of N source paths (seeded from template)` and still
   accounts for every source path by blob sha.

## Scaffolding a project that DECLARES descent

`MedxGlass` descends from `openGlass` only if it PINS it (2026-09-02). Pass
the pin and the scaffold records the descent and still gives it two legs:

```sh
./scaffold-project.py --org MedxSoft --project MedxGlass \
    --pin openGlass@<40 hex commit>
```

The pin needs a full 40-character commit — a tag can be moved and a commit
cannot — and writes `contracts/openglass-pin.yaml` beside the manifest. Do NOT
declare a pin the human has not asked for: a declaration is a claim about what
this project descends from, and inventing one puts a false fact in their tree.
With no pin, `MedxGlass` is an ordinary assembly root and the manifest records
the overlap. If the repository they name already exists and is EMPTY, add
`--reuse-empty-repo`; if it has commits, it is a live repository and adopt is
the tool, not scaffold.

## Updating a project's shape

An upstream fix to a COPIED file — the three validators, `bootstrap.py`, the
Makefile, `validate.yml` — reaches no project by itself, because the project
holds copies rather than a mount. `update-shape.py` re-copies and re-pins. It
never merges, and every refusal below is deliberate.

```sh
./update-shape.py check --root <path-to-the-project>
# 2. show the human the per-file verdicts and get an explicit yes
./update-shape.py apply --root <path> --at <commit> --yes \
    --branch shape/update-<sha>
git -C <path> push -u origin shape/update-<sha>   # then open a pull request
```

1. **`check` first, always.** It writes nothing and prints one verdict per
   PINNED file: `unchanged`, `upstream-changed`, `locally-modified` (the
   project edited its own copy) or `both`. A file with no row in
   `contracts/shape-pin.yaml` is not a shape copy and is none of your business
   — an adopted project merged some of them away on purpose.
2. **Show the human the verdicts and let them say yes.** Re-pinning records
   which openRepoShape this project is a copy of. Do not pass `--yes` on your
   own initiative.
3. **Never pass `--accept-local` to make a refusal go away.** It re-pins a
   locally edited file FROM THE PROJECT'S OWN BYTES, which makes the drift
   `validate-pins.py` reports today invisible. Whether the project keeps its
   edit is the human's decision; the other two exits are to revert it or to
   carry it upstream.
4. **`both` is a merge, and the tool refuses it.** Merge by hand, commit, then
   re-run with `--accept-local <path>` on the file you merged.
5. **`upstream-added` is a file the STANDARD gained since the pin, and `--add`
   is per file.** Report the paths `check` names; pass `--add <path>` only for
   a file the human has said to take, and never to quiet the report. Without
   it `apply` writes none of them and says so.
6. `apply` runs the project's own `validate-pins.py` and `validate-manifest.py`
   and rolls every byte back if either goes red. Land it as a pull request;
   never suggest a push to the default branch.

## Advancing a leg

A leg's gitlink, `contracts/<role>-pin.yaml` and every workflow `@<sha>` that
names it are ONE invariant, and the project's `validate-pins.py` refuses when
they disagree. `bump-leg.py` moves all three in one commit; run it from a
checkout of this standard, pointed at the project.

```sh
python3 scripts/bump-leg.py --root <path> --leg spec --to <40 hex> --dry-run
# 1. show the human the printed `old -> new` line
python3 scripts/bump-leg.py --root <path> --leg spec --to <40 hex>
git -C <path> push -u origin <branch>   # then open a pull request
```

1. **`--dry-run` first, and show the human the `old -> new` line it prints.**
   That line, the digest under it and the workflow files it names are the
   whole change. A bump nobody read is a pin nobody chose.
2. **Never edit `contracts/<role>-pin.yaml` by hand to make the validator
   agree.** The digest is RECOMPUTED from the leg's own objects, never
   adjusted to fit; a hand-written one turns the check into a formality and
   hides exactly the drift it exists to find.
3. **The commit is made on a BRANCH and lands as a pull request.** The tool
   refuses to commit onto the tracking branch for that reason. Never suggest
   a direct push to the default branch, and never `--admin`.
4. **A refusal is not something to work around.** A commit no branch of the
   leg's remote contains must be PUSHED, not pinned — a pin the rest of the
   world cannot fetch is a root it cannot bootstrap. A red validator has
   already been rolled back; the finding above it is the thing to fix.
5. The leg is left DETACHED at the new commit. `make bootstrap` in the root
   re-places it on its tracking branch AT the new pin; say so when you relay
   the result.

## Creating a family, and adding a member

A FAMILY is a holder that pins other projects' ASSEMBLY ROOTS as submodules
under `members/`. It is not a project — no legs — and membership confers
nothing. Use one when the parts DEPLOY SEPARATELY; one project is what parts
that ship together already are.

```sh
python3 scripts/family.py init --org <org> --family <Name> [--reuse-empty-repo]
python3 scripts/family.py add  --family-root <path> --member <org>/<Project>
python3 scripts/family.py bump --family-root <path> --member <Project> --to <sha>
```

1. **`init` creates a repository, so the human must say so first.** There is
   no prompt here — `family.py` is not `setup.sh` — which makes it your job
   to get an explicit yes before you run it, and to run `--dry-run` first and
   show them the plan. If `<org>/<Name>` already exists and is EMPTY, add
   `--reuse-empty-repo`; if it has commits, stop and ask.
2. **A family pins ASSEMBLY ROOTS, never legs.** `--member <org>/<Project>`,
   never `<Project>-spec`. The tool refuses a leg, and the refusal is
   correct: a leg has no `project.yaml` and belongs to its own root.
3. **Each of `add`, `bump` and `remove` writes ONE commit** moving the
   gitlink and the pin together. Land it as a pull request; never suggest a
   push to the default branch. Do not hand-edit `family.yaml`'s `members:`
   block — the tool rewrites it wholesale.
4. **The member must be scaffolded or adopted FIRST.** A family cannot make a
   project out of a repository; it can only pin one that already is.
5. `update-shape.py` updates a family root exactly as it updates a project,
   and the same four refusals apply. It mirrors into `family.yaml`.

## What you must not tell them

That the shape confers anything — or that membership of a family does.
Electing either changes no gate, no floor, no grant and no clearance
eligibility; a one-repository project in no family is reviewed identically. If you are asked to make `role: spec` mean "spec authority lives
here", say no: that turns a layout into a governance boundary, which is the
one thing this standard exists to prevent.

## Testing your changes to this repository

`python3 -m pytest tests -q`. The suite scaffolds into bare repositories in a
temporary directory. Never test by creating a real GitHub repository.
