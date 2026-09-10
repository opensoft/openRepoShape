#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Is this repository compliant with openRepoShape, and what is missing?

    ./shape-doctor.py [--root <path>] [--json]       # default --root .
    openRepoShape --doctor [<path>]                  # the same, from anywhere

ONE COMMAND, ONE VERDICT, AND IT REIMPLEMENTS NOTHING. Brett Heap asked, on
2026-09-10: "what tools do we have to check a repo to make sure it is
compliant with openRepoShape?" -- and the honest answer was five of them, in
an order nobody had written down. `validate-repository-naming.py` classifies
the names; the project's OWN `scripts/validate-manifest.py` and
`scripts/validate-pins.py` are its pinned gate; `update-shape.py check` says
whether the copies have fallen behind the standard; a FAMILY holder runs
`scripts/validate-family.py` instead of the first two; and a directory
carrying neither manifest is not a shape root at all and wants
`adopt-project.py plan` or `setup.sh`. This runs them in sequence, prints one
row each, and then prints ONE verdict. Every row is somebody else's check.

WHAT IT NEVER DOES. It never writes and it never fetches. The upstream a
project's copies are compared against is THE CHECKOUT THIS FILE IS RUN FROM,
which is the whole of why the verdict is offline: no clone, no authenticated
call, and the same answer on a machine that has never spoken to github.com.
It runs the project's own validators, which are offline by their own
contract. ONE ROW IS THE EXCEPTION AND IT IS NAMED: `machine` asks `gh`
whether it is logged in, which `gh` answers by talking to its host. That row
is `n/a` by status and cannot move the verdict -- a workstation missing `gh`
is not a repository being non-compliant -- so nothing this command CONCLUDES
depends on a network, and a machine with no `gh` at all is reported rather
than refused.

THE CHECKS ARE A REGISTRY, not a function with eight paragraphs in it. Each
one is a `Check` -- an `id`, the root kinds it `applies_to`, a `run(ctx)` that
returns one `Row`, and a `fix` slot that is `None` for every check today. That
shape is deliberate: a repair mode is coming (put a repository back into the
correct three-leg version), and it hangs a repair off `fix` rather than
rewriting this file. A `--fix` that ever calls one does so only after printing
the plan and getting the human's yes, exactly like `update-shape.py apply`.

MANIFEST VALIDATION IS KEYED BY `kind:`. `MANIFEST_VALIDATORS` maps a
manifest's declared `kind:` -- `project-manifest`, `family-manifest`,
`pinned_contract_manifest`, the two policy kinds -- to the check that covers
it, and a `contracts/*.yaml` whose `kind` has no entry is a FINDING that says
so by name. A manifest nobody validates is the failure this whole standard is
against, and "we did not notice it was there" is how it happens; a future
inventory plugs in by adding one row to that table.

THE ROWS, for an assembly root, in this order:

    naming            the three leg names against the STANDARD's own
                      `contracts/repository-naming.yaml`
    manifest          the project's own `scripts/validate-manifest.py` when it
                      has one -- it is the pinned copy, and that is the point
                      -- else the standard's template copy, and the row says
                      which ran
    pins              the project's own `scripts/validate-pins.py` likewise:
                      the lockstep invariant, and the shape-copy digests
    manifest kinds    every `kind:`-bearing manifest in the root, against
                      MANIFEST_VALIDATORS
    shape currency    `update-shape.py check`'s per-file verdicts, summarised
    legs              each leg mounted, and its checked-out commit against the
                      pin (no fetch)
    leg shape files   each present leg's `AGENTS.md`, `CLAUDE.md` and
                      `.gitignore` against `templates/<role>-root/`
    agent files       `AGENTS-shape.md`, `AGENTS.md`, `CLAUDE.md` at the root
    machine           whether this workstation can RUN the fixes named above
                      (`setup-project.py --preflight`, plus `git-filter-repo`)

and for a FAMILY holder: `family` (its own `scripts/validate-family.py`),
`manifest kinds`, `shape currency`, `members` and `machine`. A directory that
is NEITHER gets `naming` (what it is called, under the policy), `what is
here`, `the way in` -- `adopt-project.py plan` for a repository that already
exists, `setup.sh` for a new one -- and `machine`.

A FINDING NAMES ITS FIX. Every row that is not `ok` carries the exact next
command, because a refusal that does not say what to run is a refusal the
reader improvises around -- which is the house rule the rest of this standard
is built on.

EXIT CODES
    0  COMPLIANT: every row ok and the shape is current
    1  findings: the shape is behind, a copy has drifted, a validator is red,
       or a leg is off its pin
    2  NOT A SHAPE ROOT: neither `project.yaml` nor `family.yaml` is there
    3  usage or environment: no such root, or this file is not sitting in a
       checkout of the standard

THE VERDICT NAMES THE MOST SPECIFIC FINDING; THE TABLE NAMES EVERY ONE. Drift
outranks a red validator on that line for one concrete reason: an edited shape
copy is exactly what makes `validate-pins.py` red, so answering `INVALID
(validate-pins.py)` would send the reader at the symptom while the fix is
`update-shape.py`. The pins row is still printed, with its own next command.

STANDARD LIBRARY ONLY, like everything else shipped here. Printed text is
ASCII: a verdict a cp1252 console cannot render is a verdict nobody reads, and
this tool is run on every platform the standard supports.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PYTHON, Refusal, git_out, load_yaml, recorded_gitlink,
)

#: The statuses a row can carry. `n/a` is not a pass and not a failure: it is
#: a question this ROOT does not have -- a family has no legs, a project
#: standing outside a git repository has no gitlinks to read -- or, for the
#: `machine` row, a question that is not about the root at all. Nothing `n/a`
#: ever changes the verdict, which is the whole reason the word is here: this
#: command answers "is this REPOSITORY compliant", and a workstation missing
#: `gh` is not that repository being wrong.
OK = "ok"
FINDING = "FINDING"
NA = "n/a"

