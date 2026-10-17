# SPDX-License-Identifier: Apache-2.0
"""A kept submodule whose url answers nothing (#418).

`adoption verified` accounts for blobs, and the `NEXT:` it prints is `git
clone --recurse-submodules`, which clones each submodule a leg keeps from its
url, as the leg resolves it. On main nothing asked whether anything answers
there: an absolute url since moved, or a relative one that names the same
empty place from the leg as from the source, passed `check` and `execute`,
and that clone then failed, as the source's own recursive clone already did.
Now each url a leg keeps that names a repository on this machine's disk is
asked with `git ls-remote`, and one that answers nothing is a `check` finding
that `execute` refuses before any leg exists. A url on a network is never
asked, and `check` names it in a NOTE.

No network: every repository is local, a GitHub url is only ever a string,
and the one `ssh` a test could start is a stub that records being started.
These sit beside tests/test_adopt_relative_submodule_url.py (#190), and build
their sources and plans with its helpers.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

from conftest import git
from test_adopt_relative_submodule_url import (  # noqa: F401
    BOTH_IN_CODE, CODE_BARE, DEPENDENCY, DEPENDENCY_TREE, EXTRA, GITMODULES,
    GITHUB_DEPENDENCY, HTTPS_ORIGIN, RELATIVE, REMOTES, SIBLING, THING_REMOTE,
    UPSTREAM, VALUE, VERIFIED, WORK, adopter, check, clone_the_split, execute,
    found, its_org, needs_filter_repo, passes, planned, refusal_of,
    source_with)

#: The finding, as `check` prints it and `execute` raises it.
ANSWERS_NOTHING = "plan-submodule-url-answers-nothing"
#: The issue's relative url: beside whatever holds `.gitmodules`, where
#: nothing is.
MISSING = "../missing"
#: Where the issue's absolute url points, under each test's directory.
NOWHERE = "nowhere.git"
#: What the finding says before git's own words, the rest of which are git's.
UNREACHED = "where `git ls-remote` reaches no repository (fatal: "
#: How the finding ends, for the code leg every plan here keeps it in.
CLONE_FAILS = ("the assembly's recursive clone fails on it in the code leg, "
               "as the source's own recursive clone does")
#: The start of the NOTE about the urls `check` does not ask.
UNASKED = ("NOTE `check` did not ask whether the url of each submodule the "
           "plan keeps in the code leg answers, as that leg resolves it: ")
#: `to `<url>`, the repository it names from the source` in a finding.
THERE_RE = re.compile(r", to `((?:[^`\\]|\\.)*)`, the repository it names "
                      r"from the source, ")
#: What `execute --local-remote-dir`'s refusal adds to its first line when a
#: finding in it resolved a relative url from the remotes it would create,
#: as `check` given the same directory does (#417).
FROM_THE_LOCAL_LEGS = (
    " given the same --local-remote-dir, with each relative submodule url "
    "resolved from the leg remotes this run would create there:")
#: Both platforms' answer for a url that names a drive.
ON_WINDOWS = os.name == "nt"
#: Where the tests' `insteadOf` sends a path, and the url the guard is
#: tried on: ssh, which a stub `GIT_SSH_COMMAND` stands in for.
MIRRORS = "ssh://git@example.invalid/mirrors/"


def unasked_note(*items: str) -> str:
    """The NOTE `check` prints about the urls it does not ask, each of
    `items` as it names one."""
    return (UNASKED + "; ".join(items)
            + ". It asks, with `git ls-remote`, only a url that names a "
            "repository on this machine's disk, and finds one that answers "
            f"nothing as `{ANSWERS_NOTHING}`; whether a url on a network "
            "answers can depend on whose credentials ask, and neither "
            "`check` nor `execute` makes a network call to find out. The "
            "assembly's `git clone --recurse-submodules` asks, after the "
            "legs are made, and fails on one that answers nothing, as the "
            "source's own does.")


def unasked_notes(stdout: str) -> list[str]:
    """The NOTE lines `check` prints about the urls it did not ask."""
    return [line for line in stdout.splitlines() if line.startswith(UNASKED)]


def an_absolute_url(base: Path, as_a_file_url: bool) -> str:
    """NOWHERE under `base`, as a path or as the `file://` url naming it."""
    target = base / NOWHERE
    return target.as_uri() if as_a_file_url else target.as_posix()


def a_recording_ssh(base: Path, monkeypatch) -> Path:
    """`GIT_SSH_COMMAND` set to a stub that records being started and exits
    1, so no ssh is ever reached; the file it records in, under `base`, is
    returned and does not exist yet."""
    started = base / "ssh-started"
    stub = base / "ssh_stub.py"
    stub.write_text(f"open({started.as_posix()!r}, 'w').close()\n"
                    "raise SystemExit(1)\n", encoding="utf-8")
    python = Path(sys.executable).as_posix()
    monkeypatch.setenv("GIT_SSH_COMMAND", f'"{python}" "{stub.as_posix()}"')
    return started


def put_the_dependency_at(target: Path, base: Path) -> None:
    """One way out the remediation names: the repository put where the url
    names it, as a bare clone of `base`'s dependency."""
    git("clone", "-q", "--bare", str(base / "dependency"), str(target),
        cwd=base)


