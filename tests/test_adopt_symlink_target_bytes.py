# SPDX-License-Identifier: Apache-2.0
"""A symlink whose target holds a NUL after its first byte, or is longer than
Linux takes (#908: L1-76, L1-78 and L1-80 of #457), and the same link at a
copy under `shape/` or at a pin's file (#979).

ON THE V1.1.1 RELEASE COMMIT (5017830), git 2.43 on Linux, probed with a stub
`gh`: `check` read a link's target only for a NUL as its FIRST byte (#388)
and never asked its length, so both passed it and failed after both leg
repositories existed:

- `spec\\0.md` is handed to `symlink(2)` as a C string, so git makes the link
  `spec`. With the link in `docs/`, `execute` stopped at the split's `git rm
  -r -q -- docs` (the checkout holds a link that is not the index's); kept in
  the root, it ended `adopt-lost` in the verification. Whatever the plan
  answered.
- a target of 4096 or 5000 bytes is not made (`File name too long`), and the
  clone exits 128; 4095 is made on ext4 (macOS and XFS take at most 1023,
  which `check` does not ask). A single name of 300 bytes is made too.
- a root-kept `.github -> ci\\0xx` was refused as `plan-root-symlink`, which
  said it led to `ci\\x00xx`, "not in the source tree": Linux makes
  `.github -> ci`.
- a link kept in the root AT `project.yaml` got two findings, and the second's
  `drop` helps no link that cannot be made.
- `_PlannedRoot._link` started `git cat-file blob` for each link, per walk and
  per disk: 3 processes for one link, 15 for five.

Now `plan-bad-symlink-target` names each such link once, before any leg
exists, and says what git makes of it; `plan-root-symlink` does not say it
again; one finding names the link at `project.yaml`; and every link's target
is read in the one `git cat-file --batch` `check` already starts.

#979 lifted the limit #908 pinned: a bad link at `shape/README.md` was also
`plan-root-blocks-shape-copy`, and one at `contracts/shape-pin.yaml` also
`plan-root-holds-pin`, with a remedy (send it to a leg, `drop` it) that
cannot help it. Each leaves out a link the first finding names, as
`plan-root-blocks-manifest` does.

The links are made in the INDEX with `git update-index --cacheinfo`, so no
test builds a source on a disk that holds a NUL in a target, and all but the
three that ask git to check a link out (marked `needs_disk_symlinks`) run on
Windows too.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import ADOPT, as_human, git, make_source_repo, run_script
from test_adopt_empty_symlinks import (
    NAMED, REMOTES, SYMLINK, TREE, WORK, blob, check, execute_args, executed,
    findings_of, needs_disk_symlinks, needs_filter_repo, no_leg_was_created,
    planned, put_link, symlinks_off,
)
from test_adopt_root_symlinks import (
    A_PIN, GITHUB, ROOT, check as check_root, declare,
    planned as planned_root, ticked,
)

CODE = "plan-bad-symlink-target"
EMPTY = "plan-empty-symlink"
MANIFEST = "plan-root-blocks-manifest"
ROOT_SYMLINK = "plan-root-symlink"
SHAPE_MANIFEST = "project.yaml"
#: What git makes of each, on Linux.
LATE_NUL = b"spec\0.md"
CI_NUL = b"ci\0xx"
#: 5000 bytes, a name of one byte each between the slashes.
LONG = b"a/" * 2500
#: The most `symlink(2)` takes (`PATH_MAX` 4096 counts the NUL), and one more.
AT_MAX = (b"a" * 99 + b"/") * 40 + b"b" * 95
OVER_MAX = AT_MAX + b"c"
#: A single name of 300 bytes: `NAME_MAX` is no bound on a link's target.
ONE_NAME = b"c" * 300
assert len(AT_MAX) == 4095
assert len(LONG) == 5000

NUL_OID, LONG_OID, MAX_OID, OVER_OID, NAMED_OID, UNREAD_OID = (
    str(n) * 40 for n in range(1, 7))


@pytest.fixture(scope="module")
def adopter():
    module_spec = importlib.util.spec_from_file_location(
        "adopt_symlink_target_bytes", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """Every refusal here comes before `git filter-repo` would be used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


def row(path: str, size: int, oid: str, mode: str = SYMLINK) -> tuple:
    """A row of `Source.tree()`: `(path, mode, blob id, size)`."""
    return (path, mode, oid, size)


def source_of(tmp_path: Path, links: dict, tree: dict | None = None) -> Path:
    """The issue's small source with each of `links` (path -> target bytes)
    as a symlink, in its index and its one more commit."""
    source = make_source_repo(tmp_path / "Thing", tree=tree or TREE, edits=())
    for path, target in links.items():
        put_link(source, path, target)
    as_human("commit", "-qm", "Add the links", cwd=source)
    return source


def counted(trace: Path) -> dict:
    """How many `git cat-file blob <id>` and `git cat-file --batch` a run
    that wrote `GIT_TRACE` to `trace` started. A blob read by id is a link's
    target; one read as `<commit>:<path>` is a file of the source's, which
    other checks read and this rule does not touch."""
    lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = {"blob": r"built-in: git cat-file blob [0-9a-f]{40,64}$",
               "--batch": r"built-in: git cat-file --batch$"}
    return {kind: sum(1 for line in lines if re.search(rx, line))
            for kind, rx in pattern.items()}


# --- the rule, in memory ---------------------------------------------------

def test_the_limit_is_the_most_linux_takes(adopter):
    """4095: `PATH_MAX` is 4096, counting the NUL that ends the string. A
    host that takes less (macOS and XFS: 1023) is not asked."""
    assert adopter.SYMLINK_TARGET_MAX == 4095


