# SPDX-License-Identifier: Apache-2.0
"""`update-shape.py` asks the shape pin's `source_repository:` once,
whichever way a run reaches the upstream, and refuses a value that is no
`owner/repo` in the pin's name (#1203, from the review of #1166, findings 3
and 9).

THE DEFECT, measured on main be21751c (Python 3.12.3, git 2.43.0). `prepare`
read the pin's value and used it two ways:

- with no `--upstream` it was the upstream `open_upstream` opened, and a
  value that named something in the directory the command ran in that is
  no repository (`contracts`, `scripts/repo_shape.py`, the pin itself) was
  `REFUSED update-upstream-not-a-repo: --upstream contracts exists but is
  not a git repository`, naming a flag nobody passed;
- with `--upstream` passed it was never asked. Every value below was
  `check` exit 1 over the upstream one commit on, as the scaffolded pin is,
  and `apply --yes --branch shape/fu-lf` of `"opensoft/openRepoShape\\n"`
  exited 0 with a commit whose subject broke after the name.

THE RULE NOW. `pin_source` asks the value in `prepare`, before the upstream
is opened, `--upstream` or not: something there that is no repository is
`update-upstream-not-a-repo`, a value `REPOSITORY_RE` does not take whole is
`update-upstream-unresolvable`, and `checked_value`'s is `unsafe-value`,
each naming the pin and its `source_repository:`. One the pin holds is
named before a bad `--upstream`.

A PATH IS REFUSED WITH `--upstream` PASSED TOO, the decision #1203 asked
for: the value names the upstream in the commit and the pull request
`apply` makes, and no tool writes a path there. A path that holds a
repository and is not spelled `owner/repo` (`~/shape`) is refused in both
routes, where with no `--upstream` main opened it in place. An `owner/repo`
spelling that is a repository where the command runs is taken, as it was,
and with no `--upstream` it is opened in place.

THE DOCTOR ANSWERS AS IT DID. `shape-doctor.py` calls `prepare` with its
own checkout as the upstream and reads a refusal out of it as that checkout
unable to answer; asked there, a hand-edited field was CANNOT ANSWER with a
`git fetch --all` for its remedy. It passes `ask_source=False`, and the
`update-shape.py check` its row names where the root is behind asks it.

No network and no GitHub: every `--upstream` is a local clone, the A -> B
upstream of `test_update_shape.py`, and the one run with no `--upstream`
that would clone runs in this process, with a stand-in that records the
`owner/repo` it is handed and opens that upstream instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO, git, run_script
from test_shape_doctor import doctor, rows_of
from test_update_shape import (  # noqa: F401
    CHANGED, UPDATE, assert_refused_and_unpinned, root, update_shape,
    upstream_and_project, verdicts)
from test_value_pattern_line_break import LF, WRITE_THE_PIN, pin_of, rewritten

#: The pin's line as both templates scaffold it.
SCAFFOLDED = "source_repository: opensoft/openRepoShape\n"
#: The words of the two refusals that ask what the value is.
NOT_A_REPO = "which exists but is not a git repository"
NOT_A_NAME = "which is not an `owner/repo` name"


def written_as(root: Path, value: str) -> None:
    """The pin's `source_repository:` written double-quoted as `value`, as
    a hand edit makes it, and committed, so `apply` starts from a clean
    tree as the issue's measurement did."""
    rewritten(root / "contracts" / "shape-pin.yaml", SCAFFOLDED,
              f'source_repository: "{value}"\n')
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "the pin's source, as a hand edit wrote it", "--",
        "contracts/shape-pin.yaml", cwd=root)


def run(root: Path, command: str, *extra: str, cwd: Path | None = None,
        env: dict | None = None):
    """`update-shape.py <command>` of `root`, run from the root unless
    `cwd` says otherwise: where a value such as `contracts` names a
    folder."""
    return run_script(UPDATE, command, "--root", str(root), *extra,
                      cwd=cwd or root, env=env)


def upstream_of(upstream_and_project: dict) -> tuple[str, str]:
    """`--upstream`, the local clone the A -> B fixture made."""
    return ("--upstream", str(upstream_and_project["upstream"]))


def refused(root: Path, code: str, read: str, said: str) -> list[str]:
    """The two lines a refused pin's value is told, whole."""
    return [f"REFUSED {code}: {pin_of(root)}: `source_repository:` is "
            f"{read}, {said}", WRITE_THE_PIN]


ROUTES = [
    pytest.param(False, id="no-upstream"),
    pytest.param(True, id="upstream-a-clone"),
]

