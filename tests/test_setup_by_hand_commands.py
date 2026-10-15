# SPDX-License-Identifier: Apache-2.0
"""The by-hand scaffold commands the documents print are the ones setup runs (#550).

README.md's "What setup.sh does" and the handbook's "What `setup.sh` actually
runs" list "the commands that flow runs", and a reader who runs them by hand
trusts that they are. Two of them are `scaffold-project.py`: the plan, which
`setup-project.py` runs with `--dry-run`, and the real run. Both get the same
arguments from `scaffold_args`, which ALWAYS passes `--visibility` and
`--elected-by`; the documents showed the plan without them, so the plan a
reader ran could name a different elector than the real run wrote (#550).
Nothing tied the printed commands to the flow.

This is the guard. It does not read the source for the flags: it RUNS
`plan_and_confirm` and `scaffold` in process with `run` replaced by a recorder,
so what it compares is the argument list those two functions hand to the
scaffold, in the order they build it, `--dry-run` last on the plan. The
documents are held to that, after the two things a printed command does that a
list does not: a backslash continues a line, and `# ...` is a comment.

The values are the documents' own: the project `Atlas`, the visibility
`private`, the elector `Your Name`, and the organisation the documents write as
the placeholder `<your-org>`, which is stood in for by `ORG` on both sides. A
flag `setup-project.py` passes only when it is given (`--id`, `--name`,
`--local-remote-dir`) is in neither: the printed lines show the default run, and
so do the recorded ones.

One flag is on the real run alone and is left out of the printed line ON
PURPOSE: `--no-next-steps` (#538). `setup-project.py` runs the scaffold's
closing block, the `git clone`, the `cd` and `make bootstrap`, itself as its
step (7), so it tells the scaffold to leave that block out. By hand there is no
step (7): the block IS the person's next work, so the documents' lines do not
carry the flag. `what_setup_runs` asserts the flag is there, last, and that
nothing else differs from the plan's arguments, then returns the real run
without it.

Nothing here starts a process, touches git or GitHub, or reads a terminal, so
it holds on every platform; the printed commands are POSIX and are rendered
with `shlex.quote`, which is what they are written in.
"""

from __future__ import annotations

import html
import re
import shlex
import subprocess
from pathlib import Path

from conftest import REPO

from test_setup_project_py import entry_point_module

#: The organisation the documents write as a placeholder, and what stands in
#: for it on both sides of the comparison.
PLACEHOLDER = "<your-org>"
ORG = "ORG"

#: Where each document's list of commands starts. The README's is the first
#: fenced block under its heading; the handbook's is the first `<pre>` after
#: its subheading.
README_BLOCK = re.compile(
    r"^### What setup\.sh does$.*?^```sh\n(.*?)^```$", re.S | re.M)
HANDBOOK_BLOCK = re.compile(
    r"What <code>setup\.sh</code> actually runs</h4>.*?"
    r"<pre><code>(.*?)</code></pre>", re.S)

SCAFFOLD_COMMAND = "python3 scaffold-project.py"

#: What the real run carries and the printed line does not: see the module
#: docstring.
NO_NEXT_STEPS = "--no-next-steps"


def scaffold_lines(block: str) -> list[str]:
    """The `scaffold-project.py` commands in a printed block, each as one line
    with its continuations joined, its comment dropped and its whitespace
    collapsed, and the organisation placeholder replaced by `ORG`."""
    lines = []
    for line in block.replace("\\\n", " ").splitlines():
        line = " ".join(re.sub(r"\s+#.*$", "", line).split())
        if line.startswith(SCAFFOLD_COMMAND):
            lines.append(line.replace(PLACEHOLDER, ORG))
    return lines


def recorded_scaffold_runs(monkeypatch, tmp_path: Path) -> list[list[str]]:
    """The argument vectors `setup-project.py` hands `run` for the plan and the
    real run, for the documents' own values: the plan first, then the real run,
    each exactly as built, interpreter and script included."""
    module = entry_point_module()
    ran: list[list[str]] = []

    def record(argv, *args, **kwargs):
        ran.append([str(part) for part in argv])
        return subprocess.CompletedProcess(args=argv, returncode=0,
                                           stdout="", stderr="")

    monkeypatch.setattr(module, "run", record)
    opts = module.Options()
    opts.project = "Atlas"
    opts.visibility = "private"
    opts.elected_by = "Your Name"
    opts.assume_yes = True
    args = module.scaffold_args(opts, ORG)
    module.plan_and_confirm(opts, REPO, ORG, args, str(tmp_path / "Atlas"))
    module.scaffold(REPO, args)
    assert len(ran) == 2, ran
    return ran


