# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` never fetch into a partial-clone source (#1145).

A partial clone (`git clone --filter=blob:none`) lacks objects, and git
fetches one it lacks from the promisor remote on any read that needs it: it
runs the `upload-pack` the source's own `remote.origin.uploadpack` names and
writes a promisor pack into the source's `objects/`. Measured on #1119's
head bba168bd with git 2.43, the plan written from a full clone and the
source then made again as the partial clone at the same commit:

* a `--filter=blob:none --no-checkout` clone (28 objects lacking): `check`
  said `plan ok` after running that `upload-pack` 26 times, and the source's
  `.promisor` files went from 1 to 27; `execute` did the same, then made both
  leg repositories, and its `git filter-repo` died with `Blob not found`;
* a `--filter=blob:none` clone that checked its branch out (2 history blobs
  lacking): `check` said `plan ok`, and `execute` made both legs and died
  the same way.

Now both commands run with `GIT_NO_LAZY_FETCH=1` (`_lazy_fetch_off`), and
refuse a partial clone that lacks an object its branches, tags or HEAD reach
as `source-partial-clone` before anything reads it
(`_refuse_a_partial_clone_short`). A partial clone given every object again
(`git fetch --refetch --no-filter`) lacks nothing and is read as a full clone
is. Each row counts the promisor's `upload-pack` runs through a counting
`remote.origin.uploadpack`, and hashes the source's `objects/` before and
after.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, git, make_source_repo, resolve,
                      run_script, write_plan)
from test_adopt_temp_work_roots import gh_clones

#: The refusal #1145 adds.
CODE = "source-partial-clone"
REFUSED = f"REFUSED {CODE}:"
#: The way out the refusal names, for the remote a clone calls `origin`.
CURE = "`git fetch --refetch --no-filter origin`"
#: What the refusal says about a fetch run after the cure.
LATER = ("Later fetches stay filtered while "
         "`remote.origin.partialclonefilter` is set")
#: The variable `_lazy_fetch_off` sets.
VARIABLE = "GIT_NO_LAZY_FETCH"
#: A name no git reads: `NO_LAZY_FETCH` set to it stands for a git that
#: ignores the variable.
IGNORED = "GIT_IGNORED_BY_GIT"
#: The answers the synthetic source's plan asks for.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: How each source is cloned from `origin`: `cured` is fetched again with no
#: filter after its clone, and `fileallow` sets the source's own
#: `protocol.file.allow=always`, which outranked `-c protocol.allow=never`.
VARIANTS = {"nocheckout": ("--filter=blob:none", "--no-checkout"),
            "checkout": ("--filter=blob:none",),
            "fileallow": ("--filter=blob:none", "--no-checkout"),
            "cured": ("--filter=blob:none", "--no-checkout"),
            "full": ()}
#: A commit on a branch the source never clones.
SIDE = "side"
#: An annotated tag on a commit no branch reaches, which changes a spec file.
TAG = "tagged"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git-filter-repo is not installed")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_partial_clone_source", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_ambient_variable(monkeypatch):
    """No `GIT_NO_LAZY_FETCH` from the shell the suite runs in: a row asks
    what the tool sets."""
    monkeypatch.delenv(VARIABLE, raising=False)


@pytest.fixture(scope="module")
def planned_once(tmp_path_factory) -> dict:
    """`origin`, which lets a clone filter, a plan written from a full clone
    of its `main`, every entry answered, and a commit on a branch `side` no
    clone below takes, and an annotated tag `TAG` on a commit no branch
    reaches; made once, since every row reads it alone."""
    base = tmp_path_factory.mktemp("planned")
    origin = make_source_repo(base / "origin")
    git("config", "uploadpack.allowFilter", "true", cwd=origin)
    full = base / "Thing"
    git(*FILE_PROTOCOL, "clone", "-q", "--single-branch", "--no-local",
        origin.as_uri(), str(full), cwd=base)
    plan = base / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    written = write_plan(full, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    commit = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "-c", SIDE, cwd=origin)
    git("commit", "-q", "--allow-empty", "-m", "Elsewhere", cwd=origin)
    side = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    git("switch", "-q", "main", cwd=origin)
    git("switch", "-q", "--detach", cwd=origin)
    (origin / "specs" / "001-feature" / "spec.md").write_text(
        "# The feature, as the tag has it\n", encoding="utf-8")
    git("commit", "-q", "-a", "-m", "Only a tag reaches this", cwd=origin)
    git("tag", "-a", "-m", "A tag", TAG, cwd=origin)
    git("switch", "-q", "main", cwd=origin)
    return {"origin": origin, "text": plan.read_text(encoding="utf-8"),
            "at": full, "commit": commit, "side": side}


