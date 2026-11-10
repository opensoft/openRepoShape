# SPDX-License-Identifier: Apache-2.0
"""The assembly-root template's `make bootstrap`, and what adopt says of it
(#1132: RV1105's and RV1121's follow-ups, as they stand on main).

  * THE TEMPLATE gave `make bootstrap` with no caveat: `AGENTS-shape.md`'s
    "Work from here" paragraph and its five-commands table, and
    `README.md`'s Get started and parking steps. GNU make reads the first
    it finds of `GNUmakefile`, `makefile` and `Makefile`, and only that one,
    so at the root of an adoption that kept a `GNUmakefile` or a `makefile`
    it reads the source's file, and `make bootstrap` there finds no rule
    (item 1). Each now says what to run there: `python3
    scripts/bootstrap.py`, which is what the shape's `make bootstrap` runs.
  * A KEPT DIRECTORY named `GNUmakefile/` or `makefile/` is what GNU make
    finds first all the same, and it stops there, `GNUmakefile: Is a
    directory.  Stop.`, exit 2, for every target (item 2, RV1121's NIT-1).
    The `CONTRACTS_DIR` line said `make` exports the variable "only once
    `GNUmakefile` does", and NEXT printed `make bootstrap`, or, beside a kept
    `Makefile`, said the targets arrive once the two `Makefile`s are merged.
    Both now say GNU make stops there, and NEXT names `python3
    scripts/bootstrap.py`.
  * `python3` HAS NO WINDOWS WORD (item 3, RV1121's NIT-2): the template's
    `scripts/bootstrap.py` says "python3 scripts/bootstrap.py (python on
    Windows)", and every sentence that names that command for a person to
    run now does too (`BOOTSTRAP_COMMAND`).
  * THE SCRIPT-ASIDE TAIL said that, until both merges are made, neither
    `make bootstrap` nor `python3 scripts/bootstrap.py` runs the shape's
    bootstrap. The script's merge alone lets the second run it (#1105's
    second review, NIT-2), which the rows below measure.

The tests that run `execute` need `git filter-repo` and skip without it, and
the ones that run `make` skip without it. No network and no GitHub: the legs
are bare repositories on disk, and `tests/conftest.py` keeps a `gh` guard
first on PATH.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, load_without_bytecode,
                      make_source_repo, run_script, write_plan)
from test_adopt_contracts_dir import (EDITS, PROJECT, SPLIT_BRANCH, TREE,
                                      needs_filter_repo)
from test_adopt_e2e import local_next, next_block, pasted

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

needs_make = pytest.mark.skipif(
    shutil.which("make") is None or sys.platform == "win32",
    reason="needs GNU make and a POSIX shell")

TEMPLATE = REPO / "templates" / "assembly-root"


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_make_bootstrap_followups")


def flowed(text: str) -> str:
    """`text` with each run of white space one space: a paragraph as it
    reads, however it is wrapped."""
    return " ".join(text.split())


def paragraph_after(text: str, opening: str) -> str:
    """The paragraph of `text` that opens with `opening`, flowed."""
    (found,) = [block for block in re.split(r"\n\s*\n", text)
                if block.startswith(opening)]
    return flowed(found)


#: The command, as the template's own `scripts/bootstrap.py` names it.
COMMAND = "`python3 scripts/bootstrap.py` (`python` on Windows)"
#: What the template now says where `make` reads another file first.
CAVEAT = ("where the root keeps a `GNUmakefile` or a `makefile`, which GNU "
          f"make reads before `Makefile`, run {COMMAND}, which is what the "
          "shape's `make bootstrap` runs.")


# --- the template (item 1) ---------------------------------------------------

def test_the_command_is_the_one_the_templates_makefile_runs():
    """What the sentences call the shape's `make bootstrap` is the
    template's own recipe, and the Windows word is its script's own."""
    makefile = (TEMPLATE / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"(?m)^PYTHON \?= python3$", makefile), makefile
    assert re.search(r"(?m)^bootstrap:\n\t\$\(PYTHON\) scripts/bootstrap\.py$",
                     makefile), makefile
    script = (TEMPLATE / "scripts" / "bootstrap.py").read_text(
        encoding="utf-8")
    assert "# or: python3 scripts/bootstrap.py (python on Windows)" in script
    assert shape_materialize.BOOTSTRAP_COMMAND == COMMAND
    assert COMMAND.replace("`", "") == \
        "python3 scripts/bootstrap.py (python on Windows)"


def test_agents_shape_says_what_to_run_where_make_reads_another_file():
    """The "Work from here" paragraph, which every adopted project pins."""
    said = paragraph_after(
        (TEMPLATE / "AGENTS-shape.md").read_text(encoding="utf-8"),
        "**Work from here, not from a leg clone.**")
    assert said.endswith(
        "`git clone --recurse-submodules` this repository and run `make "
        f"bootstrap`; {CAVEAT}"), said


def test_agents_shape_says_the_five_commands_are_the_shapes_targets():
    """The sentence after the five-commands table. It pointed "(above)" at
    a Makefile that includes another, which nothing above it names (#1207's
    review, NIT-1)."""
    text = (TEMPLATE / "AGENTS-shape.md").read_text(encoding="utf-8")
    table = text.index("make resume      recreate the parked features here")
    after = text[text.index("```", table) + 3:].lstrip("\n")
    assert flowed(after.split("\n\n", 1)[0]) == (
        "They are the shape's Makefile's targets, so `make` at the root "
        "reaches them only where the file it reads first holds them, or "
        "includes a Makefile that does; `python3 scripts/bootstrap.py` "
        "(`python` on Windows) is what `make bootstrap` runs.")


def test_the_readme_says_it_once_for_each_make_target_below():
    """README.md's Get started: the sentence comes after its first `make
    bootstrap` and before the parking steps' one, which "below" names, and
    it says the parking steps' own targets, `make park` and `make resume`,
    work there only where the file GNU make reads first holds them: they
    are the shape's targets, and no command stands in for them (#1207's
    review, NIT-2)."""
    text = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    sentence = (
        "Where this root keeps a `GNUmakefile` or a `makefile`, which GNU "
        f"make reads before `Makefile`, run {COMMAND} instead, here and "
        "below: it is what the shape's `make bootstrap` runs. There, `make "
        "park` and `make resume` below work only where that file holds them, "
        "or includes a Makefile that does.")
    flat = flowed(text)
    assert sentence in flat
    at = flat.index(sentence)
    commands = [found.start() for found in
                re.finditer(re.escape("make bootstrap"), flat)]
    assert commands[0] < at, commands
    assert flat.index("cd {{PROJECT}} && make bootstrap && make resume") > at
    assert flat.index("make park # before you leave this workstation") > at


