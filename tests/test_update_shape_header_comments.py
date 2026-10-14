# SPDX-License-Identifier: Apache-2.0
"""A `files:` or `shape:` header that carries a trailing comment is rewritten,
and keeps it (#437).

#380 made the `commit:` and `tree_sha256:` rewrites keep each line's
indentation and comment. The two BLOCK HEADERS were still matched as
`line.rstrip() == "files:"` and `line.rstrip() == "shape:"`, so a header
followed by a comment, which the reader and both validators accept, was
refused after `check` had sent the person to `apply`: `files:  # one row per
copied file` as `update-pin-unrecognised` ("0 `files` line(s)"), and
`shape:  # mirrors contracts/shape-pin.yaml` as `update-manifest-no-shape`,
which was false (the manifest has the block) and whose remedy, "add it",
would have given the manifest a second `shape:` key.

Both headers are now found with the reader's own `_strip_comment`, at column
0, and the line is written back as it was. That is the whole claim: the
reader's rule for a comment, and nothing about how else a key may be spelled
(a quoted `"files":` or `files :` is not found, as it was not before).

TWO LEVELS, as the issue's reproduction asks for the second and #380's tests
for the first: the rewrites called in-process on the text the scaffold
renders (no scaffold, no git), and `apply` run end to end on a scaffolded
project and on a family holder, whose `family.yaml` `shape:` block goes
through the same function.

FIXTURES ARE BYTES. A comment is put on a header with `write_bytes` and a
regular expression that keeps a carriage return where there is one, so no
Windows `write_text` newline translation reaches a comparison, which is made
against what the same tool wrote for a project with no comment.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import ORG, REPO, git, run_script
from test_family import upstream_clone
from test_pin_rewrite_layout import (MANIFEST, NEW_COMMIT, NEW_ROWS, NEW_TREE,
                                     OLD_COMMIT, OLD_ROWS, OLD_TREE, make_pin,
                                     read_back)
from test_update_shape import (CHANGED_SOURCE, PROJECT, UPSTREAM_FIX_LINE,
                               apply, commit_upstream_changes, next_line_of,
                               scaffold_upstream_and_project)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, parse_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
PIN = "contracts/shape-pin.yaml"
HOLDER = "Contoso"
FAMILY_SOURCE = "templates/family-root/scripts/validate-family.py"

#: Every way a comment may follow a header. `_strip_comment` takes a `#` after
#: a space or a tab, and a later `#` or a quote inside the comment is part of
#: it.
COMMENTS = {
    "two spaces": "  # one row per copied file",
    "one space": " # one row per copied file",
    "a tab": "\t# one row per copied file",
    "a hash inside it": "  # rows, then # more",
    "quotes inside it": '  # the "files" we copy, and the \'rest\'',
    "nothing after the hash": " #",
}


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so the rewrites are called in-process."""
    spec = importlib.util.spec_from_file_location("header_comments_update",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def with_comment(text: str, key: str, comment: str) -> str:
    """`text` with `comment` after its one column-0 `<key>:` header line."""
    marker = f"\n{key}:\n"
    assert text.count(marker) == 1, f"fixture: one `{key}:` header"
    return text.replace(marker, f"\n{key}:{comment}\n")


def comment_the_header(path: Path, key: str, comment: str) -> None:
    """The same, on a file, in BYTES, keeping a CR where the file has one."""
    pattern = b"(?m)^" + key.encode() + b":(\\r?)$"
    data, count = re.subn(
        pattern, lambda found: key.encode() + b":" + comment.encode()
        + found.group(1), path.read_bytes(), count=1)
    assert count == 1, f"fixture: one `{key}:` header in {path}"
    path.write_bytes(data)


def rows_of(update_shape, rows):
    return [update_shape.Row(path, digest) for path, digest in rows]


# --- the rewrites, in-process -------------------------------------------------


@pytest.mark.parametrize("kind", ["assembly shape pin", "family shape pin"])
@pytest.mark.parametrize("comment", COMMENTS.values(), ids=COMMENTS)
def test_a_files_header_with_a_comment_is_rewritten_and_keeps_it(
        update_shape, kind, comment):
    """THE ISSUE'S PIN CASE. The result is the scaffold's own rendering of
    the target, with the header line as it was; the reader takes it back."""
    before = with_comment(make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS),
                          "files", comment)
    expected = with_comment(make_pin(kind, NEW_COMMIT, NEW_TREE, NEW_ROWS),
                            "files", comment)
    assert read_back(before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader accepts the commented header")

    new = update_shape.rewrite_shape_pin(before, NEW_COMMIT, NEW_TREE,
                                         rows_of(update_shape, NEW_ROWS))

    assert new == expected
    assert f"\nfiles:{comment}\n" in new
    assert read_back(new) == (NEW_COMMIT, NEW_TREE)
    assert [row["path"] for row in parse_yaml(new)["files"]] == [
        path for path, _ in NEW_ROWS], "the rows under it are written whole"


@pytest.mark.parametrize("kind", ["assembly shape pin", "family shape pin"])
def test_a_files_header_with_trailing_blanks_only_is_written_bare(
        update_shape, kind):
    """A header with no comment loses its trailing whitespace, as every line
    `with_scalar` writes does, so a scaffold-shaped pin is still rewritten to
    the scaffold's own bytes (#380's identity)."""
    before = make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS).replace(
        "\nfiles:\n", "\nfiles:   \n", 1)

    new = update_shape.rewrite_shape_pin(before, NEW_COMMIT, NEW_TREE,
                                         rows_of(update_shape, NEW_ROWS))

    assert new == make_pin(kind, NEW_COMMIT, NEW_TREE, NEW_ROWS)


