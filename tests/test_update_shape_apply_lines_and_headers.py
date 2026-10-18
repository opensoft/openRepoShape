# SPDX-License-Identifier: Apache-2.0
"""`update-shape.py apply` prints no line that fails as printed, and finds the
pin's `files:` and the manifest's `shape:` headers wherever the reader finds
them (#674).

FOUR CASES, each measured on main before the fix:

  * THE ROLLBACK LINE. A validator that deleted `contracts/shape-pin.yaml`
    and left `contracts/` at 0555 was handed the bare `git cat-file blob <id>
    > <pin>`, and pasted, that fails `Permission denied`: the directory the
    redirect creates the file in will not take it. The line now says `so make
    <that directory> writable, then:` first, naming `_nearest_directory`'s
    answer, which is the root itself where `contracts/` went too. A directory
    that exists over an absent file is the case #560's tests left out (its
    `os.path.lexists` choice, #458's 6192496098).
  * THE `committed on <branch>:` LINE named `paths`, which always holds the
    pin and the manifest, so a run that drops a merged-away row, or keeps a
    copy with `--accept-local` at the pinned commit, said `project.yaml` of a
    commit without it. It names what git says the commit holds now.
  * A BRANCH NAMED LIKE A TAG. In a root tagged `v1.0.0`, `--branch v1.0.0
    --push` committed and died at the push, `src refspec v1.0.0 matches more
    than one`, and both printed push lines failed the same way pasted. They
    name the branch in full now, `refs/heads/<b>:refs/heads/<b>`. And
    `current_branch` read `heads/v1.0.0` there (`--short`), so a root ON that
    branch was refused `update-branch-exists`, and a `--pr` re-run on it said
    "nothing to do" and opened nothing.
  * A QUOTED HEADER. `"files":`, `'files':` and `files :` are the key `files`
    to the reader and to both validators, so `check` sent the person to an
    `apply` that refused `update-pin-unrecognised`, and `"shape":` got
    `update-manifest-no-shape`, "has no `shape:` block". The headers are found
    with the reader's own `_split_key` now, and written back as they were.

AND THE BRANCH HEAD IS ON, READ AS GIT WROTE IT (#765): a trailing no-break
space stays on it, and a name that is not UTF-8 is refused by name
(`update-branch-not-utf8`) before the first write of a `--branch` run.

THE HARNESSES ARE THE NEIGHBOURS'.
`tests/test_update_shape_partial_rollback.py` gives the upstream (A, B above
it, C above that), the project cut at A into local bare remotes, and the
ledger run in process; `tests/test_pin_rewrite_layout.py` the pins the
scaffold renders; `tests/test_update_shape_landing.py` its `gh` stub; and
`tests/test_update_shape_merged_away.py` the adoption that makes the issue's
own merged-away row. No network is used and no real `gh`
is ever run. Every push goes to a bare remote of the test's own, so no test
moves another's, and every pasted push is run as the argv `sh` would read,
without a shell, so that half runs on every platform.
"""

from __future__ import annotations

import errno
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (NOT_UTF_8_BRANCH_NAMED, REPO, WINDOWS_SKIP, git,
                      held_by_git, on_a_branch_that_is_not_utf_8, run_script)
from test_pin_rewrite_layout import MANIFEST as MANIFEST_TEXT
from test_pin_rewrite_layout import (NEW_COMMIT, NEW_ROWS, NEW_TREE,
                                     OLD_COMMIT, OLD_ROWS, OLD_TREE, make_pin,
                                     read_back)
from test_shape_doctor import standard as doctor_standard  # noqa: F401
from test_update_shape import next_line_of
from test_update_shape_landing import URL, gh, listing  # noqa: F401
from test_update_shape_merged_away import (MERGED, SOURCE_TREE,
                                           adopt_and_clone, merge_away)
