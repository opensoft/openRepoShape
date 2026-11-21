# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py` counts commits with no path after the revision, so a
file named like it was read as the path (#1215).

`git rev-list --count <rev>` reads its argument as a revision AND, where the
current directory is a work tree holding a file of that name, as a path, and
refuses to choose: `fatal: ambiguous argument 'HEAD': both revision and
filename`, exit 128. `--` after the revision says which it is.

MEASURED ON MAIN AT 4552efa6a (2026-11-09), git 2.43.0, git-filter-repo
2.47.0, a stub `gh` and local remotes only:

  * `_extract_leg` counts the commits a leg kept with `git rev-list --count
    HEAD` in the leg's work clone, right after `git filter-repo`. A leg that
    keeps a root file named `HEAD` stopped `execute` there, `REFUSED
    extracting the <role> leg. git-failed`, exit 2, with both bare
    repositories made: neither leg pushed where the spec leg kept the file,
    and the spec leg pushed and the code leg's repository empty where the
    code leg did. `plan` and `check` passed.
  * `Source.commit_count` counts the source's commits with `git rev-list
    --count <the branch tip's id>` in the source, which is read in place. A
    file of that name in its work tree (a note somebody wrote under the id
    `git rev-parse` printed) stopped `plan`, `REFUSED git-failed`, exit 2,
    before a word of the plan was written.

Both argv end in `--` now. The two rows below fail on main and pass here, and
each has a control with no such file, which passes on both.
"""

from __future__ import annotations

import re
import shutil

import pytest

from conftest import (ADOPT, SYNTHETIC_TREE, git, make_source_repo, resolve,
                      run_script, write_plan)

PROJECT = "Northwind"
#: What `plan` leaves for a person to answer, as `test_adopt_e2e.py` does.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: The root file the revision is read as: a file git cannot tell from `HEAD`.
NAMED = "HEAD"
#: The line `_extract_leg` prints for a leg: its role and the commits kept.
KEPT = re.compile(r"^  (spec|code) +\d+ path\(s\) -> [0-9a-f]{12} "
                  r"\((\d+) commits kept\)", re.MULTILINE)

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def said(run) -> str:
    """A run's output, readable in an assertion message."""
    return f"exit {run.returncode}:\n{run.stdout}{run.stderr}"


@needs_filter_repo
@pytest.mark.parametrize("keeper", [None, "spec", "code"],
                         ids=["no-such-file", "spec-leg", "code-leg"])
def test_execute_pushes_a_leg_that_keeps_a_root_file_named_head(tmp_path,
                                                                keeper):
    """THE ISSUE. The source holds a root file named `HEAD`, which the plan
    asks about like any path no rule names, answered here as `spec` or as
    `code`. `execute` pushes both legs, says `adoption verified` and exits
    0, as it does with no such file (the control); on main the leg that kept
    it died at `git rev-list --count HEAD`, exit 128, the code leg's
    repository made and empty. Each leg's printed count is what the leg it
    pushed holds, and the pushed leg holds the file."""
    tree = dict(SYNTHETIC_TREE)
    if keeper:
        tree[NAMED] = "a root file named HEAD\n"
    source = make_source_repo(tmp_path / "Thing", tree)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, said(written)
    for path, leg in (*ANSWERS, *([(NAMED, keeper)] if keeper else [])):
        resolve(plan, path, leg)

    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--work-dir", str(tmp_path / "work"))
    assert checked.returncode == 0, said(checked)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 0, said(result)
    assert "ambiguous argument" not in result.stderr, said(result)
    assert "adoption verified" in result.stdout, said(result)
    kept = dict(KEPT.findall(result.stdout))
    assert sorted(kept) == ["code", "spec"], said(result)
    for leg in ("spec", "code"):
        bare = tmp_path / "remotes" / f"{PROJECT}-{leg}.git"
        pushed = git("rev-list", "--count", "main", cwd=bare).stdout.strip()
        assert kept[leg] == pushed, f"the {leg} leg: {kept}, pushed {pushed}"
        names = git("ls-tree", "--name-only", "main",
                    cwd=bare).stdout.split()
        assert (NAMED in names) == (leg == keeper), (leg, names)


@pytest.mark.parametrize("noted", [False, True],
                         ids=["no-such-file", "a-file-named-as-the-tip"])
def test_plan_and_check_read_a_source_holding_a_file_named_as_its_tip(
        tmp_path, noted):
    """`Source.commit_count` counts the branch tip's id, in the source, which
    is read in place. A file of that name in the source's work tree (here an
    untracked one, written under the id `git rev-parse` printed) is no
    reason to refuse: `plan` writes the plan and says `3 commits`, and
    `check` of it says `plan ok`, as for a source without the file (the
    control, which passes on main too). On main `plan` ended `REFUSED
    git-failed: git rev-list --count <id> ... ambiguous argument`, exit 2,
    and wrote no plan."""
    source = make_source_repo(tmp_path / "Thing")
    tip = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    if noted:
        (source / tip).write_text("a note under the tip's own id\n",
                                  encoding="utf-8")
    plan = tmp_path / "adoption-plan.yaml"

    written = write_plan(source, plan, project=PROJECT)

    assert written.returncode == 0, said(written)
    assert "ambiguous argument" not in written.stderr, said(written)
    assert f"@ {tip[:12]}" in written.stdout, said(written)
    assert "3 commits" in written.stdout, said(written)
    assert plan.is_file()
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--work-dir", str(tmp_path / "work"))
    assert checked.returncode == 0, said(checked)
    assert "ambiguous argument" not in checked.stderr, said(checked)
    assert "plan ok" in checked.stdout, said(checked)
