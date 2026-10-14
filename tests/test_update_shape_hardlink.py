# SPDX-License-Identifier: Apache-2.0
"""`apply` never rewrites a file that has a second name on disk (#422).

`Rollback.write` opens each file `apply` rewrites `r+b` and overwrites its
bytes where they are. A file kept as a HARD LINK is the same bytes under two
names, so the other name changed too: a file outside the root, or a whole
`cp -al` snapshot of it, that no `check` showed, no pin covers and git does
not record. Only the README's reader asked (`st_nlink > 1`, PR #152). This
file holds the rest, in the places they matter:

  * `apply` REFUSES, as `update-rewrite-hardlink`, exit 2, before `confirm`
    and before any write, every file it would rewrite that has another
    name: a pinned copy it copies, the pin, the manifest, and the root's own
    `.gitattributes` when `--add` would extend its line-ending block (#511).
    The tree is as it was by `lstat` and by bytes, the link is still a link,
    and the other name holds what it held. Several are named together, and
    the lines the refusal prints break each link from the root's side, after
    which the same command applies.
  * `check` SAYS SO FIRST, in one `REFUSAL AHEAD` line, and every row keeps
    the verdict it had: a hard-linked copy holds the right bytes, so it is
    no drift, and the doctor, which reads the rows, is not told otherwise.
  * THE CONTROLS: no link applies; a hard-linked file `apply` does not
    rewrite is left alone, and not refused; a hard-linked `README.md` is
    still `kept`, as #152 made it, rather than refused.
  * THE LEDGER'S OWN GUARD: a name that arrives while an interactive `apply`
    waits in `confirm` is refused by `Rollback.write` itself, and what was
    already written is put back.

`os.link` needs no privilege on NTFS, so these run on all three platforms,
and skip only where the filesystem will not make a link. The pastes go
through `sh`, so those few are POSIX-only.

THE FIXTURE is `tests/test_update_shape_rewrite_symlink.py`'s: a clone of
this repository at A and `Atlas` scaffolded from it into bare repositories on
disk. Commit B edits two pinned copies, `AGENTS-shape.md` and
`scripts/validate-manifest.py`, and adds one file to the assembly root's
lists, for `--add`. No network is used and `gh` is never invoked.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
from test_scaffold_ignored_shape_files import load
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               give_readme, rendered_shape_line,
                               scaffold_upstream_and_project)
from test_update_shape_add import (MATERIALIZER, commit_all, name_in_list,
                                   verdicts)
from test_update_shape_add_symlink import (assert_untouched, beyond,
                                           outside_dir, snapshot)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256, load_yaml  # noqa: E402
from shape_materialize import EOL_BLOCK_HEAD  # noqa: E402

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"
ENV = {"PYTHONDONTWRITEBYTECODE": "1"}

AGENTS = "AGENTS-shape.md"
AGENTS_SOURCE = f"templates/assembly-root/{AGENTS}"
AGENTS_EDIT = b"<!-- an upstream edit -->\n"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"
ATTRIBUTES = ".gitattributes"
#: What B adds to the assembly root's lists, so there is an `--add`.
ADDED = "AGENTS-hardlink-test.md"
ADDED_SOURCE = f"templates/assembly-root/{ADDED}"
ADDED_BODY = b"# The shape's notes, added after this project was cut.\n"
#: A pinned copy B leaves alone, so `apply` never rewrites it.
UNTOUCHED = "Makefile"

#: The three kinds of file every `apply` here rewrites: a copy B changed,
#: the pin, and the manifest that mirrors it.
REWRITTEN = [
    pytest.param(CHANGED, id="a-pinned-copy"),
    pytest.param(PIN, id="the-pin"),
    pytest.param(MANIFEST, id="the-manifest"),
]


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it, and B: two pinned copies edited
    and one file added to the lists."""
    _base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-hardlink")
    for source, edit in ((AGENTS_SOURCE, AGENTS_EDIT),
                         (CHANGED_SOURCE, UPSTREAM_FIX_LINE.encode("utf-8"))):
        path = upstream / source
        # Bytes, so the blob is what was appended on every platform.
        path.write_bytes(path.read_bytes() + edit)
    (upstream / ADDED_SOURCE).write_bytes(ADDED_BODY)
    lists = upstream / MATERIALIZER
    lists.write_bytes(name_in_list(lists.read_bytes().decode("utf-8"),
                                   "COPIED_VERBATIM", ADDED).encode("utf-8"))
    b = commit_all(upstream, "Edit two pinned copies and add a file",
                   [AGENTS_SOURCE, CHANGED_SOURCE, ADDED_SOURCE, MATERIALIZER])
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
    """`update-shape.py` as a module, for the ledger and `confirm`."""
    return load(UPDATE, "update_shape_hardlink")