from test_update_shape_partial_rollback import (  # noqa: F401
    AGENTS, BRANCH, CHANGED, DENIED, MANIFEST, PIN, apply_args,
    assert_reported_as_red, held, left, put_back, refused_by, root, standard,
    update_shape,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, parse_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"

#: The branch the issue names, and the tag beside it that takes its name.
TAGGED = "v1.0.0"
#: That branch as all three push lines now name it.
FULL = f"refs/heads/{TAGGED}:refs/heads/{TAGGED}"


def apply(standard, root: Path, at: str, *extra: str, env=None):
    """`apply --yes` at `standard[at]`, through the real tool."""
    return run_script(UPDATE, *apply_args(standard, root, at, *extra),
                      env=env)


def head_of(path: Path) -> str:
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


# ---------------------------------------------------------------------------
# A header the reader takes is one the rewrite finds
# ---------------------------------------------------------------------------

#: Each spelling of a header the reader reads as the bare key, `{key}` for
#: the key: quoted either way, a space before the colon, both, and a quoted
#: one with a trailing comment (#437's half of the same rule).
SPELLINGS = {
    "double-quoted": '"{key}":',
    "single-quoted": "'{key}':",
    "space-before-colon": "{key} :",
    "quoted-and-spaced": '"{key}" :',
    "quoted-with-comment": '"{key}":  # one row per copied file',
}


def with_header(text: str, key: str, spelling: str) -> str:
    """`text` with its one column-0 `<key>:` header spelled `spelling`."""
    marker = f"\n{key}:\n"
    assert text.count(marker) == 1, f"fixture: one `{key}:` header"
    return text.replace(marker, "\n" + spelling.format(key=key) + "\n")


def manifest_text(spelling: str, commit: str, tree: str) -> str:
    """`tests/test_pin_rewrite_layout.py`'s manifest, its `shape:` header
    spelled `spelling`: a leg's own `commit:` above the block, and a key
    after it, so a rewrite that ran past the block would show."""
    return with_header(MANIFEST_TEXT.format(member="e" * 40, commit=commit,
                                            tree=tree), "shape", spelling)


@pytest.mark.parametrize("kind", ["assembly shape pin", "family shape pin"])
@pytest.mark.parametrize("spelling", SPELLINGS.values(), ids=SPELLINGS)
def test_a_files_header_the_reader_takes_is_rewritten_as_it_was(
        update_shape, kind, spelling):
    """THE ISSUE'S PIN CASE. The reader gives each spelling a `files` key, so
    the rewrite finds it: the result is the scaffold's own rendering of the
    target with the header spelled as it was, and the reader takes it
    back, rows and all."""
    before = with_header(make_pin(kind, OLD_COMMIT, OLD_TREE, OLD_ROWS),
                         "files", spelling)
    assert read_back(before) == (OLD_COMMIT, OLD_TREE)
    assert [row["path"] for row in parse_yaml(before)["files"]] == [
        path for path, _ in OLD_ROWS], "fixture: the reader takes the key"

    new = update_shape.rewrite_shape_pin(
        before, NEW_COMMIT, NEW_TREE,
        [update_shape.Row(path, digest) for path, digest in NEW_ROWS])

    assert new == with_header(make_pin(kind, NEW_COMMIT, NEW_TREE, NEW_ROWS),
                              "files", spelling)
    assert read_back(new) == (NEW_COMMIT, NEW_TREE)
    assert [row["path"] for row in parse_yaml(new)["files"]] == [
        path for path, _ in NEW_ROWS]


@pytest.mark.parametrize("kind_name", ["PROJECT_KIND", "FAMILY_KIND"])
@pytest.mark.parametrize("spelling", SPELLINGS.values(), ids=SPELLINGS)
def test_a_shape_header_the_reader_takes_is_found_and_kept(
        update_shape, kind_name, spelling):
    """THE ISSUE'S MANIFEST CASE, for `project.yaml` and for a holder's
    `family.yaml`, which goes through the same function. It was refused
    `update-manifest-no-shape`, saying the manifest "has no `shape:` block"
    of one the reader gives a `shape` key. Only the block's two values
    move; the header stays as it was spelled."""
    before = manifest_text(spelling, OLD_COMMIT, OLD_TREE)
    assert parse_yaml(before)["shape"]["commit"] == OLD_COMMIT, (
        "fixture: the reader takes the key")

    new = update_shape.rewrite_manifest(before, NEW_COMMIT, NEW_TREE,
                                        getattr(update_shape, kind_name))

    assert new == manifest_text(spelling, NEW_COMMIT, NEW_TREE)
    shape = parse_yaml(new)["shape"]
    assert (shape["commit"], shape["digests"]["tree_sha256"]) == (
        NEW_COMMIT, NEW_TREE)


@pytest.mark.parametrize("quoted_first", [True, False],
                         ids=["quoted-first", "quoted-last"])
def test_a_quoted_shape_header_beside_a_bare_one_is_the_key_written_twice(
        update_shape, quoted_first):
    """The reader reads `"shape":` and `shape:` as ONE key written twice and
    keeps the last block, so this finder, asking the reader's question, sees
    two headers and refuses by name, as #558 refuses a bare `shape:` twice.
    The bare-only finder saw one: with the bare header first it rewrote a
    block nobody reads, and the read-back blamed "this tool's line
    rewrite"."""
    extra = 'shape:\n  commit: "{0}"\n  digests:\n    tree_sha256: "{1}"\n'
    text = (manifest_text("shape:", OLD_COMMIT, OLD_TREE)
            + extra.format(OLD_COMMIT, OLD_TREE))
    lines = text.splitlines()
    first, last = [index for index, line in enumerate(lines)
                   if line == "shape:"]
    quoted = first if quoted_first else last
    lines[quoted] = '"shape":'
    text = "\n".join(lines) + "\n"
    assert parse_yaml(text)["shape"]["commit"] == OLD_COMMIT

    with pytest.raises(Refusal) as caught:
        update_shape.rewrite_manifest(text, NEW_COMMIT, NEW_TREE,
                                      update_shape.PROJECT_KIND)

    assert caught.value.code == "update-manifest-unrecognised"
    assert caught.value.detail.startswith(
        f"project.yaml holds the `shape:` key twice, at lines {first + 1} "
        f"and {last + 1}, where exactly one was expected: the reader keeps "
        "the last block"), caught.value.detail
    assert "line rewrite" not in caught.value.detail + caught.value.remediation


@pytest.mark.parametrize("header", [
    pytest.param('  "files":', id="indented"),
    pytest.param('"files":#rows', id="comment-glued-on"),
    pytest.param('"files" rows:', id="quoted-key-then-text"),
    pytest.param("files[0]:", id="bracket-in-key"),
])
def test_a_line_that_is_no_files_header_to_the_reader_is_still_counted_none(
        update_shape, header):
    """The column and the rest of the line are the reader's too. Indented,
    or with a comment glued on, the line is no top-level `files` key, and
    the last two are lines `_split_key` refuses, as the reader refuses the
    file holding one: here each is no header, never a traceback, and the
    rewrite's own count refuses, before any byte is written (it only
    returns text)."""
    before = with_header(make_pin("assembly shape pin", OLD_COMMIT, OLD_TREE,
                                  OLD_ROWS), "files", header)

    rows = [update_shape.Row(path, digest) for path, digest in NEW_ROWS]

    with pytest.raises(Refusal) as caught:
        update_shape.rewrite_shape_pin(before, NEW_COMMIT, NEW_TREE, rows)

    assert caught.value.code == "update-pin-unrecognised"
    assert "has 0 `files` line(s) where exactly one was expected" in \
        caught.value.detail


def respell_the_header(path: Path, key: str, spelling: str) -> None:
    """`path`'s column-0 `<key>:` line spelled `spelling`, in BYTES, keeping a
    CR where the file has one, so no newline translation is compared."""
    data, count = re.subn(
        b"(?m)^" + key.encode() + b":(\\r?)$",
        lambda found: spelling.format(key=key).encode() + found.group(1),
        path.read_bytes(), count=1)
    assert count == 1, f"fixture: one `{key}:` header in {path}"
    path.write_bytes(data)


@pytest.mark.parametrize("key, path", [("files", PIN), ("shape", MANIFEST)],
                         ids=["pin", "manifest"])
def test_check_and_apply_agree_on_a_quoted_header(standard, root, key, path):
    """THE ISSUE'S RUN, end to end. Both validators pass the quoted header
    and `check` sends the person to `apply`, which now takes the update:
    exit 0, the header written back quoted, the pin moved to B, and the
    project's own validators green."""
    respell_the_header(root / path, key, '"{key}":')
    for validator in ("validate-pins.py", "validate-manifest.py"):
        green = run_script(root / "scripts" / validator, cwd=root)
        assert green.returncode == 0, green.stdout + green.stderr
    checked = run_script(UPDATE, "check", "--root", str(root), "--upstream",
                         str(standard["upstream"]), "--at", standard["b"])
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "update-shape.py apply " in next_line_of(checked.stdout)

    result = apply(standard, root, "b")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-pin-unrecognised" not in result.stderr
    assert "update-manifest-no-shape" not in result.stderr
    assert f'\n"{key}":\n' in (root / path).read_text(encoding="utf-8")
    assert parse_yaml((root / PIN).read_text(encoding="utf-8"))[
        "commit"].lower() == standard["b"]
    for validator in ("validate-pins.py", "validate-manifest.py"):
        green = run_script(root / "scripts" / validator, cwd=root)
        assert green.returncode == 0, green.stdout + green.stderr


# ---------------------------------------------------------------------------
# `committed on <branch>:` names what the commit holds
# ---------------------------------------------------------------------------


def assert_said_what_it_committed(result, root: Path, branch: str,
                                  holds: list[str]) -> None:
    """The run exits 0, its commit holds exactly `holds`, as `git show`
    lists them, and its `committed on` line names those and no others."""
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=root).stdout.split() == holds
    said = [line.strip() for line in result.stdout.splitlines()
            if line.strip().startswith("committed on ")]
    assert said == [f"committed on {branch}: " + ", ".join(holds)], said


