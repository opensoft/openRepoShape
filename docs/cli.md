# The openRepoShape CLI, flag by flag

**GENERATED** by `scripts/render-cli-reference.py`; do not edit. The test that keeps it honest is `tests/test_cli_reference.py`.

This is the flag-level reference. `AGENTS.md` is the procedure — which act to
perform, in what order, and what must never be done on your own initiative —
and it outranks this file wherever the two meet: a flag documented here is not
permission to pass it. `README.md` is the standard itself. Read this one when
you know which act you are performing and need the exact spelling.

Two rules the help texts below do not repeat, because they are about all of
them at once. Nothing here is run with `--yes` on an assistant's own
initiative, and a refusal is never worked around: each one names the command
to run instead, and running THAT is the whole of the fix.

Each block is the tool's own `--help`, captured verbatim from stdout and
stderr with four normalisations, so that regenerating on another machine
produces the same bytes: the terminal width is pinned at 80 columns;
trailing whitespace and CRLF line endings are removed; the `usage:` block is
re-wrapped from its own tokens, because argparse breaks that one line in
different places on different Python versions; and a path under the generating
machine's home directory would be replaced with a placeholder — no tool prints
one today, and the generator refuses to write this file if one ever appears.

## The tools, and what each one is for

**Run from a checkout of the standard**

