#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""THE LOCKSTEP VALIDATOR — three things move in one commit, or this refuses.

For every leg of this project, THREE facts name the same commit and they are
advanced TOGETHER, in ONE commit, or not at all:

    1. the GITLINK      — the `160000` entry this repository records for the
                          submodule at the leg's path
    2. the PIN FILE     — `commit:` in `contracts/<role>-pin.yaml`
    3. every WORKFLOW `@<sha>` REFERENCE naming that leg's repository, in
       `.github/workflows/*.yml`

This is not a hypothesis. In the xFactory aggregation the same invariant
(gitlink, `review-lane-reusable.yml@<sha>`, and a `PIN` constant in a test) was
practice for months and written down nowhere; seven consecutive pin-syncs from
2026-08-25 moved the gitlink alone and left the `validate` check red on every
pull request until 2026-08-26 — unnoticed for a day because `validate` runs on
pull requests only, so `main` never reported it and the breakage surfaced on
somebody else's change. Shipping the check in the template is what turns that
into a one-time scaffold cost instead of a per-project tribal rule.

The DIGEST is checked too: the pin records the sha256 of the leg's tree at the
pinned commit under the `sorted-ls-tree-r-v1` definition, recomputed here from
the submodule's own object store. A gitlink and a pin file that agree on a
commit whose bytes are not the bytes the pin was written against is drift the
commit comparison alone cannot see.