class Source:
    """One source made as a `VARIANTS` clone of `origin` at `<base>/Thing`,
    its `upload-pack` counted, and the plan pointed at it."""

    def __init__(self, planned: dict, base: Path, variant: str):
        self.planned = planned
        self.base = base
        self.path = base / "Thing"
        git(*FILE_PROTOCOL, "clone", "-q", "--single-branch",
            *VARIANTS[variant], "--no-local", planned["origin"].as_uri(),
            str(self.path), cwd=base)
        if variant == "cured":
            git(*FILE_PROTOCOL, "fetch", "-q", "--refetch", "--no-filter",
                "origin", cwd=self.path)
        if variant == "fileallow":
            git("config", "protocol.file.allow", "always", cwd=self.path)
        self.log = base / "upload-pack.log"
        wrapper = base / "upload_pack.py"
        wrapper.write_text(
            "import subprocess, sys\n"
            f"with open({str(self.log)!r}, 'a', encoding='utf-8') as log:\n"
            "    log.write('ran\\n')\n"
            "sys.exit(subprocess.call(['git', 'upload-pack', "
            "*sys.argv[1:]]))\n", encoding="utf-8")
        git("config", "remote.origin.uploadpack",
            f"{shlex.quote(sys.executable)} {shlex.quote(str(wrapper))}",
            cwd=self.path)
        self.plan = base / "plan" / "adoption-plan.yaml"
        self.plan.parent.mkdir()
        self.write_plan(planned["text"].replace(
            f'  local_path: "{planned["at"]}"\n',
            f'  local_path: "{self.path}"\n'))
        self.before = self.store()

    def write_plan(self, text: str) -> None:
        assert f'  local_path: "{self.path}"\n' in text
        self.plan.write_bytes(text.encode("utf-8"))

    def runs(self) -> int:
        """How many times the promisor's `upload-pack` ran."""
        return (len(self.log.read_text(encoding="utf-8").splitlines())
                if self.log.exists() else 0)

    def store(self) -> str:
        """A sha256 of every file under the source's `objects/`: each path
        and its bytes."""
        objects = self.path / ".git" / "objects"
        digest = hashlib.sha256()
        for path in sorted(objects.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(objects).as_posix().encode()
                              + b"\0" + path.read_bytes() + b"\0")
        return digest.hexdigest()

    def promisor_packs(self) -> int:
        return len(list((self.path / ".git" / "objects" / "pack")
                        .glob("*.promisor")))

    def lacking(self, refs: str = "--all") -> int:
        """How many objects `refs` (`--all`, `--branches`, `--tags` or
        `HEAD`) reach that the source lacks."""
        listed = git("rev-list", "--objects", "--missing=print", refs,
                     cwd=self.path).stdout
        return sum(line.startswith("?") for line in listed.splitlines())

    def fetch_the_tag(self) -> None:
        """Fetch `TAG` with the filter this clone keeps, so that its commit's
        changed blob is lacking; what that fetch ran is not counted."""
        git(*FILE_PROTOCOL, "fetch", "-q", "origin",
            f"refs/tags/{TAG}:refs/tags/{TAG}", cwd=self.path)
        self.log.write_text("", encoding="utf-8")
        self.before = self.store()

    def detach_at_the_fetched_tag(self) -> None:
        """Fetch `TAG` as `fetch_the_tag` does, move HEAD (not a branch) to
        its commit, and delete the tag: only HEAD reaches the blob that is
        lacking, as in a clone detached at a commit it fetched with its
        filter. `update-ref --no-deref`, not `switch --detach`, which would
        check the commit out and fetch that blob."""
        self.fetch_the_tag()
        commit = git("rev-parse", f"{TAG}^{{commit}}",
                     cwd=self.path).stdout.strip()
        git("update-ref", "--no-deref", "HEAD", commit, cwd=self.path)
        git("tag", "-d", TAG, cwd=self.path)
        self.before = self.store()

    def unborn_head(self) -> None:
        """HEAD on a branch that does not exist, as `git switch --orphan`
        leaves it: it names no commit."""
        git("symbolic-ref", "HEAD", "refs/heads/unborn", cwd=self.path)

    def untouched(self) -> None:
        """No `upload-pack` ran, and `objects/` is as it was."""
        assert self.runs() == 0
        assert self.store() == self.before

    def check(self) -> subprocess.CompletedProcess:
        return run_script(ADOPT, "check", "--plan", str(self.plan),
                          "--work-dir", str(self.base / "work"))

    def execute(self) -> subprocess.CompletedProcess:
        return run_script(ADOPT, "execute", "--plan", str(self.plan),
                          "--yes", "--local-remote-dir",
                          str(self.base / "remotes"),
                          "--work-dir", str(self.base / "work"))

    def at_the_side_commit(self, cloned: bool = False) -> None:
        """The plan names `side`'s commit, which `origin` holds and the
        source lacks; `cloned`, as a clone `plan` made of a repository GitHub
        does not have."""
        text = self.plan.read_text(encoding="utf-8")
        planned = self.planned
        # Quoted where YAML would read the hash as another type.
        text, swapped = re.subn(
            rf'^  commit: "?{planned["commit"]}"?$',
            f'  commit: "{planned["side"]}"', text, count=1, flags=re.M)
        assert swapped == 1
        if cloned:
            text = text.replace(
                "  repository: null\n", '  repository: "testorg/Elsewhere"\n',
                1).replace("  cloned: false\n", "  cloned: true\n", 1)
            assert "  cloned: true\n" in text
        self.write_plan(text)


