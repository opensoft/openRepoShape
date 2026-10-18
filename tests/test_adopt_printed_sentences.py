# SPDX-License-Identifier: Apache-2.0
"""Five sentences `adopt-project.py` prints say what the run does (#906).

Lane 3's triage of #457 at the v1.1.1 release commit found five lines that
said what the run does not do:

* L2-72. The Makefile follow-up said "the root Makefile wires `CONTRACTS_DIR`"
  where the source keeps a root `Makefile` of its own. Then the shape's, with
  the block, is written beside it as `shape/Makefile`, and `make
  contracts-dir` at the root has no rule until the two are merged. It says
  the block waits in `shape/Makefile` there, as #634 words it for the pinned
  `AGENTS-shape.md`.
* L2-73. `check`'s `mount the legs at X/ and Y/` and the split message's
  `mounted back here at X/ and Y/` ended with a ready path only where the
  spec leg holds `contracts/`, so a code file that names `specs/` got the
  key-form line and no path, where v1.0.1 printed `../spec/specs/` (v1.1.0
  already printed none: #600 took the path out of the follow-up). The spec
  leg's own path from the code leg is printed wherever the plan holds a
  read-across follow-up.
* L1-91. `plan-file-reencoded` said `execute` "would stop there, after the
  leg repositories exist", where `there` was the step git refuses. For `*
  working-tree-encoding=UTF-16LE` with `.gitattributes` exempted `execute`
  stops earlier, mounting the legs, on the `.gitmodules` it writes, and for a
  seeded leg, seeding it. The finding says where `execute` stops: measured
  below with the check that refuses it patched out.
* L1-93. A docstring, and `shape_materialize.py`'s printed follow-up, said
  "a path names no attribute", which holds only for a link target with no
  space, tab or carriage return: git reads the target as one line of rules.
* L1-75. Under `--local-remote-dir`, WHAT WILL HAPPEN printed `create
  <Project>-spec and <Project>-code (private)`, though a bare repository has
  no visibility.

The tests that run `execute` need `git filter-repo` and skip without it. No
network and no GitHub: the legs are bare repositories on disk, and
`tests/conftest.py` keeps a `gh` guard first on PATH.
"""

from __future__ import annotations

import posixpath
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, REPO, clone_just_pushed, cloned_just_pushed,
                      findings, git, load_without_bytecode, make_source_repo,
                      planned, run_script, write_plan)
from test_adopt_contracts_dir import (EDITS, MAKEFILE_FOLLOW_UP, MOUNTS,
                                      OWN_MAKEFILE, OWN_MAKEFILE_FOLLOW_UP,
                                      PROJECT, READER, SPLIT_BRANCH, TREE,
                                      adopt_with_legs_mounted_away,
                                      needs_filter_repo)
from test_adopt_literal_names import follow_up
from test_adopt_nested_attributes import (GITHUB_ATTRIBUTES, KEEP_GITHUB,
                                          NESTED, ROOT, ROOT_ATTRIBUTES,
                                          SOURCE, index_link)