NEUTRAL-PRODUCT PINS ARE RECHECKED TOO. `project.yaml`'s `neutral_product_pins:`
names every `open<Product>` this project declares descent from; each name's
`contracts/<product lowercased>-pin.yaml` is a claim of descent with a REFERENT
(2026-09-02) and this recomputes it the same way `scaffold-project.py` computed
it in the first place — OFFLINE from a local checkout when one is findable
(`--pin-source`, `SHAPE_PIN_SOURCE_<PRODUCT>`, or a checkout sitting beside this
assembly root), else from `gh api` when `gh` is authenticated. Neither is
available, this is a SKIP with a named notice, never a failure: a project with
no network and no local checkout of the product is not thereby lying about its
descent, and this check must never punish the absence of what would answer it.
A source somebody NAMED is the other way round (#295): a `--pin-source` or
`SHAPE_PIN_SOURCE_<PRODUCT>` that cannot answer is a FINDING, and a
`--pin-source` no declared pin used is a note.

EXIT CODES
    0  every leg's three facts agree, every digest recomputes, and no
       recheckable neutral-product pin disagrees
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — an uninitialized submodule,
       an unresolvable commit, an unreadable pin or workflow file (one that is
       not UTF-8, or that this user cannot open). An unanswerable pin question
       is never an implicit pass.
       No git to run is one too (`git-not-runnable`, #412), a git that is
       missing, will not run or cannot be executed: the gitlinks and the
       digests are read through git.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
#: The interpreter the `pin-gitlink-mismatch` repair lines name (#478).
from repo_shape import PYTHON  # noqa: E402
from repo_shape import (  # noqa: E402
    COMMIT_RE, SHA256_RE, TREE_DIGEST_DEFINITION, Refusal, file_sha256,
    find_repo_root, git_out, load_yaml, pin_product_key,
    pin_source_env_collisions, pin_source_env_name, pin_source_env_shared,
    recorded_gitlink, repo_basename, tree_digest, tree_digest_from_gh,
)

# `PIN_SOURCE_ENV_PREFIX` / `pin_source_env_name` live in `repo_shape` because
# the SAME checkout answers two questions about a neutral product: the digest
# recomputed here, and the chain-link declaration `NamingPolicy` verifies
# (2026-09-05). Two definitions of one variable name is how the second one
# starts disagreeing with the first.

#: `owner/repo[/path]@<40 hex>` as it appears in a `uses:` line.
WORKFLOW_REF_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?"
    r"@(?P<sha>[0-9a-fA-F]{40})"
)

LOCKSTEP = (
    "THE LOCKSTEP RULE: a leg's gitlink, its `contracts/<role>-pin.yaml` "
    "`commit:`, and EVERY `.github/workflows/*.yml` reference of the form "
    "`<org>/<leg>/...@<sha>` are ONE invariant. Move all three in ONE commit "
    "or the next pull request is red on somebody else's change."
)


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []
        #: Each finding's code, and the role of the leg whose `bump-leg.py`
        #: line puts it right, or None: in step with `findings` (#478).
        self.cleared_by: list[tuple[str, object]] = []
        #: Each `pin-gitlink-mismatch`, as `(its index in findings, role,
        #: path, gitlink, pin commit)`, for `_end_gitlink_mismatches` (#478).
        self.mismatches: list[tuple[int, object, str, str, str]] = []

    def finding(self, code: str, detail: str, leg=None) -> None:
        """`leg` is the role of the leg a `bump-leg.py` line moves when that
        line also clears this finding: the leg's gitlink against its pin,
        its pin's digest, and a workflow reference to its repository, the
        three facts it rewrites (#478)."""
        self.findings.append(f"FINDING {code}: {detail}")
        self.cleared_by.append((code, leg))

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")

    def skip(self, text: str) -> None:
        """An entry this run could not answer for, by design rather than by
        drift — printed, but never a FINDING and never the reason for a
        nonzero exit. A network absence is not evidence of anything."""
        self.notes.append(f"  skip {text}")

    def advise(self, text: str) -> None:
        """A NOTE: something a person should know that is no fault of the
        project's — printed beside the skips and, like them, never a FINDING
        and never the reason for a nonzero exit."""
        self.notes.append(f"  note {text}")

    def unused(self, text: str) -> None:
        """A `--pin-source` no declared pin read (#295): the person named a
        source that did not answer, and nothing about any pin is wrong for
        that. A note, as every one of those is."""
        self.advise(text)


class _Unreadable(NamedTuple):
    """One workflow file that could not be read (#359): the line that names it,
    and whether it failed on its ENCODING (`True`) or on being opened."""

    line: str
    encoding: bool


def _read_workflow(root: Path, path: Path) -> tuple[str, _Unreadable | None]:
    """`(text, None)` for a workflow file read as UTF-8, or `("", why)` for one
    that cannot be (#359).

    The line is `<path relative to root>: not UTF-8 at byte N (<reason>)`, in
    the words `repo_shape.load_yaml` gives the same failure (#192), so a file
    this script cannot read is named the way its other readers name one.
    POSIX, on every platform, and never the absolute path: the reader pastes
    it into git and into an editor that opens it from the root.
    A file this user cannot open (`OSError`) is the same line with the
    operating system's own reason, because it is the same unguarded read.
    """
    rel = path.relative_to(root).as_posix()
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        return "", _Unreadable(
            f"{rel}: not UTF-8 at byte {exc.start} ({exc.reason})", True)
    except OSError as exc:
        return "", _Unreadable(
            f"{rel}: cannot be read ({exc.strerror or type(exc).__name__})",
            False)


def _workflow_unreadable(files: list[_Unreadable]) -> Refusal:
    """The ONE refusal for every workflow file that could not be read (#359).

    EVERY FILE IS NAMED, in one refusal, so the operator repairs them in one
    pass instead of meeting them one run at a time; `_workflow_refs` reads
    them all before it raises. The first line follows the id and the rest
    follow it, one file to a line, so `shape-doctor.py`, which quotes the
    first `REFUSED` line of this script's output, quotes a file's name.
    """
    advice = ""
    if any(one.encoding for one in files):
        advice += (
            "In each `not UTF-8` line the byte is counted from 0 at the start "
            "of the file and is the first that is not UTF-8: re-save the file "
            "as UTF-8 (a UTF-16 file with a byte-order mark needs converting, "
            "not editing), or replace that byte with the character it was "
            "meant to be, and commit it. ")
    if not all(one.encoding for one in files):
        advice += (
            "A `cannot be read` file is not an encoding failure: this user "
            "cannot open it, so restore read access to it. ")
    return Refusal(
        "workflow-unreadable",
        "\n".join(one.line for one in files),
        f"Remediation: {len(files)} workflow file(s) under "
        ".github/workflows/ cannot be read, and every one is named above. "
        "This validator reads every `.yml` and `.yaml` file there, whether or "
        "not it names a leg, and neither skips one nor reads one lossily: a "
        "workflow it skipped could hide a `@<sha>` reference that is out of "
        "lockstep, which is what it exists to find, and a lossy read would "
        "call green a tree that the project's other readers refuse. "
        + advice + "Then run the same command again.")


def _workflow_refs(root: Path) -> list[tuple[Path, str, str]]:
    """Every (file, owner/repo, sha) `@<sha>` reference in the workflows, or
    ONE refusal naming each workflow file that cannot be read (#359).

    EVERY FILE IS READ, whether or not it names a leg: the file is opened
    before it is known to hold a reference, so a UTF-16 workflow that names no
    leg used to stop the run in a `UnicodeDecodeError` (a `ValueError`, which
    `main()` does not catch: a traceback, exit 1 -- the code this validator
    uses for a finding). It is a REFUSAL, exit 2, `workflow-unreadable`, as a
    pin that is not UTF-8 is `yaml-unreadable`: the question cannot be asked.
    """
    out: list[tuple[Path, str, str]] = []
    unreadable: list[_Unreadable] = []
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return out
    for path in sorted(workflows.iterdir()):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        text, problem = _read_workflow(root, path)
        if problem is not None:
            unreadable.append(problem)
            continue
        for match in WORKFLOW_REF_RE.finditer(text):
            out.append((path, match.group("repo"), match.group("sha").lower()))
    if unreadable:
        raise _workflow_unreadable(unreadable)
    return out


def _load_leg_pin(root: Path, role, path: str, repository: str,
                  report: Report) -> tuple[dict, str, str]:
    """Read `<role>-pin.yaml` and check its own fields, before any fact in it
    is compared against another.

    Split from `_check_leg` for #132: everything that answers "does the pin
    file itself look right" belongs together. Returns the pin, its path
    relative to `root`, and its `commit:` lowercased.
    """
    pin_path = root / "contracts" / f"{role}-pin.yaml"
    if not pin_path.is_file():
        raise Refusal(
            "pin-missing",
            f"leg {role!r} declares {repository} at {path!r} but "
            f"{pin_path.relative_to(root).as_posix()} does not exist",
        )
    pin = load_yaml(pin_path)
    if not isinstance(pin, dict):
        raise Refusal("pin-unreadable", f"{pin_path}: not a mapping")

    # POSIX, on every platform: a finding names a path in THIS repository,
    # and `str()` of a relative Path on Windows spells it with backslashes —
    # a path the reader cannot paste back into git.
    rel = pin_path.relative_to(root).as_posix()
    if pin.get("kind") != "pinned_contract_manifest":
        report.finding("pin-wrong-kind",
                       f"{rel}: kind is {pin.get('kind')!r}, expected "
                       "'pinned_contract_manifest'")
    if pin.get("revision_kind") != "commit":
        report.finding(
            "pin-tag-only",
            f"{rel}: revision_kind is {pin.get('revision_kind')!r}. A tag can "
            "be moved and a commit cannot; a pin is a commit or it is nothing.",
        )
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "pin-tag-only",
            f"{rel}: `commit:` is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.",
        )
    commit = commit.lower()
    if pin.get("submodule_path") != path:
        report.finding("pin-path-mismatch",
                       f"{rel}: submodule_path is {pin.get('submodule_path')!r} "
                       f"but project.yaml puts the {role} leg at {path!r}")
    if pin.get("source_repository") != repository:
        report.finding("pin-repository-mismatch",
                       f"{rel}: source_repository is "
                       f"{pin.get('source_repository')!r} but project.yaml "
                       f"declares {repository!r}")
    return pin, rel, commit