#: `(the value as the pin writes it, double-quoted; as the refusal reads
#: it; the code; the words)`: the issue's table.
VALUES = [
    pytest.param("contracts", "'contracts'", "update-upstream-not-a-repo",
                 NOT_A_REPO, id="a-folder"),
    pytest.param("scripts/repo_shape.py", "'scripts/repo_shape.py'",
                 "update-upstream-not-a-repo", NOT_A_REPO,
                 id="a-file-spelled-owner-repo"),
    pytest.param("contracts/shape-pin.yaml", "'contracts/shape-pin.yaml'",
                 "update-upstream-not-a-repo", NOT_A_REPO,
                 id="the-pin-itself"),
    pytest.param("opensoft/openRepoShape\\n", "'opensoft/openRepoShape\\n'",
                 "update-upstream-unresolvable", NOT_A_NAME, id="line-feed"),
    pytest.param("opensoft/openRepoShape ", "'opensoft/openRepoShape '",
                 "update-upstream-unresolvable", NOT_A_NAME,
                 id="trailing-space"),
    pytest.param("has space/x", "'has space/x'",
                 "update-upstream-unresolvable", NOT_A_NAME, id="a-space"),
]


@pytest.mark.parametrize("passed", ROUTES)
@pytest.mark.parametrize("value, read, code, said", VALUES)
def test_the_pins_source_is_asked_in_both_routes_in_the_pins_name(
        root, upstream_and_project, passed, value, read, code, said):
    """THE ISSUE'S TABLE, in both routes, run from the root. On main the
    three paths were `update-upstream-not-a-repo` of `--upstream` with none
    passed, the other three named the pin with a remedy that offered
    `--upstream` a path, and with `--upstream` passed every one was exit 1
    and a report.
    Each is refused now, exit 2, in the pin's name, before anything is
    compared."""
    written_as(root, value)
    result = run(root, "check",
                 *(upstream_of(upstream_and_project) if passed else ()))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines() == refused(root, code, read, said), \
        result.stderr
    assert result.stdout == "", result.stdout


