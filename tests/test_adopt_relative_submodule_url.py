# SPDX-License-Identifier: Apache-2.0
"""A source submodule's RELATIVE url, resolved from the leg that holds it (#190).

git resolves `url = ../dependency` against the remote of the repository
whose `.gitmodules` holds it: the source's before the split, the LEG's after
it. On main a plan that kept such a submodule in a leg checked out, executed,
and said `adoption verified`, and the assembly's `git clone
--recurse-submodules` then failed wherever the dependency did not sit beside
the leg. `check` now resolves it from both places, as git does, and finds it
where the two differ; `execute` resolves it again from the remotes it would
create and refuses it before it creates any. Given the `--local-remote-dir`
`execute` is given, `check` resolves from the same bare repositories, and
the two give one verdict (#417).

No network: a GitHub url here is only ever a string git resolves against.
Every repository is local, and the end-to-end tests clone from disk.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, clone_just_pushed, git,
                      make_source_repo, resolve, run_script, write_plan)

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: What the test with a symlink ON THE DISK needs; see
#: tests/test_adopt_ignored_shape_files.py for the same guard.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a symlink needs a privilege Windows does not grant by default")

#: The finding, as `check` prints it and `execute` raises it.
RELATIVE = "plan-submodule-relative-url"
SPLIT = "plan-submodule-split"
GITMODULES = ".gitmodules"
UPSTREAM = "upstream/"
EXTRA = "extra/"
#: The submodule every source here holds, a second one some hold, and the
#: one file of the repository each is a commit of.
DEPENDENCY = "upstream/dependency"
SECOND = "extra/second"
VALUE = "value.txt"
DEPENDENCY_TREE = {VALUE: "dependency\n"}
#: The url #190 is about: the dependency beside whatever repository holds
#: `.gitmodules`.
SIBLING = "../dependency"
#: The dependency INSIDE the repository holding `.gitmodules`, and two
#: levels up from it: git's arithmetic, not a sibling's.
INSIDE = "./dependency"
TWO_UP = "../../dependency"
#: The second submodule's url, beside whatever holds `.gitmodules`.
SECOND_SIBLING = "../second"
#: SIBLING with Windows' separator. git takes `..\` for a relative url on
#: every platform and strips it only where `\` separates directories, so on
#: Windows this is #190's own case.
BACKSLASH = "..\\dependency"
#: The source's own name, which every plan here is written in: an in-place
#: adoption keeps it, and `plan` refuses another for a source whose `origin`
#: names its repository (#499).
THING = "Thing"
#: The source's own name for its remote, beside the repositories it makes.
THING_REMOTE = f"{THING}.git"
#: Where each test's `execute` works, and what a verified one says.
WORK = "work"
VERIFIED = "adoption verified"
#: A source whose plan asks nothing but the submodules' questions.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: The plan's own organisation, and one that is not the source's.
ORG, OTHER_ORG = "testorg", "otherorg"
#: Where each test's `execute` makes its leg remotes.
REMOTES = "remotes"
#: The source's remote beside them, as `git remote add origin
#: ../remotes/Thing.git` writes it from `<tmp>/Thing`: RELATIVE.
RELATIVE_ORIGIN = f"../{REMOTES}/{THING_REMOTE}"
#: The code leg's GitHub remote, as `check` with no `--local-remote-dir`
#: resolves from it.
CODE_LEG = "https://github.com/{org}/" + THING + "-code.git"
#: The code leg's bare remote, as `execute --local-remote-dir` names it.
CODE_BARE = f"{THING}-code.git"
#: `check`'s finding for a plan whose organisation is not the source's (#499).
NOT_THE_SOURCE = "plan-not-the-source"
#: The source's `origin` on GitHub, in the spellings a clone may carry.
HTTPS_ORIGIN = "https://github.com/testorg/Thing.git"
SCP_ORIGIN = "git@github.com:testorg/Thing.git"
#: An owner spelled in another case: one organisation to GitHub.
SCP_OTHER_CASE = "git@github.com:TestOrg/Thing.git"
#: What `check` says of the source's base when it is its `origin`.
ITS_ORIGIN = "its remote `origin`"
#: Every source's dependency, from the plan's own organisation on GitHub.
GITHUB_DEPENDENCY = "https://github.com/testorg/dependency"
#: The one leg every plan here keeps the submodules in.
BOTH_IN_CODE = {GITMODULES: "code", UPSTREAM: "code"}


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` as a module: its remediation, its spelling of a
    url in a finding, and `execute`'s refusal."""
    module_spec = importlib.util.spec_from_file_location("adopt_relative",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def source_with(base: Path, url: str, origin: str | None = None,
                dependency: Path | None = None,
                second: str | None = None) -> Path:
    """`base/Thing`, holding DEPENDENCY registered with `url`, and SECOND
    registered with `second` when it is given.

    Each submodule is ADDED from the dependency's absolute path, so nothing
    is fetched from a url that is only a string, and its url is then set in
    `.gitmodules` and committed, as a hand edit would. `origin`, when given,
    is the source's remote: git resolves a relative url against it only
    when asked to.
    """
    dependency = dependency or base / "dependency"
    make_source_repo(dependency, tree=DEPENDENCY_TREE, edits=())
    source = make_source_repo(base / "Thing", tree=SMALL_TREE)
    for path, value in ((DEPENDENCY, url), (SECOND, second)):
        if value is None:
            continue
        git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), path,
            cwd=source)
        git("config", "-f", GITMODULES, f"submodule.{path}.url", value,
            cwd=source)
    commit(source, "Register the dependency")
    if origin is not None:
        git("remote", "add", "origin", origin, cwd=source)
    return source


