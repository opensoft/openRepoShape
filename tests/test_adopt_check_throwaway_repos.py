# SPDX-License-Identifier: Apache-2.0
"""`check`'s throwaway repositories answer as the split will (#910).

`check` asks this machine's git in repositories of its own: which kept
nested `.gitattributes` outrank the root's rule (#530, #619), what `git add`
stores at the root's own (#530's D5(a)), and what the split's checkout, `git
rm` and `git add` make of every file (#654's rehearsal); and, in the work
directory, whether git checks a symlink out as one (#183's probe). Lane 3's
triage of #457 filed four lines against them. Measured on c7a3ff16 with git
2.43, each in a real `check`:

* L1-90: a SHA-256 source, `GIT_DEFAULT_HASH=sha256` over a SHA-1 one, and a
  tree path git refuses (`..`, `.Git/x`) each stopped `check` with `REFUSED
  git-failed`, exit 2, at the rehearsal's `read-tree`. Before #654 `check`
  passed the path, and `execute` made both legs and stopped extracting the
  spec leg, its first clone saying `error: invalid path '..'`.
* L1-92: the three were made in `TMPDIR`, another disk than the work
  directory where `execute` builds the split, wherever `TMPDIR` was.
* L1-94: a `core.hooksPath` from this machine's global config ran its
  `post-index-change` hook 12 times in one `check`, 2 in #619's repository
  and 10 in the rehearsal.
* L1-32: a `git init` the symlink probe's work directory refused otherwise
  than with an `OSError` (`GIT_DEFAULT_HASH=bogus`) stopped `check` with "a
  git or gh command failed", exit 2, where it printed `plan-root-symlink`.

Now each is made in the work directory, each but the symlink probe with the
source's object format and no hook of this machine's (the probe keeps its
plain `git init`, which runs none), a path git refuses is
`plan-path-git-refuses`, a repository git cannot make or ask there is
`adopt-git-unasked`, which says why, and the probe's failure stands for its
finding, with a NOTE.

#1033: `refused_paths` writes its own index with `update-index -z
--index-info`, and no row said what that index makes of case twins (`a` and
`A`) where `core.ignorecase` is true, the default on a disk that ignores
case. Measured with git 2.43, it holds both twins of a path git takes, each
with its own blob, and `plan-path-git-refuses` names both twins of a path git
refuses. This bench has no usable disk that ignores case, so the row that
needs one skips here.

#1161: so `check` passed twins wherever the plan kept them, though a disk
that ignores case holds each set as one name. Measured with git 2.43 on
4c7b8acd, the work directory and every repository on such a disk: `execute`
lost `F/x` beside `f` after both legs were pushed (`adopt-lost`), and was
refused at the folder twins `D/x` and `d/x` as `plan-file-reencoded` in 2
of 4 fresh sources. Now `plan-case-twins` names each set the plan keeps in
one repository, the root or a leg, on every disk, and `execute` refuses it
before any leg exists.

#1183: twins the plan sends into different repositories, or drops one of,
are no finding, and `execute` lost them on such a disk. Measured with git
2.43 on 4d40ce9f: the split's clone checks out one file per set, holding the
bytes of the twin git wrote last, and the mount's `git rm` of the twin that
goes deleted that file (`adopt-lost` for the twin the root keeps) or refused
it as a local modification (`REFUSED mounting the legs`), after both legs
were pushed. Now the mount removes such a path with `-f` and writes each
twin the root keeps back from the index. The rows that drive the mount make
that one file on any disk, as hard links; the rows that run `execute` whole
skip on a disk that keeps case, but for one control.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, WINDOWS_SKIP, appended_to_command_scope,
                      findings, git, make_source_repo, planned,
                      refused_before_any_leg, run_script)
from test_adopt_nested_attributes import (KEEP_GITHUB, ROOT, ROOT_ATTRIBUTES,
                                          SOURCE, YML_CRLF, adoption_plan,
                                          committed_raw, github)
from test_adopt_root_symlinks import (GITHUB, OUTSIDE_CI, WORKFLOW, climbs,
                                      finding, symlink_findings)
from test_adopt_root_symlinks import links_as_links  # noqa: F401
from test_adopt_root_symlinks import unwritable_work  # noqa: F401
from test_adopt_root_symlinks import planned as planned_with_links

#: The two findings #910 adds, and the codes of `execute`'s refusals.
PATH_GIT_REFUSES = "plan-path-git-refuses"
UNASKED = "adopt-git-unasked"
#: The findings and codes the rows below meet besides.
REENCODED_FILES = "plan-file-reencoded"
WORK_DIR_UNWRITABLE = "adopt-work-dir-unwritable"
NOTES = "notes.txt"
CRLF = b"one\r\ntwo\r\n"
TEXT_EOL_LF = b"* text eol=lf\n"
#: How `plan-file-reencoded` begins for the one CRLF file the plan keeps.
KEPT_CRLF = ("the plan keeps 1 file in the assembly root, and this machine's "
             "`git add` would store it as other bytes than its blob")
#: The prefixes of the throwaway repositories of #530 and #654.
THROWAWAY_PREFIXES = ("openreposhape-attributes-",
                      "openreposhape-reencoded-")
#: The hooks the counting `core.hooksPath` holds: every one git runs where
#: an index, a checkout or a ref is written, or a commit made.
HOOKS = ("post-index-change", "post-checkout", "reference-transaction",
         "post-commit", "pre-auto-gc")
#: `adopt-git-unasked`, up to where it names why, and from where it names
#: what `execute` does: `{}` is the work directory.
UNASKED_OPENS = (
    "`check` asks this machine's git what the split will make of the source "
    "in throwaway repositories in `{}`, the work directory, where `execute` "
    "builds the split, and it could not: ")
UNASKED_ENDS = (
    ". `execute` asks the same in its own work directory before it makes "
    "either leg, and refuses while git cannot answer there. Fix what that "
    "names -- a git setting, the disk or the directory -- or pass another "
    "--work-dir, and run `check` again.")
PATH_REMEDY = "Remediation: a path git refuses is a fact of the source"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_check_throwaway_repos", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def a_source(base: Path, object_format: str = "sha1",
             files: dict | None = None) -> Path:
    """`SOURCE` committed in a repository of `object_format`, then each of
    `files` committed byte for byte (`committed_raw`)."""
    path = base / "Thing"
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", f"--object-format={object_format}", ".",
        cwd=path)
    for name, body in SOURCE.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body.encode("utf-8"))
    git("add", "-A", cwd=path)
    git("commit", "-qm", "Initial import", cwd=path)
    for name, data in (files or {}).items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        committed_raw(path, name, data)
    return path


def mktree(repo: Path, rows: list[str]) -> str:
    made = subprocess.run(["git", "mktree"], cwd=str(repo),
                          input="".join(f"{row}\n" for row in rows).encode(),
                          capture_output=True, check=True)
    return made.stdout.decode().strip()


def blob_of(repo: Path, data: bytes) -> str:
    return subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(repo), input=data, capture_output=True,
                          check=True).stdout.decode().strip()


def with_paths(repo: Path, paths: tuple[str, ...],
               own_blobs: bool = False, links: tuple[str, ...] = ()) -> None:
    """A commit on `main` whose tree gains each of `paths`, whether git
    takes it as a path or not: `git mktree` writes what it is given, and no
    index is asked. A folder HEAD already holds, `src/` say, gains them
    beside what it holds, and is not written twice. With `own_blobs`, each
    path's blob holds its own name, so an index that holds one path's blob
    under another's name is seen. Each of `links` is written as a symlink
    (mode 120000), not a file."""
    shared = blob_of(repo, b"x\n")
    nested: dict = {}
    for path in paths:
        *directories, name = path.split("/")
        here = nested
        for directory in directories:
            here = here.setdefault(directory, {})
        here[name] = ("120000" if path in links else "100644",
                      blob_of(repo, f"{path}\n".encode("utf-8"))
                      if own_blobs else shared)

    def rows(names: dict, folder: str) -> list[str]:
        held = {line.split("\t", 1)[1]: line for line in git(
            "ls-tree", f"HEAD:{folder}", cwd=repo,
            check=False).stdout.splitlines()}
        for name, below in names.items():
            inner = f"{folder}/{name}" if folder else name
            held[name] = (f"{below[0]} blob {below[1]}\t{name}"
                          if isinstance(below, tuple) else
                          f"040000 tree {mktree(repo, rows(below, inner))}"
                          f"\t{name}")
        return list(held.values())

    tree = mktree(repo, rows(nested, ""))
    commit = git("commit-tree", tree, "-p", "HEAD", "-m", "Add paths",
                 cwd=repo).stdout.strip()
    git("update-ref", "refs/heads/main", commit, cwd=repo)


def checked(plan: Path, env: dict | None = None, *extra: str):
    return run_script(ADOPT, "check", "--plan", str(plan), *extra,
                      env=env or {})


def finding_lines(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def codes(result) -> list[str]:
    return [line.split(" ", 2)[1].rstrip(":")
            for line in finding_lines(result)]


def config_with(base: Path, *lines: str) -> dict:
    """`GIT_CONFIG_GLOBAL` naming a file of `lines`, after an include of
    the session's own global config, so that what it sets stays set."""
    config = base / "global-config"
    held = os.environ.get("GIT_CONFIG_GLOBAL", "")
    included = ["[include]", f'\tpath = "{Path(held).as_posix()}"'] \
        if held else []
    config.write_bytes(("\n".join([*included, *lines]) + "\n").encode())
    return {"GIT_CONFIG_GLOBAL": str(config)}


