# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py` counts an `OSError` as `git-not-runnable` only where
git could not be started, by `validate-pins.py`'s rule, and only around the
git calls themselves (#928).

Its `_git_runs` turned ANY `OSError` into `git-not-runnable`, "put git on
PATH", and two of its blocks held a whole check: a member's gitlink check
and its tree check. So whatever else either check met was told to put git
on PATH: Python 3.12's refused `stat` of a member's `.git` inside the tree
check, and a git that could not enter the member's directory, which
`subprocess` names in `filename`. `validate-pins.py` counts only an
`OSError` whose `filename` is `git`, or a `FileNotFoundError` or a
`PermissionError` that names no file (Windows' `CreateProcess` failures
carry none), and only around its git calls. #430's slice (#956) already
refuses an unreadable checkout by name, `member-unreadable`, before any
git runs in it; what was left is the rule and the two blocks.

THE RULE IS COPIED, NOT SHARED. #928 proposed moving it into
`repo_shape.py`, but both validators are pinned copies, and a holder or a
root re-copies its pinned files one row at a time, so either may run beside
a `repo_shape.py` older than itself (#610's skew rule,
`tests/test_pinned_copy_text.py`). Here the rule's four copies are loaded
in this process and handed the same errors, and must give one answer to
each: both validators' `_git_runs`, and both roots' `bootstrap.py`, the
assembly root's `_git_runs` and the holder's `git_not_started` (#694; RV983's
NIT 1 on #983). The errors are the ones `validate-pins.py`'s own tests hand
its wrapper (`tests/test_validate_pins_without_git.py`), the member checkout
git could not enter, and Windows' `[WinError 193]`, which every copy now
counts (#1001), with the rest of the `winerror`s that say Windows could not
start git (#1040). And the four are held to one text.

WINDOWS' `[WinError 193]` (#1001), a `git.exe` Windows cannot execute, names
no file and is neither `FileNotFoundError` nor `PermissionError`, so no copy
counted it, and each run ended in a traceback, exit 1. Each copy now counts a
nameless `OSError` whose `winerror` is 193, with the words, the remedy and
the exit of a missing git; here each copy's own script is run with git
raising it, as Windows would. So it is with the rest of Windows' nameless
failures to start a program (#1040): 216, a `git.exe` built for another
architecture, 1260, one a policy blocks, and the rest of 193's `ENOEXEC`
family, 11 and 188 to 202. Each is a plain `OSError` (`PC/errmap.h`), each
copy counts each, and each script is run with git raising 216 too. A
nameless `[WinError 267]`, a `cwd` that is not a folder, still passes
through.

THE REST RUNS THE HOLDER'S OWN VALIDATOR IN THIS PROCESS, with git failing
at one of the three calls that are still wrapped (the gitlink, the pinned
commit's lookup and the digest) as `tests/test_validate_family_without_git.py`
makes it fail; and with a step that runs no git inside each of the two old
blocks raising an error the rule counts, which now passes through as it
came.
"""

from __future__ import annotations

import ast
import errno
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import REPO, git, load_without_bytecode, run_script
from test_bootstrap_without_git import (ASSEMBLY_REMEDY, FAMILY_REMEDY,
                                        GIT_FOR_ANOTHER_MACHINE,
                                        GIT_NOT_WIN32)
from test_family import MEMBERS, family, holder  # noqa: F401
from test_validate_family_without_git import (REMEDIATION, holder_validator,
                                              run, without_git)
from test_validate_pins_without_git import (CANNOT_EXECUTE, NO_FILE_NAMED,
                                            NO_GIT, NOT_EXECUTABLE,
                                            NOT_EXECUTABLE_NO_FILE_NAMED,
                                            NOT_GIT, WIN_ERROR_193,
                                            WIN_ERROR_216, WIN_ERROR_1260,
                                            win_error)
from test_validate_pins_without_git import REMEDIATION as PINS_REMEDIATION

FAMILY_TEMPLATE = (REPO / "templates" / "family-root" / "scripts" /
                   "validate-family.py")
PINS_TEMPLATE = (REPO / "templates" / "assembly-root" / "scripts" /
                 "validate-pins.py")

#: The rule's four copies, each the template and the function that holds it
#: (#1001; RV983's NIT 1 on #983): both validators' `_git_runs`, the
#: assembly root's `bootstrap.py`'s `_git_runs`, and the holder's
#: `bootstrap.py`'s `git_not_started` (#694).
COPIES = {
    "validate-family.py": (FAMILY_TEMPLATE, "_git_runs"),
    "validate-pins.py": (PINS_TEMPLATE, "_git_runs"),
    "family-root bootstrap.py": (
        REPO / "templates" / "family-root" / "scripts" / "bootstrap.py",
        "git_not_started"),
    "assembly-root bootstrap.py": (
        REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
        "_git_runs"),
}

MEMBER = MEMBERS[0]
ROW = f"members/{MEMBER}"
COUNTED = "git-not-runnable"
PASSED = "passed through unchanged"
#: What every copy's `git-not-runnable` remedy starts with.
PUT_GIT_ON_PATH = "Remediation: put git on PATH and run "


def win_error_193_naming(path: Path) -> OSError:
    """`WIN_ERROR_193` naming `path`: no error Windows raises at a git call,
    since `CreateProcess` failures carry no filename, but the half of the
    rule that counts 193 only where nothing is named (#1001)."""
    error = OSError(errno.ENOEXEC, "%1 is not a valid Win32 application",
                    str(path))
    error.winerror = 193
    return error


#: The errors git raises when it will not start, each named `git` or naming
#: nothing (`tests/test_validate_pins_without_git.py`'s): every copy counts
#: them, Windows' `[WinError 193]` too (#1001), and its `[WinError 216]` and
#: `[WinError 1260]` (#1040).
WILL_NOT_START = {
    "no-git": NO_GIT,
    "git-not-executable": NOT_EXECUTABLE,
    "git-cannot-execute": CANNOT_EXECUTE,
    "no-git-naming-no-file": NO_FILE_NAMED,
    "git-not-executable-naming-no-file": NOT_EXECUTABLE_NO_FILE_NAMED,
    "winerror-193": WIN_ERROR_193,
    "winerror-216": WIN_ERROR_216,
    "winerror-1260": WIN_ERROR_1260,
}

#: What Windows says of a program it cannot run, for most of `NOT_LOADABLE`.
CANNOT_RUN = "The operating system cannot run %1"
#: The rest of the `ENOEXEC` family `[WinError 193]` is in (#1040), each a
#: program Windows cannot load: `ERROR_BAD_FORMAT` (11), and 188 to 202 but
#: 193. `PC/errmap.h` maps each to `ENOEXEC`, so each is a plain `OSError`
#: that names no file, as 193 is, and is 193 but for its `winerror` and its
#: words. Each copy counts each; they are asked of the four copies alone, and
#: the per-call rows below ask 193 for them.
NOT_LOADABLE = {
    f"winerror-{code}": win_error(code, errno.ENOEXEC, words)
    for code, words in {
        11: "An attempt was made to load a program with an incorrect format",
        188: CANNOT_RUN, 189: CANNOT_RUN, 190: CANNOT_RUN,
        191: "Cannot run %1 in Win32 mode",
        192: CANNOT_RUN, 194: CANNOT_RUN, 195: CANNOT_RUN,
        196: "The operating system cannot run this application program",
        197: "The operating system is not presently configured to run this "
             "application",
        198: CANNOT_RUN,
        199: "The operating system cannot run this application program",
        200: "The code segment cannot be greater than or equal to 64K",
        201: CANNOT_RUN, 202: CANNOT_RUN,
    }.items()
}

#: The errors that are not a git that will not start, each built from a
#: root: `validate-pins.py`'s `NOT_GIT`, a nameless `[WinError 267]` among
#: them (#1040), the member's checkout git could not enter, which
#: `subprocess` names in `filename`, as #928 names it, and a `[WinError 193]`
#: that names it.
NOT_GITS = {
    **NOT_GIT,
    "member-checkout-not-entered": lambda root: PermissionError(
        errno.EACCES, "Permission denied", str(root / ROW)),
    "winerror-193-naming-the-member": lambda root: win_error_193_naming(
        root / ROW),
}

PARITY = [
    *(pytest.param(lambda _root, error=error: error, COUNTED, id=name)
      for name, error in {**WILL_NOT_START, **NOT_LOADABLE}.items()),
    *(pytest.param(make, PASSED, id=name) for name, make in NOT_GITS.items()),
]


@pytest.fixture(scope="module")
def copies() -> dict:
    """The four copies' templates, loaded with no bytecode, each over the
    standard's `repo_shape`; `sys.path`, which each extends, is put back."""
    saved = list(sys.path)
    try:
        return {name: load_without_bytecode(path, f"git_not_runnable_{index}")
                for index, (name, (path, _)) in enumerate(COPIES.items())}
    finally:
        sys.path[:] = saved


def answer(module, error: OSError) -> str:
    """What `module`'s copy of the rule does with `error` raised where git
    starts: the `git-not-runnable` refusal raised from it, with a missing
    git's words and remedy, or `error` itself raised on, else what it raised
    instead, or that it raised nothing. A `_git_runs` is handed it inside
    its block; the holder's `git_not_started` is asked as its call site
    asks it (`started`, #954), and the refusal it gives is raised from it."""
    try:
        if hasattr(module, "_git_runs"):
            with module._git_runs("the check named"):
                raise error
        else:
            refusal = module.git_not_started(error)
            if refusal is None:
                raise error
            raise refusal from error
    except module.Refusal as refusal:
        missing_git = (
            (refusal.code, refusal.__cause__) == (COUNTED, error)
            and refusal.detail.endswith(
                f": git could not be run ({error.strerror})")
            and refusal.remediation.startswith(PUT_GIT_ON_PATH))
        return COUNTED if missing_git else repr(refusal)
    except OSError as raised:
        return PASSED if raised is error else repr(raised)
    return "nothing raised"


@pytest.mark.parametrize("make, expected", PARITY)
def test_the_four_copies_give_one_answer_to_each_oserror(copies, tmp_path,
                                                         make, expected):
    """THE PARITY (#928, #1001, #1040): one rule in four pinned copies.
    `validate-family.py` counted all of these, and `validate-pins.py` and
    both bootstraps the five that say git will not start, until #1001 made
    `[WinError 193]` the sixth in all four, and #1040 the rest of the
    `winerror`s that say Windows could not start git. A change to any
    copy's rule fails here until the other three say the same."""
    error = make(tmp_path)
    answers = {name: answer(module, error) for name, module in copies.items()}
    assert answers == dict.fromkeys(copies, expected)


def the_rule(path: Path, function: str) -> list[str]:
    """The rule as `function` in `path` holds it, its layout aside
    (`ast.dump`): what `nameless` is, and the test of the `if` that reads
    it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    held = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == function)
    return [ast.dump(node.value if isinstance(node, ast.Assign) else node.test)
            for node in ast.walk(held)
            if (isinstance(node, ast.Assign)
                and [getattr(target, "id", None) for target in node.targets]
                == ["nameless"])
            or (isinstance(node, ast.If)
                and any(isinstance(name, ast.Name) and name.id == "nameless"
                        for name in ast.walk(node.test)))]


def test_the_four_copies_are_one_text():
    """ONE TEXT (#1001). The rule is copied, not shared (#610's skew rule),
    and the parity above holds the copies to one answer for the errors it
    knows. Here the copies are held to one rule for every error: the same
    `nameless`, and the same test of it, in each. The assembly root's
    `bootstrap.py` said the same rule in other words until #1001."""
    rules = {name: the_rule(path, function)
             for name, (path, function) in COPIES.items()}
    assert len(rules["validate-pins.py"]) == 2, rules
    assert rules == dict.fromkeys(COPIES, rules["validate-pins.py"])


@pytest.mark.parametrize("raising, error", [
    pytest.param(GIT_NOT_WIN32, WIN_ERROR_193, id="winerror-193"),
    pytest.param(GIT_FOR_ANOTHER_MACHINE, WIN_ERROR_216, id="winerror-216"),
])
@pytest.mark.parametrize("root, script, remedy", [
    pytest.param("holder", "validate-family.py", REMEDIATION,
                 id="validate-family.py"),
    pytest.param("project", "validate-pins.py", PINS_REMEDIATION,
                 id="validate-pins.py"),
    pytest.param("holder", "bootstrap.py", FAMILY_REMEDY,
                 id="family-root bootstrap.py"),
    pytest.param("project", "bootstrap.py", ASSEMBLY_REMEDY,
                 id="assembly-root bootstrap.py"),
])
def test_a_git_windows_cannot_execute_is_refused_by_each_copy(
        request, tmp_path, root, script, remedy, raising, error):
    """#1001's ROW IN EACH COPY, RUN: the root's own script, in a child, where
    every start of git raises Windows' `[WinError 193]`, and #1040's, where
    every start raises its `[WinError 216]`, a `git.exe` built for another
    architecture. Each ended in a traceback, exit 1; each now refuses
    `git-not-runnable`, exit 2, at the first check that runs git, with its
    remedy to put git on PATH."""
    where = request.getfixturevalue(root)
    shim = tmp_path / "git-not-win32"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(raising, encoding="utf-8")
    result = run_script(where / "scripts" / script, cwd=where,
                        env={"PYTHONPATH": str(shim)})
    assert result.returncode == 2, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    refused, said = result.stderr.splitlines()[-2:]
    assert refused.startswith(f"REFUSED {COUNTED}: "), result.stderr
    assert refused.endswith(
        f": git could not be run ({error.strerror})"), result.stderr
    assert said == remedy, result.stderr


class Call(NamedTuple):
    """One of the three calls that run git for a member, and how
    `without_git` makes it alone fail: in the validator's own `git_out` or in
    `repo_shape`'s (`helpers`), and only where git runs outside the holder,
    in the member (`in_member`). `unread` is what the refusal names."""

    validator: bool
    helpers: bool
    in_member: bool
    unread: str


TREE_UNREAD = (f"{MEMBER}'s pinned commit and its tree digest could not be "
               f"read in {ROW}")
CALLS = pytest.mark.parametrize("call", [
    Call(False, True, False,
         f"the gitlink recorded at {ROW} could not be read"),
    Call(True, False, True, TREE_UNREAD),
    Call(False, True, True, TREE_UNREAD),
], ids=["gitlink", "commit", "digest"])


def fail_at(call: Call, module, holder, monkeypatch, error: OSError) -> None:
    without_git(module, monkeypatch, validator=call.validator,
                helpers=call.helpers, error=error,
                outside=holder if call.in_member else None)


@CALLS
@pytest.mark.parametrize("error", WILL_NOT_START.values(),
                         ids=WILL_NOT_START.keys())
def test_a_git_that_will_not_start_is_named_at_each_call(holder, monkeypatch,
                                                         capsys, call, error):
    """Each of the three calls still names its check where git will not
    start, the digest's on its own too, which ran inside the tree check's
    block and now has one of its own. The pinned commit's lookup keeps its
    block outside its `except Refusal`, which would read the refusal as a
    commit the member does not have."""
    module = holder_validator(holder, monkeypatch)
    fail_at(call, module, holder, monkeypatch, error)
    assert run(module, holder, capsys) == (2, [
        f"REFUSED git-not-runnable: {call.unread}: git could not be run "
        f"({error.strerror})", REMEDIATION])


@CALLS
@pytest.mark.parametrize("make", NOT_GITS.values(), ids=NOT_GITS.keys())
def test_an_oserror_that_is_not_git_s_leaves_each_call_unchanged(
        holder, monkeypatch, capsys, call, make):
    """Every other `OSError` at a call leaves the block as it entered, as
    `validate-pins.py`'s leaves its own: no `git-not-runnable`, which would
    send the operator after git. The member's checkout that git could not
    enter is `member-unreadable` before git runs there (#430); at the
    call, only a race reaches it."""
    error = make(holder)
    module = holder_validator(holder, monkeypatch)
    fail_at(call, module, holder, monkeypatch, error)
    with pytest.raises(OSError) as caught:
        module.main(["--root", str(holder)])
    assert caught.value is error
    out, err = capsys.readouterr()
    assert COUNTED not in out + err


def raising(error: OSError):
    def raise_it(*args, **kwargs):
        raise error
    return raise_it


def test_the_gitlink_check_counts_nothing_but_its_git(holder, monkeypatch,
                                                      capsys):
    """THE GITLINK CHECK'S BLOCK held the whole check, and with it the
    remedy `member-gitlink-absent` builds, which reads the disk and HEAD's
    `.gitmodules`: a row whose gitlink was taken out by hand and committed.
    An error the rule counts, raised there, now passes through, where it
    was `the gitlink recorded at members/IRRS could not be read: git could
    not be run`."""
    git("rm", "-q", "--cached", "--", ROW, cwd=holder)
    git("commit", "-qm", f"{MEMBER}'s gitlink taken out by hand",
        cwd=holder)
    module = holder_validator(holder, monkeypatch)
    monkeypatch.setattr(module, "_gitlink_put_back",
                        raising(NO_FILE_NAMED))
    with pytest.raises(FileNotFoundError) as caught:
        module.main(["--root", str(holder)])
    assert caught.value is NO_FILE_NAMED
    out, err = capsys.readouterr()
    assert COUNTED not in out + err


def test_the_tree_check_counts_nothing_but_its_git(holder, monkeypatch):
    """THE TREE CHECK'S BLOCK held the whole check, and with it the `stat` of
    the member's `.git`, which Python 3.12 raised for a checkout this user
    cannot search, there `git-not-runnable`. Asked of `_check_member_checkout`
    itself, as `main` asks it once the stop has asked every member's `.git`
    (`_check_members`): the `stat` raises an error the rule counts, and it
    passes through."""
    module = holder_validator(holder, monkeypatch)
    report = module.Report()
    row = next(row for row in module.load_yaml(holder / "family.yaml")
               ["members"] if row["project"] == MEMBER)
    asked = module._check_member(holder, row, {}, report,
                                 module._member_gitlinks(holder))
    monkeypatch.setattr(module, "_checked_out",
                        raising(NOT_EXECUTABLE_NO_FILE_NAMED))
    with pytest.raises(PermissionError) as caught:
        module._check_member_checkout(holder, asked, report, set())
    assert caught.value is NOT_EXECUTABLE_NO_FILE_NAMED


def test_no_git_runs_block_holds_a_check():
    """READ FROM THE SOURCE, for every block, the twelve others too: none
    holds a call to a `_check_*` function, as the gitlink check's and the
    tree check's held `_check_member_gitlink` and `_check_member_tree`."""
    tree = ast.parse(FAMILY_TEMPLATE.read_text(encoding="utf-8"))
    blocks = [node for node in ast.walk(tree) if isinstance(node, ast.With)
              and any(isinstance(item.context_expr, ast.Call)
                      and getattr(item.context_expr.func, "id", "")
                      == "_git_runs" for item in node.items)]
    held = sorted((block.lineno, call.func.id) for block in blocks
                  for call in ast.walk(block)
                  if isinstance(call, ast.Call)
                  and isinstance(call.func, ast.Name)
                  and call.func.id.startswith("_check_"))
    assert len(blocks) >= 15, len(blocks)
    assert held == []