def commit(source: Path, message: str) -> None:
    git("add", "--", GITMODULES, cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm", message,
        cwd=source)


def planned(source: Path, base: Path, org: str = ORG,
            answers: dict | None = None, name: str | None = None) -> Path:
    """A plan of `source` for `org`, in the source's own name, in a
    directory of its own under `base` (`name`, else `plan-<org>`), with
    `.gitmodules` and DEPENDENCY both kept in code unless `answers` says
    otherwise. `org` is the source's, as `plan` reads it from its `origin`,
    or `plan` refuses it (#499): see `its_org` for a local one."""
    plan = base / (name or f"plan-{org}") / "adoption-plan.yaml"
    plan.parent.mkdir(parents=True)
    written = write_plan(source, plan, project=THING, org=org)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in (answers or BOTH_IN_CODE).items():
        resolve(plan, path, leg)
    return plan


def its_org(origin: str) -> str:
    """The organisation a LOCAL `origin` names, as `plan` reads one (#499):
    the directory its repository is in, `remotes` for `remotes/Thing.git`.
    (Where git keeps the path with `\\`, as on Windows, `plan` reads no
    repository from it, and compares nothing.)"""
    return Path(origin).parent.name


def in_another_org(plan: Path, org: str) -> Path:
    """`plan` with its `org:` edited by hand to `org`: legs in another
    organisation than the source's, which no `plan` writes since #499, so
    `check` finds the plan `plan-not-the-source` beside anything else, and
    lists it first, as `execute` refuses it before anything else (#1113)."""
    text = plan.read_bytes().decode()
    line = f"\norg: {ORG}\n"
    assert line in text, text
    plan.write_bytes(text.replace(line, f"\norg: {org}\n", 1).encode())
    return plan


def check(plan: Path, remotes: Path | None = None):
    """`check` of `plan`; given `remotes`, `check --local-remote-dir
    <remotes>` (#417), which resolves each relative url from the bare
    repositories `execute --local-remote-dir <remotes>` would create."""
    given = () if remotes is None else ("--local-remote-dir", str(remotes))
    return run_script(ADOPT, "check", "--plan", str(plan), *given)


def found(stderr: str) -> list[tuple[str, str]]:
    """`(code, detail)` for each `FINDING <code>: <detail>` line."""
    return [tuple(line.split(" ", 1)[1].split(": ", 1))
            for line in stderr.splitlines() if line.startswith("FINDING ")]


def finding_lines(text: str) -> list[str]:
    """Each `FINDING` line of `text`, as `check` prints it: a refusal of
    `execute`'s lists `check`'s lines under its first, each indented by
    two spaces."""
    return [line.removeprefix("  ") for line in text.splitlines()
            if line.removeprefix("  ").startswith("FINDING ")]


def notes(stdout: str) -> list[str]:
    """The NOTE lines `check` prints about the relative urls it resolved."""
    return [line for line in stdout.splitlines()
            if line.startswith("NOTE `check` resolved")]


def moved(adopter, url: str, base: str, which: str, here: str, remote: str,
          there: str, path: str = DEPENDENCY, entry: str = UPSTREAM) -> str:
    """The detail of the finding, for the submodule at `path` kept in code.
    `here` and `there` are git's resolutions, spelled; every other url is
    spelled here as the tool spells it, which on Windows doubles each
    backslash of a path. The submodule and its entry are between backticks,
    as every path a finding names is (#212)."""
    spelled = adopter._spelled
    return (f"the submodule `{path}` (entry `{entry}`) has leg: code, and "
            f"its url in the source's {GITMODULES} is the relative "
            f"{spelled(url)}, which git resolves against the remote of the "
            f"repository holding that file: from the source, at "
            f"{spelled(base)} ({which}), {here}, and from the code leg, at "
            f"{spelled(remote)}, {there}; the assembly's recursive clone "
            "resolves it from the leg")


