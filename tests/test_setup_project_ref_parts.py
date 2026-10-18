# SPDX-License-Identifier: Apache-2.0
"""`--shape-ref` is held to git's rule for a ref part by part (#857).

`checked_ref` refused `..` and a `.lock` at the very end, where git's rule
is asked of each part between slashes: none is empty, none starts with `.`,
none ends in `.lock`, and the whole does not end in `.`. So `a.lock/b`,
`x/y.lock/z`, `release.lock/v1`, `a/.b`, `a//b`, `a/b/`, `a.lock/` and `a.`
passed, and `git check-ref-format --branch` refuses each of them. In
self-bootstrap mode the person met git's own `pathspec ... did not match`
after the standard was cloned. Each is refused now, before anything, with
the part of the rule it failed; `topic.locked` and `a./b` still go on. A part
that starts with `.` is refused wherever it stands (`a/.b/c`, `a/b/.c/d`), and
a name that fails two rules is told the first one in the order
`why_not_a_ref` asks them (`a//..b` is a range, not an empty part).

The table asks git itself, `git check-ref-format --branch`, beside the tool:
no network, and the two give one answer for every name in it.
"""

from __future__ import annotations

import subprocess

import pytest

from conftest import REPO
from test_setup_project_name_edges import FIRST, LOCK, RANGE
from test_setup_project_py import (entry_point_module, make_outside_checkout,
                                   run_entry)
from test_setup_project_typed_name import the_refusal

LOCK_PART = ("A part of it before a `/` ends in `.lock`, the name git gives "
             "the lock file it writes beside a ref, and git takes no ref with "
             "such a part.")
DOT_PART = ("A part of it after a `/` starts with `.`, and git takes no ref "
            "with such a part.")
EMPTY_PART = ("It holds `//` or ends in `/`, and git takes no ref with an "
              "empty part between slashes.")
DOT_END = "It ends in `.`, and git takes no ref that does."

#: Each name, and the reason the tool refuses it ("" where it goes on). The
#: issue's ten come first, then the names around them.
NAMES = {
    "a.lock": LOCK,
    "a/b.lock": LOCK,
    "a.lock/b": LOCK_PART,
    "x/y.lock/z": LOCK_PART,
    "release.lock/v1": LOCK_PART,
    "a/.b": DOT_PART,
    "a/.b/c": DOT_PART,
    "a/b/.c/d": DOT_PART,
    "a//b": EMPTY_PART,
    "a/b/": EMPTY_PART,
    "a.lock/": EMPTY_PART,
    "topic.locked": "",
    "a.": DOT_END,
    "a/b.": DOT_END,
    "a./b": "",
    "a.lockb": "",
    "a/b.lock/": EMPTY_PART,
    "a/.lock": DOT_PART,
    "a..b": RANGE,
    "refs/tags/v1.0": "",
    "v1.0.0": "",
    # A name that breaks two rules is told the first one `why_not_a_ref` asks,
    # in its order: `..`, an empty part, a part that starts with `.`, a name
    # that ends in `.lock`, a part that ends in `.lock`, a `.` at the end.
    # Each row below holds one pair of neighbours in that order apart; two
    # rows above hold the others (`a/.lock`: a dot part, then a lock at the
    # end; `a/b.lock`: a lock at the end, then a lock part).
    "a//..b": RANGE,
    "a//.b": EMPTY_PART,
    "a.lock/b.": LOCK_PART,
}


def tool_answer(module, name):
    """The reason `checked_ref` gives for refusing `name`, or ""."""
    try:
        module.checked_ref("--shape-ref", name)
    except module.Refusal as refusal:
        return str(refusal).split(" command line. ", 1)[1]
    return ""


@pytest.mark.parametrize("name", NAMES)
def test_the_tool_and_git_give_one_answer(tmp_path, name):
    git = subprocess.run(["git", "check-ref-format", "--branch", name],
                         cwd=str(tmp_path), capture_output=True, text=True,
                         check=False)
    why = tool_answer(entry_point_module(), name)
    assert (why == "") == (git.returncode == 0), (name, why, git.stderr)
    assert why == NAMES[name]


@pytest.mark.parametrize("name", ["a.lock/b", "a/.b", "a//b"])
def test_a_ref_git_refuses_is_refused_before_the_clone(tmp_path, name):
    """A ref git refuses ended a self-bootstrap run in git's `pathspec ...
    did not match`, after the standard was cloned. It is refused before
    `(0) self-bootstrap` prints."""
    outside = make_outside_checkout(tmp_path)
    result = run_entry("--org", "demoorg", "--project", "Sample",
                       "--shape-ref", name,
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       cwd=outside, script=outside / "setup-project.py",
                       extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert the_refusal(result.stderr) == (
        "REFUSED: " + FIRST.format(what="--shape-ref", shown=ascii(name))
        + NAMES[name])
    assert not (tmp_path / "remotes").exists()