@pytest.mark.parametrize("kind_name", ["PROJECT_KIND", "FAMILY_KIND"])
@pytest.mark.parametrize("comment", COMMENTS.values(), ids=COMMENTS)
def test_a_shape_header_with_a_comment_is_rewritten_and_keeps_it(
        update_shape, kind_name, comment):
    """THE ISSUE'S MANIFEST CASE, for a project's `project.yaml` and for a
    holder's `family.yaml`, which goes through the same function. Only the
    block's two values move: the member row's own `commit:` above it, the
    header and the key after the block stay as they were."""
    member = "e" * 40
    before = with_comment(
        MANIFEST.format(member=member, commit=OLD_COMMIT, tree=OLD_TREE),
        "shape", comment)

    new = update_shape.rewrite_manifest(
        before, NEW_COMMIT, NEW_TREE, getattr(update_shape, kind_name))

    assert new == with_comment(
        MANIFEST.format(member=member, commit=NEW_COMMIT, tree=NEW_TREE),
        "shape", comment)
    shape = parse_yaml(new)["shape"]
    assert (shape["commit"], shape["digests"]["tree_sha256"]) == (
        NEW_COMMIT, NEW_TREE)


# --- a header that is missing is still refused, and a doubled one is refused
# --- by name ---------------------------------------------------------------------


@pytest.mark.parametrize("damage", [
    pytest.param(lambda text: text.replace("\nfiles:\n", "\nrows:\n", 1),
                 id="absent"),
    pytest.param(lambda text: text.replace("\nfiles:\n", "\n  files:\n", 1),
                 id="indented"),
    pytest.param(lambda text: text.replace("\nfiles:\n", "\n# files:\n", 1),
                 id="commented-out"),
    pytest.param(lambda text: text.replace("\nfiles:\n", "\nfiles:#rows\n", 1),
                 id="comment-glued-on"),
])
def test_a_pin_with_no_files_header_is_still_refused_by_its_count(
        update_shape, damage):
    """The count is unchanged: no `files:` line at column 0 is `0`, whatever
    else on the line looks like one. Nothing is written, since this is the
    rewrite's own refusal."""
    before = make_pin("assembly shape pin", OLD_COMMIT, OLD_TREE, OLD_ROWS)
    broken = damage(before)
    assert broken != before

    with pytest.raises(Refusal) as caught:
        update_shape.rewrite_shape_pin(broken, NEW_COMMIT, NEW_TREE,
                                       rows_of(update_shape, NEW_ROWS))

    assert caught.value.code == "update-pin-unrecognised"
    assert "has 0 `files` line(s) where exactly one was expected" in \
        caught.value.detail


@pytest.mark.parametrize("kind_name, validator", [
    ("PROJECT_KIND", "validate-manifest.py"),
    ("FAMILY_KIND", "validate-family.py")])
@pytest.mark.parametrize("damage", [
    pytest.param(lambda text: text.replace("\nshape:\n", "\nelected:\n", 1),
                 id="absent"),
    pytest.param(lambda text: text.replace("\nshape:\n", "\n  shape:\n", 1),
                 id="indented"),
    pytest.param(lambda text: text.replace("\nshape:\n", "\n# shape:\n", 1),
                 id="commented-out"),
])
def test_a_manifest_with_no_shape_header_still_names_this_kinds_validator(
        update_shape, kind_name, validator, damage):
    """`update-manifest-no-shape` is kept for a manifest that really has no
    `shape:` block at column 0, and its remedy still names the validator the
    kind carries."""
    before = MANIFEST.format(member="e" * 40, commit=OLD_COMMIT, tree=OLD_TREE)
    broken = damage(before)
    assert broken != before

    with pytest.raises(Refusal) as caught:
        update_shape.rewrite_manifest(broken, NEW_COMMIT, NEW_TREE,
                                      getattr(update_shape, kind_name))

    assert caught.value.code == "update-manifest-no-shape"
    assert validator in caught.value.remediation