def test_each_unmade_target_is_named_and_no_other(adopter):
    """A NUL after the first byte, and more than 4095 bytes. Not an empty
    target or one that begins with NUL (`plan-empty-symlink`'s: one link, one
    code), not one of 4095 bytes, not a name of 300, and not a file whose
    blob holds a NUL."""
    tree = [row("late", 5, NUL_OID), row("long", 5000, LONG_OID),
            row("empty", 0, "0" * 40), row("led", 8, "a" * 40),
            row("max", 4095, MAX_OID), row("over", 4096, OVER_OID),
            row("named", 7, NAMED_OID), row("unread", 7, UNREAD_OID),
            row("file", 5, NUL_OID, mode="100644")]
    targets = {NUL_OID: CI_NUL, LONG_OID: LONG, "a" * 40: b"\0spec.md",
               MAX_OID: AT_MAX, OVER_OID: OVER_MAX, NAMED_OID: NAMED}
    assert adopter.bad_symlink_targets(tree, targets) == [
        ("late", CI_NUL), ("long", LONG), ("over", OVER_MAX)]
    assert adopter.empty_symlinks(tree, targets) == ["empty", "led"]


def test_the_walk_stops_at_the_targets_the_source_names(adopter):
    """`_PlannedRoot` marks a link it will not follow, and names none: the
    same predicate, so the two cannot disagree about a link."""
    for raw in (b"", b"\0x", b"x\0y", b"a" * 4096):
        assert adopter._unmade_target(raw), raw[:8]
    for raw in (b"spec.md", b"a" * 4095, b"../ci", ONE_NAME):
        assert not adopter._unmade_target(raw), raw[:8]


def test_a_late_nul_says_what_git_makes_of_the_link(adopter):
    found, remediation = adopter._bad_symlink_target_findings(
        [row(".github", 5, NUL_OID)], {NUL_OID: CI_NUL})
    finding, = found
    assert finding.startswith(
        f"FINDING {CODE}: `.github` is a symlink whose target holds a NUL "
        "byte after its first 2 bytes at the source commit; a symlink's "
        "target ends at its first NUL, so git makes `.github` a link to "
        "`ci`, not to the 5 bytes the blob holds. ")
    assert "\\x00" not in finding
    assert ("the 5 bytes the blob holds. On Linux, where git makes symlinks "
            "by default, each clone `execute` makes of the source holds "
            "that other link") in finding
    assert "There," not in finding
    assert "after both leg repositories were created" in finding
    assert "whatever the plan answers for it" in finding
    assert "`core.symlinks` is false" in finding
    assert remediation == [adopter.BAD_SYMLINK_TARGET_REMEDIATION]
    assert "`drop` included" in remediation[0]
    assert ("a clone makes the link git makes of the target, or none, not "
            "the blob's") in remediation[0]
    assert "no more than 4095 bytes" in remediation[0]


def test_a_long_target_says_the_bound_and_is_not_spelled(adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row("docs/link", 5000, LONG_OID)], {LONG_OID: LONG})
    finding, = found
    assert finding.startswith(
        f"FINDING {CODE}: `docs/link` is a symlink whose target is 5000 "
        "bytes at the source commit, and Linux takes at most 4095 bytes in "
        "a symlink's target (`PATH_MAX` is 4096, counting the NUL that ends "
        "it), so git makes no symlink there: `symlink(2)` fails with `File "
        "name too long`. ")
    assert "a/a/a" not in finding, "5000 bytes of target are not printed"
    assert "then cannot be cloned on Linux" in finding


def test_a_target_the_nul_cuts_to_more_than_linux_takes_makes_no_link(
        adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row("docs/link", 5004, LONG_OID)], {LONG_OID: LONG + b"\0tail"})
    finding, = found
    assert ("`docs/link` is a symlink whose target holds a NUL byte after "
            "its first 5000 bytes at the source commit, and those alone are "
            "too many: Linux takes at most 4095 bytes") in finding
    assert "a link to" not in finding


@pytest.mark.parametrize("cut, made", [
    pytest.param(AT_MAX, True, id="4095-bytes-before-the-nul"),
    pytest.param(OVER_MAX, False, id="4096-bytes-before-the-nul"),
])
def test_the_cut_a_nul_makes_is_a_link_at_4095_bytes_and_none_at_4096(
        adopter, cut, made):
    """The boundary of "those alone are too many": git hands `symlink(2)` the
    bytes before the NUL, so 4095 of them make a link and 4096 do not."""
    raw = cut + b"\0x"
    found, _ = adopter._bad_symlink_target_findings(
        [row("docs/link", len(raw), MAX_OID)], {MAX_OID: raw})
    finding, = found
    more = len(cut) - 100
    if made:
        assert (f"a link to `{AT_MAX[:100].decode('ascii')}` and {more} more "
                f"bytes, not to the {len(raw)} bytes") in finding
        assert "those alone are too many" not in finding
    else:
        assert (f"holds a NUL byte after its first {len(cut)} bytes at the "
                "source commit, and those alone are too many") in finding
        assert "a link to" not in finding


def test_a_long_target_a_nul_cuts_to_a_short_one_is_a_link_to_the_short_one(
        adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row("l", 5003, LONG_OID)], {LONG_OID: b"ab\0" + LONG})
    assert ("git makes `l` a link to `ab`, not to the 5003 bytes the blob "
            "holds") in found[0]


def test_what_git_makes_is_spelled_to_a_hundred_bytes_and_counted(adopter):
    cut = b"c" * 300
    found, _ = adopter._bad_symlink_target_findings(
        [row("l", 302, NUL_OID)], {NUL_OID: cut + b"\0x"})
    assert ("a link to `" + "c" * 100 + "` and 200 more bytes, not to the "
            "302 bytes") in found[0]


def test_past_twenty_the_rest_are_counted(adopter):
    tree = [row(f"l{n:02d}", 5, NUL_OID) for n in range(22)]
    tree.append(row("l22", 5000, LONG_OID))
    found, _ = adopter._bad_symlink_target_findings(
        tree, {NUL_OID: CI_NUL, LONG_OID: LONG})
    assert len(found) == 21
    assert found[19].startswith(f"FINDING {CODE}: `l19` ")
    assert found[20] == (f"FINDING {CODE}: … and 3 more symlinks whose "
                         "target holds a NUL byte after its first or is "
                         "longer than Linux takes")


