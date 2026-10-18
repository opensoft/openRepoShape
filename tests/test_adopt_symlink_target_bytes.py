# SPDX-License-Identifier: Apache-2.0
"""A symlink whose target holds a NUL after its first byte, or is longer than
Linux takes (#908: L1-76, L1-78 and L1-80 of #457).

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
  clone exits 128; 4095 is made. A single name of 300 bytes is made too.
- a root-kept `.github -> ci\\0xx` was refused as `plan-root-symlink`, which
  said it led to `ci\\x00xx`, "not in the source tree": Linux makes
  `.github -> ci`.
- a link kept in the root AT `project.yaml` got two findings, and the second's
  `drop` helps no link that cannot be made.
- `_PlannedRoot._link` started `git cat-file blob` for each link, per walk and
  per disk: 3 processes for one link, 16 for five.

Now `plan-bad-symlink-target` names each such link once, before any leg
exists, and says what git makes of it; `plan-root-symlink` does not say it
again; one finding names the link at `project.yaml`; and every link's target
is read in the one `git cat-file --batch` `check` already starts.

The links are made in the INDEX with `git update-index --cacheinfo`, so no
test builds a source on a disk that holds a NUL in a target, and all but the
two that ask git to check a link out (marked `needs_disk_symlinks`) run on
Windows too.
"""

from __future__ import annotations

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
    GITHUB, ROOT, check as check_root, planned as planned_root, ticked,
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
    """4095: `PATH_MAX` is 4096, counting the NUL that ends the string."""
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
    assert "after both leg repositories were created" in finding
    assert "whatever the plan answers for it" in finding
    assert "`core.symlinks` is false" in finding
    assert remediation == [adopter.BAD_SYMLINK_TARGET_REMEDIATION]
    assert "`drop` included" in remediation[0]
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
    assert found[20] == (f"FINDING {CODE}: ... and 3 more symlinks whose "
                         "target holds a NUL byte after its first or is "
                         "longer than Linux takes")


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
    assert finding.endswith(
        "a target of its own would not end that, so remove the link or "
        "rename it in the source, commit, and re-run `plan`.")


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
    made = subprocess.run(
        ["git", "clone", "-q", "--config", "core.symlinks=true",
         str(source), str(clone)], capture_output=True, text=True,
        check=False)
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
    (`File name too long`, exit 128). Skipped where this disk takes less
    than the limit, as one with a smaller `PATH_MAX` does."""
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
    assert "File name too long" in over_stderr
    assert over_link is None


@needs_disk_symlinks
def test_git_makes_a_link_whose_one_name_is_over_name_max(tmp_path):
    """`NAME_MAX` bounds a name a path is opened through, not a link's
    target: a name of 300 bytes is made, so `check` does not ask it."""
    code, stderr, link = clone_with_links(tmp_path, ONE_NAME, "name")
    assert code == 0, stderr
    assert link == ONE_NAME.decode("ascii")