@needs_make
@pytest.mark.parametrize("kept, said", [
    pytest.param({}, "", id="shapes-makefile-only"),
    pytest.param({"GNUmakefile": "build:\n\t@echo the source's\n"},
                 "No rule to make target 'bootstrap'", id="GNUmakefile"),
    pytest.param({"makefile": "build:\n\t@echo the source's\n"},
                 "No rule to make target 'bootstrap'", id="makefile"),
    pytest.param({"GNUmakefile/rules.mk": "build:\n"},
                 "GNUmakefile: Is a directory.", id="GNUmakefile-directory"),
])
def test_make_reads_the_template_makefile_only_where_nothing_comes_first(
        tmp_path, kept, said):
    """The caveat, and the measurement it rests on, with the template's
    own `Makefile` at the root: `make -n bootstrap` prints the command the
    caveat names where nothing comes before it, and exits 2 where the root
    keeps a `GNUmakefile` or a `makefile`, file or directory."""
    assert CAVEAT in flowed(
        (TEMPLATE / "AGENTS-shape.md").read_text(encoding="utf-8"))
    (tmp_path / "Makefile").write_bytes((TEMPLATE / "Makefile").read_bytes())
    for path, text in kept.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    made = subprocess.run(["make", "-n", "bootstrap"], cwd=str(tmp_path),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    if not said:
        assert made.returncode == 0, made.stderr
        assert made.stdout.strip() == "python3 scripts/bootstrap.py"
    else:
        assert made.returncode == 2, made.stdout + made.stderr
        assert said in made.stderr, made.stderr


# --- the file GNU make finds first, file or directory (item 2) ---------------

@pytest.mark.parametrize("kept, first", [
    pytest.param((), None, id="none"),
    pytest.param(("Makefile",), None, id="Makefile"),
    pytest.param(("GNUmakefile",), "GNUmakefile", id="GNUmakefile"),
    pytest.param(("makefile",), "makefile", id="makefile"),
    pytest.param(("GNUmakefile/",), "GNUmakefile/", id="GNUmakefile-dir"),
    pytest.param(("makefile/",), "makefile/", id="makefile-dir"),
    pytest.param(("Makefile", "makefile/"), "makefile/",
                 id="Makefile+makefile-dir"),
    pytest.param(("makefile/", "GNUmakefile"), "GNUmakefile",
                 id="makefile-dir+GNUmakefile"),
    pytest.param(("GNUmakefile/", "makefile"), "GNUmakefile/",
                 id="GNUmakefile-dir+makefile"),
    pytest.param(("src/GNUmakefile", "docs/makefile/"), None,
                 id="below-the-root"),
])
def test_the_name_make_finds_first_says_whether_it_is_a_directory(
        adopter, kept, first):
    """GNU make's order, asked of the root's own paths as `_root_keeps`
    asks them, with a `/` for a directory: make 4.3 stops at the first of
    the names it finds, file or directory."""
    assert adopter._make_reads_first(set(kept)) == first


def stops(name: str, reach: str) -> str:
    """The clause for a kept DIRECTORY `name/`."""
    return (f"GNU make at the root stops at the source's directory "
            f"`{name}/`, the first of `GNUmakefile`, `makefile` and "
            f"`Makefile` it finds (`{name}: Is a directory.`), so {reach} "
            "only once the root keeps no directory of that name")


EXPORTS = "`make` there exports `CONTRACTS_DIR`"


@pytest.mark.parametrize("kept, joint, name", [
    pytest.param(("GNUmakefile/",), ", but", "GNUmakefile",
                 id="GNUmakefile-dir"),
    pytest.param(("Makefile", "GNUmakefile/"), "; and", "GNUmakefile",
                 id="Makefile+GNUmakefile-dir"),
    pytest.param(("Makefile", "makefile/"), "; and", "makefile",
                 id="Makefile+makefile-dir"),
    pytest.param(("makefile/",), "; and", "makefile", id="makefile-dir"),
])
def test_the_contracts_dir_line_says_make_stops_at_a_kept_directory(
        adopter, kept, joint, name):
    """No `does` is said of a directory: the line says GNU make stops at
    it, in make's own words."""
    line = adopter._makefile_follow_up(set(kept))
    assert line.endswith(f"{joint} {stops(name, EXPORTS)}"), line
    assert f"only once `{name}` does" not in line


#: What NEXT's NOTE says reaches `make` where the root keeps such a name.
RUN_THERE = "`make bootstrap` and the shape's other make targets run there"
#: How the NOTE ends there.
RUNS = (f"; {COMMAND} is what the shape's `make bootstrap` runs.")


def next_said(adopter, capsys, collisions, surviving=None) -> str:
    """What `_next_steps` prints, given the root's paths where `surviving`
    is not None."""
    if surviving is None:
        adopter._next_steps({"assembly": PROJECT}, collisions)
    else:
        adopter._next_steps({"assembly": PROJECT}, collisions,
                            surviving=surviving)
    return capsys.readouterr().out


HEAD = (f"\nNEXT: review the pull request on {PROJECT}, then\n"
        f"    git clone --recurse-submodules <{PROJECT} url>\n")


@pytest.mark.parametrize("name", ["GNUmakefile", "makefile"])
def test_next_names_python3_where_a_kept_directory_stops_make(
        adopter, capsys, name):
    """`make bootstrap` exits 2 at that root whatever is merged, so NEXT
    names the command it runs, and says why."""
    assert next_said(adopter, capsys, [], [f"{name}/", "src/"]) == (
        f"{HEAD}    python3 scripts/bootstrap.py\n"
        "NOTE the shape's Makefile is the root's `Makefile`, but "
        f"{stops(name, RUN_THERE)}{RUNS}\n")


#: Beside a kept `Makefile`, what reaches `make` once the directory is gone.
MERGED = f"{RUN_THERE} once the follow-up merges the two, and"


@pytest.mark.parametrize("name", ["GNUmakefile", "makefile"])
def test_next_beside_a_kept_makefile_says_the_merge_is_not_enough(
        adopter, capsys, name):
    """#480's NOTE said the targets arrive once the two `Makefile`s are
    merged; beside a kept `GNUmakefile/` they do not. Nor once the
    directory alone is gone, for the root's `Makefile` is the source's own
    until the merge: the NOTE says both (#1207's review, NIT-3)."""
    said = next_said(adopter, capsys, [("Makefile", "shape/Makefile")],
                     ["Makefile", f"{name}/"])
    assert said == (
        f"{HEAD}    python3 scripts/bootstrap.py\n"
        "NOTE the root keeps its own Makefile and the shape's is "
        f"shape/Makefile, and {stops(name, MERGED)}{RUNS}\n")
    assert "arrive only once the follow-up merges the two" not in said


def test_next_after_the_merges_names_python3_where_a_directory_stops_make(
        adopter, capsys):
    """Where the script went aside too, the command named after the merges
    is the one that runs, and not `make bootstrap`."""
    said = next_said(adopter, capsys, [
        ("Makefile", "shape/Makefile"),
        ("scripts/bootstrap.py", "shape/scripts/bootstrap.py")],
        ["Makefile", "scripts/", "GNUmakefile/"])
    assert said == (
        f"{HEAD}NOTE the root keeps its own Makefile and "
        "scripts/bootstrap.py, and the shape's are shape/Makefile and "
        "shape/scripts/bootstrap.py, "
        "so neither `make bootstrap` nor `python3 scripts/bootstrap.py` runs "
        "the shape's bootstrap yet: merge shape/Makefile into Makefile and "
        "shape/scripts/bootstrap.py into scripts/bootstrap.py first, and "
        f"then run {COMMAND}; {stops('GNUmakefile', RUN_THERE)}.\n")


def test_next_after_the_script_merge_names_python3_where_make_stops(
        adopter, capsys):
    """Where only the script went aside, the shape's `Makefile` is the
    root's, and still the command named after the merge is the one that
    runs, and not `make bootstrap` (#1207's review, SHOULD-1)."""
    said = next_said(adopter, capsys,
                     [("scripts/bootstrap.py", "shape/scripts/bootstrap.py")],
                     ["scripts/", "GNUmakefile/"])
    assert said == (
        f"{HEAD}NOTE the root keeps its own scripts/bootstrap.py, and the "
        "shape's is shape/scripts/bootstrap.py, so neither `make bootstrap` "
        "nor `python3 scripts/bootstrap.py` runs the shape's bootstrap yet: "
        "merge shape/scripts/bootstrap.py into scripts/bootstrap.py first, "
        f"and then run {COMMAND}; {stops('GNUmakefile', RUN_THERE)}.\n")


# --- `python` on Windows (item 3) --------------------------------------------

def test_the_480_note_names_python_on_windows(adopter, capsys):
    """A root that kept only its own `Makefile`: the command line is the
    one pasted as printed, and the NOTE names the Windows interpreter."""
    note = (f"{HEAD}    python3 scripts/bootstrap.py\n"
            "NOTE the root keeps its own Makefile and the shape's is "
            "shape/Makefile, so `make bootstrap` and the shape's other make "
            "targets arrive only once the follow-up merges the two; "
            f"{COMMAND} is what `make bootstrap` runs.\n")
    aside = [("Makefile", "shape/Makefile")]
    assert next_said(adopter, capsys, aside) == note
    assert next_said(adopter, capsys, aside, ["Makefile"]) == note


def test_the_collision_follow_up_names_python_on_windows():
    line = shape_materialize.collision_follow_up(
        "Makefile", "shape/Makefile", {"Makefile": "shape/Makefile"})
    assert line.endswith(f"; until then {COMMAND} is what `make bootstrap` "
                         "runs"), line


# --- the script-aside tail (#1105's second review, NIT-2) --------------------

TAIL = (f"so {COMMAND} runs the shape's bootstrap once the script is merged, "
        "and `make bootstrap` once both merges are made")


def test_the_script_aside_tail_says_what_each_merge_lets_run():
    line = shape_materialize.collision_follow_up(
        "Makefile", "shape/Makefile",
        {"Makefile": "shape/Makefile",
         "scripts/bootstrap.py": "shape/scripts/bootstrap.py"})
    assert line.endswith(
        "arrive only with that merge, and the root's scripts/bootstrap.py is "
        "the source's own until shape/scripts/bootstrap.py is merged into it "
        f"as well, {TAIL}"), line
    assert "before both merges are made" not in line


@needs_make
def test_the_script_merge_alone_lets_python3_run_the_shapes_bootstrap(
        tmp_path):
    """The tail, and the measurement it rests on, with the template's own
    `Makefile` as the shape's copy: in a root that keeps its own `Makefile` and
    `scripts/bootstrap.py`, the script's merge alone makes `python3
    scripts/bootstrap.py` run the shape's bootstrap while `make bootstrap`
    still exits 2, and both merges make `make bootstrap` run it."""
    root = tmp_path / "root"
    (root / "shape" / "scripts").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "Makefile").write_text("build:\n\t@echo the source's build\n",
                                   encoding="utf-8")
    shapes = (TEMPLATE / "Makefile").read_text(encoding="utf-8")
    (root / "shape" / "Makefile").write_text(shapes, encoding="utf-8")
    (root / "scripts" / "bootstrap.py").write_text(
        "print('SOURCE-BOOT')\n", encoding="utf-8")
    (root / "shape" / "scripts" / "bootstrap.py").write_text(
        "print('SHAPE-BOOT')\n", encoding="utf-8")

    def python3() -> str:
        ran = subprocess.run([sys.executable, "scripts/bootstrap.py"],
                             cwd=str(root), capture_output=True, text=True,
                             check=True)
        return ran.stdout.strip()

    def make() -> subprocess.CompletedProcess:
        return subprocess.run(["make", "-s", "bootstrap",
                               f"PYTHON={sys.executable}"], cwd=str(root),
                              capture_output=True, text=True, check=False)

    assert python3() == "SOURCE-BOOT"
    # The script's merge alone.
    (root / "scripts" / "bootstrap.py").write_text(
        (root / "shape" / "scripts" / "bootstrap.py").read_text(
            encoding="utf-8"), encoding="utf-8")
    assert python3() == "SHAPE-BOOT"
    alone = make()
    assert alone.returncode == 2, alone.stdout + alone.stderr
    assert "No rule to make target 'bootstrap'" in alone.stderr
    # And the Makefile's.
    with (root / "Makefile").open("a", encoding="utf-8") as handle:
        handle.write(shapes)
    both = make()
    assert both.returncode == 0, both.stdout + both.stderr
    assert both.stdout.strip() == "SHAPE-BOOT"
    # And the follow-up says what each merge lets run.
    assert shape_materialize.collision_follow_up(
        "Makefile", "shape/Makefile",
        {"Makefile": "shape/Makefile",
         "scripts/bootstrap.py": "shape/scripts/bootstrap.py"}).endswith(TAIL)


