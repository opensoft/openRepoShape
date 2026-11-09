# SPDX-License-Identifier: Apache-2.0
"""`plan` never fetches into a partial-clone `--source` or `--pin-source`
(#1162).

#1145 stopped `check` and `execute` fetching into a partial-clone source
(`tests/test_adopt_partial_clone_source.py`), and left `plan`. Measured on
#1145's head 2c8082a2 with git 2.43, each clone of a local origin whose
`remote.origin.uploadpack` counts its runs:

* a `--filter=blob:none --no-checkout` `--source` (28 objects lacking):
  `plan` wrote its plan after running that `upload-pack` 26 times, and the
  source's `.promisor` files went from 1 to 27;
* a `--filter=blob:none` `--source` that checked its branch out (2 history
  blobs lacking): `plan` wrote its plan, fetching nothing, for a source
  `check` refuses and `execute` cannot split;
* a `--filter=tree:0 --no-checkout` `--pin-source`, and a
  `--filter=blob:none --no-checkout` one that lacks the pinned commit: `plan`
  ran that `upload-pack` once, the clone gained a promisor pack, and the
  digest was read after it.

Now `plan` runs with `GIT_NO_LAZY_FETCH=1` (`_lazy_fetch_off`), refuses the
partial `--source` `check` would refuse as `source-partial-clone` before
anything reads it (`_refuse_a_partial_clone_short`), and a partial
`--pin-source` it could read only by fetching keeps the reader's own
`pin-source-unreadable`, which says that the clone is a partial one and how
to make it whole (`_pins_read_unfetched`). A `--filter=blob:none` pin clone
that holds the pinned commit has its trees, and is read as a full clone is.

The rows reuse #1145's `Source`: its counting `upload-pack` wrapper and its
hash of `objects/`. A pin clone runs the same wrapper, so one log counts the
runs of both.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ADOPT, FILE_PROTOCOL, git, make_source_repo, run_script
from repo_shape import tree_digest
from test_adopt_partial_clone_source import (  # noqa: F401 - fixtures
    CODE, CURE, IGNORED, LATER, REFUSED, SIDE, VARIABLE, Source, adopter,
    made, no_ambient_variable, planned_once,
    skip_where_git_ignores_the_variable)

#: The refusal the pin's reader gives a `--pin-source` that cannot answer.
PIN_CODE = "pin-source-unreadable"
PIN_REFUSED = f"REFUSED {PIN_CODE}:"
#: What `_pins_read_unfetched` adds to it for a partial clone.
PARTIAL = "That clone is a partial clone (`git clone --filter`)"
#: The remediation the reader gives any clone that cannot answer.
FETCH_ALL = "`git fetch --all` first"
#: The product pinned, and the files of its repository.
PRODUCT = "openGlass"
GLASS_TREE = {"README.md": "# glass\n", "lib/a.py": "A = 1\n",
              "lib/b/c.txt": "c\n"}
GLASS_EDITS = (("lib/a.py", "A = 2\n", "Two"),)
#: How each pin clone is made from the glass origin, and whether the pin is
#: `SIDE`'s commit, which no clone below takes: `cured` is fetched again
#: with no filter after its clone, as the refusal says to.
PIN_VARIANTS = {
    "full": ((), False),
    "blobnone": (("--filter=blob:none", "--no-checkout"), False),
    "blobnone-checkout": (("--filter=blob:none",), False),
    "tree0": (("--filter=tree:0", "--no-checkout"), False),
    "tree0-cured": (("--filter=tree:0", "--no-checkout"), False),
    "lacks-commit": (("--filter=blob:none", "--no-checkout"), True),
    "full-lacks-commit": ((), True),
}


@pytest.fixture(scope="module")
def glass(tmp_path_factory) -> dict:
    """The pinned product's origin, which lets a clone filter: two commits
    on `main`, and one on `SIDE` that adds a file; with the digest each
    commit's tree has, read where every object is."""
    base = tmp_path_factory.mktemp("glass")
    origin = make_source_repo(base / "glass-origin", tree=GLASS_TREE,
                              edits=GLASS_EDITS)
    git("config", "uploadpack.allowFilter", "true", cwd=origin)
    main = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "-c", SIDE, cwd=origin)
    (origin / "lib" / "d.txt").write_text("d\n", encoding="utf-8")
    git("add", "-A", cwd=origin)
    git("commit", "-q", "-m", "Elsewhere", cwd=origin)
    side = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "main", cwd=origin)
    return {"origin": origin, "main": main, "side": side,
            "digests": {main: tree_digest(origin, main),
                        side: tree_digest(origin, side)}}