#: Which kind of root this is. Read from the tree, never taken as a flag, the
#: same rule `update-shape.py`'s `root_kind` follows and for the same reason.
PROJECT = "project"
FAMILY = "family"
NOT_A_ROOT = "none"

#: The verdicts, in the order they outrank each other. See the docstring for
#: why DRIFTED sits above INVALID.
V_COMPLIANT = "COMPLIANT"
V_BEHIND = "COMPLIANT, SHAPE BEHIND"
V_DRIFTED = "DRIFTED"
V_INVALID = "INVALID"
V_NOT_A_ROOT = "NOT A SHAPE ROOT"

#: What the standard has to have around this file for any of this to mean
#: anything. `shape-doctor.py` compares a project against THE CHECKOUT IT IS RUN
#: FROM, so a copy of this one file on its own can answer nothing.
SHAPE_MARKERS = ("contracts/repository-naming.yaml",
                 "scripts/validate-repository-naming.py",
                 "templates/assembly-root", "update-shape.py")

#: The three files a scaffolded root carries for an agent. `AGENTS-shape.md`
#: is a PINNED shape copy, so the pins and shape-currency rows already digest
#: it; this row is for a reader, who wants to know whether the file is there
#: before reading two digest tables to find out.
AGENT_FILES = ("AGENTS-shape.md", "AGENTS.md", "CLAUDE.md")

#: The leg files this compares, and the ones a byte comparison is meaningless
#: for. `templates/<role>-root/AGENTS.md` and `README.md` carry
#: `{{PLACEHOLDER}}`s the scaffold renders per project, so "differs" is what
#: they are BY CONSTRUCTION; `CLAUDE.md` and `.gitignore` are verbatim and a
#: comparison of them is a fact. No leg file has a digest row anywhere today
#: -- only the assembly root's copies are pinned -- so this row reports and
#: does not judge, beyond a file that is missing altogether.
LEG_SHAPE_FILES = ("AGENTS.md", "CLAUDE.md", ".gitignore")
LEG_RENDERED = ("AGENTS.md", "README.md")


def ascii_text(text: str) -> str:
    """`text` with the typography this repository is written in flattened.

    Validator output is quoted into rows, and this repository's prose is full
    of em dashes, curly quotes and ellipses. A Windows console in the machine's
    ANSI code page raises on the first of them, in the middle of a report whose
    whole job is to be read -- so the few characters that actually occur are
    spelled out and anything else is replaced rather than raised on.
    """
    for source, target in (("—", "--"), ("–", "-"), ("‘", "'"),
                           ("’", "'"), ("“", '"'), ("”", '"'),
                           ("…", "..."), (" ", " ")):
        text = text.replace(source, target)
    return text.encode("ascii", "replace").decode("ascii")


# ---------------------------------------------------------------------------
# A row, a check, and the registry they live in
# ---------------------------------------------------------------------------


class Row:
    """One line of the report: what was asked, the answer, and the exit."""

    def __init__(self, check_id: str, label: str, status: str, reason: str,
                 next_command: str | None = None, detail: dict | None = None):
        self.id = check_id
        self.label = label
        self.status = status
        self.reason = ascii_text(reason)
        self.next_command = ascii_text(next_command) if next_command else None
        #: Structured facts for `--json`, so a caller reads numbers rather
        #: than parsing the sentence a human is meant to read.
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status,
                "reason": self.reason, "next": self.next_command,
                "detail": self.detail}


class Check:
    """One question this command knows how to ask.

    `fix` IS THE SLOT A REPAIR MODE HANGS OFF, and it is `None` for every check
    in this file today. A later `--doctor <path> --fix` calls it only after printing
    the plan
    and getting the human's yes -- the same posture `update-shape.py apply`
    takes, for the same reason: putting a repository back into shape rewrites
    somebody's tree.
    """

    def __init__(self, check_id: str, label: str, applies_to: tuple,
                 run, fix=None):
        self.id = check_id
        self.label = label
        self.applies_to = applies_to
        self.run = run
        self.fix = fix


class ManifestKind:
    """One `kind:` this standard knows a validator for.

    `covered_by` is the id of the CHECK that validates it, so the row about
    manifest kinds can say where a kind was answered rather than merely that
    it was recognised. A kind with no entry here is a FINDING by name: a
    manifest nobody validates is the gap this table exists to close.
    """

    def __init__(self, kind: str, covered_by: str, how: str):
        self.kind = kind
        self.covered_by = covered_by
        self.how = how


MANIFEST_VALIDATORS: dict[str, ManifestKind] = {
    "project-manifest": ManifestKind(
        "project-manifest", "manifest", "scripts/validate-manifest.py"),
    "family-manifest": ManifestKind(
        "family-manifest", "family", "scripts/validate-family.py"),
    "pinned_contract_manifest": ManifestKind(
        "pinned_contract_manifest", "pins",
        "scripts/validate-pins.py (or validate-family.py in a holder)"),
    "repository-naming-policy": ManifestKind(
        "repository-naming-policy", "naming",
        "scripts/validate-repository-naming.py, through NamingPolicy.load"),
    "path-classification-policy": ManifestKind(
        "path-classification-policy", "manifest-kinds",
        "scripts/path_classify.py reads it; nothing validates it in a root"),
}


# ---------------------------------------------------------------------------
# The context every check is handed
# ---------------------------------------------------------------------------