@pytest.fixture
def made(planned_once, tmp_path):
    return lambda variant: Source(planned_once, tmp_path, variant)


def skip_where_git_ignores_the_variable(source: Source) -> None:
    """Skip where this git fetches a commit the source lacks with
    `GIT_NO_LAZY_FETCH=1` set: before 2.39.4, and an unpatched 2.40 to
    2.44. Asked before the row, since an ignored variable fetches it."""
    asked = subprocess.run(
        ["git", "cat-file", "-e", f"{source.planned['side']}^{{commit}}"],
        cwd=str(source.path), capture_output=True, check=False,
        env={**os.environ, VARIABLE: "1"})
    if source.runs():
        pytest.skip(f"this git ignores {VARIABLE}: `git cat-file -e` of a "
                    f"commit a partial clone lacks fetched it "
                    f"(exit {asked.returncode})")


@pytest.mark.parametrize("variant", ["nocheckout", "checkout", "fileallow"])
def test_check_refuses_a_partial_clone_that_lacks_objects_and_fetches_none(
        made, variant):
    """Base: `plan ok`, after 26 `upload-pack` runs and `.promisor` files 1
    -> 27 for `nocheckout`, and none for `checkout`, whose 2 lacking history
    blobs `execute` then failed on. Head: refused, nothing fetched, the
    refusal gives the count it lacks at least and the cure, and says a later
    fetch stays filtered (the cure leaves `partialclonefilter` set)."""
    source = made(variant)
    assert source.lacking() > 0
    promisor = source.promisor_packs()
    result = source.check()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert "that lacks at least " in result.stderr
    assert "Remediation: make the source whole" in result.stderr
    assert CURE in result.stderr
    assert LATER in result.stderr
    assert "plan ok" not in result.stdout
    source.untouched()
    assert source.promisor_packs() == promisor


@pytest.mark.parametrize("variant", ["full", "cured"])
def test_check_reads_a_full_clone_and_a_cured_partial_clone_as_before(
        made, variant):
    """A full clone is asked its config alone, and a partial clone fetched
    again with no filter lacks nothing: both `plan ok`, nothing fetched, on
    base and head alike."""
    source = made(variant)
    assert source.lacking() == 0
    result = source.check()
    assert result.returncode == 0, result.stderr + result.stdout
    assert "plan ok" in result.stdout
    assert CODE not in result.stderr + result.stdout
    source.untouched()


@pytest.mark.parametrize("variant", ["nocheckout", "checkout"])
def test_execute_refuses_a_partial_clone_before_any_leg_and_fetches_none(
        made, variant):
    """Base: both leg repositories made, then `git filter-repo` died with
    `Blob not found` (26 `upload-pack` runs for `nocheckout`). Head: refused
    before the directory the legs go in is made, nothing fetched."""
    source = made(variant)
    result = source.execute()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert not (source.base / "remotes").exists()
    source.untouched()