# --- real adoptions of a source with a `GNUmakefile/` directory --------------

#: A rule above the shipped ones (the first match wins) that sends a
#: `GNUmakefile/` directory to the root, which no shipped rule does: there
#: `plan` asks, and its follow-ups are written before the answer.
ROOT_RULE = ("rules:\n"
             "  - id: test-gnumakefile-directory\n"
             "    paths:\n"
             "      - \"GNUmakefile/**\"\n"
             "    leg: root\n"
             "    review: false\n"
             "    reason: The source's make rules stay in the root.\n")


def policy_keeping_the_directory(base: Path) -> Path:
    shipped = (REPO / "contracts" / "path-classification.yaml").read_text(
        encoding="utf-8")
    assert shipped.count("\nrules:\n") == 1
    policy = base / "policy.yaml"
    policy.write_text(shipped.replace("\nrules:\n", "\n" + ROOT_RULE, 1),
                      encoding="utf-8")
    return policy


def answered(plan: Path, path: str, leg: str) -> None:
    """The plan's question for `path` answered `leg`, LF as `plan` wrote
    it."""
    text = plan.read_text(encoding="utf-8")
    asked = re.search(rf"(?m)^  - path: {re.escape(path)}\n    leg: null\n",
                      text)
    assert asked, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(asked.group(0), (
            f"  - path: {path}\n    leg: {leg}\n"
            f"    resolution: \"the source's make rules go to the {leg}\"\n"),
            1))