def alike(org: str, *resolved: tuple[str, str, str]) -> str:
    """The NOTE `check` prints when every `(url, path, resolution)` names,
    from the code leg on GitHub, the repository it names from the source."""
    return ("NOTE `check` resolved the relative url of each submodule the "
            "plan keeps in the code leg from that leg's GitHub remote, "
            f"`{CODE_LEG.format(org=org)}`, and each names the same "
            "repository from there as from the source: "
            + "; ".join(f"`{url}` of `{path}`, to `{to}`"
                        for url, path, to in resolved)
            + ". `execute --local-remote-dir` resolves it again from the bare "
            "repository it would create instead, and refuses there, before "
            "it creates any leg, a url that names another repository; "
            "`check`, given the same `--local-remote-dir`, resolves it there "
            "too.")


#: `from the <leg> leg, at `<remote>`, to `<url>`; ` in a finding.
LEG_RESOLUTION_RE = re.compile(
    r"from the (spec|code) leg, at `(?:[^`\\]|\\.)*`, "
    r"to `((?:[^`\\]|\\.)*)`; ")


def resolved_from_the_leg(detail: str, leg: str = "code") -> Path:
    """The url git resolved from `leg`, as the path it names: the
    spelling's backslash escapes undone, so the comparison is a Path's and
    holds whichever separator git joined it with."""
    spelled = LEG_RESOLUTION_RE.search(detail)
    assert spelled and spelled[1] == leg, detail
    return Path(re.sub(r"\\(.)", r"\1", spelled[2]))


def passes(result) -> None:
    assert result.returncode == 0, result.stderr + result.stdout
    assert "plan ok" in result.stdout
    assert RELATIVE not in result.stderr + result.stdout


# --- `check`, on the GitHub remotes the plan names --------------------------


@pytest.mark.parametrize("origin, resolved", [
    (HTTPS_ORIGIN, GITHUB_DEPENDENCY),
    (SCP_ORIGIN, "git@github.com:testorg/dependency"),
    (SCP_OTHER_CASE, "git@github.com:TestOrg/dependency"),
    # A port, and GitHub's SSH-over-the-HTTPS-port host: GitHub all the same.
    ("ssh://git@github.com:22/testorg/Thing.git",
     "ssh://git@github.com:22/testorg/dependency"),
    ("ssh://git@ssh.github.com:443/testorg/Thing.git",
     "ssh://git@ssh.github.com:443/testorg/dependency"),
], ids=["https", "scp", "scp-other-case", "ssh-port", "ssh-github-443"])
def test_check_keeps_a_relative_url_its_github_leg_resolves_alike(
        adopter, tmp_path, origin, resolved):
    """(a) Legs in the source's own organisation sit beside its dependency
    on GitHub, so `../dependency` names one repository from both, however
    the source's `origin` spells it, a port and `ssh.github.com` included:
    no finding, and the NOTE says which remotes `check` asked. In another
    organisation it names another repository, and that is found, with the
    submodule, its url, the leg's remote and both resolutions, and the
    remediation once after it. A url with a scheme is printed through
    `redacted`, which hides its user too (`ssh://***@github.com:22/...`).
    Only a hand edit puts the legs in another organisation than the
    source's, which `check` finds too (#499), first, as `execute` refuses
    it first (#1113)."""
    source = source_with(tmp_path, SIBLING, origin)
    same = check(planned(source, tmp_path))
    passes(same)
    assert notes(same.stdout) == [alike(ORG, (SIBLING, DEPENDENCY,
                                              GITHUB_DEPENDENCY))]

    result = check(in_another_org(
        planned(source, tmp_path, name=f"plan-{OTHER_ORG}"), OTHER_ORG))
    assert result.returncode == 1, result.stderr + result.stdout
    (other, _), relative = found(result.stderr)
    assert relative == (RELATIVE, moved(
        adopter, SIBLING, adopter.redacted(origin), ITS_ORIGIN,
        f"to `{adopter.redacted(resolved)}`", CODE_LEG.format(org=OTHER_ORG),
        "to `https://github.com/otherorg/dependency`"))
    assert other == NOT_THE_SOURCE
    assert notes(result.stdout) == []
    # Said once, after the findings, and it is not #166's remediation.
    assert result.stderr.count(adopter.RELATIVE_URL_REMEDIATION) == 1
    assert adopter.SUBMODULE_REMEDIATION not in result.stderr
    assert result.stderr.index("FINDING ") \
        < result.stderr.index(adopter.RELATIVE_URL_REMEDIATION) \
        < result.stderr.index(" finding(s) in ")


@pytest.mark.parametrize("url, there", [
    # Inside the repository that holds it: another one for every leg.
    (INSIDE,
     "to `https://github.com/testorg/Thing-code.git/dependency`"),
    # More `..` than the remote has components: git says so, in words
    # this pins only the start of, since they are git's to change.
    ("../" * 8 + "dependency", "not at all (fatal: "),
], ids=["dot-slash", "too-many-dotdots"])
def test_check_finds_a_relative_url_no_github_leg_resolves_alike(
        tmp_path, url, there):
    """`./dependency` names a repository INSIDE the one holding
    `.gitmodules`, so no leg resolves it to the source's; a url git cannot
    resolve from the leg is one the assembly's clone fails on. Both are found
    in the plan's own organisation, where `../dependency` is not."""
    source = source_with(tmp_path, url, HTTPS_ORIGIN)
    result = check(planned(source, tmp_path))
    assert result.returncode == 1, result.stderr + result.stdout
    [(code, detail)] = found(result.stderr)
    assert code == RELATIVE
    assert f"from the code leg, at `{CODE_LEG.format(org=ORG)}`, {there}" \
        in detail, detail
    assert detail.endswith("; the assembly's recursive clone resolves it "
                           "from the leg"), detail


