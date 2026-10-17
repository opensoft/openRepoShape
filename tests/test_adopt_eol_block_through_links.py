# SPDX-License-Identifier: Apache-2.0
"""#471's line-ending block names each pinned copy by the path git tracks
(#807).

A source may keep a symlinked directory in the root that the shape writes
through, `.github -> ci`, a layout #504 accepts. Git then tracks the shape's
workflow at `ci/workflows/validate.yml`, and the block's line named the
link's spelling, `/.github/workflows/validate.yml`, which governs nothing:
under the source's `* text=auto eol=crlf` a clone wrote that copy with CRLF,
and `validate-pins.py` exited 1 with `shape-copy-drift` after `execute` had
said `adoption verified`.

Every place that writes or reads the block now names the tracked path: the
materializer's append and the verification's count of the file
(`tests/test_adopt_attributes_eol_block.py` holds both on hand-made trees),
and the root `check` asks git about, for a nested `.gitattributes` and for
what this machine's `git add` stores, both here. A source with no symlinked
directory gets the same block, byte for byte, and one with
`core.symlinks=false` is still refused first.

`update-shape.py` writes no line of the block through a link: `apply`
refuses a pinned copy reached through one (`update-rewrite-symlink`, #286)
and `--add` a path with one on its way (`update-add-symlink`, #239), so each
path it names is the path git tracks, and on such a clone it writes nothing.

`check`'s tests put the links in the source's TREE only, which is all it
reads. The end-to-end tests make them on the disk, need `git filter-repo`,
and skip on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, REPO, appended_to_command_scope,
                      cloned_just_pushed, git, make_source_repo, run_script,
                      write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402
from shape_materialize import eol_block  # noqa: E402

UTF8 = "utf-8"
PROJECT = "Northwind"
BRANCH = "adopt/three-repo-shape"
ATTRIBUTES = ".gitattributes"
PIN = "contracts/shape-pin.yaml"
README = "README.md"
#: The pinned copy the shape writes through the link, and where git tracks it.
WORKFLOW = ".github/workflows/validate.yml"
TRACKED = "ci/workflows/validate.yml"
#: The source's own rule: every text file checks out with CRLF, everywhere.
CRLF_RULE = b"* text=auto eol=crlf\n"
#: `.github -> ci`, the chain `.github -> l1 -> ci`, and no link at all.
LINK = {".github": "ci"}
CHAIN = {".github": "l1", "l1": "ci"}
#: A source's files, with a `ci/` the links lead to.
SOURCE = {README: "# Thing\n",
          "specs/001-feature/spec.md": "# The feature\n",
          "src/app/main.py": "import contracts_reader\n",
          "ci/workflows/ci.yml": "on: [push]\n"}
SYMLINK_MODE = "120000"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def committed(source: Path, message: str) -> None:
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=source)


def source_keeping(base: Path, links: dict, files: dict,
                   on_disk: bool) -> Path:
    """A source with `SOURCE` and `files` (bytes, committed as they are),
    and `links`: real symlinks where `on_disk`, else in its tree alone."""
    source = make_source_repo(base / "Thing", tree=SOURCE, edits=())
    for name, data in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes(data)
    if on_disk:
        for link, target in links.items():
            try:
                os.symlink(target, source / link)
            except (NotImplementedError, OSError) as exc:
                pytest.skip(f"this platform cannot create a symlink: {exc}")
    git("add", "-A", "--", ".", cwd=source)
    if not on_disk:
        for link, target in links.items():
            blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                                  cwd=str(source), input=target.encode(UTF8),
                                  capture_output=True, check=True)
            git("update-index", "--add", "--cacheinfo",
                f"{SYMLINK_MODE},{blob.stdout.decode(UTF8).strip()},{link}",
                cwd=source)
    committed(source, "Keep a link, and our own attributes")
    return source


def planned(source: Path, base: Path) -> Path:
    """The plan for `source`, every question answered `root`."""
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_text(encoding=UTF8)
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text.replace("    leg: null\n",
                                  "    leg: root\n    resolution: \"kept\"\n"))
    return plan


def check(plan: Path, env: dict | None = None):
    return run_script(ADOPT, "check", "--plan", str(plan), env=env)


def execute(base: Path, plan: Path, env: dict | None = None):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"), env=env)


def finding_lines(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


# ---------------------------------------------------------------------------
# `check` asks git about the root the split writes, with the tracked line
# ---------------------------------------------------------------------------


def test_check_finds_a_nested_file_that_outranks_the_tracked_line(tmp_path):
    """`ci/.gitattributes`'s `*.yml eol=crlf` outranks the root's line for
    the copy git tracks at `ci/workflows/validate.yml`, so a clone writes it
    with CRLF on every platform, and `check` says so (#530's question). It
    asked git with the link's line, which left the copy to `* text=auto`
    already, so it found nothing to outrank, and `execute` went on."""
    source = source_keeping(tmp_path, LINK, {
        ATTRIBUTES: b"* text=auto\n",
        "ci/.gitattributes": b"*.yml eol=crlf\n"}, on_disk=False)
    result = check(planned(source, tmp_path))
    assert result.returncode == 1, result.stdout + result.stderr
    found = finding_lines(result)
    assert len(found) == 1, found
    assert found[0].startswith(
        "FINDING plan-nested-attributes: the plan keeps `ci/.gitattributes` "
        "in the assembly root"), found[0]
    assert f"the pinned copy `{TRACKED}`" in found[0], found[0]
    assert "`/workflows/validate.yml text eol=lf`" in found[0], found[0]


def test_check_asks_git_add_about_the_copy_where_git_tracks_it(tmp_path):
    """Under `core.safecrlf=true` this machine's `git add` refuses an LF
    file that `eol=crlf` reaches. The root's own rule says that of every
    file, and the block's line takes the copy out of it: named by the link's
    spelling, it did not, and `check` reported `plan-file-reencoded` for
    `ci/workflows/validate.yml`, a refusal of git's that the split itself
    would not meet. The source's `.gitattributes` keeps itself LF, so it is
    no finding of its own."""
    source = source_keeping(tmp_path, LINK, {
        ATTRIBUTES: CRLF_RULE + b"/.gitattributes text eol=lf\n"},
        on_disk=False)
    plan = planned(source, tmp_path)
    result = check(plan, env=appended_to_command_scope(
        os.environ, (("core.safecrlf", "true"),)))
    assert finding_lines(result) == []
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# End to end: `execute`, a clone, its pins, and `update-shape.py`
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", params=[
    pytest.param(LINK, id="a-link"), pytest.param(CHAIN, id="a-chain"),
    pytest.param({}, id="no-link")])
def adopted(request, tmp_path_factory) -> SimpleNamespace:
    """One real adoption of a source with `* text=auto eol=crlf` that keeps
    `.github -> ci`, the chain `.github -> l1 -> ci`, or no link."""
    if sys.platform == "win32" or shutil.which("git-filter-repo") is None:
        pytest.skip("needs git filter-repo and a disk that holds symlinks")
    base = tmp_path_factory.mktemp("tracked-spelling")
    source = source_keeping(base, request.param, {ATTRIBUTES: CRLF_RULE},
                            on_disk=True)
    plan = planned(source, base)
    checked = check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    return SimpleNamespace(source=source, links=request.param,
                           result=execute(base, plan))


def pinned_rows(source: Path) -> list[str]:
    pin = parse_yaml(git("show", f"{BRANCH}:{PIN}", cwd=source).stdout)
    return [row["path"] for row in pin["files"]]


@needs_filter_repo
def test_execute_verifies_a_block_that_names_the_tracked_path(adopted):
    """The source's bytes, then one line per pinned copy outside `shape/`
    in the pin's order, the workflow named where git tracks it. With no
    link that is each pin row's own path: the block main writes, byte for
    byte. The pin row keeps the path the copy was written at."""
    result = adopted.result
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    rows = pinned_rows(adopted.source)
    assert WORKFLOW in rows
    where = TRACKED if adopted.links else WORKFLOW
    named = [where if row == WORKFLOW else row for row in rows
             if not row.startswith("shape/")]
    shown = git("show", f"{BRANCH}:{ATTRIBUTES}", cwd=adopted.source)
    assert shown.stdout == CRLF_RULE.decode(UTF8) + eol_block(named)


@needs_filter_repo
def test_a_clone_checks_every_copy_out_as_pinned_and_its_pins_pass(adopted,
                                                                  tmp_path):
    """The source's `README.md` IS checked out with CRLF, so the rule
    reached the checkout; every pinned copy is not, the workflow read
    through the link included; and the clone's `validate-pins.py` exits 0,
    where it exited 1 with `shape-copy-drift: .github/workflows/
    validate.yml`."""
    assert adopted.result.returncode == 0
    clone = cloned_just_pushed(adopted.source, tmp_path / PROJECT, BRANCH)
    assert b"\r\n" in (clone / README).read_bytes(), "no CRLF: tests nothing"
    crlf = [row for row in pinned_rows(adopted.source)
            if b"\r\n" in (clone / row).read_bytes()]
    assert crlf == []
    pins = run_script(clone / "scripts" / "validate-pins.py", cwd=clone)
    assert pins.returncode == 0, pins.stdout + pins.stderr


@needs_filter_repo
def test_update_shape_writes_no_line_through_the_link(adopted, tmp_path):
    """`apply` on such a clone refuses the copy reached through the link
    before it writes anything, so the block keeps the line `execute` wrote,
    and no line of the link's spelling is ever added to it."""
    if not adopted.links:
        pytest.skip("only a root that keeps a link has one to write through")
    clone = cloned_just_pushed(adopted.source, tmp_path / PROJECT, BRANCH)
    before = (clone / ATTRIBUTES).read_bytes()
    commit = parse_yaml((clone / PIN).read_text(encoding=UTF8))["commit"]
    applied = run_script(REPO / "update-shape.py", "apply", "--root",
                         str(clone), "--upstream", str(REPO), "--at",
                         str(commit), "--yes")
    assert applied.returncode != 0, applied.stdout
    assert "update-rewrite-symlink" in applied.stderr, applied.stderr
    assert (clone / ATTRIBUTES).read_bytes() == before


@needs_filter_repo
def test_with_symlinks_off_execute_still_refuses_first(tmp_path):
    """Where `git` checks a symlink out as a plain file, the assembly's
    clone would hold `.github` as a file, and `execute` refuses before any
    leg exists, as it did (#183)."""
    if sys.platform == "win32":
        pytest.skip("needs a disk that holds symlinks")
    source = source_keeping(tmp_path, LINK, {ATTRIBUTES: CRLF_RULE},
                            on_disk=True)
    plan = planned(source, tmp_path)
    result = execute(tmp_path, plan, env=appended_to_command_scope(
        os.environ, (("core.symlinks", "false"),)))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED adopt-symlinks-off: the plan keeps `.github` in the " \
           "root, a symlink to `ci`" in result.stderr, result.stderr
    assert not (tmp_path / "remotes").exists()
