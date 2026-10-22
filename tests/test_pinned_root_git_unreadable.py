# SPDX-License-Identifier: Apache-2.0
"""The four other pinned callers of `find_repo_root`, and the doctor's
`members` row: a root whose OWN `.git` this user cannot read is refused by
name, and a family holder's is never a member off its pin (#1148).

#1146 made the assembly root's `validate-pins.py` and `validate-manifest.py`
refuse such a root, `git-repo-unreadable`, exit 2, and the doctor's `legs`
row name it once (`tests/test_root_git_unreadable.py`). These are the rest.

THE DEFECT, measured on #1147's head `b75babee` in a scaffold's recursive
clone and a family holder, on Python 3.12.3 and under a `sitecustomize` that
answers as Python 3.14's `Path.is_file()`, `is_dir()`, `exists()` and
`is_symlink()` do, False to ANY `OSError`:

  * a `.git` that is a link into a folder at mode 000: the assembly root's
    `scripts/bootstrap.py`, and the holder's `validate-family.py`,
    `bootstrap.py` and `siblings.py`, each ended in a `PermissionError`
    traceback out of `repo_shape`'s `find_repo_root`, exit 1, on 3.12, and
    under the shim refused `not-a-git-repo: no .git found at or above
    <root>`, exit 2, about a root that has one;
  * a `.git` directory at mode 000, which `find_repo_root` passes: the
    assembly root's bootstrap said `no gitlink recorded; leaving as is` of
    every leg before its pins validator refused; `validate-family.py`
    refused `gitlinks-unreadable` over git's `not a git repository`, with
    the remedy to ask `git status`; the holder's bootstrap said `FETCH
    INCOMPLETE` with the advice to set a credential, and failed each member
    on its own pins, exit 1, or with `--no-fetch --skip-members` said
    `family bootstrap ok`; `siblings.py` placed every member, rightly;
  * the doctor over the holder: the `members` row said `checked out at ?`
    of each member, and the verdict was `DRIFTED (a member is not at its
    pin)`, on both Pythons for the directory and under the shim for the
    link; on 3.12 the link raised out of the row.

THE RULE NOW is #430's, as #1146 applies it. Each tool asks every `.git`
`find_repo_root` would ask, in its order, with its OWN `_is_a`, and stops at
the first that is there: one this user cannot `stat` is refused
`git-repo-unreadable`, exit 2, in that tool's own words, with the advice for
the cause. The three that read the root's repository through git (both
bootstraps and `validate-family.py`) also ask what `validate-pins.py` asks:
a gitfile they cannot open, a git directory whose `HEAD` they cannot reach.
`siblings.py` asks the `stat` alone, as `validate-manifest.py` does: it
places the members from the holder's files, and a `.git` directory at 000
leaves it working. The doctor's `members` row says the gate's line ONCE,
with this doctor again as its NEXT, and no member is drift.

TWO KINDS OF CASE, as `tests/test_root_git_unreadable.py` has them: the MODE
cases change a real mode and run each tool as a person does, and skip on
Windows and as root (`CANNOT_RUN_AS_ROOT`); the STAND-IN cases refuse the
`stat` or the read in process, so they run everywhere.

NOTHING HERE REACHES A NETWORK: the doctor's own fixtures, a scaffold and a
holder into local bare remotes, and the session's `gh` guard.
"""

from __future__ import annotations

import errno
import os
import shutil
import sys
from pathlib import Path

import pytest

from conftest import REPO, load_without_bytecode, run_script
#: #827's stand-in for a `stat` the operating system refuses (#383).
from test_bump_leg_unopenable import refusal_of, refused_stat
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: #847's helpers and the gate's advice, word for word.
from test_doctor_unreadable_pin import (
    DENIED, IO_ERROR, OTHER_WHY, PERMISSION_WHY, cannot, doctored, in_process,
    refusing,
)
#: #1146's arrangements of a root's `.git`, from the file that owns them.
from test_root_git_unreadable import (
    ABSENT, CODE, POSIX_NAMES, UNPRINTABLE, as_python_314, gitfile_into,
    linked_into, moved_in, moved_out,
)
#: The doctor's fixtures, from the module that owns them: a project and a
#: holder, each built from one committed copy of this working tree.
from test_shape_doctor import (  # noqa: F401
    FAMILY_MEMBER, FAMILY_NAME, holder, project, scaffolded_here, standard,
)
#: The gate's own advice, word for word, from the file that owns it.
from test_validate_pins_named_and_spelled import AGAIN, OTHER, PERMISSION
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it.
from test_validate_pins_unreadable_workflows_dir import mode_of

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import spelled  # noqa: E402