def test_twenty_are_named_and_no_count_line_follows(adopter):
    tree = [row(f"l{n:02d}", 5, NUL_OID) for n in range(20)]
    found, _ = adopter._bad_symlink_target_findings(tree, {NUL_OID: CI_NUL})
    assert len(found) == 20
    assert not any("more symlinks" in finding for finding in found)


def test_a_nul_after_one_byte_says_its_first_byte(adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row("l", 3, NUL_OID)], {NUL_OID: b"x\0y"})
    assert ("holds a NUL byte after its first byte at the source commit; a "
            "symlink's target ends at its first NUL, so git makes `l` a link "
            "to `x`, not to the 3 bytes the blob holds") in found[0]


def test_a_cut_of_exactly_a_hundred_bytes_is_spelled_with_no_count(adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row("l", 102, NUL_OID)], {NUL_OID: b"c" * 100 + b"\0x"})
    assert ("a link to `" + "c" * 100 + "`, not to the 102 bytes") in found[0]


def test_a_source_with_none_has_no_finding_and_no_remediation(adopter):
    tree = [row("a", 7, NAMED_OID), row("b", 4095, MAX_OID),
            row("c", 0, "0" * 40)]
    assert adopter._bad_symlink_target_findings(
        tree, {NAMED_OID: NAMED, MAX_OID: AT_MAX}) == ([], [])


def test_the_finding_spells_a_name_it_cannot_print(adopter):
    """A source name is bytes and may hold a line break: one line still."""
    finding, = adopter._bad_symlink_target_findings(
        [row("a\nb", 5, NUL_OID)], {NUL_OID: CI_NUL})[0]
    assert "\n" not in finding
    assert "`a\\nb` is a symlink" in finding


def test_a_link_at_the_manifest_says_so_and_what_helps(adopter):
    found, _ = adopter._bad_symlink_target_findings(
        [row(SHAPE_MANIFEST, 5, NUL_OID)], {NUL_OID: CI_NUL},
        {SHAPE_MANIFEST})
    assert found[0].endswith(
        " The plan keeps it in the assembly root, where the shape writes "
        "its manifest, `project.yaml`, and no copy stands in for that "
        f"(`{MANIFEST}`, not said again here): a target of its own would "
        "not end that, so remove the link or rename it in the source, "
        "commit, and re-run `plan`.")
    plain, _ = adopter._bad_symlink_target_findings(
        [row(SHAPE_MANIFEST, 5, NUL_OID)], {NUL_OID: CI_NUL})
    assert "where the shape writes its manifest" not in plain[0]


# --- the targets are read once ---------------------------------------------

def test_a_second_read_of_the_targets_starts_no_process(
        adopter, tmp_path, monkeypatch):
    """`Source` keeps each blob `symlink_targets` read, so the walks of
    `_PlannedRoot` and every later question ask git for nothing (#908)."""
    source = source_of(tmp_path, {"docs/a": CI_NUL, "docs/b": NAMED})
    opened = adopter.Source.open(str(source), tmp_path / WORK)
    tree = opened.tree()
    started = []
    real_run = subprocess.run

    def counting(args, *rest, **kwargs):
        started.append(list(args))
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(adopter.subprocess, "run", counting)
    first = adopter.symlink_targets(opened, tree)
    second = adopter.symlink_targets(opened, tree)
    assert first == second
    assert len(first) == 2
    assert started == [["git", "cat-file", "--batch"]]


def test_check_reads_no_target_with_a_git_call_of_its_own(tmp_path):
    """L1-80. `.github -> ci` kept in the root with `ci/`, which the shape's
    `.github/workflows/validate.yml` runs through: `_PlannedRoot._link`
    started `git cat-file blob` for it, in each of the walks `check` makes
    (3 processes). Now every target comes from the one batch."""
    files = {"ci/workflows/ci.yml": "on: [push]\n"}
    _, plan = planned_root(tmp_path, files, {GITHUB: b"ci"},
                           {GITHUB: ROOT, "ci/": ROOT})
    trace = tmp_path / "trace.log"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         env={"GIT_TRACE": str(trace)})
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert counted(trace) == {"blob": 0, "--batch": 1}


def test_five_walked_links_are_still_one_batch(tmp_path):
    """Five links the walks meet (15 `cat-file blob <id>` before) and one
    batch."""
    files = {"ci/workflows/ci.yml": "on: [push]\n", "tools/run.sh": "echo\n",
             "gov/x.md": "g\n", "build/Makefile": "all:\n",
             "AGENTS.md": "# a\n"}
    links = {GITHUB: b"ci", "scripts": b"tools", "contracts": b"gov",
             "CLAUDE.md": b"AGENTS.md", "Makefile": b"build/Makefile"}
    legs = {GITHUB: ROOT, "ci/": ROOT, "scripts": ROOT, "tools/": ROOT,
            "contracts": ROOT, "gov/": ROOT, "CLAUDE.md": ROOT,
            "AGENTS.md": ROOT, "Makefile": ROOT, "build/": ROOT}
    _, plan = planned_root(tmp_path, files, links, legs)
    trace = tmp_path / "trace.log"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         env={"GIT_TRACE": str(trace)})
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert counted(trace) == {"blob": 0, "--batch": 1}


# --- `check` ---------------------------------------------------------------

#: What each target is, how its finding begins after the link's name, and
#: what git makes. `{link}` is the link's path.
BAD = [
    pytest.param(LATE_NUL, "holds a NUL byte after its first 4 bytes",
                 "so git makes `{link}` a link to `spec`, not to the 8 bytes",
                 id="late-nul"),
    pytest.param(LONG, "is 5000 bytes", "so git makes no symlink there",
                 id="5000-bytes"),
    pytest.param(OVER_MAX, "is 4096 bytes", "so git makes no symlink there",
                 id="one-over-the-limit"),
    pytest.param(LONG + b"\0tail", "holds a NUL byte after its first 5000 "
                 "bytes", "so git makes no symlink there",
                 id="nul-after-too-many"),
]
with_each_bad_target = pytest.mark.parametrize("target, head, makes", BAD)

