# SPDX-License-Identifier: Apache-2.0
"""A `.gitattributes` the plan keeps BELOW the root, over a pinned copy (#530).

#471 (PR #511) gives every pinned copy at the assembly root one line-ending
rule: a `/<copy> text eol=lf` line in the block the split appends to the
source's own root `.gitattributes`, or the shape's own `* text=auto eol=lf`
where the source keeps none. Git reads attributes for a path from the
`.gitattributes` of its own directory and of each directory above it, and a
deeper file outranks a shallower one. So a source's `.github/.gitattributes`
or `scripts/.gitattributes` that the plan keeps in the root outranks that
rule for every copy under it.

Measured on main at 2247dbff with git 2.43: `*.yml eol=crlf` there, `*
text=auto eol=crlf`, or a macro the root defines to say the same, checked
`.github/workflows/validate.yml` out with CRLF in EVERY clone, Linux's
included; `* !eol` did so in every clone that writes CRLF. Each time
`execute` printed `adoption verified` and exited 0, and the root's first
`make bootstrap` reported shape-copy-drift. `* -text` and `* binary` changed
no byte: a checkout writes a file that is not text as its blob, and the blob
is LF.

`check` now finds it as `plan-nested-attributes`, and `execute` refuses it
before any leg exists. The finding names the kept file, the copies it reaches
and the lines that keep them LF. The question is asked of git itself
(`git check-attr`), so the tests that need no `git filter-repo` run on every
CI job; the end-to-end ones adopt the remedied source, clone it the ways
Windows clones it, and read `git check-attr` on every pinned copy.

The root's OWN `.gitattributes` is the one file of the source's the split
writes into (#471), and `git add` stores what it writes there through git's
rules for that file. A blob committed CRLF under `* text eol=lf` was stored as
LF, and `execute` ended `adopt-lost` after both legs existed (lane 2's D5(a)
line on this issue). `check` now asks this machine's `git add` and finds it as
`plan-attributes-reencoded`, and `execute` refuses it before any leg exists.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, appended_to_command_scope,
                      clone_just_pushed, findings, git, make_source_repo,
                      planned, refused_before_any_leg, run_script)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402
from shape_materialize import CASE_ASIDE  # noqa: E402

#: The finding, and the code of `execute`'s refusal.
NESTED = "plan-nested-attributes"
ROOT_ATTRIBUTES = ".gitattributes"
GITHUB_ATTRIBUTES = ".github/.gitattributes"
WORKFLOWS_ATTRIBUTES = ".github/workflows/.gitattributes"
VALIDATE = ".github/workflows/validate.yml"
#: The line that keeps the workflow copy LF, written in `.github/`.
VALIDATE_LINE = "/workflows/validate.yml text eol=lf"
TEXT_AUTO = "* text=auto\n"
YML_CRLF = "*.yml eol=crlf\n"
ALL_CRLF = "* eol=crlf\n"
MINUS_TEXT = "* -text\n"
TEXT_SET = "* text\n"
#: The finding's own remedy for `.github/.gitattributes`, applied.
REMEDIED = f"{YML_CRLF}{VALIDATE_LINE}\n"
ROOT = "root"
UTF8 = "utf-8"
#: The tree git knows with no object stored: one with nothing in it.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
#: How the finding says where the copies go CRLF.
EVERYWHERE = "with CRLF line endings on every platform"
BY_CONFIG = "with CRLF line endings wherever git writes them"
#: The shape's scripts, in the pin's order, as `scripts/` holds them.
SCRIPTS = ("validate-pins.py", "validate-manifest.py", "bootstrap.py",
           "repo_shape.py", "validate-repository-naming.py")
BRANCH = "adopt/three-repo-shape"
PIN = "contracts/shape-pin.yaml"
#: Where a root `.gitattributes` that is a symlink leads.
LINKED_RULES = "config/attributes"

#: A source with nothing for the plan to ask about, and a workflow of its own
#: under `.github/workflows/`, which the policy sends to the code leg.
SOURCE = {"README.md": "# Thing\n", ".gitignore": "__pycache__/\n",
          "specs/001-feature/spec.md": "# The feature\n",
          "src/app/main.py": "print()\n",
          ".github/workflows/ci.yml": "on: [push]\n"}
#: `plan` asks about `.github/.gitattributes`; these answers keep it.
KEEP_GITHUB = {GITHUB_ATTRIBUTES: ROOT}
KEEP_BOTH = {GITHUB_ATTRIBUTES: ROOT, ".github/workflows/": ROOT}


def github(rules: str, root: str | None = TEXT_AUTO) -> dict:
    """A source's `.github/.gitattributes` holding `rules`, beside its own
    root `.gitattributes` holding `root`, or none."""
    files = {GITHUB_ATTRIBUTES: rules}
    if root is not None:
        files[ROOT_ATTRIBUTES] = root
    return files


def adoption_plan(base: Path, files: dict, answers: dict) -> Path:
    """The plan for `SOURCE` and `files`, with `answers` given."""
    source = make_source_repo(base / "Thing", tree={**SOURCE, **files},
                              edits=())
    return planned(source, base, answers)


def lines_of(names) -> list[str]:
    return [f"`/{name} text eol=lf`" for name in names]


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_nested_attributes",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# What a checkout does with a copy's LF blob, as git's `convert.c` decides it
# ---------------------------------------------------------------------------

#: `crlf text eol => what a checkout writes`, each value as `git check-attr`
#: prints it: the blob, CRLF everywhere, or what `core.autocrlf` and
#: `core.eol` say. `crlf` is the old spelling of `text`, read only where
#: `text` is unspecified. Each row was checked against real checkouts with
#: git 2.43: as configured, with `core.autocrlf=true` and with
#: `core.eol=crlf` (#530's review found three rows backwards).
CHECKOUTS = [
    "unspecified set lf => kept",
    "unspecified auto lf => kept",
    "unspecified unspecified lf => kept",
    "unspecified unset crlf => kept",
    "unset set crlf => everywhere",
    "unset unspecified crlf => kept",
    "input unspecified unspecified => kept",
    "unspecified input unset => kept",
    "input set crlf => everywhere",
    "unspecified auto crlf => everywhere",
    "set unset crlf => kept",
    "unspecified set unspecified => by config",
    "unspecified auto unset => by config",
    "unspecified unspecified unspecified => by config",
    "set unset native => kept",
    "unset set unspecified => by config",
]


@pytest.mark.parametrize("row", CHECKOUTS)
def test_what_a_checkout_writes_is_read_as_git_reads_it(adopter, row):
    values, written = row.split(" => ")
    crlf, text, eol = values.split()
    assert adopter.checked_out_as(
        {"crlf": crlf, "text": text, "eol": eol}) == written


# ---------------------------------------------------------------------------
# `check` finds it, and `execute` refuses it before any leg exists
# ---------------------------------------------------------------------------

#: Each way a kept file outranks the root's rule: what the source adds, the
#: plan's answers, how the finding names the copies, the lines it gives, and
#: where it says the copies go CRLF.
OUTRANKED = [
    pytest.param(github(YML_CRLF), KEEP_GITHUB, f"`{VALIDATE}`",
                 [f"`{VALIDATE_LINE}`"], EVERYWHERE, id="eol-crlf"),
    pytest.param(github("* text=auto eol=crlf\n"), KEEP_GITHUB,
                 f"`{VALIDATE}`", [f"`{VALIDATE_LINE}`"], EVERYWHERE,
                 id="text-auto-eol-crlf"),
    pytest.param(github("*.yml winfile\n",
                        "[attr]winfile text eol=crlf\n" + TEXT_AUTO),
                 KEEP_GITHUB, f"`{VALIDATE}`", [f"`{VALIDATE_LINE}`"],
                 EVERYWHERE, id="a-macro-the-root-defines"),
    pytest.param(github("* !eol\n"), KEEP_GITHUB, f"`{VALIDATE}`",
                 [f"`{VALIDATE_LINE}`"], BY_CONFIG, id="eol-unspecified"),
    pytest.param(github(YML_CRLF, None), KEEP_GITHUB, f"`{VALIDATE}`",
                 [f"`{VALIDATE_LINE}`"], EVERYWHERE,
                 id="no-root-attributes"),
    pytest.param(github("*.yml -crlf eol=crlf\n"), KEEP_GITHUB,
                 f"`{VALIDATE}`", [f"`{VALIDATE_LINE}`"], EVERYWHERE,
                 id="crlf-unset-beside-the-roots-text"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_AUTO,
                  "scripts/.gitattributes": "*.py eol=crlf\n",
                  "scripts/run.sh": "echo hi\n"}, {"scripts/": ROOT},
                 "`scripts/validate-pins.py` and 4 more", lines_of(SCRIPTS),
                 EVERYWHERE, id="a-kept-directory"),
]


@pytest.mark.parametrize(("files", "answers", "copies", "lines", "where"),
                         OUTRANKED)
def test_check_names_the_kept_file_the_copies_and_the_lines(
        tmp_path, files, answers, copies, lines, where):
    found = findings(adoption_plan(tmp_path, files, answers))
    assert [code for code, _ in found] == [NESTED], found
    detail = found[0][1]
    kept = next(path for path in files if path.endswith(f"/{ROOT_ATTRIBUTES}"))
    assert detail.startswith(
        f"the plan keeps `{kept}` in the assembly root"), detail
    assert f"the pinned cop{'ies' if len(lines) > 1 else 'y'} {copies}:" \
        in detail
    assert where in detail
    assert "so its rules outrank the root's line-ending rule for the pinned " \
        "cop" in detail
    assert "shape-copy-drift" in detail
    for line in lines:
        assert line in detail, line


def test_execute_refuses_it_before_any_leg_exists(adopter, monkeypatch,
                                                 tmp_path):
    plan = adoption_plan(tmp_path, github(YML_CRLF), KEEP_GITHUB)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == NESTED


def index_link(source: Path, link: str, target: str) -> None:
    """Commit `link -> target` in `source`'s tree only, as Git for Windows'
    `core.symlinks=false` leaves it: no symlink on the disk, so no privilege
    is needed, and `plan` reads the tree."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(source), input=target.encode(UTF8),
                          capture_output=True, check=True)
    git("update-index", "--add", "--cacheinfo",
        f"120000,{blob.stdout.decode('ascii').strip()},{link}", cwd=source)
    git("commit", "-qm", f"Link {link}", cwd=source)


