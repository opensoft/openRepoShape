# SPDX-License-Identifier: Apache-2.0
"""`apply` never REWRITES a file through a symlink the root keeps (#286).

`apply` overwrites three kinds of file: the pinned copies the standard
changed, `contracts/shape-pin.yaml` and the manifest. `Rollback.write` opens
each one `r+b`, which follows a link, so a root that kept any of them as a
committed symlink — `AGENTS-shape.md` pointing at a shared file elsewhere on
disk, say — had the standard's bytes written at the LINK'S END, outside the
root if that is where it points. git holds the link, which had not changed,
so `--branch` committed none of those bytes while printing them among what it
committed, and the pin recorded a digest no commit carries. With the
project's validators red, the rollback wrote the old bytes back through the
same link.

`tests/test_update_shape_add_symlink.py` holds `--add`'s half (#239). This
file holds the rewrites, in the places they matter:

  * (a) A PINNED COPY kept as a link is `copy-is-link` to `check`, counted
    with the conflicts, and `apply` refuses it as `update-rewrite-symlink`,
    exit 2, before it writes anything — with or without `--branch`, with the
    validators green or red.
  * (b) THE PIN OR THE MANIFEST kept as a link, or the pin under a directory
    link: `prepare` refuses it, so `check` and `apply` both say so before
    anything is written. A DANGLING link at the pin is named as the link it
    is, not as a pin that "does not exist".
  * (c) A DIRECTORY LINK ABOVE pinned copies (`scripts`, moved outside the
    root): every copy under it is `copy-is-link`, and the refusal comes
    before the validators, which used to resolve their own location through
    the link, go red, and roll back through it.
  * (d) THE CONTROLS: a DANGLING link at a pinned copy stays `copy-missing`,
    refused as `update-conflict` as before; a root reached THROUGH a link,
    with an unrelated link inside it, still updates.
  * THE LEDGER'S OWN GUARD: a link that arrives while an interactive `apply`
    waits in `confirm` is refused by `Rollback.write` itself, and what was
    already written is put back.
  * A WINDOWS JUNCTION is a link here too, on every platform, by handing the
    walk what `lstat` gives for one.

"Nothing was written" is the whole tree before and after — every file's
bytes and mode, every link by where it points, git's HEAD, branches, index
and status — and every directory beside the root that a link leads to; the
helpers are `tests/test_update_shape_add_symlink.py`'s.

THE FIXTURE is `tests/test_update_shape.py`'s: a clone of this repository at
A and `Atlas` scaffolded from it into bare repositories on disk. Commit B
edits two pinned copies, `AGENTS-shape.md` and `scripts/validate-manifest.py`,
so there is a write for a link to be in the way of whichever one is linked.
No network is used and `gh` is never invoked.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
from test_scaffold_ignored_shape_files import load
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               scaffold_upstream_and_project)
from test_update_shape_add import commit_all, validators_are_green, verdicts
from test_update_shape_add_symlink import (JUNCTION_TAG, assert_untouched,
                                           beyond, make_validators_red,
                                           outside_dir, snapshot)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import TREE_DIGEST_DEFINITION, load_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"
ENV = {"PYTHONDONTWRITEBYTECODE": "1"}

#: The issue's pinned copy, and the edit commit B makes to its source.
AGENTS = "AGENTS-shape.md"
AGENTS_SOURCE = f"templates/assembly-root/{AGENTS}"
AGENTS_EDIT = b"<!-- an upstream edit -->\n"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"
#: What an operator's own file, outside the root, holds.
THEIRS = b"someone else's file, which no tool here may touch\n"


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it, and B editing two pinned copies."""
    _base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-rewrite-symlink")
    for source, edit in ((AGENTS_SOURCE, AGENTS_EDIT),
                         (CHANGED_SOURCE, UPSTREAM_FIX_LINE.encode("utf-8"))):
        path = upstream / source
        # Bytes, so the blob is what was appended on every platform.
        path.write_bytes(path.read_bytes() + edit)
    b = commit_all(upstream, "Edit AGENTS-shape.md and fix the manifest "
                   "validator", [AGENTS_SOURCE, CHANGED_SOURCE])
    assert a != b
    return {"upstream": upstream, "clone": clone, "a": a, "b": b}