@contextmanager
def _git_runs(unread: str) -> Iterator[None]:
    """The `git-not-runnable` refusal, exit 2, for a check that reads this
    repository through git and could not start it (#412).

    `git_out` raises `FileNotFoundError` when there is no git on PATH,
    `PermissionError` when the `git` found there will not run, and a plain
    `OSError` (`ENOEXEC`) when it is no program this machine can execute, a
    binary for another architecture or a script with no shebang, and nothing
    here caught any of them: the run ended in a traceback, which exits 1, a
    FINDING's code, though nothing was found. The module's own exit codes
    make 1 "drift a reviewer can act on" and 2 "the question could not be
    asked ... never an implicit pass". So every call that runs git runs
    inside this, and `unread` says which check it was and what it could not
    read. ONE code, whichever check meets the missing git first; every one
    of them is the same fact about the machine.

    ONLY AN ERROR FROM STARTING GIT COUNTS, told apart two ways. The block
    is around the git calls alone, never around a whole check: a pin file or
    a submodule directory nobody may read is an `OSError` too, and it is not
    this, nor is telling that operator to put git on PATH any help. And
    inside a git call the class is not enough: `subprocess` raises the same
    `FileNotFoundError` or `PermissionError` when the DIRECTORY it was to run
    git in cannot be entered, and on POSIX names that directory in
    `filename` where a program that will not start names `git`. So the rule
    is the NAME: any `OSError` whose `filename` is `git` counts, `ENOEXEC`'s
    included, and an error that names a directory or any other file passes
    through unchanged, and so does any `OSError` that names none. The one
    nameless error that counts is a `FileNotFoundError` or a
    `PermissionError`: Windows' `CreateProcess` failures carry no filename,
    so a missing git there is `[WinError 2]` with `filename` None, and
    nothing says it was the directory.

    `recorded_gitlink`'s `except Refusal` is not in the way: an `OSError` is
    no `Refusal`, so a missing git reaches here instead of reading as "no
    gitlink recorded", which would be a false `pin-gitlink-absent`.
    """
    try:
        yield
    except OSError as exc:
        nameless = (exc.filename is None
                    and isinstance(exc, (FileNotFoundError, PermissionError)))
        if exc.filename != "git" and not nameless:
            raise
        raise Refusal(
            "git-not-runnable",
            f"{unread}: git could not be run ({exc.strerror or exc})",
            "Remediation: put git on PATH and run `scripts/validate-pins.py` "
            "again. This assembly root's lockstep gate reads each leg's "
            "gitlink and recomputes its pinned tree digest through git, so "
            "without it nothing says whether the pins agree, and a gate that "
            "cannot answer is never a pass.") from exc


def _gitlink_repairs(root: Path, role, gitlink: str, commit: str) -> str:
    """The two commands a `pin-gitlink-mismatch` ends on, when they can
    commit (#478; `_end_gitlink_mismatches` says when).

    WHICH COMMIT STAYS IS THE PERSON'S CALL, so both are named and neither
    is chosen. A gitlink moved and committed by hand (`git -C spec pull`,
    then `git add spec` in the root) wants the first, `--to` the gitlink's
    commit, if the move was meant and the second, `--to` the pin's, if it
    was not; a pin edited by hand reads the same with the two the other way
    round. Either is `bump-leg.py`, which puts all three facts at one commit
    in ONE commit and runs this validator before it commits: a gitlink put
    back by hand is the same single-fact move this check refuses. Its
    `--dry-run` comes first, as openRepoShape's AGENTS.md says of advancing
    a leg.

    FROM A CHECKOUT OF openRepoShape, as `validate-family.py` names
    `family.py`: no project carries `bump-leg.py`, and this file cannot know
    where the reader's checkout is, so the script is relative to one and the
    root, which it does know, is absolute and quoted.
    """
    bump = (f"{PYTHON} scripts/bump-leg.py --root {shlex.quote(str(root))} "
            f"--leg {shlex.quote(str(role))} --to")
    return ("Which commit stays is the person's call. From a checkout of "
            "openRepoShape, the first command keeps the gitlink's commit and "
            "the second the pin's; run either with `--dry-run` first. Either "
            "puts all three at it in one commit, on a branch other than the "
            "tracking branch, once this validator and validate-manifest.py "
            "pass on its rewrite (it rolls the bump back when either is red), "
            "and refuses a commit no branch of the leg's remote contains, so "
            f"push one made in the leg first:\n    {bump} {gitlink}\n"
            f"    {bump} {commit}")


def _gitlink_repairs_held_back(paths: list[str], others: list[str]) -> str:
    """Why a `pin-gitlink-mismatch` names no command, and what comes first
    (#478): `bump-leg.py` runs this validator before it commits and rolls
    the bump back when it is red, so no single line commits while another
    leg is off its pin or another finding stands."""
    what, first = [], []
    if others:
        what.append("this validator also reports " + ", ".join(others))
        first.append("clear " + ("that finding" if len(others) == 1
                                 else "those findings"))
    if len(paths) > 1:
        what.insert(0, " and ".join(paths) + (" are both" if len(paths) == 2
                                              else " are all")
                    + " off their pins")
        first.append("put one leg's gitlink back at its pin (check that leg "
                     "out at the pin's commit and commit its gitlink in this "
                     "root), or undo the commit that moved them")
    return ("No single bump-leg.py line can commit while "
            + " and ".join(what) + ": bump-leg.py moves one leg and runs "
            "this validator before it commits, rolling the bump back when it "
            "is red. First " + ", and ".join(first) + "; this validator then "
            "names the two bump-leg.py lines for "
            + ("the leg that is left." if len(paths) > 1 else "that leg."))


def _end_gitlink_mismatches(root: Path, report: Report) -> None:
    """What each `pin-gitlink-mismatch` ends on, once every check has run
    (#478).

    `bump-leg.py` RUNS THIS WHOLE VALIDATOR after its rewrite and before it
    commits, and rolls the bump back when it is red. So its two lines are
    named only where they can commit: ONE leg's gitlink is off its pin, and
    every other finding is one a bump of that leg clears (`Report.finding`'s
    `leg`). Two legs off, or any other finding, and either line is rolled
    back, so the finding names none and says what comes first instead.

    ONLY OVER A ROOT THAT HAS THIS GATE OF ITS OWN. `bump-leg.py` runs the
    root's `scripts/validate-pins.py` and skips an absent one, so this copy
    run against a root that has none cannot say what the bump's run will:
    the finding ends at THE LOCKSTEP RULE, as it did before #478, and the
    root's own gate is the thing to put back first.
    """
    if not report.mismatches \
            or not os.path.isfile(root / "scripts" / "validate-pins.py"):
        return
    roles = [role for _, role, _, _, _ in report.mismatches]
    others: list[str] = []
    for code, leg in report.cleared_by:
        if (leg is None or leg not in roles) and code not in others:
            others.append(code)
    if len(report.mismatches) == 1 and not others:
        index, role, _, gitlink, commit = report.mismatches[0]
        report.findings[index] += "\n  " + _gitlink_repairs(root, role,
                                                            gitlink, commit)
        return
    why = _gitlink_repairs_held_back(
        [path for _, _, path, _, _ in report.mismatches], others)
    for index, *_ in report.mismatches:
        report.findings[index] += "\n  " + why