def check(root, standard, *extra):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def apply(root, standard, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def pinned_commit(root) -> str:
    return str(load_yaml(root / PIN)["commit"]).lower()


def second_name(root: Path, rel: str, tmp_path: Path) -> Path:
    """`ln <root>/<rel> <outside>/<name>`: the issue's second name for a
    file of the root, beside it rather than in it. Skips where this
    filesystem will not make one."""
    other = outside_dir(tmp_path) / Path(rel).name
    try:
        os.link(root / rel, other)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"this filesystem will not hard-link: {exc}")
    return other


def still_one_file(root: Path, rel: str, other: Path) -> None:
    """The link is a link still: both names are one file, with two names.
    A write by replace would pass every byte comparison and fail here."""
    assert os.path.samefile(root / rel, other), f"{rel} is not {other} now"
    assert os.lstat(root / rel).st_nlink == 2


def hard_link_lines(stdout: str) -> list[str]:
    return [line for line in stdout.splitlines()
            if line.startswith("REFUSAL AHEAD") and "another name" in line]


def remedy_lines(stderr: str) -> list[str]:
    """The `cp -p ... && mv -f ...` lines the refusal's remediation ends
    with, one per file."""
    return [line.strip() for line in stderr.splitlines()
            if line.startswith("    cp -p -- ")]


def remedy_for(root: Path, rel: str) -> str:
    """The line the remediation prints for `rel`: the root as `prepare`
    resolved it (macOS's `/var` is `/private/var`), POSIX-quoted."""
    here = str(root.resolve() / rel)
    copy = f"{here}.update-shape-copy"
    return (shlex.join(["cp", "-p", "--", here, copy]) + " && "
            + shlex.join(["mv", "-f", "--", copy, here]))


def assert_refused_before_any_write(result) -> None:
    """Exit 2, by name, said as a refusal made BEFORE `confirm`: nothing
    written, so nothing rolled back, and no name that "arrived"."""
    assert "ROLLED BACK" not in result.stderr, (
        "the refusal came after a write, and the run rolled back:\n"
        + result.stderr)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-rewrite-hardlink" in result.stderr, result.stderr
    assert "This command never writes through a hard link" in result.stderr
    assert "arrived" not in result.stderr, result.stderr
    assert "copied   " not in result.stdout, result.stdout
    assert "re-pinned" not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# `check` says so first, and no row changes its verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", REWRITTEN)
def test_check_says_refusal_ahead_and_every_row_keeps_its_verdict(
        root, standard, tmp_path, rel):
    """One `REFUSAL AHEAD` line names the path and how many names it has.
    Every verdict, the counts and the exit code are the ones the same root
    gets with no link at all: a hard-linked copy holds the right bytes, so
    a row state of its own would make the doctor call it drift."""
    control = tmp_path / "control" / PROJECT
    shutil.copytree(standard["clone"], control, symlinks=True)
    plain = check(control, standard)
    other = second_name(root, rel, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = check(root, standard)
    assert result.returncode == plain.returncode == 1, (
        result.stdout + result.stderr)
    assert verdicts(result.stdout) == verdicts(plain.stdout), result.stdout
    assert verdicts(result.stdout)[CHANGED] == "upstream-changed"
    assert hard_link_lines(plain.stdout) == []
    said = hard_link_lines(result.stdout)
    assert len(said) == 1, (
        f"one REFUSAL AHEAD line was expected, and {len(said)} were "
        f"printed: {result.stdout}")
    assert said[0].endswith(f" — {rel} (2 names)"), (
        f"the line does not end with the path and its count: {said[0]!r}")
    assert "REFUSAL AHEAD: `apply` will refuse while" not in result.stdout, (
        "a hard link is not counted among the conflicts")
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere
    still_one_file(root, rel, other)


# ---------------------------------------------------------------------------
# `apply` refuses before any write
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("branch", [None, "shape/update-hard"],
                         ids=["no-branch", "branch"])
@pytest.mark.parametrize("rel", REWRITTEN)
def test_apply_refuses_a_hard_linked_rewrite_before_any_write(
        root, standard, tmp_path, rel, branch):
    """THE ISSUE. Main wrote B's bytes, or the re-pin, into the other name
    as well and exited 0. Now the run refuses by name before the first
    write: the tree is as it was by `lstat` and by bytes, HEAD and every
    branch with it, the link is still one file, and the other name holds
    what it held."""
    other = second_name(root, rel, tmp_path)
    held = other.read_bytes()
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, *(("--branch", branch) if branch else ()))
    # THE INVARIANT FIRST: a failure on main names the write through the
    # other name, not the wording.
    assert other.read_bytes() == held, (
        f"{rel} was rewritten THROUGH its other name, outside the root")
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    still_one_file(root, rel, other)
    assert pinned_commit(root) == standard["a"]
    assert_refused_before_any_write(result)
    assert (f"`apply` would rewrite {rel} in place, but it has 2 names on "
            "this filesystem.") in result.stderr, result.stderr
    assert remedy_lines(result.stderr) == [remedy_for(root, rel)], (
        result.stderr)
    assert "nothing to commit" in result.stderr


