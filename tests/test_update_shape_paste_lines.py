# SPDX-License-Identifier: Apache-2.0
"""The paste lines `update-shape.py` printed with a root or a path bare keep a
space, a quote or a `$` in it whole (#532).

#325 quoted the NEXT lines a run prints before anything has gone wrong, and
#202 and #204 the rollback's hand fixes. Six places still concatenated a root
or a path in, each handing a person a line that ran in the wrong directory,
did not parse, or expanded:

  * `check`'s ADDED UPSTREAM list, `--add <path>` for each path;
  * `apply`'s `update-branch-exists` remedy, `git -C <root> checkout
    <branch>`;
  * `apply`'s `update-local-drift` remedy, `--accept-local <path>` for each;
  * `apply`'s note for an `upstream-added` path it was not told to take, `pass
    --add <path>`;
  * the two sentences `check` appends to a `both` and a `locally-modified`
    row, each naming `apply --accept-local <path>` (display only: the NEXT
    line leaves the flag out, but a person types it).

Measured on 45e01f4, an added path `notes/shape notes.md` pasted as printed
was refused `unrecognized arguments: notes.md`.

THE CLAIM IS MADE THE WAY A SHELL WOULD CHECK IT. Each printed word is read
back by `shlex.split`, the word-splitting a POSIX shell performs, and must
come back as the argv it was printed to mean, for a name with a space, an
apostrophe and a `$`; then, wherever the host has `sh`, it is PASTED into one
and what it does is read from the tool or from git. The `--add` and the
`checkout` are run as printed, and the paths a standard could not hold (an
apostrophe and a `$` are outside the alphabet it accepts for a copied file) are
read by a real `sh` through `printf`.

WHAT IS NOT CLAIMED. These lines are for a POSIX shell (Git Bash, or WSL2, on
Windows), as `_by_hand` says of its own and README's "Windows, natively" says
of all of them: a Windows root holds a backslash, which `shlex` quotes, so
every exact-string expectation is built with `shlex` too, and the pastes into
`sh` are POSIX-only.

NO NETWORK: the upstream is a clone of this repository on disk, passed with
`--upstream <path>`, and the project is a private copy of one scaffolded from
it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
#: The one reading of a printed line, and the one `sh` a line is pasted into,
#: and the three directory names a root is put under: the bump tests' (#532).
from test_bump_leg_paste_lines import ROOTS, paste, words
from test_update_shape import PROJECT, scaffold_upstream_and_project
from test_update_shape_add import MATERIALIZER, commit_all, name_in_list

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, load_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"

#: A Windows root holds a backslash, which `shlex` quotes, and a Windows host
#: has no `sh` to paste into.
ON_WINDOWS = os.name == "nt"

#: A file the standard gains after the project was cut, whose name holds a
#: space: the one an ADDED UPSTREAM line has to carry whole. A name with an
#: apostrophe or a `$` is not a name the standard may have (`SAFE_PATH_RE`),
#: so those two are read in-process, below.
ADDED = "AGENTS shape added.md"
ADDED_BYTES = b"# A file the standard gained, named with a space.\n"

#: Each way a PATH breaks a line pasted bare: a space, an apostrophe, a `$`.
PATHS = [
    pytest.param("notes/sp ace.md", id="space"),
    pytest.param("notes/it's.md", id="apostrophe"),
    pytest.param("notes/d$x.md", id="dollar"),
]


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone of this repository at A, a project scaffolded from it, and B:
    a commit that adds `ADDED` to the assembly root's copy list."""
    base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-paste-lines")
    (upstream / "templates" / "assembly-root" / ADDED).write_bytes(ADDED_BYTES)
    source = upstream / MATERIALIZER
    source.write_bytes(name_in_list(source.read_bytes().decode("utf-8"),
                                    "COPIED_VERBATIM", ADDED).encode("utf-8"))
    commit_b = commit_all(upstream, "Add a file whose name holds a space",
                          [MATERIALIZER, f"templates/assembly-root/{ADDED}"])
    assert commit_a != commit_b
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b}