@pytest.fixture
def root(standard, tmp_path):
    """A private, mutable copy of the project as it was cut at A."""
    target = tmp_path / PROJECT
    shutil.copytree(standard["clone"], target, symlinks=True)
    return target


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, for the ledger and the walk."""
    return load(UPDATE, "update_shape_rewrite_symlink")


def check(root, standard, *extra):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def apply(root, standard, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def pinned_commit(root) -> str:
    """The pin's `commit:`, read through whatever the root keeps there."""
    return str(load_yaml(root / PIN)["commit"]).lower()


def commit_root(root: Path, message: str) -> None:
    """Commit everything the test just did to the root, so the tree is
    clean and the link is what git holds, as in the issue."""
    git("add", "-A", "--", ".", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        message, cwd=root)


def keep_as_link(root: Path, rel: str, where: Path) -> Path:
    """The issue's `mv` and `ln -s`, committed: `rel` moved to `where`
    beside the root, with a symlink to it left at `rel`. Returns `where`."""
    where.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root / rel), str(where))
    (root / rel).symlink_to(where, target_is_directory=where.is_dir())
    commit_root(root, f"keep {rel} as a link")
    return where


def said(path: str, name: str, points) -> str:
    """How `update-shape.py` names a link on `path`'s way: the phrase
    `link_said` prints, spelled out so a change to it is seen here."""
    above = "" if name == path else f", on the way to {path}"
    return f"{name} in this root is a symlink{above}, pointing at {points!r}"


def one_link_said(path: str, name: str, points) -> str:
    """How `update-rewrite-symlink` opens when it names ONE path: on one
    line, so the doctor can quote it inside one line of its table."""
    return f"`apply` would rewrite {path}, but " + said(path, name, points)


def assert_refused_before_any_write(result) -> None:
    """Exit 2, by name, and nothing written to put back: the refusal came
    before the first byte, not after a write through the link."""
    assert "ROLLED BACK" not in result.stderr, (
        "the refusal came after a write, and the run rolled back:\n"
        + result.stderr)
    assert "update-validators-red" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-rewrite-symlink" in result.stderr, result.stderr
    assert "never writes through a symlink" in result.stderr
    assert "copied   " not in result.stdout, result.stdout
    assert "re-pinned" not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# (a) A pinned copy kept as a link
# ---------------------------------------------------------------------------


@WINDOWS_SKIP
def test_check_names_a_pinned_copy_kept_as_a_link(root, standard, tmp_path):
    """Main read through the link and called the row `upstream-changed`,
    which `apply` then wrote through. The row is the link's now, with where
    it points, and the conflicts line says `apply` will refuse it; the other
    copy B changed still reports as it did."""
    where = keep_as_link(root, AGENTS, outside_dir(tmp_path) / AGENTS)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = check(root, standard)
    assert result.returncode == 1, result.stdout + result.stderr
    found = verdicts(result.stdout)
    assert found[AGENTS] == "copy-is-link", result.stdout
    assert found[CHANGED] == "upstream-changed", result.stdout
    assert said(AGENTS, AGENTS, str(where)) in result.stdout
    ahead = [line for line in result.stdout.splitlines()
             if line.startswith("REFUSAL AHEAD")]
    assert len(ahead) == 1 and AGENTS in ahead[0], result.stdout
    assert "copy-is-link 1" in result.stdout, "the summary counts it"
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


@WINDOWS_SKIP
@pytest.mark.parametrize("validators", ["green", "red"])
@pytest.mark.parametrize("branch", [None, "shape/update-link"],
                         ids=["no-branch", "branch"])
def test_apply_refuses_a_pinned_copy_kept_as_a_link_before_any_write(
        root, standard, tmp_path, branch, validators):
    """THE ISSUE. Green, main wrote the standard's bytes at the link's end,
    exited 0, and with `--branch` named `AGENTS-shape.md` among what it
    committed while the commit held only the pin and the manifest. Red, it
    rolled back by writing the old bytes through the same link. Now the
    run refuses by name before the first write: the file at the link's end,
    the tree, the pin, HEAD and every branch are as they were."""
    where = keep_as_link(root, AGENTS, outside_dir(tmp_path) / AGENTS)
    if validators == "red":
        make_validators_red(root)
    held = where.read_bytes()
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, *(("--branch", branch) if branch else ()))
    # THE INVARIANT FIRST: a failure on main names the write through the
    # link, not the wording.
    assert where.read_bytes() == held, (
        "the standard's bytes were written THROUGH the link, outside the "
        "root")
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert (root / AGENTS).is_symlink()
    assert pinned_commit(root) == standard["a"]
    assert_refused_before_any_write(result)
    assert one_link_said(AGENTS, AGENTS, str(where)) in result.stderr, (
        result.stderr)
    assert "replace the link with what it points at" in result.stderr