def test_a_root_attributes_symlink_still_has_its_copies_outranked(tmp_path):
    """The root's `.gitattributes` is a symlink, which the split appends
    nothing to (#471's follow-up says so and lists the lines a regular file
    needs). The kept `.github/.gitattributes` is asked against the rule that
    follow-up asks for, so its own `eol=crlf`, which writes CRLF on every
    platform, is still found."""
    source = make_source_repo(
        tmp_path / "Thing", tree={**SOURCE, **github(YML_CRLF, None),
                                  LINKED_RULES: TEXT_AUTO}, edits=())
    index_link(source, ROOT_ATTRIBUTES, LINKED_RULES)
    found = findings(planned(source, tmp_path,
                             {**KEEP_GITHUB, "config/": ROOT}))
    assert [code for code, _ in found] == [NESTED], found
    assert f"`{VALIDATE_LINE}`" in found[0][1]
    assert ("so its rules outrank the line-ending rule #471's follow-up asks "
            "a regular root `.gitattributes` to hold (the root's is a "
            "symlink, which gives none) for the pinned copy") in found[0][1]


def test_a_kept_symlink_is_read_as_its_target_text(tmp_path):
    """A checkout reads a `.gitattributes` from the index first, and there a
    symlink's blob is its target: git 2.43 checked the copy out with CRLF
    under a kept `.github/.gitattributes` linking to `*.yml eol=crlf`. The
    remedy says to replace the link, which nothing can end."""
    source = make_source_repo(tmp_path / "Thing", tree=dict(SOURCE),
                              edits=())
    index_link(source, GITHUB_ATTRIBUTES, YML_CRLF.strip())
    found = findings(planned(source, tmp_path, KEEP_GITHUB))
    assert [code for code, _ in found] == [NESTED], found
    assert (f"or replace the symlink `{GITHUB_ATTRIBUTES}` in the source with "
            f"a regular file that ends with the line `{VALIDATE_LINE}`, "
            "commit") in found[0][1]


