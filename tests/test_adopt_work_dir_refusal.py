# SPDX-License-Identifier: Apache-2.0
"""A `--work-dir` that is a file or cannot be made is refused by name in
`plan`, `check` and `execute`; `plan` refuses to clone into one this user
cannot write in; `check` refuses as `execute` does where it cannot open the
source, and before it says it clones one again; and `--help` says what
`--work-dir` is and where `--org` comes from (#650: L1-19, L1-20, L1-21,
L1-25, L1-28 and L1-49 of #457).

ON MAIN AT a5245427 (2026-10-16), probed:
- L1-19. `_work_root` made the directory with a bare `mkdir`, so a
  `--work-dir` that is a file ended `plan`, `check` and `execute` in a
  `FileExistsError` traceback, exit 1; one under a file, in a
  `NotADirectoryError` one; and one under a directory this user cannot
  write in (`chmod 500`), in a `PermissionError` one. All before any leg.
- L1-20. `plan --source acme/Atlas --work-dir <that directory itself>`
  ended in a `PermissionError` traceback at `source-readonly`, exit 1,
  where `check` and `execute` refuse the same directory as
  `adopt-work-dir-unwritable` (#524).
- L1-21. With that directory and `--source nonsense`, `check` refused
  `source-unresolvable` and `execute` `adopt-work-dir-unwritable`.
- L1-28. With that directory and a plan whose recorded clone is gone,
  `check` printed the NOTE that it clones `source.repository` again, and
  then refused `adopt-work-dir-unwritable`; `execute` refused with no NOTE.
- L1-25 and L1-49. `--work-dir` had no help on any of the three commands,
  and `--org` none on `plan`, so `docs/cli.md` said nothing of either.

And (#796) `plan` refuses a `--source` that is a file, a directory inside
a repository, empty or under a `~user` this machine has not, before it makes
the `--work-dir`: on main it made it first.

And (#978) a `--work-dir` that is a symlink round a loop is refused in
words that name the link and the loop. On main at 1a47ed07 a link to
itself, or one of a pair that lead to each other, was refused as "making
it a directory failed (File exists)", which reads as a file in the way,
with the way out for a folder this user cannot write in; a link that leads
into a loop it is not part of, or one whose path runs through a loop, said
`File exists` or `Too many levels of symbolic links` of a path the person
never typed, and a link to a file named the file and not the link. Each
names the link now, and the way out is to remove it or make it lead to a
directory. A dangling link is still made where it leads.

`chmod` keeps neither root nor a Windows user from making a directory, so
the tests of such a directory skip where it cannot (`unwritable_work`).
Nothing here reaches `gh`: every refusal comes before any clone.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import (ADOPT, git, load_without_bytecode, make_source_repo,
                      rmtree, run_script, write_plan)
from test_adopt_plan_leg_path_help import HELP_ENV, option_help, option_lines
from test_adopt_root_symlinks import (  # noqa: F401
    BASIC, PLAN_FILE, PROJECT, REMOTES, THING, WORK_FLAG, check,
    no_leg_was_created, planned, ticked, unwritable_work,
)
from test_adopt_shape_pin_and_work_dir import (
    FIX, WORK_DIR_UNWRITABLE, cannot_write,
)

#: `execute`'s word, before `FIX`, that nothing exists yet.
NOTHING_PUSHED = "no leg repository was created and nothing was pushed. "
PLAN_VERB, CHECK, EXECUTE = "plan", "check", "execute"
COMMANDS = (PLAN_VERB, CHECK, EXECUTE)
#: What `plan` is told, after `--source <it>`.
PLANNED = ("--project", PROJECT, "--org", "testorg", "--elected-by",
           "Test Human", "--elected-on", "2026-09-02")
#: The plan a refused `plan` would have written.
AGAIN = "again.yaml"
MINE = "mine\n"
#: Each command's codes for a `--work-dir`, which its help names.
WORK_DIR_OCCUPIED = "adopt-work-dir-occupied"
#: One another user owns, or every user can write in (#803).
WORK_DIR_SHARED = "adopt-work-dir-shared"
WORK_DIR_CODES = {
    command: (WORK_DIR_UNWRITABLE, WORK_DIR_OCCUPIED, WORK_DIR_SHARED)
    for command in COMMANDS}
NO_ORG = "adopt-no-org"
#: How the NOTE about a recorded clone that is gone begins.
GONE = "NOTE the plan's `source.local_path`, "


def run_in(command: str, base: Path, work: Path, *source: str):
    """`command --work-dir work`, for the source `planned` made under
    `base`: `plan` of that source, which writes `AGAIN`, or `check` or
    `execute` of its plan. `source` is a `--source` to pass instead."""
    plan = base / PLAN_FILE
    if command == PLAN_VERB:
        given = source or (str(base / THING),)
        return run_script(ADOPT, PLAN_VERB, "--source", *given, *PLANNED,
                          "--out", str(base / AGAIN), WORK_FLAG, str(work))
    flags = (("--source", *source) if source else ())
    if command == CHECK:
        return check(plan, *flags, WORK_FLAG, str(work))
    return run_script(ADOPT, EXECUTE, "--plan", str(plan), *flags, "--yes",
                      "--local-remote-dir", str(base / REMOTES),
                      WORK_FLAG, str(work))


def refused(command: str, detail: str, fix: str = FIX) -> str:
    """The whole of stderr when `command` refuses a `--work-dir`, with the
    way out `fix`."""
    done = NOTHING_PUSHED if command == EXECUTE else ""
    return (f"REFUSED {WORK_DIR_UNWRITABLE}: {detail}\n"
            f"Remediation: {done}{fix}\n")


#: What a `--work-dir` that is a symlink round a loop is refused for, in
#: #978's words.
LOOPS = "it is a symbolic link that leads round a loop"


def link_fix(link: Path) -> str:
    """The way out of a `--work-dir` that cannot be made because of the
    symlink `link`, the `--work-dir` or one on the way to it (#978)."""
    return (f"Remove the symbolic link {ticked(str(link))}, or make it lead "
            "to a directory, or pass another --work-dir, or none: without "
            "one, each run makes a new one.")


def linked(link: Path, target: str) -> None:
    """`link`, a symlink to `target`; the test skips on a machine that
    cannot make one."""
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("this machine cannot make a symlink")


def listed(base: Path) -> list[str]:
    """Every entry under `base`, a symlink as itself and never followed."""
    return sorted(os.path.relpath(os.path.join(top, name), base)
                  for top, directories, files in os.walk(base)
                  for name in (*directories, *files))


def refused_for_a_link(command: str, base: Path, work: Path, why: str,
                       link: Path) -> None:
    """`command --work-dir work` refuses it by name, exit 2, as `why`, with
    the way out for `link`: before any leg exists, with no plan written,
    and with nothing made or changed under `base` (#978)."""
    before = listed(base)
    result = run_in(command, base, work)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == refused(
        command, f"--work-dir {ticked(str(work))} cannot be made: {why}",
        link_fix(link))
    assert listed(base) == before
    assert not (base / AGAIN).exists()
    no_leg_was_created(base)


def real(base: Path, name: str) -> Path:
    """`name` in `base`, the directory read as `os.path.realpath` reads it:
    the spelling `_work_root` finds a link in."""
    return Path(os.path.realpath(base)) / name


def plan_cannot_write(work: Path, repository: str) -> str:
    """Why `plan` refuses `--work-dir work` for the `org/repo` source
    `repository`: as `check` and `execute` say it, up to what the command
    does there. `plan` clones, and says that (#903); `execute` builds."""
    why, _, _ = cannot_write(work).partition(", and `execute` builds")
    return (f"{why}, and `plan` clones {repository} into "
            f"`source-readonly/{repository.split('/')[1]}` there")


def mkdir_says(work: Path) -> str:
    """Why this machine cannot make `work` as `_work_root` makes it, in the
    words of its own error: `File exists` on Linux, for a file."""
    with pytest.raises(OSError) as caught:
        work.mkdir(parents=True, exist_ok=True)
    return caught.value.strerror


def cannot_make(work: Path) -> str:
    """Why `--work-dir work` is refused when it cannot be made. The path
    is read as `_work_root` reads it, with `os.path.realpath`, which takes
    a symlink loop as it is where Python 3.12's `Path.resolve` raises."""
    return (f"--work-dir {ticked(os.path.realpath(work))} cannot be made: "
            f"making it a directory failed ({mkdir_says(work)})")


def refused_alike(command: str, base: Path, work: Path) -> None:
    """`command --work-dir work` refuses by name, exit 2, before any leg
    exists and with no plan written, where it ended in a traceback."""
    expected = refused(command, cannot_make(work))
    result = run_in(command, base, work)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == expected
    assert not (base / AGAIN).exists()
    no_leg_was_created(base)


# ---------------------------------------------------------------------------
# L1-19: a `--work-dir` that cannot be made
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("below", [pytest.param("", id="a-file"),
                                   pytest.param("work", id="under-a-file")])
def test_a_work_dir_that_a_file_is_in_the_way_of_is_refused(
        tmp_path, command, below):
    """A file AT the `--work-dir`, or above it, and the directory cannot be
    made: each command refuses it as `adopt-work-dir-unwritable`, naming it
    and the system's reason, and the file is left as it was."""
    planned(tmp_path, {}, {}, {})
    a_file = tmp_path / "a-file"
    a_file.write_text(MINE)
    refused_alike(command, tmp_path, a_file / below if below else a_file)
    assert a_file.read_text() == MINE


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("pair", [pytest.param(False, id="to-itself"),
                                  pytest.param(True, id="a-pair")])
def test_a_work_dir_that_is_a_symlink_loop_is_refused(tmp_path, command,
                                                      pair):
    """A symlink at the `--work-dir` that leads to itself, or to another
    that leads back to it: no directory can be made there, and each command
    refuses it by name, where Python 3.12's `Path.resolve` ended it in a
    `RuntimeError` traceback before `mkdir`. The reason names the link and
    the loop, and the way out the link (#978): on main at 1a47ed07 both
    were refused as "making it a directory failed (File exists)", the words
    of a file in the way, with the way out for a folder this user cannot
    write in."""
    planned(tmp_path, {}, {}, {})
    loop = tmp_path / "loop"
    linked(loop, "other" if pair else loop.name)
    if pair:
        linked(tmp_path / "other", loop.name)
    refused_for_a_link(command, tmp_path, loop, LOOPS, loop)
    assert os.readlink(loop) == ("other" if pair else loop.name)


#: `--work-dir work`, a symlink into a loop it is not part of: the links,
#: as `(name, target)`, and the one in the loop `os.path.realpath` stops at.
#: It leads to one of a pair of links that lead to each other, or to a path
#: under a link to itself, which fails `mkdir` with ELOOP and not EEXIST.
INTO_A_LOOP = {
    "into-a-pair": ((("work", "a"), ("a", "b"), ("b", "a")), "a"),
    "through-a-loop": ((("work", "loop/sub"), ("loop", "loop")), "loop"),
}


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("shape", list(INTO_A_LOOP))
def test_a_work_dir_that_leads_into_a_loop_is_refused(tmp_path, command,
                                                      shape):
    """The `--work-dir` is a symlink that leads round a loop further on.
    The reason names it, and the link in the loop where `os.path.realpath`
    stopped; the way out names the `--work-dir`, which can be removed or
    mended whatever the loop is. On main at 1a47ed07 the reason named only
    the link in the loop, as if it were the `--work-dir`, with `File
    exists` or `Too many levels of symbolic links`."""
    planned(tmp_path, {}, {}, {})
    links, stop = INTO_A_LOOP[shape]
    for name, target in links:
        linked(tmp_path / name, target)
    work = tmp_path / "work"
    refused_for_a_link(
        command, tmp_path, work,
        f"{LOOPS}, at the symbolic link {ticked(str(real(tmp_path, stop)))}",
        work)


@pytest.mark.parametrize("command", COMMANDS)
def test_a_work_dir_under_a_symlink_loop_is_refused(tmp_path, command):
    """The `--work-dir` is no link, but the way to it runs through a link
    to itself: the reason says so and names that link, and the way out is
    to remove or mend it. On main at 1a47ed07 it said only `Too many levels
    of symbolic links`, with the way out for a folder this user cannot
    write in."""
    planned(tmp_path, {}, {}, {})
    linked(tmp_path / "loop", "loop")
    loop = real(tmp_path, "loop")
    refused_for_a_link(
        command, tmp_path, tmp_path / "loop" / "sub",
        f"the way to it leads round a loop, at the symbolic link "
        f"{ticked(str(loop))}", loop)


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for `_the_loop_in`."""
    return load_without_bytecode(ADOPT, "adopt_work_dir_refusal")


def test_only_a_symlink_that_loops_is_called_a_loop(adopter, tmp_path):
    """`_the_loop_in` names the symlink in a path that leads round a loop,
    and no other (#978). `os.path.realpath` leaves only such a link in the
    path it returns, and the system is asked all the same (ELOOP), so that
    a link left there for any other reason, one to a file or to a
    directory, is never called a loop."""
    (tmp_path / "a-dir").mkdir()
    (tmp_path / "a-file").write_text(MINE)
    for name, target in (("loop", "loop"), ("to-file", "a-file"),
                         ("to-dir", "a-dir")):
        linked(tmp_path / name, target)
    loop = real(tmp_path, "loop")
    assert adopter._the_loop_in(loop) == loop
    assert adopter._the_loop_in(loop / "sub") == loop
    for name in ("to-file", "to-dir/sub", "a-dir/sub"):
        assert adopter._the_loop_in(real(tmp_path, name)) is None, name


@pytest.mark.parametrize("command", COMMANDS)
def test_a_work_dir_that_is_a_symlink_to_a_file_is_refused(tmp_path,
                                                           command):
    """A symlink at the `--work-dir` that leads to a file is no loop, and
    is not said to be one: the reason names the link and the file it leads
    to, and the way out the link. On main at 1a47ed07 it named the file
    alone, as if it were the `--work-dir`, with `File exists`. A file AT
    the `--work-dir` is still `File exists` (above)."""
    planned(tmp_path, {}, {}, {})
    a_file = tmp_path / "a-file"
    a_file.write_text(MINE)
    work = tmp_path / "work"
    linked(work, a_file.name)
    refused_for_a_link(
        command, tmp_path, work,
        f"it is a symbolic link that leads to "
        f"{ticked(str(real(tmp_path, a_file.name)))}, which is not a "
        "directory", work)
    assert a_file.read_text() == MINE


@pytest.mark.parametrize("command", (PLAN_VERB, CHECK))
@pytest.mark.parametrize("target", ["target-a", "missing-dir/target-b"])
def test_a_dangling_symlink_work_dir_is_made_where_it_leads(tmp_path,
                                                            command, target):
    """CONTROL, as on main: a `--work-dir` that is a symlink to nothing is
    read with `os.path.realpath` as the path it leads to, which is made,
    with any directory missing above it, and the run goes on. So a dangling
    link never meets #978's refusal (r903's measure on #963)."""
    planned(tmp_path, {}, {}, {})
    work = tmp_path / "work"
    linked(work, target)
    result = run_in(command, tmp_path, work)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / target).is_dir()
    assert os.readlink(work) == target


@pytest.mark.parametrize("command", COMMANDS)
def test_a_work_dir_this_user_cannot_make_is_refused(tmp_path, command,
                                                     unwritable_work):
    """A `--work-dir` in a directory this user cannot write in (`chmod
    500`): each command refuses it by name, where it ended in a
    `PermissionError` traceback."""
    planned(tmp_path, {}, {}, {})
    refused_alike(command, tmp_path, unwritable_work / "made-here")


# ---------------------------------------------------------------------------
# L1-20: `plan` of an `org/repo` source, into a directory it cannot write in
# ---------------------------------------------------------------------------

def test_plan_refuses_to_clone_into_a_work_dir_it_cannot_write_in(
        tmp_path, unwritable_work):
    """An `org/repo` source is cloned into the work directory, so `plan`
    refuses one this user cannot write in, as `check` does, before it says
    it clones anything: it ended in a `PermissionError` traceback at
    `source-readonly`. A local source is read in place, and nothing is
    written there, so `plan` of one still writes its plan."""
    planned(tmp_path, {}, {}, {})
    cloned = run_in(PLAN_VERB, tmp_path, unwritable_work,
                    f"testorg/{PROJECT}")
    assert cloned.returncode == 2, cloned.stderr + cloned.stdout
    assert cloned.stdout == ""
    assert cloned.stderr == refused(PLAN_VERB, plan_cannot_write(
        unwritable_work, f"testorg/{PROJECT}"))
    assert not (tmp_path / AGAIN).exists()
    read = run_in(PLAN_VERB, tmp_path, unwritable_work)
    assert read.returncode == 0, read.stderr + read.stdout
    assert (tmp_path / AGAIN).is_file()


# ---------------------------------------------------------------------------
# L1-21 and L1-28: `check` refuses as `execute` does
# ---------------------------------------------------------------------------

def test_check_refuses_a_source_it_cannot_open_as_execute_does(
        tmp_path, unwritable_work):
    """With a `--work-dir` this user cannot write in, `execute` refuses it
    before it opens the source, so a `--source` that is neither a path nor
    an `org/repo` is never asked about. `check` refuses the same, where it
    refused `source-unresolvable`."""
    planned(tmp_path, {}, {}, {})
    executed = run_in(EXECUTE, tmp_path, unwritable_work, "nonsense")
    checked = run_in(CHECK, tmp_path, unwritable_work, "nonsense")
    assert executed.stderr == refused(EXECUTE, cannot_write(unwritable_work))
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert checked.stderr == refused(CHECK, cannot_write(unwritable_work))


def test_check_asks_the_work_dir_before_it_says_it_clones_again(
        tmp_path, unwritable_work):
    """A plan whose clone `plan` made records its repository, and where
    that clone is gone, `check` clones the repository again and says so in
    a NOTE. Into a `--work-dir` this user cannot write in it cannot, so it
    refuses first, with no NOTE, as `execute` does: it said the repository
    is cloned again, then refused. The plan here is of a local source, its
    record then marked as `plan`'s own clone (`cloned: true`), so that no
    `gh` is needed (#652: a path the person gave is never cloned again)."""
    source = make_source_repo(tmp_path / THING, tree=BASIC)
    git("remote", "add", "origin",
        f"https://github.com/testorg/{PROJECT}.git", cwd=source)
    written = write_plan(source, tmp_path / PLAN_FILE, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    plan = tmp_path / PLAN_FILE
    text = plan.read_bytes()
    assert text.count(b"  cloned: false\n") == 1
    plan.write_bytes(text.replace(b"  cloned: false\n", b"  cloned: true\n"))
    rmtree(source)
    executed = run_in(EXECUTE, tmp_path, unwritable_work)
    checked = run_in(CHECK, tmp_path, unwritable_work)
    assert executed.stdout == ""
    assert GONE not in checked.stdout
    assert checked.stderr == refused(CHECK, cannot_write(unwritable_work))
    assert executed.stderr == refused(EXECUTE, cannot_write(unwritable_work))


# ---------------------------------------------------------------------------
# #796: `plan` refuses a `--source` before it makes the `--work-dir`
# ---------------------------------------------------------------------------

#: `--source` values `plan` refuses before anything exists, each as the
#: source repository `THING` in `base` would be given: a file in it, a
#: directory inside it, nothing, and a `~user` this machine has not.
REFUSED_SOURCES = {
    "a-file": lambda source: str(source / "README.md"),
    "a-directory-inside": lambda source: str(source / "src"),
    "empty": lambda _: "",
    "unknown-user": lambda _: "~no-such-user-796/Thing",
}


@pytest.mark.parametrize("given", list(REFUSED_SOURCES.values()),
                         ids=list(REFUSED_SOURCES))
def test_plan_refuses_a_source_before_it_makes_the_work_dir(tmp_path, given):
    """On main `plan` made the `--work-dir` it was given, and then ended in
    a traceback (a file, `~user`) or planned a directory inside the
    repository, or, for `''`, the one it ran in, exit 0. Each is refused
    now, run in the repository, and the `--work-dir` is never made."""
    source = make_source_repo(tmp_path / THING, tree=BASIC)
    work = tmp_path / "made-here"
    result = run_script(ADOPT, PLAN_VERB, "--source", given(source),
                        *PLANNED, "--out", str(tmp_path / AGAIN), WORK_FLAG,
                        str(work), cwd=source)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith("REFUSED source-"), result.stderr
    assert not work.exists()
    assert not (tmp_path / AGAIN).exists()


# ---------------------------------------------------------------------------
# L1-25 and L1-49: what `--help` says
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def helps() -> dict[str, str]:
    """Each command's `--help`, at the width `docs/cli.md` is rendered at."""
    out = {}
    for command in COMMANDS:
        result = run_script(ADOPT, command, "--help", env=HELP_ENV)
        assert result.returncode == 0, result.stderr + result.stdout
        out[command] = result.stdout
    return out


@pytest.mark.parametrize("command", COMMANDS)
def test_each_commands_help_says_what_its_work_dir_is(helps, command):
    """Where the default lands and that it goes when it holds nothing; that
    a `--work-dir` given is made where it is missing and kept; and the codes
    the command refuses one under, which the tests above print."""
    said = option_help(helps[command], WORK_FLAG)
    for words in ("system temp folder", "holds no file",
                  "made where it is missing", "nothing in it is removed",
                  *(f"`{code}`" for code in WORK_DIR_CODES[command])):
        assert words in said, f"`{command} --help` never says {words}"


@pytest.mark.parametrize(("command", "flag", "code"), [
    *((command, WORK_FLAG, code) for command in COMMANDS
      for code in WORK_DIR_CODES[command]),
    (PLAN_VERB, "--org", NO_ORG)])
def test_a_code_sits_whole_on_one_line_of_the_help(helps, command, flag,
                                                   code):
    """`docs/cli.md` is grepped for the code a tool prints, and at 80
    columns `textwrap` breaks a hyphenated word at a line end."""
    lines = option_lines(helps[command], flag)
    assert any(f"`{code}`" in line for line in lines), "\n".join(lines)


def test_plan_help_says_where_org_comes_from(helps):
    """`--org` is read from the source when it is not given: the `org/repo`
    `plan` clones, or the url a local source's `origin` names. A path
    `origin`, or none, names no organisation, and `plan` refuses without
    the flag."""
    said = option_help(helps[PLAN_VERB], "--org")
    for words in ("`org/repo` --source", "`origin`", "is a path",
                  f"`{NO_ORG}`"):
        assert words in said, f"`plan --help` says no {words} of --org"