def _check_gitlink_matches_pin(root: Path, role, path: str, commit: str,
                               rel: str, report: Report) -> str:
    """Fact 1 vs fact 2: the recorded gitlink against the pin file's
    `commit:`. Split from `_check_leg` for #132. Returns the gitlink so the
    caller can check it again against fact 3, the workflow references.
    """
    with _git_runs(f"the {role} leg's gitlink recorded at {path!r} could "
                   "not be read"):
        gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        raise Refusal(
            "pin-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. The {role} leg is "
            "declared in project.yaml but this repository does not record it "
            "as a submodule.",
        )
    if gitlink != commit:
        report.finding(
            "pin-gitlink-mismatch",
            f"{path}: gitlink {gitlink} != {rel} commit {commit}\n  " + LOCKSTEP,
            leg=role,
        )
        report.mismatches.append((len(report.findings) - 1, role, path,
                                  gitlink, commit))
    else:
        report.note(f"{path}: gitlink == {rel} commit {commit[:12]}")
    return gitlink


def _check_pin_digest(root: Path, path: str, commit: str, pin: dict, rel: str,
                      report: Report, role=None) -> None:
    """The digest: split from `_check_leg` for #132. Recomputes the leg's
    tree sha256 at the pinned commit, because a gitlink and a pin file that
    agree on a commit may still disagree on that commit's bytes. A mismatch
    is one `bump-leg.py` clears, since it recomputes the digest (#478).
    """
    submodule = root / path
    if not (submodule / ".git").exists():
        raise Refusal(
            "pin-submodule-uninitialized",
            f"{path} is not an initialized submodule checkout, so the pinned "
            "digest cannot be recomputed. Presence is not identity and an "
            "unreadable surface must fail rather than degrade.",
        )
    # `_git_runs` OUTSIDE the `try`: the refusal it raises is a `Refusal`, and
    # inside, the `except Refusal` below would turn "no git to run" into
    # `pin-commit-unresolvable`, which says the commit is missing.
    with _git_runs(f"{path}: the pinned commit {commit[:12]} could not be "
                   "looked up in that submodule"):
        try:
            git_out(["rev-parse", "--verify", "--quiet",
                     f"{commit}^{{commit}}"], cwd=submodule)
        except Refusal as exc:
            raise Refusal(
                "pin-commit-unresolvable",
                f"{path}: the pinned commit {commit} is not in that "
                f"submodule's object store ({exc.detail})",
            ) from exc
    recorded = (pin.get("digests") or {}).get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("pin-digest-malformed",
                       f"{rel}: digests.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding(
            "pin-digest-definition",
            f"{rel}: digest_definition is {pin.get('digest_definition')!r}, "
            f"expected {TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.",
        )
    else:
        with _git_runs(f"{path}: the tree digest at {commit[:12]} could not "
                       "be recomputed"):
            actual = tree_digest(submodule, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "pin-digest-mismatch",
                f"{rel}: digests.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                f"  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  " + LOCKSTEP,
                leg=role,
            )
        else:
            report.note(f"{path}: tree digest recomputes ({recorded[:12]}…)")


def _check_workflow_refs_for_leg(refs, repository: str, path: str,
                                 gitlink: str, report: Report,
                                 role=None) -> None:
    """Fact 3: split from `_check_leg` for #132 — every workflow `@<sha>`
    reference naming this leg's repository must agree with the gitlink. A
    mismatch is one `bump-leg.py` clears, since it moves every one (#478).
    """
    seen = 0
    for wf_path, wf_repo, wf_sha in refs:
        if wf_repo != repository:
            continue
        seen += 1
        if wf_sha != gitlink:
            report.finding(
                "pin-workflow-ref-mismatch",
                f"{wf_path.name}: `{wf_repo}@{wf_sha}` != the gitlink "
                f"{gitlink} recorded at {path!r}\n  " + LOCKSTEP,
                leg=role,
            )
    if seen:
        report.note(f"{repository}: {seen} workflow @<sha> reference(s) "
                    f"agree with the gitlink")


def _check_leg(root: Path, leg: dict, report: Report, refs) -> None:
    role = leg.get("role")
    path = str(leg.get("path") or "")
    repository = str(leg.get("repository") or "")
    pin, rel, commit = _load_leg_pin(root, role, path, repository, report)
    gitlink = _check_gitlink_matches_pin(root, role, path, commit, rel, report)
    _check_pin_digest(root, path, commit, pin, rel, report, role)
    _check_workflow_refs_for_leg(refs, repository, path, gitlink, report,
                                 role)