@pytest.mark.parametrize(("root", "named"), [
    pytest.param(b"* text=auto eol=lf\n", 1, id="the-root-keeps-it-lf"),
    pytest.param(TEXT_AUTO.encode(UTF8), 0, id="the-root-leaves-it-crlf")])
def test_only_a_copy_the_roots_own_files_keep_lf_is_outranked(adopter, root,
                                                              named):
    """One finding per cause: a copy the root's own files already leave to
    the configuration -- a symlink the root keeps leads it where #471's
    block, which names it by its pinned path, does not reach -- is not the
    kept nested file's to answer for, whatever that file says."""
    row = (GITHUB_ATTRIBUTES, "100644", "0" * 40, GITHUB_ATTRIBUTES)
    with adopter._AttributesProbe() as asked:
        found = adopter._outranking(
            asked, False, [VALIDATE], {ROOT_ATTRIBUTES: root},
            {GITHUB_ATTRIBUTES: (row, YML_CRLF.encode(UTF8))})
    assert len(found) == named, found


def test_a_kept_shape_attributes_file_is_the_copys_finding_alone(tmp_path):
    """The source keeps its own `.gitattributes` and `shape/.gitattributes`
    in the root, where the shape writes its copy of the first:
    `plan-root-blocks-shape-copy` names that (#262), and the kept file is
    not asked about the copies under `shape/` as well."""
    files = {ROOT_ATTRIBUTES: TEXT_AUTO, "shape/.gitattributes": YML_CRLF}
    found = findings(adoption_plan(tmp_path, files, {"shape/": ROOT}))
    assert [code for code, _ in found] == ["plan-root-blocks-shape-copy"], \
        found