def test_several_are_named_together(root, standard, tmp_path):
    """Two files with second names are one refusal listing both, one path
    a line, and one remedy line each, in the order `apply` writes them."""
    for rel in (CHANGED, PIN):
        second_name(root, rel, tmp_path)
    before = snapshot(root)

    result = apply(root, standard)
    assert_refused_before_any_write(result)
    assert ("`apply` would rewrite these files in place, but each has "
            "another name on this filesystem:\n"
            f"    {CHANGED}: 2 names\n    {PIN}: 2 names\n") in result.stderr
    assert remedy_lines(result.stderr) == [remedy_for(root, CHANGED),
                                           remedy_for(root, PIN)]
    assert_untouched(before, snapshot(root))


@WINDOWS_SKIP
def test_the_remedy_breaks_each_link_and_the_same_command_then_applies(
        root, standard, tmp_path):
    """The printed lines, pasted: each file of the root is a file of its
    own again, with its bytes and its mode, the other names keep theirs, git
    sees nothing to commit, and the same `apply` then lands B everywhere but
    in those other names."""
    others = {rel: second_name(root, rel, tmp_path)
              for rel in (CHANGED, PIN, MANIFEST)}
    held = {rel: other.read_bytes() for rel, other in others.items()}
    modes = {rel: os.lstat(root / rel).st_mode for rel in others}
    status = git("status", "--porcelain", cwd=root).stdout

    refused = apply(root, standard)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    lines = remedy_lines(refused.stderr)
    assert len(lines) == 3, refused.stderr
    for line in lines:
        subprocess.run(["sh", "-c", line], check=True)

    for rel, other in others.items():
        assert not os.path.samefile(root / rel, other), rel
        assert (root / rel).read_bytes() == held[rel] == other.read_bytes()
        assert os.lstat(root / rel).st_mode == modes[rel], rel
        assert not Path(f"{root / rel}.update-shape-copy").exists()
    assert git("status", "--porcelain", cwd=root).stdout == status, (
        "breaking a link is no change git can see")

    result = apply(root, standard)
    assert result.returncode == 0, result.stdout + result.stderr
    assert pinned_commit(root) == standard["b"]
    assert (root / CHANGED).read_bytes().endswith(
        UPSTREAM_FIX_LINE.encode("utf-8"))
    for rel, other in others.items():
        assert other.read_bytes() == held[rel], (
            f"{other} moved with {rel} after the link was broken")


# ---------------------------------------------------------------------------
# The controls
# ---------------------------------------------------------------------------


def test_with_no_second_name_apply_rewrites_as_before(root, standard):
    """No link anywhere: B's copies are written, the pin moves, and nothing
    is said about links."""
    result = apply(root, standard)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-rewrite-hardlink" not in result.stderr
    assert pinned_commit(root) == standard["b"]
    assert (root / AGENTS).read_bytes().endswith(AGENTS_EDIT)