def _check_shape_pin_header(root: Path, manifest: dict, report: Report
                            ) -> tuple[dict, str]:
    """Load `shape-pin.yaml` and check the fields that describe its own
    commit, before the files it lists are checked one by one.

    Split from `_check_shape_pin` for #132. Returns the pin and its path
    relative to `root`.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        raise Refusal("shape-pin-missing", f"{pin_path} does not exist")
    pin = load_yaml(pin_path)
    rel = pin_path.relative_to(root).as_posix()
    if not isinstance(pin, dict):
        raise Refusal("shape-pin-unreadable", f"{pin_path}: not a mapping")
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{rel}: revision_kind is {pin.get('revision_kind')!r}")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        report.finding("shape-pin-commit",
                       f"{rel}: `commit:` {commit!r} is not 40 hex")
    declared = (manifest.get("shape") or {}).get("commit")
    if declared and str(declared).lower() != commit.lower():
        report.finding("shape-pin-manifest-disagree",
                       f"{rel} commit {commit} != project.yaml shape.commit "
                       f"{declared}")
    return pin, rel


def _check_shape_copy(root: Path, row, rel: str, report: Report) -> None:
    """One `files:` row of the shape pin.

    Split from `_check_shape_pin` for #132 so the loop over the pinned files
    is a single call per row: is it a mapping, is the file still there, and
    does its sha256 still match what the pin recorded.
    """
    if not isinstance(row, dict):
        report.finding("shape-pin-row", f"{rel}: a files row is not a mapping")
        return
    target = root / str(row.get("path"))
    if not target.is_file():
        report.finding("shape-copy-missing",
                       f"{rel}: {row.get('path')} is pinned but absent")
        return
    actual = file_sha256(target)
    if actual != str(row.get("sha256", "")).lower():
        report.finding(
            "shape-copy-drift",
            f"{row.get('path')}: sha256 {actual}\n"
            f"       {rel} records {row.get('sha256')}\n"
            "  A shape file was edited in place. Either revert it, or "
            "carry the change upstream to openRepoShape and re-pin.",
        )


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The shape pin is a COPY pin, and it is checked as one.

    openRepoShape is not a submodule of a scaffolded project: the scaffold
    COPIES a small set of files out of it so the project is self-contained in
    an org that may never obtain the upstream. There is therefore no gitlink to
    compare — the identity of the copies is carried by the per-file `sha256`
    rows, exactly the half of `neutral-product-pin`'s shape that exists for
    artifacts a consumer holds rather than mounts.
    """
    pin, rel = _check_shape_pin_header(root, manifest, report)
    before = len(report.findings)
    files = pin.get("files") or []
    if not isinstance(files, list):
        # Asked, not assumed (#290): `files: 5` was iterated, and the run
        # ended in a TypeError with no finding naming the pin.
        report.finding("shape-pin-row",
                       f"{rel}: `files:` is {files!r}, not a list of "
                       "`path:`/`sha256:` rows, so nothing about the copied "
                       "shape files is actually asserted")
        return
    if not files:
        report.finding("shape-pin-no-files",
                       f"{rel}: no `files:` rows, so nothing about the copied "
                       "shape files is actually asserted")
    for row in files:
        _check_shape_copy(root, row, rel, report)
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their digests")


class PinSources:
    """Every `--pin-source` value AS TYPED, read against the neutral-product
    pins `project.yaml` declares, and which of them a pin actually read.

    THE READING (#295). `PRODUCT=PATH` and a bare `PATH` are told apart by an
    `=`, and a path may hold one: a stand-in cloned under `a=b/` is
    `--pin-source a=b/openGlass`. Splitting every value at its first `=` made
    that a source keyed to a product `a` that nothing declares, which no pin
    ever looked up — the digest went to `gh api` and a `skip`, exit 0, with
    the skip line itself suggesting the `--pin-source` the person had just
    passed. So the text before the first `=` is a PRODUCT only when it
    casefolds to a declared pin's name, the same casefold the lookup below
    uses, and any other value is a bare PATH, whole. A declared name wins
    even when a directory is spelled like the whole value
    (`openGlass=x/openGlass` beside a directory `openGlass=x`): the reading is
    decided by the manifest and never by what happens to be on the disk, and
    `./openGlass=x/openGlass` is how to mean that directory.

    WHAT NO PIN READ (#295). A value no declared pin used — a mistyped key, a
    bare path every pin had a more specific answer for, an earlier value a
    later one replaced — is said once the pins are checked, by
    `_note_unused_pin_sources`. Saying nothing is how a mistyped key read as
    a pass that never looked.
    """

    def __init__(self, values: list[str], declared) -> None:
        #: The declared pins, spelled as `project.yaml` spells them.
        self.declared = [p for p in declared if isinstance(p, str) and p]
        names = {product.casefold(): product for product in self.declared}
        #: `{product casefolded: (typed, path)}`, the last value given wins.
        self.keyed: dict[str, tuple[str, Path]] = {}
        #: `(typed, path)` of the last bare value, if any.
        self.bare: tuple[str, Path] | None = None
        #: Every distinct value in the order given, and the declared pin it
        #: was read as keyed to, or None for a bare PATH.
        self.reading: dict[str, str | None] = {}
        #: `{typed: the later value that took its place}`.
        self.replaced: dict[str, str] = {}
        #: The values a pin's digest was asked of, readable or not.
        self.used: set[str] = set()
        for typed in values:
            key, sep, path = typed.partition("=")
            product = names.get(key.casefold()) if sep else None
            self.reading[typed] = product
            if product is not None:
                earlier = self.keyed.get(product.casefold())
                self.keyed[product.casefold()] = (typed, Path(path))
            else:
                earlier = self.bare
                self.bare = (typed, Path(typed))
            self.replaced.pop(typed, None)
            if earlier is not None and earlier[0] != typed:
                self.replaced[earlier[0]] = typed

    def read_as_path(self, typed: str | None) -> str:
        """The sentence saying a value holding `=` was read as a bare PATH,
        or `""` — what a person who meant `PRODUCT=PATH` and mistyped the
        product needs told, since nothing else in the run names it. Nothing
        when no pin is declared: the note has already said so."""
        if typed is None or self.reading.get(typed) is not None \
                or "=" not in typed or not self.declared:
            return ""
        key = typed.partition("=")[0]
        what = f"`{key}` is not" if key else "nothing before its `=` is"
        return (f"It was read as a PATH: {what} a declared neutral-product "
                f"pin (declared: {', '.join(self.declared)}).")