from test_adopt_reencoded_files import (CRLF, NOTES, REQUIRED, REQUIRED_ONLY,
                                        SAFECRLF, TEXT_EOL_LF, configure,
                                        raw_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for its helpers."""
    return load_without_bytecode(ADOPT, "adopt_printed_sentences")


def split_line(output: str) -> str:
    """`check`'s one `ONE split commit ... mount the legs at X/ and Y/`
    line."""
    (line,) = [line for line in output.splitlines()
               if line.startswith("  ONE split commit")]
    return line


def entries_of(*rows: tuple) -> list:
    """Plan entries as `follow_ups_for` and `_predict_collisions` read them:
    each `(path, leg)` is a row with those two attributes."""
    return [SimpleNamespace(path=path, leg=leg) for path, leg in rows]


# --- L2-72: the Makefile follow-up beside a root Makefile --------------------

NAMES = {"assembly": PROJECT, "spec": f"{PROJECT}-spec",
         "code": f"{PROJECT}-code"}


def makefile_lines(follow_ups: list) -> list:
    return [item for item in follow_ups if "Makefile wires `CONTRACTS_DIR`"
            in item]


@pytest.mark.parametrize("makefile_leg, said", [
    pytest.param("root", OWN_MAKEFILE_FOLLOW_UP, id="the-root-keeps-it"),
    pytest.param("code", MAKEFILE_FOLLOW_UP, id="it-goes-to-the-code-leg"),
    pytest.param(None, MAKEFILE_FOLLOW_UP, id="the-source-has-none"),
])
def test_the_makefile_line_follows_the_entry_that_moves_the_shapes_copy(
        adopter, monkeypatch, makefile_leg, said):
    """The line reads the plan's entries as `_predict_collisions` does
    (`_root_keeps`): where the root keeps the source's `Makefile`, the
    shape's goes beside it under `shape/` and the block waits there; where
    it goes to a leg, or the source has none, the shape's is the root's."""
    # The read-across lines are the `git grep`'s, which this asks nothing of.
    monkeypatch.setattr(adopter, "cross_leg_references",
                        lambda source, entries: [])
    rows = [("contracts/", "spec"), ("src/", "code")]
    if makefile_leg is not None:
        rows.append(("Makefile", makefile_leg))
    entries = entries_of(*rows)
    collisions = adopter._predict_collisions(entries)
    ups = adopter.follow_ups_for(None, entries, NAMES, collisions)
    assert makefile_lines(ups) == [said]
    # One reading, two lines: the follow-up says the block waits in
    # `shape/Makefile` exactly where the collision follow-up moves it there.
    moved = [item for item in collisions
             if item.startswith("merge shape/Makefile into Makefile")]
    assert bool(moved) is (said == OWN_MAKEFILE_FOLLOW_UP)


def test_plan_says_where_a_kept_makefile_leaves_the_block(tmp_path):
    """On `50178305`, a source that keeps its own root `Makefile` got `the
    root Makefile wires `CONTRACTS_DIR` ...`, and its root wired nothing: the
    block was in `shape/Makefile`."""
    source = make_source_repo(tmp_path / "Thing",
                              {**TREE, "Makefile": OWN_MAKEFILE}, edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    follow_ups = [str(item) for item in load_yaml(plan)["follow_ups"]]
    assert makefile_lines(follow_ups) == [OWN_MAKEFILE_FOLLOW_UP]
    assert MAKEFILE_FOLLOW_UP not in follow_ups
    assert any(item.startswith("merge shape/Makefile into Makefile")
               for item in follow_ups)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert f"  follow-up: {OWN_MAKEFILE_FOLLOW_UP}" in checked.stdout


@needs_filter_repo
@pytest.mark.skipif(shutil.which("make") is None or sys.platform == "win32",
                    reason="needs make, and a POSIX `$(CURDIR)` spelling")
def test_a_kept_makefile_wires_nothing_where_the_split_message_says_so(
        tmp_path):
    """The measurement the line rests on. After a real `execute` the split
    commit's message, which is the pull request's body, holds the line that
    says the block waits in `shape/Makefile`, the root's own Makefile is the
    source's bytes, and `make contracts-dir` there has no rule while the
    same target in `shape/Makefile` prints the spec leg's `contracts/`."""
    adopted = adopt_with_legs_mounted_away(
        tmp_path, by_hand=False, tree={**TREE, "Makefile": OWN_MAKEFILE})
    message = " ".join(git("log", "-1", "--format=%B", SPLIT_BRANCH,
                           cwd=adopted["source"]).stdout.split())
    assert OWN_MAKEFILE_FOLLOW_UP in message
    assert MAKEFILE_FOLLOW_UP not in message
    assert adopted["makefile"].decode("utf-8").splitlines() == \
        OWN_MAKEFILE.splitlines()
    clone = adopted["clone"]
    at_the_root = subprocess.run(
        ["make", "--no-print-directory", "-s", "contracts-dir"],
        cwd=str(clone), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False)
    assert at_the_root.returncode != 0, at_the_root.stdout
    assert "No rule to make target 'contracts-dir'" in at_the_root.stderr
    in_the_shapes = subprocess.run(
        ["make", "--no-print-directory", "-s", "-f", "shape/Makefile",
         "contracts-dir"],
        cwd=str(clone), capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False)
    assert in_the_shapes.returncode == 0, in_the_shapes.stderr
    contracts = Path(in_the_shapes.stdout.strip())
    assert contracts.is_dir()
    assert contracts.resolve() == (clone / "legs" / "spec"
                                   / "contracts").resolve()


# --- L2-73: the spec leg's own path, beside the mounts -----------------------

#: A source whose one code file names `specs/`, which the rules send to the
#: spec leg: no `contracts/` anywhere, so the clause for it has nothing to
#: lead to, and the read-across line is the plan's only follow-up about paths.
SPECS_ONLY = {
    "README.md": "# Thing\n",
    "specs/001-feature/spec.md": "# The feature\n",
    READER: "SPEC = 'specs/001-feature/spec.md'\n",
    "tests/test_main.py": "def test_ok():\n    assert True\n",
}
READ_ACROSS_SPECS = follow_up(READER, "specs/")
READ_ACROSS_CONTRACTS = follow_up(READER, "contracts/")
#: Plan lines that say nothing is to be read across.
OTHER_FOLLOW_UPS = [
    "merge shape/README.md into README.md: the source repository already "
    "has that name, so the shape's copy was written beside it and NOTHING "
    "was overwritten",
    "CODEOWNERS in the assembly root now names paths that live in the legs; "
    "re-scope it here and add one to each leg",
    MAKEFILE_FOLLOW_UP,
]


@pytest.mark.parametrize("spec_path, code_path, across", MOUNTS)
def test_the_spec_legs_own_path_is_printed_where_the_plan_reads_across(
        adopter, spec_path, code_path, across):
    """A read-across follow-up, with no `contracts/` in the spec leg: the
    sentence that prints the mounts ends with the spec leg's own path from
    the code leg, which leads to the spec leg's mount for every layout."""
    said = adopter.contracts_from_code_leg(
        spec_path, code_path, ["specs/", "docs/"], [READ_ACROSS_SPECS])
    assert said == f", so from the code leg the spec leg is `{across}/`"
    assert posixpath.normpath(posixpath.join(code_path, across)) == spec_path


def test_both_clauses_are_said_where_the_spec_leg_holds_contracts_too(
        adopter):
    said = adopter.contracts_from_code_leg(
        "legs/spec", "impl/code", ["contracts/", "specs/"],
        [READ_ACROSS_CONTRACTS, READ_ACROSS_SPECS])
    assert said == (", so from the code leg the spec leg is "
                    "`../../legs/spec/` and the spec leg's `contracts/` is "
                    "`../../legs/spec/contracts/`")


@pytest.mark.parametrize("spec_leg_paths, follow_ups, said", [
    pytest.param(["specs/"], [], "", id="no-follow-up-no-contracts"),
    pytest.param(["specs/"], OTHER_FOLLOW_UPS, "",
                 id="follow-ups-that-read-nothing-across"),
    pytest.param(["contracts/"], OTHER_FOLLOW_UPS,
                 ", so from the code leg the spec leg's `contracts/` is "
                 "`../spec/contracts/`", id="contracts-alone-is-as-before"),
    pytest.param(["contracts/"], [READ_ACROSS_SPECS],
                 ", so from the code leg the spec leg is `../spec/` and the "
                 "spec leg's `contracts/` is `../spec/contracts/`",
                 id="both"),
])
def test_the_clauses_follow_the_plan_and_the_spec_leg(adopter, spec_leg_paths,
                                                      follow_ups, said):
    assert adopter.contracts_from_code_leg(
        "spec", "code", spec_leg_paths, follow_ups) == said


@pytest.mark.parametrize("spec_path, code_path", [
    pytest.param("spec", "spec", id="one-path-for-both"),
    pytest.param("spec", "SPEC", id="two-paths-that-differ-in-case"),
    pytest.param("../spec", "code", id="parent-segment"),
    pytest.param("spec", None, id="a-mount-that-is-not-text"),
])
def test_no_path_is_computed_from_values_that_are_not_two_mounts(
        adopter, spec_path, code_path):
    assert adopter.contracts_from_code_leg(
        spec_path, code_path, ["specs/"], [READ_ACROSS_SPECS]) == ""


def test_every_read_across_line_the_plan_writes_is_found(adopter, tmp_path):
    """`holds_a_read_across` reads the plan's own lines, so it has to find
    the two lines `plan` writes for a file that names a spec directory: the
    one for a file git found, in a real plan, and the one for a name git
    could not search for, which tells the person to look by hand."""
    source = make_source_repo(tmp_path / "Thing", SPECS_ONLY, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    follow_ups = [str(item) for item in load_yaml(plan)["follow_ups"]]
    assert [item for item in follow_ups if item == READ_ACROSS_SPECS]
    assert adopter.holds_a_read_across(follow_ups)
    by_hand = adopter._search_by_hand("specs/", "git said no")
    assert adopter.holds_a_read_across([by_hand])
    assert not adopter.holds_a_read_across(OTHER_FOLLOW_UPS)


@pytest.mark.parametrize("spec_path, code_path, across", [
    pytest.param(*row.values, id=row.id)
    for row in MOUNTS if row.id in ("defaults", "siblings-in-legs",
                                    "code-nested", "one-segment-shared")])
def test_check_prints_the_spec_legs_path_beside_the_mounts(
        tmp_path, spec_path, code_path, across):
    """On `50178305`, a code file that names `specs/` got the read-across
    line and a `mount the legs at X/ and Y/` that ended there. It ends with
    the spec leg's path from the code leg now, for every layout."""
    source = make_source_repo(tmp_path / "Thing", SPECS_ONLY, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT,
                         extra=("--spec-path", spec_path,
                                "--code-path", code_path))
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert split_line(checked.stdout).endswith(
        f"mount the legs at {spec_path}/ and {code_path}/, so from the code "
        f"leg the spec leg is `{across}/`")
    assert f"  follow-up: {READ_ACROSS_SPECS}" in checked.stdout.splitlines()


def split_message_of(adopter, follow_ups: list) -> str:
    return adopter._split_message(
        NAMES, {"spec": ["specs/"], "code": ["src/"], "drop": [],
                "root": ["README.md"]},
        {"spec": "a" * 40, "code": "b" * 40}, "spec", "code", follow_ups, [])


def test_the_split_message_prints_it_where_the_plan_reads_across(adopter):
    said = split_message_of(adopter, [READ_ACROSS_SPECS]).splitlines()[2]
    assert ("mounted back here at spec/ and code/, so from the code leg the "
            "spec leg is `../spec/`.") in said
    # With no read-across line, the sentence is the mounts alone, as before.
    bare = split_message_of(adopter, OTHER_FOLLOW_UPS).splitlines()[2]
    assert "mounted back here at spec/ and code/." in bare
    assert "`../spec/`" not in bare


@needs_filter_repo
def test_the_path_the_split_message_prints_leads_to_the_spec_leg(tmp_path):
    """End to end. The split commit's message, which is also the pull
    request's body, names the spec leg's path from the code leg, and
    followed from the code leg of a recursive clone it reaches the file the
    code names."""
    source = make_source_repo(tmp_path / "Thing", SPECS_ONLY, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout, result.stdout
    message = git("log", "-1", "--format=%B", SPLIT_BRANCH, cwd=source).stdout
    assert ("mounted back here at spec/ and code/, so from the code leg the "
            "spec leg is `../spec/`.") in message
    clone = tmp_path / PROJECT
    proc = clone_just_pushed(source, clone, branch=SPLIT_BRANCH)
    assert proc.returncode == 0, proc.stderr
    reached = (clone / "code").joinpath("..", "spec", "specs", "001-feature",
                                        "spec.md")
    assert reached.resolve().is_file()


# --- L1-91: where `execute` stops --------------------------------------------

#: What `check` says of where `execute` stops for a `git add` that is
#: refused: committing the split, which the push of its branch follows, or a
#: step before it that meets the same rule first.
STOPS_AT_THE_SPLIT = (
    "no later than committing the split, and sooner where a step before it "
    "meets the same rule: extracting or seeding a leg, or mounting the legs, "
    "where the rule reaches the `.gitmodules` it writes")
STOPS_AT_A_CLONE = "at its first clone of the source"
#: `* working-tree-encoding=UTF-16LE`, with the one file that holds the rules
#: exempted: the case #906 names, which stops mounting the legs.
ENCODED_EXCEPT_RULES = (b"* working-tree-encoding=UTF-16LE\n"
                        b".gitattributes -working-tree-encoding\n")

#: `(the source's files, plan answers, git configuration, the stop `check`
#: names, the step `execute` REFUSES at when the check is patched out)`.
STOPS = [
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: ROOT},
                 SAFECRLF, STOPS_AT_THE_SPLIT,
                 "REFUSED committing the split.", id="the-common-case"),
    pytest.param({ROOT_ATTRIBUTES: ENCODED_EXCEPT_RULES}, {}, (),
                 STOPS_AT_THE_SPLIT, "REFUSED mounting the legs.",
                 id="encoding-over-every-file-but-the-rules"),
    pytest.param({ROOT_ATTRIBUTES: f"*.txt filter={REQUIRED}\n".encode(),
                  NOTES: b"abc\n"}, {NOTES: ROOT},
                 (*REQUIRED_ONLY, (f"filter.{REQUIRED}.smudge", "false")),
                 STOPS_AT_A_CLONE, "REFUSED extracting the spec leg.",
                 id="a-checkout-git-refuses"),
    pytest.param({}, {"src/": ROOT, ".github/": ROOT},
                 (("core.autocrlf", "true"), ("core.safecrlf", "true")),
                 STOPS_AT_THE_SPLIT, "REFUSED seeding the code leg.",
                 id="a-seeded-leg-meets-the-same-config"),
]


@pytest.mark.parametrize(("files", "answers", "config", "stops", "step"),
                         STOPS)
def test_the_finding_says_where_execute_would_stop(monkeypatch, tmp_path,
                                                   files, answers, config,
                                                   stops, step):
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    ((code, detail),) = findings(plan)
    assert code == "plan-file-reencoded"
    assert ("so `execute` would stop after the leg repositories exist, "
            f"{stops}. ") in detail
    assert "would stop there" not in detail


@needs_filter_repo
@pytest.mark.parametrize(("files", "answers", "config", "stops", "step"),
                         STOPS)
def test_execute_stops_where_the_finding_says(adopter, monkeypatch, capsys,
                                              tmp_path, files, answers,
                                              config, stops, step):
    """The measurement. With `check`'s refusal patched out, `execute` runs
    on and stops at the step the finding names, after both leg repositories
    exist: committing the split for a `git add` that is refused, mounting
    the legs on the `.gitmodules` it writes where a rule reaches every file
    but the rules', seeding a leg, whose own `git add -A` meets the same
    config before the split does, and the first clone of the source,
    extracting the spec leg, for a checkout git refuses. The finding named it
    as `there` before, and `there` was the split's `git add` in all four."""
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    monkeypatch.setattr(adopter, "_refuse_what_check_finds",
                        lambda *args, **kwargs: None)
    args = Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / "remotes",
                     allow_empty_leg=["code"] if "seeding" in step else [],
                     yes=True, work_dir=tmp_path / "work")
    assert adopter.cmd_execute(args) == 2
    said = capsys.readouterr().err
    assert step in said, said
    if "mounting the legs" in step:
        assert "failed to encode '.gitmodules'" in said, said
    assert (tmp_path / "remotes" / "Northwind-spec.git").is_dir()
    assert (tmp_path / "remotes" / "Northwind-code.git").is_dir()
    # What the finding names covers where it stopped.
    named = {"committing the split": "committing the split",
             "mounting the legs": "mounting the legs",
             "extracting the spec leg": "first clone of the source",
             "seeding the code leg": "seeding a leg"}
    (where,) = [word for word in named if word in step]
    assert named[where] in stops