def test_a_source_with_no_remote_resolves_from_its_own_directory(adopter,
                                                                 tmp_path):
    """With no remote, git resolves a relative url against the source's own
    directory, so `../dependency` is the directory beside the source -- and
    a GitHub leg resolves it to GitHub. `check` says which it used."""
    source = source_with(tmp_path, SIBLING)
    result = check(planned(source, tmp_path))
    assert result.returncode == 1, result.stderr + result.stdout
    resolved = adopter._spelled((tmp_path / "dependency").as_posix())
    assert found(result.stderr) == [(RELATIVE, moved(
        adopter, SIBLING, source.as_posix(),
        "its own directory, as it has no remote `origin`", f"to {resolved}",
        CODE_LEG.format(org=ORG), f"to `{GITHUB_DEPENDENCY}`"))]


def test_the_source_resolves_from_the_remote_its_branch_tracks(tmp_path):
    """git's default remote is the one the branch tracks, and `origin` only
    when it tracks none: a `main` that tracks a fork resolves against the
    fork, and against `origin`, the repository being adopted, once it
    tracks none. (`origin` is the source's own repository, which the plan
    names, #499; the fork is the remote it tracks.)"""
    source = source_with(tmp_path, SIBLING, HTTPS_ORIGIN)
    git("remote", "add", "fork", "https://github.com/someone/Thing.git",
        cwd=source)
    git("config", "branch.main.remote", "fork", cwd=source)
    result = check(planned(source, tmp_path))
    assert [code for code, _ in found(result.stderr)] == [RELATIVE]
    assert ("from the source, at `https://github.com/someone/Thing.git` "
            "(its remote `fork`), to `https://github.com/someone/dependency`"
            ) in result.stderr
    git("config", "--unset", "branch.main.remote", cwd=source)
    passes(check(planned(source, tmp_path, name="untracked")))


def test_each_relative_url_is_resolved_on_its_own(adopter, tmp_path):
    """Two submodules in one leg, resolved in one scratch repository: the
    one whose url names another repository from the leg is found, by its
    own path and url, and the one that does not is not; with both alike,
    the NOTE names both, in the tree's order."""
    source = source_with(tmp_path, INSIDE, HTTPS_ORIGIN,
                         second=SECOND_SIBLING)
    answers = {**BOTH_IN_CODE, EXTRA: "code"}
    result = check(planned(source, tmp_path, answers=answers))
    assert found(result.stderr) == [(RELATIVE, moved(
        adopter, INSIDE, HTTPS_ORIGIN, ITS_ORIGIN,
        "to `https://github.com/testorg/Thing.git/dependency`",
        CODE_LEG.format(org=ORG),
        "to `https://github.com/testorg/Thing-code.git/dependency`"))]
    assert notes(result.stdout) == []

    both = source_with(tmp_path / "both", SIBLING, HTTPS_ORIGIN,
                       second=SECOND_SIBLING)
    result = check(planned(both, tmp_path / "both", answers=answers))
    passes(result)
    assert notes(result.stdout) == [alike(
        ORG, (SECOND_SIBLING, SECOND, "https://github.com/testorg/second"),
        (SIBLING, DEPENDENCY, GITHUB_DEPENDENCY))]


def test_a_dropped_submodule_leaves_its_relative_url_inert(tmp_path):
    """git resolves the url of a submodule it finds a gitlink for, and of no
    other: dropped on its own, its registration stays behind in the leg and
    is never resolved, and nothing is said of it. Kept, it is found."""
    source = source_with(tmp_path, SIBLING)
    dropped = check(planned(source, tmp_path,
                            answers={GITMODULES: "code", UPSTREAM: "drop"}))
    passes(dropped)
    assert notes(dropped.stdout) == []
    kept = check(planned(source, tmp_path, name="kept"))
    assert [code for code, _ in found(kept.stderr)] == [RELATIVE]


def test_a_split_submodule_is_a_split_and_nothing_more(tmp_path):
    """A submodule kept away from its `.gitmodules` is #166's split: the
    leg that holds it holds no url for it, relative or not, so it is not
    also a relative url resolved from a leg."""
    source = source_with(tmp_path, SIBLING)
    result = check(planned(source, tmp_path,
                           answers={GITMODULES: "code", UPSTREAM: "spec"}))
    assert [code for code, _ in found(result.stderr)] == [SPLIT]