ASSEMBLY = REPO / "templates" / "assembly-root" / "scripts"
FAMILY = REPO / "templates" / "family-root" / "scripts"

#: Each tool: the file in a root's `scripts/`, and whether it is the
#: assembly root's (`project`) or the holder's (`family_root`).
FILES = {
    "assembly-bootstrap": ("bootstrap.py", "project"),
    "validate-family": ("validate-family.py", "family"),
    "family-bootstrap": ("bootstrap.py", "family"),
    "siblings": ("siblings.py", "family"),
}
#: What each tool's remedy says before the advice for the cause.
BEFORE = {
    "assembly-bootstrap": (
        "Remediation: this command reads the root's own repository, where it "
        "finds the root, each leg's gitlink and each leg's own repository, "
        "and one it cannot read is not one that records no gitlink, which "
        "would place no leg. "),
    "validate-family": (
        "Remediation: this validator reads the holder's own repository, "
        "where it finds the holder and each gitlink, `.gitmodules` and HEAD "
        "it records, and one it cannot read is a question it cannot answer, "
        "never a pass. "),
    "family-bootstrap": (
        "Remediation: The holder's own repository is where this command "
        "finds the holder, and where git finds each member it fetches and "
        "each member's own repository, and it could not be read, so nothing "
        "was fetched or run. A path this command cannot read is a question "
        "it cannot answer, never a pass. "),
    "siblings": (
        "Remediation: The holder's `.git` is how this command finds the "
        "holder, and it could not be asked, so nothing was cloned, fetched "
        "or run. A path this command cannot read is a question it cannot "
        "answer, never a pass. "),
}
TOOLS = pytest.mark.parametrize("tool", sorted(FILES))
#: The three that read the root's repository through git, and so ask what
#: `.git` is or names, as `validate-pins.py` does.
GIT_READERS = sorted(set(FILES) - {"siblings"})
#: `siblings.py`'s advice for a permission, whose clones sit outside the
#: holder (#430): the gate's, less "inside the root".
SIBLINGS_PERMISSION = PERMISSION.replace(" inside the root", "")


def advice(tool: str, cause: str) -> str:
    """The tool's advice for `cause`, `permission` or `other`."""
    if cause == "other":
        return OTHER
    return SIBLINGS_PERMISSION if tool == "siblings" else PERMISSION


def refused(tool: str, line: str, cause: str = "permission") -> str:
    """The whole of a tool's stderr for a `.git` it cannot read."""
    return f"REFUSED {CODE}: {line}\n{BEFORE[tool]}{advice(tool, cause)}{AGAIN}\n"


def members_said(line: str) -> str:
    """The `members` row's reason for a holder whose `.git` cannot be read."""
    return (f"{line}, so no gitlink is read and no member is compared with "
            "its pin")


def member_entry(line: str) -> dict:
    """The holder's one member, as the `members` row keeps it then: every
    key a member's entry has, each null that the row did not ask."""
    return {"project": FAMILY_MEMBER, "path": f"members/{FAMILY_MEMBER}",
            "pin": None, "populated": None, "head": None, "own_git": None,
            "unborn": None, "detached": None, "mounted_from": None,
            "sibling": None, "working_clone": None, "other_origin": None,
            "gitlink_cannot_be_read": line}


@pytest.fixture
def family_root(holder, tmp_path) -> Path:
    """A private copy of the doctor's holder, in a folder named after it,
    the layout `make siblings` asks for."""
    root = tmp_path / FAMILY_NAME / FAMILY_NAME
    root.parent.mkdir()
    shutil.copytree(holder["root"], root, symlinks=True)
    return root


@pytest.fixture
def roots(project, family_root) -> dict:
    """`{tool: the root it runs in}`."""
    return {tool: project if kind == "project" else family_root
            for tool, (_, kind) in FILES.items()}


