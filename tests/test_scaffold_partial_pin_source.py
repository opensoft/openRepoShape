# SPDX-License-Identifier: Apache-2.0
"""A partial-clone `--pin-source` is read, and never fetched into (#1182).

`scaffold-project.py --pin <product>@<commit> --pin-source <clone>` reads the
pin's digest with git in the clone: `git cat-file -t` of the commit, then
`git ls-tree -r` of it. In a partial clone (`git clone --filter`) git fetches
an object the clone lacks from its promisor remote on any read that needs
it. Measured on 961640c6 with git 2.43, the real run and `--dry-run` alike:
a `--filter=tree:0` clone, which holds the pinned commit and lacks its
trees, and a `--filter=blob:none` clone that lacks the pinned commit, each
ran the clone's `upload-pack` once and gained a promisor pack before the
digest was read, and the run went on to exit 0.

NOW THE PINS ARE READ WITH `GIT_NO_LAZY_FETCH=1` (`pin_values_unfetched`),
and such a clone is `pin-source-unreadable`, whose refusal says the clone is
a partial one and names `git fetch --refetch --no-filter <remote>`, which
makes it whole. Every row counts the clone's `upload-pack` runs with a
wrapper set as `remote.origin.uploadpack`, so "no fetch" is an answer: the
controls, which do read, count none either.

WHICH GIT HONOURS THE VARIABLE: git 2.45.0 and later, and the security
releases of 2024-05-14 back to 2.39.4. The rows that need it ask this git
first (`honoured`), and skip, saying why, where it is ignored.

NO NETWORK AND NO GITHUB. The origin is a folder on this machine, reached
over `file://`, and every run names `--pin-source`, so `gh` is never asked.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, ORG, REPO, SCAFFOLD,
                      clear_ambient_pin_sources, git, load_without_bytecode,
                      make_source_repo, run_script)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import tree_digest  # noqa: E402

#: The variable git reads to leave out a partial clone's fetch.
NO_LAZY_FETCH = "GIT_NO_LAZY_FETCH"
#: A name no git reads, put in its place to show what the variable does.
IGNORED_BY_GIT = "GIT_IGNORED_BY_GIT"
PROJECT = "MedxGlass"
PIN_FILE = Path(PROJECT) / "contracts" / "openglass-pin.yaml"

#: What each kind of `--pin-source` is: its `git clone` flags, and whether
#: the pin is the commit on `main`, which the clone holds, or the one on
#: `side`, which a `--single-branch` clone of `main` lacks.
KINDS = {
    "tree0": (("--filter=tree:0", "--no-checkout"), "main"),
    "lacks-commit": (("--filter=blob:none", "--no-checkout"), "side"),
    "full": ((), "main"),
    "blobnone": (("--filter=blob:none", "--no-checkout"), "main"),
    "blobnone-checkout": (("--filter=blob:none",), "main"),
    "full-lacks-commit": ((), "side"),
}

#: Where this git reads a partial clone's missing object with no fetch.
IGNORED = ("this git ignores GIT_NO_LAZY_FETCH (older than 2.45.0, and no "
           "security release of 2024-05-14): it fetches as before #1182")

PARTIAL = "That clone is a partial clone (`git clone --filter`)"
NEVER_FETCHES = "the scaffold never fetches into a --pin-source"
CURE = "`git fetch --refetch --no-filter origin`"
FETCH_ALL = "(`git fetch --all` first)"
NOTHING_MADE = ("Remediation: nothing was created, and `--dry-run` refuses "
                "the same. Make that clone whole, then run the scaffold "
                "again: in ")


@pytest.fixture(scope="module")
def glass(tmp_path_factory) -> dict:
    """A local stand-in for `openGlass` that serves a filtered clone:
    `main`, three commits, and `side`, one commit more. `digest` is the
    `main` commit's, as any reader of the whole tree gets it."""
    origin = make_source_repo(tmp_path_factory.mktemp("glass") / "openGlass")
    git("config", "uploadpack.allowFilter", "true", cwd=origin)
    main = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "-c", "side", cwd=origin)
    (origin / "side.txt").write_bytes(b"side\n")
    git("add", "side.txt", cwd=origin)
    git("commit", "-q", "-m", "On side alone", cwd=origin)
    side = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "main", cwd=origin)
    return {"origin": origin, "main": main, "side": side,
            "digest": tree_digest(origin, main)}