# --- L1-93: what a link target names -----------------------------------------

@pytest.mark.parametrize(("target", "found"), [
    pytest.param("config/attributes", False, id="a-path-with-no-separator"),
    pytest.param("docs/read me.md", False,
                 id="a-space-and-an-attribute-no-line-ending-reads"),
    pytest.param("*.yml eol=crlf", True, id="a-pattern-and-an-attribute"),
    pytest.param("*.yml\teol=crlf", True, id="a-tab-between-them"),
    pytest.param("*.yml\reol=crlf", True,
                 id="a-carriage-return-between-them"),
])
def test_a_link_target_names_an_attribute_only_with_a_separator(
        tmp_path, target, found):
    """Measured with git 2.43: a kept `.github/.gitattributes` linking to
    `config/attributes` left `.github/workflows/validate.yml` LF, and one
    linking to `*.yml eol=crlf`, or to `*.yml` and `eol=crlf` with a tab or a
    carriage return between them, wrote it CRLF: git reads the target as one
    line of rules, and a space, a tab and a carriage return all separate its
    fields. A target with a space that names no line-ending attribute
    changes nothing either."""
    source = make_source_repo(tmp_path / "Thing", tree=dict(SOURCE), edits=())
    index_link(source, GITHUB_ATTRIBUTES, target)
    got = findings(planned(source, tmp_path, KEEP_GITHUB))
    assert [code for code, _ in got] == ([NESTED] if found else []), got