@WINDOWS_SKIP
def test_accept_local_does_not_take_a_pinned_copy_kept_as_a_link(
        root, standard, tmp_path):
    """`--accept-local` re-pins a row from the root's bytes, and these are
    the link's end's: there is no local edit to accept, only a place this
    command does not write, so it is refused the same way."""
    keep_as_link(root, AGENTS, outside_dir(tmp_path) / AGENTS)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--accept-local", AGENTS)
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert_refused_before_any_write(result)


# ---------------------------------------------------------------------------
# (b) The pin or the manifest kept as a link
# ---------------------------------------------------------------------------


def pin_at_a_link(root: Path, tmp_path: Path):
    """The issue's second row: the pin moved outside, a link in its place."""
    keep_as_link(root, PIN, outside_dir(tmp_path) / "shape-pin.yaml")
    return PIN, PIN


def pin_under_a_directory_link(root: Path, tmp_path: Path):
    """`contracts` moved outside whole: the pin is a plain file, under a
    link."""
    keep_as_link(root, "contracts", outside_dir(tmp_path) / "contracts")
    return PIN, "contracts"


def manifest_at_a_link(root: Path, tmp_path: Path):
    """`project.yaml`, the record that mirrors the pin, moved outside."""
    keep_as_link(root, MANIFEST, outside_dir(tmp_path) / MANIFEST)
    return MANIFEST, MANIFEST


RECORD_LINKS = [
    pytest.param(pin_at_a_link, id="pin-at-a-link"),
    pytest.param(pin_under_a_directory_link, id="pin-under-a-directory-link"),
    pytest.param(manifest_at_a_link, id="manifest-at-a-link"),
]


@WINDOWS_SKIP
@pytest.mark.parametrize("make_link", RECORD_LINKS)
def test_check_refuses_a_pin_or_manifest_kept_as_a_link(
        root, standard, tmp_path, make_link):
    """Main read the pin through its link and reported the copies, and never
    read the manifest at all, so `check` exited 1 with a `NEXT` line whose
    `apply` would write through either. `prepare` refuses now, as `read_pin`
    does for any pin it cannot use."""
    path, name = make_link(root, tmp_path)
    points = os.readlink(root / name)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = check(root, standard)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-rewrite-symlink" in result.stderr, result.stderr
    # ONE LINE, link and reason together: the doctor quotes this refusal
    # inside one line of its table.
    refused = [line for line in result.stderr.splitlines()
               if line.startswith("REFUSED")]
    assert len(refused) == 1, result.stderr
    assert one_link_said(path, name, points) in refused[0], result.stderr
    assert refused[0].endswith("never writes through a symlink"), (
        result.stderr)
    assert "NEXT" not in result.stdout, result.stdout
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


@WINDOWS_SKIP
@pytest.mark.parametrize("branch", [None, "shape/update-link"],
                         ids=["no-branch", "branch"])
@pytest.mark.parametrize("make_link", RECORD_LINKS)
def test_apply_refuses_a_pin_or_manifest_kept_as_a_link_before_any_write(
        root, standard, tmp_path, make_link, branch):
    """Main rewrote the pin, or the manifest, at the link's end and exited
    0; with `--branch` the commit moved the copies and the other record but
    not the linked one, while the run said it had committed it. Refused now
    before the first write, so not even the copies B changed are written."""
    path, name = make_link(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)
    copy = (root / CHANGED).read_bytes()

    result = apply(root, standard, *(("--branch", branch) if branch else ()))
    assert beyond(tmp_path) == elsewhere, (
        "a record was rewritten THROUGH the link, outside the root")
    assert_untouched(before, snapshot(root))
    assert (root / name).is_symlink()
    assert (root / CHANGED).read_bytes() == copy
    assert pinned_commit(root) == standard["a"]
    assert_refused_before_any_write(result)
    assert one_link_said(path, name, os.readlink(root / name)) \
        in result.stderr, result.stderr


