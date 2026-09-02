# AGENTS.md — scaffolding a new project with this shape

You are an AI assistant in a checkout (usually a FORK) of `openRepoShape` and a
human has said "scaffold a new project with this shape". This is the whole
procedure; `README.md` says what the shape is.

## The rule that outranks the rest

**Never create a repository without the human's explicit confirmation of the
plan, and never bypass an organisation ruleset.** A ruleset that refuses a
direct push to `main` is doing its job; the exits are in the scaffold's own
failure message (seed by pull request, or ask an operator with the bypass
right). Working around one is never the answer, and `--admin` is not a remedy.

## 1. Confirm five things, out loud, before touching anything

| | | |
|---|---|---|
| `--org` | the GitHub organisation | e.g. `opensoft` |
| `--project` | the assembly-root name, ONE CamelCase token | e.g. `Atlas` |
| `--id` | the lowercase project id | defaults to the project lowercased |
| `--visibility` | `private` or `public` | defaults to `private` |
| `--elected-by` | the human electing the shape | defaults to `git config user.name` |

Electing this shape is a human's decision. If they have not said which
visibility they want, ask — do not assume. `elected_by` records whose act it was.

## 2. Check the names before anything exists

```sh
python3 scripts/validate-repository-naming.py --explain \
    <Project> <Project>-spec <Project>-code
```

Exit 0 means all three classify as project legs. Exit 1 means at least one
matches no family — fix the name, do not proceed. A naming mistake caught here
costs a message; caught later it costs three repositories and a rename.

## 3. Show the plan and get an explicit yes

```sh
python3 scaffold-project.py --org <org> --project <Project> \
    --id <id> --visibility <private|public> --elected-by '<Name>' --dry-run
```

Print the plan output verbatim. Say plainly: this will create THREE
repositories in `<org>`. Wait for the human to say yes. "Go ahead" about
something else is not a yes about this.

## 4. Run it for real

Remove `--dry-run`. Nothing else changes. If it refuses, read the refusal: it
names the exact command that failed and what to run instead. Do not retry with
`--force` — there is none, deliberately.

## 5. Hand over the next steps

```sh
git clone --recurse-submodules https://github.com/<org>/<Project>.git
cd <Project>
make bootstrap
```

Tell the human what `make bootstrap` does: it puts each leg on its tracking
branch AT the pinned commit, runs the three neutral validators, and prints any
wallet-carried review authority — or the line `authority is not wallet-carried
in this org`, which is a report and not a fault.

## What you must not tell them

That the shape confers anything. Electing it changes no gate, no floor, no
grant and no clearance eligibility; a one-repository project is reviewed
identically. If you are asked to make `role: spec` mean "spec authority lives
here", say no: that turns a layout into a governance boundary, which is the
one thing this standard exists to prevent.

## Testing your changes to this repository

`python3 -m pytest tests -q`. The suite scaffolds into bare repositories in a
temporary directory. Never test by creating a real GitHub repository.