def resolve_neutral_pin_source(root: Path, product: str, repository: str,
                               sources: PinSources,
                               env_shared: bool = False,
                               ) -> tuple[Path | None, str | None, str | None]:
    """Where to read `product`'s tree OFFLINE, if anywhere at all.

    Tried in order, the most explicit ask first:

      1. `--pin-source <product>=<path>` (case-insensitive on the name, which
         must be a declared pin's for the value to be read this way, #295)
      2. `SHAPE_PIN_SOURCE_<PRODUCT>` in the environment
      3. a checkout sitting BESIDE this assembly root, named for the pinned
         repository (`opensoft/openGlass` -> `../openGlass`) — the ordinary
         shape of a workspace that clones a project and its neutral products
         side by side
      4. a bare `--pin-source <path>` with no `product=` prefix, which applies
         to whichever pin does not already have a more specific answer — the
         common case is exactly one declared neutral-product pin

    Rule 2 is skipped when `env_shared` is true, which is when another
    declared pin names the same variable (#275): a variable that cannot say
    which product it holds answers for neither, and `neutral-pin-source-
    collides` is noted for the pair. The pin still verifies through rule 1,
    3 or 4.

    Returns `(path, how, typed)`, `typed` being the `--pin-source` value as
    given when one of those answered, so the caller can mark it used (#295).
    `(None, None, None)` when nothing above answers; the caller's next step
    is `gh api`, and after that, a SKIP.
    """
    keyed = sources.keyed.get(product.casefold())
    if keyed is not None:
        typed, path = keyed
        return path, f"--pin-source {product}=...", typed
    env_name = pin_source_env_name(product)
    env_value = None if env_shared else os.environ.get(env_name)
    if env_value:
        return Path(env_value), f"${env_name}", None
    sibling = root.parent / repo_basename(repository)
    if (sibling / ".git").exists():
        return sibling, f"sibling checkout ({sibling})", None
    if sources.bare is not None:
        typed, path = sources.bare
        return path, "--pin-source", typed
    return None, None, None


def _digest_from_source(source: Path, commit: str) -> str:
    """`tree_digest` over a local source, with every way that source can fail
    to answer raised as a `Refusal` (#295).

    `tree_digest` runs `git` IN the source, and a directory that is not there
    is not a git failure but a `FileNotFoundError` out of `subprocess.run`
    (`NotADirectoryError` for a file, `PermissionError` for a directory this
    user cannot enter), which nothing caught: `--pin-source
    openGlass=<missing>` died on a traceback, exit 1, where a directory that
    is not a checkout is the `neutral-pin-source-unreadable` FINDING. An
    explicit source that cannot answer is that finding however it fails.

    `stat()` INSIDE THE GUARD, and not `exists()`/`is_dir()`: before 3.14
    those two swallow only a missing path and raise every other `OSError`,
    so a source under a parent this user cannot enter, or a name longer than
    the filesystem takes, was still a traceback on 3.9 to 3.13 and, on 3.14,
    a finding saying "no such directory" about a directory that exists. The
    reason the finding gives is the system's own.
    """
    try:
        mode = source.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        raise Refusal("pin-source-missing", "no such directory") from None
    except OSError as exc:
        raise Refusal("pin-source-unreadable",
                      f"{exc.strerror or exc}") from exc
    if not stat.S_ISDIR(mode):
        raise Refusal("pin-source-not-a-directory",
                      "it is a file, not a directory")
    try:
        return tree_digest(source, commit)
    except OSError as exc:
        raise Refusal("pin-source-unreadable",
                      f"{exc.strerror or exc}") from exc


def _check_neutral_pin_entry_and_load(root: Path, product, report: Report
                                      ) -> tuple[dict, str] | None:
    """Validate one `neutral_product_pins:` entry and load its pin file.

    Split from `_check_neutral_product_pins` for #132. Returns `None` when
    the entry itself is malformed — already reported, and there is no pin
    file name to go read — so the caller moves on to the next entry exactly
    as the original loop's `continue` did.
    """
    if not isinstance(product, str) or not product:
        report.finding(
            "neutral-pin-entry-malformed",
            f"project.yaml neutral_product_pins entry {product!r} is not "
            "a non-empty product name",
        )
        return None
    pin_path = root / "contracts" / f"{product.lower()}-pin.yaml"
    if not pin_path.is_file():
        raise Refusal(
            "neutral-pin-missing",
            f"project.yaml declares a pin on {product!r} but "
            f"{pin_path.relative_to(root).as_posix()} does not exist",
            "Remediation: `scaffold-project.py --pin "
            f"{product}@<commit>` writes that file. A declaration in "
            "project.yaml with no pin file beside it is a claim with no "
            "referent — either restore the file or remove the "
            "declaration.",
        )
    pin = load_yaml(pin_path)
    rel = pin_path.relative_to(root).as_posix()
    if not isinstance(pin, dict):
        raise Refusal("neutral-pin-unreadable", f"{pin_path}: not a mapping")
    return pin, rel


def _check_neutral_pin_commit_and_digest_fields(pin: dict, rel: str,
                                                report: Report
                                                ) -> tuple[str, str] | None:
    """The pin's own `revision_kind`/`commit`/digest fields, before any
    recompute of the referent is attempted.

    Split from `_check_neutral_product_pins` for #132. Returns `None` when
    the digest fields are themselves malformed — already reported, and
    recomputing anything to compare against them would be pointless — else
    `(commit, recorded_digest)`.
    """
    if pin.get("revision_kind") != "commit":
        report.finding(
            "neutral-pin-tag-only",
            f"{rel}: revision_kind is {pin.get('revision_kind')!r}. A tag "
            "can be moved and a commit cannot; a pin is a commit or it is "
            "nothing.",
        )
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "neutral-pin-tag-only",
            f"{rel}: `commit:` is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.",
        )
    commit = commit.lower()

    recorded = (pin.get("digests") or {}).get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("neutral-pin-digest-malformed",
                       f"{rel}: digests.tree_sha256 is {recorded!r}, not "
                       "64 hex")
        return None
    if pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding(
            "neutral-pin-digest-definition",
            f"{rel}: digest_definition is "
            f"{pin.get('digest_definition')!r}, expected "
            f"{TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.",
        )
        return None
    return commit, recorded


def _also_a_directory(typed: str | None, sources: PinSources) -> str:
    """The line for a value read as `PRODUCT=PATH` that ALSO names an
    existing directory whole (#295): the keyed reading won, and this is how
    to ask for the other one. `os.path.isdir`, which is False for every
    `OSError` on every Python, where `Path.is_dir` before 3.14 raised a name
    too long out of the finding it was adding a line to."""
    if typed is None or sources.reading.get(typed) is None \
            or not os.path.isdir(typed):
        return ""
    return (f"`{typed}` is also a directory; `--pin-source ./{typed}` "
            "reads it as one.")