def test_a_hard_linked_file_apply_does_not_rewrite_is_left_alone(
        root, standard, tmp_path):
    """`Makefile` is a pinned copy B does not change, so `apply` writes
    nothing at it: a second name there is nobody's business here. `check`
    says nothing about it and `apply` lands B, with the Makefile and its
    other name one file, as they were."""
    other = second_name(root, UNTOUCHED, tmp_path)
    held = other.read_bytes()

    checked = check(root, standard)
    assert hard_link_lines(checked.stdout) == [], checked.stdout
    assert verdicts(checked.stdout)[UNTOUCHED] == "unchanged"

    result = apply(root, standard)
    assert result.returncode == 0, result.stdout + result.stderr
    assert pinned_commit(root) == standard["b"]
    assert other.read_bytes() == held
    still_one_file(root, UNTOUCHED, other)


def test_a_hard_linked_readme_is_still_kept(root, standard, tmp_path):
    """THE ONE PATH #152 GUARDED, guarded as it was. Its reader keeps a
    README with another name and says so; the hard-link refusal is not
    asked about it, so `apply` lands the re-pin and leaves the README, its
    stale line and its other name exactly as they were."""
    readme = give_readme(root, rendered_shape_line(standard["a"]))
    before = readme.read_bytes()
    other = second_name(root, "README.md", tmp_path)

    checked = check(root, standard)
    assert "readme-shape-line: hard-link" in checked.stdout
    assert hard_link_lines(checked.stdout) == [], checked.stdout

    result = apply(root, standard, "--branch", "shape/update-readme")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-rewrite-hardlink" not in result.stderr
    assert ("kept     README.md: another name points at these same bytes, "
            "untouched") in result.stdout
    assert readme.read_bytes() == before == other.read_bytes()
    still_one_file(root, "README.md", other)
    assert pinned_commit(root) == standard["b"]


# ---------------------------------------------------------------------------
# The root's own `.gitattributes`, which `--add` extends (#511)
# ---------------------------------------------------------------------------


def give_attributes_a_block(root: Path, named: tuple) -> None:
    """The root's `.gitattributes` carrying #471's line-ending block, naming
    the copies in `named`, as an adopted root's own file does, committed,
    its pin row moved to the new bytes so the copy reads `unchanged`. A
    scaffolded root stands in for the adopted one, whose own file the pin
    does not carry: what `apply` asks of the file is the same, and an
    adoption costs a filter-repo run."""
    path = root / ATTRIBUTES
    old = file_sha256(path)
    path.write_bytes(path.read_bytes() + "".join(
        f"{line}\n" for line in (EOL_BLOCK_HEAD, *(
            f"/{rel} text eol=lf" for rel in named))).encode("utf-8"))
    pin = (root / PIN).read_bytes()
    assert pin.count(old.encode("ascii")) == 1, "the row is not one row"
    (root / PIN).write_bytes(pin.replace(old.encode("ascii"),
                                         file_sha256(path).encode("ascii")))
    git("add", "--", ATTRIBUTES, PIN, cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "the root's .gitattributes carries the line-ending block", cwd=root)


@pytest.mark.parametrize("block, add, refused", [
    pytest.param((AGENTS,), True, True, id="add-would-extend-the-block"),
    pytest.param((AGENTS,), False, False, id="no-add"),
    pytest.param(None, True, False, id="no-block-to-extend"),
    pytest.param((AGENTS, ADDED), True, False,
                 id="the-block-already-names-the-add"),
])
def test_attributes_are_refused_only_when_add_would_extend_their_block(
        root, standard, tmp_path, block, add, refused):
    """`_extend_the_eol_block` writes the root's own `.gitattributes`
    through the ledger only when `--add` names a file the block does not
    name yet. That one case is refused, by name, before anything is
    written; without `--add`, without a block, or with a block that names
    the file already, the file is not written and its second name is no
    reason to refuse."""
    if block is not None:
        give_attributes_a_block(root, block)
    other = second_name(root, ATTRIBUTES, tmp_path)
    held = other.read_bytes()
    before = snapshot(root)

    result = apply(root, standard, *(("--add", ADDED) if add else ()))
    assert other.read_bytes() == held
    still_one_file(root, ATTRIBUTES, other)
    if refused:
        assert_refused_before_any_write(result)
        assert (f"`apply` would rewrite {ATTRIBUTES} in place, but it has 2 "
                "names on this filesystem.") in result.stderr
        assert not (root / ADDED).exists()
        assert_untouched(before, snapshot(root))
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert (root / ADDED).exists() == add
        assert pinned_commit(root) == standard["b"]


