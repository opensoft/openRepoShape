# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/validate-family.py`: a path this user
cannot read is refused by name, and never read as absent (#430, slice E of
lane 1's plan, issuecomment-6251069236).

`Path.is_file()`, `is_dir()` and `exists()` raised a refused `stat` up to
Python 3.13 and answer False to ANY `OSError` from 3.14, and
`os.path.lexists` always did. So each guard here ended the run in a
`PermissionError` traceback on 3.12, exit 1, or said a false thing on 3.14:
a member checkout under a folder this user cannot search was
`member-uninitialized`, whose `git submodule update` then failed `could not
open '<path>/.git' for writing`; a member's `project.yaml` behind one was
`member-not-a-project`; the shape pin `shape-pin-missing`, a shape copy
`shape-copy-missing` and `family.yaml` `family-manifest-missing`; a staged
removal's lines ended on that same failing update; a case variant's `git rm
--cached` lost the `-f` git needs there, or called a checkout none; and the
checkout `git mv` moved went unnamed again (#879's C4).

EACH SITE HAS THREE ROWS:
- ABSENT, the control: nothing there is said as it always was.
- A REFUSED `stat`, in-process (`refused_stat`, from
  `tests/test_bump_leg_unopenable.py`), which answers as 3.14 does on every
  Python and platform, and as root: the refusal names the path, exit 2.
- MODE 000 or 444 on the folder above it, in a subprocess, skipped on
  Windows and as root (`needs_a_mode`): the same refusal, and once the mode
  is back the gate answers as it did before, so the cure is the whole of it.

The sites are the member checkout's `.git` (`_check_members`' stop,
`_check_member_checkout`, `_check_member_tree`), `_check_member_identity`'s
`project.yaml`, `_load_shape_pin`, `_check_one_shape_file`, `_run_checks`'
`family.yaml`, the staged removal's `_put_back_lines` and `_moved_checkouts`
(`_gone`: nothing there is ENOENT alone, so a file where the checkout should
be is refused, never "none there"), `_names_store`, `_on_disk` and
`_held_as`, which decide the `-f` of a gitlink's `git rm --cached`,
`_staged_over` (#889's round 2), which decides whether a hand mount's `git
rm` is said to refuse a staged gitlink, and `_hand_cached` and
`_cached_left` (#936), which decide whether it is `git rm --cached`.

WHAT IS ON DISK IS ASKED ONLY WHERE IT IS SAID (round 2, r956's SHOULD 1
on #956): `_forced` and `_staged_over` ask git first, and where HEAD
records a gitlink at the index's own commit, the disk under it is never
asked, so a folder this user cannot search there changes nothing. A hand
mount's is said (#936): whether its plain `git rm` works turns on what is
there, a clone no section names or what is no checkout, and under a folder
this user cannot search that `git rm` exits 128, so a hand mount HEAD
records is refused by name there too (`_hand_cached`). And ONE
CODE HAS ONE TEXT (r956's SHOULD 2): a member's `project.yaml` that cannot
be opened says what one whose `stat` is refused says.

A refused `stat` of `.git` refuses the holder's own `.git` too, which the
pinned `repo_shape.find_repo_root` asks; #430's plan leaves that function
out, so the gate run in-process is given the holder as its root (`gate`).
"""

from __future__ import annotations

import contextlib
import errno
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import git, load_without_bytecode
from test_bump_leg_unopenable import (
    made_unopenable, needs_a_mode, refusal_of, refused_stat,
)
from test_family import SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder  # noqa: F401
from test_family_head_lost_gitmodules import case_sensitive_disk  # noqa: F401
from test_validate_family_typed_states import OTHER, ROW, VARIANT_PATH
from test_validate_family_unnamed_mounts import (
    codes, commands, findings, spare_commits, stage_gitlink,
)

OTHER_ROW = f"members/{OTHER}"
HAND = f"members/{SPARE}"
MEMBER_UNREADABLE = "member-unreadable"

#: What the remedy of a refusal for want of permission says, and what one
#: for any other reason says in its place, never told to `chmod`.
CURE = "chmod u+rx"
OTHER_REASON_SAID = "Where the operating system gave another reason"

#: The line a staged removal prints to put its gitlink back, and the update
#: that checks the member out where none is there (`_put_back_lines`).
RESET = f"git reset -q -- {ROW}"
UPDATE = f"git submodule update --init --recursive -- {ROW}"


def gate(holder: Path, monkeypatch):
    """The holder's own `scripts/validate-family.py`, the template's bytes
    (`family.py init` copies it verbatim), loaded in-process with
    `find_repo_root` answering the holder; `sys.path`, which the module
    extends, is put back afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    module = load_without_bytecode(holder / "scripts" / "validate-family.py",
                                   "validate_family_unreadable")
    monkeypatch.setattr(module, "find_repo_root", lambda start: holder)
    return module


def assert_refused(code: int, err: str, refusal: str, named: str,
                   reason: str = "Permission denied") -> None:
    """Exit 2, `refusal`'s line naming `named` and the system's reason
    first, no traceback, and the cure for that cause: `chmod` for a
    permission, `OTHER_REASON_SAID` for anything else."""
    assert code == 2, err
    assert err.splitlines()[0] == (
        f"REFUSED {refusal}: {named}: cannot be read ({reason})"), err
    assert "Traceback" not in err
    permission = reason == "Permission denied"
    assert (CURE in err) is permission, err
    assert (OTHER_REASON_SAID in err) is not permission, err


# --- the states each row starts from -----------------------------------------

def as_made(holder: Path, request) -> tuple[str, ...]:
    """The holder as `family.py` made it."""
    return ()


def pins_alone(holder: Path, request) -> tuple[str, ...]:
    """The holder as made, asked `--pins`, what `make pins` runs."""
    return ("--pins",)


def not_checked_out(holder: Path, request) -> tuple[str, ...]:
    """IRRS's checkout moved out of the holder whole, and the empty
    directory a plain clone leaves in its place."""
    shutil.move(str(holder / ROW), str(request.getfixturevalue("tmp_path")
                                       / "aside"))
    (holder / ROW).mkdir()
    return ()


def sections_out(*paths: str):
    """A state: each of `paths`' section taken out of `.gitmodules` and
    committed, `member-gitmodules-absent` for each, so `_check_members`'
    stop asks nothing of its checkout and `_check_member_checkout` does."""
    def made(holder: Path, request) -> tuple[str, ...]:
        for path in paths:
            git("config", "-f", ".gitmodules", "--remove-section",
                f"submodule.{path}", cwd=holder)
        git("add", "--", ".gitmodules", cwd=holder)
        git("commit", "-qm", "Sections taken out", cwd=holder)
        return ()
    return made


def unregistered_not_checked_out(holder: Path, request) -> tuple[str, ...]:
    sections_out(ROW)(holder, request)
    return not_checked_out(holder, request)


def removal_staged(holder: Path, request) -> tuple[str, ...]:
    """IRRS's gitlink taken out of the index alone, its checkout kept:
    `member-gitlink-removal-staged`, under `--no-members`."""
    git("rm", "-q", "--cached", "--", ROW, cwd=holder)
    return ("--no-members",)


def removal_staged_not_checked_out(holder: Path, request) -> tuple[str, ...]:
    extra = removal_staged(holder, request)
    not_checked_out(holder, request)
    return extra


def moved_to_the_variant(holder: Path, request) -> tuple[str, ...]:
    """`git mv members/IRRS Members/IRRS`, staged: a stray whose `git rm
    --cached` takes `-f` over a checkout (`_on_disk`, `_held_as`), on a disk
    that holds the two names apart."""
    request.getfixturevalue("case_sensitive_disk")
    (holder / "Members").mkdir()
    git("mv", "--", ROW, VARIANT_PATH, cwd=holder)
    return ("--no-members",)


def hand_mount_staged(holder: Path, request) -> tuple[str, ...]:
    """SPARE's gitlink staged by hand at `members/IRQS`, which no row
    names, over an empty directory, as #889's round 2 measures it: a plain
    `git rm` refuses it as staged, which `_staged_over` asks."""
    stage_gitlink(holder, HAND,
                  spare_commits(request.getfixturevalue("family"))[1])
    (holder / HAND).mkdir()
    return ("--no-members",)


def hand_mount_committed(holder: Path, request) -> tuple[str, ...]:
    """The hand mount committed: HEAD records SPARE's gitlink at the
    index's own commit, so no `-f` is said and no staged clause, whatever
    is on disk (r956's C19 on #956). Whether a plain `git rm` takes it
    turns on what is on disk (#936): over this empty directory it does."""
    extra = hand_mount_staged(holder, request)
    git("commit", "-qm", "A hand mount", cwd=holder)
    return extra


def variant_committed(holder: Path, request) -> tuple[str, ...]:
    """A second path to IRRS, `Members/IRRS`, committed at IRRS's commit
    over a directory holding a file: its `git rm --cached` takes no `-f`,
    so what is on disk there is never said (r956's C20 on #956)."""
    request.getfixturevalue("case_sensitive_disk")
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    git("update-index", "--add", "--cacheinfo",
        f"160000,{commit},{VARIANT_PATH}", cwd=holder)
    git("commit", "-qm", "A second path to IRRS", cwd=holder)
    (holder / VARIANT_PATH).mkdir(parents=True)
    (holder / VARIANT_PATH / "kept.txt").write_text("kept\n",
                                                    encoding="utf-8")
    return ("--no-members",)


def policy_elsewhere(holder: Path, request) -> tuple[str, ...]:
    """The naming policy read from a copy outside the holder, so a
    `contracts/` this user cannot search reaches the shape pin."""
    policy = request.getfixturevalue("tmp_path") / "policy.yaml"
    shutil.copyfile(holder / "contracts" / "repository-naming.yaml", policy)
    return ("--policy", str(policy))


# --- absent: the control ---------------------------------------------------

def unlinked(name: str):
    def made(holder: Path, request) -> tuple[str, ...]:
        (holder / name).unlink()
        return ()
    return made


@pytest.mark.parametrize("made,exit_code,first", [
    pytest.param(not_checked_out, 2,
                 f"REFUSED member-uninitialized: {ROW} is not an initialized "
                 "submodule checkout, so neither", id="member-checkout"),
    pytest.param(unregistered_not_checked_out, 1,
                 f"FINDING member-gitmodules-absent: {ROW} is a gitlink",
                 id="unregistered-member-checkout"),
    pytest.param(unlinked(f"{ROW}/project.yaml"), 1,
                 f"FINDING member-not-a-project: {ROW}: no project.yaml",
                 id="member-project-yaml"),
    pytest.param(unlinked("contracts/shape-pin.yaml"), 2,
                 "REFUSED shape-pin-missing: ", id="shape-pin"),
    pytest.param(unlinked(".github/workflows/validate.yml"), 1,
                 "FINDING shape-copy-missing: contracts/shape-pin.yaml: "
                 ".github/workflows/validate.yml is pinned but absent",
                 id="shape-copy"),
    pytest.param(unlinked("family.yaml"), 2,
                 "REFUSED family-manifest-missing: ", id="family-yaml"),
    pytest.param(hand_mount_staged, 1,
                 f"FINDING member-gitlink-unnamed: {HAND} is a gitlink",
                 id="hand-mount-staged"),
])
def test_what_is_not_there_is_said_as_it_always_was(holder, request, made,
                                                    exit_code, first):
    """THE CONTROLS: nothing at the name (ENOENT) is the absence it always
    was, word for word, and never `cannot be read`."""
    result = validate(holder, *made(holder, request))
    assert result.returncode == exit_code, result.stderr + result.stdout
    assert result.stderr.startswith(first), result.stderr
    assert "cannot be read" not in result.stderr


# --- a refused `stat`, as Python 3.14 answers it (everywhere, root too) -----

@pytest.mark.parametrize("made,names,refusal,named", [
    pytest.param(as_made, (".git",), MEMBER_UNREADABLE, f"{ROW}/.git",
                 id="member-checkout"),
    pytest.param(pins_alone, (".git",), MEMBER_UNREADABLE, f"{ROW}/.git",
                 id="member-checkout-pins"),
    pytest.param(sections_out(ROW, OTHER_ROW), (".git",), MEMBER_UNREADABLE,
                 f"{ROW}/.git", id="unregistered-member-checkout"),
    pytest.param(as_made, ("shape-pin.yaml",), "shape-pin-unreadable",
                 "contracts/shape-pin.yaml", id="shape-pin"),
    pytest.param(as_made, ("validate.yml",), "shape-copy-unreadable",
                 ".github/workflows/validate.yml", id="shape-copy"),
    pytest.param(as_made, ("family.yaml",), "family-manifest-unreadable",
                 "family.yaml", id="family-yaml"),
    pytest.param(removal_staged, (".git",), MEMBER_UNREADABLE, f"{ROW}/.git",
                 id="staged-removal-checkout"),
    pytest.param(moved_to_the_variant, ("IRRS",), MEMBER_UNREADABLE,
                 VARIANT_PATH, id="variant-on-disk"),
    pytest.param(moved_to_the_variant, (".git",), MEMBER_UNREADABLE,
                 f"{VARIANT_PATH}/.git", id="variant-checkout"),
    pytest.param(hand_mount_staged, (SPARE,), MEMBER_UNREADABLE, HAND,
                 id="hand-mount-staged"),
    pytest.param(hand_mount_committed, (SPARE,), MEMBER_UNREADABLE, HAND,
                 id="hand-mount-committed"),
])
def test_a_path_whose_stat_is_refused_is_refused_by_name(
        holder, request, monkeypatch, capsys, made, names, refusal, named):
    """On every Python: the path the gate asks first is refused by name,
    `<path>: cannot be read (Permission denied)`, with the `chmod` cure,
    where 3.14 read it as not there: `member-uninitialized` for a member's
    checkout, in members mode and `--pins` alike."""
    extra = made(holder, request)
    module = gate(holder, monkeypatch)
    refused_stat(monkeypatch, *names)
    code = module.main(["--root", str(holder), *extra])
    err = capsys.readouterr().err
    assert_refused(code, err, refusal, named)
    assert "member-uninitialized" not in err


def test_a_project_yaml_whose_stat_is_refused_is_named_not_a_leg(
        holder, monkeypatch, capsys):
    """`member-manifest-unreadable`, the finding a `project.yaml` that
    cannot be opened already is, naming the file and the cure, exit 1:
    3.14 called the member `member-not-a-project`, "a family pins assembly
    roots, never legs", of an assembly root."""
    module = gate(holder, monkeypatch)
    refused_stat(monkeypatch, "project.yaml")
    code = module.main(["--root", str(holder)])
    result = SimpleNamespace(stderr=capsys.readouterr().err)
    assert code == 1, result.stderr
    assert codes(result) == ["member-manifest-unreadable"] * 2
    assert findings(result)[0].startswith(
        f"FINDING member-manifest-unreadable: {ROW}/project.yaml: cannot be "
        "read (Permission denied). Make what this user may not open "
        "readable by this user: `chmod u+r` on a file"), result.stderr


@pytest.mark.parametrize("kind,number,reason,cure", [
    pytest.param(PermissionError, errno.EACCES, "Permission denied",
                 "Make what this user may not open readable by this user: "
                 "`chmod u+r` on a file", id="permission"),
    pytest.param(OSError, errno.EIO, "Input/output error", OTHER_REASON_SAID,
                 id="io-error"),
])
def test_a_project_yaml_that_cannot_be_opened_says_what_its_stat_says(
        holder, monkeypatch, capsys, kind, number, reason, cure):
    """ONE CODE, ONE TEXT (r956's SHOULD 2 on #956): a `project.yaml` whose
    open fails is `<path>: cannot be read (<reason>)` with the cure for
    that cause, as one whose `stat` is refused. It named the file twice,
    relative and then absolute, as `load_yaml`'s `yaml-unreadable` line
    has it, and gave no cure."""
    module = gate(holder, monkeypatch)
    real = Path.read_text

    def failing(self, *args, **kwargs):
        if self.name == "project.yaml":
            raise kind(number, reason, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing)
    code = module.main(["--root", str(holder)])
    result = SimpleNamespace(stderr=capsys.readouterr().err)
    assert code == 1, result.stderr
    assert findings(result)[0].startswith(
        f"FINDING member-manifest-unreadable: {ROW}/project.yaml: cannot be "
        f"read ({reason}). {cure}"), result.stderr
    assert str(holder) not in result.stderr


def test_a_row_that_gives_no_path_is_named_at_its_own(
        holder, monkeypatch, capsys):
    """A ROW THAT GIVES NO `path:` is read at `members/<P>`, as
    `_check_member_repository_and_path` resolves it, and named there: its
    `project.yaml` was `None/project.yaml` (r956's NIT 1 on #956)."""
    manifest = holder / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    line = re.compile(rf"^ *path: {re.escape(ROW)}\n", re.MULTILINE)
    assert len(line.findall(text)) == 1, text
    manifest.write_text(line.sub("", text), encoding="utf-8")
    module = gate(holder, monkeypatch)
    refused_stat(monkeypatch, "project.yaml")
    code = module.main(["--root", str(holder)])
    result = SimpleNamespace(stderr=capsys.readouterr().err)
    assert code == 1, result.stderr
    assert findings(result)[0].startswith(
        f"FINDING member-manifest-unreadable: {ROW}/project.yaml: cannot be "
        "read (Permission denied)"), result.stderr


def test_a_shape_copy_that_fails_for_another_reason_is_refused_sans_chmod(
        holder, monkeypatch, capsys):
    """A copy whose read fails with an I/O error: the same refusal, the
    system's reason, and no `chmod`. It ended in `file_sha256`'s
    traceback on every Python."""
    module = gate(holder, monkeypatch)
    real = module.file_sha256

    def failing(path):
        if path.name == "validate.yml":
            raise OSError(errno.EIO, "Input/output error", str(path))
        return real(path)

    monkeypatch.setattr(module, "file_sha256", failing)
    code = module.main(["--root", str(holder)])
    assert_refused(code, capsys.readouterr().err, "shape-copy-unreadable",
                   ".github/workflows/validate.yml", "Input/output error")


def test_the_member_tree_asked_alone_names_the_checkout(holder, monkeypatch):
    """`_check_member_tree`, which `main` reaches only after the stop has
    asked the same `.git`: asked alone, the same refusal."""
    module = gate(holder, monkeypatch)
    refused_stat(monkeypatch, ".git")
    refusal = refusal_of(module, module._check_member_tree, holder / ROW, {},
                         ROW, "0" * 40, "IRRS", module.Report(), "")
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == f"{ROW}/.git: cannot be read (Permission denied)"


@pytest.mark.parametrize("asked,there", [
    ("_put_back_lines", [([RESET], "its gitlink")]),
    ("_moved_checkouts", ([], [])),
])
def test_the_staged_removal_asks_the_row_s_own_checkout_alone(
        holder, request, monkeypatch, asked, there):
    """`_put_back_lines` and `_moved_checkouts`, each asked alone, since in
    `main` the second meets a `.git` the first has asked: a checkout there
    prints no update and names nothing (the control), and one whose `stat`
    is refused is refused, not "none there", which printed the update and
    searched the other gitlinks for where it went."""
    removal_staged(holder, request)
    module = gate(holder, monkeypatch)
    args = {"_put_back_lines": (holder, ROW, []),
            "_moved_checkouts": (holder, ROW,
                                 module._member_gitlinks(holder), {})}[asked]
    assert getattr(module, asked)(*args) == there
    refused_stat(monkeypatch, ".git")
    refusal = refusal_of(module, getattr(module, asked), *args)
    assert refusal.code == MEMBER_UNREADABLE
    assert refusal.detail == f"{ROW}/.git: cannot be read (Permission denied)"


def test_a_git_file_that_cannot_be_read_names_no_store_by_name(
        holder, monkeypatch):
    """`_names_store`: another gitlink's `.git` FILE names its own store
    (the control), and one whose `stat` is refused, or whose read fails for
    another reason, is refused naming it. It answered "names no store", and
    the checkout `git mv` moved there went unnamed (#879's C4)."""
    module = gate(holder, monkeypatch)
    store = module._store(holder, OTHER_ROW, {})
    assert module._names_store(holder, OTHER_ROW, store)
    real = Path.read_bytes

    def failing(self):
        if self.name == ".git":
            raise OSError(errno.EIO, "Input/output error", str(self))
        return real(self)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", failing)
        refusal = refusal_of(module, module._names_store, holder, OTHER_ROW,
                             store)
    assert refusal.detail == (f"{OTHER_ROW}/.git: cannot be read "
                              "(Input/output error)")
    assert "chmod" not in refusal.remediation
    refused_stat(monkeypatch, ".git")
    refusal = refusal_of(module, module._names_store, holder, OTHER_ROW,
                         store)
    assert refusal.code == MEMBER_UNREADABLE
    assert CURE in refusal.remediation


# --- the staged removal's lines: `_gone`, ENOENT alone ----------------------

@pytest.mark.parametrize("made,lines", [
    pytest.param(removal_staged, [RESET], id="checkout-there"),
    pytest.param(removal_staged_not_checked_out, [RESET, UPDATE],
                 id="nothing-there"),
])
def test_the_staged_removal_updates_only_where_nothing_is(holder, request,
                                                          made, lines):
    """THE CONTROLS of `_put_back_lines`: the update that checks the member
    out is printed where nothing is at its path, and not over a checkout."""
    result = validate(holder, *made(holder, request))
    assert codes(result) == ["member-gitlink-removal-staged"]
    assert commands(findings(result)[0]) == lines


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows answers a name under a file "
                           "ERROR_PATH_NOT_FOUND, which is ENOENT there")
def test_a_file_where_the_checkout_should_be_is_no_place_to_update(
        holder, request):
    """`_gone` IS ENOENT ALONE: a FILE at `members/IRRS`, the checkout moved
    away, makes its `.git` ENOTDIR, which `exists()` read as nothing there,
    so the lines ended on an update git cannot check out over a file. It is
    refused naming the `.git`, with the system's reason and no `chmod`."""
    removal_staged_not_checked_out(holder, request)
    (holder / ROW).rmdir()
    (holder / ROW).write_text("in the way\n", encoding="utf-8")
    result = validate(holder, "--no-members")
    assert_refused(result.returncode, result.stderr, MEMBER_UNREADABLE,
                   f"{ROW}/.git", "Not a directory")


def test_a_stray_whose_rm_takes_no_f_asks_nothing_of_its_git(
        holder, request, monkeypatch, capsys):
    """WHAT IS ON DISK IS ASKED ONLY WHERE IT IS SAID (`_held_if_forced`):
    a second path to IRRS, committed at IRRS's commit over a directory, is
    taken out with no `-f`, so the sentence that names what `-f` goes over
    is not printed, and a `.git` whose `stat` would be refused is never
    asked: the finding, not a refusal."""
    extra = variant_committed(holder, request)
    module = gate(holder, monkeypatch)
    refused_stat(monkeypatch, ".git")
    code = module.main(["--root", str(holder), *extra])
    result = SimpleNamespace(stderr=capsys.readouterr().err)
    assert code == 1, result.stderr
    assert codes(result) == ["member-gitlink-unnamed"]
    assert commands(findings(result)[0]) == [
        f"git rm --cached -- {VARIANT_PATH}"]


def said(module, holder: Path, capsys, extra: tuple[str, ...]) -> tuple:
    """`(exit code, stderr)` of the gate run in-process over `holder`."""
    code = module.main(["--root", str(holder), *extra])
    return code, capsys.readouterr().err


@pytest.mark.parametrize("made,names", [
    pytest.param(variant_committed, ("IRRS",), id="variant-committed"),
])
def test_a_gitlink_head_records_as_staged_asks_nothing_of_the_disk(
        holder, request, monkeypatch, capsys, made, names):
    """GIT FIRST (r956's SHOULD 1 on #956): where HEAD records a gitlink at
    the index's own commit, a plain `git rm --cached` takes it, so neither
    the `-f` (`_forced`) nor the staged clause (`_staged_over`) is said,
    whatever is on disk, and a path whose `stat` would be refused is never
    asked. The finding is the control's, word for word, on every Python:
    asked first, the disk refused it `member-unreadable`, exit 2. A hand
    mount HEAD records is no row here: whether its plain `git rm` works
    turns on what is on disk (#936), so it is refused by name
    (`test_a_path_whose_stat_is_refused_is_refused_by_name`)."""
    extra = made(holder, request)
    module = gate(holder, monkeypatch)
    control = said(module, holder, capsys, extra)
    assert control[0] == 1, control[1]
    refused_stat(monkeypatch, *names)
    assert said(module, holder, capsys, extra) == control


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a symbolic link needs a privilege on Windows")
def test_a_link_at_a_gitlink_path_is_on_disk_wherever_it_leads(
        tmp_path, holder, monkeypatch):
    """`_anything_at` asks a link's own `lstat` first, as `os.path.lexists`
    asked it: a link that leads nowhere is something on disk, and so is one
    whose target this user cannot reach, which its `stat` would refuse
    (r956's NIT 2 on #956). A name whose own `stat` is refused is refused
    by name."""
    module = gate(holder, monkeypatch)
    nowhere = tmp_path / "nowhere"
    nowhere.symlink_to(tmp_path / "missing")
    beyond = tmp_path / "beyond"
    beyond.symlink_to(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    refused_stat(monkeypatch, "beyond", "plain")
    assert module._anything_at(nowhere, "nowhere")
    assert module._anything_at(beyond, "beyond")
    refusal = refusal_of(module, module._anything_at, plain, "plain")
    assert refusal.detail == "plain: cannot be read (Permission denied)"


def test_a_name_that_needs_spelling_is_spelled_where_it_cannot_be_read(
        holder, monkeypatch):
    """`_cannot_read` prints the name `spelled`, as `validate-pins.py`'s
    line does (#610): a control character in a path is never printed raw
    (r956's NIT 2 on #956)."""
    module = gate(holder, monkeypatch)
    named = f"members/A{chr(27)}[31mB/.git"
    line = module._cannot_read(named, PermissionError(errno.EACCES,
                                                      "Permission denied"))
    assert line == (f"{module.spelled(named)}: cannot be read "
                    "(Permission denied)")
    assert chr(27) not in line


# --- mode 000 and 444 (POSIX, not as root) ----------------------------------

@needs_a_mode
@pytest.mark.parametrize("made,folder,mode,refusal,named,after", [
    pytest.param(as_made, ROW, 0, MEMBER_UNREADABLE, f"{ROW}/.git", [],
                 id="member-000"),
    pytest.param(as_made, ROW, 0o444, MEMBER_UNREADABLE, f"{ROW}/.git", [],
                 id="member-444"),
    pytest.param(as_made, "members", 0, MEMBER_UNREADABLE, f"{ROW}/.git", [],
                 id="members-000"),
    pytest.param(sections_out(ROW), ROW, 0, MEMBER_UNREADABLE, f"{ROW}/.git",
                 ["member-gitmodules-absent"], id="unregistered-member-000"),
    pytest.param(policy_elsewhere, "contracts", 0, "shape-pin-unreadable",
                 "contracts/shape-pin.yaml", [], id="contracts-000"),
    pytest.param(as_made, ".github/workflows", 0, "shape-copy-unreadable",
                 ".github/workflows/validate.yml", [], id="workflows-000"),
    pytest.param(as_made, ".github/workflows", 0o444,
                 "shape-copy-unreadable", ".github/workflows/validate.yml",
                 [], id="workflows-444"),
    pytest.param(as_made, ".github/workflows/validate.yml", 0,
                 "shape-copy-unreadable", ".github/workflows/validate.yml",
                 [], id="shape-copy-000"),
    pytest.param(removal_staged, ROW, 0, MEMBER_UNREADABLE, f"{ROW}/.git",
                 ["member-gitlink-removal-staged"],
                 id="staged-removal-000"),
    pytest.param(removal_staged_not_checked_out, OTHER_ROW, 0,
                 MEMBER_UNREADABLE, f"{OTHER_ROW}/.git",
                 ["member-gitlink-removal-staged"],
                 id="other-checkout-000"),
    pytest.param(moved_to_the_variant, "Members", 0, MEMBER_UNREADABLE,
                 VARIANT_PATH,
                 ["member-gitlink-unnamed", "gitmodules-path-unnamed",
                  "member-gitlink-removal-staged"], id="variant-folder-000"),
    pytest.param(moved_to_the_variant, VARIANT_PATH, 0, MEMBER_UNREADABLE,
                 f"{VARIANT_PATH}/.git",
                 ["member-gitlink-unnamed", "gitmodules-path-unnamed",
                  "member-gitlink-removal-staged"], id="variant-000"),
    pytest.param(hand_mount_staged, "members", 0, MEMBER_UNREADABLE, HAND,
                 ["member-gitlink-unnamed"], id="hand-mount-folder-000"),
    pytest.param(hand_mount_committed, "members", 0, MEMBER_UNREADABLE, HAND,
                 ["member-gitlink-unnamed"],
                 id="hand-mount-committed-folder-000"),
    pytest.param(hand_mount_committed, HAND, 0o444, MEMBER_UNREADABLE,
                 f"{HAND}/.git", ["member-gitlink-unnamed"],
                 id="hand-mount-committed-444"),
])
def test_a_folder_this_user_cannot_search_is_refused_by_name(
        holder, request, made, folder, mode, refusal, named, after):
    """THE ISSUE'S CELLS, on this Python: a traceback up to 3.13, and on
    3.14 a false "not there". Now the refusal of the path asked first, exit
    2, and with the mode back the gate answers as it did before the mode
    was changed (`after`, the codes of its findings), so the cure it names
    is the whole of it."""
    extra = made(holder, request)
    with made_unopenable(holder, folder, mode=mode):
        result = validate(holder, *extra)
    assert_refused(result.returncode, result.stderr, refusal, named)
    again = validate(holder, *extra)
    assert codes(again) == after
    assert again.returncode == (1 if after else 0), again.stderr


@needs_a_mode
@pytest.mark.parametrize("made,folder", [
    pytest.param(variant_committed, "Members", id="variant-committed"),
])
def test_a_folder_under_a_gitlink_git_takes_is_never_asked(
        holder, request, made, folder):
    """r956's C20 on #956, on this Python: with the folder at mode 000, the
    gate says what it says with the folder open, word for word, since
    nothing it says turns on what is in that folder. C19's hand mount is no
    row here: what its line says turns on that folder (#936), and a plain
    `git rm` of it under a folder at mode 000 exits 128 (`failed to stat`,
    `could not remove`), so it is refused by name
    (`hand-mount-committed-folder-000` above)."""
    extra = made(holder, request)
    control = validate(holder, *extra)
    with made_unopenable(holder, folder):
        result = validate(holder, *extra)
    assert (result.returncode, result.stderr) == (control.returncode,
                                                  control.stderr)


@needs_a_mode
def test_a_project_yaml_at_mode_000_is_named_once_with_its_cure(holder):
    """The file itself at mode 000, the common case of r956's SHOULD 2 on
    #956: one name, the reason and the cure, where it was named twice."""
    manifest = holder / ROW / "project.yaml"
    manifest.chmod(0)
    try:
        result = validate(holder)
    finally:
        manifest.chmod(0o644)
    assert findings(result)[0].startswith(
        f"FINDING member-manifest-unreadable: {ROW}/project.yaml: cannot be "
        "read (Permission denied). Make what this user may not open "
        "readable"), result.stderr
    assert validate(holder).returncode == 0


@contextlib.contextmanager
def behind_a_locked_folder(path: Path, tmp_path: Path):
    """`path` replaced by a symbolic link to a copy of it in a folder of
    mode 000, which this user cannot search, given its mode back in
    `finally`: the one way a name whose own folder is searchable has a
    `stat` that is refused."""
    locked = tmp_path / "locked"
    locked.mkdir()
    shutil.copyfile(path, locked / path.name)
    path.unlink()
    path.symlink_to(locked / path.name)
    locked.chmod(0)
    try:
        yield
    finally:
        locked.chmod(0o755)


@needs_a_mode
@pytest.mark.parametrize("name,first", [
    (f"{ROW}/project.yaml",
     f"FINDING member-manifest-unreadable: {ROW}/project.yaml: cannot be "
     "read (Permission denied). Make what this user may not open readable"),
    ("family.yaml",
     "REFUSED family-manifest-unreadable: family.yaml: cannot be read "
     "(Permission denied)"),
], ids=["member-project-yaml", "family-yaml"])
def test_a_file_behind_a_folder_this_user_cannot_search_is_named(
        holder, tmp_path, name, first):
    """A member's `project.yaml`, and `family.yaml`, each a link into a
    folder this user cannot search: named, where 3.14 said
    `member-not-a-project` and `family-manifest-missing`, and with the mode
    back the gate passes through the link."""
    with behind_a_locked_folder(holder / name, tmp_path):
        result = validate(holder)
    assert result.stderr.splitlines()[0].startswith(first), result.stderr
    assert "Traceback" not in result.stderr
    assert validate(holder).returncode == 0