@pytest.mark.parametrize("passed", ROUTES)
@pytest.mark.parametrize("kept, read, code, said", [
    pytest.param("shape", "'~/shape'", "update-upstream-unresolvable",
                 NOT_A_NAME, id="a-clone"),
    pytest.param("notes", "'~/notes'", "update-upstream-not-a-repo",
                 NOT_A_REPO, id="a-folder"),
])
def test_a_source_under_home_is_looked_up_as_open_upstream_looks(
        root, upstream_and_project, tmp_path, passed, kept, read, code,
        said):
    """`~/<kept>`, with `~` expanded as `open_upstream` expands it. A clone
    of the upstream there is THE DECISION's row: with no `--upstream` main
    opened it in place (exit 1, the copies compared), and with one passed
    it was never asked; it is a path and no `owner/repo` name, so it is
    refused in both routes. A folder there that holds no repository is
    `update-upstream-not-a-repo` in the pin's name, as `contracts` is."""
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    git("clone", "-q", str(upstream_and_project["upstream"]),
        str(home / "shape"), cwd=tmp_path)
    written_as(root, f"~/{kept}")
    result = run(root, "check",
                 *(upstream_of(upstream_and_project) if passed else ()),
                 env={"HOME": str(home), "USERPROFILE": str(home)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines() == refused(root, code, read, said), \
        result.stderr


def test_a_source_checked_value_refuses_is_refused_with_upstream_passed(
        root, upstream_and_project):
    """`checked_value`'s refusal, of a value `REPOSITORY_RE` takes: with no
    `--upstream` it names the pin since #1139; with one passed, main never
    asked it and `check` exited 1."""
    written_as(root, "-opensoft/openRepoShape")
    result = run(root, "check", *upstream_of(upstream_and_project))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[0] == (
        f"REFUSED unsafe-value: {pin_of(root)}: `source_repository:` is "
        "'-opensoft/openRepoShape', which is not a value this tool will put "
        "on a `git` or `gh` command line"), result.stderr


def test_the_pins_source_is_named_before_a_bad_upstream(root):
    """Asked before the upstream is opened: where the pin's value and
    `--upstream` are both refused, the pin is named first, and no clone is
    started for a flag whose run would end in the pin's refusal. On main
    the flag was named."""
    written_as(root, "opensoft/openRepoShape\\n")
    result = run(root, "check", "--upstream", "opensoft/openRepoShape" + LF)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines() == refused(
        root, "update-upstream-unresolvable", "'opensoft/openRepoShape\\n'",
        NOT_A_NAME), result.stderr


def test_apply_over_a_refused_source_writes_nothing(root,
                                                    upstream_and_project):
    """THE ISSUE'S `apply`: on main, over the upstream one commit on, `apply
    --yes --branch shape/fu-lf` exited 0 and committed `Re-sync the shape
    copies to opensoft/openRepoShape`, a line feed, then ` @ <sha>`. It is
    refused now before the upstream is opened: no branch, no commit, the
    pin's `commit:` as it was and the tree clean."""
    written_as(root, "opensoft/openRepoShape\\n")
    head = git("rev-parse", "HEAD", cwd=root).stdout
    result = run(root, "apply", "--yes", *upstream_of(upstream_and_project),
                 "--at", upstream_and_project["b"], "--branch", "shape/fu-lf")
    assert_refused_and_unpinned(
        result, root, upstream_and_project, "update-upstream-unresolvable",
        refused(root, "update-upstream-unresolvable",
                "'opensoft/openRepoShape\\n'", NOT_A_NAME)[0])
    assert git("rev-parse", "HEAD", cwd=root).stdout == head
    assert git("branch", "--list", "shape/fu-lf", cwd=root).stdout == ""
    assert git("status", "--porcelain", cwd=root).stdout == ""


def test_an_owner_repo_that_is_a_clone_where_it_runs_is_opened_in_place(
        root, upstream_and_project, tmp_path):
    """UNCHANGED, AND ON PURPOSE. The scaffolded `opensoft/openRepoShape`,
    run with no `--upstream` from a folder that keeps a clone at
    `opensoft/openRepoShape`, as a checkout laid out by owner does: main
    opened that clone in place, and it still does, so `check` answers as it
    does with `--upstream` naming the clone."""
    here = tmp_path / "here"
    clone = here / "opensoft" / "openRepoShape"
    git("clone", "-q", str(upstream_and_project["upstream"]), str(clone),
        cwd=tmp_path)
    in_place = run(root, "check", cwd=here)
    passed = run(root, "check", "--upstream", str(clone), cwd=here)
    assert in_place.returncode == 1, in_place.stdout + in_place.stderr
    assert verdicts(in_place.stdout)[CHANGED] == "upstream-changed"
    assert (in_place.returncode, in_place.stdout) == (passed.returncode,
                                                      passed.stdout)


def test_a_pin_as_scaffolded_hands_its_owner_repo_to_open_upstream(
        update_shape, root, upstream_and_project, monkeypatch, capsys):
    """UNCHANGED: the scaffolded pin with no `--upstream` reaches
    `open_upstream` with `opensoft/openRepoShape`, which bare-clones it.
    In this process, with a stand-in that records what it is handed and
    opens the local upstream instead, `check` answers as it does with
    `--upstream` naming that upstream. The stand-in takes, and drops, the
    pin's path that main's `prepare` handed `open_upstream` too, so this
    row is asked of main's code as it is of this."""
    real = update_shape.open_upstream
    asked: list[str] = []

    def opening(spec, *_pin_path):
        asked.append(spec)
        return real(str(upstream_and_project["upstream"]))

    monkeypatch.setattr(update_shape, "open_upstream", opening)
    code = update_shape.main(["check", "--root", str(root)])
    out = capsys.readouterr().out
    passed = run(root, "check", *upstream_of(upstream_and_project))
    assert asked == ["opensoft/openRepoShape"]
    assert (code, out) == (passed.returncode, passed.stdout)


def test_the_doctor_does_not_call_a_hand_edited_source_the_standards(root):
    """THE DOCTOR'S ANSWER IS MAIN'S. `shape-doctor.py` hands `prepare` its
    own checkout as the upstream and reads a refusal out of it as that
    checkout unable to answer, so, asked there, a hand edit of the field
    was CANNOT ANSWER, exit 3, with a `git fetch --all` NEXT that mends
    nothing (measured with `ask_source` left True). The doctor passes
    `ask_source=False`: its row is no `environment` row, and it does not
    exit 3. The doctor here is this checkout's, and so is the
    `update-shape.py` it loads."""
    written_as(root, "opensoft/openRepoShape\\n")
    result = doctor(REPO, root, "--json")
    row = rows_of(result)["shape-currency"]
    assert result.returncode != 3, result.stdout + result.stderr
    assert "environment" not in row["detail"], row