@pytest.mark.parametrize("as_a_file_url", [False, True],
                         ids=["path", "file-url"])
def test_check_finds_an_absolute_url_that_answers_nothing(
        adopter, tmp_path, as_a_file_url):
    """The issue's absolute case. git copies an absolute url as it stands, so
    the source and every leg ask the same place, and on main `check` said
    `plan ok` over a url where nothing is. Now it is found, with the
    submodule, the url and git's words, and the remediation once after it;
    `execute`, with `--local-remote-dir` or without it, refuses it in
    `check`'s words; and with the dependency put where the url names it, the
    same plan passes."""
    url = an_absolute_url(tmp_path, as_a_file_url)
    plan = planned(source_with(tmp_path, url), tmp_path)
    result = check(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    [(code, detail)] = found(result.stderr)
    assert code == ANSWERS_NOTHING
    assert detail.startswith(
        f"the submodule `{DEPENDENCY}` (entry `{UPSTREAM}`) has leg: code, "
        f"and its url in the source's {GITMODULES} is "
        f"{adopter._spelled(url)}, {UNREACHED}"), detail
    assert detail.endswith(CLONE_FAILS), detail
    assert result.stderr.count(adopter.URL_ANSWERS_NOTHING_REMEDIATION) == 1
    for remotes in (None, tmp_path / REMOTES):
        refusal = refusal_of(adopter, plan, tmp_path, remotes)
        assert refusal.detail.splitlines() == [
            f"1 finding(s) in {plan}, as `check` prints them:",
            f"  FINDING {code}: {detail}"]

    put_the_dependency_at(tmp_path / NOWHERE, tmp_path)
    passes(check(plan))


def test_execute_refuses_a_relative_url_that_names_nothing_from_either_side(
        adopter, tmp_path):
    """The issue's relative case. The source's remote sits where `execute
    --local-remote-dir` makes the legs, so `../missing` names one place from
    the source and from the code leg -- which #190 takes as settled -- and
    nothing is there. On main `execute` went on and verified, and the
    assembly's recursive clone failed. Now it refuses before any leg exists,
    and says, as it does of #190's finding, that it resolved the url from
    the leg remotes this run would create. From legs anywhere else the url
    names another repository, and that is #190's finding alone: one cause,
    one finding."""
    remotes = tmp_path / REMOTES
    origin = str(remotes / THING_REMOTE)
    plan = planned(source_with(tmp_path, MISSING, origin), tmp_path,
                   its_org(origin))
    refusal = refusal_of(adopter, plan, tmp_path, remotes)
    assert refusal.code == ANSWERS_NOTHING
    first, finding = refusal.detail.splitlines()
    assert first == f"1 finding(s) in {plan}, as `check` prints them" \
        + FROM_THE_LOCAL_LEGS
    leg = adopter._spelled(str(remotes.resolve() / CODE_BARE))
    assert finding.startswith(
        f"  FINDING {ANSWERS_NOTHING}: the submodule `{DEPENDENCY}` (entry "
        f"`{UPSTREAM}`) has leg: code, and its url in the source's "
        f"{GITMODULES} is the relative `{MISSING}`, which git resolves from "
        f"the code leg, at {leg}, to "), finding
    there = THERE_RE.search(finding)
    assert there, finding
    assert Path(re.sub(r"\\(.)", r"\1", there[1])) \
        == remotes.resolve() / "missing"
    assert UNREACHED in finding
    assert finding.endswith(CLONE_FAILS), finding
    assert refusal.remediation.endswith(
        "\n" + adopter.URL_ANSWERS_NOTHING_REMEDIATION)
    # Where a relative url is resolved from is said of the run, not of the
    # command: `check` given this directory resolves it here too (#417).
    assert ("which is on GitHub, or, under `--local-remote-dir`, the bare "
            "repository `execute` would create there.") in refusal.remediation
    assert "no leg repository was created" in refusal.remediation

    elsewhere = refusal_of(adopter, plan, tmp_path, tmp_path / "elsewhere")
    assert [line.split(": ", 1)[0]
            for line in elsewhere.detail.splitlines()[1:]] \
        == [f"  FINDING {RELATIVE}"]


@needs_filter_repo
@pytest.mark.parametrize("relative", [True, False],
                         ids=["relative", "absolute"])
def test_execute_refuses_before_any_leg_and_the_remediation_clones(
        tmp_path, relative):
    """End to end, as the issue ran it. On main `execute --local-remote-dir`
    said `adoption verified` and the assembly's recursive clone exited 1.
    Now it exits 2 before it makes the remotes directory or writes into its
    work directory, and the source is untouched. With the dependency put
    where the url names it, the same plan adopts and verifies, and the
    assembly's recursive clone checks the dependency out in the leg."""
    remotes = tmp_path / REMOTES
    origin = str(remotes / THING_REMOTE)
    target = remotes / "missing" if relative else tmp_path / NOWHERE
    source = source_with(tmp_path, MISSING if relative else target.as_posix(),
                         origin)
    head = git("rev-parse", "HEAD", cwd=source).stdout
    plan = planned(source, tmp_path, its_org(origin))
    work = tmp_path / WORK
    refused = execute(plan, work, remotes)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {ANSWERS_NOTHING}: 1 finding(s) in " in refused.stderr
    assert VERIFIED not in refused.stdout
    assert not remotes.exists(), "a refused plan made the remotes directory"
    assert list(work.iterdir()) == [], "a refused plan wrote into its work"
    assert git("rev-parse", "HEAD", cwd=source).stdout == head

    put_the_dependency_at(target, tmp_path)
    result = execute(plan, tmp_path / "work-again", remotes)
    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    clone = tmp_path / "clone"
    cloned = clone_the_split(source, clone)
    assert cloned.returncode == 0, cloned.stderr
    assert (clone / "code" / DEPENDENCY / VALUE).read_text() \
        == DEPENDENCY_TREE[VALUE]


def test_check_notes_each_url_it_does_not_ask(adopter, tmp_path, monkeypatch):
    """Against GitHub whether a url answers can depend on whose credentials
    ask, so a url that names no repository on this machine's disk is never
    asked, and `check` passes and names each in ONE NOTE, in the tree's
    order: an absolute url on GitHub, its credential redacted, and #190's
    relative url as the code leg's GitHub remote resolves it, which is the
    issue's GitHub case. Neither is handed to the function that asks."""
    secret = "s3cret-token"
    second = f"https://x-access-token:{secret}@github.com/testorg/second.git"
    plan = planned(source_with(tmp_path, SIBLING, HTTPS_ORIGIN, second=second),
                   tmp_path, answers={**BOTH_IN_CODE, EXTRA: "code"})
    result = check(plan)
    passes(result)
    assert secret not in result.stdout + result.stderr
    assert unasked_notes(result.stdout) == [unasked_note(
        "`https://***@github.com/testorg/second.git` of `extra/second`",
        f"`{SIBLING}` of `{DEPENDENCY}`, to `{GITHUB_DEPENDENCY}`")]

    asked: list[str] = []
    answers = adopter._answers
    monkeypatch.setattr(adopter, "_answers",
                        lambda urls: asked.extend(urls) or answers(urls))
    loaded = adopter.Plan.load(plan)
    adopter._entry_findings(loaded, loaded.open_source(None, tmp_path / WORK))
    assert asked == []


def test_check_given_local_remotes_still_notes_a_url_on_a_network(tmp_path):
    """`check --local-remote-dir` resolves a relative url from the bare
    repositories `execute` would create there, which are on this disk, and
    asks it there (#417); a url on a network it never asks, as without the
    flag, and it names that url in the NOTE all the same."""
    remotes = tmp_path / REMOTES
    origin = str(remotes / THING_REMOTE)
    second = "https://github.com/testorg/second.git"
    plan = planned(source_with(tmp_path, SIBLING, origin,
                               remotes / "dependency", second=second),
                   tmp_path, its_org(origin),
                   answers={**BOTH_IN_CODE, EXTRA: "code"})
    result = check(plan, remotes)
    passes(result)
    assert unasked_notes(result.stdout) == [unasked_note(
        f"`{second}` of `extra/second`")]


def test_a_path_this_machine_rewrites_to_a_network_is_not_asked(
        tmp_path, monkeypatch):
    """A `url.<base>.insteadOf` can send a path on this disk to a network,
    and git rewrites a url before it connects. So a url is asked as git here
    expands it, which contacts nothing, and one the expansion takes off the
    disk is named in the NOTE with where it goes, and never asked: the `ssh`
    git would start for it is a stub that records being started, and it
    never is."""
    started = a_recording_ssh(tmp_path, monkeypatch)
    moved = f"{(tmp_path / 'moved').as_posix()}/"
    config = tmp_path / "gitconfig"
    config.write_text(f'[url "{MIRRORS}"]\n\tinsteadOf = {moved}\n',
                      encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    url = f"{moved}dep.git"
    result = check(planned(source_with(tmp_path, url), tmp_path))
    passes(result)
    # Where it goes is `redacted`, as every url with a scheme is: its user
    # is hidden with any credential.
    assert unasked_notes(result.stdout) == [unasked_note(
        f"`{url}` of `{DEPENDENCY}`, which git here rewrites to "
        "`ssh://***@example.invalid/mirrors/dep.git`")]
    assert not started.exists(), "git started ssh for a url nobody may ask"


def test_git_is_held_to_the_disk_when_it_asks(adopter, tmp_path, monkeypatch):
    """`git ls-remote` asks under `GIT_ALLOW_PROTOCOL=file`, so a url that
    `_on_this_disk` were wrong about still reaches no network: with that
    judgement forced for an `ssh://` url, git itself refuses the transport,
    the answer is what git said, and the `ssh` git would start is never
    started. No global config rewrites the url on the way."""
    started = a_recording_ssh(tmp_path, monkeypatch)
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setattr(adopter, "_on_this_disk", lambda _url: True)
    [(_, said)] = adopter._answers([f"{MIRRORS}dep.git"])
    assert said is not None
    assert not started.exists(), "git started ssh for a url on a network"


@pytest.mark.parametrize("url, on_this_disk", [
    ("/srv/mirrors/dependency.git", True),
    ("file:///srv/mirrors/dependency.git", True),
    # A drive is a drive on Windows alone; elsewhere git reads `C:` as the
    # scp host `C`, which only a network could answer.
    ("C:/mirrors/dependency.git", ON_WINDOWS),
    ("D:\\mirrors\\dependency.git", ON_WINDOWS),
    ("file:///C:/mirrors/dependency.git", ON_WINDOWS),
    ("https://github.com/testorg/dependency.git", False),
    ("git@github.com:testorg/dependency.git", False),
    ("ssh://git@github.com:22/testorg/dependency.git", False),
    ("file://mirror-host/srv/dependency.git", False),
    # Two separators begin a share on another machine on Windows, reached
    # over the network with the asker's credentials, and on POSIX `\\`
    # begins a name relative to the clone: asked on neither.
    ("\\\\fileserver\\git\\dependency.git", False),
    ("//fileserver/git/dependency.git", False),
    ("file:////fileserver/git/dependency.git", False),
    # Relative to wherever the clone is made, which nobody knows yet.
    ("dependency", False),
], ids=["path", "file-url", "drive", "drive-backslash", "drive-file-url",
        "https", "scp", "ssh", "file-url-with-a-host", "unc", "unc-slash",
        "unc-file-url", "bare-name"])
def test_only_a_repository_on_this_disk_is_asked(adopter, url, on_this_disk):
    """The urls `check` and `execute` ask: an absolute path or a `file://`
    url with no host, as git on THIS machine opens one, and never a UNC
    path."""
    assert adopter._on_this_disk(url) is on_this_disk