@pytest.mark.parametrize(("target", "crlf"), [
    pytest.param("config/attributes", False, id="a-path-with-no-separator"),
    pytest.param("docs/read me.md", False,
                 id="a-space-and-an-attribute-no-line-ending-reads"),
    pytest.param("* eol=crlf", True, id="a-space-between-them"),
    pytest.param("*\teol=crlf", True, id="a-tab-between-them"),
    pytest.param("*\reol=crlf", True, id="a-carriage-return-between-them"),
])
def test_a_root_link_is_read_as_rules_only_with_a_separator(tmp_path, target,
                                                            crlf):
    """The measurement `_attributes_link_follow_up`'s sentence rests on.
    Measured with git 2.43: a clone of a source whose root `.gitattributes`
    links to `config/attributes` writes a text file it commits LF with LF,
    and one whose link leads to `* eol=crlf`, or to `*` and `eol=crlf` with a
    tab or a carriage return between them, writes it CRLF. The printed
    follow-up says no line-ending rule reaches the pinned copies "for a link
    to a path" for that reason, and not for every link."""
    source = make_source_repo(tmp_path / "Thing", tree={NOTES: "one\ntwo\n"},
                              edits=())
    index_link(source, ROOT_ATTRIBUTES, target)
    clone = cloned_just_pushed(source, tmp_path / "clone", recurse=False)
    written = (clone / NOTES).read_bytes()
    assert written == (b"one\r\ntwo\r\n" if crlf else b"one\ntwo\n")


