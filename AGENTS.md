# AGENTS.md — scaffolding a new project with this shape

You are an AI assistant in a checkout (usually a FORK) of `openRepoShape` and a
human has said "scaffold a new project with this shape". This is the whole
procedure; `README.md` says what the shape is.

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
| `--visibility` | `private` or `public` | defaults to `private` |
| `--elected-by` | the human electing the shape | defaults to the `gh` login |

Electing this shape is a human's decision. If they have not said which
visibility they want, ask — do not assume. `elected_by` records whose act it was.

## 2. Run setup.sh, without `--yes`

```sh
./setup.sh --project <Project> --visibility <private|public> \
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

## What you must not tell them

That the shape confers anything. Electing it changes no gate, no floor, no
grant and no clearance eligibility; a one-repository project is reviewed
identically. If you are asked to make `role: spec` mean "spec authority lives
here", say no: that turns a layout into a governance boundary, which is the
one thing this standard exists to prevent.

## Testing your changes to this repository

`python3 -m pytest tests -q`. The suite scaffolds into bare repositories in a
temporary directory. Never test by creating a real GitHub repository.