def test_a_credential_in_the_source_remote_is_never_printed(adopter,
                                                            tmp_path):
    """A source's `origin` may carry a token, and every url resolved against
    it carries it too. The finding names both with the credential redacted,
    as the doctor does, and the token appears nowhere `check` writes."""
    secret = "s3cret-token"
    origin = f"https://x-access-token:{secret}@github.com/testorg/Thing.git"
    source = source_with(tmp_path, SIBLING, origin)
    result = check(in_another_org(
        planned(source, tmp_path, name=f"plan-{OTHER_ORG}"), OTHER_ORG))
    assert secret not in result.stderr + result.stdout
    (other, _), relative = found(result.stderr)
    assert relative == (RELATIVE, moved(
        adopter, SIBLING,
        "https://***@github.com/testorg/Thing.git", ITS_ORIGIN,
        "to `https://***@github.com/testorg/dependency`",
        CODE_LEG.format(org=OTHER_ORG),
        "to `https://github.com/otherorg/dependency`"))
    # #499's finding names the source by the `org/repo` its `origin` ends
    # in, which holds no credential.
    assert other == NOT_THE_SOURCE
    # And from the plan's own organisation it is one repository: the
    # credential is not part of a repository's identity.
    same = check(planned(source, tmp_path))
    passes(same)
    assert secret not in same.stderr + same.stdout


def test_an_absolute_url_resolves_nothing(adopter, tmp_path, monkeypatch):
    """(d) A url that is not relative is copied by git as it stands, so it
    is never resolved and `_resolved` makes no scratch repository for it: a
    source with an absolute url that answers (#418) checks exactly as it did
    on #166's base, with no finding and no NOTE. The same plan with a
    relative url is resolved."""
    def refuse(*_):
        raise AssertionError("a url was resolved")

    monkeypatch.setattr(adopter, "_resolved", refuse)
    dependency = tmp_path / "dependency"
    absolute = source_with(tmp_path / "absolute", dependency.as_posix(),
                           dependency=dependency)
    plan = adopter.Plan.load(planned(absolute, tmp_path / "absolute"))
    opened = plan.open_source(None, tmp_path / WORK)
    assert adopter._entry_findings(plan, opened) == ([], [], [])

    relative = source_with(tmp_path / "relative", SIBLING)
    plan = adopter.Plan.load(planned(relative, tmp_path / "relative"))
    opened = plan.open_source(None, tmp_path / WORK)
    with pytest.raises(AssertionError, match="a url was resolved"):
        adopter._entry_findings(plan, opened)


# --- `execute`, on the remotes it would create -------------------------------


def refusal_of(adopter, plan: Path, tmp_path: Path,
               remotes: Path | None = None):
    """What `_refuse_what_check_finds` raises for `plan` against the leg
    remotes `execute` would make under `remotes`, or GitHub's; None when it
    raises nothing."""
    loaded = adopter.Plan.load(plan)
    opened = loaded.open_source(None, tmp_path / WORK)
    try:
        adopter._refuse_what_check_finds(loaded, opened, remotes)
    except adopter.Refusal as refusal:
        return refusal
    return None


@pytest.mark.parametrize("origin, url, org", [
    (HTTPS_ORIGIN, SIBLING, ORG),
    (SCP_ORIGIN, SIBLING, ORG),
    (SCP_OTHER_CASE, SIBLING, ORG),
    # git's arithmetic: two `..` leave the organisation behind. It is the
    # source's own, as every plan's is since #499; one in another was this
    # case's point, and is now `plan-not-the-source` first.
    (HTTPS_ORIGIN, TWO_UP, ORG),
], ids=["https", "scp", "scp-other-case", "dotdot-dotdot"])
def test_execute_resolves_again_from_the_remotes_it_would_create(
        adopter, tmp_path, monkeypatch, origin, url, org):
    """(c) `check` with no `--local-remote-dir` resolves from GitHub's
    remotes, where these plans name one repository from both and pass, and
    says so. `execute --local-remote-dir` resolves again from the bare
    repositories it would make there, where they do not, and refuses before
    it makes any -- saying that `check` prints the finding given the same
    `--local-remote-dir`, which it does, line for line, making nothing
    (#417)."""
    source = source_with(tmp_path, url, origin)
    plan = planned(source, tmp_path, org)
    checked = check(plan)
    passes(checked)
    assert len(notes(checked.stdout)) == 1
    remotes = tmp_path / REMOTES
    given = check(plan, remotes)
    assert given.returncode == 1, given.stderr + given.stdout
    # Every refusal here comes before the tool would be used.
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / WORK))
    refusal = caught.value
    assert refusal.code == RELATIVE
    first, finding = refusal.detail.splitlines()
    assert first == (
        f"1 finding(s) in {plan}, as `check` prints them given the same "
        "--local-remote-dir, with each relative submodule url resolved from "
        "the leg remotes this run would create there:")
    assert finding_lines(given.stderr) == finding_lines(refusal.detail)
    leg = adopter._spelled(str(remotes.resolve() / CODE_BARE))
    assert finding.startswith(f"  FINDING {RELATIVE}: the submodule "
                              f"`{DEPENDENCY}` (entry `{UPSTREAM}`)"), finding
    assert f", and from the code leg, at {leg}, to " in finding
    assert refusal.remediation.endswith(
        "\n" + adopter.RELATIVE_URL_REMEDIATION)
    assert ("which `check` asks only when given the same "
            "`--local-remote-dir`") in refusal.remediation
    assert "no leg repository was created" in refusal.remediation
    assert not remotes.exists()