@pytest.fixture(scope="module")
def tools():
    """The four templates, loaded by path, `sys.path` and `sys.modules` put
    back after: `siblings.py` imports the holder's `bootstrap` beside it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "path", list(sys.path))
        family_bootstrap = load_without_bytecode(
            FAMILY / "bootstrap.py", "pinned_root_git_family_bootstrap")
        patch.setitem(sys.modules, "bootstrap", family_bootstrap)
        return {
            "assembly-bootstrap": load_without_bytecode(
                ASSEMBLY / "bootstrap.py", "pinned_root_git_bootstrap"),
            "validate-family": load_without_bytecode(
                FAMILY / "validate-family.py", "pinned_root_git_family_gate"),
            "family-bootstrap": family_bootstrap,
            "siblings": load_without_bytecode(
                FAMILY / "siblings.py", "pinned_root_git_siblings"),
        }


def run_tool(tool: str, root: Path, *args: str):
    """The root's own copy of `tool`, run from the root as a person runs
    it."""
    return run_script(root / "scripts" / FILES[tool][0], *args, cwd=root)


# --- the mode cases: a real mode, each tool run as a person runs it ----------

@CANNOT_RUN_AS_ROOT
@TOOLS
def test_each_tool_refuses_a_root_git_linked_into_a_locked_folder(roots,
                                                                  tool):
    """The issue's case. Run from the root with no argument, as `make
    bootstrap`, `make validate` and `make siblings` run each: the base ended
    in a `PermissionError` traceback, exit 1. One refusal now, exit 2,
    naming `.git` with the cure, and nothing printed before it."""
    root = roots[tool]
    linked_into(root)
    with mode_of(root.parent, "locked", 0):
        result = run_tool(tool, root)
    assert result.stderr == refused(
        tool, cannot(".git", os.strerror(errno.EACCES))), result.stderr
    assert result.returncode == 2
    assert result.stdout == ""


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("tool", GIT_READERS)
@pytest.mark.parametrize("bits", [pytest.param(0, id="git-000"),
                                  pytest.param(0o444, id="git-r--")])
def test_a_git_reading_tool_refuses_a_root_git_directory_it_cannot_search(
        roots, tool, bits):
    """`.git` itself at 000 or 444: its `stat` works and its `HEAD` cannot
    be reached. The base's assembly bootstrap said `no gitlink recorded` of
    each leg; `validate-family.py` refused `gitlinks-unreadable` over git's
    words; the holder's bootstrap said `FETCH INCOMPLETE` with the advice to
    set a credential. Each refuses `.git` by name now, before anything."""
    root = roots[tool]
    with mode_of(root, ".git", bits):
        result = run_tool(tool, root)
    assert result.stderr == refused(
        tool, cannot(".git", os.strerror(errno.EACCES))), result.stderr
    assert result.returncode == 2
    assert result.stdout == ""


@CANNOT_RUN_AS_ROOT
def test_siblings_still_places_the_members_of_a_holder_whose_git_is_at_000(
        family_root):
    """The control for `siblings.py`'s one question, which the base passed
    too: it reads the holder's files, and `.gitmodules` as a file, so a
    `.git` directory at 000 is no refusal. Each member would be cloned
    beside the holder, and the holder's branch, which git cannot read, is
    `?`."""
    with mode_of(family_root, ".git", 0):
        result = run_tool("siblings", family_root, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert f"[{FAMILY_MEMBER}] would clone " in result.stdout
    holder_row = next(line.split() for line in result.stdout.splitlines()
                      if line.split()[:1] == ["holder"])
    assert holder_row[-1] == "?", holder_row


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("tool", GIT_READERS)
def test_a_gitfile_into_a_locked_folder_is_named_by_its_git_directory(
        roots, tool):
    """A `.git` gitfile naming a git directory in a folder this user cannot
    search: its own `stat` works, so `.git` is not what is named; the git
    directory is, whole, since it is outside the root."""
    root = roots[tool]
    gitdir = gitfile_into(root)
    line = cannot(str(gitdir.resolve()), os.strerror(errno.EACCES))
    with mode_of(root.parent, "locked", 0):
        result = run_tool(tool, root)
    assert result.stderr == refused(tool, line), result.stderr
    assert result.returncode == 2


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("arrange", [
    pytest.param(lambda root: (linked_into(root), "locked"), id="linked"),
    pytest.param(lambda root: (None, ".git"), id="git-000"),
])
def test_the_doctor_names_a_holder_git_it_cannot_read_never_drift(
        standard, family_root, arrange):
    """The doctor over the holder. The base's `members` row said `checked
    out at ?` of the member, and the verdict was DRIFTED; on 3.12 the link
    raised out of the row. The row now says the gate's line once, a FINDING
    for a person to mend, and the `family` row is the holder's own
    `validate-family.py` refusing `.git` by name: INVALID (family)."""
    locked = arrange(family_root)[1]
    folder = family_root.parent if locked == "locked" else family_root
    line = cannot(".git", os.strerror(errno.EACCES))
    with mode_of(folder, locked, 0):
        rows, verdict = doctored(standard, family_root)
    assert verdict == "INVALID (family)"
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert members["reason"] == members_said(line)
    assert members["next"] == doctor_again(standard, family_root)
    assert members["why"] == PERMISSION_WHY
    assert members["detail"]["members"] == [member_entry(line)]
    assert rows["family"]["reason"] == (
        "the project's own scripts/validate-family.py refuses (exit 2): "
        f"REFUSED {CODE}: {line}")
    for row in rows.values():
        assert "checked out at ?" not in row["reason"], row
        assert "crashed" not in row["reason"], row


def test_roots_whose_git_can_be_read_are_unchanged(standard, roots):
    """The control, which the base passed too: the doctor calls the holder
    COMPLIANT, and each tool, run as the root runs it, goes on past the
    question (the holder's bootstrap with nothing to fetch or run)."""
    family_root = roots["validate-family"]
    rows, verdict = doctored(standard, family_root)
    assert verdict == "COMPLIANT"
    assert rows["members"]["status"] == "ok", rows["members"]
    for tool, args in (("assembly-bootstrap", ["--skip-validators"]),
                       ("validate-family", []),
                       ("family-bootstrap", ["--no-fetch", "--skip-members"]),
                       ("siblings", ["--dry-run"])):
        result = run_tool(tool, roots[tool], *args)
        assert result.returncode == 0, (tool, result.stderr)
        assert CODE not in result.stderr


# --- the stand-in cases: in process, on every platform and as root ----------

@TOOLS
@pytest.mark.parametrize("cause", ["permission", "other"])
def test_each_tool_refuses_a_refused_root_git_on_every_python(
        roots, tools, monkeypatch, capsys, tool, cause):
    """Every `.git`'s `stat` refused, as Python 3.14's `exists()` answers it,
    where the base refused `not-a-git-repo` over a root that has a `.git`:
    one refusal by name, the advice for the cause, exit 2, and the run goes
    no further."""
    if cause == "permission":
        refused_stat(monkeypatch, ".git")
        reason = DENIED
    else:
        refusing(monkeypatch, "stat", ".git", OSError(errno.EIO, IO_ERROR))
        reason = IO_ERROR
    assert tools[tool].main(["--root", str(roots[tool])]) == 2
    seen = capsys.readouterr()
    assert seen.err == refused(tool, cannot(".git", reason), cause)
    assert seen.out == ""


@TOOLS
def test_a_root_git_above_the_folder_given_is_asked_and_named_whole(
        roots, tools, monkeypatch, capsys, tool):
    """The walk: `--root` a folder inside the root, which holds no `.git`,
    and the root's own refused. The base's 3.14 walked past it, to
    `not-a-git-repo`. It is named whole, since it is not under the folder
    given."""
    root = roots[tool]
    dotgit = root.resolve() / ".git"
    as_python_314(monkeypatch, {dotgit: PermissionError(errno.EACCES,
                                                        DENIED)})
    assert tools[tool].main(["--root", str(root / "contracts")]) == 2
    assert capsys.readouterr().err == refused(tool,
                                              cannot(str(dotgit), DENIED))


@POSIX_NAMES
@TOOLS
def test_a_root_git_named_whole_is_spelled(tools, tmp_path, monkeypatch,
                                           capsys, tool):
    """The same walk, from a folder inside a root that sits in a folder
    whose name holds an ESC, and the root's own `.git` refused: it is named
    whole, since it is not under the folder given, and the WHOLE path is
    spelled (`spelled`, #391), so the ESC reaches the terminal written as
    its escape, never as the control. The base's 3.14 walked past it, to
    `not-a-git-repo`. Each tool spells it: `siblings.py` by its own call,
    the three that read the root's repository through their helpers."""
    root = tmp_path / UNPRINTABLE / "root"
    (root / ".git").mkdir(parents=True)
    (root / "contracts").mkdir()
    dotgit = root.resolve() / ".git"
    as_python_314(monkeypatch, {dotgit: PermissionError(errno.EACCES,
                                                        DENIED)})
    assert tools[tool].main(["--root", str(root / "contracts")]) == 2
    named = spelled(str(dotgit))
    assert UNPRINTABLE not in named
    assert capsys.readouterr().err == refused(tool, cannot(named, DENIED))


@TOOLS
def test_a_relative_root_is_walked_from_where_it_resolves(
        roots, tools, monkeypatch, capsys, tool):
    """Run from `<root>/contracts` with `--root .`, and the root's `.git`
    refused: the walk starts where `.` resolves, as `find_repo_root`'s
    does, reaches the root's `.git` and names it whole. `Path(".")` has no
    parents, so a walk from it unresolved asks `contracts/.git` alone."""
    root = roots[tool]
    dotgit = root.resolve() / ".git"
    as_python_314(monkeypatch, {dotgit: PermissionError(errno.EACCES,
                                                        DENIED)})
    monkeypatch.chdir(root / "contracts")
    assert tools[tool].main(["--root", "."]) == 2
    assert capsys.readouterr().err == refused(tool,
                                              cannot(str(dotgit), DENIED))


@TOOLS
def test_a_git_above_the_root_is_never_asked(roots, tools, monkeypatch,
                                             tool):
    """`find_repo_root` stops at the first `.git` that is there, and so does
    the question: a `.git` above the root that cannot be read is not this
    root's."""
    root = roots[tool]
    as_python_314(monkeypatch, {
        root.resolve().parent / ".git": PermissionError(errno.EACCES,
                                                        DENIED)})
    assert tools[tool]._refuse_an_unreadable_root(root) is None


@TOOLS
def test_the_walk_stops_at_a_git_that_is_a_gitfile(roots, tools,
                                                   monkeypatch, tool):
    """The root's `.git` a readable gitfile naming a git directory inside
    it, and a `.git` above the root refused: the walk stops at the gitfile,
    the first `.git` that is there whatever it is."""
    root = roots[tool]
    moved_in(root)
    as_python_314(monkeypatch, {
        root.resolve().parent / ".git": PermissionError(errno.EACCES,
                                                        DENIED)})
    assert tools[tool]._refuse_an_unreadable_root(root) is None


@pytest.mark.parametrize("tool", GIT_READERS)
@pytest.mark.parametrize("arrange, name, method, named", [
    pytest.param(lambda root: None, "HEAD", "stat", lambda root: ".git",
                 id="git-directory-head"),
    pytest.param(moved_out, ".git", "read_bytes", lambda root: ".git",
                 id="gitfile-open"),
    pytest.param(moved_out, "HEAD", "stat",
                 lambda root: str(root.resolve().parent / "elsewhere"
                                  / "projgit"),
                 id="gitfile-names-a-directory-outside"),
    pytest.param(moved_in, "HEAD", "stat", lambda root: ".gitdir",
                 id="gitfile-names-a-directory-inside"),
    pytest.param(lambda root: moved_in(root, ending=b"\r\n"), "HEAD", "stat",
                 lambda root: ".gitdir",
                 id="gitfile-ending-in-cr-lf-names-a-directory-inside"),
    pytest.param(lambda root: moved_in(root, UNPRINTABLE), "HEAD", "stat",
                 lambda root: spelled(UNPRINTABLE),
                 id="gitfile-names-an-unprintable-directory",
                 marks=POSIX_NAMES),
])
def test_a_git_reading_tool_names_what_its_root_git_is_or_names(
        roots, tools, monkeypatch, tool, arrange, name, method, named):
    """What `.git` is or names, refused, as `validate-pins.py` asks it
    (#1146): a git directory whose `HEAD` cannot be reached, or a gitfile
    that cannot be opened. Named relative to the root where it is inside
    it and whole where it is not, from a gitfile whose line ends in CR LF
    as from one ending in LF, and spelled where it is not printable."""
    root = roots[tool]
    arrange(root)
    refusing(monkeypatch, method, name, PermissionError(errno.EACCES, DENIED))
    module = tools[tool]
    refusal = refusal_of(module, module._refuse_an_unreadable_root, root)
    assert refusal.code == CODE
    assert refusal.detail == cannot(named(root), DENIED)
    assert f"{refusal.detail}\n{refusal.remediation}\n" == refused(
        tool, refusal.detail)[len(f"REFUSED {CODE}: "):]


@pytest.mark.parametrize("method, name", [
    pytest.param("stat", "HEAD", id="git-directory-head"),
    pytest.param("read_bytes", ".git", id="gitfile-open"),
])
def test_siblings_asks_only_the_stat(family_root, tools, monkeypatch,
                                     method, name):
    """`siblings.py` asks what `exists()` asked and nothing more, as
    `validate-manifest.py` does: what git reads inside the holder's
    repository is `validate-family.py`'s question and `make bootstrap`'s."""
    if method == "read_bytes":
        moved_out(family_root)
    refusing(monkeypatch, method, name, PermissionError(errno.EACCES, DENIED))
    assert tools["siblings"]._refuse_an_unreadable_root(family_root) is None


@pytest.mark.parametrize("arrange", ABSENT)
def test_what_answers_absent_is_left_to_find_repo_root(roots, tools,
                                                       arrange):
    """The controls: a `.git` that answers absent (nothing there, a link
    that leads nowhere or to itself), and one git answers for itself (a
    gitfile naming no directory, a git directory with no `HEAD`), are not a
    `.git` this user cannot read: no tool refuses it, and `find_repo_root`
    answers for it as before."""
    arrange(roots["assembly-bootstrap"])
    arrange(roots["validate-family"])
    for tool, module in tools.items():
        assert module._refuse_an_unreadable_root(roots[tool]) is None, tool


@pytest.mark.parametrize("failure, reason, why", [
    pytest.param(PermissionError(errno.EACCES, DENIED), DENIED,
                 PERMISSION_WHY, id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), IO_ERROR, OTHER_WHY,
                 id="io-error"),
])
def test_the_members_row_names_a_refused_holder_git_once(
        standard, family_root, monkeypatch, failure, reason, why):
    """In process, on every platform and as root: only the holder's own
    `.git` refused, as Python 3.14's `exists()` answers it. The `members`
    row says the gate's line once, with the advice for the cause, and the
    member is not drift."""
    module, ctx = in_process(standard, family_root)
    as_python_314(monkeypatch, {ctx.root / ".git": failure})
    line = cannot(".git", reason)
    row = module.check_members(ctx)
    assert row.status == module.FINDING
    assert row.reason == members_said(line)
    assert row.next_command == doctor_again(standard, family_root)
    assert row.why == why
    assert row.detail == {"members": [member_entry(line)],
                          "without_working_clone": [], "on_a_branch": []}
    assert module.drifted_reasons({"members": row}, {}) == []


def test_a_member_beside_one_whose_gitlink_cannot_be_read_is_still_drift(
        standard, family_root):
    """`drifted_reasons` counts no member that carries
    `gitlink_cannot_be_read`, and still counts one beside it that it could
    read and is off its pin."""
    module = in_process(standard, family_root)[0]
    unread = member_entry(cannot(".git"))
    off = {"project": "IRSS", "path": "members/IRSS", "pin": "2" * 40,
           "populated": True, "head": "1" * 40, "own_git": True,
           "unborn": None}
    row = module.Row("members", "members", module.FINDING, "x", None,
                     {"members": [unread, dict(unread, project="IRSS")]})
    assert module.drifted_reasons({"members": row}, {}) == []
    row.detail["members"] = [unread, off]
    assert module.drifted_reasons({"members": row}, {}) == [
        "a member is not at its pin"]