#: Kept files that leave every copy as its pin records it: not text, text
#: with the root's `eol`, another path, the finding's own remedy, a file a
#: leg takes, and a rule a deeper kept file restores.
KEPT_LF = [
    pytest.param(github(MINUS_TEXT), KEEP_GITHUB, id="minus-text"),
    pytest.param(github("* binary\n"), KEEP_GITHUB, id="binary"),
    pytest.param(github(TEXT_SET), KEEP_GITHUB, id="text-alone"),
    pytest.param(github("* -crlf\n* crlf=input\n"), KEEP_GITHUB,
                 id="the-old-crlf-spelling"),
    pytest.param(github("*.png binary\n"), KEEP_GITHUB, id="another-path"),
    pytest.param(github("*.yml crlf -text eol=crlf\n"), KEEP_GITHUB,
                 id="crlf-set-under-minus-text"),
    pytest.param(github(REMEDIED), KEEP_GITHUB, id="the-remedy"),
    pytest.param(github(YML_CRLF), {GITHUB_ATTRIBUTES: "code"},
                 id="sent-to-a-leg"),
    pytest.param({**github(ALL_CRLF),
                  WORKFLOWS_ATTRIBUTES: "*.yml eol=lf\n"}, KEEP_BOTH,
                 id="restored-below-it"),
]


@pytest.mark.parametrize(("files", "answers"), KEPT_LF)
def test_a_kept_file_that_leaves_each_copy_lf_is_no_finding(tmp_path, files,
                                                           answers):
    assert findings(adoption_plan(tmp_path, files, answers)) == []


def test_only_a_file_that_changes_a_copy_is_named(tmp_path):
    """`.github/workflows/.gitattributes` says `text`, which the root's rule
    says already: the copy's CRLF is `.github/.gitattributes`' alone."""
    files = {**github(ALL_CRLF), WORKFLOWS_ATTRIBUTES: TEXT_SET}
    found = findings(adoption_plan(tmp_path, files, KEEP_BOTH))
    assert [code for code, _ in found] == [NESTED], found
    assert found[0][1].startswith(f"the plan keeps `{GITHUB_ATTRIBUTES}`")
    assert WORKFLOWS_ATTRIBUTES not in found[0][1]


def test_a_file_that_alone_keeps_the_copy_lf_is_not_named(tmp_path):
    """`.github/.gitattributes` says `* text=auto`, which changes what git
    says of the copy but, alone over the root's rule, leaves it LF: the
    copy's CRLF is the deeper `* eol=crlf`'s, which alone is named, and
    whose line alone keeps the copy LF (#530's review, F3)."""
    files = {**github(TEXT_AUTO), WORKFLOWS_ATTRIBUTES: ALL_CRLF}
    found = findings(adoption_plan(tmp_path, files, KEEP_BOTH))
    assert [detail.split("`")[1] for _, detail in found] == [
        WORKFLOWS_ATTRIBUTES], found


def test_a_cause_two_files_make_only_together_is_still_named(tmp_path):
    """`* -text eol=crlf` alone leaves the copy as its blob, and `* text`
    alone says what the root says; together they write it CRLF. No file
    alone breaks the copy, so the one that changes what git says of it is
    named, and its line keeps the copy LF."""
    files = {**github("* -text eol=crlf\n"), WORKFLOWS_ATTRIBUTES: TEXT_SET}
    found = findings(adoption_plan(tmp_path, files, KEEP_BOTH))
    assert [detail.split("`")[1] for _, detail in found] == [
        GITHUB_ATTRIBUTES], found


def test_each_file_that_changes_a_copy_has_a_finding_with_its_own_lines(
        tmp_path):
    """Both kept files change the copy's `eol`, so each is named once, with
    the line its own directory spells: the copy is LF only once both end
    with one."""
    files = {**github(ALL_CRLF), WORKFLOWS_ATTRIBUTES: "*.yml !eol\n"}
    found = findings(adoption_plan(tmp_path, files, KEEP_BOTH))
    assert [detail.split("`")[1] for _, detail in found] == [
        GITHUB_ATTRIBUTES, WORKFLOWS_ATTRIBUTES], found
    assert f"`{VALIDATE_LINE}`" in found[0][1]
    assert "`/validate.yml text eol=lf`" in found[1][1]


def test_a_pattern_that_matches_only_once_case_is_ignored_says_so(tmp_path):
    """`*.YML` reaches `validate.yml` only where git ignores case, as it
    does on a macOS or Windows disk (`core.ignorecase`)."""
    found = findings(adoption_plan(tmp_path, github("*.YML eol=crlf\n"),
                                   KEEP_GITHUB))
    assert [code for code, _ in found] == [NESTED], found
    assert f"`{VALIDATE}`{CASE_ASIDE}:" in found[0][1]
    assert "line endings on such a disk, whatever git is set to," \
        in found[0][1]
    assert "Linux and macOS included" not in found[0][1]