def clone_of(glass: dict, base: Path, kind: str) -> Path:
    """A `--single-branch` clone of `main` in `base`, as `kind` says, whose
    `upload-pack` runs are counted into `base`'s log (`upload_packs`)."""
    flags, _branch = KINDS[kind]
    clone = base / "openGlass"
    git(*FILE_PROTOCOL, "clone", "-q", "--single-branch", *flags,
        "--no-local", glass["origin"].as_uri(), str(clone), cwd=base)
    wrapper = base / "upload_pack.py"
    wrapper.write_text(
        "import subprocess, sys\n"
        f"with open({str(base / 'upload-pack.log')!r}, 'a', "
        "encoding='utf-8') as log:\n"
        "    log.write('ran\\n')\n"
        "sys.exit(subprocess.call(['git', 'upload-pack', *sys.argv[1:]]))\n",
        encoding="utf-8")
    git("config", "remote.origin.uploadpack",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(wrapper))}",
        cwd=clone)
    return clone


def upload_packs(base: Path) -> int:
    """How many times a clone in `base` ran its origin's `upload-pack`."""
    log = base / "upload-pack.log"
    if not log.exists():
        return 0
    return len(log.read_text(encoding="utf-8").splitlines())


def objects_of(clone: Path) -> dict:
    """Every file under the clone's `objects/`, by path, as its sha256: a
    fetch adds a pack and its `.promisor`."""
    objects = clone / ".git" / "objects"
    return {path.relative_to(objects).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in objects.rglob("*") if path.is_file()}


def pinned(glass: dict, kind: str) -> str:
    """The commit `kind`'s pin names."""
    return glass[KINDS[kind][1]]


def scaffold_argv(base: Path, source: Path, commit: str, *,
                  dry_run: bool) -> list:
    """The scaffold's command line: `--pin openGlass@<commit>` read in
    `source`, building in `base`."""
    return ["--org", ORG, "--project", PROJECT,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--pin", f"openGlass@{commit}", "--pin-source", str(source),
            "--local-remote-dir", str(base / "remotes"),
            "--work-dir", str(base / "work"),
            *(("--dry-run",) if dry_run else ())]


def scaffold(base: Path, source: Path, commit: str, *,
             dry_run: bool) -> subprocess.CompletedProcess:
    """`scaffold-project.py` run as a person runs it."""
    return run_script(SCAFFOLD, *scaffold_argv(base, source, commit,
                                               dry_run=dry_run), cwd=base)


def made(base: Path) -> list:
    """What the scaffold created in `base`: nothing, where it refused."""
    return [name for name in ("remotes", "work") if (base / name).exists()]


@pytest.fixture(autouse=True)
def no_variable_inherited(monkeypatch):
    """A run starts with no `GIT_NO_LAZY_FETCH` of the runner's own, so the
    scaffold alone decides whether its gits fetch."""
    monkeypatch.delenv(NO_LAZY_FETCH, raising=False)


@pytest.fixture(scope="module")
def honoured(glass, tmp_path_factory) -> bool:
    """Whether this git reads `GIT_NO_LAZY_FETCH`: a `tree:0` clone's
    `ls-tree` of the commit fails with it and runs no `upload-pack`."""
    base = tmp_path_factory.mktemp("honoured")
    clone = clone_of(glass, base, "tree0")
    proc = subprocess.run(["git", "ls-tree", "-r", glass["main"]],
                          cwd=str(clone), capture_output=True, text=True,
                          env={**os.environ, NO_LAZY_FETCH: "1"}, check=False)
    return proc.returncode != 0 and upload_packs(base) == 0


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "run"])
@pytest.mark.parametrize("kind", ["tree0", "lacks-commit"])
def test_a_partial_clone_short_of_the_pin_is_refused_with_no_fetch(
        glass, honoured, tmp_path, kind, dry_run):
    """A `tree:0` clone holding the commit and none of its trees, and a
    `blob:none` clone lacking the commit, were each fetched into once and
    the run went on (exit 0). Now: `pin-source-unreadable`, saying the clone
    is a partial one the scaffold never fetches into, and naming the cure,
    not `git fetch --all`; nothing made, no `upload-pack`, and the clone's
    objects as they were."""
    if not honoured:
        pytest.skip(IGNORED)
    clone = clone_of(glass, tmp_path, kind)
    before = objects_of(clone)
    result = scaffold(tmp_path, clone, pinned(glass, kind), dry_run=dry_run)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED pin-source-unreadable: " in result.stderr, result.stderr
    assert f"{PARTIAL}, whose git fetches" in result.stderr, result.stderr
    assert "from its promisor remote (`origin`)" in result.stderr
    assert NEVER_FETCHES in result.stderr, result.stderr
    assert f"{NOTHING_MADE}{clone.resolve()}, run {CURE}," in result.stderr
    assert FETCH_ALL not in result.stderr, result.stderr
    assert made(tmp_path) == []
    assert upload_packs(tmp_path) == 0, "the scaffold fetched"
    assert objects_of(clone) == before