@needs_filter_repo
@needs_make
@pytest.mark.parametrize("by_policy", [
    pytest.param(True, id="a-rule-keeps-it"),
    pytest.param(False, id="answered-root"),
])
def test_an_adoption_keeping_a_gnumakefile_directory(tmp_path, by_policy):
    """A source with a `GNUmakefile/` directory, kept in the root by a
    `--path-policy` rule or by the answer to `plan`'s question. `execute`'s
    NEXT, read from the plan as it stands, names `python3
    scripts/bootstrap.py` and says GNU make stops there; in the clone NEXT's
    own clone line makes, `make -n bootstrap` stops at the directory, and
    the printed command, run with this test's interpreter, exits 0. Where
    the rule kept it, `plan` wrote the `CONTRACTS_DIR` line that says so,
    `check` prints it and the split commit's message carries it. (Where the
    question was answered, that line was written before the answer and does
    not name the directory: #1132's item 5, its own issue.)"""
    source = make_source_repo(
        tmp_path / "Thing",
        {**TREE, "GNUmakefile/rules.mk": "build:\n\t@echo source build\n"},
        edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    extra = (("--path-policy", str(policy_keeping_the_directory(tmp_path)))
             if by_policy else ())
    written = write_plan(source, plan, project=PROJECT, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    if not by_policy:
        answered(plan, "GNUmakefile/", "root")
    (line,) = [str(item) for item in load_yaml(plan)["follow_ups"]
               if "wires `CONTRACTS_DIR`" in str(item)]
    if by_policy:
        assert line.endswith(f", but {stops('GNUmakefile', EXPORTS)}"), line
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert f"  follow-up: {line}" in checked.stdout

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 0, result.stderr + result.stdout
    said = next_block(result.stdout)
    assert said == [
        *local_next(source), "    python3 scripts/bootstrap.py",
        "NOTE the shape's Makefile is the root's `Makefile`, but "
        f"{stops('GNUmakefile', RUN_THERE)}{RUNS}"], result.stdout
    message = " ".join(git("log", "-1", "--format=%B", SPLIT_BRANCH,
                           cwd=source).stdout.split())
    assert line in message
    here = tmp_path / "here"
    here.mkdir()
    cloned = pasted(said[1], here, tmp_path / "remotes")
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    clone = here / source.name
    assert (clone / "GNUmakefile" / "rules.mk").is_file()
    made = subprocess.run(["make", "-n", "bootstrap"], cwd=str(clone),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    assert made.returncode == 2, made.stdout + made.stderr
    assert "GNUmakefile: Is a directory." in made.stderr
    ran = subprocess.run([sys.executable, *said[2].split()[1:]],
                         cwd=str(clone), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr


@needs_filter_repo
@needs_make
def test_an_adoption_sending_a_gnumakefile_directory_to_a_leg(tmp_path):
    """The same source, with `plan`'s question for `GNUmakefile/` answered
    `code`: the directory goes to the code leg, the root keeps none, and
    NEXT names `make bootstrap`, which runs in the clone NEXT's own clone
    line makes. NEXT reads only the paths the plan sends to the ROOT: given
    every leg's paths, it said GNU make stops at a directory the root does
    not hold (#1207's review, NIT-4)."""
    source = make_source_repo(
        tmp_path / "Thing",
        {**TREE, "GNUmakefile/rules.mk": "build:\n\t@echo source build\n"},
        edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    answered(plan, "GNUmakefile/", "code")

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 0, result.stderr + result.stdout
    said = next_block(result.stdout)
    assert said == [*local_next(source), "    make bootstrap"], result.stdout
    here = tmp_path / "here"
    here.mkdir()
    cloned = pasted(said[1], here, tmp_path / "remotes")
    assert cloned.returncode == 0, cloned.stdout + cloned.stderr
    clone = here / source.name
    assert (clone / "code" / "GNUmakefile" / "rules.mk").is_file()
    assert not (clone / "GNUmakefile").exists()
    ran = subprocess.run(["make", "-s", *said[2].split()[1:],
                          f"PYTHON={sys.executable}"], cwd=str(clone),
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", check=False)
    assert ran.returncode == 0, ran.stdout + ran.stderr
