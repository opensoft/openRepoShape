# AGENTS.md — scaffolding, adopting, updating, and declaring descent

You are an AI assistant in a checkout (usually a FORK) of `openRepoShape` and a
human has said "scaffold a new project with this shape", or "convert this
repository to it". This is the whole procedure; `README.md` says what the shape
is. Sections 1-3 scaffold a NEW project; the three after them cover an
EXISTING repository, a project that declares descent from a neutral product,
and a project whose copied shape files have fallen behind the upstream.

## The rules that outrank the rest

**Never create a repository without the human's explicit confirmation.** Run
`./setup.sh` WITHOUT `--yes` and let it ask. The human types `yes` at its
prompt; you never answer it for them.

**Never pass `--allow-upstream-org` on your own initiative.** It exists because
cloning `opensoft/openRepoShape` instead of forking it looks identical from
inside the directory. If setup.sh refuses on it, STOP and relay what it said —
the answer is almost always that they should fork, or pass `--org <their-org>`.
Pass it only if the human asks for it in those words.

**Never bypass an organisation ruleset.** A ruleset that refuses a direct push
to `main` is doing its job; the exits are in the scaffold's own failure message
(seed by pull request, or ask an operator with the bypass right). `--admin` is
not a remedy.

## 1. Confirm what you are about to do

| | | |
|---|---|---|
| org | detected from the fork's `origin` | `--org` overrides |
| `--project` | the assembly-root name, ONE CamelCase token | e.g. `Atlas` |
| `--id` | the lowercase project id | defaults to the project lowercased |
| `--visibility` | `private`, `public` or `internal` | defaults to `private` |
| `--elected-by` | the human electing the shape | defaults to the `gh` login |

Electing this shape is a human's decision. If they have not said which
visibility they want, ask — do not assume. `elected_by` records whose act it was.

## 2. Run setup.sh, without `--yes`

```sh
./setup.sh --project <Project> --visibility <private|public|internal> \
    --elected-by '<Name>'
```

It runs the preflight, detects the organisation, checks the three names against
the naming policy, prints the scaffold plan, and then asks. Show the human its
output verbatim — the plan especially — and let them answer its prompt. "Go
ahead" about something else is not a yes about this.

If it refuses, read the refusal: each one names what to run instead. Do not
retry with `--force`; there is none, deliberately.

## 3. It finishes the job

setup.sh clones the new assembly root beside the fork, runs `make bootstrap` in
it, and prints the clone path, the three repository URLs and the next commands.
Relay that block. Say that bootstrap put each leg on its tracking branch AT the
pinned commit, and that the line `authority is not wallet-carried in this org`
is a report and not a fault.

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
5. `apply` runs the project's own `validate-pins.py` and `validate-manifest.py`
   and rolls every byte back if either goes red. Land it as a pull request;
   never suggest a push to the default branch.

## What you must not tell them

That the shape confers anything. Electing it changes no gate, no floor, no
grant and no clearance eligibility; a one-repository project is reviewed
identically. If you are asked to make `role: spec` mean "spec authority lives
here", say no: that turns a layout into a governance boundary, which is the
one thing this standard exists to prevent.

## Testing your changes to this repository

`python3 -m pytest tests -q`. The suite scaffolds into bare repositories in a
temporary directory. Never test by creating a real GitHub repository.