@needs_filter_repo
def test_execute_splits_a_cured_partial_clone_and_fetches_none(made):
    """A partial clone that lacks nothing is split as a full clone is."""
    source = made("cured")
    result = source.execute()
    assert result.returncode == 0, result.stderr + result.stdout
    assert CODE not in result.stderr + result.stdout
    assert sorted(path.name for path in (source.base / "remotes").iterdir())
    assert source.runs() == 0


def test_the_guard_alone_refuses_where_git_ignores_the_variable(
        adopter, made, monkeypatch, capsys):
    """A git that ignores `GIT_NO_LAZY_FETCH` (stood for by setting another
    name) still fetches nothing: the source is refused before it is read.
    `raising=False`, so the base fails on what it does, not on the name."""
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    source = made("nocheckout")
    code = adopter.main(["check", "--plan", str(source.plan),
                         "--work-dir", str(source.base / "work")])
    said = capsys.readouterr()
    assert code == 2, said.err + said.out
    assert REFUSED in said.err
    source.untouched()
    assert VARIABLE not in os.environ and IGNORED not in os.environ


def test_check_reads_no_commit_the_plan_names_and_the_source_lacks(
        adopter, made, monkeypatch, capsys):
    """A cured partial clone, whose branches lack nothing, and a plan whose
    `commit:` the source lacks: `check` reads that commit (the Triad
    advisory reads the plan's), and git would fetch it. The variable keeps
    it unfetched; with the variable ignored, the same `check` fetches."""
    source = made("cured")
    source.at_the_side_commit()
    skip_where_git_ignores_the_variable(source)
    args = ["check", "--plan", str(source.plan),
            "--work-dir", str(source.base / "work")]
    code = adopter.main(args)
    said = capsys.readouterr()
    source.untouched()
    assert code == 1, said.err + said.out
    assert "FINDING plan-stale" in said.err
    assert CODE not in said.err
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    adopter.main(args)
    capsys.readouterr()
    assert source.runs() >= 1


def test_execute_reads_no_commit_a_cloned_plan_names_and_the_source_lacks(
        adopter, made, monkeypatch, capsys, tmp_path):
    """The same through a plan whose source `plan` cloned (`source.cloned:
    true`): whether that clone still holds the plan's commit is asked before
    the guard, and git would fetch it. The variable keeps it unfetched, and
    the clone is taken as no longer whole (cloned again, from a GitHub that
    does not have it); with the variable ignored, the same `execute`
    fetches."""
    gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    source = made("cured")
    source.at_the_side_commit(cloned=True)
    skip_where_git_ignores_the_variable(source)
    args = ["execute", "--plan", str(source.plan), "--yes",
            "--local-remote-dir", str(source.base / "remotes"),
            "--work-dir", str(source.base / "work")]
    code = adopter.main(args)
    said = capsys.readouterr()
    source.untouched()
    assert code == 2, said.err + said.out
    assert "no longer whole" in said.out + said.err
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    adopter.main(args)
    capsys.readouterr()
    assert source.runs() >= 1
    assert not (source.base / "remotes").exists()


def test_the_refusal_names_the_filter_key_of_each_promisor_remote(made):
    """Two promisor remotes: each is fetched again, and each keeps the key
    that filters a later fetch."""
    source = made("nocheckout")
    git("config", "remote.second.promisor", "true", cwd=source.path)
    result = source.check()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert ("`git fetch --refetch --no-filter origin`, then `git fetch "
            "--refetch --no-filter second`") in result.stderr
    assert ("Later fetches stay filtered while "
            "`remote.origin.partialclonefilter` or "
            "`remote.second.partialclonefilter` is set") in result.stderr
    source.untouched()


@pytest.mark.parametrize("command", ["check", "execute"])
def test_a_tag_whose_blob_the_source_lacks_is_refused(made, command):
    """Only a tag reaches what is lacking: a cured partial clone lacks
    nothing, then fetches `TAG` with the filter it keeps, and that tag's
    commit changes a spec file, whose blob is not fetched. Its branches lack
    0 objects and its tags lack some. Refused through `check` and through
    `execute`, no leg made, nothing fetched. With `--tags` out of the walk,
    `check` said `plan ok`, and `execute` made both legs and then died in
    `git filter-repo`, `Blob not found`."""
    source = made("cured")
    source.fetch_the_tag()
    assert source.lacking("--branches") == 0
    assert source.lacking("--tags") > 0
    result = getattr(source, command)()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert "plan ok" not in result.stdout
    assert not (source.base / "remotes").exists()
    source.untouched()