def test_a_manifest_rewritten_with_its_own_bytes_is_not_said_committed(
        standard, root):
    """`--accept-local` AT THE COMMIT THE PIN NAMES: the kept copy's row is
    recomputed from the project's bytes, so the pin changes, and the
    manifest's `shape:` block is rewritten with the bytes it had. The line
    said `contracts/shape-pin.yaml, project.yaml`; the commit holds the pin
    alone, and the line says so."""
    local = root / "scripts" / "bootstrap.py"
    local.write_bytes(local.read_bytes() + b"# A local edit, kept.\n")
    git("commit", "-q", "-m", "A local edit", "--", "scripts/bootstrap.py",
        cwd=root)

    result = apply(standard, root, "a", "--accept-local",
                   "scripts/bootstrap.py", "--branch", BRANCH)

    assert_said_what_it_committed(result, root, BRANCH, [PIN])


@pytest.fixture(scope="module")
def adopted(doctor_standard, tmp_path_factory) -> dict:
    """The issue's own input: the source
    `tests/test_update_shape_merged_away.py` adopts, with a `.gitignore` and
    a `Makefile` of its own, so the shape's copies of both are pinned under
    `shape/`."""
    return adopt_and_clone(doctor_standard,
                           tmp_path_factory.mktemp("apply-lines-merged"),
                           SOURCE_TREE)


@pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")
def test_a_run_that_only_drops_merged_away_rows_says_it_committed_the_pin(
        doctor_standard, adopted, tmp_path):
    """THE ISSUE'S MEASUREMENT (AT-scaffold N9, #458's 6172776355): both
    `shape/` copies merged into the files they collided with, and `apply
    --branch` at the commit the pin already names drops their rows. The
    manifest is rewritten with the bytes it had; the line said
    `contracts/shape-pin.yaml, project.yaml`."""
    root = tmp_path / "Medx"
    shutil.copytree(adopted["clone"], root, symlinks=True)
    merge_away(root, *MERGED.values())
    branch = "shape/update-merged-away"

    result = run_script(UPDATE, "apply", "--root", str(root), "--upstream",
                        str(doctor_standard), "--at",
                        head_of(doctor_standard), "--yes", "--branch",
                        branch)

    for path in MERGED:
        assert f"  dropped  {path} " in result.stdout, result.stdout
    assert_said_what_it_committed(result, root, branch, [PIN])


# ---------------------------------------------------------------------------
# A branch that shares its name with a tag
# ---------------------------------------------------------------------------


def own_remote(root: Path, tmp_path: Path) -> Path:
    """`root` pushing to an EMPTY bare remote of this test's own: the bare
    remote."""
    remote = tmp_path / "own-remote.git"
    git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    git("remote", "set-url", "origin", str(remote), cwd=root)
    return remote


def tagged(root: Path, tmp_path: Path) -> Path:
    """`root` with a tag `v1.0.0` at HEAD, pushing to `own_remote`: the bare
    remote."""
    git("tag", TAGGED, cwd=root)
    return own_remote(root, tmp_path)


def on_the_remote(remote: Path) -> str | None:
    """What `remote` holds at the BRANCH `v1.0.0`, or None."""
    proc = git("rev-parse", "--verify", "--quiet", f"refs/heads/{TAGGED}",
               cwd=remote, check=False)
    return proc.stdout.strip() or None


def push_half(line: str) -> list[str]:
    """The `git ... push` a NEXT line opens with, as the argv `sh` reads."""
    words = shlex.split(line.removeprefix("NEXT  "))
    return words[:words.index("&&")]