def command_scope(key: str, value: str) -> dict:
    """`key=value` in git's command scope (`GIT_CONFIG_COUNT`), appended to
    what the environment holds: the Windows job sets `core.autocrlf` there,
    and the last entry of a key is the one git reads."""
    return appended_to_command_scope(os.environ, [(key, value)])


def checked(plan: Path, env: dict):
    """`check` of `plan`, run with `env` laid over this process's own."""
    return run_script(ADOPT, "check", "--plan", str(plan), env=env)


def checked_with(tmp_path: Path, env: dict, rules: str = YML_CRLF):
    """`check` of the plan keeping `.github/.gitattributes` holding
    `rules`, run with `env` laid over this process's own."""
    return checked(adoption_plan(tmp_path, github(rules), KEEP_GITHUB), env)


def test_this_machines_own_attributes_are_not_read(tmp_path):
    """A clone on another machine reads none of this one's attributes. A
    macro this machine's global attributes file defines, `[attr]keepbytes
    -text`, would make the kept `*.yml keepbytes eol=crlf` say `text:
    unset`, which `check` would then call kept, so that file is not read:
    `core.attributesFile` is set by this run's git's command scope
    (`GIT_CONFIG_COUNT`, appended to what the environment holds), and the
    finding still stands."""
    rules = tmp_path / "global-attributes"
    rules.write_bytes(b"[attr]keepbytes -text\n")
    checked = checked_with(
        tmp_path, command_scope("core.attributesFile", str(rules)),
        "*.yml keepbytes eol=crlf\n")
    assert f"FINDING {NESTED}: " in checked.stderr, checked.stderr


def global_attr_tree(tmp_path: Path) -> dict:
    """A global config naming the empty tree as `attr.tree`."""
    config = tmp_path / "global-config"
    config.write_bytes(f"[attr]\n\ttree = {EMPTY_TREE}\n".encode(UTF8))
    return {"GIT_CONFIG_GLOBAL": str(config)}


@pytest.mark.parametrize("where", [
    pytest.param(lambda _: {"GIT_ATTR_SOURCE": "HEAD"},
                 id="git-attr-source-head"),
    pytest.param(lambda _: {"GIT_ATTR_SOURCE": EMPTY_TREE},
                 id="git-attr-source-the-empty-tree"),
    pytest.param(global_attr_tree, id="attr-tree-in-the-global-config"),
    pytest.param(lambda _: command_scope("attr.tree", EMPTY_TREE),
                 id="attr-tree-in-the-command-scope")])
def test_no_tree_this_machine_names_steers_the_question(tmp_path, where):
    """`GIT_ATTR_SOURCE` and `attr.tree` make git read attributes from a
    tree instead of the work tree the question is written into (#530's review,
    checklist item 2). With git 2.43, `GIT_ATTR_SOURCE=HEAD` failed there,
    an empty repository, so `check` printed `REFUSED git-failed`; and the
    empty tree, named by either, made git read no rule at all, which
    silenced the finding. None of them is read, and the finding stands."""
    checked = checked_with(tmp_path, where(tmp_path))
    assert "REFUSED" not in checked.stderr, checked.stderr
    assert f"FINDING {NESTED}: " in checked.stderr, checked.stderr


@pytest.mark.parametrize(("rel", "said"), [
    pytest.param("workflows/validate.yml", f"`{VALIDATE_LINE}`", id="plain"),
    pytest.param("ci files/validate.yml",
                 "a `text eol=lf` line that names `ci files/validate.yml`",
                 id="a-name-a-line-cannot-spell")])
def test_a_copys_line_is_spelled_only_where_git_reads_it_literally(
        adopter, rel, said):
    """A symlink the root keeps can lead a copy to a name with a space,
    which a `.gitattributes` line would read as a pattern and an attribute:
    the finding names the copy instead of a line that says something else."""
    assert adopter._copy_line(rel) == said


class _NoProbe:
    def __init__(self, *_args, **_kwargs) -> None:
        raise AssertionError("git was asked about attributes")


@pytest.mark.parametrize(("files", "answers"), [
    pytest.param({}, {}, id="no-nested-file"),
    pytest.param({"notes/.gitattributes": YML_CRLF, "notes/a.md": "# A\n"},
                 {"notes/.gitattributes": ROOT}, id="above-no-copy"),
])
def test_a_source_with_no_kept_file_above_a_copy_asks_git_nothing(
        adopter, monkeypatch, tmp_path, files, answers):
    """Every source with no nested `.gitattributes` above a pinned copy
    adopts as it did on main: nothing is asked, and nothing is found."""
    plan = adopter.Plan.load(adoption_plan(tmp_path, files, answers))
    (tmp_path / "work").mkdir()
    source = plan.open_source(None, tmp_path / "work")
    monkeypatch.setattr(adopter, "_AttributesProbe", _NoProbe)
    assert adopter._nested_attributes_findings(plan, source,
                                               source.tree()) == []