def test_a_branch_whose_commit_the_source_lacks_is_refused(made):
    """A branch git cannot walk, written by hand at a commit the source
    lacks: before git 2.45 `rev-list --missing=print` exits 128 on it, and
    from 2.45 it lists it as lacking. Refused either way, by its code
    alone, and nothing is fetched."""
    source = made("cured")
    ghost = source.path / ".git" / "refs" / "heads" / "ghost"
    ghost.write_text(source.planned["side"] + "\n", encoding="ascii")
    source.before = source.store()
    result = source.check()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    source.untouched()


@pytest.mark.parametrize("head", ["born", "unborn"])
def test_a_partial_clone_git_cannot_walk_is_refused_on_any_git(
        adopter, made, monkeypatch, capsys, head):
    """A walk that fails tells nothing of what is lacking, so it is no
    `0`: a cured partial clone, its walk made to fail (an option no git
    has), is refused, naming the walk as run (`HEAD` last where HEAD names a
    commit) and how git exited, saying git could not walk the refs (and no
    object count), naming `git fsck` in the source, as what names a ref
    whose object is lacking and no object a promisor holds, and the cure."""
    monkeypatch.setattr(adopter, "LACKING_WALK",
                        ("rev-list", "--no-such-option"), raising=False)
    source = made("cured")
    if head == "unborn":
        source.unborn_head()
    code = adopter.main(["check", "--plan", str(source.plan),
                         "--work-dir", str(source.base / "work")])
    said = capsys.readouterr()
    walk = "`git rev-list --no-such-option" + (
        " HEAD`" if head == "born" else "`")
    assert code == 2, said.err + said.out
    assert REFUSED in said.err
    assert (f"{walk}, which lists what a clone lacks without fetching it, "
            "exited ") in said.err
    assert "branches, tags and HEAD git could not walk" in said.err
    assert "lacks at least" not in said.err
    assert (f"Remediation: run `git fsck` in "
            f"{adopter.shown_path(source.path)}: it names a branch, tag or "
            "HEAD whose object the repository lacks, and does not list what "
            "a partial clone's promisor remote holds.") in said.err
    assert CURE in said.err
    assert LATER in said.err
    source.untouched()


@pytest.mark.parametrize("command", ["check", "execute"])
def test_a_head_whose_blob_the_source_lacks_is_refused(made, command):
    """Only HEAD reaches what is lacking: a cured partial clone lacks
    nothing, then fetches `TAG` with the filter it keeps, so that the blob
    that tag's commit changes is lacking, moves HEAD to that commit and
    deletes the tag. Its branches and tags lack 0 objects and HEAD's commit
    lacks some. Refused through `check` and through `execute`, no leg made,
    nothing fetched. With HEAD out of the walk, `check` said `plan ok`, and
    `execute` made both legs and then its clone died in the checkout of
    HEAD, `unable to read sha1 file`."""
    source = made("cured")
    source.detach_at_the_fetched_tag()
    assert source.lacking("--branches") == 0
    assert source.lacking("--tags") == 0
    assert source.lacking("HEAD") > 0
    result = getattr(source, command)()
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert "that lacks at least " in result.stderr
    assert "plan ok" not in result.stdout
    assert not (source.base / "remotes").exists()
    source.untouched()


def test_a_head_at_a_commit_the_source_lacks_is_refused_and_not_fetched(
        adopter, made, monkeypatch, capsys):
    """HEAD names a commit the source lacks, written into `.git/HEAD` by
    hand (`git update-ref` would fetch it): refused, and fetched by nothing,
    with the variable ignored too. Asking HEAD for a commit
    (`HEAD^{commit}`) read the object, and fetched it."""
    monkeypatch.setattr(adopter, "NO_LAZY_FETCH", IGNORED, raising=False)
    source = made("cured")
    (source.path / ".git" / "HEAD").write_text(
        source.planned["side"] + "\n", encoding="ascii")
    code = adopter.main(["check", "--plan", str(source.plan),
                         "--work-dir", str(source.base / "work")])
    said = capsys.readouterr()
    assert code == 2, said.err + said.out
    assert REFUSED in said.err
    source.untouched()


@pytest.mark.parametrize("command", [
    "check", pytest.param("execute", marks=needs_filter_repo)])