@WINDOWS_SKIP
def test_a_dangling_link_at_the_pin_is_named_as_the_link(root, standard,
                                                         tmp_path):
    """`is_file()` follows a link, so main called a dangling one a pin that
    "does not exist" and sent the operator to `adopt-project.py`. The link
    is asked first, by `lstat`, and named — with where it points — as any
    link at the pin is."""
    (root / PIN).unlink()
    gone = tmp_path / "no-such-dir" / "shape-pin.yaml"
    (root / PIN).symlink_to(gone)
    commit_root(root, "a pin that leads nowhere")
    before, elsewhere = snapshot(root), beyond(tmp_path)

    for result in (check(root, standard), apply(root, standard)):
        assert result.returncode == 2, result.stdout + result.stderr
        assert "REFUSED update-rewrite-symlink" in result.stderr, (
            result.stderr)
        assert "update-pin-missing" not in result.stderr
        assert said(PIN, PIN, str(gone)) in result.stderr, result.stderr
    assert not gone.parent.exists()
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


# ---------------------------------------------------------------------------
# (c) A directory link above pinned copies
# ---------------------------------------------------------------------------


@WINDOWS_SKIP
def test_a_directory_link_above_pinned_copies_is_refused_before_the_validators(
        root, standard, tmp_path):
    """`scripts` moved outside the root whole, a link in its place. Main
    wrote B's `scripts/validate-manifest.py` through it, then ran the
    project's validators, which resolve their own location THROUGH the link,
    found no repository there, went red, and rolled every byte back through
    the same link. Every copy under the link is `copy-is-link` now, and the
    refusal comes before anything is written or run."""
    where = keep_as_link(root, "scripts", outside_dir(tmp_path) / "scripts")
    pinned = [str(row["path"]) for row in load_yaml(root / PIN)["files"]]
    under = [path for path in pinned if path.startswith("scripts/")]
    assert CHANGED in under
    before, elsewhere = snapshot(root), beyond(tmp_path)

    checked = check(root, standard)
    found = verdicts(checked.stdout)
    assert {path: found.get(path) for path in under} == {
        path: "copy-is-link" for path in under}, checked.stdout
    assert found[AGENTS] == "upstream-changed", checked.stdout
    assert said(CHANGED, "scripts", str(where)) in checked.stdout

    result = apply(root, standard, "--branch", "shape/update-link")
    assert beyond(tmp_path) == elsewhere, (
        "a copy was written THROUGH the directory link, outside the root")
    assert_untouched(before, snapshot(root))
    assert (root / AGENTS).read_bytes() == \
        (standard["clone"] / AGENTS).read_bytes(), (
            "the copy outside the link was written too")
    assert_refused_before_any_write(result)
    assert f"    {CHANGED}: " + said(CHANGED, "scripts", str(where)) \
        in result.stderr, result.stderr
    assert "the project's own validators" not in result.stdout, (
        "the validators ran: the refusal came after a write")


# ---------------------------------------------------------------------------
# (d) The controls
# ---------------------------------------------------------------------------


@WINDOWS_SKIP
def test_a_dangling_link_at_a_pinned_copy_is_still_copy_missing(
        root, standard, tmp_path):
    """There is no file to read at a dangling link, so the row is what main
    called it — `copy-missing` — and `apply` refuses it as the conflict it
    always was, before any write, without creating the link's end."""
    (root / AGENTS).unlink()
    gone = tmp_path / "gone" / AGENTS
    (root / AGENTS).symlink_to(gone)
    commit_root(root, "AGENTS-shape.md leads nowhere")
    before, elsewhere = snapshot(root), beyond(tmp_path)

    checked = check(root, standard)
    assert verdicts(checked.stdout)[AGENTS] == "copy-missing", checked.stdout
    assert "copy-is-link" not in checked.stdout

    result = apply(root, standard)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-conflict" in result.stderr, result.stderr
    assert "update-rewrite-symlink" not in result.stderr
    assert not gone.parent.exists()
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