class Context:
    """The root, what it is, and the few things every check would recompute."""

    def __init__(self, root: Path):
        self.root = root
        self.shape = SHAPE_ROOT
        self.manifest_path: Path | None = None
        self.manifest: dict | None = None
        self.kind = NOT_A_ROOT
        self._update_shape = None
        project = root / "project.yaml"
        family = root / "family.yaml"
        # `kind:` DECIDES, not the filename. A `project.yaml` that declares
        # something else is not a project manifest, and reading the name alone
        # would let a file called the right thing assert whatever it liked.
        if project.is_file() and self._declares(project, "project-manifest"):
            self.kind, self.manifest_path = PROJECT, project
        elif family.is_file() and self._declares(family, "family-manifest"):
            self.kind, self.manifest_path = FAMILY, family
        if self.manifest_path is not None:
            data = self._read(self.manifest_path)
            self.manifest = data if isinstance(data, dict) else None

    @staticmethod
    def _read(path: Path):
        try:
            return load_yaml(path)
        except (Refusal, OSError, UnicodeDecodeError):
            return None

    def _declares(self, path: Path, kind: str) -> bool:
        data = self._read(path)
        return isinstance(data, dict) and data.get("kind") == kind

    def legs(self) -> list[dict]:
        """The non-assembly legs `project.yaml` declares, in its own order."""
        return [leg for leg in ((self.manifest or {}).get("legs") or [])
                if isinstance(leg, dict) and leg.get("role") != "assembly"]

    def members(self) -> list[dict]:
        return [row for row in ((self.manifest or {}).get("members") or [])
                if isinstance(row, dict)]

    def update_shape(self):
        """`update-shape.py` as a module, loaded once.

        BY PATH, because the filename has a hyphen and cannot be imported by
        name -- the same reason `tests/test_repo_hygiene.py` loads
        `setup-project.py` that way. Importing it rather than shelling out to
        it is what gives this command the per-file verdicts instead of a
        screenful of somebody else's report to parse back.
        """
        if self._update_shape is None:
            path = self.shape / "update-shape.py"
            spec = importlib.util.spec_from_file_location(
                "openreposhape_update_shape", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._update_shape = module
        return self._update_shape


# ---------------------------------------------------------------------------
# Running somebody else's validator
# ---------------------------------------------------------------------------


def run_validator(ctx: Context, script: Path, args: list[str]) -> tuple:
    """`(exit code, first line worth quoting, whole output)`.

    THE PYTHONPATH IS THE POINT OF THE `env` BLOCK. A project's own
    `scripts/validate-pins.py` sits beside its own copy of `repo_shape.py` and
    imports it from there. The STANDARD's template copy has no `repo_shape.py`
    beside it -- that file is copied out of the shape itself, not out of the
    template -- so when this command falls back to the template it must put
    `<shape>/scripts` on the path or the fallback dies on an ImportError that
    says nothing about the project being checked.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    scripts = str(ctx.shape / "scripts")
    env["PYTHONPATH"] = (f"{scripts}{os.pathsep}{existing}" if existing
                         else scripts)
    # UTF-8 whatever the console is: these validators print this repository's
    # own prose, and `ascii_text` flattens it for the report afterwards.
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, str(script), *args],
                          cwd=str(ctx.root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          stdin=subprocess.DEVNULL, env=env)
    whole = (proc.stdout or "") + (proc.stderr or "")
    quoted = ""
    for line in whole.splitlines():
        stripped = line.strip()
        if stripped.startswith(("FINDING", "REFUSED", "WARNING")):
            quoted = stripped
            break
    if not quoted:
        lines = [line.strip() for line in whole.splitlines() if line.strip()]
        quoted = lines[-1] if lines else ""
    return proc.returncode, quoted[:200], whole


def validator_row(ctx: Context, check_id: str, label: str, own: str,
                  template: str, args: list[str]) -> Row:
    """One row for a validator that the ROOT may carry its own copy of.

    THE PROJECT'S OWN COPY FIRST, ALWAYS, AND THE ROW SAYS SO. That copy is
    the pinned one -- it is what the project's own gate runs, and running the
    standard's newer copy instead would answer a question nobody asked: not
    "does this project pass its gate" but "would it pass a gate it does not
    have". The template copy is the fallback for a root that has lost or never
    had one, and the row names which of the two answered.
    """
    own_path = ctx.root / own
    used, which = (own_path, f"the project's own {own}") if own_path.is_file() \
        else (ctx.shape / template, f"the standard's {template}")
    if not used.is_file():
        return Row(check_id, label, FINDING,
                   f"neither {own} nor {template} is readable, so the "
                   "question cannot be asked",
                   f"{PYTHON} {ctx.shape / 'setup.sh'} --help  # this checkout "
                   "of the standard is incomplete", {"validator": None})
    code, quoted, _ = run_validator(ctx, used, args)
    detail = {"validator": used.as_posix(), "own_copy": own_path.is_file(),
              "exit": code}
    if code == 0:
        return Row(check_id, label, OK, f"{which} passes", None, detail)
    verb = "refuses" if code >= 2 else "reports a finding"
    reason = f"{which} {verb} (exit {code})" + (f": {quoted}" if quoted else "")
    return Row(check_id, label, FINDING, reason,
               f"{PYTHON} {used.name} in {ctx.root}  # read its output in "
               "full; it names what it refused", detail)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def check_naming(ctx: Context) -> Row:
    """The leg names, against THE STANDARD's copy of the naming policy.

    The standard's rather than the project's on purpose: this command answers
    "is this compliant with openRepoShape", and openRepoShape is the checkout
    this file is in. A project whose copied policy is older is exactly the
    thing the shape-currency row is for, and it says so there.
    """
    script = ctx.shape / "scripts" / "validate-repository-naming.py"
    code, quoted, _ = run_validator(
        ctx, script, ["--project", str(ctx.root / "project.yaml"), "--quiet"])
    detail = {"policy": (ctx.shape / "contracts" /
                         "repository-naming.yaml").as_posix(), "exit": code}
    if code == 0:
        return Row("naming", "naming", OK,
                   "every leg name classifies, and each declared role agrees "
                   "with its form", None, detail)
    return Row("naming", "naming", FINDING,
               f"the naming policy is not satisfied (exit {code})"
               + (f": {quoted}" if quoted else ""),
               f"{PYTHON} {script} --explain --project "
               f"{ctx.root / 'project.yaml'}", detail)


def check_manifest(ctx: Context) -> Row:
    return validator_row(
        ctx, "manifest", "manifest", "scripts/validate-manifest.py",
        "templates/assembly-root/scripts/validate-manifest.py",
        ["--root", str(ctx.root)])


def check_pins(ctx: Context) -> Row:
    return validator_row(
        ctx, "pins", "pins", "scripts/validate-pins.py",
        "templates/assembly-root/scripts/validate-pins.py",
        ["--root", str(ctx.root)])


def check_family(ctx: Context) -> Row:
    return validator_row(
        ctx, "family", "family", "scripts/validate-family.py",
        "templates/family-root/scripts/validate-family.py",
        ["--root", str(ctx.root)])


def manifest_candidates(root: Path) -> list[Path]:
    """Every file in a root that might DECLARE a `kind:`.

    The two manifests at the top, and everything under `contracts/`. Not the
    whole tree: a leg is its own repository with its own contracts, and a
    holder's `members/<Project>` is a whole project -- walking into either
    would make this command report on repositories it was not pointed at.
    """
    found = [root / "project.yaml", root / "family.yaml"]
    contracts = root / "contracts"
    if contracts.is_dir():
        found += sorted(p for p in contracts.iterdir()
                        if p.is_file() and p.suffix in (".yaml", ".yml"))
    return [path for path in found if path.is_file()]


def check_manifest_kinds(ctx: Context) -> Row:
    """Every `kind:`-bearing manifest in this root, against the registry.

    A YAML FILE WITH NO `kind:` IS NOT A MANIFEST and is skipped in silence:
    an adopted project's `contracts/policy.yaml` is its own business, and a
    tool that called every file it did not recognise a finding would be
    reporting on somebody else's data. What is reported is the other case --
    a file that DOES declare a kind that nothing here validates, which is a
    manifest travelling in a shape root with no gate behind it.
    """
    known: list[str] = []
    unknown: list[str] = []
    unreadable: list[str] = []
    for path in manifest_candidates(ctx.root):
        data = Context._read(path)
        if not isinstance(data, dict):
            unreadable.append(path.relative_to(ctx.root).as_posix())
            continue
        kind = data.get("kind")
        if not isinstance(kind, str) or not kind:
            continue
        rel = path.relative_to(ctx.root).as_posix()
        entry = MANIFEST_VALIDATORS.get(kind)
        (known if entry else unknown).append(f"{rel} ({kind})")
    detail = {"validated": known, "unregistered": unknown,
              "unreadable": unreadable,
              "registered_kinds": sorted(MANIFEST_VALIDATORS)}
    if unknown or unreadable:
        parts = []
        if unknown:
            parts.append("no validator registered for kind "
                         + ", ".join(unknown))
        if unreadable:
            parts.append("unreadable as YAML: " + ", ".join(unreadable))
        return Row("manifest-kinds", "manifest kinds", FINDING,
                   "; ".join(parts),
                   "register the kind in shape-doctor.py's "
                   "MANIFEST_VALIDATORS, beside the check that validates it, "
                   "or remove the file from the root", detail)
    return Row("manifest-kinds", "manifest kinds", OK,
               f"{len(known)} manifest(s), every declared kind has a "
               "registered validator", None, detail)


def check_shape_currency(ctx: Context) -> Row:
    """`update-shape.py check`, summarised, against THIS checkout.

    NO NETWORK AND NO CLONE. `update-shape.py` reads a local path as an
    upstream in place -- the same thing that makes its own tests offline -- so
    the shape this project is compared against is the checkout this file sits
    in, at its HEAD. What that costs is honesty about which standard answered,
    which is why both commits are in the row.
    """
    us = ctx.update_shape()
    args = argparse.Namespace(root=str(ctx.root), upstream=str(ctx.shape),
                              at=None)
    try:
        _root, _pin, rows, additions, upstream, pinned, target, _kind = \
            us.prepare(args)
    except Refusal as exc:
        return Row("shape-currency", "shape currency", FINDING,
                   f"the copies cannot be compared: {exc.detail}",
                   f"{PYTHON} {ctx.shape / 'update-shape.py'} check --root "
                   f"{ctx.root} --upstream {ctx.shape}",
                   {"error": exc.code})
    try:
        added = [add for add in additions if not add.present]
        reported = list(rows) + added
        counts = us.counted(reported)
        summary = " / ".join(f"{counts.get(state, 0)} {state}"
                             for state in (us.UNCHANGED, us.UPSTREAM_CHANGED,
                                           us.LOCALLY_MODIFIED, us.BOTH,
                                           us.UPSTREAM_ADDED))
        by_state: dict[str, list[str]] = {}
        for row in reported:
            by_state.setdefault(row.state, []).append(row.path)
        conflicts = [row.path for row in rows if row.is_conflict]
        detail = {"pinned": pinned, "standard": target,
                  "counts": {state: counts.get(state, 0)
                             for state in us.ORDER if counts.get(state)},
                  "paths": by_state, "conflicts": conflicts,
                  "behind": bool(counts.get(us.UPSTREAM_CHANGED)
                                 or counts.get(us.UPSTREAM_ADDED)),
                  "drifted": bool(counts.get(us.LOCALLY_MODIFIED)
                                  or counts.get(us.BOTH) or conflicts)}
        where = f"pinned {pinned[:12]}, this standard {target[:12]}"
        moved = [row for row in reported if row.state != us.UNCHANGED]
        if not moved:
            note = ("the pin names this standard's commit"
                    if pinned == target else
                    "no copied file differs, though the pin names an older "
                    "commit")
            return Row("shape-currency", "shape currency", OK,
                       f"{note}; {summary} ({where})", None, detail)
        accept = "".join(f" --accept-local {row.path}" for row in rows
                         if row.state == us.LOCALLY_MODIFIED)
        named = ", ".join(row.path for row in moved[:4])
        if len(moved) > 4:
            named += f", and {len(moved) - 4} more"
        return Row("shape-currency", "shape currency", FINDING,
                   f"{summary} ({where}): {named}",
                   f"{PYTHON} {ctx.shape / 'update-shape.py'} check --root "
                   f"{ctx.root} --upstream {ctx.shape}   # then apply --at "
                   f"{target} --yes{accept} --branch shape/update-"
                   f"{target[:12]}", detail)
    finally:
        upstream.close()


def head_of(path: Path) -> str | None:
    try:
        return git_out(["rev-parse", "HEAD"], cwd=path).lower()
    except (Refusal, OSError):
        return None


def pin_commit(root: Path, relative: str) -> str | None:
    pin = Context._read(root / relative)
    if not isinstance(pin, dict):
        return None
    commit = str(pin.get("commit") or "").lower()
    return commit if COMMIT_RE.match(commit) else None


def check_legs(ctx: Context) -> Row:
    """Each leg mounted, and its checked-out commit against the pin.

    NOTHING IS FETCHED. The question is what is on this disk right now: an
    empty mount is a clone nobody bootstrapped, and a mount at another commit
    is a leg somebody moved -- both of which `make bootstrap` answers, and
    neither of which needs a remote to be asked about. The GITLINK against the
    pin file is `validate-pins.py`'s question and is left to it; this row
    reports the gitlink it found so the two can be read together.
    """
    legs = ctx.legs()
    if not legs:
        return Row("legs", "legs", NA,
                   "project.yaml declares no non-assembly leg; a "
                   "one-repository project has none and is not less governed "
                   "for it", None, {"legs": []})
    rows: list[dict] = []
    problems: list[str] = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        mount = ctx.root / rel
        pinned = pin_commit(ctx.root, f"contracts/{role}-pin.yaml")
        gitlink = recorded_gitlink(ctx.root, rel)
        populated = mount.is_dir() and any(mount.iterdir())
        head = head_of(mount) if populated else None
        entry = {"role": role, "path": rel, "pin": pinned,
                 "gitlink": gitlink, "populated": populated, "head": head}
        rows.append(entry)
        if gitlink is None:
            problems.append(f"{rel}: no gitlink recorded, so this leg is not "
                            "mounted as a submodule at all")
        elif not populated:
            problems.append(f"{rel}: the gitlink is there and the directory "
                            "is empty -- an unbootstrapped clone")
        elif head is None:
            problems.append(f"{rel}: populated, but git cannot read a HEAD in "
                            "it")
        elif pinned is None:
            problems.append(f"{rel}: contracts/{role}-pin.yaml carries no "
                            "40-hex commit to compare HEAD against")
        elif head != pinned:
            problems.append(f"{rel}: checked out at {head[:12]}, pinned at "
                            f"{pinned[:12]}")
    detail = {"legs": rows}
    if problems:
        return Row("legs", "legs", FINDING, "; ".join(problems),
                   f"{PYTHON} scripts/bootstrap.py in {ctx.root}   # what "
                   "`make bootstrap` runs: it puts every leg on its tracking "
                   "branch AT the pinned commit", detail)
    return Row("legs", "legs", OK,
               f"{len(rows)} leg(s) mounted and checked out at their pins",
               None, detail)


def check_leg_shape_files(ctx: Context) -> Row:
    """Each present leg's shape files against `templates/<role>-root/`.

    A COMPARISON, NOT A GATE. No leg file has a digest row anywhere today --
    `contracts/shape-pin.yaml` covers the assembly root's copies and nothing
    else -- so a leg whose `.gitignore` has grown a line is not thereby wrong,
    and saying it were would be a rule this standard has not made. What IS
    reported as a finding is a file that is not there at all, because a leg
    with no `AGENTS.md` is a leg an agent reads nothing in.

    `AGENTS.md` and `README.md` are RENDERED from their templates -- they
    carry `{{PLACEHOLDER}}`s the scaffold fills in -- so "differs" is their
    permanent state and the row says `rendered` rather than pretending a byte
    comparison meant something.
    """
    legs = ctx.legs()
    if not legs:
        return Row("leg-shape-files", "leg shape files", NA,
                   "no legs to compare", None, {"legs": []})
    per_leg: dict[str, dict] = {}
    missing: list[tuple[str, str, str]] = []
    for leg in legs:
        role = str(leg.get("role") or "?")
        rel = str(leg.get("path") or role)
        mount = ctx.root / rel
        template = ctx.shape / "templates" / f"{role}-root"
        if not (mount.is_dir() and any(mount.iterdir())):
            per_leg[rel] = {"role": role, "state": "not populated"}
            continue
        if not template.is_dir():
            per_leg[rel] = {"role": role,
                            "state": f"no templates/{role}-root/ to compare "
                                     "against"}
            continue
        files: dict[str, str] = {}
        for name in LEG_SHAPE_FILES:
            here, there = mount / name, template / name
            if not here.is_file():
                files[name] = "absent"
                missing.append((role, rel, name))
            elif name in LEG_RENDERED:
                files[name] = "rendered"
            elif not there.is_file():
                files[name] = "present (the template has none)"
            elif here.read_bytes() == there.read_bytes():
                files[name] = "identical"
            else:
                files[name] = "differs"
        per_leg[rel] = {"role": role, "state": "compared", "files": files}
    detail = {"legs": per_leg, "compared": list(LEG_SHAPE_FILES)}
    summary = "; ".join(
        f"{rel}: " + (entry["state"] if entry["state"] != "compared" else
                      ", ".join(f"{name} {state}"
                                for name, state in entry["files"].items()))
        for rel, entry in per_leg.items())
    if missing:
        role, rel, name = missing[0]
        named = ", ".join(f"{leg}/{file}" for _, leg, file in missing)
        return Row("leg-shape-files", "leg shape files", FINDING,
                   f"{summary}  (missing: {named})",
                   f"cp {ctx.shape / 'templates' / (role + '-root') / name} "
                   f"{ctx.root / rel / name}   # AGENTS.md and README.md are "
                   "RENDERED per project, so those are re-rendered rather "
                   "than copied", detail)
    return Row("leg-shape-files", "leg shape files", OK, summary, None, detail)


def check_agent_files(ctx: Context) -> Row:
    present = {name: (ctx.root / name).is_file() for name in AGENT_FILES}
    absent = [name for name, there in present.items() if not there]
    detail = {"files": present}
    if not absent:
        return Row("agent-files", "agent files", OK,
                   ", ".join(f"{name} present" for name in AGENT_FILES),
                   None, detail)
    fix = (f"{PYTHON} {ctx.shape / 'update-shape.py'} check --root {ctx.root} "
           f"--upstream {ctx.shape}   # AGENTS-shape.md is a pinned copy: it "
           "is reported upstream-added and taken with `apply --add "
           "AGENTS-shape.md`") if "AGENTS-shape.md" in absent else (
        f"the scaffold renders {' and '.join(absent)}; write it, or take it "
        f"from templates/assembly-root/")
    return Row("agent-files", "agent files", FINDING,
               "absent: " + ", ".join(absent), fix, detail)


def check_members(ctx: Context) -> Row:
    """Each member pinned under `members/`, and the working clone beside it."""
    members = ctx.members()
    members_dir = str((ctx.manifest or {}).get("members_dir") or "members")
    if not members:
        return Row("members", "members", OK,
                   "no members yet: a family with none is empty, not wrong",
                   None, {"members": []})
    rows: list[dict] = []
    problems: list[str] = []
    siblings_absent: list[str] = []
    for row in members:
        project = str(row.get("project") or "?")
        rel = str(row.get("path") or f"{members_dir}/{project}")
        mount = ctx.root / rel
        pin = row.get("pin") if isinstance(row.get("pin"), dict) else {}
        pinned = str(pin.get("commit") or "").lower()
        pinned = pinned if COMMIT_RE.match(pinned) else None
        populated = mount.is_dir() and any(mount.iterdir())
        head = head_of(mount) if populated else None
        sibling = ctx.root.parent / project
        has_sibling = (sibling / ".git").exists()
        rows.append({"project": project, "path": rel, "pin": pinned,
                     "populated": populated, "head": head,
                     "working_clone": sibling.as_posix() if has_sibling
                     else None})
        if not populated:
            problems.append(f"{rel}: not populated -- the pinned copy is an "
                            "unbootstrapped submodule")
        elif pinned is None:
            problems.append(f"{project}: the row carries no 40-hex "
                            "`pin.commit` to compare against")
        elif head != pinned:
            problems.append(f"{rel}: checked out at "
                            f"{(head or '?')[:12]}, pinned at {pinned[:12]}")
        if not has_sibling:
            siblings_absent.append(project)
    detail = {"members": rows, "without_working_clone": siblings_absent}
    if problems:
        return Row("members", "members", FINDING, "; ".join(problems),
                   f"{PYTHON} scripts/bootstrap.py in {ctx.root}   # what "
                   "`make bootstrap` runs in a holder: it fetches every "
                   "member at its pin", detail)
    note = f"{len(rows)} member(s) mounted at their pins"
    if siblings_absent:
        # NOT A FINDING. The working clones are the WORKSTATION layout, and a
        # holder on a machine that has not placed them is not thereby
        # non-compliant -- `members/<Project>` is what the gate reads.
        return Row("members", "members", OK,
                   f"{note}; no working clone beside the holder for "
                   + ", ".join(siblings_absent)
                   + " (`make siblings` places them; the pinned copy under "
                     f"{members_dir}/ is detached by design)", None, detail)
    return Row("members", "members", OK,
               f"{note}, each with a working clone beside the holder", None,
               detail)


# ---------------------------------------------------------------------------
# What is here instead, when this is not a shape root
# ---------------------------------------------------------------------------


def origin_name(root: Path) -> str | None:
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=root)
    except (Refusal, OSError):
        return None
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".git") else name or None


def check_not_a_root_naming(ctx: Context) -> Row:
    """Classify what this directory is CALLED, under the naming policy.

    The directory name and, when there is one, `origin`'s repository name.
    They are usually the same and are not always: a clone into a differently
    named folder is ordinary, and the name that matters for the policy is the
    repository's.
    """
    script = ctx.shape / "scripts" / "validate-repository-naming.py"
    names = [ctx.root.name]
    remote = origin_name(ctx.root)
    if remote and remote not in names:
        names.append(remote)
    code, quoted, whole = run_validator(ctx, script, ["--explain", *names])
    detail = {"names": names, "origin": remote, "exit": code,
              "explain": ascii_text(whole).strip().splitlines()[:40]}
    reason = f"{', '.join(names)}: " + (
        "classifies under the naming policy" if code == 0
        else (quoted or "matches no family in the policy"))
    return Row("naming", "naming", OK if code == 0 else FINDING, reason,
               None if code == 0 else
               f"{PYTHON} {script} --explain {' '.join(names)}", detail)


def check_what_is_here(ctx: Context) -> Row:
    """What IS in this directory, said plainly, so the reader can place it."""
    root = ctx.root
    facts: list[str] = []
    detail = {}
    for name, note in ((".git", "a git repository"),
                       (".gitmodules", "a .gitmodules"),
                       ("contracts", "a contracts/ directory"),
                       ("spec", "a spec/ directory"),
                       ("code", "a code/ directory"),
                       ("AGENTS.md", "an AGENTS.md"),
                       ("Makefile", "a Makefile")):
        there = (root / name).exists()
        detail[name] = there
        if there:
            facts.append(note)
    detail["project_yaml"] = (root / "project.yaml").is_file()
    detail["family_yaml"] = (root / "family.yaml").is_file()
    if detail["project_yaml"] or detail["family_yaml"]:
        # A manifest is THERE and did not declare the kind that makes it one,
        # which is a different fault from having none, and worth saying.
        facts.append("a manifest file that declares neither `kind: "
                     "project-manifest` nor `kind: family-manifest`")
    return Row("contents", "what is here", NA,
               ", ".join(facts) if facts else
               "no git repository, no manifest, no contracts/ -- an ordinary "
               "directory", None, detail)


#: Named in the `machine` row because the doctor's OWN next commands need it
#: and the preflight does not ask about it: `adopt-project.py` extracts a
#: leg's history with `git filter-repo` and refuses without it, and
#: `adopt-project.py plan` is what the NOT A SHAPE ROOT verdict sends a person
#: at. Absent is not a finding -- it is needed to ADOPT and for nothing else.
ADOPTION_TOOL = "git-filter-repo"


def check_machine(ctx: Context) -> Row:
    """Can this machine run the fixes the rows above name?

    IT RUNS THE REAL PREFLIGHT rather than a second copy of the check list.
    `setup-project.py --preflight` is section (1) of the scaffold and nothing
    else -- git, a Python 3.9+, the bootstrap interpreter, `gh` and its login,
    the credential helper, and the autocrlf warning -- and re-listing those
    here would be two lists to keep in step, which is the duplication #50
    removed. It is run with stdin CLOSED, so the "no terminal, no offer" rule
    fires and nothing is offered, prompted for or installed: the doctor
    diagnoses, and installing something is a different act with a different
    consent.

    THIS IS THE ONE ROW THAT CAN REACH A NETWORK, and it is `n/a` by status
    for a separate reason. Asking `gh` whether it is logged in is a question
    `gh` answers by talking to its host; nothing else in this command leaves
    the disk. And a machine's state is not the repository's: a workstation
    with no `gh` cannot open the pull request a fix needs, which is worth
    saying and is not this repository being non-compliant. So the row reports
    and never changes the verdict.
    """
    entry = ctx.shape / "setup-project.py"
    adoption = shutil.which(ADOPTION_TOOL)
    detail = {"preflight": entry.as_posix(),
              ADOPTION_TOOL: adoption or None}
    if not entry.is_file():
        return Row("machine", "machine", NA,
                   f"{entry} is not here, so the preflight could not be run",
                   None, detail)
    code, quoted, whole = run_validator(ctx, entry, ["--preflight"])
    detail["exit"] = code
    # The preflight's own `[ok]`/`[!!]`/`[??]` lines, which are its report.
    marks = [ascii_text(line.strip()) for line in whole.splitlines()
             if line.strip().startswith(("[ok]", "[!!]", "[??]"))]
    detail["report"] = marks
    ready = "this machine is ready" if code == 0 else \
        "this machine is missing something the fixes above may need"
    extra = ("" if adoption else
             f"; {ADOPTION_TOOL} is not on PATH, which only `adopt-project.py`"
             " needs")
    reason = f"{ready} (setup-project.py --preflight, exit {code}){extra}"
    if code != 0 and quoted:
        reason += f": {quoted}"
    return Row("machine", "machine", NA, reason,
               None if code == 0 else
               f"{PYTHON} {entry} --preflight   # it names each missing "
               "prerequisite and offers to install it, on a typed yes",
               detail)


def check_the_way_in(ctx: Context) -> Row:
    """The two ways a directory becomes a shape root, and who decides.

    NEITHER IS RUN HERE AND NEITHER IS RECOMMENDED OVER THE OTHER. Adopting an
    existing repository keeps its identity and its history and cuts two legs
    out of it; scaffolding creates three new repositories. Which of those a
    person wants is a fact about their repository, not about this directory
    listing, so both are named and the human chooses.
    """
    root = ctx.root
    is_repo = (root / ".git").exists()
    project = "".join(part.capitalize()
                      for part in root.name.replace("_", "-").split("-")
                      if part) or "Project"
    if is_repo:
        fix = (f"{PYTHON} {ctx.shape / 'adopt-project.py'} plan --source "
               f"{root} --project {project}")
        reason = ("this is a git repository with no shape manifest: it is "
                  "ADOPTED in place, keeping its name, identity and history")
    else:
        fix = (f"{ctx.shape / 'setup.sh'} --org <your-org> --project "
               f"{project}   # without --yes; it asks")
        reason = ("there is no repository here to adopt: a new project is "
                  "SCAFFOLDED, which creates three repositories and asks "
                  "first")
    return Row("way-in", "the way in", NA, reason, fix,
               {"git_repository": is_repo, "suggested_project": project})


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


CHECKS = (
    Check("naming", "naming", (PROJECT,), check_naming),
    Check("manifest", "manifest", (PROJECT,), check_manifest),
    Check("pins", "pins", (PROJECT,), check_pins),
    Check("family", "family", (FAMILY,), check_family),
    Check("manifest-kinds", "manifest kinds", (PROJECT, FAMILY),
          check_manifest_kinds),
    Check("shape-currency", "shape currency", (PROJECT, FAMILY),
          check_shape_currency),
    Check("legs", "legs", (PROJECT,), check_legs),
    Check("leg-shape-files", "leg shape files", (PROJECT,),
          check_leg_shape_files),
    Check("agent-files", "agent files", (PROJECT, FAMILY), check_agent_files),
    Check("members", "members", (FAMILY,), check_members),
    Check("naming", "naming", (NOT_A_ROOT,), check_not_a_root_naming),
    Check("contents", "what is here", (NOT_A_ROOT,), check_what_is_here),
    Check("way-in", "the way in", (NOT_A_ROOT,), check_the_way_in),
    # LAST, AND ON EVERY KIND OF ROOT. It reports the machine rather than
    # the repository, so it is `n/a` by status and never moves the verdict
    # -- see `check_machine`. It reads last because it is about the
    # commands the rows ABOVE it named.
    Check("machine", "machine", (PROJECT, FAMILY, NOT_A_ROOT),
          check_machine),
)


def run_checks(ctx: Context) -> list[Row]:
    rows: list[Row] = []
    for check in CHECKS:
        if ctx.kind not in check.applies_to:
            continue
        try:
            rows.append(check.run(ctx))
        except Refusal as exc:
            rows.append(Row(check.id, check.label, FINDING,
                            f"refused: {exc.detail}", exc.remediation or None,
                            {"error": exc.code}))
        except OSError as exc:
            rows.append(Row(check.id, check.label, FINDING,
                            f"could not be run: {exc}", None, {}))
    return rows


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


def verdict_for(ctx: Context, rows: list[Row]) -> tuple[str, int]:
    """ONE line, and the exit code that goes with it.

    The order below IS the precedence, and the docstring at the top of this
    file argues the one that surprises: drift outranks a red validator,
    because an edited shape copy is what makes `validate-pins.py` red and
    naming the validator would send the reader at the symptom.
    """
    if ctx.kind == NOT_A_ROOT:
        return V_NOT_A_ROOT, 2
    by_id = {row.id: row for row in rows}
    currency = by_id.get("shape-currency")
    detail = currency.detail if currency else {}
    counts = detail.get("counts") or {}

    reasons: list[str] = []
    if detail.get("drifted"):
        for state in ("locally-modified", "both"):
            if counts.get(state):
                reasons.append(f"{counts[state]} {state}")
        for state in ("upstream-removed", "unmapped", "copy-missing"):
            if counts.get(state):
                reasons.append(f"{counts[state]} {state}")
    legs = by_id.get("legs")
    if legs is not None and legs.status == FINDING:
        off = [leg for leg in (legs.detail.get("legs") or [])
               if leg.get("head") != leg.get("pin")]
        reasons.append(f"{len(off) or 1} leg(s) not at the pin")
    members = by_id.get("members")
    if members is not None and members.status == FINDING:
        reasons.append("a member is not at its pin")
    if reasons:
        return f"{V_DRIFTED} ({', '.join(reasons)})", 1

    red = [row.id for row in rows
           if row.status == FINDING
           and row.id in ("naming", "manifest", "pins", "family",
                          "manifest-kinds", "agent-files", "leg-shape-files")]
    if red:
        return f"{V_INVALID} ({', '.join(red)})", 1

    if detail.get("behind"):
        changed = counts.get("upstream-changed", 0)
        added = counts.get("upstream-added", 0)
        return (f"{V_BEHIND} ({changed} upstream-changed, "
                f"{added} upstream-added)"), 1
    # THE CATCH-ALL, and it is here so that a check ADDED LATER cannot exit 0
    # while its row says FINDING. A new row that belongs in `red` above is a
    # one-line edit; a new row nobody classified still fails loudly.
    other = [row.id for row in rows if row.status == FINDING]
    if other:
        return f"{V_INVALID} ({', '.join(other)})", 1
    return V_COMPLIANT, 0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(ctx: Context, rows: list[Row], verdict: str, code: int) -> None:
    described = {PROJECT: "assembly root (project.yaml)",
                 FAMILY: "family holder (family.yaml)",
                 NOT_A_ROOT: "not a shape root"}[ctx.kind]
    print(f"root        {ctx.root}")
    print(f"kind        {described}")
    print(f"standard    {ctx.shape}")
    print()
    width = max([len(row.label) for row in rows] + [10])
    status_width = max(len(row.status) for row in rows)
    for row in rows:
        print(f"  {row.status:<{status_width}}  {row.label:<{width}}  "
              f"{row.reason}")
        if row.next_command:
            print(f"  {'':<{status_width}}  {'NEXT':<{width}}  "
                  f"{row.next_command}")
    print()
    print(f"{verdict}   (exit {code})")
    note = verdict_note(ctx)
    if note:
        print(note)


#: The line NOT A SHAPE ROOT adds, and the one thing in this file that is
#: about a HABIT rather than about a repository. `--doctor` meant "check this
#: machine" until 2026-09-10; a person who types it out of that habit, in a
#: directory that is not a shape root, would otherwise read a verdict about
#: their repository as an answer about their machine. One line tells them
#: where the old verb went. It is printed under the verdict, never instead of
#: it, and it changes no exit code.
PREFLIGHT_MOVED = ("the machine check is `openRepoShape --preflight` now; "
                   "`--doctor` is this report")


def verdict_note(ctx: Context) -> str | None:
    return PREFLIGHT_MOVED if ctx.kind == NOT_A_ROOT else None


def as_json(ctx: Context, rows: list[Row], verdict: str, code: int) -> str:
    return json.dumps({
        "root": ctx.root.as_posix(),
        "standard": ctx.shape.as_posix(),
        "kind": ctx.kind,
        "rows": [row.as_dict() for row in rows],
        "verdict": verdict,
        "note": verdict_note(ctx),
        "exit": code,
    }, indent=2, sort_keys=False)


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shape-doctor.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".",
                        help="the repository to check (default: .)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="the same report as one JSON object")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = [marker for marker in SHAPE_MARKERS
               if not (SHAPE_ROOT / marker).exists()]
    if missing:
        print("REFUSED shape-doctor-not-in-the-standard: this file is at "
              f"{SHAPE_ROOT}, which is missing {', '.join(missing)}. "
              "shape-doctor.py compares a repository against THE CHECKOUT IT "
              "IS RUN FROM, so it needs one.\n  Remediation: run it from a "
              "clone of openRepoShape, or `openRepoShape --doctor <path>`, "
              "which fetches one for you.", file=sys.stderr)
        return 3
    root = Path(args.root).expanduser()
    try:
        root = root.resolve()
    except OSError as exc:
        print(f"REFUSED shape-doctor-root-unreadable: --root {args.root}: "
              f"{exc}", file=sys.stderr)
        return 3
    if not root.is_dir():
        print(f"REFUSED shape-doctor-root-missing: --root {args.root} is not a "
              "directory on this machine.\n  Remediation: pass a path to a "
              "checkout. This command reads a tree; it never clones one.",
              file=sys.stderr)
        return 3
    ctx = Context(root)
    rows = run_checks(ctx)
    verdict, code = verdict_for(ctx, rows)
    if args.as_json:
        print(as_json(ctx, rows, verdict, code))
    else:
        report(ctx, rows, verdict, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