@pytest.fixture
def make_root(standard, tmp_path):
    """`make_root(name)`: a private copy of the project at `<tmp>/<name>/Atlas`.

    A COPY rather than a scaffold into such a directory: the point under test
    is what the tool PRINTS about a root, and a submodule's `.git` is a file
    holding a RELATIVE path into `../.git/modules/<name>`, which keeps the
    copy honest as well as cheap."""
    def make(name: str) -> Path:
        target = tmp_path / name / PROJECT
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(standard["clone"], target, symlinks=True)
        return target

    return make


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so a line is built in this process."""
    spec = importlib.util.spec_from_file_location("update_shape_paste_lines",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(standard, root, *extra):
    return run_script(UPDATE, "check", "--root", str(root), "--upstream",
                      str(standard["upstream"]), "--at", standard["b"],
                      *extra)


def apply(standard, root, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]), "--at",
                      standard["b"], *extra)


def sh_reads(fragment: str, cwd: Path) -> list[str]:
    """The words a real `sh` makes of `fragment`: `printf` prints each
    argument on a line of its own."""
    pasted = paste("printf '%s\\n' " + fragment, cwd)
    assert pasted.returncode == 0, pasted.stderr
    return pasted.stdout.splitlines()


def apply_line(standard, root: Path, tail: str) -> str:
    """An `apply` a person could paste, every word quoted, ending in `tail`."""
    head = [sys.executable, str(UPDATE), "apply", "--root", str(root),
            "--yes", "--upstream", str(standard["upstream"]), "--at",
            standard["b"]]
    return f"{shlex.join(head)} {tail}"


def pin_paths(root: Path) -> list[str]:
    return [row["path"] for row in
            load_yaml(root / "contracts" / "shape-pin.yaml")["files"]]


# --- check: the ADDED UPSTREAM list ------------------------------------------


def added_tail(stdout: str) -> str:
    """The `--add <path>` words `check` ends its ADDED UPSTREAM sentence on."""
    found = re.search(r"one path at a time — (.*)$", stdout, re.M)
    assert found, stdout
    return found.group(1)


@pytest.mark.parametrize("name", ROOTS)
def test_check_offers_an_added_path_as_one_argument(standard, make_root, name):
    """`--add AGENTS shape added.md` pasted bare is `--add AGENTS` and two
    words `apply` refuses; quoted, it is the one path."""
    root = make_root(name)
    result = check(standard, root)
    assert result.returncode == 1, result.stdout + result.stderr
    tail = added_tail(result.stdout)
    assert words(tail) == ["--add", ADDED]
    assert tail == f"--add {shlex.quote(ADDED)}"


@WINDOWS_SKIP
def test_pasting_the_added_upstream_words_into_apply_takes_the_file(
        standard, make_root, tmp_path):
    """THE WORDS, RUN: an `apply` whose last words are the ones `check`
    printed takes the one file the standard gained, at the path it has."""
    root = make_root("it's")
    tail = added_tail(check(standard, root).stdout)
    assert ADDED not in pin_paths(root)

    pasted = paste(apply_line(standard, root, tail), tmp_path)
    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    assert (root / ADDED).read_bytes() == ADDED_BYTES
    assert ADDED in pin_paths(root)


# --- apply: the note for a path it was not told to take ----------------------


@pytest.mark.parametrize("name", ROOTS)
def test_apply_without_add_names_the_path_to_pass_as_one_argument(
        standard, make_root, name):
    root = make_root(name)
    result = apply(standard, root)
    assert result.returncode == 0, result.stdout + result.stderr
    noted = [line for line in result.stdout.splitlines()
             if line.startswith("  note     ") and ADDED in line]
    assert len(noted) == 1, result.stdout
    took = noted[0].split("; not added; ")[1]
    assert took == f"pass --add {shlex.quote(ADDED)}"
    assert words(took) == ["pass", "--add", ADDED]
    assert not (root / ADDED).exists(), "no --add was passed"


# --- apply: the update-branch-exists remedy ----------------------------------


def checkout_remedy(stderr: str) -> str:
    """The command between the backticks of `update-branch-exists`'s
    remediation."""
    found = re.search(r"check out that branch first — `(.*)` — if that is",
                      stderr)
    assert found, stderr
    return found.group(1)


@pytest.mark.parametrize("name", ROOTS)
def test_the_branch_exists_remedy_is_one_command(standard, make_root, name):
    """`git -C <root> checkout <branch>` bare was `git -C .../sp` and an
    argument nobody wrote under `sp ace/` (exit 128), a quotation nothing
    closes under `it's/`."""
    root = make_root(name)
    git("branch", "shape/someone-elses", cwd=root)

    result = apply(standard, root, "--branch", "shape/someone-elses")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-branch-exists" in result.stderr, result.stderr
    line = checkout_remedy(result.stderr)
    argv = ["git", "-C", str(root.resolve()), "checkout",
            "shape/someone-elses"]
    assert words(line) == argv
    assert line == shlex.join(argv)


@WINDOWS_SKIP
@pytest.mark.parametrize("name", ROOTS)
def test_pasting_the_branch_exists_remedy_checks_the_branch_out(
        standard, make_root, tmp_path, name):
    """THE LINE, RUN: pasted into `sh` it checks the existing branch out in
    THAT root, which is what the remedy says the hand merge needs first."""
    root = make_root(name)
    git("branch", "shape/someone-elses", cwd=root)
    refused = apply(standard, root, "--branch", "shape/someone-elses")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == "main"

    pasted = paste(checkout_remedy(refused.stderr), tmp_path)
    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == "shape/someone-elses"


@pytest.mark.skipif(ON_WINDOWS, reason="a Windows root holds a backslash, "
                    "which `shlex` quotes")
def test_an_ordinary_root_prints_the_remedy_it_always_did(standard, make_root):
    """Nothing is quoted that needs no quoting."""
    root = make_root("plain")
    git("branch", "shape/someone-elses", cwd=root)
    result = apply(standard, root, "--branch", "shape/someone-elses")
    assert checkout_remedy(result.stderr) == (
        f"git -C {root.resolve()} checkout shape/someone-elses")


# --- the paths in the drift refusal and the two sentences `check` appends ----
#
# A path a pin can carry is one the standard's copy lists name, so none holds
# an apostrophe or a `$` in real use; these are read in-process, with the
# printing functions handed the rows directly, so the quoting is held to every
# path a shell reads differently, and a real `sh` reads the quoted words back.


def local_edit(update_shape, path: str):
    """A row for `path` as `classify` leaves a file the project edited."""
    row = update_shape.Row(path, "a" * 64)
    row.state = update_shape.LOCALLY_MODIFIED
    return row


def addition(update_shape, path: str):
    """An `upstream-added` path the root has nothing at."""
    copy = update_shape.Copy(path, f"templates/assembly-root/{path}", False)
    return update_shape.Addition(copy, False, b"added\n")


@pytest.mark.parametrize("path", PATHS)
def test_the_drift_refusal_names_each_path_as_one_argument(update_shape, path,
                                                           tmp_path):
    other = "docs/other file.md"
    rows = [local_edit(update_shape, path), local_edit(update_shape, other)]
    with pytest.raises(Refusal) as raised:
        update_shape._refuse_local_drift(rows, set())
    said = raised.value
    assert said.code == "update-local-drift"
    tail = said.remediation.split("re-run with ")[1]
    assert words(tail) == ["--accept-local", path, "--accept-local", other]
    # The unquoted paths are still listed, one a line, for the person to read.
    assert f"    {path}\n" in said.detail + "\n"
    if ON_WINDOWS:
        return
    assert sh_reads(tail, tmp_path) == ["--accept-local", path,
                                        "--accept-local", other]


def test_an_accepted_path_is_not_in_the_refusal(update_shape):
    """Control: the paths the refusal asks about are the unaccepted ones."""
    rows = [local_edit(update_shape, "a b.md"),
            local_edit(update_shape, "c d.md")]
    with pytest.raises(Refusal) as raised:
        update_shape._refuse_local_drift(rows, {"a b.md"})
    assert words(raised.value.remediation.split("re-run with ")[1]) == [
        "--accept-local", "c d.md"]


def backticked(sentence: str) -> str:
    """The command the one pair of backticks in `sentence` holds."""
    found = re.findall(r"`([^`]*)`", sentence)
    assert len(found) == 1, sentence
    return found[0]


@pytest.mark.parametrize("path", PATHS)
def test_the_both_sentence_names_the_path_as_one_argument(update_shape, path,
                                                          tmp_path):
    sentence = update_shape.accept_local_exit(path)
    command = backticked(sentence)
    assert words(command) == ["apply", "--accept-local", path]
    assert command == f"apply --accept-local {shlex.quote(path)}"
    if not ON_WINDOWS:
        assert sh_reads(command, tmp_path) == ["apply", "--accept-local",
                                               path]


@pytest.mark.parametrize("path", PATHS)
def test_the_locally_modified_sentence_names_the_path_as_one_argument(
        update_shape, path, tmp_path):
    sentence = update_shape.keep_local_exits(path)
    command = backticked(sentence)
    assert words(command) == ["apply", "--accept-local", path]
    assert command == f"apply --accept-local {shlex.quote(path)}"
    if not ON_WINDOWS:
        assert sh_reads(command, tmp_path) == ["apply", "--accept-local",
                                               path]


@pytest.mark.parametrize("path", PATHS)
def test_the_untaken_addition_note_names_the_path_as_one_argument(
        update_shape, path, tmp_path, capsys):
    update_shape._note_untaken_additions([addition(update_shape, path)], [])
    printed = capsys.readouterr().out.splitlines()
    assert len(printed) == 1, printed
    said = printed[0]
    assert said.startswith(f"  note     {path} is new upstream; not added; ")
    took = said.split("; not added; ")[1]
    assert words(took) == ["pass", "--add", path]
    assert took == f"pass --add {shlex.quote(path)}"
    if not ON_WINDOWS:
        assert sh_reads(took, tmp_path) == ["pass", "--add", path]


def test_a_path_that_needs_no_quoting_prints_as_it_always_did(update_shape,
                                                              capsys):
    """Nothing is quoted that needs no quoting, so every existing line a
    plain path prints is byte for byte what it was."""
    path = "scripts/new-check.py"
    assert update_shape.accept_local_exit(path).endswith(
        "`apply --accept-local scripts/new-check.py` so the row is "
        "recomputed from what you merged")
    assert update_shape.keep_local_exits(path).endswith(
        "on their word, `apply --accept-local scripts/new-check.py`")
    update_shape._note_untaken_additions([addition(update_shape, path)], [])
    assert capsys.readouterr().out == (
        "  note     scripts/new-check.py is new upstream; not added; "
        "pass --add scripts/new-check.py\n")
    rows = [local_edit(update_shape, path)]
    with pytest.raises(Refusal) as raised:
        update_shape._refuse_local_drift(rows, set())
    assert raised.value.remediation.endswith(
        "re-run with --accept-local scripts/new-check.py")
