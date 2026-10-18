# SPDX-License-Identifier: Apache-2.0
r"""A `--local-remote-dir` the tools cannot write down is refused by every tool
that writes it, with a remedy that says why, and the clone line the READMEs
print pastes as one command (#693).

#640 (#433) asked `unwritable_reason` of the clone URL `scaffold-project.py`
and `family.py init` write into their READMEs. Four things were left, each
measured on main:

  * `family.py add --local-remote-dir <dir>/caf<e9>` exited 0, dry run and
    real, and committed the byte into the holder's `.gitmodules`, where the
    holder's `make siblings` read the URL back as `caf\ufffd`, another path;
    a line break, an escape and a bidi override were committed too. `add`
    now asks `init`'s question of the member's URL, before the member is
    read or anything is mounted, `--dry-run` alike, and refuses
    `family-unwritable-value`.
  * `--local-remote-dir link`, a UTF-8 name linked to a `caf<e9>` directory,
    was refused naming the RESOLVED URL, by a remedy that said to pass a path
    that is UTF-8 text, which it was. Each remedy now says that the URL is
    the resolved path, and that a link's target is then the fault.
  * a lone surrogate, the unpaired UTF-16 half a Windows name can hold, is a
    reason `unwritable_reason` gives, and no clone-URL remedy named it. Linux
    has no file name that decodes to one, so it is asked of each refusal
    function directly.
  * the READMEs' `git clone --recurse-submodules <url>` line took a local
    path raw, so under `a b/` or `it's/` it split when pasted. The URL is now
    one word in the POSIX dialect, and an ordinary path is left bare.

NO NETWORK AND NO GITHUB, on the harnesses of `test_clone_url_bytes.py` and
`test_family_add_refusals.py`: local bare repositories, a `gh` that logs and
exits 97 (or no process at all, where a refusal comes first), and directory
names made from BYTES, skipped where the disk cannot hold one. Every
invisible character in this file is spelled as an escape.
"""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

import pytest

from conftest import SCAFFOLD, git, pasted
from test_clone_url_bytes import (  # noqa: F401 - only_the_branch_question
    BAD_DIRECTORIES, BAD_IDS, HOLDER, NOT_UTF8, PROJECT, THE_RESOLVED_PATH,
    assert_nothing_was_made, child, directory_named, family_argv,
    family_refusal, only_the_branch_question, scaffold_argv, scaffold_refusal)
from test_family import (  # noqa: F401 - fixtures
    FAMILY, SPARE, allow_file_protocol, family, family_module)
from test_family_add_refusals import (  # noqa: F401 - fixtures
    assert_unchanged, holder, offline, snapshot)
from test_scaffold_free_text_values import (  # noqa: F401 - fixtures
    no_process, scaffold)

#: What `unwritable_reason` says of a lone surrogate.
LONE_SURROGATE = "it holds a lone surrogate, which is no character"

#: What `add`'s refusal tells a person to do: `init`'s way out, with `add`'s
#: verb and GitHub URL, but a directory that already holds the member's bare
#: repository, not one made anew (a new, empty one is refused again), and why
#: `.gitmodules` cannot hold the URL as text.
MEMBER_REMEDIATION = (
    "Remediation: `--dry-run` refuses the same. Pass a --local-remote-dir "
    "whose path is one line of UTF-8 text with no control character in it "
    "and that holds the member's bare repository `<Project>.git`, its "
    "directory renamed or the repository moved, and run again; or run `add` "
    "against GitHub, without --local-remote-dir, where the clone URL is "
    "`https://github.com/<org>/<Project>.git`. " + THE_RESOLVED_PATH
    + "The holder's `.gitmodules` records the clone URL as git is given it, "
    "and the holder's `make siblings` reads it back as UTF-8 text, a line a "
    "value: a byte that is not UTF-8 in the path (a directory named in a "
    "legacy code page), or a lone surrogate, reads back as another path, a "
    "line break ends the URL where it falls, a control character garbles "
    "the line it is shown in, and a bidirectional embedding, override or "
    "isolate control shows the rest of that line in another order than it "
    "is written.")

