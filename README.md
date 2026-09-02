# openRepoShape

Status: staged. The repository name and public visibility were ruled by Brett
Heap on 2026-09-02; the standard it will hold is still a staged topic in
`opensoft/openxFactory` at `ideation/staging/project-repo-schema/`. Nothing
here is ratified yet.

## What this repository will hold

- `contracts/repository-naming.yaml` — the naming convention as data: neutral
  products (`open<Product>`), domain descendants (`<Domainx><Product>`),
  installs (`<X>-Install`), and project legs (`<Project>`, `<Project>-spec`,
  `<Project>-code`).
- `templates/` — the assembly-root skeleton: README, `.gitmodules` stub,
  per-leg digest pin files, a self-describing `project.yaml` manifest, and the
  lockstep pin validator.
- `scaffold-project.py` — creates the three repositories in an org, pushes
  their initial trees, and pins the legs into the assembly root.
- `bootstrap` — the one command an engineer runs after
  `git clone --recurse-submodules`.
- `AGENTS.md` — the procedure an AI assistant follows to scaffold a project.

## How it is consumed

Fork this repository into your org (a fork, not a GitHub template copy, so
the upstream link is kept and shape updates can be pulled). Run the scaffold
from the fork. `opensoft/openxFactory` pins this repository by commit and
digest; nobody copies it.

The shape is elective and confers no authority. A project that declines it is
not less governed; a project that adopts it earns no additional clearance.
Review lanes and wallet-carried authority are overlays an org may add later.

## Licence

Apache-2.0. See `LICENSE`.