def test_execute_without_local_remotes_refuses_what_check_prints(
        adopter, tmp_path):
    """Against GitHub, `execute` resolves from the remotes `check` resolved
    from, so its refusal is `check`'s list, line for line, under the first
    line `check`'s refusals have always had."""
    source = source_with(tmp_path, SIBLING)
    plan = planned(source, tmp_path)
    printed = found(check(plan).stderr)
    assert [code for code, _ in printed] == [RELATIVE]
    refusal = refusal_of(adopter, plan, tmp_path)
    assert refusal.code == RELATIVE
    assert refusal.detail.splitlines() == [
        f"1 finding(s) in {plan}, as `check` prints them:",
        *(f"  FINDING {code}: {detail}" for code, detail in printed)]


def test_the_refusal_says_nothing_of_local_remotes_it_did_not_use(
        adopter, tmp_path):
    """Under `--local-remote-dir` a plan refused for anything BUT a relative
    url is refused in `check`'s words: the first line adds nothing about
    remotes it resolved nothing from."""
    source = source_with(tmp_path, SIBLING)
    plan = planned(source, tmp_path,
                   answers={GITMODULES: "code", UPSTREAM: "spec"})
    refusal = refusal_of(adopter, plan, tmp_path, tmp_path / REMOTES)
    assert refusal.code == SPLIT
    assert refusal.detail.splitlines()[0] \
        == f"1 finding(s) in {plan}, as `check` prints them:"


@needs_disk_symlinks
def test_one_directory_through_a_symlink_is_one_repository(adopter,
                                                           tmp_path):
    """The source's `origin` reaches the remotes directory through a
    symlink, and `--local-remote-dir` names it directly: two spellings, one
    directory, so `../dependency` names one repository from both and is not
    refused. The dependency is there, as a url that answers nothing is
    refused for that (#418). A directory that is not the same one is."""
    remotes = tmp_path / REMOTES
    remotes.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(remotes, link, target_is_directory=True)
    except OSError as exc:
        # A platform, or a filesystem, that refuses one: not a failure.
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    linked = source_with(tmp_path / "linked", SIBLING,
                         str(link / THING_REMOTE), remotes / "dependency")
    plan = planned(linked, tmp_path / "linked",
                   its_org(str(link / THING_REMOTE)))
    assert refusal_of(adopter, plan, tmp_path, remotes) is None

    there = str(tmp_path / "elsewhere" / THING_REMOTE)
    elsewhere = source_with(tmp_path / "elsewhere", SIBLING, there)
    plan = planned(elsewhere, tmp_path / "elsewhere", its_org(there))
    refusal = refusal_of(adopter, plan, tmp_path, remotes)
    assert refusal is not None and refusal.code == RELATIVE


@pytest.mark.parametrize("relative", [True, False],
                         ids=["relative-origin", "absolute-origin"])
def test_a_relative_origin_resolves_from_the_source_working_tree(
        adopter, tmp_path, relative):
    """git resolves `../dependency` against the RELATIVE origin
    `../remotes/Thing.git` to `../remotes/dependency`, keeps it relative,
    and the clone opens it from the source's working tree: the directory
    beside the bare legs `execute --local-remote-dir` would make there,
    which name it too, so nothing is refused, as on main. With the legs
    anywhere else it names another repository and is refused, and the
    finding names the directory git opens and says why. The same remote
    spelled absolute resolves to an absolute path, said as before. `check`
    given either directory says what `execute` given it says (#417)."""
    remotes = tmp_path / REMOTES
    origin = RELATIVE_ORIGIN if relative else str(remotes / THING_REMOTE)
    source = source_with(tmp_path, SIBLING, origin, remotes / "dependency")
    plan = planned(source, tmp_path, its_org(origin))
    assert refusal_of(adopter, plan, tmp_path, remotes) is None
    given = check(plan, remotes)
    passes(given)
    # It checks for the run that skips the topics, and says so as that run.
    assert "  topics skipped for local remotes" in given.stdout.splitlines()

    elsewhere = tmp_path / "elsewhere"
    refusal = refusal_of(adopter, plan, tmp_path, elsewhere)
    assert refusal is not None and refusal.code == RELATIVE
    assert finding_lines(check(plan, elsewhere).stderr) \
        == finding_lines(refusal.detail)
    [_, finding] = refusal.detail.splitlines()
    if relative:
        which = f"{ITS_ORIGIN}, relative to its working tree"
        opened = (tmp_path.resolve() / "Thing"
                  / f"../{REMOTES}/dependency").as_posix()
    else:
        # git keeps the base's own separators and joins with `/`.
        which, opened = ITS_ORIGIN, f"{remotes}/dependency"
    assert (f"from the source, at {adopter._spelled(origin)} ({which}), to "
            f"{adopter._spelled(opened)}, and from the code leg, at ") \
        in finding, finding
    assert resolved_from_the_leg(finding) \
        == elsewhere.resolve() / "dependency"