# ---------------------------------------------------------------------------
# The root's own `.gitattributes`, which `git add` would re-encode (#530, D5)
# ---------------------------------------------------------------------------

#: The finding, and the code of `execute`'s refusal.
REENCODED = "plan-attributes-reencoded"
#: The start of every such finding.
KEPT_AND_APPENDED = ("the plan keeps the source's `.gitattributes` in the "
                     "assembly root, where the split appends #471's block to "
                     "it, and this machine's `git add` ")
STORES_OTHER_BYTES = "would store other bytes there"
CRLF_UNDER_TEXT = b"* text eol=lf\r\n"


def committed_raw(source: Path, name: str, data: bytes) -> None:
    """Commit `data` at `name` in `source` byte for byte, whatever the
    attributes say, as a file committed before its rules were, or by a
    machine that wrote it CRLF, is held: `hash-object --no-filters`, then
    `update-index`."""
    target = source / name
    target.write_bytes(data)
    blob = git("hash-object", "-w", "--no-filters", "--", name, cwd=source)
    git("update-index", "--add", "--cacheinfo",
        f"100644,{blob.stdout.strip()},{name}", cwd=source)
    git("commit", "-qm", f"Commit {name} as it is", cwd=source)


def root_attributes_plan(base: Path, data: bytes) -> Path:
    """The plan for `SOURCE` with a root `.gitattributes` committed as
    `data`, which `plan` asks nothing about."""
    source = make_source_repo(base / "Thing", tree=dict(SOURCE), edits=())
    committed_raw(source, ROOT_ATTRIBUTES, data)
    return planned(source, base, {})


#: Root `.gitattributes` blobs whose own rules make `git add` store them as
#: other bytes once the split appends the block: CRLF under `text`, under
#: `eol` alone (which says `text`), and an `ident` collapsed on the way in.
#: Each of the first three ended `adopt-lost` after both legs at 2423eaa2.
REENCODED_ROOTS = [
    pytest.param(CRLF_UNDER_TEXT, id="crlf-under-text-eol-lf"),
    pytest.param(b"* text eol=crlf\r\n", id="crlf-under-text-eol-crlf"),
    pytest.param(b"* eol=lf\r\n", id="crlf-under-eol-alone"),
    pytest.param(b"* text\r\n", id="crlf-under-text"),
    pytest.param(b"# $Id: deadbeef $\n* ident\n", id="an-expanded-ident"),
]


@pytest.mark.parametrize("data", REENCODED_ROOTS)
def test_a_root_attributes_git_add_would_reencode_is_found(tmp_path, data):
    """lane 2's D5(a) line, measured at 2423eaa2: `check` exited 0 and
    `execute` 1, `FINDING adopt-lost: .gitattributes`, after both leg remotes
    were made. `check` now finds it, says why, and names the way out."""
    found = findings(root_attributes_plan(tmp_path, data))
    assert [code for code, _ in found] == [REENCODED], found
    detail = found[0][1]
    assert detail.startswith(KEPT_AND_APPENDED + STORES_OTHER_BYTES), detail
    assert ("The verification would then report the source's `.gitattributes` "
            "as `adopt-lost`, in no leg and not in the root tree, after both "
            "legs exist.") in detail
    assert ("Commit the file in the source as git stores it (`git add "
            "--renormalize -- .gitattributes`, then commit), or change the "
            "rule git applies to it, and re-run `plan`.") in detail


def test_an_encoding_the_root_attributes_is_not_in_is_found(tmp_path):
    """`* working-tree-encoding=UTF-16LE` reaches the root's own
    `.gitattributes`, which is UTF-8: `git add` stores it decoded as
    UTF-16, or refuses it, as the length of what the split writes falls.
    Either is found, before any leg; at 2423eaa2 `execute` died after both,
    at mounting the legs (#654's L1-12), and `git add --renormalize` stages
    the encoded bytes, which git reads no rule from: the finding says so,
    and names the line that keeps the rule off the file. The files its
    rules reach are `plan-file-reencoded`'s, after it."""
    found = findings(root_attributes_plan(
        tmp_path, b"* working-tree-encoding=UTF-16LE\n"))
    assert [code for code, _ in found][0] == REENCODED, found
    assert {code for code, _ in found[1:]} == {"plan-file-reencoded"}, found
    detail = found[0][1]
    assert ("a `working-tree-encoding` rule reaches that file itself: the "
            "split's checkout writes it in that encoding, git then reads no "
            "rule from it, and the files its rules reach are stored again as "
            "other bytes, so the mount's `git rm` refuses those sent to a "
            "leg, at mounting the legs, after both legs exist.") in detail
    assert ("`git add --renormalize -- .gitattributes` is no way out: it "
            "stores the encoded bytes, which git reads no rule from. Keep the "
            "rule off the file with the line `.gitattributes "
            "-working-tree-encoding` after it, or narrow the rule, commit, "
            "and re-run `plan`.") in detail