#: Where the link sits and what the plan answers for it: a leg's path, and a
#: top-level link answered each way. `drop` is among them: the clone stops at
#: the link before the split takes out anything.
PLACES = [
    pytest.param("docs/link", {}, id="in-docs-sent-to-spec"),
    *(pytest.param("link", {"link": leg}, id=f"top-level-answered-{leg}")
      for leg in ("root", "code", "spec", "drop")),
]


@with_each_bad_target
@pytest.mark.parametrize("link, answers", PLACES)
def test_check_names_the_link_once_and_says_what_git_makes(
        tmp_path, link, answers, target, head, makes):
    plan = planned(source_of(tmp_path, {link: target}),
                   tmp_path / "plan.yaml", answers)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {CODE}: {ticked(link)} is a symlink whose target {head}")
    assert makes.format(link=link) in finding
    assert "plan ok" not in result.stdout
    assert result.stderr.count("Remediation: a symlink's target is a fact "
                               "of the source") == 1


def test_check_says_the_same_where_git_makes_no_symlinks(tmp_path):
    """It reads the tree, not the disk, as #303's finding does."""
    plan = planned(source_of(tmp_path, {"docs/link": LATE_NUL}),
                   tmp_path / "plan.yaml", env=symlinks_off())
    off, on = check(plan, env=symlinks_off()), check(plan)
    assert off.returncode == on.returncode == 1
    assert findings_of(off) == findings_of(on)
    assert len(findings_of(on)) == 1


def test_a_late_nul_in_a_root_kept_link_says_what_the_link_really_is(
        tmp_path):
    """L1-78. `.github -> ci\\0xx`, with the `ci/` it leads to kept too:
    `plan-root-symlink` said `.github` led to `ci\\x00xx`, which "is not in
    the source tree", where Linux makes `.github -> ci`. Now the one finding
    says it is a link to `ci`, and the walk names nothing."""
    files = {"ci/workflows/ci.yml": "on: [push]\n"}
    _, plan = planned_root(tmp_path, files, {GITHUB: CI_NUL},
                           {GITHUB: ROOT, "ci/": ROOT})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {CODE}: {ticked(GITHUB)} is a symlink whose target holds "
        "a NUL byte after its first 2 bytes at the source commit; a "
        "symlink's target ends at its first NUL, so git makes `.github` a "
        "link to `ci`, not to the 5 bytes the blob holds. ")
    assert ROOT_SYMLINK not in result.stderr
    assert "\\x00xx" not in result.stderr


@pytest.mark.parametrize("kept", [
    pytest.param({GITHUB: ROOT, "ci/": ROOT}, id="ci-kept-in-the-root"),
    pytest.param({GITHUB: ROOT}, id="ci-in-a-leg"),
])
@pytest.mark.parametrize("target", [
    pytest.param(CI_NUL, id="late-nul"),
    pytest.param(LONG, id="5000-bytes"),
])
def test_a_root_kept_link_the_shape_runs_through_is_one_finding(
        tmp_path, kept, target):
    files = {"ci/workflows/ci.yml": "on: [push]\n"}
    _, plan = planned_root(tmp_path, files, {GITHUB: target}, kept)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {CODE}: {ticked(GITHUB)} is a ")
    assert ROOT_SYMLINK not in result.stderr


def test_a_link_in_a_chain_that_git_does_not_make_is_named_not_walked(
        tmp_path):
    """`.github -> ci`, and `ci` is the link with the late NUL: the walk
    meets it second, and names nothing of it, as it names no empty one."""
    _, plan = planned_root(tmp_path, {}, {GITHUB: b"ci", "ci": LATE_NUL},
                           {GITHUB: ROOT, "ci": ROOT})
    result = check_root(plan)
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {CODE}: `ci` is a symlink ")
    assert ROOT_SYMLINK not in result.stderr


# --- one finding for a link at project.yaml (L1-80) -------------------------

AT_THE_MANIFEST = [
    pytest.param(b"", EMPTY, "is empty at the source commit",
                 id="empty-target"),
    pytest.param(b"\0spec.md", EMPTY, "begins with a NUL byte",
                 id="nul-led-target"),
    pytest.param(LATE_NUL, CODE, "holds a NUL byte after its first 4 bytes",
                 id="late-nul"),
    pytest.param(LONG, CODE, "is 5000 bytes", id="5000-bytes"),
]


@pytest.mark.parametrize("target, code, head", AT_THE_MANIFEST)
def test_a_link_kept_at_the_manifest_is_one_finding_and_says_what_helps(
        tmp_path, target, code, head):
    """Lane 1's measurement on 5017830: `plan-empty-symlink` AND
    `plan-root-blocks-manifest` for an empty or NUL-led target (the second's
    `drop` helps no link that cannot be made), and for a late NUL or a long
    target the second alone, which said nothing of why. Now one finding."""
    _, plan = planned_root(tmp_path, {}, {SHAPE_MANIFEST: target},
                           {SHAPE_MANIFEST: ROOT})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {code}: `project.yaml` is a symlink whose target {head}")
    assert f"FINDING {MANIFEST}" not in result.stderr
    assert ("The plan keeps it in the assembly root, where the shape writes "
            "its manifest, `project.yaml`, and no copy stands in for that"
            ) in finding
    assert "once case is ignored" not in finding
    assert finding.endswith(
        "a target of its own would not end that, so remove the link or "
        "rename it in the source, commit, and re-run `plan`.")


@pytest.mark.parametrize("target, code", [
    pytest.param(b"", EMPTY, id="empty-target"),
    pytest.param(LATE_NUL, CODE, id="late-nul"),
    pytest.param(LONG, CODE, id="5000-bytes"),
])
def test_a_case_twin_of_the_manifest_is_one_finding_and_keeps_its_aside(
        tmp_path, target, code):
    """`Project.yaml` is the manifest's place only once case is ignored, as a
    macOS or Windows disk does, and `plan-root-blocks-manifest` said so of it
    before this finding took it over: on Linux the tail must not say the
    shape writes its manifest AT `Project.yaml`."""
    _, plan = planned_root(tmp_path, {}, {"Project.yaml": target},
                           {"Project.yaml": ROOT})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {code}: `Project.yaml` is a symlink whose target ")
    assert ("The plan keeps it in the assembly root, at `project.yaml` once "
            "case is ignored, as a macOS or Windows disk does, where the "
            "shape writes its manifest, and no copy stands in for that "
            ) in finding
    assert f"FINDING {MANIFEST}" not in result.stderr
    assert finding.endswith(
        "a target of its own would not end that, so remove the link or "
        "rename it in the source, commit, and re-run `plan`.")