def execute(plan: Path, work: Path, remotes: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(remotes),
                      "--work-dir", str(work))


def clone_the_split(source: Path, clone: Path):
    """`git clone --recurse-submodules` of the branch `execute` pushed the
    split to: what a person runs next."""
    return clone_just_pushed(source, clone, "adopt/three-repo-shape")


@needs_filter_repo
@pytest.mark.parametrize("url, leg, there", [
    # #190 itself: the re-verifier's `relative-url` case.
    (SIBLING, "code", "remotes/dependency"),
    (INSIDE, "code", "remotes/Thing-code.git/dependency"),
    (TWO_UP, "code", "dependency"),
    # The SPEC leg's own remote, which `./` names from inside.
    (INSIDE, "spec", "remotes/Thing-spec.git/dependency"),
    # Where `\` separates nothing, git appends `..\dependency` whole.
    (BACKSLASH, "code",
     "remotes/dependency" if sys.platform == "win32"
     else "remotes/Thing-code.git/..\\dependency"),
], ids=["dotdot", "dot-slash", "dotdot-dotdot", "spec-leg", "backslash"])
def test_execute_refuses_a_relative_url_its_leg_resolves_elsewhere(
        tmp_path, url, leg, there):
    """A source with no remote of its own, as the re-verifier built it:
    `check` with no `--local-remote-dir` finds it from GitHub's remotes, and
    `execute --local-remote-dir` from the bare ones it would make. On main
    both passed, `execute` said `adoption verified`, and the assembly's
    recursive clone exited 1. Now `execute` exits 2 before the remotes
    directory exists, and the source is untouched -- from either leg, and
    for `..\\` as for `../`."""
    source = source_with(tmp_path, url)
    head = git("rev-parse", "HEAD", cwd=source).stdout
    plan = planned(source, tmp_path, answers={GITMODULES: leg, UPSTREAM: leg})
    assert [code for code, _ in found(check(plan).stderr)] == [RELATIVE]
    remotes, work = tmp_path / REMOTES, tmp_path / WORK
    result = execute(plan, work, remotes)
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED {RELATIVE}: 1 finding(s) in " in result.stderr
    [detail] = [line.split(": ", 1)[1] for line in result.stderr.splitlines()
                if line.startswith(f"  FINDING {RELATIVE}: ")]
    assert resolved_from_the_leg(detail, leg) == tmp_path.resolve() / there
    assert "creating the leg repositories" not in result.stdout
    assert VERIFIED not in result.stdout
    assert not remotes.exists(), "a refused plan made the remotes directory"
    assert list(work.iterdir()) == [], "a refused plan wrote into its work"
    assert git("rev-parse", "HEAD", cwd=source).stdout == head


@needs_filter_repo
def test_the_remediation_adopts_and_clones(tmp_path):
    """The refusal's remediation works: the absolute url committed in the
    source's `.gitmodules`, a fresh plan answered as before, and `check`
    passes with nothing to say of it, `execute` verifies into the remotes
    the refused run never made, and the assembly's recursive clone fetches
    the dependency into the leg."""
    source = source_with(tmp_path, SIBLING)
    remotes = tmp_path / REMOTES
    refused = execute(planned(source, tmp_path), tmp_path / WORK, remotes)
    assert f"REFUSED {RELATIVE}: " in refused.stderr, refused.stderr

    git("config", "-f", GITMODULES, f"submodule.{DEPENDENCY}.url",
        (tmp_path / "dependency").as_posix(), cwd=source)
    commit(source, "Register the dependency by its absolute url")
    plan = planned(source, tmp_path, name="replanned")
    checked = check(plan)
    passes(checked)
    assert notes(checked.stdout) == []
    result = execute(plan, tmp_path / "work-again", remotes)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    clone = tmp_path / "clone"
    cloned = clone_the_split(source, clone)
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / "code" / DEPENDENCY / VALUE).read_text() \
        == DEPENDENCY_TREE[VALUE]