def test_a_branch_named_like_a_tag_is_pushed_beside_it(standard, root,
                                                       tmp_path):
    """THE ISSUE'S RUN: `--branch v1.0.0 --push` in a root tagged `v1.0.0`.
    It refused `pushing v1.0.0`, exit 2, after the commit. The branch is
    pushed now, the tag stays out of it, and `-u` still sets the
    upstream."""
    remote = tagged(root, tmp_path)

    result = apply(standard, root, "b", "--branch", TAGGED, "--push")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"pushed {TAGGED} to origin" in result.stdout
    assert on_the_remote(remote) == head_of(root)
    assert git("for-each-ref", "refs/tags", cwd=remote).stdout == ""
    assert git("config", f"branch.{TAGGED}.merge",
               cwd=root).stdout.strip() == f"refs/heads/{TAGGED}"


def test_the_branch_next_line_pushes_a_branch_named_like_a_tag(standard, root,
                                                               tmp_path):
    """`--branch` alone ends on the push and the pull request. The push
    named the branch bare, and pasted it failed as the run's own did. It
    names it in full, and run as printed it pushes."""
    remote = tagged(root, tmp_path)

    result = apply(standard, root, "b", "--branch", TAGGED)

    assert result.returncode == 0, result.stdout + result.stderr
    push = push_half(next_line_of(result.stdout))
    assert push == ["git", "-C", str(root), "push", "-u", "origin", FULL]
    pasted = subprocess.run(push, capture_output=True, text=True, check=False)
    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    assert on_the_remote(remote) == head_of(root)


def test_a_failed_push_of_a_branch_named_like_a_tag_prints_one_that_works(
        standard, root, tmp_path):
    """`landing_failed`'s NEXT line, the other printed push: after a push
    origin refused, it pushes before it opens the pull request. Named in
    full there too, it pushes once origin will take it."""
    remote = tagged(root, tmp_path)
    git("remote", "set-url", "--push", "origin",
        str(tmp_path / "no-such-remote.git"), cwd=root)

    result = apply(standard, root, "b", "--branch", TAGGED, "--push")

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED pushing {TAGGED}" in result.stderr
    assert f"git push -q -u -- origin {FULL}" in result.stderr
    push = push_half(next_line_of(result.stdout))
    assert push == ["git", "-C", str(root), "push", "-u", "--", "origin",
                    FULL]
    git("remote", "set-url", "--push", "origin", str(remote), cwd=root)
    pasted = subprocess.run(push, capture_output=True, text=True, check=False)
    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    assert on_the_remote(remote) == head_of(root)


def test_apply_on_a_branch_named_like_a_tag_commits_onto_it(standard, root,
                                                            tmp_path):
    """`--branch` naming THE CURRENT BRANCH commits onto it: the hand-merge
    posture AGENTS.md describes. On `v1.0.0` beside a tag `v1.0.0` it was
    refused `update-branch-exists`, "('heads/v1.0.0' is checked out)",
    because `--short` spelled the branch so."""
    tagged(root, tmp_path)
    git("switch", "-q", "-c", TAGGED, cwd=root)
    before = head_of(root)

    result = apply(standard, root, "b", "--branch", TAGGED)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-branch-exists" not in result.stderr
    assert git("symbolic-ref", "HEAD",
               cwd=root).stdout.strip() == f"refs/heads/{TAGGED}"
    assert git("rev-parse", "HEAD~1", cwd=root).stdout.strip() == before


def test_current_branch_is_the_branch_git_has_checked_out(update_shape, root,
                                                         tmp_path):
    """In process: the branch beside a tag of its name, a branch whose name
    merely looks like a full refname (`refs/heads/x`, which git nests), and
    a detached HEAD, which is on no branch."""
    tagged(root, tmp_path)
    git("switch", "-q", "-c", TAGGED, cwd=root)
    assert update_shape.current_branch(root) == TAGGED
    git("switch", "-q", "-c", "refs/heads/x", cwd=root)
    assert update_shape.current_branch(root) == "refs/heads/x"
    git("switch", "-q", "--detach", cwd=root)
    assert update_shape.current_branch(root) is None