#: Root `.gitattributes` blobs `git add` stores as the split writes them: a
#: CRLF blob `text=auto` leaves alone because the index already holds it
#: with CRLF, an LF blob, a file its own rules leave as it is, and one no
#: rule names. The first two adopted at 2423eaa2, as main does.
STORED_AS_WRITTEN = [
    pytest.param(b"* text=auto\r\n", id="crlf-under-text-auto"),
    pytest.param(b"* text=auto eol=lf\r\n", id="crlf-under-text-auto-eol-lf"),
    pytest.param(b"* text eol=lf\n", id="lf-under-text-eol-lf"),
    pytest.param(b"* text eol=crlf\n", id="lf-under-text-eol-crlf"),
    pytest.param(CRLF_UNDER_TEXT + b".gitattributes -text\r\n",
                 id="crlf-its-own-rules-leave-alone"),
    pytest.param(b"*.md text\r\n", id="crlf-no-rule-names-it"),
]


@pytest.mark.parametrize("data", STORED_AS_WRITTEN)
def test_a_root_attributes_git_add_stores_as_written_is_no_finding(tmp_path,
                                                                  data):
    assert findings(root_attributes_plan(tmp_path, data)) == []


def test_execute_refuses_a_reencoded_root_attributes_before_any_leg(
        adopter, monkeypatch, tmp_path):
    plan = root_attributes_plan(tmp_path, CRLF_UNDER_TEXT)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == REENCODED


def checked_root_with(tmp_path: Path, env: dict,
                      data: bytes = CRLF_UNDER_TEXT):
    """`check` of the plan keeping a root `.gitattributes` committed as
    `data`, run with `env` laid over this process's own."""
    return checked(root_attributes_plan(tmp_path, data), env)


def reencoded(checked) -> str:
    """The one `plan-attributes-reencoded` line `check` printed."""
    lines = [line for line in checked.stderr.splitlines()
             if line.startswith(f"FINDING {REENCODED}: ")]
    assert len(lines) == 1, checked.stderr
    return lines[0]


def test_what_this_machines_git_add_refuses_is_found_in_gits_words(tmp_path):
    """`core.safecrlf=true` makes this machine's `git add` refuse a CRLF it
    would store as LF, so the split would die committing, not verifying."""
    line = reencoded(checked_root_with(
        tmp_path, command_scope("core.safecrlf", "true")))
    assert (KEPT_AND_APPENDED + "refuses what the split writes there (git "
            "said `fatal: CRLF would be replaced by LF in .gitattributes`), "
            "so the split's own `git add` would fail, after both legs "
            "exist.") in line, line


def test_this_machines_own_attributes_are_read_for_the_split(tmp_path):
    """Unlike the nested question, which a clone elsewhere answers, the
    split's `git add` runs here and reads this machine's attributes: a
    global file saying `.gitattributes text eol=lf` makes it store a CRLF
    blob whose own rules say nothing of it as LF."""
    rules = tmp_path / "global-attributes"
    rules.write_bytes(b".gitattributes text eol=lf\n")
    checked = checked_root_with(
        tmp_path, command_scope("core.attributesFile", str(rules)),
        b"*.md text\r\n")
    assert STORES_OTHER_BYTES in reencoded(checked)


@pytest.mark.parametrize("where", [
    pytest.param(lambda: {"GIT_ATTR_SOURCE": "HEAD"},
                 id="git-attr-source-head"),
    pytest.param(lambda: {"GIT_ATTR_SOURCE": EMPTY_TREE},
                 id="git-attr-source-the-empty-tree"),
    pytest.param(lambda: command_scope("attr.tree", EMPTY_TREE),
                 id="attr-tree-in-the-command-scope")])
def test_no_tree_this_machine_names_steers_the_split_question(tmp_path,
                                                              where):
    """The question's throwaway repository has no commit for `HEAD` to name,
    and the empty tree would make git read no rule at all: neither is
    inherited, so git neither fails nor goes quiet."""
    checked = checked_root_with(tmp_path, where())
    assert "REFUSED" not in checked.stderr, checked.stderr
    assert STORES_OTHER_BYTES in reencoded(checked)