@needs_filter_repo
@pytest.mark.parametrize("url, origin, legs", [
    # The dependency beside the source's remote, and the legs beside both.
    (SIBLING, THING_REMOTE, "."),
    # Two levels: the source's remote and the legs in sibling directories.
    (TWO_UP, f"sources/{THING_REMOTE}", "legs"),
    # The first layout with the remote written relative to the source.
    (SIBLING, RELATIVE_ORIGIN, "."),
], ids=["dotdot", "dotdot-dotdot", "relative-origin"])
def test_a_relative_url_its_leg_resolves_alike_adopts_and_clones(
        tmp_path, url, origin, legs):
    """(a) end to end. The source's `origin` and the legs are local, in a
    layout where its relative url names the dependency from both: `check`
    with no `--local-remote-dir`, which resolves from GitHub's remotes, finds
    it, and `execute`, which resolves from the ones it makes, adopts and
    verifies, and the assembly's `git clone --recurse-submodules` and
    `bootstrap.py` both exit 0 with the dependency checked out in the leg,
    whose `.gitmodules` still says what the source committed. An `origin`
    beginning `..` is written as it stands, relative to the source's working
    tree; any other is a path in the remotes directory."""
    remotes = tmp_path / REMOTES
    dependency = remotes / "dependency"
    origin = origin if origin.startswith("..") else str(remotes / origin)
    source = source_with(tmp_path, url, origin, dependency)
    plan = planned(source, tmp_path, its_org(origin))
    assert [code for code, _ in found(check(plan).stderr)] == [RELATIVE]
    result = execute(plan, tmp_path / WORK, remotes / legs)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    clone = tmp_path / "clone"
    cloned = clone_the_split(source, clone)
    assert cloned.returncode == 0, cloned.stderr
    leg = clone / "code"
    assert git("config", "-f", GITMODULES, "--get",
               f"submodule.{DEPENDENCY}.url", cwd=leg).stdout.strip() == url
    assert (leg / DEPENDENCY / VALUE).read_text() == DEPENDENCY_TREE[VALUE]
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, (bootstrapped.stderr
                                          + bootstrapped.stdout)


# --- `check --local-remote-dir`, on the remotes `execute` would create ------


@needs_filter_repo
@pytest.mark.parametrize("local", [True, False],
                         ids=["A-local-origin", "B-github-origin"])
def test_check_and_execute_given_one_local_remote_dir_agree(tmp_path, local):
    """#417's two layouts, end to end as the issue ran them: `../dependency`
    both times, and the dependency beside the legs `execute
    --local-remote-dir` makes. A: the source's `origin` is there too, so the
    url names one repository from the source and from a leg there. B: the
    `origin` is on GitHub, and the url names another repository from a leg
    there. `check` with no `--local-remote-dir` resolves from GitHub's
    remotes and says the opposite in each: a finding over an adoption that
    verifies in A, and `plan ok` over one `execute` refuses in B. Given the
    directory `execute` is given, `check` says what `execute` says: in A it
    passes, `execute` verifies and the assembly's recursive clone checks the
    dependency out in the leg; in B it finds what `execute` refuses, line
    for line, and neither makes a leg."""
    remotes = tmp_path / REMOTES
    origin = str(remotes / THING_REMOTE) if local else HTTPS_ORIGIN
    source = source_with(tmp_path, SIBLING, origin, remotes / "dependency")
    plan = planned(source, tmp_path, its_org(origin) if local else ORG)
    on_github = check(plan)
    given = check(plan, remotes)
    result = execute(plan, tmp_path / WORK, remotes)
    assert finding_lines(given.stderr) == finding_lines(result.stderr)
    assert [code for code, _ in found(on_github.stderr)] \
        == ([RELATIVE] if local else [])
    if not local:
        assert [code for code, _ in found(given.stderr)] == [RELATIVE]
        assert (given.returncode, result.returncode) == (1, 2), \
            given.stderr + result.stderr
        assert not (remotes / CODE_BARE).exists()
        return
    passes(given)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    clone = tmp_path / "clone"
    cloned = clone_the_split(source, clone)
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / "code" / DEPENDENCY / VALUE).read_text() \
        == DEPENDENCY_TREE[VALUE]


@needs_filter_repo
def test_check_names_another_repository_first_as_execute_refuses_it(
        tmp_path):
    """A plan for another repository beside a relative url its leg resolves
    elsewhere (#1113): `execute` refuses `plan-not-the-source` before it
    resolves any url (#499), so `check`, given the same `--local-remote-dir`
    or none, lists that first and the url after it. On #1125's head `check`
    listed the url first, so its first finding was not `execute`'s refusal.
    Neither makes a leg."""
    source = source_with(tmp_path, SIBLING, HTTPS_ORIGIN)
    plan = in_another_org(
        planned(source, tmp_path, name=f"plan-{OTHER_ORG}"), OTHER_ORG)
    remotes = tmp_path / REMOTES
    for checked in (check(plan), check(plan, remotes)):
        assert checked.returncode == 1, checked.stderr + checked.stdout
        assert [code for code, _ in found(checked.stderr)] \
            == [NOT_THE_SOURCE, RELATIVE], checked.stderr
    result = execute(plan, tmp_path / WORK, remotes)
    assert result.returncode == 2, result.stderr + result.stdout
    [refused] = [line for line in result.stderr.splitlines()
                 if line.startswith("REFUSED ")]
    assert refused.startswith(f"REFUSED {NOT_THE_SOURCE}: "), refused
    assert not remotes.exists(), "a refused plan made the remotes directory"
