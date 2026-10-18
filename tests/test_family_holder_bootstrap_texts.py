# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/bootstrap.py` and
`scripts/validate-family.py`: seven lines of #839, each in the state it
names, each remedy typed as printed.

THE ISSUE'S SEVEN LINES, each reproduced on #819's head (233a334e) before
this change, but where one already held there:

- 1. `make bootstrap` told a person to set `SHAPE_LEGS_TOKEN` and, on the
  next line, that no credential would check the members out: the advice was
  printed for every failed `git submodule update`. It is printed only where
  git asked for a credential, not where its init died at a gitlink it has
  no url for or it read nothing from `.gitmodules`; beside the denial, it
  is for the members the denial does not name.
- 2. A member's refusal and its finding both read `make bootstrap exited
  2`: make exits 2 for any command that fails, and for a failure of its
  own. The line names the code of the member's command, read from make's
  `Error <code>` line, or says make printed none.
- 3. In the gate's state after `git mv members/<P> Members/<P>`, staged,
  with a commit or an untracked file in the checkout it moved, the printed
  `git rm --cached -- Members/<P>` refused, exit 1 (`staged content
  different from both the file and the HEAD`). It carries `-f`, with what
  `-f` does, there and in the wrong-case move's `git rm`.
- 4. The wrong-case move's guarded `mv` kept a symbolic link at the variant
  that points at the row's own directory or at a clone, so `family.py add`
  then refused it; and with nothing at the variant, a fresh clone's, the
  `mv` failed `cannot stat`, exit 1 (comment 6237599648 is the same fault).
  A link is always moved, the link and never what it points at, and nothing
  there moves nothing.
- 5. Comment 6237354577 (a): bootstrap read `.gitmodules` only from the
  work tree. That HELD at 233a334e (#819's `gitmodules_source` reads the
  index's, then HEAD's): the credential's skip here asks it again where
  the work tree lost the file.
- 6. Comment 6237354577 (b): `member-gitmodules-absent`'s `git config -f`
  lines, where the work tree's `.gitmodules` is gone, made a file of one
  section, which staged and committed dropped every other. The first
  finding that writes the file puts it back first, and no other does,
  which a second `member-gitmodules-url-absent` did over the url the first
  had written.

#884, from rv876's review of #876, the change that made the lines above
true:

- Five mutants of line 1's and line 2's code passed every test: the
  advice where every member was checked out and git read nothing (R10,
  R11), the first `Error` line read for the last (R1), the line read only
  from a make run by no make (R8), and the prompt a member writes to
  stderr held back until its answer was typed (R7). A test holds each
  now, and line 3's test asserts the store its docstring names.
- Line 2's line misled in three cases: a member whose make runs another
  read `exited 2` for its inner command's 1; under `make -k`, an `Error`
  line followed by more than 4096 bytes was said not to be there; and a
  command a signal killed under dash read `exited 137`, which
  `run_make`'s docstring said could not happen. It names the innermost
  command's code, reads each line as it passes, and its docstring says
  what a signal does.
- Passing make's stderr on changes what a member's commands and a person
  see: `run_make`'s docstring says what, and the tests hold what it says.

THE SAME FAMILY, OFFLINE RULES AND HELPERS as
`tests/test_family_bootstrap_gate_order.py` (#648) and
`tests/test_validate_family_remedies_typed.py` (#681). A missing credential
is git's refusal of the file transport to the fixture's local remotes, as
there. A state that needs a directory or a link at a case variant is
skipped where the disk cannot hold one (`case_sensitive_disk`).
"""

from __future__ import annotations

import os
import re
import select
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import REPO, load_without_bytecode, rmtree, run_script
from test_family import FAMILY, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import (
    NO_GITLINK, NO_SECTION, NO_URL, OUTSIDE_CURE, SECTION_CURE, STOPPED,
    UNMERGED, UNMERGED_CURE, UNNAMED_CURE, UNNAMED_STOPS, VALIDATOR_CURE,
    bootstrap, cloned, edited_clone, failed_on, fetching, not_fetched,
    skip_by_subset, type_line, variant, without_url,
)
from test_family_dry_run import isolated
from test_family_gitmodules_values import (
    DAMAGED, LOST, MEND_CURE, UNPARSED, refused_why, value_cure, with_line,
)
from test_family_head_lost_gitmodules import (  # noqa: F401
    FORCED_SAID, GUARDED_MOVE, absent, assert_passes_in_every_mode,
    case_sensitive_disk, commit_all, committed_gitmodules, head_lost,
    moved_as_printed, pinned, recorded_at, refused_at, staged_and_committed,
    variant_refused,
)
from test_family_member_path import MEMBER, OTHER, raw
from test_family_remove_gitmodules import verb_args
from test_validate_family_remedies_typed import (
    MOVED_TO, VARIANT_PATH, mounted_at_the_variant,
)
from test_validate_family_typed_states import GONE, ROW, URL_ABSENT, gone
from test_validate_family_unnamed_mounts import (
    GITLINK_SAID, VARIANT, codes, commands, findings, spare_commits,
    stage_gitlink, take_out_as_printed,
)

# --- line 1: the credential advice -----------------------------------------

#: The advice (a) gives where git asked for a credential, alone and beside
#: the line that names members no credential would check out.
ADVICE = ("  If {which} are PRIVATE, set SHAPE_LEGS_TOKEN (a fine-grained "
          "PAT with contents:read on them) or export an App-minted "
          "SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive is "
          "bootstrapped below.")
ALONE = ADVICE.format(which="the members")
BESIDE = ADVICE.format(which="the members the next line does not name")

#: How each line bootstrap writes to stderr itself begins; git's own lines,
#: which (a) passes on under the first, begin otherwise.
OURS = ("  FETCH INCOMPLETE ", "  If ", "  NOT CHECKED OUT, ",
        "  NO MEMBER UPDATED, ", "family bootstrap ")
FETCH_LINE = re.compile(r"  FETCH INCOMPLETE \(git exit \d+\) using "
                        r"credential source 'none':")


def after_fetch_line(result) -> list[str]:
    """Bootstrap's own stderr lines, which must begin with the fetch's,
    after it: git's lines between are its own."""
    ours = [line for line in result.stderr.splitlines()
            if line.startswith(OURS)]
    assert ours, result.stderr
    assert FETCH_LINE.fullmatch(ours[0]), result.stderr
    return ours[1:]


def unmerged_gitmodules(root: Path, env: dict) -> None:
    """`.gitmodules` held in the index only at a merge's three conflict
    stages, each the blob it held, as a conflicted merge leaves it."""
    blob = raw(root, env, "rev-parse", ":.gitmodules").stdout.decode(
        "ascii").strip()
    raw(root, env, "update-index", "--index-info", stdin=(
        f"0 {'0' * 40}\t.gitmodules\n"
        + "".join(f"100644 {blob} {stage}\t.gitmodules\n"
                  for stage in (1, 2, 3))).encode("ascii"))


def plain_clone_of(set_up):
    """A state `set_up` makes in the holder, then a plain clone of it."""
    def made(holder: Path, env: dict, family, tmp_path: Path) -> Path:
        set_up(holder, env)
        return cloned(holder, env, family, tmp_path, recurse=False)
    return made


def edited(edit):
    """HEAD's `.gitmodules` put through `edit` and committed, then a plain
    clone of it."""
    def made(holder: Path, env: dict, family, tmp_path: Path) -> Path:
        return edited_clone(holder, env, family, tmp_path, edit)[0]
    return made


def unmerged_in_a_clone(holder: Path, env: dict, family,
                        tmp_path: Path) -> Path:
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    unmerged_gitmodules(clone, env)
    return clone


def unnamed_stop(name: str):
    """rv648's S1 or H1, then a plain clone of it."""
    def made(holder: Path, env: dict, family, tmp_path: Path) -> Path:
        UNNAMED_STOPS[name](holder, env, family)
        return cloned(holder, env, family, tmp_path, recurse=False)
    return made


def outside(holder: Path, env: dict, family, tmp_path: Path) -> Path:
    """rv648's H2: a gitlink outside members/, then a plain clone of it."""
    stage_gitlink(holder, f"vendor/{SPARE}", spare_commits(family)[1])
    commit_all(holder, env, "A gitlink mounted by hand outside members/")
    return cloned(holder, env, family, tmp_path, recurse=False)


ROWS = (f"members/{MEMBER}", f"members/{OTHER}")
STOP_AT_OTHER = STOPPED.format(path=f"members/{OTHER}")

#: `(a plain clone in the state, why (a) says each row is no credential's,
#: what it says cures them)`: every reason `unfetchable` gives where git
#: exits non-zero (#648, #768). Git asked for no credential in any.
NO_CREDENTIAL_ASKED = {
    "head-lost": (plain_clone_of(head_lost), (NO_SECTION, NO_SECTION),
                  VALIDATOR_CURE),
    "variant": (plain_clone_of(variant),
                (STOPPED.format(path=f"Members/{OTHER}"), NO_GITLINK),
                f"{VALIDATOR_CURE} {UNNAMED_CURE}"),
    "no-url": (edited(lambda data: without_url(data, OTHER)),
               (STOP_AT_OTHER, NO_URL),
               SECTION_CURE.format(path=f"members/{OTHER}")),
    "unmerged": (unmerged_in_a_clone, (UNMERGED, UNMERGED), UNMERGED_CURE),
    "value-refused": (edited(with_line("update = None")),
                      (refused_why("update", "None"),) * 2,
                      value_cure("update")),
    "unparsed": (edited(lambda data: data + DAMAGED["conflict-marker"]),
                 (UNPARSED, UNPARSED), MEND_CURE),
    "stray": (unnamed_stop("stray"),
              (STOPPED.format(path=f"Members/{OTHER}"),) * 2, UNNAMED_CURE),
    "hand-mount": (unnamed_stop("hand-mount"),
                   (STOPPED.format(path=f"members/{SPARE}"),) * 2,
                   UNNAMED_CURE),
    "outside": (outside, (STOPPED.format(path=f"vendor/{SPARE}"),) * 2,
                OUTSIDE_CURE.format(path=f"vendor/{SPARE}")),
}


@pytest.mark.parametrize("make, whys, cure", NO_CREDENTIAL_ASKED.values(),
                         ids=NO_CREDENTIAL_ASKED)
def test_no_advice_is_printed_beside_its_denial(family, holder, offline,
                                                tmp_path, make, whys, cure):
    """LINE 1, each reason a row is no credential's. Git died in its init,
    or reading `.gitmodules`, and fetched nothing, so (a)'s line says both
    members are no credential's, and the advice to set one printed just
    above it said the opposite. Bootstrap's own lines on stderr are now the
    fetch's, the denial and the failure, exactly."""
    env = fetching(isolated(offline, tmp_path))
    clone = make(holder, env, family, tmp_path)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_fetch_line(result) == [
        not_fetched(*zip(ROWS, whys), cure=cure), failed_on(MEMBER, OTHER)]


def as_cloned(root: Path, env: dict) -> None:
    """The plain clone, as it was cloned."""


#: A plain clone, and one whose work tree lost `.gitmodules`, not
#: committed, where git reads the index's or HEAD's (comment (a)).
CREDENTIAL_S = {"as-cloned": as_cloned, **LOST}


@pytest.mark.parametrize("lose", CREDENTIAL_S.values(), ids=CREDENTIAL_S)
def test_the_credential_s_skip_prints_the_advice_alone(family, holder,
                                                       offline, tmp_path,
                                                       lose):
    """LINE 1's other half, and comment (a): a plain clone with no
    credential for the members, where git asked for one and was refused.
    The advice stands, alone, and the run ends ok. Where the work tree lost
    `.gitmodules`, git reads the index's, or HEAD's, and bootstrap reads the
    file git reads (#819), so the members are still the credential's, not
    `no section of .gitmodules gives that path`."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    lose(clone, env)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert after_fetch_line(result) == [ALONE]
    assert result.stdout.endswith("\nfamily bootstrap ok\n"), result.stdout


def test_a_leg_the_credential_s_keeps_the_advice_with_every_member_out(
        family, holder, offline, tmp_path):
    """No misfire: every member checked out, and their legs refused for
    want of a credential. No row is left out, so no line denies anything,
    and the advice, which is for the legs too, stands."""
    env = isolated(offline, tmp_path)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    raw(clone, fetching(env), "submodule", "update", "--init")
    assert not (clone / ROW / "spec" / ".git").exists(), "premise: no legs"

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 0, result.stdout + result.stderr
    assert after_fetch_line(result) == [ALONE]


def test_beside_a_denial_the_advice_is_for_the_members_it_does_not_name(
        family, holder, offline, tmp_path):
    """LINE 1, both kinds at once: a clone that chose MEMBER alone, whose
    fetch git refuses for want of a credential, and OTHER's section with no
    url, which git skips there and no credential cures. The advice, then
    the denial for OTHER, the advice saying it is for the members the next
    line does not name."""
    env = isolated(offline, tmp_path)
    clone = edited(lambda data: without_url(data, OTHER))(
        holder, env, family, tmp_path)
    env = skip_by_subset(clone, env)

    result = bootstrap(clone, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_fetch_line(result) == [
        BESIDE,
        not_fetched((f"members/{OTHER}", NO_URL),
                    cure=SECTION_CURE.format(path=f"members/{OTHER}")),
        failed_on(OTHER)]


#: `(an edit to HEAD's .gitmodules, why git updated no member, what cures
#: it)`: a value git refuses, and a line it cannot parse (#768).
GIT_READ_NOTHING = {
    "value-refused": (with_line("update = None"),
                      refused_why("update", "None"), value_cure("update")),
    "unparsed": (lambda data: data + DAMAGED["conflict-marker"], UNPARSED,
                 MEND_CURE),
}


@pytest.mark.parametrize("edit, why, cure", GIT_READ_NOTHING.values(),
                         ids=GIT_READ_NOTHING)
def test_no_advice_beside_no_member_updated_with_every_member_checked_out(
        holder, offline, tmp_path, edit, why, cure):
    """LINE 1 with every member checked out, as in the holder itself, and
    the edit committed: git dies reading `.gitmodules`, so it fetched
    nothing, and the line says no member was updated, and not for want of
    a credential. No row is left to deny, so nothing else keeps the advice
    off the line before (rv876's R10 and R11, which dropped `unreadable`
    or `refused` from `credential_advice` and printed it there, as
    `tests/test_family_gitmodules_values.py`, asking only the last two
    lines, let pass). Bootstrap's own lines are the fetch's, that one and
    the failure, exactly."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    committed_gitmodules(holder, env, edit(data))

    result = bootstrap(holder, env, "--skip-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert after_fetch_line(result) == [
        f"  NO MEMBER UPDATED, and not for want of a credential: {why}. "
        f"{cure}", "family bootstrap FAILED: .gitmodules (git cannot read it)"]


# --- line 2: a member's finding, its refusal, and make's own failure --------

#: `{project: its Makefile}`, every recipe for both targets (#839's line 2).
MAKEFILES = {
    "Find": b"bootstrap validate:\n\t@echo 'Find: a finding' >&2; exit 1\n",
    "Fine": b"bootstrap validate:\n\t@true\n",
    "Refuse": b"bootstrap validate:\n\t@echo 'Refuse: refused' >&2; exit 2\n",
    "NoRule": b"other:\n\t@true\n",
}


def with_members(holder: Path, makefiles: dict[str, bytes]) -> None:
    """`holder`'s `family.yaml` naming one member for each of `makefiles`,
    `{project: its Makefile}`, at `members/<project>`, checked out there
    as far as bootstrap asks: a `.git` and that Makefile."""
    (holder / "family.yaml").write_bytes(
        b"name: InkRouter\nmembers:\n" + b"".join(
            f"  - project: {project}\n    path: members/{project}\n"
            .encode("ascii") for project in makefiles))
    for project, makefile in makefiles.items():
        (holder / "members" / project / ".git").mkdir(parents=True)
        (holder / "members" / project / "Makefile").write_bytes(makefile)


@pytest.mark.parametrize("target", ["bootstrap", "validate"])
def test_a_finding_a_refusal_and_make_s_own_failure_are_told_apart(
        holder, tmp_path, target):
    """LINE 2. Four members, each checked out, whose `make <target>` runs a
    command that exits 1 (a finding, as a member's `bootstrap FAILED`), one
    that exits 0, one that exits 2 (a refusal), and none at all, make
    failing on its own (`No rule to make target`). Make exits 2 for all
    three failures, and the line said `exited 2` for each; it names the
    command's own code now, read from make's `Error <code>` line, and says
    so where make printed none. Make's own lines, and the members', reach
    stderr as they did. `--members-make validate`, which has no script of
    its own to call, the same."""
    if shutil.which("make") is None:
        pytest.skip("no make on PATH")
    with_members(holder, MAKEFILES)

    result = run_script(holder / "scripts" / "bootstrap.py", "--no-fetch",
                        "--members-make", target, cwd=holder,
                        env={"MAKE": ""})

    assert result.returncode == 1, result.stdout + result.stderr
    errors = result.stderr.splitlines()
    assert errors[-1] == failed_in_make(
        exited("Find", 1, target), exited("Refuse", 2, target),
        named_none("NoRule", target)), result.stderr
    for said in ("Find: a finding", "Refuse: refused",
                 f"No rule to make target '{target}'"):
        assert any(said in line for line in errors[:-1]), (said, errors)
    assert f"  --- Fine: make {target} ---" in result.stdout.splitlines()


def exited(project: str, code: int, target: str = "bootstrap") -> str:
    """What the line says of a member whose command make names."""
    return f"{project} (make {target}: the member's command exited {code})"


def named_none(project: str, target: str = "bootstrap") -> str:
    """What the line says of a member whose make named no command's code."""
    return (f"{project} (make {target} exited 2 and printed no `Error "
            "<code>` line for a command of the member's: make's own message "
            "above says what failed)")


def failed_in_make(*said: str) -> str:
    """The run's last line, naming each member's failure as `said`."""
    return "family bootstrap FAILED: " + ", ".join(said)


def without_make() -> dict:
    """This process's environment without the `MAKE`, `MAKEFLAGS`,
    `MAKELEVEL` and `MFLAGS` a make running the tests would give it, so a
    run starts as it does from a shell."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("MAKE", "MFLAGS"))}


def made(holder: Path, tmp_path: Path, *,
         under_make: bool) -> subprocess.CompletedProcess:
    """`bootstrap.py --no-fetch` in `holder`, every member's make with
    `-k`, its output as bytes: run as it is, or run by a make of its own
    (`under_make`), as the holder's own `make bootstrap` runs it, so that
    the member's make is `make[1]` and prints that."""
    env = without_make()
    argv = [sys.executable, "scripts/bootstrap.py", "--no-fetch"]
    if under_make:
        parent = tmp_path / "parent.mk"
        parent.write_bytes(f"run:\n\t@{shlex.join(argv)}\n".encode())
        argv = ["make", "-k", "-f", str(parent)]
    else:
        env["MAKEFLAGS"] = "k"
    return subprocess.run(argv, cwd=str(holder), env=env,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          check=False)


#: Members whose make runs another make, or whose `Error` line is followed
#: by more than 4096 bytes on stderr, each with what the line says of it:
#: the innermost command's code, read from each line as it passes (#884's
#: line 2). An inner make that fails on its own names none, as make's own
#: failure does, but its parent's `Error 2` is passed over only: a command
#: that runs one and then fails itself is named.
INNERMOST = {
    "Recurse": (b"bootstrap:\n\t@$(MAKE) -s inner\n"
                b"inner:\n\t@echo 'Find: a finding' >&2; exit 1\n", 1),
    "RecurseRefuse": (b"bootstrap:\n\t@$(MAKE) -s inner\n"
                      b"inner:\n\t@echo 'Refuse: refused' >&2; exit 2\n", 2),
    "InnerOwn": (b"bootstrap:\n\t@$(MAKE) -s nothere\n", None),
    "InnerThenOwn": (b"bootstrap:\n\t@$(MAKE) -s nothere; exit 3\n", 3),
    "Long": (b"bootstrap: one two\n"
             b"one:\n\t@echo 'Find: a finding' >&2; exit 1\n"
             b"two:\n\t@printf '%05000d' 0 >&2; echo >&2\n", 1),
}
#: A member whose two commands fail, under `-k`: the last `Error` line
#: names the code (rv876's R1), and a member's finding, both under a
#: parent make, where make prints `make[1]:` (R8).
LAST = {"Find": (MAKEFILES["Find"], 1),
        "Twice": (b"bootstrap: one two\n"
                  b"one:\n\t@echo 'one: a finding' >&2; exit 1\n"
                  b"two:\n\t@echo 'two: refused' >&2; exit 2\n", 2)}
#: A command a signal kills: where the shell outlives it, as dash does,
#: the shell exits 137, which make names; where it is the shell that is
#: killed, make prints `Killed` in place of a code (`run_make`'s
#: docstring).
SIGNALLED = {"Outlived": (b"bootstrap:\n\t@sh -c 'kill -KILL $$$$'; "
                          b"exit $$?\n", 137),
             "Killed": (b"bootstrap:\n\t@kill -KILL $$$$\n", None)}
#: `(run by a make of its own?, {project: (its Makefile, the code the line
#: names, None for none)})`.
MAKE_CASES = {"last-under-make": (True, LAST),
              "innermost-under-make": (True, INNERMOST),
              "innermost": (False, INNERMOST),
              "signal": (False, SIGNALLED)}


@pytest.mark.parametrize("under_make, members", MAKE_CASES.values(),
                         ids=MAKE_CASES)
def test_the_line_names_the_code_of_the_member_s_innermost_command(
        holder, tmp_path, under_make, members):
    """#884's LINE 2, and rv876's R1 and R8. At #876's head a member whose
    make ran `$(MAKE) inner` read `exited 2` for the inner command's 1, a
    refusal's code, since make's own `Error 2` for the inner make came
    last; and under `make -k`, an `Error 1` followed by 5000 bytes read
    "printed no `Error <code>` line", since only the last 4096 bytes were
    read. Each is named now, run as it is and under a parent make, where
    the member's make says `make[1]:` and the make it runs `make[2]:`. The
    last `Error` line of a member's names its code, and a signal's code is
    its shell's, where the shell outlives it, as `run_make` now says."""
    if shutil.which("make") is None:
        pytest.skip("no make on PATH")
    with_members(holder, {project: makefile
                          for project, (makefile, _) in members.items()})

    result = made(holder, tmp_path, under_make=under_make)

    errors = result.stderr.decode("utf-8", "replace").splitlines()
    assert result.returncode == (2 if under_make else 1), errors
    assert [line for line in errors if line.startswith("family ")] == [
        failed_in_make(*(named_none(project) if code is None
                         else exited(project, code)
                         for project, (_, code) in members.items()))]
    if under_make:
        assert errors[-1].startswith("make: *** "), errors
        assert not [line for line in errors[:-1]
                    if line.startswith("make: ")], errors


def loaded(script: str, name: str):
    """The family holder's `scripts/<script>`, loaded by path as `name`;
    `sys.path` as it was."""
    kept = list(sys.path)
    module = load_without_bytecode(
        REPO / "templates" / "family-root" / "scripts" / script, name)
    sys.path[:] = kept
    return module


def test_a_line_that_comes_in_pieces_is_read_whole():
    """`MakeErrors` reads make's stderr in whatever pieces the pipe gives:
    an `Error` line cut in two is read whole, and a line nothing ends, as
    a progress meter's carriage returns leave one, is kept only as its
    last `LINE_KEPT` bytes while it waits."""
    boot = loaded("bootstrap.py", "bootstrap_holder_texts")
    errors = boot.MakeErrors()
    for _ in range(10):
        errors.read(b"x" * 1000 + b"\r")
    assert len(errors.unended) == boot.LINE_KEPT
    errors.read(b"make[1]: *** [Makefile:2: boot")
    errors.read(b"strap] Error 1\n")
    assert errors.code == 1


#: A member that says whether its stdout and stderr are a terminal, then
#: asks on stderr and reads the answer, as a member's recipe may; what it
#: asks, the answer typed, and how long the question may take to show
#: before the answer is typed all the same.
ASKS = (b"bootstrap:\n"
        b"\t@if test -t 1; then echo 'stdout: a terminal'; fi\n"
        b"\t@if test -t 2; then :; else echo 'stderr: no terminal'; fi\n"
        b"\t@printf 'Continue? ' >&2; read answer; echo \"got $$answer\"\n")
PROMPT, ANSWER, PROMPT_WAIT = b"Continue? ", b"yes\n", 10.0


def read_until(leader: int, wanted: bytes | None, deadline: float) -> bytes:
    """What a pseudo-terminal's `leader` gives until `wanted` shows in it,
    every writer has closed it, or `deadline` passes."""
    got = b""
    while time.monotonic() < deadline and not (wanted and wanted in got):
        if not select.select([leader], [], [], 0.1)[0]:
            continue
        try:
            chunk = os.read(leader, 4096)
        except OSError:  # EIO: every writer closed it
            break
        if not chunk:
            break
        got += chunk
    return got


def on_a_terminal(argv: list[str], cwd: Path) -> tuple[bytes, bytes, int]:
    """`argv` run with a pseudo-terminal for its stdin, stdout and stderr,
    as a person runs `make bootstrap`: what it wrote before `PROMPT`
    showed, what it wrote after `ANSWER` was typed, and its exit code.
    `ANSWER` is typed once `PROMPT` shows, or after `PROMPT_WAIT` seconds
    where it does not."""
    pty = pytest.importorskip("pty")
    leader, follower = pty.openpty()
    proc = subprocess.Popen(argv, cwd=str(cwd), env=without_make(),
                            stdin=follower, stdout=follower, stderr=follower,
                            start_new_session=True)
    os.close(follower)
    try:
        before = read_until(leader, PROMPT, time.monotonic() + PROMPT_WAIT)
        os.write(leader, ANSWER)
        after = read_until(leader, None, time.monotonic() + 60)
    finally:
        os.close(leader)
    return before, after, proc.wait(timeout=60)


def test_a_member_s_question_shows_before_its_answer_is_typed(holder):
    """rv876's R7, and what `run_make` says a member loses. On a terminal,
    as a person runs it, a member asks `Continue? ` on stderr and waits
    for the answer: the question passes through this run, which flushes it
    as it comes, so it shows before the answer is typed. With
    `passed_on`'s flush dropped it showed only once the run ended, after
    the answer, and every test passed. The member's stdout is the
    terminal; its stderr, a pipe, is not."""
    if shutil.which("make") is None:
        pytest.skip("no make on PATH")
    with_members(holder, {"Ask": ASKS})

    before, after, code = on_a_terminal(
        [sys.executable, "scripts/bootstrap.py", "--no-fetch"], holder)

    assert before.split(b"\r\n")[1:] == [
        b"", b"(a) members and their legs", b"  skipped (--no-fetch)", b"",
        b"(b) each member's own `make bootstrap`",
        b"  --- Ask: make bootstrap ---", b"stdout: a terminal",
        b"stderr: no terminal", PROMPT], before
    assert after.split(b"\r\n") == [
        b"yes", b"got yes", b"", b"family bootstrap ok", b""], after
    assert code == 0


#: A member whose command writes bytes to stderr that are not UTF-8, and
#: leaves a process running that writes to stderr a second later.
LEAVES = (b"bootstrap:\n"
          b"\t@cat said >&2; ( sleep 1; echo 'late' >&2 ) &\n")


def test_what_a_member_s_make_leaves_on_stderr_is_passed_on_as_written(
        holder, tmp_path):
    """What `run_make` says passing make's stderr on does: the bytes are
    passed on as they were written, never decoded, and a process a command
    leaves running holds the run until it closes stderr, its words passed
    on before the run ends. Reading only until make exited would end the
    run at once, and that process at its next write (SIGPIPE), unsaid."""
    if shutil.which("make") is None:
        pytest.skip("no make on PATH")
    with_members(holder, {"Leaves": LEAVES})
    said = b"caf" + bytes([0xE9]) + b"\n"
    (holder / "members" / "Leaves" / "said").write_bytes(said)

    result = made(holder, tmp_path, under_make=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == said + b"late\n"
    assert result.stdout.endswith(b"\nfamily bootstrap ok\n"), result.stdout


# --- line 3: `-f` where git rm --cached refuses ------------------------------

#: What lands in the checkout `git mv` moved, as w761 measured it on #828.
WORK = {"commit": lambda checkout, env: raw(
            checkout, env, "commit", "-q", "--allow-empty", "-m",
            "Work there"),
        "untracked": lambda checkout, env: (
            checkout / "scratch.txt").write_bytes(b"mine\n")}

#: The `STRAY` finding for `Members/<P>`, staged where HEAD records nothing.
STAGED_STRAY = (
    GITLINK_SAID + VARIANT + " Take it out of the index alone, which touches "
    "no file: HEAD records nothing there, so nothing of it is left to commit. "
    "The index stages it over a checkout, so the line takes -f: "
    + FORCED_SAID + ":\n    git rm --cached -f -- {path}")


@pytest.mark.parametrize("work", WORK.values(), ids=WORK)
def test_a_git_mv_staged_with_work_in_the_checkout_is_undone_as_printed(
        family, holder, offline, tmp_path, case_sensitive_disk, work):
    """LINE 3, reproduced on the gate's own state as the issue asks: `mkdir
    Members && git mv members/IRRS Members/IRRS`, staged, then a commit, or
    an untracked file, in the checkout it moved. The gate names the
    variant, a second path to the member's directory, and the row's own
    gitlink, whose removal is staged. Its `git rm --cached` refused there,
    exit 1, in every mode; it carries `-f` now and says what it does, and
    every line printed, typed as printed, puts the member back as HEAD has
    it, nothing left to commit. The gate then passes in every mode, and
    the checkout's commit is still in the member's store."""
    env = fetching(isolated(offline, tmp_path))
    commit = pinned(holder, MEMBER)
    (holder / "Members").mkdir()
    raw(holder, env, "mv", ROW, VARIANT_PATH)
    work(holder / VARIANT_PATH, env)
    checkout = raw(holder / VARIANT_PATH, env, "rev-parse",
                   "HEAD").stdout.decode("ascii").strip()
    stray = STAGED_STRAY.format(path=VARIANT_PATH, commit=commit,
                                row_path=ROW, project=MEMBER)

    for extra in ((), ("--pins",), ("--no-members",)):
        found = validate(holder, *extra)
        assert found.returncode == 1, (extra, found.stdout + found.stderr)
        assert codes(found) == ["member-gitlink-unnamed",
                                "gitmodules-path-unnamed",
                                "member-gitlink-removal-staged"], extra
        assert findings(found)[0] == stray, extra
    every = [line for finding in findings(validate(holder))
             for line in commands(finding)]
    head = raw(holder, env, "rev-parse", "--verify", "--quiet",
               f"HEAD:{VARIANT_PATH}", check=False)
    for line in every:
        type_line(holder, env, line)

    assert head.returncode != 0, "premise: HEAD records nothing there"
    assert raw(holder, env, "diff", "--cached", "--quiet",
               check=False).returncode == 0, "nothing left to commit"
    assert_passes_in_every_mode(holder, 2)
    assert raw(holder, env, "rev-parse", f"HEAD:{ROW}").stdout.decode(
        "ascii").strip() == commit
    assert kept(holder, env, holder / ".git" / "modules" / ROW, checkout), (
        "the checkout's commit is still in the member's store")


def kept(holder: Path, env: dict, store: Path, commit: str) -> bool:
    """Whether a member's store, the git directory `store`, holds
    `commit`."""
    return raw(holder, env, f"--git-dir={store}", f"--work-tree={holder}",
               "cat-file", "-e", commit, check=False).returncode == 0


def test_a_staged_second_path_with_nothing_on_disk_takes_no_f(
        holder, offline, tmp_path):
    """No misfire: a second path to MEMBER's directory, `Members/IRRS`,
    staged and not committed, and nothing on disk there. Git takes the
    gitlink out with no `-f`, so the line prints none; typed as printed,
    the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    commit = pinned(holder, MEMBER)
    stage_gitlink(holder, VARIANT_PATH, commit)

    (finding,) = findings(validate(holder, "--no-members"))

    assert finding == (
        GITLINK_SAID.format(path=VARIANT_PATH, commit=commit)
        + VARIANT.format(row_path=ROW, project=MEMBER)
        + " Take it out of the index alone, which touches no file, and "
        f"commit that:\n    git rm --cached -- {VARIANT_PATH}")
    type_line(holder, env, commands(finding)[0])
    assert_passes_in_every_mode(holder, 2)


def test_a_checkout_moved_on_at_the_variant_is_moved_with_f(
        family, holder, offline, tmp_path, case_sensitive_disk):
    """LINE 3, the wrong-case move's own `git rm`: MEMBER recorded only at
    `Members/IRRS`, by a committed `git submodule add`, then a commit in
    that checkout staged in the holder, and an untracked file left in it.
    The index stages the variant at a commit HEAD does not record there,
    over a checkout that holds a file git does not track, so the plain
    `git rm -r --cached` refused, exit 1, and the move stopped there. It
    carries `-f` and says why; typed as printed, with the commit, the
    section `git submodule add` wrote taken out as printed, and the
    checkout deleted by hand as the text says, the gate passes in every
    mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = pinned(holder, MEMBER)
    checkout = holder / VARIANT_PATH
    mounted_at_the_variant(family, holder, env, commit, "submodule")
    raw(checkout, env, "commit", "-q", "--allow-empty", "-m", "Work there")
    work = raw(checkout, env, "rev-parse", "HEAD").stdout.decode().strip()
    raw(holder, env, "add", "--", VARIANT_PATH)
    (checkout / "scratch.txt").write_bytes(b"mine\n")

    refused = validate(holder)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    lines = refused.stderr.splitlines()
    assert lines == variant_refused(ROW, commit, [VARIANT_PATH],
                                    {VARIANT_PATH: work},
                                    forced=(VARIANT_PATH,))
    moved_as_printed(holder, env, lines, [VARIANT_PATH])
    left = validate(holder)
    assert codes(left) == ["gitmodules-path-unnamed"], left.stderr
    take_out_as_printed(holder, findings(left)[0])
    rmtree(checkout)
    assert_passes_in_every_mode(holder, 2)
    store = holder / ".git" / "modules" / "Members" / MEMBER
    assert kept(holder, env, store, work), "the commit is kept"


# --- line 4: what the guarded `mv` moves -------------------------------------

def link_to_the_row(holder: Path, tmp_path: Path) -> Path | None:
    """A link to the row's own directory. Returns what a link there
    points at, which must be there after the move."""
    (holder / "Members").mkdir()
    os.symlink(f"../{ROW}", holder / VARIANT_PATH, target_is_directory=True)
    return holder / ROW


def link_to_a_clone(holder: Path, tmp_path: Path) -> Path | None:
    """A link to a clone beside the holder, a directory holding a `.git`
    file."""
    clone = tmp_path / f"{MEMBER}-clone"
    clone.mkdir()
    (clone / ".git").write_bytes(b"gitdir: ../nowhere\n")
    (holder / "Members").mkdir()
    os.symlink(str(clone), holder / VARIANT_PATH, target_is_directory=True)
    return clone


def dangling_link(holder: Path, tmp_path: Path) -> Path | None:
    (holder / "Members").mkdir()
    os.symlink("nowhere", holder / VARIANT_PATH)
    return None


def nothing(holder: Path, tmp_path: Path) -> Path | None:
    """Nothing at the variant, as a fresh clone of a holder whose index
    records only the variant leaves it after the move."""
    return None


LAYOUTS = {"link-to-the-row": link_to_the_row,
           "link-to-a-clone": link_to_a_clone,
           "dangling-link": dangling_link,
           "nothing": nothing}


@pytest.mark.parametrize("shell", ["sh", "bash"])
@pytest.mark.parametrize("layout", LAYOUTS.values(), ids=LAYOUTS)
def test_a_link_or_nothing_at_the_variant_is_typed_as_printed(
        family, holder, offline, tmp_path, case_sensitive_disk, layout,
        shell):
    """LINE 4 and comment 6237599648, in w840's state: MEMBER's gitlink
    held only at `Members/IRRS`, committed, its checkout at its row's path.
    After the move's two lines and their commit, what is at the variant,
    then the guarded `mv` typed as printed, in dash (this host's `sh`) and
    in bash. A link there, to the row's own directory, to a clone, or to
    nowhere, is moved, the link and never what it points at: the guard
    kept the first two, reading through them, and `family.py add` then
    refused the link, on disk and untracked. Nothing there moves nothing
    and exits 0, where the bare `mv` failed `cannot stat`, exit 1. The gate
    then passes in every mode, and SPARE is added."""
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} on PATH")
    env = fetching(isolated(offline, tmp_path))
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    lines = refused_at(holder, commit, [VARIANT_PATH])
    moved_as_printed(holder, env, lines, [VARIANT_PATH])
    try:
        pointed = layout(holder, tmp_path)
    except OSError as exc:
        pytest.skip(f"no symbolic link here: {exc}")
    link = os.path.islink(holder / VARIANT_PATH)
    target = os.readlink(holder / VARIANT_PATH) if link else None
    (move,) = GUARDED_MOVE.findall(lines[1])

    typed = subprocess.run([shell, "-c", move], cwd=str(holder),
                           capture_output=True, check=False)

    assert typed.returncode == 0, typed.stderr
    assert not os.path.lexists(holder / VARIANT_PATH)
    moved = tmp_path / MOVED_TO
    assert os.path.islink(moved) is link
    if link:
        assert os.readlink(moved) == target
    assert pointed is None or pointed.is_dir()
    assert (holder / ROW / "project.yaml").is_file()
    assert_passes_in_every_mode(holder, 2)
    added = run_script(FAMILY, *verb_args("add", holder, family), env=env)
    assert added.returncode == 0, added.stdout + added.stderr
    assert_passes_in_every_mode(holder, 3)


# --- comment (b): the work tree's .gitmodules put back, once ---------------

def put_back_first(finding: str, how: str) -> str:
    """`finding` with the line that puts the work tree's `.gitmodules`
    back from where git reads it (`GONE`), as its first command."""
    whose, line = GONE[how]
    said = "then stage and commit .gitmodules:\n"
    assert finding.count(said) == 1, finding
    return finding.replace(
        said, "then stage and commit .gitmodules, which is gone from the "
        f"work tree: the first line puts back {whose}, so that every other "
        f"section stays:\n    {line}\n")


def typed_and_committed(root: Path, env: dict, result) -> None:
    """Every command every finding prints, typed as printed, then
    `.gitmodules` staged and committed, as each says."""
    for finding in findings(result):
        for line in commands(finding):
            type_line(root, env, line)
    staged_and_committed(root, env, "Written back as printed")


@pytest.mark.parametrize("how", GONE)
def test_a_section_absent_from_head_is_written_into_the_file_put_back(
        holder, offline, tmp_path, how):
    """COMMENT (b): OTHER's section taken out of HEAD's `.gitmodules`, and
    the work tree's file gone, deleted or its deletion staged. The finding
    printed the `git config -f` lines alone, which made a file of OTHER's
    section, so staged and committed HEAD lost MEMBER's: a second round.
    The line that puts the file back from where git reads it comes first
    now, in every mode; typed as printed and committed, HEAD keeps
    MEMBER's section, and the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    committed_gitmodules(holder, env, section_taken_out(data, OTHER))
    gone(holder, env, how)
    expected = put_back_first(
        absent(OTHER, pinned(holder, OTHER), held=True), how)

    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        assert findings(result) == [expected], extra

    typed_and_committed(holder, env, validate(holder))
    assert f'[submodule "{ROW}"]'.encode() in raw(
        holder, env, "show", "HEAD:.gitmodules").stdout
    assert_passes_in_every_mode(holder, 2)


def section_taken_out(data: bytes, project: str) -> bytes:
    """`.gitmodules` bytes with `project`'s section taken out by hand."""
    section = re.compile(rb'\[submodule "members/' + project.encode()
                         + rb'"\]\n(?:\t[^\n]*\n)*')
    return section.sub(b"", data)


#: `(the edit to HEAD's .gitmodules, each finding as `(url-less?, project)`
#: in the order printed)`: two findings that each write the file.
TWO_WRITE = {
    "two-url-less": (lambda data: without_url(without_url(data, MEMBER),
                                              OTHER),
                     ((True, MEMBER), (True, OTHER))),
    "absent-then-url-less": (lambda data: without_url(
        section_taken_out(data, MEMBER), OTHER),
        ((False, MEMBER), (True, OTHER))),
    "url-less-then-absent": (lambda data: section_taken_out(
        without_url(data, MEMBER), OTHER),
        ((True, MEMBER), (False, OTHER))),
}


@pytest.mark.parametrize("edit, made", TWO_WRITE.values(), ids=TWO_WRITE)
def test_two_findings_that_write_the_file_put_it_back_once(
        holder, offline, tmp_path, edit, made):
    """COMMENT (b)'s ORDER: two findings that write `.gitmodules`, with the
    work tree's gone. Each `member-gitmodules-url-absent` put the file back
    first, so the second put it back over the url the first had written,
    and a `member-gitmodules-absent` before one had its section put back
    over the same way: a second round. Only the first puts it back now;
    typed as printed and committed, the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    committed_gitmodules(holder, env, edit(data))
    gone(holder, env, "deleted")
    expected = [
        (URL_ABSENT.replace(OTHER, project).format(
            commit=pinned(holder, project)) if url_less
         else absent(project, pinned(holder, project), held=True))
        for url_less, project in made]
    expected[0] = put_back_first(expected[0], "deleted")

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == expected
    typed_and_committed(holder, env, result)
    assert_passes_in_every_mode(holder, 2)


def test_a_value_finding_that_put_head_s_back_is_not_put_back_over(
        holder, offline, tmp_path):
    """No second put back after `gitmodules-value-refused`'s: MEMBER's
    section given `update = None`, OTHER's taken out, committed, and the
    work tree's file deleted. The value's finding puts HEAD's back first
    (#768) and takes the key out; OTHER's `member-gitmodules-absent` then
    writes into that file, and puts nothing back over the key it took
    out. Typed as printed and committed, the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    line = f"\tpath = members/{MEMBER}\n".encode()
    assert data.count(line) == 1, data
    committed_gitmodules(holder, env, section_taken_out(
        data.replace(line, line + b"\tupdate = None\n"), OTHER))
    gone(holder, env, "deleted")

    result = validate(holder, "--no-members")

    assert result.returncode == 1, result.stdout + result.stderr
    assert codes(result) == ["gitmodules-value-refused",
                             "member-gitmodules-absent"]
    assert commands(findings(result)[0])[0] == (
        "git checkout HEAD -- .gitmodules")
    assert findings(result)[1] == absent(OTHER, pinned(holder, OTHER),
                                         held=True)
    typed_and_committed(holder, env, result)
    assert_passes_in_every_mode(holder, 2)


# --- the guard's text, typed in both shells on every layout ----------------

#: `(what is at the variant, whether the guard moves it)` for the guard
#: alone, in a scratch tree: the issue's seven layouts.
GUARD_LAYOUTS = {
    "nothing": (lambda root: None, False),
    "dangling-link": (lambda root: os.symlink(
        "nowhere", root / VARIANT_PATH), True),
    "link-to-the-row": (lambda root: os.symlink(
        f"../{ROW}", root / VARIANT_PATH), True),
    "link-to-a-checkout": (lambda root: os.symlink(
        "../../clone", root / VARIANT_PATH), True),
    "Members-a-link-to-members": (None, False),
    "a-directory-apart": (lambda root: (root / VARIANT_PATH).mkdir(), True),
    "a-checkout-apart": (lambda root: (
        (root / VARIANT_PATH).mkdir(),
        (root / VARIANT_PATH / ".git").write_bytes(b"gitdir: x\n")), False),
}


@pytest.fixture(scope="module")
def guarded_move():
    """The gate's own `_guarded_move`."""
    return loaded("validate-family.py",
                  "validate_family_holder_texts")._guarded_move


@pytest.mark.parametrize("shell", ["sh", "bash"])
@pytest.mark.parametrize("place, moves", GUARD_LAYOUTS.values(),
                         ids=GUARD_LAYOUTS)
def test_the_guard_moves_a_link_always_and_nothing_where_nothing_is(
        tmp_path, case_sensitive_disk, guarded_move, shell, place, moves):
    """The guarded `mv` the variant refusal prints, on its own, on the
    issue's seven layouts, in dash and in bash: exit 0 on each, a link
    always moved, the link itself; nothing there, `Members` itself a link
    to `members` (how `tests/test_validate_family_remedies_typed.py`
    emulates a folding disk), and a checkout apart kept."""
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} on PATH")
    root = tmp_path / "holder"
    (root / ROW).mkdir(parents=True)
    (root / ROW / ".git").write_bytes(b"gitdir: x\n")
    (tmp_path / "clone").mkdir()
    (tmp_path / "clone" / ".git").write_bytes(b"gitdir: y\n")
    (move,) = GUARDED_MOVE.findall(guarded_move(VARIANT_PATH, ROW))
    try:
        if place is None:
            os.symlink("members", root / "Members", target_is_directory=True)
        else:
            (root / "Members").mkdir()
            place(root)
    except OSError as exc:
        pytest.skip(f"no symbolic link here: {exc}")
    there = os.path.lexists(root / VARIANT_PATH)

    typed = subprocess.run([shell, "-c", move], cwd=str(root),
                           capture_output=True, check=False)

    assert typed.returncode == 0, typed.stderr
    assert os.path.lexists(tmp_path / MOVED_TO) is moves
    assert os.path.lexists(root / VARIANT_PATH) is (there and not moves)
    assert (root / ROW / ".git").is_file()