def _never_asked(*_args, **_kwargs):
    raise AssertionError("git was asked what `git add` stores")


def no_root_attributes(base: Path) -> Path:
    return make_source_repo(base / "Thing", tree=dict(SOURCE), edits=())


def a_root_attributes_symlink(base: Path) -> Path:
    source = make_source_repo(
        base / "Thing", tree={**SOURCE, LINKED_RULES: TEXT_AUTO},
        edits=())
    index_link(source, ROOT_ATTRIBUTES, LINKED_RULES)
    return source


@pytest.mark.parametrize(("made", "answers"), [
    pytest.param(no_root_attributes, {}, id="no-root-attributes"),
    pytest.param(a_root_attributes_symlink, {"config/": ROOT},
                 id="a-root-attributes-symlink")])
def test_a_root_attributes_the_split_does_not_write_into_asks_git_nothing(
        adopter, monkeypatch, tmp_path, made, answers):
    """The split writes into the source's root `.gitattributes` only where
    the root keeps it as a regular file: where it keeps none the shape's own
    is written, and through a symlink nothing is (#471's follow-up)."""
    plan = adopter.Plan.load(planned(made(tmp_path), tmp_path, answers))
    (tmp_path / "work").mkdir()
    source = plan.open_source(None, tmp_path / "work")
    monkeypatch.setattr(adopter, "_stored_as_written", _never_asked)
    assert adopter._reencoded_attributes_findings(plan, source,
                                                  source.tree()) == []


# ---------------------------------------------------------------------------
# End to end: the remedy adopts, and every pinned copy keeps its bytes
# ---------------------------------------------------------------------------

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def adopted_by_execute(plan: Path, base: Path) -> None:
    """`execute --yes` of `plan`, its remotes and work under `base`; it
    exits 0 and says `adoption verified`."""
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout, result.stdout


@pytest.fixture(scope="module", params=[
    pytest.param(github(REMEDIED), id="the-remedy"),
    pytest.param(github(MINUS_TEXT), id="minus-text")])
def adopted(request, tmp_path_factory) -> Path:
    """One real adoption that keeps `.github/.gitattributes` in the root:
    the source the finding's remedy was applied to, and one whose kept file
    says `-text`."""
    base = tmp_path_factory.mktemp("nested-attributes")
    adopted_by_execute(adoption_plan(base, request.param, KEEP_GITHUB), base)
    return base / "Thing"


@needs_filter_repo
@pytest.mark.parametrize("config", [
    pytest.param([], id="as-configured"),
    pytest.param(["-c", "core.autocrlf=true"], id="autocrlf"),
    pytest.param(["-c", "core.eol=crlf"], id="eol-crlf")])
def test_every_pinned_copy_keeps_its_bytes_in_the_adopted_clone(
        adopted, tmp_path, config):
    """`git check-attr` on every pinned copy of the clone says `eol: lf`,
    the bytes on disk hold no CRLF, and the first bootstrap passes. The
    source's own README, which no copy rule reaches, is the control: where
    the clone was asked to write CRLF, it did."""
    clone = tmp_path / "Northwind"
    cloned = clone_just_pushed(adopted, clone, BRANCH, config=config)
    assert cloned.returncode == 0, cloned.stderr
    pinned = [row["path"] for row in parse_yaml(
        (clone / PIN).read_text(encoding=UTF8))["files"]]
    said = git("check-attr", "-z", "eol", "--", *pinned, cwd=clone).stdout
    fields = said.split("\0")
    eol = dict(zip(fields[0::3], fields[2::3]))
    assert {path: eol.get(path) for path in pinned} == dict.fromkeys(
        pinned, "lf")
    assert [path for path in pinned
            if b"\r\n" in (clone / path).read_bytes()] == []
    if config:
        assert b"\r\n" in (clone / "README.md").read_bytes(), \
            "this clone did not write CRLF, so it tests nothing"
    booted = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    assert booted.returncode == 0, booted.stderr + booted.stdout


@needs_filter_repo
def test_a_renormalized_root_attributes_adopts(tmp_path):
    """The finding's way out, taken: the CRLF root `.gitattributes`
    committed again as git stores it, and the plan made again. `check` finds
    nothing, and `execute` verifies the source's bytes followed by the
    block."""
    source = make_source_repo(tmp_path / "Thing", tree=dict(SOURCE), edits=())
    committed_raw(source, ROOT_ATTRIBUTES, CRLF_UNDER_TEXT)
    git("add", "--renormalize", "--", ROOT_ATTRIBUTES, cwd=source)
    git("commit", "-qm", "Renormalize .gitattributes", cwd=source)
    plan = planned(source, tmp_path, {})
    assert findings(plan) == []
    adopted_by_execute(plan, tmp_path)