# ---------------------------------------------------------------------------
# The ledger's own guard: a name that arrives after `apply` looked
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arrives_at, restored", [
    pytest.param(CHANGED, (), id="at-the-first-copy"),
    pytest.param(AGENTS, (CHANGED,), id="at-a-later-copy"),
    pytest.param(PIN, (CHANGED, AGENTS), id="at-the-pin"),
    pytest.param(MANIFEST, (CHANGED, AGENTS, PIN), id="at-the-manifest"),
])
def test_a_name_that_arrives_while_apply_waits_is_refused_and_rolled_back(
        update_shape, root, standard, tmp_path, monkeypatch, arrives_at,
        restored):
    """`confirm` is where an interactive `apply` waits for a human, after
    the refusal before it has looked; the second name arrives there. The
    write to it is refused by `Rollback.write`, and whatever was written
    before it is put back by `cmd_apply`'s refusal arm, so the tree is
    exactly as it was when the run began to write and the other name holds
    what it held."""
    seen: dict = {}

    def a_name_arrives(*_args, **_kwargs) -> None:
        seen["other"] = second_name(root, arrives_at, tmp_path)
        seen["held"] = seen["other"].read_bytes()
        seen["root"], seen["beyond"] = snapshot(root), beyond(tmp_path)

    monkeypatch.setattr(update_shape, "confirm", a_name_arrives)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    args = update_shape.build_parser().parse_args([
        "apply", "--root", str(root), "--yes",
        "--upstream", str(standard["upstream"]), "--at", standard["b"]])

    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.cmd_apply(args)
    assert seen["other"].read_bytes() == seen["held"], (
        f"{arrives_at} was rewritten THROUGH its other name")
    assert beyond(tmp_path) == seen["beyond"]
    assert_untouched(seen["root"], snapshot(root))
    still_one_file(root, arrives_at, seen["other"])
    assert refused.value.code == "update-rewrite-hardlink"
    assert (f"`apply` would rewrite {arrives_at} in place, but it has 2 "
            "names on this filesystem.") in refused.value.detail
    assert "It had no other name when this run looked" in refused.value.detail
    if restored:
        assert "ROLLED BACK: every byte" in refused.value.detail, (
            refused.value.detail)
    else:
        assert "ROLLED BACK" not in refused.value.detail, (
            "nothing was written before it, so nothing is put back")
    for rel in restored:
        assert f"restored  {rel}" in refused.value.detail


def test_the_ledger_never_rewrites_a_file_with_another_name(update_shape,
                                                            tmp_path):
    """The guard alone, with nothing in front of it. Main opened the path
    `r+b` and overwrote the bytes both names share. Refused by name now,
    with nothing read into the ledger, so there is nothing for an undo to
    write back through the other name either."""
    root = tmp_path / PROJECT
    root.mkdir()
    (root / "agents.md").write_bytes(b"the project's bytes\n")
    other = second_name(root, "agents.md", tmp_path)
    ledger = update_shape.Rollback(root)

    with pytest.raises(update_shape.Refusal) as refused:
        ledger.write(root / "agents.md", b"the standard's bytes\n")
    assert other.read_bytes() == b"the project's bytes\n"
    assert ledger.written == {}
    assert refused.value.code == "update-rewrite-hardlink"
    still_one_file(root, "agents.md", other)


def test_how_many_names_is_asked_of_a_regular_file_only(update_shape,
                                                        tmp_path):
    """`hard_links`: a count only for a regular file with more than one
    name. One name, a directory, nothing at all — 0; and a symlink is
    never followed to the count of what it leads to, where the platform
    lets this test make one."""
    alone = tmp_path / "alone"
    alone.write_bytes(b"x")
    twice = tmp_path / "twice"
    twice.write_bytes(b"y")
    second_name(tmp_path, "twice", tmp_path)

    assert update_shape.hard_links(alone) == 0
    assert update_shape.hard_links(twice) == 2
    assert update_shape.hard_links(tmp_path) == 0
    assert update_shape.hard_links(tmp_path / "nothing-here") == 0
    link = tmp_path / "a-symlink"
    try:
        link.symlink_to(twice)
    except OSError:  # pragma: no cover - Windows without the privilege
        return
    assert update_shape.hard_links(link) == 0