| tool | what it is for |
| --- | --- |
| [`setup.sh`](#setupsh) | The front door for a NEW project: preflight, the naming check, the plan, one typed `yes`, then three repositories. A SHIM over `setup-project.py`, so the help below is that tool's own. |
| [`openRepoShape`](#openreposhape) | The same front door as an installed command, plus `--install` (itself, into `~/.local/bin`), `--preflight` (this MACHINE) and `--doctor` (one REPOSITORY). |
| [`setup-project.py`](#setup-projectpy) | THE FLOW itself, and the only way in on a machine with no bash. |
| [`scaffold-project.py`](#scaffold-projectpy) | Creates the three repositories and writes the pins. What the front door calls once the human has said yes. |
| [`adopt-project.py`](#adopt-projectpy) | Converts an EXISTING repository into the shape, in place, keeping its name and its history. |
| [`update-shape.py`](#update-shapepy) | Re-copies a project's shape files from this standard and re-pins them. It never merges. |
| [`shape-doctor.py`](#shape-doctorpy) | Answers ONE question about ONE repository: is it compliant with this shape, and what is missing. Writes nothing. |
| [`bootstrap`](#bootstrap) | Runs this standard's canonical bootstrap against a project that was never scaffolded, so a repository that elected nothing still has the command. |
| [`scripts/bump-leg.py`](#scriptsbump-legpy) | Advances ONE leg's pin — the gitlink, `contracts/<role>-pin.yaml` and every workflow `@<sha>` — in one lockstep commit. |
| [`scripts/family.py`](#scriptsfamilypy) | Creates a FAMILY holder and maintains its member pins. |
| [`scripts/validate-repository-naming.py`](#scriptsvalidate-repository-namingpy) | Classifies repository names against `contracts/repository-naming.yaml`, and explains which form won. |

**Shipped into every project (copied, digest-pinned)**

| tool | what it is for |
| --- | --- |
| [`templates/assembly-root/scripts/bootstrap.py`](#templatesassembly-rootscriptsbootstrappy) | The one command after `git clone --recurse-submodules`: places each leg on its tracking branch AT the pinned commit. What `make bootstrap` runs. |
| [`templates/assembly-root/scripts/validate-manifest.py`](#templatesassembly-rootscriptsvalidate-manifestpy) | The project's own `project.yaml` validator: the manifest against the naming and path policies it was cut from. |
| [`templates/assembly-root/scripts/validate-pins.py`](#templatesassembly-rootscriptsvalidate-pinspy) | The project's own LOCKSTEP validator: the gitlink, the pin and the workflow references must agree, and every digest must recompute. |
| [`templates/family-root/scripts/bootstrap.py`](#templatesfamily-rootscriptsbootstrappy) | The holder's own bootstrap: mounts every member at its pin and runs each member's. |
| [`templates/family-root/scripts/siblings.py`](#templatesfamily-rootscriptssiblingspy) | Places the WORKSTATION layout: every member cloned BESIDE the holder, on its tracking branch. It moves nothing and overwrites nothing. |
| [`templates/family-root/scripts/validate-family.py`](#templatesfamily-rootscriptsvalidate-familypy) | The holder's own `family.yaml` validator: the members, their pins and its shape copies. |

## Run from a checkout of the standard

Every command below is typed at the root of a clone of this repository. `openRepoShape` is also the one file `--install` places on `PATH`, and is the only entry point that needs no checkout at all.

### `setup.sh`

`./setup.sh --help`:

```
usage: setup-project.py [<Project>] [options] [-- <extra scaffold flags>]

  <Project>               the assembly-root name, as a positional. Exactly
                          the same thing as --project; give one or the other.
  --project <Project>     the assembly-root name: ONE CamelCase token, no
                          hyphen, underscore, dot or space. Prompted for when
                          omitted and a terminal is attached.
  --id <id>               lowercase project id      (default: project lowercased)
  --name "<Display>"      display name              (default: the project name)
  --visibility private|public|internal              (default: private)
  --elected-by "<Name>"   who is electing the shape (default: your gh login)
  --family <Family>       the FAMILY HOLDER this project joins: one CamelCase
                          token, the holder's own name. The clone lands at
                          <into>/<Family>/<Project> instead of
                          <into>/<Project>, and <into>/<Family>/ is created if
                          it is not there. Already standing IN the family
                          folder? Then it lands at <into>/<Project>: a family
                          is never nested inside a family. It records NOTHING
                          in the project - membership is recorded only in the
                          holder's family.yaml, and the next commands name the
                          `family.py add` that writes it.
  --into <dir>            PARENT directory for the clone (default: ..; in
                          self-bootstrap mode, the directory you ran this
                          from), so the clone lands at <dir>/<Project>
  --org <org>             override the detected organisation. REQUIRED when
                          run outside a checkout of openRepoShape
                          (self-bootstrap mode): there is no origin to read it
                          from.
  --allow-upstream-org    permit `--org opensoft` itself: opensoft is the
                          upstream owner of openRepoShape, and almost never
                          what you meant to scaffold into.
  --shape-ref <ref>       self-bootstrap mode only: clone this commit or tag
                          of the standard instead of its default branch.
  --keep-shape-checkout   self-bootstrap mode only: do not delete the
                          temporary checkout on exit; print its path instead.
  --yes                   skip the confirmation prompt. It answers the ONE
                          question about creating three repositories, and
                          never an offer to install something.
  --preflight             check this machine and stop: the preflight and
                          the offers it makes, nothing else. Exit 0 when
                          everything is there, 1 when it is not. Creates
                          nothing, and needs no <Project> and no --org.
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Set $OPENREPOSHAPE_REPO to clone a fork or mirror in self-bootstrap mode
instead of opensoft/openRepoShape.

Anything after `--` is passed straight through to scaffold-project.py.
```

### `openRepoShape`

`openRepoShape --help`:

```
openRepoShape --install            install (or update) this command into ~/.local/bin
openRepoShape --preflight          check this MACHINE and stop; creates nothing
openRepoShape --doctor [<path>]    diagnose a REPOSITORY against this standard
openRepoShape <Project> [--org <org>] [setup-project.py options] [-- <scaffold flags>]
openRepoShape --help | --version

Those four lines are the whole command: install it, check the machine you are
on, diagnose a repository, scaffold a project. Run with NO arguments it prints
this and exits 1, because a bare run has nothing to do.

<Project> is the assembly-root name, ONE CamelCase token (e.g. Atlas); omit it
and setup.sh asks, if a terminal is attached. `--org` comes from that flag,
else $OPENREPOSHAPE_ORG, else a prompt — it is NEVER defaulted. Every other
argument reaches setup.sh unchanged: --visibility, --elected-by, --family,
--into, --yes, --local-remote-dir, and anything after `--`, which setup.sh
hands on to scaffold-project.py. `./setup.sh --help` prints setup-project.py's
usage, which lists them all.

`--install` places ONE command, and it is this one file:

  openRepoShape <Project> --org <org>    scaffold a project

The estate verbs are not here. `park` and `resume` — commit, push and RECORD an
estate's open features, then rebuild them on the next workstation — are
opensoft/openRepoTools', and its own installer places them:

  curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoTools/main/openRepoTools | bash -s -- --install

  $OPENREPOSHAPE_REPO       owner/name to fetch from (default opensoft/openRepoShape)
  $OPENREPOSHAPE_REF        the ref to fetch it at   (default main)
  $OPENREPOSHAPE_ORG        the organisation, when --org is not given
  $OPENREPOSHAPE_BIN_DIR    where --install puts it  (default ~/.local/bin)
  $OPENREPOSHAPE_SETUP_SH   run this setup.sh on disk instead of fetching one

`--doctor [<path>]` runs `shape-doctor.py` over <path> (default `.`) and prints
one row per check and ONE verdict: COMPLIANT, COMPLIANT SHAPE BEHIND, DRIFTED,
INVALID or NOT A SHAPE ROOT. It writes nothing, and every finding names the
command that fixes it. Exit 0 compliant, 1 findings, 2 not a shape root, 3
usage. Run beside a checkout of the standard it uses that one; run from
anywhere else it clones the standard into a temporary directory first.

`--preflight` is the MACHINE check -- it was spelled `--doctor` until
2026-09-10, and the name moved to the repository diagnosis above, which is
what a person means by a doctor.
```

### `setup-project.py`

`python3 setup-project.py --help`:

```
usage: setup-project.py [<Project>] [options] [-- <extra scaffold flags>]

  <Project>               the assembly-root name, as a positional. Exactly
                          the same thing as --project; give one or the other.
  --project <Project>     the assembly-root name: ONE CamelCase token, no
                          hyphen, underscore, dot or space. Prompted for when
                          omitted and a terminal is attached.
  --id <id>               lowercase project id      (default: project lowercased)
  --name "<Display>"      display name              (default: the project name)
  --visibility private|public|internal              (default: private)
  --elected-by "<Name>"   who is electing the shape (default: your gh login)
  --family <Family>       the FAMILY HOLDER this project joins: one CamelCase
                          token, the holder's own name. The clone lands at
                          <into>/<Family>/<Project> instead of
                          <into>/<Project>, and <into>/<Family>/ is created if
                          it is not there. Already standing IN the family
                          folder? Then it lands at <into>/<Project>: a family
                          is never nested inside a family. It records NOTHING
                          in the project - membership is recorded only in the
                          holder's family.yaml, and the next commands name the
                          `family.py add` that writes it.
  --into <dir>            PARENT directory for the clone (default: ..; in
                          self-bootstrap mode, the directory you ran this
                          from), so the clone lands at <dir>/<Project>
  --org <org>             override the detected organisation. REQUIRED when
                          run outside a checkout of openRepoShape
                          (self-bootstrap mode): there is no origin to read it
                          from.
  --allow-upstream-org    permit `--org opensoft` itself: opensoft is the
                          upstream owner of openRepoShape, and almost never
                          what you meant to scaffold into.
  --shape-ref <ref>       self-bootstrap mode only: clone this commit or tag
                          of the standard instead of its default branch.
  --keep-shape-checkout   self-bootstrap mode only: do not delete the
                          temporary checkout on exit; print its path instead.
  --yes                   skip the confirmation prompt. It answers the ONE
                          question about creating three repositories, and
                          never an offer to install something.
  --preflight             check this machine and stop: the preflight and
                          the offers it makes, nothing else. Exit 0 when
                          everything is there, 1 when it is not. Creates
                          nothing, and needs no <Project> and no --org.
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Set $OPENREPOSHAPE_REPO to clone a fork or mirror in self-bootstrap mode
instead of opensoft/openRepoShape.

Anything after `--` is passed straight through to scaffold-project.py.
```

### `scaffold-project.py`

`python3 scaffold-project.py --help`:

```
usage: scaffold-project.py [-h] --org ORG --project PROJECT [--id ID]
                           [--name NAME]
                           [--visibility {private,public,internal}]
                           [--pin-owner PIN_OWNER] [--elected-by ELECTED_BY]
                           [--elected-on ELECTED_ON] [--reference REFERENCE]
                           [--tracking-branch TRACKING_BRANCH]
                           [--spec-path SPEC_PATH] [--code-path CODE_PATH]
                           [--dry-run] [--local-remote-dir LOCAL_REMOTE_DIR]
                           [--no-push] [--reuse-empty-repo]
                           [--pin openProduct@COMMIT]
                           [--referent-chain openLayer,openProduct]
                           [--pin-source PIN_SOURCE] [--work-dir WORK_DIR]

Create a project's three repositories in the shape this standard describes.

options:
  -h, --help            show this help message and exit
  --org ORG
  --project PROJECT     the assembly-root name, e.g. Atlas
  --id ID               lowercase project id
  --name NAME           display name
  --visibility {private,public,internal}
                        default: private for a fresh scaffold; with --reuse-
                        empty-repo and an existing assembly root, the two new
                        legs INHERIT that root's own visibility instead (a
                        mismatch with an explicit --visibility is a warning,
                        not a refusal)
  --pin-owner PIN_OWNER
                        the organisation an UNQUALIFIED --pin name resolves
                        under (default: opensoft, where every neutral
                        open<Product> lives — never this scaffold's own
                        --org). Name the owner in --pin itself
                        (owner/openProduct@<sha>) to override it for one pin
                        without changing this default for the others.
  --elected-by ELECTED_BY
  --elected-on ELECTED_ON
                        YYYY-MM-DD
  --reference REFERENCE
                        the document the election followed. Default:
                        openxFactory's ratified docs/project-repo-schema.md
                        for an election on or after 2026-09-02, and the staged
                        fragment it was ratified from for one dated earlier —
                        so --elected-on chooses it, and a back-dated project
                        does not claim it followed a document that did not
                        exist yet.
  --tracking-branch TRACKING_BRANCH
  --spec-path SPEC_PATH
  --code-path CODE_PATH
  --dry-run
  --local-remote-dir LOCAL_REMOTE_DIR
                        create bare repositories here instead of calling `gh
                        repo create` (the TEST path; no network)
  --no-push
  --reuse-empty-repo    if <org>/<Project> already exists and has ZERO
                        commits, use it as the assembly root instead of
                        refusing. A repository with commits is still refused:
                        that is a live project, not a slot.
  --pin openProduct@COMMIT
                        declare a neutral-product pin, e.g. --pin
                        openGlass@<40 hex>. It writes
                        contracts/<openproduct>-pin.yaml and lists the product
                        in the manifest, which is what makes a
                        `<Domainx><Product>` name a DESCENDANT rather than a
                        name shaped like one. Repeatable.
  --referent-chain openLayer,openProduct
                        the CHAIN of neutral-product pins this project reaches
                        its referent through, e.g. --referent-chain
                        openXdox,openDox. Its first entry must be one of the
                        --pin products (the pin this project actually holds)
                        and its last must be the `open<Product>` the name
                        claims; the manifest RECORDS it, which is what makes a
                        descendant that pins a LAYER a descendant
                        (2026-09-05).
  --pin-source PIN_SOURCE
                        a local clone to compute --pin digests from, instead
                        of reading the forge with `gh api` (the TEST path; no
                        network)
  --work-dir WORK_DIR   where the working trees are built (default: a
                        temporary directory)
```

### `adopt-project.py`

`python3 adopt-project.py --help`:

```
usage: adopt-project.py [-h] {plan,check,execute} ...

Adopt an EXISTING repository into the three-repository shape, IN PLACE.

positional arguments:
  {plan,check,execute}
    plan                classify a source repository
    check               validate a plan
    execute             carry the plan out

options:
  -h, --help            show this help message and exit
```

#### `adopt-project.py plan`

`python3 adopt-project.py plan --help`:

```
usage: adopt-project.py plan [-h] --source SOURCE --project PROJECT
                             [--org ORG] [--id ID]
                             [--visibility {private,public,internal}]
                             [--elected-by ELECTED_BY]
                             [--elected-on ELECTED_ON] [--reference REFERENCE]
                             [--tracking-branch TRACKING_BRANCH]
                             [--spec-path SPEC_PATH] [--code-path CODE_PATH]
                             [--pin PIN] [--allow-empty-leg {spec,code}]
                             [--path-policy PATH_POLICY] [--out OUT]
                             [--work-dir WORK_DIR]

options:
  -h, --help            show this help message and exit
  --source SOURCE       a local path (read only) or `org/repo` to clone
  --project PROJECT     the assembly-root name; for an in-place adoption it is
                        the source repository's own name
  --org ORG
  --id ID
  --visibility {private,public,internal}
  --elected-by ELECTED_BY
  --elected-on ELECTED_ON
                        YYYY-MM-DD
  --reference REFERENCE
                        the document the election followed. Default:
                        openxFactory's ratified docs/project-repo-schema.md
                        for an election on or after 2026-09-02, and the staged
                        fragment it was ratified from for one dated earlier —
                        so --elected-on chooses it.
  --tracking-branch TRACKING_BRANCH
  --spec-path SPEC_PATH
  --code-path CODE_PATH
  --pin PIN             a neutral product this project declares a pin on — a
                        NAME only, e.g. --pin openGlass or --pin
                        opensoft/openGlass to name the owner explicitly.
                        Adopting a project pins no commit at plan time, so a
                        trailing @<commit> (scaffold-project.py's syntax) is
                        refused.
  --allow-empty-leg {spec,code}
                        record in the plan that this leg having NO path is
                        intended, so it may be SEEDED from the shape's
                        template instead of extracted. The InkRouter services
                        are specifications with no code yet (2026-09-04):
                        `--allow-empty-leg code`. Repeatable.
  --path-policy PATH_POLICY
  --out OUT
  --work-dir WORK_DIR
```

#### `adopt-project.py check`

`python3 adopt-project.py check --help`:

```
usage: adopt-project.py check [-h] --plan PLAN [--source SOURCE]
                              [--work-dir WORK_DIR]

options:
  -h, --help           show this help message and exit
  --plan PLAN
  --source SOURCE      override the source the plan names
  --work-dir WORK_DIR
```

#### `adopt-project.py execute`

`python3 adopt-project.py execute --help`:

```
usage: adopt-project.py execute [-h] --plan PLAN [--source SOURCE]
                                [--local-remote-dir LOCAL_REMOTE_DIR]
                                [--allow-empty-leg {spec,code}] [--yes]
                                [--work-dir WORK_DIR]

options:
  -h, --help            show this help message and exit
  --plan PLAN
  --source SOURCE
  --local-remote-dir LOCAL_REMOTE_DIR
                        create the legs as bare repositories here instead of
                        calling `gh` (the TEST path)
  --allow-empty-leg {spec,code}
                        proceed even though NO path is assigned to this leg,
                        seeding it from the shape's template. Unioned with the
                        plan's own `allow_empty_legs:`; without one of the
                        two, execute refuses.
  --yes                 the human has read the plan and the follow-ups
  --work-dir WORK_DIR
```

### `update-shape.py`

`python3 update-shape.py --help`:

```
usage: update-shape.py [-h] {check,apply} ...

Re-sync a root's COPIED shape files with openRepoShape, and re-pin.

positional arguments:
  {check,apply}
    check        report what the upstream has changed; write nothing
    apply        re-copy the changed files and re-pin

options:
  -h, --help     show this help message and exit
```

#### `update-shape.py check`

`python3 update-shape.py check --help`:

```
usage: update-shape.py check [-h] --root ROOT [--upstream UPSTREAM] [--at AT]

options:
  -h, --help           show this help message and exit
  --root ROOT          the assembly root to update
  --upstream UPSTREAM  a path to a clone of openRepoShape, or `owner/repo`
                       (default: the pin's `source_repository`)
  --at AT              the upstream revision to update to (default: the
                       upstream's tip)
```

#### `update-shape.py apply`

`python3 update-shape.py apply --help`:

```
usage: update-shape.py apply [-h] --root ROOT [--upstream UPSTREAM] [--at AT]
                             [--yes] [--accept-local PATH] [--add PATH]
                             [--branch BRANCH] [--trailer "KEY: VALUE"]
                             [--push] [--pr]

options:
  -h, --help            show this help message and exit
  --root ROOT           the assembly root to update
  --upstream UPSTREAM   a path to a clone of openRepoShape, or `owner/repo`
                        (default: the pin's `source_repository`)
  --at AT               the upstream revision to update to (default: the
                        upstream's tip)
  --yes                 the human has read `check` and said yes
  --accept-local PATH   re-pin this locally-modified file FROM THE ROOT'S OWN
                        BYTES; repeatable
  --add PATH            copy this `upstream-added` file into the root and
                        append its pin row; repeatable, and never passed for a
                        file a human has not said to take
  --branch BRANCH       create this branch and commit the change to it, with
                        explicit pathspecs
  --trailer "KEY: VALUE"
                        append this `<Key>: <value>` line to the commit, after
                        any already there; repeatable, kept in the order
                        given, and needs --branch — there is no commit to put
                        a line on without one
  --push                push the branch to origin (needs --branch)
  --pr                  open a pull request with `gh` (needs --branch)
```

### `shape-doctor.py`

`python3 shape-doctor.py --help`:

```
usage: shape-doctor.py [-h] [--root ROOT] [--json] [--placement-plan FILE]

Is this repository compliant with openRepoShape, and what is missing?

options:
  -h, --help            show this help message and exit
  --root ROOT           the repository to check (default: .)
  --json                the same report as one JSON object
  --placement-plan FILE
                        write the `placement` row's paths to FILE as an
                        adoption-plan-style YAML to resolve by hand. The only
                        thing this command writes, and it still moves nothing:
                        a path changing legs is a pull request on each leg and
                        a pin bump in the root
```

### `bootstrap`

A shim: it runs `templates/assembly-root/scripts/bootstrap.py` with `--root` set to the directory you are standing in, which is why the help below prints under THAT file's name and carries its flags.

`python3 bootstrap --help`:

```
usage: bootstrap.py [-h] [--root ROOT] [--branch BRANCH] [--skip-validators]

The one command an engineer runs after `git clone --recurse-submodules`.

options:
  -h, --help         show this help message and exit
  --root ROOT
  --branch BRANCH    tracking branch to place the legs on (default:
                     project.yaml `tracking_branch`, else main)
  --skip-validators
```

### `scripts/bump-leg.py`

`python3 scripts/bump-leg.py --help`:

```
usage: bump-leg.py [-h] --root PATH --leg {spec,code} --to COMMIT
                   [--local-remote-dir LOCAL_REMOTE_DIR] [--dry-run]

Advance ONE leg of an assembly root, in ONE LOCKSTEP COMMIT.

options:
  -h, --help            show this help message and exit
  --root PATH           the project's ASSEMBLY ROOT — the repository carrying
                        project.yaml
  --leg {spec,code}     which leg to advance, by the `role:` its own
                        project.yaml declares
  --to COMMIT           the 40-hex commit to move the gitlink, the pin and
                        every workflow reference to, together
  --local-remote-dir LOCAL_REMOTE_DIR
                        resolve the leg's remote to a bare repository here
                        instead of its origin (the TEST path; no network)
  --dry-run             print what would move and change nothing
```

### `scripts/family.py`

`python3 scripts/family.py --help`:

```
usage: family.py [-h] {init,add,bump,remove,siblings} ...

Create and maintain a FAMILY: a holder that pins member assembly roots.

positional arguments:
  {init,add,bump,remove,siblings}
    init                create a family holder
    add                 mount and pin a member
    bump                move a member's pin
    remove              unmount a member
    siblings            clone every member BESIDE the holder, on its tracking
                        branch

options:
  -h, --help            show this help message and exit
```

#### `scripts/family.py init`

`python3 scripts/family.py init --help`:

```
usage: family.py init [-h] --org ORG --family FAMILY [--id ID] [--name NAME]
                      [--visibility {private,public,internal}]
                      [--created-by CREATED_BY] [--created-on CREATED_ON]
                      [--tracking-branch TRACKING_BRANCH] [--reuse-empty-repo]
                      [--local-remote-dir LOCAL_REMOTE_DIR] [--into DIR]
                      [--work-dir WORK_DIR] [--no-push] [--dry-run]

options:
  -h, --help            show this help message and exit
  --org ORG
  --family FAMILY       the holder's name, ONE CamelCase token, e.g. InkRouter
  --id ID               lowercase family id
  --name NAME           display name
  --visibility {private,public,internal}
  --created-by CREATED_BY
  --created-on CREATED_ON
                        YYYY-MM-DD
  --tracking-branch TRACKING_BRANCH
  --reuse-empty-repo    if <org>/<Family> already exists and has ZERO commits,
                        use it as the holder instead of refusing. A repository
                        with commits is still refused: that is live, not a
                        slot.
  --local-remote-dir LOCAL_REMOTE_DIR
                        create a bare repository here instead of calling `gh
                        repo create` (the TEST path; no network)
  --into DIR            the PARENT directory the family folder is made in
                        (default: the directory you are standing in). The
                        holder lands at <into>/<Family>/<Family>, beside where
                        `make siblings` clones the members.
  --work-dir WORK_DIR   THE OVERRIDE: land the holder at <work-dir>/<Family>
                        and make no family folder at all. Mutually exclusive
                        with --into.
  --no-push
  --dry-run
```

#### `scripts/family.py add`

`python3 scripts/family.py add --help`:

```
usage: family.py add [-h] --family-root FAMILY_ROOT --member ORG/PROJECT
                     [--at COMMIT] [--local-remote-dir LOCAL_REMOTE_DIR]

options:
  -h, --help            show this help message and exit
  --family-root FAMILY_ROOT
  --member ORG/PROJECT  the member's ASSEMBLY ROOT, `<org>/<Project>` — never
                        a leg
  --at COMMIT           pin this 40-hex commit instead of the member's current
                        tip
  --local-remote-dir LOCAL_REMOTE_DIR
                        resolve the member to a bare repository here instead
                        of github.com (the TEST path)
```

#### `scripts/family.py bump`

`python3 scripts/family.py bump --help`:

```
usage: family.py bump [-h] --family-root FAMILY_ROOT --member PROJECT
                      --to COMMIT [--trailer "KEY: VALUE"]

options:
  -h, --help            show this help message and exit
  --family-root FAMILY_ROOT
  --member PROJECT
  --to COMMIT           the 40-hex commit to move the gitlink and the pin to,
                        together
  --trailer "KEY: VALUE"
                        append this `<Key>: <value>` line to the commit this
                        writes; repeatable, kept in the order given
```

#### `scripts/family.py remove`

`python3 scripts/family.py remove --help`:

```
usage: family.py remove [-h] --family-root FAMILY_ROOT --member PROJECT

options:
  -h, --help            show this help message and exit
  --family-root FAMILY_ROOT
  --member PROJECT
```

#### `scripts/family.py siblings`

`python3 scripts/family.py siblings --help`:

```
usage: family.py siblings [-h] --family-root FAMILY_ROOT [--dry-run]

options:
  -h, --help            show this help message and exit
  --family-root FAMILY_ROOT
                        the HOLDER (`<Family>/<Family>`); the siblings are
                        placed in the folder around it
  --dry-run             say what would be cloned and fetched; clone nothing,
                        fetch nothing, move nothing
```

### `scripts/validate-repository-naming.py`

`python3 scripts/validate-repository-naming.py --help`:

```
usage: validate-repository-naming.py [-h] [--policy POLICY]
                                     [--project PROJECT]
                                     [--role {assembly,spec,code,family}]
                                     [--pins PINS]
                                     [--referent-chain REFERENT_CHAIN]
                                     [--link-source [PRODUCT=]PATH]
                                     [--explain] [--quiet] [names ...]

Classify repository names against `contracts/repository-naming.yaml`.

positional arguments:
  names                 repository names to classify

options:
  -h, --help            show this help message and exit
  --policy POLICY
  --project PROJECT     read the leg names, their roles and the declared
                        neutral-product pins from a project.yaml manifest
  --role {assembly,spec,code,family}
                        the role the NAMES on the command line are offered as;
                        a descendant-form name with no referent pin is
                        classified by this, and `family` is what asks whether
                        a name is a valid HOLDER — a form spelled exactly like
                        an assembly root, so it is reported only when declared
  --pins PINS           comma-separated neutral products the project declares
                        a pin on, e.g. --pins openChart. A
                        `<Domainx><Product>` name is a domain descendant only
                        when its `open<Product>` is in this list.
  --referent-chain REFERENT_CHAIN
                        the pin chain the project RECORDS as reaching its
                        referent, e.g. --referent-chain openXdox,openDox. The
                        first entry must be in --pins and the last must be the
                        name's `open<Product>`; with --project it is read from
                        each leg's `naming.referent_chain:` instead.
  --link-source [PRODUCT=]PATH
                        where a chain LINK's own tree is, so its
                        `neutral_product_pins:` can be read and the link
                        VERIFIED — e.g. --link-source openXdox=../openXdox. A
                        bare PATH applies to whichever link has no more
                        specific answer. SHAPE_PIN_SOURCE_<PRODUCT> and a
                        checkout beside the project are tried too. A link no
                        source answers for is declared-unverified, which is a
                        warning and not a finding.
  --explain             print every family each name satisfies, why one of
                        them won, and what the others are recorded as
  --quiet
```

## Shipped into every project (copied, digest-pinned)

These six are COPIES. `scaffold-project.py` writes them into a scaffolded project or a family holder and records each one by sha256 in that root's own `contracts/shape-pin.yaml`, which is what lets a project run its gate with no network and no mount. They are run from INSIDE such a root, under its own `scripts/`, never from a checkout of this standard — the help below is rendered from the master copy here, because a change to one of them is made here and reaches a project through `update-shape.py`.

### `templates/assembly-root/scripts/bootstrap.py`

Run as `python3 scripts/bootstrap.py` from inside an assembly root.

`python3 scripts/bootstrap.py --help`:

```
usage: bootstrap.py [-h] [--root ROOT] [--branch BRANCH] [--skip-validators]

The one command an engineer runs after `git clone --recurse-submodules`.

options:
  -h, --help         show this help message and exit
  --root ROOT
  --branch BRANCH    tracking branch to place the legs on (default:
                     project.yaml `tracking_branch`, else main)
  --skip-validators
```

### `templates/assembly-root/scripts/validate-manifest.py`

Run as `python3 scripts/validate-manifest.py` from inside an assembly root.

`python3 scripts/validate-manifest.py --help`:

```
usage: validate-manifest.py [-h] [--root ROOT] [--policy POLICY] [--quiet]

Validate this project's `project.yaml` — the SOURCE of the group.

options:
  -h, --help       show this help message and exit
  --root ROOT
  --policy POLICY
  --quiet
```

### `templates/assembly-root/scripts/validate-pins.py`

Run as `python3 scripts/validate-pins.py` from inside an assembly root.

`python3 scripts/validate-pins.py --help`:

```
usage: validate-pins.py [-h] [--root ROOT] [--quiet]
                        [--pin-source [PRODUCT=]PATH]

THE LOCKSTEP VALIDATOR — three things move in one commit, or this refuses.

options:
  -h, --help            show this help message and exit
  --root ROOT           assembly root (default: the enclosing repository)
  --quiet
  --pin-source [PRODUCT=]PATH
                        a local checkout to recompute a neutral-product pin's
                        digest from, instead of `gh api` — e.g. --pin-source
                        openGlass=../openGlass. A bare PATH with no `PRODUCT=`
                        applies to whichever declared pin has no more specific
                        answer (the common case is exactly one). Repeatable.
                        SHAPE_PIN_SOURCE_<PRODUCT> (env) and a checkout
                        sitting beside this assembly root are also tried,
                        before `gh api` and before this flag's bare form.
```

### `templates/family-root/scripts/bootstrap.py`

Run as `python3 scripts/bootstrap.py` from inside a family holder.

`python3 scripts/bootstrap.py --help`:

```
usage: bootstrap.py [-h] [--root ROOT] [--no-fetch] [--members-make TARGET]
                    [--skip-members]

The one command an engineer runs after cloning a FAMILY holder.

options:
  -h, --help            show this help message and exit
  --root ROOT
  --no-fetch            skip step (a); the members are already there (what
                        `make validate` passes)
  --members-make TARGET
                        the make target to run in each member (default:
                        bootstrap)
  --skip-members        fetch only; run nothing in the members
```

### `templates/family-root/scripts/siblings.py`

Run as `python3 scripts/siblings.py` from inside a family holder.

`python3 scripts/siblings.py --help`:

```
usage: siblings.py [-h] [--root ROOT] [--dry-run] [--make TARGET]
                   [--make-arg ARG]

Clone every member of this family BESIDE the holder, and check the layout.

options:
  -h, --help      show this help message and exit
  --root ROOT     the family holder (default: the enclosing repository)
  --dry-run       say what would be cloned and fetched (or, with --make, what
                  would be run); clone nothing, fetch nothing, run nothing,
                  move nothing
  --make TARGET   run `make TARGET` in each member's WORKING CLONE beside the
                  holder instead of placing them; clones nothing and fetches
                  nothing. What the holder's `make park` / `make resume` use
  --make-arg ARG  appended verbatim to each member's `make` command line (the
                  holder passes `ARGS=...` through this way); repeatable,
                  --make only
```

### `templates/family-root/scripts/validate-family.py`

Run as `python3 scripts/validate-family.py` from inside a family holder.

`python3 scripts/validate-family.py --help`:

```
usage: validate-family.py [-h] [--root ROOT] [--policy POLICY] [--pins]
                          [--no-members] [--quiet]

Validate this FAMILY's `family.yaml`, its member pins and its shape copies.

options:
  -h, --help       show this help message and exit
  --root ROOT      the family root (default: the enclosing repository)
  --policy POLICY
  --pins           the member lockstep check alone: gitlink, digest and
                   identity, with no envelope and no shape-copy check (what
                   `make pins` runs)
  --no-members     the envelope and the shape copies alone, skipping every
                   member. The complement of --pins, and what CI runs when the
                   members could not be checked out: the checks that do not
                   need them still run, and the ones that do are skipped out
                   loud rather than passing on an unreadable surface.
  --quiet
```