def _recompute_neutral_pin_digest(root: Path, product: str, repository: str,
                                  commit: str, rel: str, sources: PinSources,
                                  report: Report,
                                  shared: frozenset[str] = frozenset()
                                  ) -> tuple[str, str] | None:
    """Recompute the referent's tree digest: offline where a source can be
    found, else from `gh api`, else a named SKIP that never fails the run.

    Split from `_check_neutral_product_pins` for #132. Returns `(actual,
    how)`, or `None` when nothing could answer — a finding or a skip is
    already reported in that case, exactly as the original loop's
    `continue` left it.
    """
    env_shared = pin_product_key(product) in shared
    source, how, typed = resolve_neutral_pin_source(root, product, repository,
                                                    sources, env_shared)
    if source is not None:
        if typed is not None:
            sources.used.add(typed)
        try:
            return _digest_from_source(source, commit), how
        except Refusal as exc:
            report.finding(
                "neutral-pin-source-unreadable",
                f"{rel}: {source} ({how}) could not answer for "
                f"{repository} @ {commit}: {exc.detail}"
                + "".join(f"\n  {line}" for line in (
                    sources.read_as_path(typed),
                    _also_a_directory(typed, sources),
                    f"Remediation: point it at a clone of {repository} that "
                    "has that commit (`git fetch` in it first), or drop it "
                    "so the next source in the order answers.") if line),
            )
            return None
    try:
        return tree_digest_from_gh(repository, commit), "gh-api-tree-recursive"
    except Refusal as exc:
        # A variable another pin shares is not offered, and neither is the
        # bare `--pin-source`, which answers for every pin that has no more
        # specific answer: the keyed form is the one that says which pin it
        # is for (#275).
        offered = (f"A --pin-source {product}=<path> or" if env_shared else
                   f"A --pin-source, {pin_source_env_name(product)}, or")
        report.skip(
            f"{product}: pin commit {commit[:12]} digest NOT "
            f"rechecked — no local checkout ({exc.code}: "
            f"{exc.detail}). {offered} a checkout at "
            f"../{repo_basename(repository)} beside "
            "this assembly root would verify it offline.",
        )
        return None


def _check_one_neutral_product_pin(root: Path, product, report: Report,
                                   sources: PinSources,
                                   shared: frozenset[str] = frozenset()
                                   ) -> None:
    """One `neutral_product_pins:` entry, start to finish.

    Split from `_check_neutral_product_pins` for #132 so the loop in that
    function is a single call per entry instead of the whole re-check
    inline; each `return` below is one of the original loop's `continue`s.
    """
    loaded = _check_neutral_pin_entry_and_load(root, product, report)
    if loaded is None:
        return
    pin, rel = loaded
    repository = str(pin.get("source_repository") or "")
    fields = _check_neutral_pin_commit_and_digest_fields(pin, rel, report)
    if fields is None:
        return
    commit, recorded = fields
    recomputed = _recompute_neutral_pin_digest(root, product, repository,
                                               commit, rel, sources, report,
                                               shared)
    if recomputed is None:
        return
    actual, how = recomputed
    if actual.lower() != recorded.lower():
        report.finding(
            "neutral-pin-digest-mismatch",
            f"{rel}: digests.tree_sha256 {recorded}\n"
            f"       recomputed at {commit[:12]} {actual} ({how})\n"
            "  A neutral-product pin's digest no longer matches the "
            "bytes it names — the referent this project's name claims "
            "descent from has moved, or the pin was hand-edited.",
        )
    else:
        report.note(f"{product}: pin commit {commit[:12]} digest "
                   f"recomputes ({how})")


def _report_pin_source_collisions(products, report: Report) -> None:
    """One `neutral-pin-source-collides` NOTE for each variable two or more
    declared products share (#275), naming every one of them and the
    variable. It is a note and never a finding: such a project did nothing
    the standard forbade when it was made (`scaffold-project.py` has refused
    it only since #275), every pin in it still verifies through the keyed
    `--pin-source <product>=<path>` or a checkout beside this assembly root,
    and a finding would make `update-shape.py apply` refuse every shape
    update (`update-validators-red`) until a person dropped a true
    declaration of descent. Which declaration stays is that person's
    decision, so the note says so and nothing here asks for one to go.
    `pin_source_env_collisions` is `repo_shape`'s, the one answer
    `scaffold-project.py` refuses on too: products are distinct by their pin
    files, so a product listed twice is not a collision here. The names are
    quoted with `repr`, as `neutral-pin-entry-malformed` quotes an entry: they
    are the manifest's own text and may hold a newline, and a note is one
    line."""
    for variable, group in pin_source_env_collisions(products).items():
        names = " and ".join(repr(product) for product in group)
        report.advise(
            "neutral-pin-source-collides: project.yaml neutral_product_pins "
            f"declares {names}, and one variable, {variable}, names the local "
            "checkout of each: it cannot say which it holds, so it is read "
            "for none of them. Each pin still verifies from the keyed "
            "`--pin-source <product>=<path>` or from a checkout beside this "
            "assembly root; a bare `--pin-source` answers for every pin that "
            "has no more specific source. Which declaration stays is the "
            "human's decision, and nothing here fails on it.")