def test_a_bad_link_below_a_directory_kept_at_the_manifest_is_not_left_out(
        tmp_path):
    """The skip is for a link AT `project.yaml`. One below a directory the
    plan keeps there is named by its own finding, and the directory still
    blocks the manifest, which no change to the link ends."""
    _, plan = planned_root(tmp_path, {}, {"project.yaml/x": LATE_NUL},
                           {"project.yaml/": ROOT})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    own, blocked = findings_of(result)
    assert own.startswith(f"FINDING {CODE}: `project.yaml/x` is a symlink ")
    assert "where the shape writes its manifest" not in own
    assert blocked.startswith(f"FINDING {MANIFEST}: ")


@pytest.mark.parametrize("target, code", [
    pytest.param(LATE_NUL, CODE, id="late-nul"),
    pytest.param(b"", EMPTY, id="empty-target"),
])
@pytest.mark.parametrize("before, named", [
    pytest.param(19, True, id="the-twentieth-is-named-one-by-one"),
    pytest.param(20, False, id="the-twenty-first-is-only-counted"),
])
def test_a_link_at_the_manifest_is_left_to_its_own_finding_only_if_it_is_named(
        tmp_path, target, code, before, named):
    """The links are named in tree order, `a00`, `a01`, ... then
    `project.yaml`, then `z00`: the 20th is named, the 21st is only counted,
    and for it nothing else would name the link at the manifest, so
    `plan-root-blocks-manifest` stays its own."""
    links = {f"a{n:02d}": target for n in range(before)}
    links[SHAPE_MANIFEST] = target
    links["z00"] = target
    _, plan = planned_root(tmp_path, {}, links, {path: ROOT for path in links})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings_of(result)
    own = [f for f in found if f.startswith(
        f"FINDING {code}: `{SHAPE_MANIFEST}` is a symlink ")]
    blocks = [f for f in found if f.startswith(f"FINDING {MANIFEST}: ")]
    counted = found[20]
    if named:
        assert len(own) == 1 and blocks == []
        assert "where the shape writes its manifest" in own[0]
        assert counted.startswith(f"FINDING {code}: … and 1 more ")
    else:
        assert own == []
        block, = blocks
        assert "the symlink `project.yaml` in the assembly root" in block
        assert counted.startswith(f"FINDING {code}: … and 2 more ")
    assert len(found) == 21 + len(blocks)


@pytest.mark.parametrize("target", [
    pytest.param(b"", id="empty"),
    pytest.param(LATE_NUL, id="late-nul"),
])
def test_a_link_at_the_manifest_the_plan_sends_to_a_leg_says_nothing_of_it(
        tmp_path, target):
    """The tail is for a link kept in the root, where the shape writes the
    manifest. Sent to a leg, it is still a finding of its own, with no word
    of the manifest."""
    _, plan = planned_root(tmp_path, {}, {SHAPE_MANIFEST: target},
                           {SHAPE_MANIFEST: "spec"})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert "where the shape writes its manifest" not in finding
    assert f"FINDING {MANIFEST}" not in result.stderr


def test_a_link_at_the_manifest_with_a_target_git_makes_is_unchanged(
        adopter, tmp_path):
    """The control: `plan-root-blocks-manifest`, alone, as before, and
    nothing of this rule's about it."""
    source, plan = planned_root(tmp_path, {}, {SHAPE_MANIFEST: NAMED},
                                {SHAPE_MANIFEST: ROOT})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {MANIFEST}: ")
    opened = adopter.Source.open(str(source), tmp_path / WORK)
    tree = opened.tree()
    targets = adopter.symlink_targets(opened, tree)
    assert adopter.bad_symlink_targets(tree, targets) == []


# --- one finding for a link at a copy or at a pin's file (#979) ------------

COPY = "plan-root-blocks-shape-copy"
HOLDS_PIN = "plan-root-holds-pin"
#: What keeps the source's `contracts/` a directory the plan can keep.
PIN_FILES = {"contracts/x.md": "x\n"}
#: Where a link sits that a second finding named after its own until #979:
#: AT the copy under `shape/` of a path the root holds, and AT the shape's
#: own pin. Each is the source's other files, the link, what the plan keeps
#: in the root, and the code of that second finding.
AT_A_COPY_OR_A_PIN = [
    pytest.param({}, "shape/README.md", {"shape/": ROOT, "README.md": ROOT},
                 COPY, id="the-readme-copy"),
    pytest.param({"Makefile": "all:\n"}, "shape/Makefile",
                 {"shape/": ROOT, "Makefile": ROOT}, COPY,
                 id="the-makefile-copy"),
    pytest.param(PIN_FILES, "contracts/shape-pin.yaml", {"contracts/": ROOT},
                 HOLDS_PIN, id="the-shape-pin"),
]
#: The first words of #908's remediation and #303's, alike.
FACT_OF_THE_SOURCE = "Remediation: a symlink's target is a fact of the source"


@pytest.mark.parametrize("target, own, head", AT_THE_MANIFEST)
@pytest.mark.parametrize("files, link, kept, second", AT_A_COPY_OR_A_PIN)
def test_a_named_link_at_a_copy_or_a_pin_is_one_finding(
        tmp_path, files, link, kept, second, target, own, head):
    """The limit `test_only_the_manifest_finding_leaves_a_named_link_out`
    pinned, lifted on purpose (#979): a bad link at `shape/README.md` was
    also `plan-root-blocks-shape-copy`, and one at
    `contracts/shape-pin.yaml` also `plan-root-holds-pin`, whose remedy
    (send it to a leg, `drop` it) helps no link a clone does not make. Now
    its own finding names it alone, says nothing of the manifest, and the
    remediation that helps is said once after it."""
    _, plan = planned_root(tmp_path, files, {link: target}, kept)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {own}: `{link}` is a symlink whose target {head}")
    assert f"FINDING {second}" not in result.stderr
    assert "where the shape writes" not in finding
    assert result.stderr.count(FACT_OF_THE_SOURCE) == 1