def doubled_manifest() -> str:
    """A manifest whose `shape:` key is written twice, the second block holding
    the old values: the reader keeps the LAST block."""
    doubled = (MANIFEST.format(member="e" * 40, commit=OLD_COMMIT,
                               tree=OLD_TREE)
               + f'shape:\n  commit: "{OLD_COMMIT}"\n  digests:\n'
                 f'    tree_sha256: "{OLD_TREE}"\n')
    assert parse_yaml(doubled)["shape"]["commit"] == OLD_COMMIT, (
        "fixture: the reader keeps the last block")
    return doubled


@pytest.mark.parametrize("kind_name", ["PROJECT_KIND", "FAMILY_KIND"])
@pytest.mark.parametrize("which", ["neither", "first", "last", "both"])
def test_a_doubled_shape_header_is_refused_by_name_as_a_key_written_twice(
        update_shape, kind_name, which):
    """THE READER DOES NOT REFUSE A DOUBLED `shape:` (it keeps the last), and a
    rewrite of the first block would move a pin nobody reads. It is refused
    BY NAME, in words that are true of a key written twice, whichever header
    carries a comment: the read-back's, "this tool's line rewrite", are not.
    On main a first header with a comment was skipped by the exact match, so
    that manifest was rewritten at its last block and went through (review of
    PR #558); it is refused here, as the uncommented one always was."""
    text = doubled_manifest()
    first, last = text.index("\nshape:\n"), text.rindex("\nshape:\n")
    assert first != last
    if which in ("first", "both"):
        text = text[:first] + "\nshape:  # first\n" + text[first + 8:]
    if which in ("last", "both"):
        last = text.rindex("\nshape:\n")
        text = text[:last] + "\nshape:  # last\n" + text[last + 8:]
    assert (text != doubled_manifest()) is (which != "neither")

    with pytest.raises(Refusal) as caught:
        update_shape.rewrite_manifest(text, NEW_COMMIT, NEW_TREE,
                                      getattr(update_shape, kind_name))

    kind = getattr(update_shape, kind_name)
    assert caught.value.code == "update-manifest-unrecognised"
    assert caught.value.detail.startswith(
        f"{kind.manifest} holds the `shape:` key twice, at lines 8 and 17, "
        "where exactly one was expected: the reader keeps the last block")
    assert "Remediation: delete the extra `shape:` block by hand" in \
        caught.value.remediation
    assert "line rewrite" not in (caught.value.detail
                                  + caught.value.remediation)


# --- `apply`, end to end ------------------------------------------------------


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A, its upstream moved to B, and the line-for-line control
    this file compares with: the same project with no comment, applied."""
    base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-header-comments")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    assert commit_a != commit_b
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b}


@pytest.fixture(scope="module")
def controlled(project, tmp_path_factory) -> dict:
    """What `apply` writes for a project with NO comment on either header:
    the bytes of its pin and its manifest after the update."""
    root = tmp_path_factory.mktemp("header-comments-control") / PROJECT
    shutil.copytree(project["clone"], root, symlinks=True)
    result = apply(root, project)
    assert result.returncode == 0, result.stdout + result.stderr
    return {"pin": (root / PIN).read_bytes(),
            "manifest": (root / "project.yaml").read_bytes()}


@pytest.fixture
def root(project, tmp_path) -> Path:
    """A private, mutable copy of the project as it was scaffolded at A."""
    target = tmp_path / PROJECT
    shutil.copytree(project["clone"], target, symlinks=True)
    return target


def expected_bytes(control: bytes, key: str, comment: str) -> bytes:
    """`control`, which `apply` wrote with bare headers, with the comment the
    project's own header carried put after `key:`."""
    marker = f"\n{key}:".encode()
    data, count = re.subn(
        re.escape(marker) + b"(\\r?)\n",
        lambda found: marker + comment.encode() + found.group(1) + b"\n",
        control, count=1)
    assert count == 1
    return data


@pytest.mark.parametrize("which", ["pin", "manifest", "both"])
@pytest.mark.parametrize("comment", [COMMENTS["two spaces"],
                                     COMMENTS["a tab"]],
                         ids=["two-spaces", "tab"])