def _check_neutral_product_pins(root: Path, manifest: dict, report: Report,
                                pin_source_values: list[str]) -> None:
    """Re-check every `neutral_product_pins:` entry `project.yaml` declares.

    `<Domainx><Product>` is a CLAIM of descent and a claim needs a REFERENT
    (Brett Heap, 2026-09-02): the referent is `contracts/<product lowercased>-
    pin.yaml`, and this recomputes its digest the same way
    `scaffold-project.py` computed it when the pin was first written — from a
    local checkout when one can be found, else from `gh api`. Neither
    available is a SKIP, never a finding and never a refusal: the absence of
    a way to answer is not evidence that the pin is wrong.

    TWO PRODUCTS THAT SHARE ONE VARIABLE ARE A NOTE (#275), and neither
    reads it. `SHAPE_PIN_SOURCE_<PRODUCT>` is the product's name upper-cased
    with every character outside `[A-Z0-9_]` turned into `_`, so `open-glass`,
    `open_glass` and `open.glass` are three pin files and one variable.
    Whichever checkout it named answered for all of them, and the pin it was
    not a checkout of was reported as `neutral-pin-source-unreadable`: drift
    in the project, said about a variable. Now no pin reads it, each pin
    verifies from its own source, and `neutral-pin-source-collides` says so
    and goes no further: it is not a finding, because a project that already
    declares such a pair could not otherwise take a shape update, and which
    declaration to drop is a human's to decide.

    The `--pin-source` values are READ here rather than in `main`, because
    whether `a=b/openGlass` is keyed to a product or a bare path depends on
    the pins this manifest declares (#295); each one no pin used is noted
    once every pin has been checked.
    """
    products = manifest.get("neutral_product_pins") or []
    sources = PinSources(pin_source_values, products)
    _report_pin_source_collisions(products, report)
    shared = frozenset(pin_source_env_shared(products))
    for product in products:
        _check_one_neutral_product_pin(root, product, report, sources, shared)
    _note_unused_pin_sources(sources, report)


def _note_unused_pin_sources(sources: PinSources, report: Report) -> None:
    """A note for each `--pin-source` value no declared pin read (#295),
    naming it as typed and why: a later value replaced it, its pin was never
    recomputed, nothing is declared, or every pin had a more specific
    answer. A value holding `=` that was read as a PATH says so, because
    that is the mistyped key's only trace in the run.
    """
    for typed, product in sources.reading.items():
        if typed in sources.used:
            continue
        later = sources.replaced.get(typed)
        if later is not None:
            why = f"the later `--pin-source {later}` replaced it"
        elif product is not None:
            why = f"{product}'s digest was not recomputed from any source"
        elif not sources.declared:
            why = "project.yaml declares no neutral-product pin"
        else:
            why = ("each declared pin had a more specific source (a keyed "
                   "--pin-source, SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout "
                   "beside this assembly root) or was not recomputed")
        report.unused(" ".join(filter(None, (
            f"--pin-source {typed}: not used — {why}.",
            sources.read_as_path(typed)))))


def _load_legs_to_check(root: Path) -> tuple[dict, list[dict]]:
    """The manifest and its non-assembly legs, or a Refusal naming why there
    is nothing here to check. Split from `main` for #132.
    """
    manifest_path = root / "project.yaml"
    if not manifest_path.is_file():
        raise Refusal(
            "manifest-missing",
            f"{manifest_path} does not exist, so there is no declaration of "
            "which legs to check. A one-repository project has no legs and "
            "does not run this validator.",
        )
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("manifest-unreadable", f"{manifest_path}: not a mapping")
    legs = [leg for leg in (manifest.get("legs") or [])
            if isinstance(leg, dict) and leg.get("role") != "assembly"]
    if not legs:
        raise Refusal("manifest-no-legs",
                      f"{manifest_path}: no non-assembly legs declared")
    return manifest, legs


def _run_all_checks(root: Path, report: Report,
                    pin_source_values: list[str]) -> None:
    """Every check `main` runs inside its one `try`, in order. Split from
    `main` for #132 so that `try` wraps a single call.
    """
    manifest, legs = _load_legs_to_check(root)
    refs = _workflow_refs(root)
    for leg in legs:
        _check_leg(root, leg, report, refs)
    _check_shape_pin(root, manifest, report)
    _check_neutral_product_pins(root, manifest, report, pin_source_values)
    _end_gitlink_mismatches(root, report)


def _emit_report(report: Report, quiet: bool) -> int:
    """Print the notes and findings and choose the exit code. Split from
    `main` for #132.

    A CHARACTER STDOUT CANNOT ENCODE IS PRINTED ESCAPED (#295). A note names
    a `--pin-source` as typed, and a `sibling checkout (<path>)` line names a
    path, so a stdout in cp1252 (what Windows gives one that is not the
    console) raised `UnicodeEncodeError` on `日本` and turned a passing run
    into a traceback. A `strict` or `surrogateescape` stdout, the two that
    raise, becomes `backslashreplace`, the handler stderr already has; any
    other handler, one somebody chose, is left alone. The tools run from a
    checkout of the standard use `escape_what_stdout_cannot_encode` (#214),
    which also writes a byte `surrogateescape` read in back as that byte; it
    lives in `shape_materialize.py`, which no project carries, and this file
    imports nothing but `repo_shape`, so here such a byte prints as `\\udcXX`,
    as it already does on stderr.
    """
    if getattr(sys.stdout, "errors", None) in ("strict", "surrogateescape"):
        try:
            sys.stdout.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
    if not quiet:
        for note in report.notes:
            print(note)
    for finding in report.findings:
        print(finding, file=sys.stderr)
    if report.findings:
        print(f"\n{len(report.findings)} finding(s). " + LOCKSTEP, file=sys.stderr)
        return 1
    print("pins ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="assembly root (default: the enclosing repository)")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--pin-source", action="append", default=[],
        metavar="[PRODUCT=]PATH",
        help="a local checkout to recompute a neutral-product pin's digest "
             "from, instead of `gh api` — e.g. --pin-source openGlass=../"
             "openGlass. The text before the first `=` is a PRODUCT only when "
             "it names a pin project.yaml declares, and then that reading "
             "wins even over a directory spelled like the whole value "
             "(./PATH reads that directory); any other value is a bare PATH, "
             "which applies to whichever declared pin has no more specific "
             "answer (the common case is exactly one). Repeatable; a value no "
             "pin used is noted, and one that cannot be read is a finding. "
             "SHAPE_PIN_SOURCE_<PRODUCT> (env) and a checkout sitting beside "
             "this assembly root are also tried, before `gh api` and before "
             "this flag's bare form.")
    args = parser.parse_args(argv)

    report = Report()
    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        _run_all_checks(root, report, args.pin_source)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return _emit_report(report, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