def test_an_unborn_head_is_read_as_before(made, command):
    """HEAD on a branch that does not exist (`git switch --orphan`) names no
    commit, and a cured partial clone lacks nothing: read as a full clone is,
    nothing fetched. A plain `HEAD` in the walk exits 128 on it, `ambiguous
    argument 'HEAD'`, and would refuse it."""
    source = made("cured")
    source.unborn_head()
    assert source.lacking("--branches") == 0
    result = getattr(source, command)()
    assert result.returncode == 0, result.stderr + result.stdout
    assert CODE not in result.stderr + result.stdout
    if command == "check":
        assert "plan ok" in result.stdout
        source.untouched()
    else:
        assert sorted(path.name
                      for path in (source.base / "remotes").iterdir())
        assert source.runs() == 0


@pytest.mark.parametrize("lacked", ["branch", "tag", "head", "promised"])
def test_git_fsck_names_a_ref_whose_object_is_lacking_and_no_promised_one(
        made, lacked):
    """What the refusal of a walk git could not make says of `git fsck`: it
    names a branch, tag or HEAD whose object the source lacks, and lists no
    object its promisor remote holds. The blobs `nocheckout` lacks are
    promised, and fsck is silent on them; and it fetches nothing."""
    source = made("nocheckout")
    assert source.lacking("--branches") > 0
    ghost = source.planned["side"] + "\n"
    git_dir = source.path / ".git"
    if lacked == "branch":
        (git_dir / "refs" / "heads" / "ghost").write_text(ghost,
                                                          encoding="ascii")
    elif lacked == "tag":
        (git_dir / "refs" / "tags" / "ghost").write_text(ghost,
                                                         encoding="ascii")
    elif lacked == "head":
        (git_dir / "HEAD").write_text(ghost, encoding="ascii")
    fsck = git("fsck", cwd=source.path, check=False)
    said = fsck.stdout + fsck.stderr
    if lacked == "promised":
        assert fsck.returncode == 0, said
        assert said == ""
    else:
        assert fsck.returncode != 0, said
        assert {"branch": "refs/heads/ghost", "tag": "refs/tags/ghost",
                "head": "HEAD"}[lacked] in said
    source.untouched()


@pytest.mark.parametrize(("config", "remotes"), [
    ((("remote.origin.promisor", "true"),), ["origin"]),
    ((("remote.origin.promisor", "yes"),), ["origin"]),
    ((("remote.origin.partialclonefilter", "blob:none"),), ["origin"]),
    ((("extensions.partialclone", "origin"),), ["origin"]),
    ((("remote.origin.promisor", "false"),), []),
    ((("extensions.partialclone", "first"),
      ("remote.second.promisor", "true"),
      ("remote.first.partialclonefilter", "blob:none")),
     ["second", "first"]),
    ((("extensions.partialclone", "o"),
      ("remote.o.promisor", "true"),
      ("remote.p.promisor", "true")), ["p", "o"]),
    ((), []),
], ids=["promisor", "promisor-yes", "filter", "extension", "promisor-false",
        "extension-last", "extension-also-promisor", "none"])
def test_promisor_remotes_reads_git_s_rule(adopter, tmp_path, config,
                                           remotes):
    """Each key git's `promisor-remote.c` reads, the remote
    `extensions.partialclone` names last, one that is also a promisor
    included; `promisor = false` alone is none."""
    git("init", "-q", str(tmp_path / "repo"), cwd=tmp_path)
    for key, value in config:
        git("config", key, value, cwd=tmp_path / "repo")
    assert adopter._promisor_remotes(tmp_path / "repo") == remotes


@pytest.mark.parametrize("before", [None, "0"], ids=["unset", "set"])
def test_lazy_fetch_off_puts_the_environment_back(adopter, monkeypatch,
                                                  before):
    """`GIT_NO_LAZY_FETCH=1` inside, and as it was afterwards, an exception
    included."""
    if before is not None:
        monkeypatch.setenv(VARIABLE, before)

    with pytest.raises(LookupError):
        with adopter._lazy_fetch_off():
            assert os.environ[VARIABLE] == "1"
            raise LookupError
    assert os.environ.get(VARIABLE) == before

    @adopter._lazy_fetch_off()
    def inside() -> str:
        return os.environ[VARIABLE]

    assert inside() == "1"
    assert os.environ.get(VARIABLE) == before