@pytest.mark.parametrize("target, own", [
    pytest.param(LATE_NUL, CODE, id="late-nul"),
    pytest.param(b"", EMPTY, id="empty-target"),
])
@pytest.mark.parametrize("files, link, kept, second", [
    pytest.param({}, "Shape/README.md", {"Shape/": ROOT, "README.md": ROOT},
                 COPY, id="the-copy-once-case-is-ignored"),
    pytest.param(PIN_FILES, "contracts/Shape-pin.yaml", {"contracts/": ROOT},
                 HOLDS_PIN, id="the-pin-once-case-is-ignored"),
])
def test_a_named_link_at_a_case_twin_of_a_copy_or_a_pin_is_one_finding(
        tmp_path, files, link, kept, second, target, own):
    """`Shape/README.md` is the copy's place, and `contracts/Shape-pin.yaml`
    the pin's, only on a disk that ignores case, which each second finding
    asks as well and said so of the link. Left out there too."""
    _, plan = planned_root(tmp_path, files, {link: target}, kept)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {own}: `{link}` is a symlink ")
    assert f"FINDING {second}" not in result.stderr


@pytest.mark.parametrize("files, link, kept, second", [
    pytest.param({}, "shape/README.md/x", {"shape/": ROOT, "README.md": ROOT},
                 COPY, id="below-the-copy"),
    pytest.param(PIN_FILES, "contracts/shape-pin.yaml/x",
                 {"contracts/": ROOT}, HOLDS_PIN, id="below-the-shape-pin"),
])
def test_a_bad_link_below_a_directory_kept_at_a_copy_or_a_pin_is_not_left_out(
        tmp_path, files, link, kept, second):
    """The skip is for a link AT the copy or the pin's file, as at the
    manifest. A directory the plan keeps there is in the way whatever the
    link below it holds, so both findings stay."""
    _, plan = planned_root(tmp_path, files, {link: LATE_NUL}, kept)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    own, blocked = findings_of(result)
    assert own.startswith(f"FINDING {CODE}: `{link}` is a symlink ")
    assert blocked.startswith(f"FINDING {second}: ")


@pytest.mark.parametrize("before, named", [
    pytest.param(19, True, id="the-twentieth-is-named-one-by-one"),
    pytest.param(20, False, id="the-twenty-first-is-only-counted"),
])
@pytest.mark.parametrize("files, link, kept, second", [
    AT_A_COPY_OR_A_PIN[0], AT_A_COPY_OR_A_PIN[2]])
def test_a_link_at_a_copy_or_a_pin_is_left_out_only_if_it_is_named(
        tmp_path, files, link, kept, second, before, named):
    """As at the manifest: the links are named in tree order, `a00`, ...
    then the link, then `z00`. Only counted, the link is named by nothing
    else if the second finding leaves it out too, so that finding stays."""
    links = {f"a{n:02d}": LATE_NUL for n in range(before)}
    links[link] = LATE_NUL
    links["z00"] = LATE_NUL
    legs = {path: ROOT for path in links if path != link}
    _, plan = planned_root(tmp_path, files, links, {**legs, **kept})
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings_of(result)
    own = [f for f in found if f.startswith(f"FINDING {CODE}: `{link}` ")]
    seconds = [f for f in found if f.startswith(f"FINDING {second}: ")]
    counted = found[20]
    if named:
        assert len(own) == 1 and seconds == []
        assert counted.startswith(f"FINDING {CODE}: … and 1 more ")
    else:
        assert own == []
        blocked, = seconds
        assert f"the symlink `{link}`" in blocked
        assert counted.startswith(f"FINDING {CODE}: … and 2 more ")
    assert len(found) == 21 + len(seconds)


@pytest.mark.parametrize("files, link, kept, second", AT_A_COPY_OR_A_PIN)
def test_a_link_at_a_copy_or_a_pin_with_a_target_git_makes_is_unchanged(
        tmp_path, files, link, kept, second):
    """The control: the second finding, alone, as before #979."""
    _, plan = planned_root(tmp_path, files, {link: NAMED}, kept)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {second}: ")
    assert f"the symlink `{link}`" in finding
    assert FACT_OF_THE_SOURCE not in result.stderr


@pytest.mark.parametrize("link, declared", [
    pytest.param("contracts/shape-pin.yaml", [], id="the-shape-pin"),
    pytest.param("contracts/openglass-pin.yaml", ["openGlass"],
                 id="a-declared-pin"),
    pytest.param("contracts/OpenGlass-pin.yaml", ["openGlass"],
                 id="a-declared-pin-once-case-is-ignored"),
])
def test_the_pin_finding_leaves_out_a_named_link_at_any_pin_file(
        adopter, monkeypatch, link, declared):
    """`_kept_pin_findings` asks each pin file `execute` writes, a declared
    pin's as well as the shape's own, and leaves out a link `named_links`
    holds at any of them, and no other."""
    monkeypatch.setattr(adopter, "_declared_pins", lambda plan: declared)
    plan = adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place",
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": [{"path": "contracts/", "leg": ROOT}]})
    tree = [row(link, 5, NUL_OID)]
    said = adopter._pin_findings(plan, tree)
    assert len(said) == 1, said
    assert said[0].startswith(
        f"FINDING {HOLDS_PIN}: the plan keeps the symlink `{link}` ")
    assert adopter._pin_findings(plan, tree, {link}) == []
    assert adopter._pin_findings(plan, tree, {"contracts/x"}) == said


