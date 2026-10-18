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
`tests/test_pinned_copy_text.py`). Here the two templates' `_git_runs` are
loaded in this process and handed the same errors, and must give one
answer to each: the errors `validate-pins.py`'s own tests hand its wrapper
(`tests/test_validate_pins_without_git.py`), the member checkout git could
not enter, and Windows' `[WinError 193]`.

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
from typing import NamedTuple

import pytest

from conftest import REPO, git, load_without_bytecode
from test_family import MEMBERS, family, holder  # noqa: F401
from test_validate_family_without_git import (REMEDIATION, holder_validator,
                                              run, without_git)
from test_validate_pins_without_git import (CANNOT_EXECUTE, NO_FILE_NAMED,
                                            NO_GIT, NOT_EXECUTABLE,
                                            NOT_EXECUTABLE_NO_FILE_NAMED,
                                            NOT_GIT)

FAMILY_TEMPLATE = (REPO / "templates" / "family-root" / "scripts" /
                   "validate-family.py")
PINS_TEMPLATE = (REPO / "templates" / "assembly-root" / "scripts" /
                 "validate-pins.py")

MEMBER = MEMBERS[0]
ROW = f"members/{MEMBER}"
COUNTED = "git-not-runnable"
PASSED = "passed through unchanged"


def win_error_193(_root=None) -> OSError:
    """What CPython raises on Windows for a `git.exe` that Windows cannot
    execute (`[WinError 193] %1 is not a valid Win32 application`): a plain
    `OSError`, since `winerror` 193 maps to `errno` `ENOEXEC`, which has no
    subclass, and no filename, since `CreateProcess` failures carry none.
    Read from CPython (`PC/errmap.h`, `_winapi.CreateProcess`), not run on
    Windows, and built by hand on every OS: neither rule reads `winerror`."""
    error = OSError(errno.ENOEXEC, "%1 is not a valid Win32 application")
    error.winerror = 193
    return error


#: The errors git raises when it will not start, each named `git` or naming
#: nothing (`tests/test_validate_pins_without_git.py`'s): both rules count
#: them.
WILL_NOT_START = {
    "no-git": NO_GIT,
    "git-not-executable": NOT_EXECUTABLE,
    "git-cannot-execute": CANNOT_EXECUTE,
    "no-git-naming-no-file": NO_FILE_NAMED,
    "git-not-executable-naming-no-file": NOT_EXECUTABLE_NO_FILE_NAMED,
}

#: The errors that are not a git that will not start, each built from a
#: root: `validate-pins.py`'s `NOT_GIT`, the member's checkout git could
#: not enter, which `subprocess` names in `filename`, as #928 names it, and
#: Windows' `[WinError 193]`, which both rules pass through.
NOT_GITS = {
    **NOT_GIT,
    "member-checkout-not-entered": lambda root: PermissionError(
        errno.EACCES, "Permission denied", str(root / ROW)),
    "winerror-193": win_error_193,
}

PARITY = [
    *(pytest.param(lambda _root, error=error: error, COUNTED, id=name)
      for name, error in WILL_NOT_START.items()),
    *(pytest.param(make, PASSED, id=name) for name, make in NOT_GITS.items()),
]


@pytest.fixture(scope="module")
def validators() -> dict:
    """Both templates' validators, loaded with no bytecode, each over the
    standard's `repo_shape`; `sys.path`, which each extends, is put back."""
    saved = list(sys.path)
    try:
        return {
            "validate-family.py": load_without_bytecode(
                FAMILY_TEMPLATE, "validate_family_git_not_runnable"),
            "validate-pins.py": load_without_bytecode(
                PINS_TEMPLATE, "validate_pins_git_not_runnable"),
        }
    finally:
        sys.path[:] = saved


def answer(module, error: OSError) -> str:
    """What `module._git_runs` does with `error` raised inside it: the
    `git-not-runnable` refusal raised from it, or `error` itself raised on,
    else what it raised instead, or that it raised nothing."""
    try:
        with module._git_runs("the check named"):
            raise error
    except module.Refusal as refusal:
        return (COUNTED if (refusal.code, refusal.__cause__)
                == (COUNTED, error) else repr(refusal))
    except OSError as raised:
        return PASSED if raised is error else repr(raised)
    return "nothing raised"


@pytest.mark.parametrize("make, expected", PARITY)
def test_both_validators_give_one_answer_to_each_oserror(validators,
                                                         tmp_path, make,
                                                         expected):
    """THE PARITY (#928): one rule in two pinned copies. `validate-family.py`
    counted all of these, and `validate-pins.py` the five that say git will
    not start. A change to either copy's rule fails here until the other
    copy says the same."""
    error = make(tmp_path)
    answers = {name: answer(module, error)
               for name, module in validators.items()}
    assert answers == dict.fromkeys(validators, expected)


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