def what_setup_runs(monkeypatch, tmp_path: Path) -> list[str]:
    """The two `scaffold-project.py` commands `setup-project.py` runs for the
    documents' own values, as `python3 scaffold-project.py <arguments>` lines:
    the plan first, then the real run.

    THE REAL RUN IS RETURNED WITHOUT `--no-next-steps` (#538), after it is
    asserted to be there. setup's step (7) clones, `cd`s and bootstraps
    itself, so it has the scaffold leave out the closing block that prints the
    same three commands, which printed in the middle of setup read as work
    left to the person. By hand there is no step (7) and that block is the
    person's next work, so the documents' lines stay without the flag, and
    this compares them with the run it would be the same as. The assertion
    keeps the exception exact: the flag is last, and the real run is otherwise
    the plan's arguments, so a flag added to one of the two alone still fails
    here."""
    plan, real = recorded_scaffold_runs(monkeypatch, tmp_path)
    assert plan[-1] == "--dry-run", plan
    assert real == [*plan[:-1], NO_NEXT_STEPS], (
        "the real run is the plan's arguments and a final "
        f"{NO_NEXT_STEPS}, nothing else:\n  {plan}\n  {real}")
    lines = []
    for argv in (plan, real[:-1]):
        assert Path(argv[1]).name == "scaffold-project.py", argv
        lines.append(" ".join([SCAFFOLD_COMMAND,
                               *(shlex.quote(part) for part in argv[2:])]))
    return lines


def assert_the_same(name: str, printed: list[str], ran: list[str]) -> None:
    """The document's `scaffold-project.py` lines are the ones setup runs, in
    order, and the failure shows both side by side."""
    assert printed == ran, (
        f"{name} prints these `scaffold-project.py` commands as the ones "
        "setup runs (the plan, then the real run):\n  "
        + "\n  ".join(printed) + "\nsetup-project.py runs these:\n  "
        + "\n  ".join(ran)
        + "\nThe plan and the real run take the same arguments from "
        "`scaffold_args`, `--visibility` and `--elected-by` included (#550).")


def test_the_readme_prints_the_commands_setup_runs(monkeypatch, tmp_path):
    text = (REPO / "README.md").read_bytes().decode("utf-8")
    found = README_BLOCK.search(text)
    assert found, "README.md has no fenced block under `### What setup.sh does`"
    assert_the_same(
        "README.md", scaffold_lines(found.group(1)),
        what_setup_runs(monkeypatch, tmp_path))


def test_the_handbook_prints_the_commands_setup_runs(monkeypatch, tmp_path):
    text = (REPO / "docs" / "handbook.html").read_bytes().decode("utf-8")
    found = HANDBOOK_BLOCK.search(text)
    assert found, ("docs/handbook.html has no code block under `What "
                   "setup.sh actually runs`")
    assert_the_same(
        "docs/handbook.html", scaffold_lines(html.unescape(found.group(1))),
        what_setup_runs(monkeypatch, tmp_path))


def test_setup_runs_the_plan_and_the_real_run_with_the_same_arguments(
        monkeypatch, tmp_path):
    recorded = recorded_scaffold_runs(monkeypatch, tmp_path)
    assert recorded[1][-1] == NO_NEXT_STEPS, recorded[1]
    assert NO_NEXT_STEPS not in recorded[0], recorded[0]
    plan, real = what_setup_runs(monkeypatch, tmp_path)
    assert plan == real + " --dry-run"
    assert "--visibility private" in real and "--elected-by 'Your Name'" in real


def test_a_printed_command_is_read_as_one_line_without_its_comment():
    block = ("git clone x\n"
             "python3 scaffold-project.py --org <your-org> --project Atlas \\\n"
             "    --visibility private --elected-by 'Your Name'   # or public\n"
             "mkdir -p y   # python3 scaffold-project.py is not here\n")
    assert scaffold_lines(block) == [
        "python3 scaffold-project.py --org ORG --project Atlas "
        "--visibility private --elected-by 'Your Name'"]


def test_a_plan_printed_without_the_flags_the_real_run_has_is_a_different_line():
    printed = scaffold_lines(
        "python3 scaffold-project.py --org <your-org> --project Atlas "
        "--dry-run\n")
    assert printed == ["python3 scaffold-project.py --org ORG --project Atlas "
                       "--dry-run"]
    assert printed[0] != ("python3 scaffold-project.py --org ORG --project "
                          "Atlas --visibility private --elected-by 'Your Name'"
                          " --dry-run")