# ---------------------------------------------------------------------------
# L1-90: the source's object format
# ---------------------------------------------------------------------------

#: `(the source's object format, what the environment adds)`: each of the
#: first three stopped `check` with `REFUSED git-failed` on c7a3ff16; the
#: last is the control, which did not.
FORMATS = [
    pytest.param("sha256", {}, id="a-sha256-source"),
    pytest.param("sha1", {"GIT_DEFAULT_HASH": "sha256"},
                 id="default-hash-sha256-over-a-sha1-source"),
    pytest.param("sha256", {"GIT_DEFAULT_HASH": "sha1"},
                 id="default-hash-sha1-over-a-sha256-source"),
    pytest.param("sha1", {}, id="control-a-sha1-source"),
]


@pytest.mark.parametrize(("object_format", "env"), FORMATS)
def test_the_rehearsal_answers_in_the_sources_object_format(
        tmp_path, object_format, env):
    """The CRLF file the plan keeps under `* text eol=lf` is found in every
    format, so the rehearsal was asked, and answered, in the source's."""
    plan = planned(a_source(tmp_path, object_format,
                            {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    result = checked(plan, env)
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [REENCODED_FILES], result.stderr
    assert KEPT_CRLF in finding_lines(result)[0]


@pytest.mark.parametrize(("object_format", "env"), FORMATS[:3])
def test_a_source_with_nothing_to_find_is_plan_ok_in_its_format(
        tmp_path, object_format, env):
    plan = planned(a_source(tmp_path, object_format), tmp_path, {})
    result = checked(plan, env)
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout


# ---------------------------------------------------------------------------
# L1-90: a tree path git refuses
# ---------------------------------------------------------------------------

def one_refused(path: str) -> str:
    return (f"the source commit holds 1 path this machine's git refuses as a "
            f"path, and holds in no index: `{path}`. Each clone the split "
            "makes of the source would stop at it, `unable to checkout "
            "working tree`, so `execute` refuses it before it makes either "
            "leg, whatever the plan answers for it.")


#: `(paths, the plan's entries for them, what `check` says)`.
REFUSED_PATHS = [
    pytest.param(("..",), {"..": ROOT}, one_refused(".."), id="dot-dot"),
    pytest.param((".Git/x",), {".Git/": ROOT}, one_refused(".Git/x"),
                 id="dot-git-in-another-case"),
    pytest.param(("notes/.git/x",), {"notes/": ROOT},
                 one_refused("notes/.git/x"), id="dot-git-below-the-root"),
    pytest.param(("..", ".Git/x", "notes/.git/x"),
                 {"..": ROOT, ".Git/": ROOT, "notes/": ROOT},
                 "the source commit holds 3 paths this machine's git refuses "
                 "as a path, and holds in no index: `..`, `.Git/x` and "
                 "`notes/.git/x`. Each clone the split makes of the source "
                 "would stop at the first, `unable to checkout working "
                 "tree`, so `execute` refuses them before it makes either "
                 "leg, whatever the plan answers for them.",
                 id="three-in-the-trees-order"),
]


@pytest.mark.parametrize(("paths", "answers", "said"), REFUSED_PATHS)
def test_a_path_git_refuses_is_a_finding(tmp_path, paths, answers, said):
    source = a_source(tmp_path)
    with_paths(source, paths)
    result = checked(planned(source, tmp_path, answers))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [f"FINDING {PATH_GIT_REFUSES}: {said}"]
    assert result.stderr.count(PATH_REMEDY) == 1, result.stderr


def test_a_path_git_takes_beside_them_is_no_finding(tmp_path):
    """The control: `..x` and `.Gitx/x` are paths git takes."""
    source = a_source(tmp_path)
    with_paths(source, ("..x", ".Gitx/x"))
    assert findings(planned(source, tmp_path,
                            {"..x": ROOT, ".Gitx/": ROOT})) == []


def test_execute_refuses_a_path_git_refuses_before_any_leg(
        adopter, monkeypatch, tmp_path):
    source = a_source(tmp_path)
    with_paths(source, ("..",))
    refusal = refused_before_any_leg(
        adopter, monkeypatch, planned(source, tmp_path, {"..": ROOT}),
        tmp_path)
    assert refusal.code == PATH_GIT_REFUSES
    assert PATH_REMEDY in refusal.remediation


def test_the_rehearsal_asks_nothing_more_of_a_tree_git_refuses(adopter,
                                                               tmp_path):
    """Asked on its own, the rehearsal stops before its `read-tree`, which
    git refuses at `..`: `plan-path-git-refuses` names the path."""
    source = a_source(tmp_path)
    with_paths(source, ("..",))
    plan = adopter.Plan.load(planned(source, tmp_path, {"..": ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    assert adopter._reencoded_files_findings(plan, opened,
                                             opened.tree()) == []
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# #1033: case twins, with `core.ignorecase` true
# ---------------------------------------------------------------------------

#: `(the case twins a source commit holds, the ones git refuses)`. `git
#: mktree` writes twins that no checkout on a disk that ignores case could,
#: each with a blob of its own (`with_paths`).
CASE_TWINS = [
    pytest.param(("A", "a"), (), id="file-twins"),
    pytest.param(("D/x", "d/x"), (), id="folder-twins"),
    pytest.param(("F/x", "f"), (), id="a-folder-and-a-file"),
    pytest.param(("E", "e/x"), (), id="a-file-and-a-folder"),
    pytest.param(("AB", "Ab", "ab"), (), id="three-twins"),
    pytest.param(("\u00c9", "\u00e9"), (), id="non-ascii-twins"),
    pytest.param((".Git/A", ".Git/a"), (".Git/A", ".Git/a"),
                 id="twins-under-a-path-git-refuses"),
    pytest.param((".GIT/x", ".Git/x"), (".GIT/x", ".Git/x"),
                 id="twins-git-refuses"),
]
#: The twins of `file-twins`, `folder-twins` and `a-folder-and-a-file`, and
#: the two refused sets above, in one source commit; the ones git refuses,
#: in the tree's order; and the plan's answers for them all.
ALL_TWINS = ("A", "a", "D/x", "d/x", "F/x", "f", ".Git/A", ".Git/a",
             ".GIT/x", ".Git/x")
TWINS_REFUSED = (".GIT/x", ".Git/A", ".Git/a", ".Git/x")
TWIN_ANSWERS = {"A": ROOT, "a": ROOT, "D/": ROOT, "d/": ROOT, "F/": ROOT,
                "f": ROOT, ".GIT/": ROOT, ".Git/": ROOT}


def with_twins(adopter, base: Path, twins: tuple[str, ...],
               links: tuple[str, ...] = ()):
    """`a_source` whose commit gains `twins`, each with a blob of its own,
    opened as `check` opens it, with `base/work` its work directory."""
    path = a_source(base)
    with_paths(path, twins, own_blobs=True, links=links)
    work = base / "work"
    work.mkdir()
    return adopter.Source(path, None, "main",
                          git("rev-parse", "HEAD", cwd=path).stdout.strip(),
                          work_root=work)


def twins_asked(adopter, source, twins: tuple[str, ...],
                ignorecase: str | None) -> tuple[str, list[str], dict]:
    """`(core.ignorecase as the rehearsal's own config holds it, the paths
    `refused_paths` names, each twin's fate)`, the fate read from the index
    with `git ls-files -s`: `held` under its own name with its own blob,
    `named`, `held with another blob`, or `dropped without a word`. Where
    `ignorecase` is given it is written into that config first, as `git
    init` writes `true` on a disk that ignores case; None keeps what `git
    init` wrote. The index must hold every path of the tree it does not
    name, and nothing else."""
    tree = source.tree()
    blobs = {path: oid for path, _, oid, _ in tree}
    with adopter._SplitRehearsal(source) as asked:
        if ignorecase is not None:
            git("config", "core.ignorecase", ignorecase, cwd=asked.work)
        written = git("config", "--local", "--get", "core.ignorecase",
                      cwd=asked.work, check=False).stdout.strip()
        named = asked.refused_paths(tree)
        held = asked.staged(adopter.PATHS_HELD)
    assert sorted(held) == [path for path, _, _, _ in tree
                            if path not in named], held
    return written, named, {
        twin: "named" if twin in named
        else "held" if held.get(twin) == blobs[twin]
        else "held with another blob" if twin in held
        else "dropped without a word" for twin in twins}


def as_measured(twins: tuple[str, ...], refused: tuple[str, ...]) -> dict:
    return {twin: "named" if twin in refused else "held" for twin in twins}


@pytest.mark.parametrize("ignorecase", ["true", "false"])
@pytest.mark.parametrize(("twins", "refused"), CASE_TWINS)
def test_each_case_twin_is_held_with_its_own_blob_or_named(
        adopter, tmp_path, twins, refused, ignorecase):
    """`refused_paths` writes its index with `update-index -z --index-info`.
    Measured with git 2.43 and `core.ignorecase` true in the rehearsal's
    own config:
    - git holds each twin of a path it takes, each under its own name with
      its own blob, at a file, a folder, or a folder beside a file;
    - git leaves out both twins of a path it refuses, and `refused_paths`
      names each one.
    No twin is folded into the other, and none is dropped without a word.
    `false` is the control, and git answers the same."""
    source = with_twins(adopter, tmp_path, twins)
    written, named, fates = twins_asked(adopter, source, twins, ignorecase)
    assert written == ignorecase
    assert named == list(refused)
    assert fates == as_measured(twins, refused)


@pytest.mark.parametrize("ignorecase", ["true", "false"])
def test_a_twin_git_refuses_by_its_mode_is_named_beside_the_one_it_holds(
        adopter, tmp_path, ignorecase):
    """Git refuses a path by its mode too: a symlink named `.GITMODULES`, in
    any case, and holds the file `.gitmodules`. Measured with git 2.43,
    `core.ignorecase` unset, false and true: so git can refuse one twin and
    hold the other, and an answer that folds the index's paths into one case
    would take the refused twin for a held one."""
    twins = (".GITMODULES", ".gitmodules")
    source = with_twins(adopter, tmp_path, twins, links=(".GITMODULES",))
    written, named, fates = twins_asked(adopter, source, twins, ignorecase)
    assert written == ignorecase
    assert named == [".GITMODULES"]
    assert fates == {".GITMODULES": "named", ".gitmodules": "held"}


def test_on_a_disk_that_ignores_case_each_twin_is_held_or_named(adopter,
                                                                tmp_path):
    """Where the work directory's disk ignores case, as on macOS and
    Windows, `git init` writes `core.ignorecase=true` into each throwaway
    repository's own config. `refused_paths` reads nothing else of the disk:
    `update-index --index-info` and `ls-files` read the index, never the
    work tree. The rows above write that setting by hand, so they answer
    for such a disk on any disk. This row asks the disk itself, and is
    skipped on a disk that keeps case, as every CI disk is (CI is Linux
    only since #597)."""
    source = with_twins(adopter, tmp_path, ALL_TWINS)
    written, named, fates = twins_asked(adopter, source, ALL_TWINS, None)
    if written != "true":
        pytest.skip("needs a disk that ignores case: `git init` wrote no "
                    "`core.ignorecase=true` in the work directory, so that "
                    "disk keeps case; the rows above write the setting into "
                    "the throwaway repository by hand instead")
    assert named == list(TWINS_REFUSED)
    assert fates == as_measured(ALL_TWINS, TWINS_REFUSED)


def test_check_names_each_twin_git_refuses_and_each_set_it_holds(tmp_path):
    """`check` over a source holding the twins of `file-twins`,
    `folder-twins` and `a-folder-and-a-file`, and the two refused sets
    above, with `core.ignorecase` true in the global config. On a disk that
    keeps case, `git init` writes no `core.ignorecase` into a throwaway
    repository, so the global setting is the one each throwaway reads.
    `plan` asks about each twin as a path of its own (`planned` answers
    each by name). Under a global `core.ignorecase=true` the #654
    rehearsal's `git add` refuses the folder twins `D/x` and `d/x` as
    `plan-file-reencoded`; this row does not see it, because the rehearsal
    asks nothing of a source that holds a path git refuses
    (`_reencoded_files_findings`, `if refused: return []`).
    `refused_paths` meets every twin: `plan-path-git-refuses` names, in the
    tree's order, the four git refuses, and `plan-case-twins` (#1161) names
    the six it holds, set by set, because the plan keeps them all in the
    root, and none of the four, which are the first finding's alone."""
    source = a_source(tmp_path)
    with_paths(source, ALL_TWINS, own_blobs=True)
    result = checked(planned(source, tmp_path, TWIN_ANSWERS),
                     config_with(tmp_path, "[core]", "\tignorecase = true"))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [
        f"FINDING {PATH_GIT_REFUSES}: the source commit holds 4 paths this "
        "machine's git refuses as a path, and holds in no index: `.GIT/x`, "
        "`.Git/A`, `.Git/a` and `.Git/x`. Each clone the split makes of the "
        "source would stop at the first, `unable to checkout working tree`, "
        "so `execute` refuses them before it makes either leg, whatever the "
        "plan answers for them.",
        twins_kept("3 sets", ROOT_TWINS, "6 paths",
                   "`A`, `a`, `D/x`, `d/x`, `F/x` and `f`")]
    assert result.stderr.count(PATH_REMEDY) == 1, result.stderr
    assert result.stderr.count(TWINS_REMEDY) == 1, result.stderr


# ---------------------------------------------------------------------------
# #1161: the case twins the plan keeps in one repository
# ---------------------------------------------------------------------------

#: The finding #1161 adds, the code of `execute`'s refusal, how its
#: remediation begins, and the whole of it: a rename in the source. It
#: offers no answer that sends the twins into different repositories
#: (r1189's MUST 1), written while a disk that ignores case lost those too;
#: `execute` keeps them since #1183 (the rows under #1183 below).
PLAN_CASE_TWINS = "plan-case-twins"
TWINS_REMEDY = "Remediation: rename paths in the source until no two"
TWINS_REMEDIATION = (
    "Remediation: rename paths in the source until no two that one "
    "repository would hold differ only in case -- each twin of a set but "
    "one, or the folder above a twin -- commit that, and re-run `plan`: a "
    "plan is written against one commit of the source, and `check` calls it "
    "`plan-stale` once the source has moved.")
#: Where `plan-case-twins` says the plan keeps a set.
ROOT_TWINS, SPEC_TWINS, CODE_TWINS = ("the assembly root", "the spec leg",
                                      "the code leg")


def twins_kept(sets: str, where: str, paths: str, named: str) -> str:
    """`plan-case-twins` as `check` prints it for `sets` sets of twins in
    `where`, `paths` paths, named as `named`."""
    return (f"FINDING {PLAN_CASE_TWINS}: the plan keeps {sets} of case twins "
            f"in {where}, {paths}, the paths of a set differing only in "
            "case, or one naming in another case a folder above another: "
            f"{named}. A disk that ignores case, as a macOS or Windows disk "
            "does by default, holds each set as one name: a clone made there "
            "checks out only one path of each set, and `execute` could stop "
            "there before any leg exists, at git's `will not add file "
            "alias`, or after both legs are pushed, as `adopt-lost` or at "
            "`git rm` mounting the legs, so `execute` refuses them on every "
            "disk.")


def one_blob_twins(sets: str, where: str, paths: str, named: str) -> str:
    """The NOTE `check` prints for `sets` sets of twins in `where` whose
    paths fold to one name and hold one blob in one mode, `paths` paths,
    named as `named`: `plan-case-twins` leaves them out (r1189's SHOULD
    5)."""
    return (f"NOTE the plan keeps {sets} of case twins in {where} whose "
            f"paths hold one blob in one mode, {paths}: {named}. A disk that "
            "ignores case holds each set as one name, and a clone made there "
            "checks out one path of each, git saying `the following paths "
            "have collided`; that path holds what each path of the set "
            "holds, so none is lost, and `check` names no "
            f"`{PLAN_CASE_TWINS}` for them.")


#: `(the paths a source commit gains, each with a blob of its own, the
#: plan's answers, what `check` finds)`. An answer left out is the one
#: `plan` wrote: `specs/` goes to the spec leg and `src/` to the code leg.
#: On 4c7b8acd, #1158's head, `check` printed `plan ok` for every one.
TWINS_KEPT = [
    pytest.param(("A", "a"), {"A": ROOT, "a": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`")],
                 id="file-twins"),
    pytest.param(("D/x", "d/x"), {"D/": ROOT, "d/": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`D/x` and `d/x`")],
                 id="folder-twins"),
    pytest.param(("F/x", "f"), {"F/": ROOT, "f": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`F/x` and `f`")],
                 id="a-folder-and-a-file"),
    pytest.param(("E", "e/x"), {"E": ROOT, "e/": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`E` and `e/x`")],
                 id="a-file-and-a-folder"),
    pytest.param(("AB", "Ab", "aB"), {"AB": ROOT, "Ab": ROOT, "aB": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "3 paths",
                             "`AB`, `Ab` and `aB`")],
                 id="three-twins-none-in-lower-case"),
    pytest.param(("specs/A", "specs/a"), {},
                 [twins_kept("1 set", SPEC_TWINS, "2 paths",
                             "`specs/A` and `specs/a`")],
                 id="twins-in-the-spec-leg"),
    pytest.param(("src/É", "src/é"), {},
                 [twins_kept("1 set", CODE_TWINS, "2 paths",
                             "`src/É` and `src/é`")],
                 id="non-ascii-twins-in-the-code-leg"),
    pytest.param(("src/A", "src/D/x", "src/a", "src/d/x"), {},
                 [twins_kept("2 sets", CODE_TWINS, "4 paths",
                             "`src/A`, `src/a`, `src/D/x` and `src/d/x`")],
                 id="two-sets-in-the-code-leg-set-by-set"),
    pytest.param(("A", "a", "specs/A", "specs/a", "src/A", "src/a"),
                 {"A": ROOT, "a": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`"),
                  twins_kept("1 set", SPEC_TWINS, "2 paths",
                             "`specs/A` and `specs/a`"),
                  twins_kept("1 set", CODE_TWINS, "2 paths",
                             "`src/A` and `src/a`")],
                 id="a-set-in-each-repository"),
    pytest.param(tuple("AaBbCcDdEeFf"), dict.fromkeys("AaBbCcDdEeFf", ROOT),
                 [twins_kept("6 sets", ROOT_TWINS, "12 paths",
                             "`A`, `a`, `B`, `b`, `C`, `c`, `D`, `d`, `E`, "
                             "`e` and 2 more")],
                 id="ten-named-and-the-rest-counted"),
    # r1189's SHOULD 6: a file against a folder below the top level, and
    # one against a folder two levels above another path.
    pytest.param(("src/E", "src/e/x"), {},
                 [twins_kept("1 set", CODE_TWINS, "2 paths",
                             "`src/E` and `src/e/x`")],
                 id="a-file-and-a-folder-in-the-code-leg"),
    pytest.param(("f", "F/G/x"), {"f": ROOT, "F/": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`F/G/x` and `f`")],
                 id="a-file-and-a-folder-two-levels-above"),
    # Known limit 1: `casefold` folds `ß` to `ss`, as `lower` does not.
    pytest.param(("src/straße", "src/STRASSE"), {},
                 [twins_kept("1 set", CODE_TWINS, "2 paths",
                             "`src/STRASSE` and `src/straße`")],
                 id="sharp-s-folded-as-ss"),
    pytest.param(("AB", "Ab", "aB", "ab"), dict.fromkeys(("AB", "Ab", "aB",
                                                          "ab"), ROOT),
                 [twins_kept("1 set", ROOT_TWINS, "4 paths",
                             "`AB`, `Ab`, `aB` and `ab`")],
                 id="one-set-of-four"),
]


@pytest.mark.parametrize(("paths", "answers", "found"), TWINS_KEPT)
def test_check_names_the_case_twins_the_plan_keeps_in_one_repository(
        tmp_path, paths, answers, found):
    """A disk that ignores case holds each set as one name. Measured for
    #1161 with git 2.43 on 4c7b8acd, the work directory and every
    repository on such a disk: `check` printed `plan ok` for each set, and
    `execute` lost `F/x` after both legs were pushed (`adopt-lost`), or was
    refused at folder twins as `plan-file-reencoded`, git saying `will not
    add file alias`. Now `check` names each set on every disk, one finding
    for each repository that holds one, root, spec leg, code leg, and says
    its remediation once."""
    source = a_source(tmp_path)
    with_paths(source, paths, own_blobs=True)
    result = checked(planned(source, tmp_path, answers))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == found
    assert result.stderr.count(TWINS_REMEDY) == 1, result.stderr
    assert TWINS_REMEDIATION in result.stderr.splitlines(), result.stderr
    assert "NOTE the plan keeps" not in result.stdout, result.stdout


def test_twins_come_before_coverage_and_name_executes_refusal(
        adopter, monkeypatch, tmp_path):
    """r1189's SHOULD 6: beside a path no entry covers, `plan-case-twins`
    is listed before `plan-uncovered`, as a rename in the source is their
    first fix, and so it is the code of `execute`'s refusal."""
    source = a_source(tmp_path)
    with_paths(source, ("A", "a", "z"), own_blobs=True)
    plan = planned(source, tmp_path, {"A": ROOT, "a": ROOT, "z": ROOT})
    lines = plan.read_bytes().decode().splitlines(keepends=True)
    start = lines.index("  - path: z\n")
    end = start + 1
    while lines[end].startswith("    "):
        end += 1
    plan.write_bytes("".join(lines[:start] + lines[end:]).encode())
    assert [code for code, _ in findings(plan)] == [PLAN_CASE_TWINS,
                                                    "plan-uncovered"]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == PLAN_CASE_TWINS


#: `(the paths a source commit gains, all with one blob, or each with its
#: own, the plan's answers, the finding, the NOTE)`: r1189's SHOULD 5. A
#: set of one name whose paths hold one blob in one mode is checked out as
#: one path holding what each holds, and no path is lost; its own blobs
#: lose one. A file against a folder is the finding with one blob too. In
#: the root the NOTE takes only two paths whose names differ only in their
#: last part (r1189b's SHOULD 1): on a disk that ignores case, folder twins
#: and three paths of one blob there met git's `will not add file alias`,
#: and in a leg they verified.
ONE_BLOB = [
    pytest.param(("A", "a"), False, {"A": ROOT, "a": ROOT}, [],
                 [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                 "`A` and `a`")],
                 id="one-blob"),
    pytest.param(("A", "a"), True, {"A": ROOT, "a": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`")],
                 [], id="two-blobs"),
    pytest.param(("src/AB", "src/Ab", "src/ab"), False, {}, [],
                 [one_blob_twins("1 set", CODE_TWINS, "3 paths",
                                 "`src/AB`, `src/Ab` and `src/ab`")],
                 id="one-blob-in-the-code-leg"),
    pytest.param(("F/x", "f"), False, {"F/": ROOT, "f": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`F/x` and `f`")],
                 [], id="a-folder-and-a-file-with-one-blob"),
    pytest.param(("D/x", "d/x"), False, {"D/": ROOT, "d/": ROOT},
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`D/x` and `d/x`")],
                 [], id="folder-twins-of-one-blob-in-the-root"),
    pytest.param(("AB", "Ab", "ab"), False,
                 dict.fromkeys(("AB", "Ab", "ab"), ROOT),
                 [twins_kept("1 set", ROOT_TWINS, "3 paths",
                             "`AB`, `Ab` and `ab`")],
                 [], id="three-of-one-blob-in-the-root"),
    pytest.param(("D/A", "D/a"), False, {"D/": ROOT}, [],
                 [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                 "`D/A` and `D/a`")],
                 id="two-of-one-blob-in-one-folder-of-the-root"),
    pytest.param(("src/D/x", "src/d/x"), False, {}, [],
                 [one_blob_twins("1 set", CODE_TWINS, "2 paths",
                                 "`src/D/x` and `src/d/x`")],
                 id="folder-twins-of-one-blob-in-the-code-leg"),
    # The spec leg takes the NOTE as the code leg does: only the root asks
    # for two paths in one folder.
    pytest.param(("specs/D/x", "specs/d/x"), False, {}, [],
                 [one_blob_twins("1 set", SPEC_TWINS, "2 paths",
                                 "`specs/D/x` and `specs/d/x`")],
                 id="folder-twins-of-one-blob-in-the-spec-leg"),
    # A file against a folder in a leg, one blob and one last name: the
    # whole paths fold to two names, so it is the finding there too.
    pytest.param(("src/F/f", "src/f"), False, {},
                 [twins_kept("1 set", CODE_TWINS, "2 paths",
                             "`src/F/f` and `src/f`")],
                 [], id="a-folder-and-a-file-of-one-blob-in-the-code-leg"),
]


@pytest.mark.parametrize(("paths", "own_blobs", "answers", "found", "noted"),
                         ONE_BLOB)
def test_a_set_of_one_blob_is_a_note_and_not_the_finding(
        tmp_path, paths, own_blobs, answers, found, noted):
    source = a_source(tmp_path)
    with_paths(source, paths, own_blobs=own_blobs)
    result = checked(planned(source, tmp_path, answers))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == (1 if found else 0), result.stderr
    assert finding_lines(result) == found
    assert [line for line in result.stdout.splitlines()
            if line.startswith("NOTE the plan keeps")] == noted
    assert ("plan ok" in result.stdout) is not found, result.stdout
    assert (TWINS_REMEDY in result.stderr) is bool(found), result.stderr


def asked_of(adopter, rows: list[tuple[str, str, str]], leg: str = ROOT):
    """`_case_twin_findings` over a tree of `(path, mode, object)` rows, the
    plan keeping each in the repository `leg:` `leg` sends it to, the root
    unless named: its findings and NOTEs, no remediation but where there is
    a finding."""
    plan = SimpleNamespace(entries=[{"path": path, "leg": leg}
                                    for path, _, _ in rows])
    found, remedies, notes = adopter._case_twin_findings(
        plan, [(path, mode, oid, 1) for path, mode, oid in rows])
    assert remedies == ([TWINS_REMEDIATION] if found else [])
    return found, notes


ONE = "1" * 40
OTHER = "2" * 40


#: `(the tree's rows, the findings, the NOTEs)`: one blob in one mode,
#: asked of the function itself, as `with_paths` writes no mode but a
#: file's or a symlink's.
ONE_BLOB_ROWS = [
    pytest.param([("A", "100644", ONE), ("a", "100755", ONE)],
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`")],
                 [], id="one-blob-in-two-modes"),
    pytest.param([("A", "160000", ONE), ("a", "160000", ONE)],
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`")],
                 [], id="submodules-at-one-commit"),
    pytest.param([("A", "120000", ONE), ("a", "120000", ONE)], [],
                 [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                 "`A` and `a`")],
                 id="symlinks-to-one-target"),
    pytest.param([("AB", "100644", ONE), ("Ab", "100644", ONE),
                  ("ab", "100644", OTHER)],
                 [twins_kept("1 set", ROOT_TWINS, "3 paths",
                             "`AB`, `Ab` and `ab`")],
                 [], id="one-of-three-another-blob"),
    pytest.param([("A", "100644", ONE), ("B", "100644", ONE),
                  ("a", "100644", ONE), ("b", "100644", OTHER)],
                 [twins_kept("1 set", ROOT_TWINS, "2 paths", "`B` and `b`")],
                 [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                 "`A` and `a`")],
                 id="a-set-of-each-in-one-repository"),
    pytest.param([("A", "100644", ONE), ("B", "100644", OTHER),
                  ("a", "100644", ONE), ("b", "100644", OTHER)], [],
                 [one_blob_twins("2 sets", ROOT_TWINS, "4 paths",
                                 "`A`, `a`, `B` and `b`")],
                 id="two-sets-of-one-blob-set-by-set"),
    # One name as `casefold` folds it, as the set itself was folded.
    pytest.param([("STRASSE", "100644", ONE), ("straße", "100644", ONE)],
                 [], [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                     "`STRASSE` and `straße`")],
                 id="sharp-s-and-ss-of-one-blob"),
    # Two paths in the root whose names differ in their folder AND their
    # last part are not the NOTE's shape: their folders are twins too.
    pytest.param([("D/A", "100644", ONE), ("d/a", "100644", ONE)],
                 [twins_kept("1 set", ROOT_TWINS, "2 paths",
                             "`D/A` and `d/a`")],
                 [], id="two-of-one-blob-in-folders-in-another-case"),
]


@pytest.mark.parametrize(("rows", "found", "noted"), ONE_BLOB_ROWS)
def test_only_one_blob_in_one_mode_is_left_to_the_note(adopter, rows, found,
                                                       noted):
    assert asked_of(adopter, rows) == (found, noted)


@pytest.mark.parametrize("mode", ["100755", "120000"],
                         ids=["executable", "symlink"])
def test_every_path_of_a_leg_set_is_asked_its_mode(adopter, mode):
    """Three paths of one name and one blob in the code leg, the last of
    them an executable or a symlink: the set holds two modes, so it is the
    finding, and no NOTE, whichever path differs."""
    rows = [("src/AB", "100644", ONE), ("src/Ab", "100644", ONE),
            ("src/ab", mode, ONE)]
    assert asked_of(adopter, rows, "code") == (
        [twins_kept("1 set", CODE_TWINS, "3 paths",
                    "`src/AB`, `src/Ab` and `src/ab`")], [])


def test_the_one_blob_note_is_the_first_of_the_entries_notes(
        adopter, monkeypatch, tmp_path):
    """`_entry_findings` lists the twins' NOTE before the pins' NOTEs, as it
    lists their finding before the pins' findings."""
    source = a_source(tmp_path)
    with_paths(source, ("A", "a"))
    plan = adopter.Plan.load(planned(source, tmp_path, {"A": ROOT, "a": ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    monkeypatch.setattr(adopter, "_pin_digest_findings",
                        lambda _plan: ([], ["NOTE a pin's"]))
    found, _, notes = adopter._entry_findings(plan, opened)
    assert found == []
    assert notes == [one_blob_twins("1 set", ROOT_TWINS, "2 paths",
                                    "`A` and `a`"), "NOTE a pin's"]


#: `(the paths, the answers)` of sources no repository the split makes holds
#: twins of, and `check` finds nothing in, on 4c7b8acd and now.
NO_TWINS_KEPT = [
    pytest.param(("A", "a", "D/x", "d/x"),
                 {"A": ROOT, "a": "code", "D/": ROOT, "d/": "code"},
                 id="twins-in-different-repositories"),
    pytest.param(("A", "a"), {"A": ROOT, "a": "drop"}, id="a-twin-dropped"),
    pytest.param(("D/x", "d/y"), {"D/": ROOT, "d/": ROOT},
                 id="folders-in-another-case-holding-other-names"),
    pytest.param(("A", "b", "D/x", "e/x"),
                 {"A": ROOT, "b": ROOT, "D/": ROOT, "e/": ROOT},
                 id="no-twins"),
]


@pytest.mark.parametrize(("paths", "answers"), NO_TWINS_KEPT)
def test_paths_no_one_repository_holds_as_one_name_are_no_finding(
        tmp_path, paths, answers):
    """Folders in another case merge into one whose names differ, and no
    path is lost. Twins the plan sends to different repositories, and a
    twin it drops beside one it keeps, are not this finding, which asks one
    repository at a time (r1189's SHOULD 3). On a disk that ignores case
    `execute` lost them, as `adopt-lost` after both legs were pushed, until
    #1183: it keeps them now (the rows under #1183 below)."""
    source = a_source(tmp_path)
    with_paths(source, paths, own_blobs=True)
    assert findings(planned(source, tmp_path, answers)) == []


def test_a_twin_still_unanswered_is_named_by_plan_unresolved_alone(
        tmp_path):
    """`a` still has `leg: null`: `plan-unresolved` names it, and no set is
    named while one of its twins goes nowhere yet."""
    source = a_source(tmp_path)
    with_paths(source, ("A", "a"), own_blobs=True)
    result = checked(planned(source, tmp_path, {"A": ROOT}))
    assert result.returncode == 1, result.stderr
    assert codes(result) == ["plan-unresolved"], result.stderr
    assert TWINS_REMEDY not in result.stderr, result.stderr


def test_execute_refuses_case_twins_before_any_leg(adopter, monkeypatch,
                                                   tmp_path):
    """The set measured to stop `execute` after both legs were pushed."""
    source = a_source(tmp_path)
    with_paths(source, ("F/x", "f"), own_blobs=True)
    refusal = refused_before_any_leg(
        adopter, monkeypatch,
        planned(source, tmp_path, {"F/": ROOT, "f": ROOT}), tmp_path)
    assert refusal.code == PLAN_CASE_TWINS
    assert TWINS_REMEDY in refusal.remediation


def test_execute_takes_sets_of_one_blob_past_checks_findings(
        adopter, monkeypatch, tmp_path):
    """The NOTE is no refusal: a plan keeping sets of one blob in the root
    (`A`, `a`) and in the code leg (`src/A`, `src/a`) is `plan ok`, and
    `execute` goes on past `check`'s findings to its next step, which a
    sentinel stops here before any leg exists."""
    source = a_source(tmp_path)
    with_paths(source, ("A", "a", "src/A", "src/a"))
    plan = planned(source, tmp_path, {"A": ROOT, "a": ROOT})
    assert findings(plan) == []

    class NextStep(Exception):
        """`execute` reached the step after `_refuse_what_check_finds`."""

    def next_step(*_args):
        raise NextStep

    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(adopter, "_refuse_symlinks_checked_out_as_files",
                        next_step)
    remotes = tmp_path / "remotes"
    with pytest.raises(NextStep):
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert not remotes.exists()


def test_on_a_disk_that_ignores_case_check_names_the_twins_too(tmp_path):
    """The rows above ask nothing of the disk, and `plan-case-twins` asks
    nothing of it either. This row runs `check` with its work directory on
    the disk `git init` is asked about, and is skipped where that disk keeps
    case, as every CI disk does (CI is Linux only since #597)."""
    work = tmp_path / "work"
    git("init", "-q", str(work / "probe"), cwd=tmp_path)
    if git("config", "--local", "--get", "core.ignorecase",
           cwd=work / "probe", check=False).stdout.strip() != "true":
        pytest.skip("needs a disk that ignores case: `git init` wrote no "
                    "`core.ignorecase=true` in the work directory, so that "
                    "disk keeps case; the rows above find the twins on "
                    "every disk")
    source = a_source(tmp_path)
    with_paths(source, ("A", "a"), own_blobs=True)
    result = checked(planned(source, tmp_path, {"A": ROOT, "a": ROOT}), None,
                     "--work-dir", str(work / "check"))
    assert finding_lines(result) == [
        twins_kept("1 set", ROOT_TWINS, "2 paths", "`A` and `a`")]


# ---------------------------------------------------------------------------
# #1183: case twins the plan sends into different repositories, or drops
# ---------------------------------------------------------------------------

#: The branch `_commit_the_split` checks the assembly out on.
SPLIT_BRANCH = "adopt/three-repo-shape"
#: The two legs as `_mount_the_legs` finds them in the work directory.
LEG_NAMES = {"spec": "Northwind-spec", "code": "Northwind-code"}
#: What the mount adds to the root's index: its two gitlinks and the file
#: that registers them.
MOUNTED = (".gitmodules", "spec", "code")
#: `git rm` of one path, as `_mount_the_legs` runs it, and with `-f`.
REMOVED_AS = ["git", "--literal-pathspecs", "rm", "-r", "-q", "--"]
FORCED_AS = ["git", "--literal-pathspecs", "rm", "-r", "-q", "-f", "--"]
#: How the mount writes the twins the root keeps back from the index.
WRITTEN_AS = ["git", "checkout-index", "-f", "-z", "--stdin"]


def at_or_under(path: str, top: str) -> bool:
    return path == top or path.startswith(top + "/")


def z_rows(repository: Path, *args: str) -> list[str]:
    """The rows `git <args>` prints in `repository`, each ended by a NUL,
    decoded as `_git_path` decodes a path: a byte that is not UTF-8 kept as
    a surrogate, which `git`'s text would refuse."""
    raw = subprocess.run(["git", *args], cwd=str(repository),
                         capture_output=True, check=True).stdout
    return [row.decode("utf-8", "surrogateescape")
            for row in raw.split(b"\0") if row]


def an_assembly(base: Path, paths: tuple[str, ...],
                add=with_paths) -> tuple[Path, dict]:
    """`(assembly, blobs)`: `a_source` whose commit gains `paths` by `add`,
    each with a blob of its own, cloned into `base/work` as
    `_commit_the_split` clones it, with no template and the split branch
    checked out at that commit, beside the two legs; `blobs` holds each
    path of that commit's tree and its blob."""
    source = a_source(base)
    add(source, paths, own_blobs=True)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    work = base / "work"
    assembly = work / "Northwind"
    git("clone", "-q", "--template=", str(source), str(assembly), cwd=base)
    git("checkout", "-q", "-B", SPLIT_BRANCH, commit, cwd=assembly)
    for role, name in LEG_NAMES.items():
        make_source_repo(work / name, tree={"file.txt": role}, edits=())
    return assembly, {row.split("\t", 1)[1]: row.split()[2]
                      for row in z_rows(source, "ls-tree", "-r", "-z",
                                        commit)}


def as_one_file(assembly: Path, sets: tuple[tuple[str, ...], ...]) -> None:
    """What a clone on a disk that ignores case checks out of each of
    `sets`, made on a disk that keeps case: ONE FILE, holding the bytes of
    the twin git wrote last, the last of the set in the index's order, as
    #1183's trace measured. Each other twin is made a hard link to that
    twin's file, so the twins share one file as they do there. Where the
    clone's own disk ignores case, git did this itself, and nothing is
    done."""
    if git("config", "--get", "core.ignorecase", cwd=assembly,
           check=False).stdout.strip() == "true":
        return
    for named in sets:
        *others, last = named
        for twin in others:
            (assembly / twin).unlink()
            os.link(assembly / last, assembly / twin)


def mounted(adopter, base: Path, assembly: Path, moved: dict) -> None:
    """`_mount_the_legs` of `assembly`, `moved` its `paths_for`, then the
    `git add -A -- .` that `_stage_the_split` begins with."""
    work = base / "work"
    adopter._mount_the_legs(
        assembly, work, LEG_NAMES,
        {role: str(work / name) for role, name in LEG_NAMES.items()},
        {"spec": [], "code": [], "drop": [], **moved}, "spec", "code")
    git("add", "-A", "--", ".", cwd=assembly)


def staged(assembly: Path) -> dict:
    """Each path the assembly's index holds but the mount's own, and its
    object."""
    held = {row.split("\t", 1)[1]: row.split()[1]
            for row in z_rows(assembly, "ls-files", "-s", "-z")}
    return {path: oid for path, oid in held.items() if path not in MOUNTED}


#: `(the paths a source commit gains, each with a blob of its own, the sets
#: of them a disk that ignores case holds as one, each in the index's
#: order, and the paths the plan sends to a leg or drops, by `leg:`)`.
#: Measured on 4d40ce9f on such a disk, `execute` stopped after both legs
#: were pushed: as `adopt-lost` for the twin the root keeps where the twin
#: that goes sorts last (`across`, `dropped`, `a-folder-kept-beside-a-file`),
#: and `REFUSED mounting the legs` at `git rm` where it sorts first.
SPLIT_TWINS = [
    pytest.param(("A", "a", "D/x", "d/x"), (("A", "a"), ("D/x", "d/x")),
                 {"code": ["a", "d/"]}, id="across"),
    pytest.param(("A", "a", "D/x", "d/x"), (("A", "a"), ("D/x", "d/x")),
                 {"code": ["A", "D/"]}, id="across-the-other-way"),
    pytest.param(("A", "a"), (("A", "a"),), {"drop": ["a"]}, id="dropped"),
    pytest.param(("A", "a"), (("A", "a"),), {"drop": ["A", "a"]},
                 id="both-dropped"),
    pytest.param(("A", "a"), (("A", "a"),), {"spec": ["A"], "code": ["a"]},
                 id="one-to-each-leg"),
    pytest.param(("F/x", "f"), (("F/x", "f"),), {"code": ["f"]},
                 id="a-folder-kept-beside-a-file"),
]


@pytest.mark.parametrize(("paths", "sets", "moved"), SPLIT_TWINS)
def test_the_mount_keeps_each_twin_the_root_keeps_with_its_own_blob(
        adopter, tmp_path, paths, sets, moved):
    """The twins share one file, as on a disk that ignores case. On
    4d40ce9f the mount's `git rm` refused that file as a local
    modification where the twin that goes sorts first, and elsewhere the
    root kept the other twin's bytes (on such a disk, none: the one file
    was gone). Now the root's index holds each path the plan keeps there,
    each with its own blob, and no path the plan moved or dropped."""
    assembly, blobs = an_assembly(tmp_path, paths)
    as_one_file(assembly, sets)
    mounted(adopter, tmp_path, assembly, moved)
    removed = [path.rstrip("/") for leg in moved.values() for path in leg]
    assert staged(assembly) == {
        path: oid for path, oid in blobs.items()
        if not any(at_or_under(path, top) for top in removed)}


def git_commands_of_the_mount(adopter, monkeypatch, base: Path,
                              assembly: Path, moved: dict) -> list:
    """`(command, input)` of each `git rm` and `git checkout-index` that
    `mounted` runs, in order, each command as text."""
    ran = []
    real = subprocess.run

    def recorded(command, *args, **named):
        words = [os.fsdecode(word) for word in command]
        if "rm" in words[:3] or "checkout-index" in words[:2]:
            ran.append((words, named.get("input")))
        return real(command, *args, **named)

    monkeypatch.setattr(subprocess, "run", recorded)
    mounted(adopter, base, assembly, moved)
    monkeypatch.undo()
    return ran


def test_a_source_with_no_twin_set_split_is_mounted_as_before(
        adopter, monkeypatch, tmp_path):
    """`AB` and `ab` are twins the root keeps both of, and `a` goes to the
    code leg: no set has a path at or under a path that goes (`a` is no
    folder above `ab`), so each path is removed as on 4d40ce9f, without
    `-f`, and nothing is written back from the index."""
    assembly, _ = an_assembly(tmp_path, ("AB", "a", "ab", "b/x"))
    assert git_commands_of_the_mount(
        adopter, monkeypatch, tmp_path, assembly,
        {"code": ["a"], "drop": ["b/"]}) == [
            ([*REMOVED_AS, "a"], None), ([*REMOVED_AS, "b"], None)]


def test_only_a_path_a_twin_is_at_or_under_is_removed_with_f(
        adopter, monkeypatch, tmp_path):
    """`a` and `b` go to the code leg, and `A`, the twin of `a`, stays in
    the root: `a` alone is removed with `-f`, and `A` alone is written back
    from the index, after the last `git rm`. On 4d40ce9f neither was."""
    assembly, _ = an_assembly(tmp_path, ("A", "a", "b"))
    assert git_commands_of_the_mount(
        adopter, monkeypatch, tmp_path, assembly, {"code": ["a", "b"]}) == [
            ([*FORCED_AS, "a"], None), ([*REMOVED_AS, "b"], None),
            (WRITTEN_AS, b"A\0")]


def test_a_path_git_cannot_write_back_is_refused_naming_the_command(
        adopter, tmp_path):
    """`_write_from_the_index` of a path the index does not hold: git
    refuses it, and the mount raises `CommandFailed`, one of
    `LATE_FAILURES`, naming the command and carrying what git said, as
    `_git_rm` does."""
    assembly, _ = an_assembly(tmp_path, ("A",))
    with pytest.raises(adopter.CommandFailed) as caught:
        adopter._write_from_the_index(assembly, ["nowhere"])
    assert caught.value.args_list == WRITTEN_AS
    assert caught.value.code != 0
    assert "nowhere" in caught.value.output


def test_a_forced_git_rm_git_refuses_is_refused_naming_it_with_f(
        adopter, tmp_path):
    """`_git_rm` with `forced` of a path the index does not hold: git
    refuses it, and the mount raises `CommandFailed` naming the command it
    ran, with `-f`, as `execute` prints it after both legs exist."""
    assembly, _ = an_assembly(tmp_path, ("A",))
    with pytest.raises(adopter.CommandFailed) as caught:
        adopter._git_rm(assembly, "nowhere", True)
    assert caught.value.args_list == [*FORCED_AS, "nowhere"]
    assert caught.value.code != 0
    assert "nowhere" in caught.value.output


#: Case twins whose names hold the byte E9, which is not UTF-8, each spelled
#: as `_git_path` spells it: that byte as the surrogate U+DCE9.
NOT_UTF8_TWINS = ("caf\udce9A", "caf\udce9a")


def with_names_not_utf8(repository: Path, paths: tuple[str, ...],
                        own_blobs: bool = True) -> None:
    """`with_paths` for names that are not UTF-8, which it hands `git
    mktree` as text: each of `paths` goes into the index as the bytes it
    spells, with a blob of its own holding those bytes and a newline, and
    the index is committed on `main`."""
    assert own_blobs
    for path in paths:
        name = path.encode("utf-8", "surrogateescape")
        blob = blob_of(repository, name + b"\n")
        subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                        b"100644," + blob.encode("ascii") + b"," + name],
                       cwd=str(repository), check=True)
    git("commit", "-qm", "Add paths", cwd=repository)


def test_twins_whose_names_are_not_utf_8_keep_their_own_blobs(
        adopter, tmp_path):
    """`caf<E9>A` kept in the root and `caf<E9>a` sent to the code leg, the
    byte E9 not UTF-8, sharing one file: the mount reads the index's names
    as bytes, and hands the twin it writes back to git as the bytes the
    tree holds, so the root's index holds that twin with its own blob. A
    listing decoded, or a name encoded, as strict UTF-8 raises a
    `UnicodeError` there, after both legs are pushed."""
    try:
        os.close(os.open(os.fsencode(tmp_path) + b"/caf\xe9",
                         os.O_CREAT | os.O_WRONLY, 0o644))
    except (OSError, ValueError):
        pytest.skip("this disk, or this platform, takes no file name that "
                    "is not UTF-8")
    kept, moved = NOT_UTF8_TWINS
    assembly, blobs = an_assembly(tmp_path, NOT_UTF8_TWINS,
                                  with_names_not_utf8)
    as_one_file(assembly, (NOT_UTF8_TWINS,))
    mounted(adopter, tmp_path, assembly, {"code": [moved]})
    assert kept in blobs
    assert staged(assembly) == {path: oid for path, oid in blobs.items()
                                if path != moved}


needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def executed(base: Path, paths: tuple[str, ...], answers: dict):
    """`execute` of a plan for `a_source` whose commit gains `paths`, each
    with a blob of its own, `answers` given, with its legs under
    `--local-remote-dir` and its work directory in `base`."""
    source = a_source(base)
    with_paths(source, paths, own_blobs=True)
    plan = planned(source, base, answers)
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))


def assert_adopted(result) -> None:
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout, result.stdout


#: `(the paths, the plan's answers)`, run whole. On 4d40ce9f, on a disk
#: that ignores case, `execute` exited 1 with `adopt-lost` for `A` and
#: `D/x` (`across`) and `A` (`dropped`), and 2 with `REFUSED mounting the
#: legs` (`across-the-other-way`, `one-to-each-leg`), each after both legs
#: and, for `adopt-lost`, the split were pushed.
SPLIT_EXECUTED = [
    pytest.param(("A", "a", "D/x", "d/x"),
                 {"A": ROOT, "a": "code", "D/": ROOT, "d/": "code"},
                 id="across"),
    pytest.param(("A", "a", "D/x", "d/x"),
                 {"A": "code", "a": ROOT, "D/": "code", "d/": ROOT},
                 id="across-the-other-way"),
    pytest.param(("A", "a"), {"A": ROOT, "a": "drop"}, id="dropped"),
    pytest.param(("A", "a"), {"A": "spec", "a": "code"},
                 id="one-to-each-leg"),
]


@needs_filter_repo
@pytest.mark.parametrize(("paths", "answers"), SPLIT_EXECUTED)
def test_on_a_disk_that_ignores_case_execute_keeps_twins_it_splits(
        tmp_path, paths, answers):
    """`execute` whole, its work directory and its legs on the disk `git
    init` is asked about; skipped where that disk keeps case, as every CI
    disk does (CI is Linux only since #597), where the rows above make the
    one file themselves."""
    probe = tmp_path / "probe"
    git("init", "-q", str(probe), cwd=tmp_path)
    if git("config", "--local", "--get", "core.ignorecase", cwd=probe,
           check=False).stdout.strip() != "true":
        pytest.skip("needs a disk that ignores case: `git init` wrote no "
                    "`core.ignorecase=true` in the work directory, so that "
                    "disk keeps case; the rows that drive the mount make "
                    "each set one file on every disk")
    assert_adopted(executed(tmp_path, paths, answers))


@needs_filter_repo
def test_execute_adopts_twins_it_sends_to_different_repositories(tmp_path):
    """The control, on any disk: `A` and `D/x` kept in the root, `a` and
    `d/x` sent to the code leg, `execute` whole. On a disk that keeps case
    it was adopted on 4d40ce9f too, and it still is."""
    assert_adopted(executed(tmp_path, ("A", "a", "D/x", "d/x"),
                            {"A": ROOT, "a": "code", "D/": ROOT,
                             "d/": "code"}))


# ---------------------------------------------------------------------------
# L1-92: in the work directory
# ---------------------------------------------------------------------------

def test_each_throwaway_repository_is_made_in_the_work_directory(
        adopter, monkeypatch, tmp_path):
    """The source keeps a nested `.gitattributes` above a pinned copy and
    its own root one, so all three questions are asked: each throwaway
    repository is made in the work directory the source was opened in, not
    in `TMPDIR`, and none is left there."""
    plan = adopter.Plan.load(adoption_plan(tmp_path, github(YML_CRLF),
                                           KEEP_GITHUB))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    made = []

    def mkdtemp(suffix=None, prefix=None, dir=None):
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        made.append((prefix, Path(path).parent.resolve()))
        return path

    monkeypatch.setattr(adopter, "tempfile", SimpleNamespace(
        mkdtemp=mkdtemp, gettempdir=tempfile.gettempdir,
        TemporaryDirectory=tempfile.TemporaryDirectory))
    found, _, _ = adopter._entry_findings(plan, opened)
    assert any(line.startswith("FINDING plan-nested-attributes: ")
               for line in found), found
    asked = [(prefix, parent) for prefix, parent in made
             if prefix in THROWAWAY_PREFIXES]
    assert {prefix for prefix, _ in asked} == set(THROWAWAY_PREFIXES)
    assert {parent for _, parent in asked} == {work.resolve()}
    assert list(work.iterdir()) == []


# ---------------------------------------------------------------------------
# L1-94: no hook of this machine's
# ---------------------------------------------------------------------------

def counting_hooks(base: Path) -> tuple[Path, Path]:
    """`(hooks, log)`: a directory of `HOOKS`, each adding its name to
    `log` as a line each time git runs it."""
    hooks = base / "hooks"
    hooks.mkdir()
    log = base / "hook-runs.log"
    for name in HOOKS:
        hook = hooks / name
        hook.write_bytes(f"#!/bin/sh\necho {name} >> '{log.as_posix()}'\n"
                         .encode())
        hook.chmod(0o755)
    return hooks, log


def runs(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() \
        if log.exists() else []


def in_the_global_config(base: Path, hooks: Path) -> dict:
    return config_with(base, "[core]", f'\thooksPath = "{hooks.as_posix()}"')


def in_the_command_scope(_base: Path, hooks: Path) -> dict:
    return appended_to_command_scope(os.environ,
                                     [("core.hooksPath", hooks.as_posix())])


@pytest.mark.parametrize("configured", [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count")])
def test_no_hook_of_this_machines_runs_in_a_throwaway_repository(
        tmp_path, configured):
    """The source keeps its own root `.gitattributes`, so #619's question
    of `git add` is asked as well as the rehearsal's: on c7a3ff16 the
    global config's hook ran 12 times in this `check`."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: b"*.md text\n"}),
                   tmp_path, {})
    hooks, log = counting_hooks(tmp_path)
    result = checked(plan, configured(tmp_path, hooks))
    assert result.returncode == 0, result.stderr
    assert runs(log) == []


@pytest.mark.parametrize("configured", [
    pytest.param(in_the_global_config, id="global-config"),
    pytest.param(in_the_command_scope, id="git-config-count")])
def test_the_counting_hook_runs_where_this_machines_config_reaches(
        tmp_path, configured):
    """The control: the same config runs the hook in a repository of its
    own, so the row above counts something that would run."""
    hooks, log = counting_hooks(tmp_path)
    repository = tmp_path / "ordinary"
    git("init", "-q", str(repository), cwd=tmp_path)
    (repository / "a").write_bytes(b"a\n")
    subprocess.run(["git", "add", "a"], cwd=str(repository), check=True,
                   env={**os.environ, **configured(tmp_path, hooks)})
    assert runs(log) == ["post-index-change"]


# ---------------------------------------------------------------------------
# L1-32: the symlink probe's own failure
# ---------------------------------------------------------------------------

def linked_github_plan(base: Path) -> Path:
    """A plan that keeps `.github`, a symlink climbing out of the root, in
    the root: `check`'s finding for it asks the probe (#531)."""
    _, plan = planned_with_links(base, {}, {GITHUB: OUTSIDE_CI},
                                 {GITHUB: ROOT})
    return plan


NO_PROBE_NOTE = "NOTE `check` could not ask git whether it checks a symlink"


def test_a_probe_git_will_not_make_stands_for_its_finding(
        links_as_links, tmp_path):  # noqa: F811
    """`GIT_DEFAULT_HASH=bogus` makes the probe's `git init` fail, and only
    it: each throwaway repository names its format. `check` prints the
    finding the probe stands for, as it does with no such variable, and
    says why in a NOTE."""
    result = checked(linked_github_plan(tmp_path),
                     {"GIT_DEFAULT_HASH": "bogus"})
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert symlink_findings(result) == [
        finding(GITHUB, OUTSIDE_CI, WORKFLOW, climbs(GITHUB))]
    assert NO_PROBE_NOTE in result.stdout, result.stdout
    assert "unknown hash algorithm 'bogus'" in result.stdout, result.stdout


def test_a_probe_git_makes_prints_the_same_finding_and_no_note(
        links_as_links, tmp_path):  # noqa: F811
    """The control: the same plan, with no such variable."""
    result = checked(linked_github_plan(tmp_path))
    assert result.returncode == 1, result.stderr
    assert symlink_findings(result) == [
        finding(GITHUB, OUTSIDE_CI, WORKFLOW, climbs(GITHUB))]
    assert NO_PROBE_NOTE not in result.stdout


@pytest.mark.parametrize("failure", [
    pytest.param(lambda adopter: adopter.CommandFailed(
        ["git", "init", "-q", "probe"], None, 128,
        "fatal: unknown hash algorithm 'bogus'"), id="command-failed"),
    pytest.param(lambda adopter: adopter.Refusal(
        "git-failed", "`git init` exited 128: fatal: unknown hash "
        "algorithm 'bogus'"), id="refusal")])
def test_the_probe_takes_a_failed_git_init_as_a_disk_with_symlinks(
        adopter, monkeypatch, tmp_path, failure):
    def refused(_work_root):
        raise failure(adopter)

    monkeypatch.setattr(adopter, "_checks_out_symlinks", refused)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.symlinks() is True
    notes = probe.notes()
    assert len(notes) == 1, notes
    assert "fatal: unknown hash algorithm 'bogus'" in notes[0]


def test_a_work_directory_the_probe_cannot_write_gives_no_note(
        adopter, monkeypatch, tmp_path):
    """An `OSError` is `adopt-work-dir-unwritable`'s to say (#524), and the
    probe adds no NOTE of its own."""
    def unwritable(_work_root):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(adopter, "_checks_out_symlinks", unwritable)
    probe = adopter._SymlinkProbe(tmp_path)
    assert probe.symlinks() is True
    assert probe.notes() == []


# ---------------------------------------------------------------------------
# A throwaway repository git cannot make or ask: `adopt-git-unasked`
# ---------------------------------------------------------------------------

def bad_default_branch(base: Path) -> dict:
    """A global config whose `init.defaultBranch` git will not take."""
    return config_with(base, "[init]", "\tdefaultBranch = a..b")


#: What the stub `git` of `refusing_init` says for each throwaway `git init`.
REFUSED_INIT = "fatal: r1031: no repository can be made here"


def refusing_init(base: Path) -> dict:
    """The environment of a git that makes no throwaway repository: a stub
    first on PATH refuses each `git init` given a `--template`, as every one
    `check` makes is given one, and hands any other command to the real git.
    Which setting stops a `git init` is git's version's to say (CI on
    #1031), so the rows below do not lean on one."""
    stubs = base / "stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes("\n".join([
        "#!/bin/sh",
        'for arg in "$@"; do',
        '  case "$arg" in --template=*) ;; *) continue ;; esac',
        '  for word in "$@"; do',
        '    [ "$word" = init ] || continue',
        f'    echo "{REFUSED_INIT}" >&2',
        "    exit 128",
        "  done",
        "done",
        'exec "$REAL_GIT" "$@"', ""]).encode("ascii"))
    stub.chmod(0o755)
    return {"PATH": str(stubs) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git")}


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_a_repository_git_cannot_make_is_one_finding_that_says_why(
        tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    work = tmp_path / "work"
    result = checked(plan, refusing_init(tmp_path), "--work-dir", str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert finding_lines(result) == [
        f"FINDING {UNASKED}: " + UNASKED_OPENS.format(os.path.realpath(work))
        + f"`git init` there exited 128: {REFUSED_INIT}" + UNASKED_ENDS]
    assert list(work.iterdir()) == []


def test_a_default_branch_git_will_not_take_stops_no_question(tmp_path):
    """Each throwaway `git init` names its branch, as the split's own `git
    init -b` does, so `init.defaultBranch = a..b` stops none of `check`'s
    questions, on any git: the CRLF file the plan keeps is found. Read, it
    was `adopt-git-unasked`, which `execute` refused, though git 2.55's
    `git clone`, which CI runs, does not stop at it (CI on #1031)."""
    plan = planned(a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF,
                                             NOTES: CRLF}),
                   tmp_path, {NOTES: ROOT})
    work = tmp_path / "work"
    result = checked(plan, bad_default_branch(tmp_path), "--work-dir",
                     str(work))
    assert "REFUSED" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [REENCODED_FILES], result.stderr
    assert list(work.iterdir()) == []


@WINDOWS_SKIP  # a `#!` stub named `git` first on PATH
def test_execute_refuses_it_before_any_leg_exists(adopter, monkeypatch,
                                                 tmp_path):
    plan = planned(a_source(tmp_path), tmp_path, {})
    for name, value in refusing_init(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNASKED
    assert REFUSED_INIT in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert not remotes.exists()


def test_a_step_git_fails_in_the_rehearsal_is_one_finding_in_its_words(
        adopter, monkeypatch, tmp_path):
    """A step git fails in the rehearsal's repository once it is made, here
    its `read-tree` of the source commit, is `adopt-git-unasked` in git's
    words, in the place of the question asked there, and no `git-failed`
    refusal stops `check` (`_SplitRehearsal.asked`; r1031's SHOULD-2)."""
    plan = adopter.Plan.load(planned(
        a_source(tmp_path, files={ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}),
        tmp_path, {NOTES: ROOT}))
    work = tmp_path / "work"
    work.mkdir()
    opened = plan.open_source(None, work)
    real = adopter._SplitRehearsal.git

    def git(self, args, index, data=b""):
        if args[0] == "read-tree":
            return subprocess.CompletedProcess(args, 128, b"",
                                               b"fatal: r1031")
        return real(self, args, index, data)

    monkeypatch.setattr(adopter._SplitRehearsal, "git", git)
    try:
        found, _, _ = adopter._entry_findings(plan, opened)
    except adopter.Refusal as refusal:
        pytest.fail(f"REFUSED {refusal.code}: {refusal.detail}")
    assert len(found) == 1, found
    assert found[0].startswith(
        f"FINDING {UNASKED}: "
        + UNASKED_OPENS.format(os.path.realpath(work))
        + f"`git read-tree {opened.commit}` in "), found[0]
    assert "exited 128: fatal: r1031" in found[0]
    assert found[0].endswith(UNASKED_ENDS), found[0]
    assert list(work.iterdir()) == []


#: The NOTE `check` prints where no throwaway repository can be made in the
#: work directory at all; `{}` is that directory.
UNMADE_NOTE = ("NOTE `check` could not make a throwaway repository in `{}`, "
               "the work directory, to ask this machine's git what the split "
               "will make of the source: a directory or a file could not be "
               "made there (Permission denied). It asked nothing about the "
               "source's paths and files there; run `check` again with a "
               "--work-dir this user can write in.")


def test_a_work_directory_nothing_can_be_made_in_says_so_once(
        tmp_path, unwritable_work):  # noqa: F811
    """`adopt-work-dir-unwritable` names the directory (#524), the one
    finding for the one cause, as `check` asks it the same way, and a NOTE
    the questions it kept from being asked, where on c7a3ff16 they were
    asked in `TMPDIR`, another disk than the split's."""
    plan = planned(a_source(tmp_path), tmp_path, {})
    result = checked(plan, None, "--work-dir", str(unwritable_work))
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr
    assert codes(result) == [WORK_DIR_UNWRITABLE], result.stderr
    assert UNMADE_NOTE.format(os.path.realpath(unwritable_work)) in \
        result.stdout.splitlines(), result.stdout