def test_apply_takes_the_update_for_a_header_with_a_comment_and_keeps_it(
        project, controlled, root, which, comment):
    """THE ISSUE'S TWO REPRODUCTIONS, and both at once. `check` sends the
    person to `apply`, which now exits 0 with each comment where it was and
    every other byte what it is for a project with no comment: it wrote the
    same bytes, and its own validators, which `apply` runs, are green."""
    if which in ("pin", "both"):
        comment_the_header(root / PIN, "files", comment)
    if which in ("manifest", "both"):
        comment_the_header(root / "project.yaml", "shape", comment)
    checked = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                         str(project["upstream"]), "--at", project["b"])
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "apply" in next_line_of(checked.stdout)

    result = apply(root, project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-pin-unrecognised" not in result.stderr
    assert "update-manifest-no-shape" not in result.stderr
    pin_wanted = (expected_bytes(controlled["pin"], "files", comment)
                  if which in ("pin", "both") else controlled["pin"])
    manifest_wanted = (expected_bytes(controlled["manifest"], "shape", comment)
                       if which in ("manifest", "both")
                       else controlled["manifest"])
    assert (root / PIN).read_bytes() == pin_wanted
    assert (root / "project.yaml").read_bytes() == manifest_wanted
    for validator in ("validate-pins.py", "validate-manifest.py"):
        green = run_script(root / "scripts" / validator, cwd=root)
        assert green.returncode == 0, green.stdout + green.stderr


def test_a_commented_header_lands_on_a_branch_with_the_comment_in_the_commit(
        project, root):
    """`--branch` commits the pin and the manifest from the working tree, so
    the commit holds the commented headers too: what a person reviews is the
    two values and the rows, never a header that lost its comment."""
    comment_the_header(root / PIN, "files", COMMENTS["two spaces"])
    comment_the_header(root / "project.yaml", "shape", COMMENTS["two spaces"])
    git("add", "--", PIN, "project.yaml", cwd=root)
    git("commit", "-q", "-m", "Comment the two headers", cwd=root)

    result = apply(root, project, "--branch", "shape/update-header-comments")

    assert result.returncode == 0, result.stdout + result.stderr
    pin = git("show", f"HEAD:{PIN}", cwd=root).stdout
    assert "\nfiles:  # one row per copied file\n" in pin
    manifest = git("show", "HEAD:project.yaml", cwd=root).stdout
    assert "\nshape:  # one row per copied file\n" in manifest
    assert git("status", "--porcelain", cwd=root).stdout == ""


# --- a family holder ----------------------------------------------------------


@pytest.fixture(scope="module")
def holder_project(tmp_path_factory) -> dict:
    """A real family holder cut into a local bare repository, an upstream
    that has since moved to B, and the control `apply` writes with no
    comment."""
    base = tmp_path_factory.mktemp("header-comments-family")
    created = run_script(
        REPO / "scripts" / "family.py", "init", "--org", ORG,
        "--family", HOLDER, "--created-by", "Test Human",
        "--created-on", "2026-09-09",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert created.returncode == 0, created.stderr + created.stdout
    upstream = upstream_clone(base / "openRepoShape")
    commit_b = commit_upstream_changes(
        upstream, "Fix the family validator",
        {FAMILY_SOURCE: "\n# An upstream fix that must reach every family.\n"})
    clone = base / "work" / HOLDER
    control = base / "control" / HOLDER
    shutil.copytree(clone, control, symlinks=True)
    result = apply(control, {"upstream": upstream, "b": commit_b})
    assert result.returncode == 0, result.stdout + result.stderr
    return {"upstream": upstream, "clone": clone, "b": commit_b,
            "pin": (control / PIN).read_bytes(),
            "manifest": (control / "family.yaml").read_bytes()}


@pytest.mark.parametrize("which", ["pin", "manifest", "both"])
def test_apply_takes_the_update_for_a_family_holder_header_with_a_comment(
        holder_project, tmp_path, which):
    """`family.yaml`'s `shape:` block goes through the same function as
    `project.yaml`'s, and a holder's pin through the same `files:` rewrite:
    each comment is kept, the holder's own validator stays green, and the
    rest is what `apply` wrote for the holder with no comment."""
    holder = tmp_path / HOLDER
    shutil.copytree(holder_project["clone"], holder, symlinks=True)
    comment = COMMENTS["two spaces"]
    if which in ("pin", "both"):
        comment_the_header(holder / PIN, "files", comment)
    if which in ("manifest", "both"):
        comment_the_header(holder / "family.yaml", "shape", comment)

    result = apply(holder, holder_project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-manifest-no-shape" not in result.stderr
    assert (holder / PIN).read_bytes() == (
        expected_bytes(holder_project["pin"], "files", comment)
        if which in ("pin", "both") else holder_project["pin"])
    assert (holder / "family.yaml").read_bytes() == (
        expected_bytes(holder_project["manifest"], "shape", comment)
        if which in ("manifest", "both") else holder_project["manifest"])
    green = run_script(holder / "scripts" / "validate-family.py", cwd=holder)
    assert green.returncode == 0, green.stdout + green.stderr