class PinClone:
    """A `PIN_VARIANTS` clone of the glass origin beside `source`, run with
    `source`'s counting `upload-pack`, so `source.runs()` counts both."""

    def __init__(self, glass: dict, source: Source, variant: str):
        flags, on_the_side = PIN_VARIANTS[variant]
        self.path = source.base / PRODUCT
        git(*FILE_PROTOCOL, "clone", "-q", "--single-branch", *flags,
            "--no-local", glass["origin"].as_uri(), str(self.path),
            cwd=source.base)
        if variant.endswith("-cured"):
            git(*FILE_PROTOCOL, "fetch", "-q", "--refetch", "--no-filter",
                "origin", cwd=self.path)
        counted = git("config", "--get", "remote.origin.uploadpack",
                      cwd=source.path).stdout.strip()
        git("config", "remote.origin.uploadpack", counted, cwd=self.path)
        self.commit = glass["side" if on_the_side else "main"]
        self.digest = glass["digests"][self.commit]
        self.before = self.store()

    def store(self) -> str:
        """`Source.store`, of this clone's `objects/`."""
        return Source.store(SimpleNamespace(path=self.path))

    def flags(self) -> tuple:
        return ("--pin", f"{PRODUCT}@{self.commit}",
                "--pin-source", str(self.path))


def plan_argv(source: Source, *extra: str) -> tuple[Path, list[str]]:
    """`(where the plan goes, the command line of a `plan` of `source`)`:
    written beside it, its work directory there too."""
    out = source.base / "planned" / "adoption-plan.yaml"
    out.parent.mkdir(exist_ok=True)
    return out, ["plan", "--source", str(source.path),
                 "--project", "Northwind", "--org", "testorg",
                 "--elected-by", "Test Human", "--elected-on", "2026-09-02",
                 "--out", str(out),
                 "--work-dir", str(source.base / "plan-work"), *extra]


def planned(source: Source, *extra: str):
    """`(where the plan goes, the run of `plan_argv`'s `plan`)`."""
    out, argv = plan_argv(source, *extra)
    return out, run_script(ADOPT, *argv)


def skip_unless_the_variable_holds(pin: PinClone, source: Source,
                                   glass: dict) -> None:
    """#1145's `skip_where_git_ignores_the_variable`, asked of the pin
    clone: a commit it lacks, `SIDE`'s, read with the variable set."""
    skip_where_git_ignores_the_variable(SimpleNamespace(
        path=pin.path, planned={"side": glass["side"]}, runs=source.runs))


@pytest.mark.parametrize("variant", ["nocheckout", "checkout"])
def test_plan_refuses_a_partial_clone_source_that_lacks_objects(
        made, variant):
    """Base: the plan written, after 26 `upload-pack` runs and `.promisor`
    files 1 -> 27 for `nocheckout`, and none for `checkout`, a source
    `check` refuses. Head: refused before the plan exists, nothing
    fetched."""
    source = made(variant)
    assert source.lacking() > 0
    promisor = source.promisor_packs()
    out, result = planned(source)
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert "`plan`, `check` and `execute` never fetch" in result.stderr
    assert CURE in result.stderr
    assert not out.exists()
    source.untouched()
    assert source.promisor_packs() == promisor


@pytest.mark.parametrize("variant", ["full", "cured"])
def test_plan_reads_a_full_clone_and_a_cured_partial_clone_as_before(
        made, variant):
    """A full clone, and a partial clone fetched again with no filter, lack
    nothing: the plan is written, and nothing is fetched, on base and head
    alike."""
    source = made(variant)
    assert source.lacking() == 0
    out, result = planned(source)
    assert result.returncode == 0, result.stderr + result.stdout
    assert out.exists()
    assert CODE not in result.stderr + result.stdout
    source.untouched()


def test_plan_s_guard_alone_refuses_where_git_ignores_the_variable(
        adopter, made, monkeypatch, capsys):
    """A git that ignores `GIT_NO_LAZY_FETCH` (stood for by setting another
    name) still fetches nothing: the source is refused before it is read.
    Base: the plan written, after 26 `upload-pack` runs."""
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    source = made("nocheckout")
    code = adopter.main(plan_argv(source)[1])
    said = capsys.readouterr()
    assert code == 2, said.err + said.out
    assert REFUSED in said.err
    source.untouched()
    assert VARIABLE not in os.environ and IGNORED not in os.environ


@pytest.mark.parametrize("variant", ["full", "blobnone", "blobnone-checkout",
                                     "tree0-cured"])