DRY_RUN = pytest.mark.parametrize("dry_run", [True, False],
                                  ids=["dry-run", "real"])


def member_refusal(url: str, reason: str) -> str:
    """The whole of what `family.py add` prints to stderr."""
    return (
        "REFUSED family-unwritable-value: under --local-remote-dir the "
        "member's clone URL is the bare repository's own path, "
        f"{url!r}, which `add` writes into the holder's `.gitmodules`, and "
        f"{reason}. No git command that writes was run and nothing was "
        f"written.\n{MEMBER_REMEDIATION}\n")


def holding_the_spare(family, directory: Path) -> Path:
    """`directory` with a copy of the spare member's bare repository in it,
    where `add --local-remote-dir` looks for `<Project>.git`."""
    shutil.copytree(family["remotes"] / f"{SPARE}.git",
                    directory / f"{SPARE}.git", symlinks=True)
    return directory


def linked_to(tmp_path: Path, target: Path) -> Path:
    """`tmp_path/link`, a name that is text, linked to `target`; skipped
    where this host makes no symbolic link."""
    link = tmp_path / "link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"this host makes no symbolic link: {error}")
    return link


def flags(dry_run: bool) -> list[str]:
    return ["--dry-run"] if dry_run else []


# --- `add`: the member's clone URL, asked before anything is read ----------

@DRY_RUN
@pytest.mark.parametrize("label, raw, reason", BAD_DIRECTORIES, ids=BAD_IDS)
def test_add_from_a_directory_no_file_can_name_is_refused(
        family, holder, offline, tmp_path, label, raw, reason, dry_run):
    """The issue's row, `add --local-remote-dir <dir>/caf<e9>`, and the
    other paths `unwritable_reason` refuses. On main each exited 0 and wrote
    the URL into `.gitmodules`. Now: exit 2, nothing on stdout (the member
    is not even read), the refusal in full, and the holder exactly as it
    was, with no throwaway clone left and no `gh` called."""
    remotes = holding_the_spare(family, directory_named(tmp_path, raw))
    before = snapshot(holder)
    result = offline.add(holder, SPARE, *flags(dry_run), remotes=remotes)
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert result.stderr == member_refusal(
        str(remotes.resolve() / f"{SPARE}.git"), reason)
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@DRY_RUN
def test_add_through_a_link_to_such_a_directory_says_the_target_is_the_fault(
        family, holder, offline, tmp_path, dry_run):
    """`add --local-remote-dir link`, `link` a UTF-8 name pointing at the
    `caf<e9>` directory: refused, naming the URL the link RESOLVES to, with
    the remedy saying that a link's target is then what to rename."""
    target = holding_the_spare(family, directory_named(tmp_path, b"caf\xe9"))
    link = linked_to(tmp_path, target)
    before = snapshot(holder)
    result = offline.add(holder, SPARE, *flags(dry_run), remotes=link)
    assert (result.returncode, result.stdout) == (2, ""), result.stderr
    assert result.stderr == member_refusal(
        str(target.resolve() / f"{SPARE}.git"), NOT_UTF8)
    assert THE_RESOLVED_PATH in result.stderr
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


@pytest.mark.parametrize("how", ["directory-renamed", "repository-moved"])
def test_add_follows_its_own_remedy_to_a_mount(family, holder, offline,
                                               tmp_path, how):
    """`add`'s remedy says to pass a path of text that HOLDS the member's bare
    repository, "its directory renamed or the repository moved". Both
    are measured: from the refused `caf<e9>` directory, either one makes
    `add` exit 0 with the member mounted, and the pin in `.gitmodules` is
    the new path. The words "made anew" are not there because a new, empty
    directory is refused again (`<Project>.git` does not exist in it), which
    lane 1's review of #812 measured."""
    bad = holding_the_spare(family, directory_named(tmp_path, b"caf\xe9"))
    refused = offline.add(holder, SPARE, remotes=bad)
    assert refused.returncode == 2, refused.stderr
    assert "family-unwritable-value" in refused.stderr
    if how == "directory-renamed":
        good = tmp_path / "renamed"
        os.rename(bad, good)
    else:
        good = tmp_path / "moved"
        good.mkdir()
        shutil.move(bad / f"{SPARE}.git", good / f"{SPARE}.git")
    result = offline.add(holder, SPARE, remotes=good)
    assert result.returncode == 0, result.stderr + result.stdout
    url = str(good.resolve() / f"{SPARE}.git")
    assert git("config", "-f", ".gitmodules", "--get",
               f"submodule.members/{SPARE}.url",
               cwd=holder).stdout == f"{url}\n"
    offline.assert_left_nothing()