def test_a_pr_rerun_on_a_branch_named_like_a_tag_opens_the_missing_one(
        standard, root, tmp_path, gh):
    """#204's re-run, on `v1.0.0` beside its tag: the first run commits and
    pushes, and its `gh pr create` fails; the same command again finds
    nothing to write and opens that pull request. `_awaits_its_pull_request`
    compared `--short`'s `heads/v1.0.0` with the branch, so the re-run said
    "nothing to do" and opened nothing."""
    remote = tagged(root, tmp_path)
    flags = ("--branch", TAGGED, "--push", "--pr")
    gh.failing(True)
    first = apply(standard, root, "b", *flags, env=gh.env)
    assert first.returncode == 2, first.stdout + first.stderr
    assert f"REFUSED opening the pull request for {TAGGED}" in first.stderr
    create = gh.calls()[0]
    assert on_the_remote(remote) == head_of(root)

    gh.failing(False)
    gh.forget()
    second = apply(standard, root, "b", *flags, env=gh.env)

    assert second.returncode == 0, second.stdout + second.stderr
    assert "nothing to do" not in second.stdout
    assert f"pull request {URL}" in second.stdout
    assert gh.calls() == [listing(TAGGED), create]


# ---------------------------------------------------------------------------
# The branch HEAD is on, read as git wrote it (#765)
# ---------------------------------------------------------------------------


def test_a_branch_ending_in_a_no_break_space_is_not_taken_for_its_neighbour(
        standard, root, tmp_path):
    """`feat<U+00A0>` checked out beside `feat`, and `--branch feat --push`:
    `strip()` read HEAD as `feat`, so the run took `feat` for the branch
    checked out, committed onto `feat<U+00A0>` and pushed `feat`, which
    holds no re-pin. Read as git wrote it, `feat` is a branch that exists
    and is not checked out: refused `update-branch-exists`, naming the
    branch HEAD is on, with both where they were and nothing pushed."""
    remote = own_remote(root, tmp_path)
    name = "feat" + chr(0xA0)
    git("branch", "feat", cwd=root)
    git("switch", "-q", "-c", name, cwd=root)
    before = held_by_git(root)

    result = apply(standard, root, "b", "--branch", "feat", "--push")

    assert result.returncode == 2, result.stdout + result.stderr
    assert ("REFUSED update-branch-exists: --branch feat already exists and "
            f"is not the current branch ({name!r} is checked out)"
            in result.stderr), result.stderr
    assert held_by_git(root) == before
    assert git("for-each-ref", cwd=remote).stdout == ""


def test_a_branch_named_with_a_byte_that_is_not_utf8_is_refused_first(
        standard, root, tmp_path):
    """HEAD on `caf<0xE9>` (#765): `errors="replace"` read it as
    `caf<U+FFFD>`, a branch nobody has, which the lines that name the branch
    HEAD is on then named. Refused by name now, by its bytes, before the
    first write, so there is nothing to roll back, with how to rename it,
    the root and its refs as they were, and nothing pushed."""
    remote = own_remote(root, tmp_path)
    before = on_a_branch_that_is_not_utf_8(root)

    result = apply(standard, root, "b", "--branch", BRANCH, "--push")

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"REFUSED update-branch-not-utf8: {root} is on the branch "
            f"{NOT_UTF_8_BRANCH_NAMED}, whose name is not UTF-8"
            in result.stderr), result.stderr
    assert result.stderr.rstrip().endswith(" branch -m <a new name>"), (
        result.stderr)
    assert "ROLLED BACK" not in result.stderr, "refused before any write"
    assert held_by_git(root) == before
    assert git("for-each-ref", cwd=remote).stdout == ""


@WINDOWS_SKIP
@pytest.mark.parametrize("env", [{}, {"LC_ALL": "C", "PYTHONUTF8": "0"}],
                         ids=["locale", "c-locale"])