@WINDOWS_SKIP
def test_a_root_reached_through_a_link_still_updates(root, standard,
                                                     tmp_path):
    """`--root` is resolved before any path is walked, so a root named
    through a symlink (macOS's `/var`, a project kept under a link into a
    bigger disk) is not "a link on the way", and neither is a link the root
    holds somewhere `apply` does not write: B's two copies are written, the
    pin moves, the commit holds all of it, and the validators stay green."""
    (root / "notes-link").symlink_to(outside_dir(tmp_path),
                                     target_is_directory=True)
    via = tmp_path / "via"
    via.symlink_to(root, target_is_directory=True)

    result = apply(via, standard, "--branch", "shape/update-via")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / AGENTS).read_bytes().endswith(AGENTS_EDIT)
    assert (root / CHANGED).read_bytes().endswith(
        UPSTREAM_FIX_LINE.encode("utf-8"))
    assert pinned_commit(root) == standard["b"]
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=root).stdout.split())
    assert {AGENTS, CHANGED, PIN, MANIFEST} <= committed, committed
    assert os.listdir(tmp_path / "outside") == []
    validators_are_green(root)


# ---------------------------------------------------------------------------
# The ledger's own guard: a link that arrives after `prepare` looked
# ---------------------------------------------------------------------------


@WINDOWS_SKIP
@pytest.mark.parametrize("arrives_at, rewrites, restored", [
    pytest.param(AGENTS, AGENTS, (CHANGED,), id="at-a-pinned-copy"),
    pytest.param(PIN, PIN, (CHANGED, AGENTS), id="at-the-pin"),
    pytest.param(MANIFEST, MANIFEST, (CHANGED, AGENTS, PIN),
                 id="at-the-manifest"),
    pytest.param("contracts", PIN, (CHANGED, AGENTS),
                 id="a-directory-link-above-the-pin"),
])
def test_a_link_that_arrives_while_apply_waits_is_refused_and_rolled_back(
        update_shape, root, standard, tmp_path, monkeypatch, arrives_at,
        rewrites, restored):
    """`confirm` is where an interactive `apply` waits for a human, after
    `prepare` has looked; the operator's link arrives there, at `arrives_at`,
    in the way of the write to `rewrites`. Whatever was written before it —
    the copy, or both copies, or both copies and the pin when the manifest
    is the one linked — is put back by `cmd_apply`'s refusal arm, and the
    tree is exactly as it was when the run began to write. Main wrote
    through the link and finished the run. `contracts` arrives as a
    DIRECTORY link: the pin under it is the write refused."""
    where = outside_dir(tmp_path) / Path(arrives_at).name
    end = where / Path(rewrites).relative_to(arrives_at)
    seen: dict = {}

    def a_link_arrives(*_args, **_kwargs) -> None:
        shutil.move(str(root / arrives_at), str(where))
        (root / arrives_at).symlink_to(where,
                                       target_is_directory=where.is_dir())
        seen["held"] = end.read_bytes()
        seen["root"], seen["beyond"] = snapshot(root), beyond(tmp_path)

    monkeypatch.setattr(update_shape, "confirm", a_link_arrives)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    args = update_shape.build_parser().parse_args([
        "apply", "--root", str(root), "--yes",
        "--upstream", str(standard["upstream"]), "--at", standard["b"]])

    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.cmd_apply(args)
    assert end.read_bytes() == seen["held"], (
        f"{end} was written THROUGH the link")
    assert beyond(tmp_path) == seen["beyond"]
    assert_untouched(seen["root"], snapshot(root))
    assert refused.value.code == "update-rewrite-symlink"
    assert said(rewrites, arrives_at, str(where)) in refused.value.detail
    assert "it arrived while `apply` ran" in refused.value.detail
    assert "ROLLED BACK: every byte" in refused.value.detail, (
        refused.value.detail)
    for rel in restored:
        assert f"restored  {rel}" in refused.value.detail


@WINDOWS_SKIP
@pytest.mark.parametrize("above", [False, True],
                         ids=["at-the-path", "above-the-path"])
def test_the_ledger_never_rewrites_a_file_through_a_link(update_shape,
                                                         tmp_path, above):
    """The guard alone, with nothing in front of it. Main opened the path
    `r+b`, followed the link and overwrote what it leads to. Refused by
    name now, with nothing read into the ledger, so there is nothing for an
    undo to write back through the link either."""
    root = tmp_path / PROJECT
    root.mkdir()
    outside = outside_dir(tmp_path)
    (outside / "agents.md").write_bytes(THEIRS)
    if above:
        (root / "docs").symlink_to(outside, target_is_directory=True)
        rel, name = "docs/agents.md", "docs"
    else:
        (root / "agents.md").symlink_to(outside / "agents.md")
        rel, name = "agents.md", "agents.md"
    ledger = update_shape.Rollback(root)

    with pytest.raises(update_shape.Refusal) as refused:
        ledger.write(root / rel, b"the standard's bytes\n")
    assert (outside / "agents.md").read_bytes() == THEIRS
    assert ledger.written == {}
    assert refused.value.code == "update-rewrite-symlink"
    assert said(rel, name, os.readlink(root / name)) in refused.value.detail