def test_the_docstring_says_it_of_a_target_with_no_separator_only(adopter):
    said = " ".join(adopter._kept_nested_attributes.__doc__.split())
    assert "A target that is a path names no attribute" not in said
    assert ("A target with no space, tab or carriage return, a path, is a "
            "pattern and names no attribute, and changes nothing; one with "
            "any of them is a pattern and the attributes after it") in said


# --- L1-75: no visibility for a bare repository ------------------------------

def what_will_happen_creates(output: str) -> list[str]:
    return [line for line in output.splitlines()
            if line.startswith("  create ")]


@pytest.mark.parametrize("visibility", ["private", "public", "internal"])
def test_a_local_remote_dir_prints_no_visibility_for_a_bare_repository(
        tmp_path, visibility):
    """On `50178305`, `check --local-remote-dir` printed `create
    Northwind-spec and Northwind-code (private)`: `execute` makes both with
    `git init --bare`, which has no visibility. Against GitHub the plan's
    visibility is still the one the legs are created at."""
    source = make_source_repo(tmp_path / "Thing", TREE, edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_text(encoding="utf-8")
    assert "visibility: private\n" in text, text
    with open(plan, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("visibility: private\n",
                                  f"visibility: {visibility}\n"))
    local = run_script(ADOPT, "check", "--plan", str(plan),
                       "--local-remote-dir", str(tmp_path / "remotes"))
    assert local.returncode == 0, local.stderr + local.stdout
    assert what_will_happen_creates(local.stdout) == [
        f"  create {PROJECT}-spec and {PROJECT}-code"]
    assert f"({visibility})" not in local.stdout
    github = run_script(ADOPT, "check", "--plan", str(plan))
    assert github.returncode == 0, github.stderr + github.stdout
    assert what_will_happen_creates(github.stdout) == [
        f"  create {PROJECT}-spec and {PROJECT}-code ({visibility})"]