def test_a_relative_pin_source_is_named_in_the_cure_by_its_resolved_path(
        glass, honoured, tmp_path):
    """`--pin-source openGlass`, typed relative to the folder the run is
    in: the refusal's remediation names the clone's absolute path, the one a
    person pastes the cure into from any folder, and not `openGlass` as
    typed. The partial clone is still found through the typed path."""
    if not honoured:
        pytest.skip(IGNORED)
    clone = clone_of(glass, tmp_path, "tree0")
    result = scaffold(tmp_path, Path(clone.name), glass["main"], dry_run=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED pin-source-unreadable: " in result.stderr, result.stderr
    assert PARTIAL in result.stderr, result.stderr
    assert f"{NOTHING_MADE}{clone.resolve()}, run {CURE}," in result.stderr
    assert f"{NOTHING_MADE}{clone.name}, run" not in result.stderr
    assert upload_packs(tmp_path) == 0, "the scaffold fetched"


def test_the_cure_as_printed_makes_a_tree0_clone_readable(
        glass, honoured, tmp_path):
    """The command the refusal names, run as printed in the clone, makes it
    whole: the scaffold run again reads the pin, the origin's own digest,
    with no fetch of its own."""
    if not honoured:
        pytest.skip(IGNORED)
    clone = clone_of(glass, tmp_path, "tree0")
    refused = scaffold(tmp_path, clone, glass["main"], dry_run=True)
    cure = re.search(r"run `(git fetch [^`]+)`", refused.stderr)
    assert cure, refused.stderr
    subprocess.run(shlex.split(cure.group(1)), cwd=str(clone), check=True,
                   capture_output=True)
    cured = upload_packs(tmp_path)
    assert cured >= 1
    result = scaffold(tmp_path, clone, glass["main"], dry_run=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'tree_sha256: "{glass["digest"]}"' in (
        tmp_path / "work" / PIN_FILE).read_text(encoding="utf-8")
    assert upload_packs(tmp_path) == cured, "the scaffold fetched"


@pytest.mark.parametrize("kind", ["full", "blobnone", "blobnone-checkout",
                                  "tree0-cured"])
def test_a_clone_holding_the_pin_and_its_trees_is_read_with_no_fetch(
        glass, tmp_path, kind):
    """A full clone, a `blob:none` clone holding the commit (its trees come
    with it), checked out or not, and a `tree:0` clone made whole by `git
    fetch --refetch --no-filter`: the real run reads the origin's own
    digest, and runs no `upload-pack`. The same on 961640c6."""
    clone = clone_of(glass, tmp_path,
                     "tree0" if kind == "tree0-cured" else kind)
    if kind == "tree0-cured":
        git("fetch", "-q", "--refetch", "--no-filter", "origin", cwd=clone)
    cured = upload_packs(tmp_path)
    result = scaffold(tmp_path, clone, glass["main"], dry_run=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'tree_sha256: "{glass["digest"]}"' in (
        tmp_path / "work" / PIN_FILE).read_text(encoding="utf-8")
    assert upload_packs(tmp_path) == cured, "the scaffold fetched"


def test_a_full_clone_lacking_the_pin_keeps_the_fetch_all_remediation(
        glass, tmp_path):
    """A clone that is no partial one keeps the reader's refusal as it was,
    `git fetch --all` and all, with no word of a partial clone."""
    clone = clone_of(glass, tmp_path, "full-lacks-commit")
    result = scaffold(tmp_path, clone, glass["side"], dry_run=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED pin-source-unreadable: " in result.stderr, result.stderr
    assert FETCH_ALL in result.stderr, result.stderr
    assert "partial clone" not in result.stderr, result.stderr
    assert "--refetch" not in result.stderr, result.stderr
    assert upload_packs(tmp_path) == 0


def test_a_folder_in_a_partial_clone_is_still_not_a_clone(glass, tmp_path):
    """`--pin-source <partial clone>/lib` is `pin-source-not-a-clone`, as
    any folder below a clone's top level is, with no word of a partial
    clone: only `pin-source-unreadable` is asked about the clone."""
    clone = clone_of(glass, tmp_path, "tree0")
    (clone / "lib").mkdir()
    result = scaffold(tmp_path, clone / "lib", glass["main"], dry_run=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED pin-source-not-a-clone: " in result.stderr, result.stderr
    assert "partial clone" not in result.stderr, result.stderr
    assert upload_packs(tmp_path) == 0


def test_in_process_the_variable_is_what_stops_the_fetch_and_is_put_back(
        glass, honoured, tmp_path, monkeypatch, capsys):
    """`main` run in this process: a `tree:0` clone is refused with no
    fetch, and with the variable's name changed to one git does not read,
    the same run fetches and goes on (exit 0), as before #1182. Neither name
    is left in this process's environment after either run."""
    if not honoured:
        pytest.skip(IGNORED)
    module = load_without_bytecode(SCAFFOLD, "scaffold_partial_pin_source")
    materialize = sys.modules[module.pin_values_unfetched.__module__]
    assert vars(materialize) is module.pin_values_unfetched.__globals__
    monkeypatch.delenv("LANES_LANE", raising=False)
    clear_ambient_pin_sources(monkeypatch)
    clone = clone_of(glass, tmp_path, "tree0")
    argv = scaffold_argv(tmp_path, clone, glass["main"], dry_run=True)
    assert module.main(argv) == 2
    assert "REFUSED pin-source-unreadable: " in capsys.readouterr().err
    assert upload_packs(tmp_path) == 0
    assert NO_LAZY_FETCH not in os.environ
    monkeypatch.setattr(materialize, "NO_LAZY_FETCH", IGNORED_BY_GIT)
    assert module.main(argv) == 0, capsys.readouterr().err
    assert upload_packs(tmp_path) >= 1
    assert NO_LAZY_FETCH not in os.environ
    assert IGNORED_BY_GIT not in os.environ


def test_each_promisor_remote_is_named_with_its_own_cure(
        glass, honoured, tmp_path):
    """A `tree:0` clone with a second promisor remote: the refusal names
    both, in git's order, and the cure is one fetch from each, in the
    reader's own words; the reader's refusal is the cause."""
    if not honoured:
        pytest.skip(IGNORED)
    clone = clone_of(glass, tmp_path, "tree0")
    git("remote", "add", "second", glass["origin"].as_uri(), cwd=clone)
    git("config", "remote.second.promisor", "true", cwd=clone)
    args = Namespace(pin=[f"openGlass@{glass['main']}"],
                     pin_owner="opensoft", pin_source=clone)
    with pytest.raises(shape_materialize.Refusal) as caught:
        shape_materialize.pin_values_unfetched(
            args, reader="the reader", nothing_made="Nothing was made.")
    refusal = caught.value
    assert refusal.code == "pin-source-unreadable"
    assert ("from its promisor remote (`origin`, `second`) on any read that "
            "needs it, and the reader never fetches into a --pin-source"
            ) in refusal.detail
    assert str(refusal).count("Remediation: Nothing was made. Make that "
                              "clone whole, then run the reader again: in "
                              f"{clone.resolve()}, run {CURE}, then `git "
                              "fetch --refetch --no-filter second`, which "
                              "fetches every object again") == 1
    assert isinstance(refusal.__cause__, shape_materialize.Refusal)
    assert refusal.__cause__.code == "pin-source-unreadable"
    assert refusal.detail.startswith(refusal.__cause__.detail + ". ")
    assert upload_packs(tmp_path) == 0
    assert NO_LAZY_FETCH not in os.environ


# --- the helpers, one by one --------------------------------------------


@pytest.mark.parametrize("before", [None, "0"])
def test_lazy_fetch_off_sets_the_variable_and_puts_it_back(
        monkeypatch, before):
    """`GIT_NO_LAZY_FETCH=1` inside, and outside the environment as it was:
    a value it had restored, one it did not have removed."""
    if before is not None:
        monkeypatch.setenv(NO_LAZY_FETCH, before)
    with shape_materialize.lazy_fetch_off():
        assert os.environ.get(NO_LAZY_FETCH) == "1"
    assert os.environ.get(NO_LAZY_FETCH) == before


def test_lazy_fetch_off_puts_it_back_when_the_read_raises():
    """A read that raised leaves the environment as it was too."""
    with pytest.raises(LookupError):
        with shape_materialize.lazy_fetch_off():
            raise LookupError
    assert NO_LAZY_FETCH not in os.environ


#: Config set in a fresh `git init`, in this order, and the promisor
#: remotes git would ask, in its order (`promisor-remote.c`, git 2.43).
PROMISOR_CONFIG = {
    "none": ([], []),
    "promisor-false": ([("remote.a.promisor", "false")], []),
    "promisor-true": ([("remote.a.promisor", "true")], ["a"]),
    "promisor-yes": ([("remote.a.promisor", "yes")], ["a"]),
    "filter": ([("remote.b.partialclonefilter", "blob:none")], ["b"]),
    "named-last": ([("extensions.partialclone", "c"),
                    ("remote.c.promisor", "true"),
                    ("remote.d.promisor", "true")], ["d", "c"]),
    "named-only": ([("extensions.partialclone", "f")], ["f"]),
    "once": ([("remote.e.partialclonefilter", "tree:0"),
              ("remote.e.promisor", "true")], ["e"]),
    "config-order": ([("remote.z.promisor", "true"),
                      ("remote.y.promisor", "true")], ["z", "y"]),
    "dotted-name": ([("remote.a.b.promisor", "true")], ["a.b"]),
}


@pytest.mark.parametrize("case", list(PROMISOR_CONFIG))
def test_promisor_remotes_reads_gits_rule(tmp_path, case):
    """`promisor_remotes` of a repository with only the config `case` sets:
    each remote git fetches a missing object from, once, in the config's
    order, and the one `extensions.partialclone` names last."""
    entries, expected = PROMISOR_CONFIG[case]
    git("init", "-q", str(tmp_path), cwd=tmp_path)
    for key, value in entries:
        git("config", key, value, cwd=tmp_path)
    assert shape_materialize.promisor_remotes(tmp_path) == expected


def test_promisor_remotes_of_a_folder_that_is_not_there_is_none(tmp_path):
    """A folder git cannot run in names no remote, and raises nothing."""
    assert shape_materialize.promisor_remotes(tmp_path / "missing") == []


@pytest.mark.parametrize("remote, expected", [
    ("origin", "`git fetch --refetch --no-filter origin`"),
    ("my remote", "`git fetch --refetch --no-filter 'my remote'`"),
    ("-x", "a `git fetch --refetch --no-filter` from the remote named `-x`"),
    ("a`b", "a `git fetch --refetch --no-filter` from the remote named "
            + repr("a`b")),
    ("a\x1bb", "a `git fetch --refetch --no-filter` from the remote named "
               + repr("a\x1bb")),
], ids=["plain", "spaced", "an-option", "a-backtick", "unprintable"])
def test_refetch_command_is_one_to_paste_or_the_step_in_words(
        remote, expected):
    """A name that pastes safely is quoted into the command; an option, a
    backtick or a character that does not print is named, and the step said
    in words."""
    assert shape_materialize.refetch_command(remote) == expected


@pytest.mark.parametrize("remote, expected", [
    ("origin", "`origin`"),
    ("-x", "`-x`"),
    ("a`b", repr("a`b")),
    ("a\nb", repr("a\nb")),
], ids=["plain", "an-option", "a-backtick", "a-line-break"])
def test_a_remote_is_named_between_backticks_or_as_repr(remote, expected):
    """Between backticks where it prints and holds none; otherwise as
    Python's `repr` spells it, so no line break reaches the terminal."""
    assert shape_materialize._remote_named(remote) == expected