def test_a_named_link_at_the_pin_is_found_there_and_no_case_twin_is_asked(
        adopter):
    """The pin's finding asks the disk that ignores case only where the one
    that keeps case finds nothing at the pin's file (#524). A named link
    there is something found: the finding leaves it out (#979) and does not
    go on to name the case twin the plan keeps beside it, which it never
    named beside a link either, so `_links_at_a_pin` still reads the disk
    the finding reads. The twin is found once the link is gone."""
    plan = adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place",
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": [{"path": "contracts/", "leg": ROOT}]})
    twin = row("contracts/Shape-pin.yaml", 5, NAMED_OID, "100644")
    link = row(adopter.SHAPE_PIN, 5, NUL_OID)
    named = {adopter.SHAPE_PIN}
    said, = adopter._pin_findings(plan, [twin, link])
    assert f"the symlink `{adopter.SHAPE_PIN}` " in said
    assert adopter._pin_findings(plan, [twin, link], named) == []
    alone, = adopter._pin_findings(plan, [twin], named)
    assert "the file `contracts/Shape-pin.yaml` " in alone
    assert "once case is ignored" in alone


#: Where a named link sits beside a SECOND path the shape also writes, kept
#: in the root, so that `check` makes two findings and not one: the link's
#: own and the second path's (#1089, SHOULD-2 of r1070). What the skips leave
#: out is the link and no other path, and each case is a mutant of them that
#: #1070's whole file let live, because the second finding was the only one
#: it lost: a link at `shape/README.md` beside a case twin of that copy (M12),
#: a link at a declared pin's file beside a file at the shape's own pin (M13),
#: and a link at the README copy beside a file at the Makefile copy (M14). In
#: each the second path is asked after the link's, on the same disk or the
#: next. The link's own entry is answered `root` where `plan` proposes
#: another leg for it (`shape/README.md`: `spec`, by its `.md` extension),
#: because a link sent to a leg is not kept in the root, and the copy skip
#: that M14 breaks is never reached for it.
#:
#: The source's other files, a declared pin, the link, what the plan keeps in
#: the root, the code of the second finding and what it says of its path.
LINK_BESIDE_A_SECOND_PATH = [
    pytest.param(
        {"Shape/README.md": "the case twin\n"}, False, "shape/README.md",
        {"shape/": ROOT, "Shape/": ROOT, "README.md": ROOT}, COPY,
        "That path is the file `Shape/README.md` once case is ignored",
        id="a-case-twin-of-the-readme-copy"),
    pytest.param(
        {"contracts/shape-pin.yaml": "not the shape's pin\n"}, True,
        "contracts/openglass-pin.yaml", {"contracts/": ROOT}, HOLDS_PIN,
        "the plan keeps the file `contracts/shape-pin.yaml` in the assembly "
        "root", id="a-file-at-the-shape-pin-after-a-declared-pins-link"),
    pytest.param(
        {"Makefile": "all:\n", "shape/Makefile": "the source's own\n"}, False,
        "shape/README.md",
        {"shape/Makefile": ROOT, "shape/README.md": ROOT, "Makefile": ROOT,
         "README.md": ROOT}, COPY,
        "the shape's copy of `Makefile` is written to `shape/Makefile`",
        id="a-file-at-the-makefile-copy-after-the-readme-copys-link"),
]


@pytest.mark.parametrize("files, declared, link, kept, second, says",
                         LINK_BESIDE_A_SECOND_PATH)