def test_add_from_a_utf8_directory_still_mounts(family, holder, offline,
                                                tmp_path):
    """The control, `<dir>/café`: text, so `add` mounts and pins it, exit 0,
    and `.gitmodules` records the path as it stands."""
    remotes = holding_the_spare(family, tmp_path / "café")
    result = offline.add(holder, SPARE, remotes=remotes)
    assert result.returncode == 0, result.stderr + result.stdout
    url = str(remotes.resolve() / f"{SPARE}.git")
    assert git("config", "-f", ".gitmodules", "--get",
               f"submodule.members/{SPARE}.url",
               cwd=holder).stdout == f"{url}\n"
    offline.assert_left_nothing()


# --- the scaffold and `init`: a link's target is named as the fault --------

@DRY_RUN
def test_a_scaffold_through_a_link_says_the_target_is_the_fault(
        scaffold, no_process, capsys, tmp_path, dry_run):
    """`--local-remote-dir link` to a `caf<e9>` directory: refused as #640
    refused it, before any process, and the remedy now says the link's
    target is the fault."""
    target = directory_named(tmp_path, b"caf\xe9")
    link = linked_to(tmp_path, target)
    work = tmp_path / "work"
    code = scaffold.main(scaffold_argv(link, work, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == scaffold_refusal(str(target.resolve() / f"{PROJECT}.git"),
                                   NOT_UTF8)
    assert THE_RESOLVED_PATH in err
    assert_nothing_was_made(target, work)


@DRY_RUN
def test_a_family_through_a_link_says_the_target_is_the_fault(
        only_the_branch_question, capsys, tmp_path, dry_run):
    """The same for `family.py init`."""
    target = directory_named(tmp_path, b"caf\xe9")
    link = linked_to(tmp_path, target)
    into = tmp_path / "into"
    code = family_module().main(family_argv(link, into, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == family_refusal(str(target.resolve() / f"{HOLDER}.git"),
                                 NOT_UTF8)
    assert THE_RESOLVED_PATH in err
    assert_nothing_was_made(target, into)


# --- a lone surrogate, which only a Windows name holds ---------------------

#: A clone URL holding U+D800, outside the U+DC80-U+DCFF range a byte that is
#: not UTF-8 decodes to, so the reason given is the surrogate's own.
SURROGATE_URL = "/remotes/\ud800/Atlas.git"


def refused_text(module, function: str) -> str:
    """What `module`'s refusal `function` raises for `SURROGATE_URL` under
    `--local-remote-dir`, as the tool prints it to stderr."""
    refuse = getattr(module, function)
    with pytest.raises(module.Refusal) as caught:
        refuse(True, SURROGATE_URL)
    return f"{caught.value}\n"


def test_the_scaffold_explains_a_lone_surrogate(scaffold):
    text = refused_text(scaffold, "_refuse_an_unwritable_clone_url")
    assert text == scaffold_refusal(SURROGATE_URL, LONE_SURROGATE)
    assert "or a lone surrogate, cannot be written at all" in text


def test_init_explains_a_lone_surrogate():
    text = refused_text(family_module(), "_refuse_an_unwritable_clone_url")
    assert text == family_refusal(SURROGATE_URL, LONE_SURROGATE)
    assert "or a lone surrogate, cannot be written at all" in text


def test_add_explains_a_lone_surrogate():
    text = refused_text(family_module(), "_refuse_an_unwritable_member_url")
    assert text == member_refusal(SURROGATE_URL, LONE_SURROGATE)
    assert "or a lone surrogate, reads back as another path" in text


def test_add_asks_only_a_local_url():
    """Against GitHub the member's URL is ASCII by construction."""
    assert family_module()._refuse_an_unwritable_member_url(
        False, f"https://github.com/InkRouter/{SPARE}.git") is None


# --- the READMEs' clone line pastes as one command --------------------------

#: `(id, the folder the remotes go under, whether a POSIX shell needs the URL
#: quoted)`: the issue's two rows, and an ordinary name left bare. On Windows
#: the path is spelled with `\`, which `sh` reads as an escape, so the
#: ordinary row is quoted there too.
FOLDERS = [("space", "a b", True), ("apostrophe", "it's", True),
           ("ordinary", "plain", os.name == "nt")]
FOLDER_IDS = [row[0] for row in FOLDERS]


def clone_line(url: str, quoted: bool) -> str:
    """The clone line a POSIX shell reads as three words and the URL: the URL
    in single quotes, each `'` in it closed, escaped and reopened, or bare."""
    word = "'" + url.replace("'", "'\\''") + "'" if quoted else url
    return f"git clone --recurse-submodules {word}"


def clone_lines(readme: Path) -> list[str]:
    """Every `git clone --recurse-submodules` line `readme` holds, read as
    the bytes the tool wrote."""
    text = readme.read_bytes().decode("utf-8")
    return [line for line in text.splitlines()
            if line.startswith("git clone --recurse-submodules ")]


def assert_one_command(lines: list[str], url: str, quoted: bool) -> None:
    """Each line is the clone line, and `shlex` reads it as `sh` does: the
    three words and the URL whole."""
    assert lines, lines
    assert set(lines) == {clone_line(url, quoted)}, lines
    assert shlex.split(lines[0]) == ["git", "clone", "--recurse-submodules",
                                     url]


@pytest.mark.parametrize("label, folder, quoted", FOLDERS, ids=FOLDER_IDS)
def test_the_scaffolds_readmes_print_a_clone_line_that_pastes_whole(
        tmp_path, label, folder, quoted):
    """End to end into local bare remotes under `<dir>/<folder>/`: the
    assembly root's README (twice, getting started and parking) and each
    leg's print the clone URL as one word. On main the `a b` row printed
    `.../a b/remotes/Atlas.git` bare, which `sh` reads as two arguments."""
    remotes = tmp_path / folder / "remotes"
    work = tmp_path / "work"
    code, out, err = child(SCAFFOLD, *scaffold_argv(remotes, work,
                                                    dry_run=False))
    assert code == 0, err + out
    url = str(remotes.resolve() / f"{PROJECT}.git")
    root_lines = clone_lines(work / PROJECT / "README.md")
    assert len(root_lines) == 2, root_lines
    assert_one_command(root_lines, url, quoted)
    for leg in ("spec", "code"):
        assert_one_command(clone_lines(work / f"{PROJECT}-{leg}" / "README.md"),
                           url, quoted)


@pytest.mark.skipif(shutil.which("sh") is None, reason="no `sh` to paste into")
@pytest.mark.parametrize("label, folder, quoted", FOLDERS, ids=FOLDER_IDS)
def test_the_holders_readme_prints_a_clone_line_that_pastes_whole(
        tmp_path, label, folder, quoted):
    """End to end for `family.py init`, and the line then PASTED into `sh`
    as a person pastes it: it clones the holder. On main the `a b` row
    asked git to clone `.../a`, which is no repository."""
    remotes = tmp_path / folder / "remotes"
    into = tmp_path / "into"
    code, out, err = child(FAMILY, *family_argv(remotes, into, dry_run=False))
    assert code == 0, err + out
    url = str(remotes.resolve() / f"{HOLDER}.git")
    lines = clone_lines(into / HOLDER / HOLDER / "README.md")
    assert len(lines) == 1, lines
    assert_one_command(lines, url, quoted)
    paste = tmp_path / "paste"
    paste.mkdir()
    done = pasted(lines, paste, allow_file_protocol())
    assert done.returncode == 0, done.stderr
    assert (paste / HOLDER / "family.yaml").is_file()