def test_plan_reads_a_pin_clone_that_holds_the_commit_and_its_trees(
        glass, made, variant):
    """A digest is read from the pinned commit's trees: a full clone, a
    `--filter=blob:none` clone that holds the commit, checked out or not,
    and a `tree:0` clone fetched again with no filter, as the refusal below
    says to, each record the digest the origin has and fetch nothing, on
    base and head alike."""
    source = made("full")
    pin = PinClone(glass, source, variant)
    out, result = planned(source, *pin.flags())
    assert result.returncode == 0, result.stderr + result.stdout
    assert pin.digest in out.read_text(encoding="utf-8")
    assert source.runs() == 0
    assert pin.store() == pin.before


@pytest.mark.parametrize("variant", ["tree0", "lacks-commit"])
def test_plan_refuses_a_partial_pin_source_it_could_read_only_by_fetching(
        glass, made, variant):
    """Base: the plan written, after one `upload-pack` run that fetched
    the trees, or the commit, into the pin clone, a promisor pack more.
    Head: `pin-source-unreadable`, naming the partial clone, the fetch
    that makes it whole, and that a later fetch stays filtered, as the
    source's refusal says; no plan, nothing fetched. Skipped where this git
    ignores the variable, which alone keeps such a read unfetched."""
    source = made("full")
    pin = PinClone(glass, source, variant)
    skip_unless_the_variable_holds(pin, source, glass)
    out, result = planned(source, *pin.flags())
    assert result.returncode == 2, result.stderr + result.stdout
    assert PIN_REFUSED in result.stderr
    assert f"could not answer for opensoft/{PRODUCT} @ {pin.commit}" \
        in result.stderr
    assert PARTIAL in result.stderr
    assert "`plan` never fetches into a --pin-source" in result.stderr
    assert CURE in result.stderr
    assert f"{LATER}, so the clone can lack objects again." in result.stderr
    assert FETCH_ALL not in result.stderr
    assert not out.exists()
    assert source.runs() == 0
    assert pin.store() == pin.before


def test_a_partial_source_is_refused_before_a_partial_pin_source_is_read(
        glass, made):
    """The order: the `--source` guard comes before `_checked_plan_inputs`
    reads the pins. A partial `--source` that lacks objects and a `tree:0`
    `--pin-source` together are refused as `source-partial-clone`, not as
    `pin-source-unreadable`: no plan, and nothing fetched into either
    clone, on any git, since the pin clone is never read. With the guard
    after the pin read, the pin's refusal came first."""
    source = made("nocheckout")
    pin = PinClone(glass, source, "tree0")
    out, result = planned(source, *pin.flags())
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert PIN_CODE not in result.stderr
    assert not out.exists()
    source.untouched()
    assert pin.store() == pin.before


def test_a_full_pin_clone_that_lacks_the_commit_is_refused_as_before(
        glass, made):
    """A clone that is no partial one keeps the reader's refusal as it was,
    on base and head alike: nothing about a partial clone, and its own
    remediation."""
    source = made("full")
    pin = PinClone(glass, source, "full-lacks-commit")
    out, result = planned(source, *pin.flags())
    assert result.returncode == 2, result.stderr + result.stdout
    assert PIN_REFUSED in result.stderr
    assert FETCH_ALL in result.stderr
    assert PARTIAL not in result.stderr
    assert not out.exists()
    assert source.runs() == 0


def test_a_folder_inside_a_partial_pin_clone_is_no_clone_as_before(
        glass, made):
    """Only the reader's `pin-source-unreadable` is said otherwise: a
    folder inside a partial clone is `pin-source-not-a-clone`, in its own
    words, though git there reads the clone's promisor config."""
    source = made("full")
    pin = PinClone(glass, source, "blobnone-checkout")
    flags = list(pin.flags())
    flags[-1] = str(pin.path / "lib")
    out, result = planned(source, *flags)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED pin-source-not-a-clone:" in result.stderr
    assert PARTIAL not in result.stderr
    assert not out.exists()
    assert source.runs() == 0


def test_the_variable_is_what_keeps_a_partial_pin_source_unfetched(
        adopter, glass, made, monkeypatch, capsys):
    """A `tree:0` pin clone: refused with nothing fetched, and, with the
    variable `plan` sets ignored, the same `plan` fetches its trees and
    writes the plan. Base: the first run already fetches."""
    source = made("full")
    pin = PinClone(glass, source, "tree0")
    skip_unless_the_variable_holds(pin, source, glass)
    _, argv = plan_argv(source, *pin.flags())
    code = adopter.main(argv)
    said = capsys.readouterr()
    assert source.runs() == 0
    assert code == 2, said.err + said.out
    assert PIN_REFUSED in said.err
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    code = adopter.main(argv)
    said = capsys.readouterr()
    assert code == 0, said.err + said.out
    assert source.runs() >= 1
    assert VARIABLE not in os.environ and IGNORED not in os.environ