def test_a_named_link_leaves_out_its_own_finding_and_no_other(
        tmp_path, files, declared, link, kept, second, says):
    """Left out for the link's own sake, the second path is still asked: its
    finding is made, and its remedy (send it to a leg, `drop` it) helps the
    file it names. The link is named once, by its own finding, and
    #908's remediation is said once after the findings."""
    _, plan = planned_root(tmp_path, files, {link: LATE_NUL}, kept)
    if declared:
        declare(plan, A_PIN)
    result = check_root(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    found = findings_of(result)
    assert len(found) == 2, f"the second finding is lost: {found}"
    own, made = found
    assert own.startswith(
        f"FINDING {CODE}: `{link}` is a symlink whose target holds a NUL "
        "byte after its first 4 bytes")
    assert made.startswith(f"FINDING {second}: ")
    assert says in made
    assert result.stderr.count(FACT_OF_THE_SOURCE) == 1


@pytest.mark.parametrize("files, link, kept, second", AT_A_COPY_OR_A_PIN)
def test_execute_refuses_a_named_link_at_a_copy_or_a_pin_with_one_finding(
        adopter, no_filter_repo_probe, tmp_path, files, link, kept, second):
    """`execute` refuses `check`'s own findings before any leg exists
    (#168), so it names the link once too."""
    source, plan = planned_root(tmp_path, files, {link: LATE_NUL}, kept)
    printed, = findings_of(check_root(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == CODE
    assert printed in caught.value.detail
    assert second not in caught.value.detail
    assert adopter.BAD_SYMLINK_TARGET_REMEDIATION in caught.value.remediation
    no_leg_was_created(tmp_path, source)


# --- controls: what must not change ------------------------------------------

@pytest.mark.parametrize("target", [
    pytest.param(NAMED, id="an-ordinary-link"),
    pytest.param(b"../docs/spec.md", id="several-names"),
    pytest.param(AT_MAX, id="4095-bytes-the-most-linux-takes"),
    pytest.param(ONE_NAME, id="one-name-of-300-bytes"),
])
def test_a_link_git_makes_as_the_blob_holds_it_is_no_finding(
        adopter, tmp_path, target):
    source = source_of(tmp_path, {"docs/link": target})
    opened = adopter.Source.open(str(source), tmp_path / WORK)
    tree = opened.tree()
    targets = adopter.symlink_targets(opened, tree)
    assert adopter.bad_symlink_targets(tree, targets) == []
    result = check(planned(source, tmp_path / "plan.yaml"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout
    assert CODE not in result.stderr


@pytest.mark.parametrize("how", ["removed", "given-a-target"])
def test_the_remediation_the_finding_names_makes_check_pass(tmp_path, how):
    """Refused as it is, fixed in the source and planned again, the plan
    checks ok. The first half is what keeps this test from passing on a
    script that never names the link."""
    source = source_of(tmp_path, {"docs/link": LATE_NUL})
    refused = check(planned(source, tmp_path / "plan-before.yaml"))
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert f"FINDING {CODE}: `docs/link`" in refused.stderr
    if how == "removed":
        git("update-index", "--force-remove", "docs/link", cwd=source)
    else:
        put_link(source, "docs/link", b"spec")
    as_human("commit", "-qm", f"The link, {how}", cwd=source)
    result = check(planned(source, tmp_path / "plan.yaml"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


def test_it_comes_after_plan_empty_symlink_and_before_coverage(tmp_path):
    """No answer fixes it, so it is listed with the findings about the
    source, after #303's, and before those about the answers."""
    source = source_of(tmp_path, {"docs/empty": b"", "docs/late": LATE_NUL})
    plan = planned(source, tmp_path / "plan.yaml")
    text = plan.read_bytes().decode("utf-8")
    text, count = re.subn(r"(?m)^  - path: src/\n(?:    .*\n)+", "", text)
    assert count == 1
    plan.write_bytes(text.encode("utf-8"))
    codes = [line.split(":")[0] for line in findings_of(check(plan))]
    assert codes == [f"FINDING {EMPTY}", f"FINDING {CODE}",
                     "FINDING plan-uncovered"]


# --- `plan` and `execute` ----------------------------------------------------

@with_each_bad_target
def test_plan_notes_it_and_still_writes_the_plan(
        tmp_path, target, head, makes):
    source = source_of(tmp_path, {"docs/link": target})
    out = tmp_path / "plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         "Northwind", "--org", "testorg", "--out", str(out),
                         "--elected-by", "Test Human")
    assert written.returncode == 0, written.stderr + written.stdout
    assert out.is_file()
    assert f"\nNOTE `docs/link` is a symlink whose target {head}" \
        in written.stdout
    assert (f"`check` reports this as `{CODE}` and `execute` refuses it, "
            "whatever the plan answers") in written.stdout


@with_each_bad_target
@pytest.mark.parametrize("link, answers", PLACES)
def test_execute_refuses_it_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path, link, answers, target, head,
        makes):
    source = source_of(tmp_path, {link: target})
    plan = planned(source, tmp_path / "plan.yaml", answers)
    printed, = findings_of(check(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == CODE
    assert printed in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert adopter.BAD_SYMLINK_TARGET_REMEDIATION in caught.value.remediation
    no_leg_was_created(tmp_path, source)


@needs_filter_repo
@pytest.mark.parametrize("target", [
    pytest.param(LATE_NUL, id="late-nul"),
    pytest.param(LONG, id="5000-bytes"),
])
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path, target):
    """On 5017830 both leg repositories were made, then exit 2 at the split's
    `git rm` (late NUL) or the first clone (5000 bytes). Refused before a leg
    is made, so the EMPTY `--local-remote-dir` stays empty."""
    source = source_of(tmp_path, {"docs/link": target})
    plan = planned(source, tmp_path / "plan.yaml")
    (tmp_path / REMOTES).mkdir()
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {CODE}: 1 finding(s) in " in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert "adoption verified" not in result.stdout
    assert list((tmp_path / REMOTES).iterdir()) == [], "no leg was made"


# --- what git does, which the limit is read from -----------------------------

def clone_with_links(tmp_path: Path, target: bytes, name: str):
    """`(the clone's exit, the clone's stderr, the link it made or None)` of
    a source whose one symlink `link` holds `target`, cloned with symlinks
    on."""
    source = tmp_path / f"{name}-source"
    source.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=source)
    git("update-index", "--add", "--cacheinfo",
        f"{SYMLINK},{blob(source, target)},link", cwd=source)
    as_human("commit", "-qm", "A link", cwd=source)
    clone = tmp_path / f"{name}-clone"
    # In the C locale, so that git's strerror is the one `os.strerror` gives.
    made = subprocess.run(
        ["git", "clone", "-q", "--config", "core.symlinks=true",
         str(source), str(clone)], capture_output=True, text=True,
        check=False, env={**os.environ, "LC_ALL": "C"})
    link = clone / "link"
    return (made.returncode, made.stderr,
            os.readlink(link) if os.path.islink(link) else None)


@needs_disk_symlinks
def test_git_makes_the_link_a_nul_cuts_to(adopter, tmp_path):
    """`ci\\0xx` is the link `ci`, on Linux: the measurement behind
    `plan-bad-symlink-target`'s sentence."""
    code, stderr, link = clone_with_links(tmp_path, CI_NUL, "late")
    assert code == 0, stderr
    assert link == "ci"
    tree = [row("link", 5, NUL_OID)]
    assert adopter.bad_symlink_targets(tree, {NUL_OID: CI_NUL}) == [
        ("link", CI_NUL)]


@needs_disk_symlinks
def test_git_makes_a_link_of_the_limit_and_not_one_byte_more(
        adopter, tmp_path):
    """The limit is the measurement: 4095 bytes are made, 4096 are not
    (ENAMETOOLONG, exit 128). Skipped where this disk takes less than the
    limit, as macOS and XFS do (1023): `check` does not ask them."""
    probe = tmp_path / "probe"
    try:
        os.symlink(AT_MAX.decode("ascii"), probe)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this disk takes no target of 4095 bytes: {exc}")
    code, stderr, link = clone_with_links(tmp_path, AT_MAX, "max")
    assert code == 0, stderr
    assert link is not None
    assert len(link) == adopter.SYMLINK_TARGET_MAX
    over_code, over_stderr, over_link = clone_with_links(
        tmp_path, OVER_MAX, "over")
    assert over_code == 128, over_stderr
    assert os.strerror(errno.ENAMETOOLONG) in over_stderr
    assert over_link is None


@needs_disk_symlinks
def test_git_makes_a_link_whose_one_name_is_over_name_max(tmp_path):
    """`NAME_MAX` bounds a name a path is opened through, not a link's
    target: a name of 300 bytes is made, so `check` does not ask it."""
    code, stderr, link = clone_with_links(tmp_path, ONE_NAME, "name")
    assert code == 0, stderr
    assert link == ONE_NAME.decode("ascii")