def test_a_rollback_puts_head_back_on_the_branch_it_started_on(
        standard, root, env):
    """A run from `feat<U+00A0>`, beside `feat`, whose commit a `pre-commit`
    hook refuses (#765, r765's findings 2 and 3). `strip()` read the branch
    HEAD started on as `feat`, so the rollback "switched HEAD back to feat",
    the neighbour. And handed back to git as text, the name raised
    `UnicodeEncodeError` under `LC_ALL=C PYTHONUTF8=0` part way through the
    rollback, leaving the copies written and HEAD on the new branch. HEAD
    goes back on `feat<U+00A0>` now, in both locales, with every byte git
    holds as it was."""
    git("branch", "feat", cwd=root)
    git("switch", "-q", "-c", "feat" + chr(0xA0), cwd=root)
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_bytes(b"#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    before = held_by_git(root)

    result = apply(standard, root, "b", "--branch", BRANCH, env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert held_by_git(root) == before


# ---------------------------------------------------------------------------
# A rollback line for a file a validator deleted under a shut directory
# ---------------------------------------------------------------------------


def red_after_removing(update_shape, monkeypatch, gone: Path,
                       shut: Path) -> None:
    """The project's validators go red, having removed `gone` (a file, or a
    directory with what is in it) and left `shut` at 0555."""
    def red(_root, _script):
        if gone.is_dir():
            shutil.rmtree(gone)
        elif gone.exists():
            gone.unlink()
        shut.chmod(0o555)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", red)


def blob_of(root: Path, data: bytes) -> str:
    """The id `data` has in `root`'s object store."""
    return subprocess.run(["git", "hash-object", "--stdin"], cwd=str(root),
                          input=data, capture_output=True,
                          check=True).stdout.decode("ascii").strip()


def follow(line: str, said: str, opened: Path, root: Path,
           original: bytes) -> None:
    """`line` is exactly `said` and then the command, which fails while
    `opened` is shut — the reason the line names it — and, once `opened` is
    made writable as the line says, puts `original` back at the pin."""
    assert line.startswith(said), line
    command = line[len(said):]
    shut = subprocess.run(["sh", "-c", command], capture_output=True,
                          check=False)
    assert shut.returncode != 0, "the line's command ran with it shut"
    opened.chmod(0o755)
    subprocess.run(["sh", "-c", command], check=True, capture_output=True)
    assert (root / PIN).read_bytes() == original


@WINDOWS_SKIP
def test_a_pin_deleted_under_a_shut_directory_is_told_to_open_it_first(
        update_shape, root, standard, monkeypatch):
    """THE ISSUE'S CASE (R560v's probe d7): the pin deleted, `contracts/`
    left at 0555. A checkout would unlink and create, so the line is the
    `cat-file` redirect, and a redirect creates the file in a directory that
    will not take it: the line now says to make `contracts/` writable first,
    by the path it has, and never "make it writable" of a file that is not
    there. Followed, it puts the pin's bytes back."""
    contracts = root / "contracts"
    original = held(root)[PIN]
    red_after_removing(update_shape, monkeypatch, root / PIN, contracts)
    try:
        refusal = refused_by(update_shape, standard, root, "b")
        if f"restored  {PIN}" in refusal.detail:  # pragma: no cover
            pytest.skip("this user is not stopped by permission bits")
        assert_reported_as_red(refusal)
        assert put_back(refusal.detail) == [
            f"restored  {path}" for path in (CHANGED, AGENTS, MANIFEST)]
        (line,) = left(refusal.detail)
        kept = blob_of(root, original)
        follow(line, f"file      {PIN} was not put back ({DENIED}); its bytes "
                     f"before this run are kept as blob {kept[:12]} in this "
                     f"repository, so make {contracts} writable, then: ",
               contracts, root, original)
        assert "make it writable" not in line
    finally:
        contracts.chmod(0o755)


@WINDOWS_SKIP
def test_a_directory_deleted_under_a_shut_root_names_the_root(
        update_shape, root, standard, monkeypatch):
    """THE DIRECTORY NAMED IS THE NEAREST ONE THAT EXISTS: a validator that
    deleted `contracts/` and left the ROOT at 0555 gets the `mkdir -p` the
    redirect needs, and the line says to make the root writable, which is
    where `mkdir` writes, not `contracts/`, which is not there."""
    contracts = root / "contracts"
    original = held(root)[PIN]
    red_after_removing(update_shape, monkeypatch, contracts, root)
    try:
        refusal = refused_by(update_shape, standard, root, "b")
        if f"restored  {PIN}" in refusal.detail:  # pragma: no cover
            pytest.skip("this user is not stopped by permission bits")
        assert_reported_as_red(refusal)
        (line,) = left(refusal.detail)
        kept = blob_of(root, original)
        said = (f"file      {PIN} was not put back "
                f"({os.strerror(errno.ENOENT)}); its bytes before this run "
                f"are kept as blob {kept[:12]} in this repository, so make "
                f"{root} writable, then: ")
        assert line[len(said):].startswith(
            f"mkdir -p {shlex.quote(str(contracts))} && "), line
        follow(line, said, root, root, original)
    finally:
        root.chmod(0o755)