def test_the_ledger_still_rewrites_a_plain_file(update_shape, tmp_path):
    """The control: no link anywhere on the way, so the file is rewritten
    and its first bytes are kept for the undo."""
    root = tmp_path / PROJECT
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "agents.md").write_bytes(THEIRS)
    ledger = update_shape.Rollback(root)

    ledger.write(root / "docs" / "agents.md", b"new\n")
    assert (root / "docs" / "agents.md").read_bytes() == b"new\n"
    assert ledger.written == {root / "docs" / "agents.md": THEIRS}


# ---------------------------------------------------------------------------
# A Windows junction is a link for the rewrites too
# ---------------------------------------------------------------------------
#
# `is_link_info` and the walk are #239's, and its tests hand the walk what
# Windows' `lstat` gives for a junction. These hand it the same at the three
# places a rewrite is decided — a pinned row, the pin, the manifest — on
# every platform, since no POSIX runner can make a real junction.


def junction_at(monkeypatch, junctions: dict) -> None:
    """`os.lstat` reports each path in `junctions` as a directory carrying
    the mount point's reparse tag, and `os.readlink` answers its target."""
    real_lstat, real_readlink = os.lstat, os.readlink

    def lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if Path(path) in junctions:
            return SimpleNamespace(st_mode=info.st_mode,
                                   st_reparse_tag=JUNCTION_TAG)
        return info

    def readlink(path, *args, **kwargs):
        if Path(path) in junctions:
            return junctions[Path(path)]
        return real_readlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)
    monkeypatch.setattr(os, "readlink", readlink)


def a_bare_root(tmp_path: Path) -> Path:
    """A root holding a pin `read_pin` accepts, a manifest and one pinned
    copy under `scripts/` — nothing more is read before the walk decides."""
    root = tmp_path / PROJECT
    (root / "contracts").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "x.py").write_bytes(b"pass\n")
    (root / MANIFEST).write_bytes(b"name: atlas\n")
    (root / PIN).write_text(
        f'commit: "{"a" * 40}"\n'
        f'digest_definition: "{TREE_DIGEST_DEFINITION}"\n'
        "files:\n  - path: scripts/x.py\n    sha256: \"0\"\n",
        encoding="utf-8")
    return root


def test_a_junction_above_a_pinned_copy_makes_the_row_copy_is_link(
        update_shape, tmp_path, monkeypatch):
    """`scripts` reads as a junction: the row is `copy-is-link`. The stub
    upstream holds the root's own bytes at every commit, so a walk that
    missed the junction would go on to compare them and give the row an
    ordinary verdict."""
    root = a_bare_root(tmp_path)
    junction_at(monkeypatch, {root / "scripts": r"\\?\C:\elsewhere"})
    row = update_shape.Row("scripts/x.py", "0" * 64)
    upstream = SimpleNamespace(blob=lambda _rev, _path: b"pass\n")

    update_shape._classify_row(root, row, upstream, "a" * 40, "b" * 40,
                               update_shape.PROJECT_KIND)
    assert row.state == "copy-is-link"
    assert row.is_conflict
    assert row.link == ("scripts", r"\\?\C:\elsewhere")


@pytest.mark.parametrize("junction, refused_at", [
    pytest.param("contracts", PIN, id="above-the-pin"),
    pytest.param(MANIFEST, MANIFEST, id="at-the-manifest"),
])
def test_a_junction_at_or_above_a_record_is_refused_by_prepare(
        update_shape, tmp_path, monkeypatch, junction, refused_at):
    """The pin under a junction is refused by `read_pin`, the manifest at
    one by `prepare`, before `--upstream` is even opened (it names nothing
    that exists)."""
    root = a_bare_root(tmp_path)
    junction_at(monkeypatch, {root / junction: r"\\?\C:\elsewhere"})
    args = SimpleNamespace(root=str(root), upstream=str(tmp_path / "none"),
                           at=None)

    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.prepare(args)
    assert refused.value.code == "update-rewrite-symlink"
    assert said(refused_at, junction, r"\\?\C:\elsewhere") in \
        refused.value.detail
