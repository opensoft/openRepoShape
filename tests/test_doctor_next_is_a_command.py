# SPDX-License-Identifier: Apache-2.0
"""A doctor NEXT is the command and only the command (#277).

THE DEFECT. Sixteen of the doctor's NEXT builders ended the command with
`   # <comment>`, and one printed prose in the command's place; doctor A
(#276) and doctor B (#278, #298) wrote five more tails while this was open.
A tail was harmless in exactly the shells that read `#` as a comment where
a word starts -- `sh -c`, bash, `zsh -c` -- which is how every test and
every agent tool call had read one. An INTERACTIVE zsh without
`interactivecomments` -- zsh's default, and macOS's login shell, the one a
person pastes into -- reads `#` as a word. Pasted there, the manifest NEXT
handed `# read its output in full` to the validator as arguments, ran `it
names what it refused` as a second command and exited 127; the `legs` and
`members` NEXTs ran the `make bootstrap` their comments put in backticks,
in whatever directory the person was standing in.

THE FIX IS A FIELD, NOT A SPELLING. Each sentence moved, verbatim, to the
row's `why` -- `"why"` in `--json`, a `WHY` line under `NEXT` in the table,
`Why:` after `Remediation:` -- and `next` is the bare command. So this file
holds three things, and the code before #277 fails each of them:

  * a PROPERTY over one fixture per converted builder and branch: the NEXT
    has no shell comment (`shlex` reads it the same with and without
    comments), no backtick, no `$(` that `sh` would run and, on POSIX, none
    of `;`, `&`, `|`, `(`, `)` outside a quotation (PowerShell's `$env:`
    line ends its assignment with a `;`, by design);
  * a PASTE into `zsh -f -i` through a pty, as a person pastes: the manifest
    NEXT is the validator's own finding and exit, and the legs NEXT, pasted
    in a directory whose Makefile's `bootstrap` target leaves a marker,
    leaves none -- each beside a line the doctor printed before #277, pasted
    the same way, so the harness is shown to see the defect it guards;
  * an AST GUARD over `shape-doctor.py`: no string that is not a docstring
    holds a tail -- two or more blanks, or a tab, then `#` and a blank --
    except `placement_plan_leg`'s YAML comment lines and the one `placement
    plan written to` line in `report`, where that text is not a NEXT. It is
    what turns a tail landed later, by any lane, into a red test.

The fixtures are `tests/test_shape_doctor.py`'s, imported rather than rebuilt
(the precedent is `tests/test_family_add_refusals.py`); importing a fixture
gives this module its own instance of it.
"""

from __future__ import annotations

import ast
import os
import re
import select
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, rmtree
#: The lane a lane's run sets, from the file that owns that rule.
from test_commit_trailers import LANE
#: The doctor's own fixtures and helpers, from the module that owns them. A
#: project or a holder made any other way would be a different project.
from test_shape_doctor import (  # noqa: F401
    BREAKAGES, DOCTOR, DRIFT_TARGET, FAMILY_MEMBER, FAMILY_NAME,
    UPSTREAM_TARGET, behind_row, break_manifest, doctor, doctor_module,
    holder, project, red_root, rows_of, scaffolded_here, stage, standard,
    standard_ahead, standard_of_another_history,
)
#: Doctor A's ways to make a leg or a member red (#276), from the module that
#: owns them: the `legs` and `members` lines are A's, so the roots are too.
from test_doctor_legs_members_next import (
    commit_in, holder_copy, holder_without, make_gitlink_moved,
    make_member_gitlink_mismatch, member_unbootstrapped,
)
#: Doctor B's crashing validator and unloaded manifest (#278, #298), from the
#: module that owns them.
from test_doctor_validator_rows import crashing, unloaded


# --- making each converted row print its NEXT -------------------------------

def a_short_standard(tmp_path: Path, name: str) -> Path:
    """A directory standing in for a standard that lacks what a row needs:
    what the doctor's own checkout cannot be made to lack in a test."""
    short = tmp_path / name
    short.mkdir()
    return short


def _validator_neither_readable(standard, project, holder, tmp_path):
    # Neither the root's copy nor the standard's is there: a validator name
    # nothing carries, asked of the builder itself.
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    return module.validator_row(
        ctx, "manifest", "manifest", "scripts/validate-nothing.py",
        "templates/assembly-root/scripts/validate-nothing.py",
        ["--root", str(ctx.root)]).as_dict()


def _validator_own_copy(standard, project, holder, tmp_path):
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    return rows_of(doctor(standard, root, "--json"))["manifest"]


def _validator_template_copy(standard, project, holder, tmp_path):
    root = red_root("pins", project, holder, tmp_path)
    return rows_of(doctor(standard, root, "--json"))["pins"]


def _unloaded_manifest(standard, project, holder, tmp_path):
    edit, code = BREAKAGES["tab-indent"]
    break_manifest(project.resolve() / "project.yaml", edit, code)
    return rows_of(doctor(standard, project, "--json"))["manifest"]


def _unloaded_manifest_neither_readable(standard, project, holder, tmp_path):
    # The branch that hands on `validator_row`'s NEXT -- and now its `why`.
    edit, code = BREAKAGES["tab-indent"]
    break_manifest(project.resolve() / "project.yaml", edit, code)
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    assert ctx.manifest_refusal is not None, "the manifest still loads"
    return module.unloaded_manifest_row(
        ctx, "manifest", "manifest", "scripts/validate-nothing.py",
        "templates/assembly-root/scripts/validate-nothing.py").as_dict()


def _shape_currency_cannot_answer(standard, project, holder, tmp_path):
    stranger = standard_of_another_history(standard, tmp_path)
    return rows_of(doctor(stranger, project, "--json"))["shape-currency"]


def _shape_currency_behind_pin_only(standard, project, holder, tmp_path):
    # Run inside a lane, so the `apply` grows its trailer -- which is `why`'s
    # to carry now, and never `next`'s.
    row = behind_row(standard_ahead(standard, tmp_path), project, LANE)
    assert row["detail"].get("behind_pin_only") is True, row
    assert row["why"].endswith(f" --trailer 'Lane: {LANE}'"), row["why"]
    return row


def _shape_currency_moved(standard, project, holder, tmp_path):
    ahead = standard_ahead(standard, tmp_path, UPSTREAM_TARGET,
                           "\n# an upstream fix, after this project was cut\n",
                           "An upstream fix to a copied file")
    edited = project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8")
                      + "\n# a local edit nobody carried upstream\n",
                      encoding="utf-8")
    row = behind_row(ahead, project, LANE)
    # The `apply` -- its `--accept-local` and the lane's trailer with it --
    # is the row's `why`, and nothing of it is on the NEXT.
    assert f"--accept-local {DRIFT_TARGET}" in row["why"], row["why"]
    assert row["why"].endswith(f" --trailer 'Lane: {LANE}'"), row["why"]
    for moved in ("apply", "--accept-local", "--trailer"):
        assert moved not in row["next"], (moved, row["next"])
    return row


def _legs(standard, project, holder, tmp_path):
    # A leg committed past its pin where the gitlink IS the pin: doctor A's
    # git line, which a checkout cures (#276).
    commit_in(project / "spec")
    return rows_of(doctor(standard, project, "--json"))["legs"]


def _legs_lockstep(standard, project, holder, tmp_path):
    # A gitlink that is not the pin, which no checkout cures: doctor A's
    # lockstep line, the root's own `validate-pins.py` (`lockstep_next`).
    make_gitlink_moved(project)
    return rows_of(doctor(standard, project, "--json"))["legs"]


def _leg_shape_files_partly_copyable(standard, project, holder, tmp_path):
    (project / "spec" / "AGENTS.md").unlink()
    (project / "spec" / "CLAUDE.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["leg-shape-files"]


def _leg_shape_files_all_rendered(standard, project, holder, tmp_path):
    # The NEXT that WAS prose, with a command in backticks inside it.
    (project / "spec" / "AGENTS.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    # The `--help` the sentence names, now the command itself. Its path may
    # be quoted (a Windows temporary directory is), so read as words.
    words = row["next"].split()
    assert words[-1] == "--help" and "scaffold-project.py" in words[-2], \
        row["next"]
    return row


def _placement_policy_missing(standard, project, holder, tmp_path):
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    ctx.shape = a_short_standard(tmp_path, "a-standard-without-adopt")
    adopt, _policy, row = module.placement_policy(
        ctx, ctx.shape / "contracts" / "path-classification.yaml")
    assert adopt is None and row is not None, row
    return row.as_dict()


def _placement_plan(standard, project, holder, tmp_path):
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    return rows_of(doctor(standard, project, "--json"))["placement"]


def _agent_files_pinned(standard, project, holder, tmp_path):
    (project / "AGENTS-shape.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["agent-files"]


def _agent_files_unpinned(standard, project, holder, tmp_path):
    # No `contracts/shape-pin.yaml` names `AGENTS-shape.md`: the branch
    # that sends the reader to `update-shape.py check` and `apply --add`.
    module = doctor_module(standard)
    here = tmp_path / "unpinned"
    here.mkdir()
    for name in ("AGENTS.md", "CLAUDE.md"):
        (here / name).write_text("an agent file\n", encoding="utf-8")
    return module.check_agent_files(module.Context(here)).as_dict()


def _agent_files_rendered(standard, project, holder, tmp_path):
    (project / "CLAUDE.md").unlink()
    return rows_of(doctor(standard, project, "--json"))["agent-files"]


def _members(standard, project, holder, tmp_path):
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    mount = root / "members" / FAMILY_MEMBER
    rmtree(mount)
    mount.mkdir()
    return rows_of(doctor(standard, root, "--json"))["members"]


def _members_git_line(standard, project, holder, tmp_path):
    # A holder whose own bootstrap cannot run: doctor A's plain git line.
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    return rows_of(doctor(standard, root, "--json"))["members"]


def _members_lockstep(standard, project, holder, tmp_path):
    # A member whose gitlink is not its pin: the family gate, through the
    # same `lockstep_next` as the `legs` row.
    root = holder_copy(holder, tmp_path)
    make_member_gitlink_mismatch(root)
    return rows_of(doctor(standard, root, "--json"))["members"]


def _validator_crashed(standard, project, holder, tmp_path):
    # The root's own `validate-pins.py` raising: doctor B's crash line (#278).
    here, root, row_id, _own = crashing("own-pins", standard, project, holder,
                                        tmp_path)
    return rows_of(doctor(here, root, "--json"))[row_id]


def _unloaded_manifest_restore(standard, project, holder, tmp_path):
    # A manifest that does not load and a gate whose `repo_shape.py` is gone
    # from the tree, which HEAD still holds: doctor B's restore line (#298).
    root, row_id, _refusal = unloaded("project", project, holder, tmp_path,
                                      "tree")
    return rows_of(doctor(standard, root, "--json"))[row_id]


def _machine(standard, project, holder, tmp_path):
    # A preflight that is not ready, on every host: whether the real one is
    # depends on the machine, and the row's NEXT only exists when it is not.
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    ctx.shape = a_short_standard(tmp_path, "a-standard-not-ready")
    (ctx.shape / "setup-project.py").write_text(
        "import sys\nprint('[!!] a prerequisite is missing')\nsys.exit(1)\n",
        encoding="utf-8")
    return module.check_machine(ctx).as_dict()


def _way_in(standard, project, holder, tmp_path):
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    return rows_of(doctor(standard, here, "--json"))["way-in"]


#: One fixture per NEXT #277 converted, by the builder and branch it reaches,
#: and how the sentence that used to follow `   # ` on it now opens -- moved
#: VERBATIM, less the `#`, so these are the words main and doctors A and B
#: printed. Not `check_manifest_kinds`, whose prose NEXTs are lane 2's
#: (#291), and not a `Refusal.remediation` printed as one.
CASES = {
    "validator_row-neither-readable": (
        _validator_neither_readable,
        "from a complete checkout of the standard; this one is missing that "
        "file"),
    "validator_row-own-copy": (
        _validator_own_copy,
        "read its output in full; it names what it refused"),
    "validator_row-template-copy": (
        _validator_template_copy,
        "read its output in full; it names what it refused"),
    "unloaded_manifest_row": (
        _unloaded_manifest, "the file to fix is "),
    "unloaded_manifest_row-neither-readable": (
        _unloaded_manifest_neither_readable,
        "from a complete checkout of the standard; this one is missing that "
        "file"),
    "check_shape_currency-cannot-answer": (
        _shape_currency_cannot_answer,
        "this checkout of the standard does not carry the commit the pin "
        "names; fetch it, or run the doctor from a clone that has it"),
    "check_shape_currency-pin-alone-behind": (
        _shape_currency_behind_pin_only, "then apply --at "),
    "check_shape_currency-copies-moved": (
        _shape_currency_moved, "then apply --at "),
    "validator_row-crashed": (
        _validator_crashed,
        "read its output in full, it shows where the validator stopped"),
    "unloaded_manifest_row-restore": (
        _unloaded_manifest_restore,
        "it puts back the scripts/repo_shape.py HEAD holds, the copy this "
        "project committed and scripts/validate-manifest.py imports, where "
        "update-shape.py apply would copy a newer one"),
    "check_legs": (
        _legs,
        "checks each leg out at the commit this repository records for it, "
        "and fetches a mount that is empty"),
    "lockstep_next-legs": (
        _legs_lockstep,
        "no submodule update cures a leg whose gitlink or pin is missing or "
        "disagrees, or a mount git cannot read a HEAD in. validate-pins.py "
        "prints what it finds and names the repair where it has one"),
    "missing_shape_file_fix-partly-copyable": (
        _leg_shape_files_partly_copyable,
        "and the rest are RENDERED per project (placeholders): "
        "scaffold-project.py writes those, and copying a template verbatim "
        "would not"),
    "missing_shape_file_fix-all-rendered": (
        _leg_shape_files_all_rendered,
        "the missing file(s) are RENDERED per project from "
        "templates/<role>-root/ -- `"),
    "placement_policy": (
        _placement_policy_missing,
        "from a COMPLETE checkout of the standard; this one is short "
        "adopt-project.py"),
    "check_placement": (
        _placement_plan,
        "writes the paths above as a plan to resolve by hand. Moving one is a "
        "pull request on each leg and a pin bump in the root, so this "
        "command makes neither"),
    "check_agent_files-pinned": (
        _agent_files_pinned,
        "the pin has a `files:` row for it, so it was deleted rather than "
        "never copied; restore it from this repository's own history, then "),
    "check_agent_files-unpinned": (
        _agent_files_unpinned,
        "no pin row names it, so it is reported upstream-added and taken, on "
        "the human's word, with `apply --add AGENTS-shape.md`"),
    "check_agent_files-rendered": (
        _agent_files_rendered,
        "CLAUDE.md is RENDERED per project, not copied; write it, or take a "
        "rendered one from a scaffolded root"),
    "members_verdict": (
        _members,
        "what `make bootstrap` runs in a holder: it fetches every member at "
        "its pin and leaves it detached there"),
    "members_verdict-git-line": (
        _members_git_line,
        "checks each member out at the commit this repository records for "
        "it, and fetches a mount that is empty"),
    "lockstep_next-members": (
        _members_lockstep,
        "no submodule update cures a member whose gitlink or pin is missing "
        "or disagrees, or a mount git cannot read a HEAD in. "
        "validate-family.py prints what it finds and names the repair where "
        "it has one"),
    "check_machine": (
        _machine,
        "it names each missing prerequisite and offers to install it, on a "
        "typed yes"),
    "check_the_way_in": (
        _way_in, "without --yes; it asks"),
}


def unquoted_operators(command: str) -> list[str]:
    """The control operators `sh` would act on in `command`: `;`, `&`, `|`,
    `(`, `)`, `<`, `>`, outside any quotation.

    `commenters` IS EMPTY ON PURPOSE. To an interactive zsh a `#` is a word,
    so an operator after one is live there, and a reader that stopped at the
    `#` the way `sh` does would wave through the very line #277 is about.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [token for token in lexer
            if token and set(token) <= set("();<>|&")]


#: The operators a NEXT must not carry outside a quotation on POSIX: a list
#: (`;`, `&`, `&&`, `|`, `||`) runs a second command, a parenthesis opens a
#: subshell -- and an unquoted `$(` is read as `$` then the operator `(`,
#: so it is one of them. `<` and `>` are not here: the way-in row's
#: `<your-org>` is a placeholder the reader replaces, unquoted on purpose.
LIVE_OPERATORS = ";&|()"


def outside_single_quotes(command: str) -> str:
    """`command` less what `sh` reads literally: single-quoted spans and the
    character after a backslash. A `$(` left in it is run -- inside double
    quotes as much as outside them -- which `shlex`'s tokens cannot show:
    they read `"$(make)"` as the one word `$(make)`, exactly as they read
    the quoted path `'$(make)'`, which runs nothing."""
    kept, single, double, at = [], False, False, 0
    while at < len(command):
        char = command[at]
        if single:
            single = char != "'"
        elif char == "\\":
            at += 1
        elif char == "'" and not double:
            single = True
        else:
            double = double != (char == '"')
            kept.append(char)
        at += 1
    return "".join(kept)


def test_the_operator_readers_see_what_sh_runs_and_not_a_quoted_path():
    """The property below is only as good as these two readers, so each is
    shown to find an operator `sh` acts on, and to pass one that sits in a
    quoted path."""
    assert set("".join(unquoted_operators("a; b && c | d (e)"))) == set(
        LIVE_OPERATORS)
    assert unquoted_operators("git -C '/w/a;b&c|d (e)' status") == []
    assert "(" in unquoted_operators("echo $(make)")
    assert "$(" in outside_single_quotes('echo "$(make)"')
    assert "$(" not in outside_single_quotes("echo '$(make)'")
    assert "$(" not in outside_single_quotes("echo \\$(make)")
    assert "$(" not in outside_single_quotes("echo 'it'\"'\"'s $(here)'")


@pytest.mark.parametrize("case", list(CASES))
def test_every_converted_next_is_a_command_and_nothing_else(
        standard, project, holder, tmp_path, case):
    """The property, over one red fixture per converted builder and branch.

    NO SHELL COMMENT: `shlex` reads the line the same with comments on and
    off, so nothing in it is a `#` where a word starts. NO BACKTICK, AND NO
    `$(` THAT RUNS: command substitution in sh, bash and zsh alike. On
    POSIX, NO `;`, `&`, `|`, `(` OR `)` OUTSIDE A QUOTATION, read from
    `shlex`'s tokens so that a quoted path holding one is a path: what
    followed a `;` in a tail was the second command an interactive zsh ran,
    and the others start one too. AND THE SENTENCE IS NOT LOST: it is the
    row's `why`, opening with the words printed after `   # ` before #277.
    """
    build, opens = CASES[case]
    row = build(standard, project, holder, tmp_path)
    command, why = row["next"], row["why"]
    assert command, (case, row)
    assert why and why.startswith(opens), (case, opens, why)
    assert shlex.split(command, comments=True) == shlex.split(command), (
        case, command)
    assert "`" not in command, (case, command)
    if os.name != "nt":
        live = "".join(unquoted_operators(command))
        for operator in LIVE_OPERATORS:
            assert operator not in live, (case, operator, command)
        assert "$(" not in outside_single_quotes(command), (case, command)
    assert "   # " not in command, (case, command)


# --- pasted, as a person pastes ---------------------------------------------

#: The line the paste ends with, and what it prints: the status of the line
#: before it. `$?` is never expanded in the echo of what was typed, so only
#: the shell's own answer matches.
PASTED_EXIT = re.compile(r"pasted-exit=(\d+)")


def paste_into_zsh(line: str, cwd: Path, timeout: float = 120.0) -> tuple:
    """`(status, transcript)`: `line` typed into `zsh -f -i` through a pty.

    `-f` reads no startup file of the person's, so `interactivecomments` is
    zsh's default, OFF, which is the shell #277 is about; `TERM=dumb` keeps
    the line editor quiet. The line is typed whole, then a second line that
    prints its status; `exit` is typed only once that answer is read, so a
    platform that drops a pty's unread output when the shell ends cannot
    lose it. `status` is None when no answer came -- a line that left the
    shell inside an open quotation, say -- and the transcript says why.

    The environment is the test's own, less `PYTHONPATH` (a NEXT carries
    what it needs, #238) and with file-protocol git for the one child that
    may clone from the suite's local remotes -- per process, never
    `GIT_ALLOW_PROTOCOL` (see `tests/conftest.py`).
    """
    import pty  # POSIX only: `tty` beneath it needs `termios`
    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env.update({"TERM": "dumb", "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "protocol.file.allow",
                "GIT_CONFIG_VALUE_0": "always"})
    master, slave = pty.openpty()
    try:
        shell = subprocess.Popen(["zsh", "-f", "-i"], stdin=slave,
                                 stdout=slave, stderr=slave, cwd=str(cwd),
                                 env=env, start_new_session=True)
    finally:
        os.close(slave)
    heard = bytearray()
    deadline = time.monotonic() + timeout

    def listen(until=None) -> re.Match | None:
        while time.monotonic() < deadline:
            if until is not None:
                found = until.search(heard.decode("utf-8", "replace"))
                if found:
                    return found
            ready, _, _ = select.select([master], [], [], 0.5)
            if not ready:
                if shell.poll() is not None:
                    return None
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:  # EIO: Linux's EOF on a pty whose shell is gone
                return None
            if not chunk:
                return None
            heard.extend(chunk)
        return None

    try:
        os.write(master, line.encode("utf-8") + b"\n"
                 + b"print -r -- pasted-exit=$?\n")
        answered = listen(PASTED_EXIT)
        try:
            os.write(master, b"exit\n")
        except OSError:
            pass
        deadline = min(deadline, time.monotonic() + 10)
        listen()
    finally:
        if shell.poll() is None:
            shell.kill()
        shell.wait(timeout=30)
        os.close(master)
    transcript = heard.decode("utf-8", "replace")
    return (int(answered.group(1)) if answered else None), transcript


#: What a pasted line must not have made the shell say: a word the shell
#: tried to run (the text after a `;`), or an argument the command refused
#: (the comment's own words, handed to it).
MISREAD = ("command not found", "unrecognized arguments")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_the_manifest_next_pasted_into_an_interactive_zsh_is_the_validator(
        standard, project, holder, tmp_path):
    """The validator's own finding, with the validator's own exit.

    THE LINE MAIN PRINTED IS PASTED TOO, and is the defect: its validator
    refuses the comment's words as arguments, `it names what it refused`
    after the `;` is a command that does not exist, and the status the person
    sees is that one's, 127. That half is what shows this harness reads `#`
    the way the person's shell does; without it the first half could pass
    in a shell that skipped the comment.
    """
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    row = rows_of(doctor(standard, root, "--json"))["manifest"]
    assert row["status"] == "FINDING" and row["detail"]["own_copy"], row
    here = tmp_path / "standing-anywhere"
    here.mkdir()

    status, transcript = paste_into_zsh(row["next"], here)
    assert status == row["detail"]["exit"], transcript
    assert "FINDING manifest-topic" in transcript, transcript
    for misread in MISREAD:
        assert misread not in transcript, (misread, transcript)

    status, transcript = paste_into_zsh(f"{row['next']}   # {row['why']}",
                                        here)
    assert status == 127, transcript
    assert "command not found: it" in transcript, transcript


def legs_line_before_277(standard: Path, root: Path) -> str:
    """The `legs` NEXT the doctor printed for `root` before #276 and #277
    (`check_legs` at 3ae0109, the line #277 was filed against): the root's
    own bootstrap, and a tail holding `make bootstrap` in backticks.

    SPELLED HERE BECAUSE NOTHING PRINTS IT ANY MORE. #276 made the `legs`
    NEXT a git line whose sentence carries no backtick, so the line it
    prints today, with its `why` put back after `   # `, runs no `make`
    pasted, and could not show that this harness runs a backtick at all.
    """
    module = doctor_module(standard)
    return (f"{module.PYTHON} "
            f"{module.quote_arg(root / 'scripts' / 'bootstrap.py')} "
            f"--root {module.quote_arg(root)}   # what `make bootstrap` "
            "runs: it puts every leg on its tracking branch AT the pinned "
            "commit")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("zsh") is None or shutil.which("make") is None,
                    reason="needs zsh and make")
def test_the_legs_next_pasted_into_an_interactive_zsh_runs_no_make(
        standard, project, tmp_path):
    """Pasted where a Makefile's `bootstrap` target leaves a marker: none.

    The `legs` comment said "what `make bootstrap` runs" -- a pair of
    backticks, which an interactive zsh runs as command substitution in the
    directory the person is standing in, before the command it was pasted
    with. That line (`legs_line_before_277`) is pasted second, in the same
    directory, and leaves the marker, so the first half cannot be passing
    because the harness never runs a backtick.
    """
    commit_in(project / "spec")
    row = rows_of(doctor(standard, project, "--json"))["legs"]
    assert row["status"] == "FINDING", row
    here = tmp_path / "standing-here"
    here.mkdir()
    (here / "Makefile").write_text("bootstrap:\n\ttouch MARKER\n",
                                   encoding="utf-8")
    marker = here / "MARKER"

    status, transcript = paste_into_zsh(row["next"], here)
    assert status is not None, transcript
    assert not marker.exists(), transcript
    for misread in MISREAD:
        assert misread not in transcript, (misread, transcript)

    paste_into_zsh(legs_line_before_277(standard, project.resolve()), here)
    assert marker.exists(), (
        "the line the doctor printed before #277 must run `make bootstrap` "
        "here, or this test is proving nothing about the backticks")


# --- the report says the sentence, off the command's line -------------------

def test_the_table_prints_why_on_its_own_line_under_next(standard, project,
                                                        holder, tmp_path):
    """`NEXT` is the command as `--json` has it, and `WHY` is the line under
    it, with the sentence `--json` carries as `why`. Two rows at once, so the
    pairing is shown to be per row, and every row of the run carries the key.
    """
    root = red_root("manifest", project, holder, tmp_path, keep_own=True)
    commit_in(root / "spec")
    rows = rows_of(doctor(standard, root, "--json"))
    for name, row in rows.items():
        assert "why" in row, (name, row)
    explained = [row for row in rows.values() if row["next"] and row["why"]]
    assert {"manifest", "legs"} <= {row["id"] for row in explained}, rows
    table = doctor(standard, root).stdout.splitlines()
    for row in explained:
        [at] = [index for index, line in enumerate(table)
                if line.split()[:1] == ["NEXT"]
                and line.endswith("  " + row["next"])]
        assert table[at + 1].split()[0] == "WHY", table[at:at + 2]
        assert table[at + 1].endswith("  " + row["why"]), table[at:at + 2]


def test_a_report_that_cannot_answer_says_why_after_the_remediation(
        standard, project, tmp_path):
    """The CANNOT ANSWER block on stderr: `Remediation:` is the command, as
    the row's `next` is, and `Why:` is the line after it."""
    stranger = standard_of_another_history(standard, tmp_path)
    row = rows_of(doctor(stranger, project, "--json"))["shape-currency"]
    plain = doctor(stranger, project)
    assert plain.returncode == 3, plain.stdout + plain.stderr
    said = plain.stderr.splitlines()
    [at] = [index for index, line in enumerate(said)
            if line.startswith("  Remediation: ")]
    assert said[at] == "  Remediation: " + row["next"], said
    assert said[at + 1] == "  Why: " + row["why"], said


def test_a_cannot_answer_row_with_no_command_still_says_why(
        standard, project, capsys):
    """`Why:` is printed whenever the row has a `why`, whether or not it has
    a command for `Remediation:` (the coordinator's ruling on #277's merge
    with #278, which prints no `Remediation:` for a row with no NEXT). No
    row the doctor builds today is that row, so the report is handed one."""
    module = doctor_module(standard)
    ctx = module.Context(project.resolve())
    row = module.Row("cannot", "cannot", module.FINDING, "it could not ask",
                     None, {"environment": True}, why="what to do instead")
    module.report(ctx, [row], "CANNOT ANSWER (cannot: it could not ask)", 3)
    said = capsys.readouterr().err.splitlines()
    at = said.index("REFUSED shape-doctor-cannot-answer: it could not ask")
    assert said[at + 1:] == ["  Why: what to do instead"], said


# --- the guard: no tail comes back -------------------------------------------

#: What the guard calls a tail: two or more blanks, or a tab, then `#` and a
#: blank. The house spelling was three spaces; two, or a tab, is the same
#: comment to a shell, and the same word to an interactive zsh.
TAIL = re.compile(r"(?:[ \t]{2,}|\t)#[ \t]")

#: The strings that may hold one, by the def they are written in -- its
#: whole path from the module, so a nested def or a method that shares the
#: name is not waved through -- and why: neither is a NEXT. `None` allows
#: every string in that def; text allows that one string and no other, so a
#: tail written anywhere else in `report` is still found. A line number
#: would move with every edit above it.
TAIL_ALLOWED = {
    # YAML comment lines, written into the placement plan.
    "placement_plan_leg": None,
    # `placement plan written to <file>   # nothing moved: ...`, a line of
    # the report and not a command.
    "report": "   # nothing moved: answer every `resolution:` before a repair "
              "runs it",
}


def tails_in(source: str) -> list[tuple[int, str, str]]:
    """`(line, def, text)` for every string constant in `source` that holds
    a `TAIL` and is not a docstring, by the path of the defs it is written
    in (`outer/inner`, or `<module>`).

    The pieces of an f-string are constants too, so a tail spelled after a
    `{command}` is found like any other.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and \
                    isinstance(first.value, ast.Constant) and \
                    isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    found: list[tuple[int, str, str]] = []

    def visit(node, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, child.name if owner == "<module>"
                      else f"{owner}/{child.name}")
                continue
            if isinstance(child, ast.Constant) and \
                    isinstance(child.value, str) and \
                    id(child) not in docstrings and TAIL.search(child.value):
                found.append((child.lineno, owner, child.value))
            visit(child, owner)

    visit(tree, "<module>")
    return found


def disallowed(found: list[tuple[int, str, str]]) -> list:
    """The tails `TAIL_ALLOWED` does not allow."""
    return [(line, owner, text) for line, owner, text in found
            if owner not in TAIL_ALLOWED
            or TAIL_ALLOWED[owner] not in (None, text)]


def test_no_string_in_the_doctor_ends_a_command_with_a_comment():
    """The CLASS of the defect, for every builder, including later ones.

    Every NEXT is built from string constants in `shape-doctor.py`, so a
    tail in one is on its way to a NEXT. Two places hold that text for
    other reasons (`TAIL_ALLOWED`). A builder that wants to say why its
    command is the fix says it as the row's `why`.

    THE SCANNER IS SHOWN TO SEE ONE FIRST, on samples spelled the ways a
    tail can be -- three spaces after an f-string's `{command}`, two spaces,
    a tab, a second tail in `report` beside its allowed line, and one in a
    nested def that shares the name `report` -- beside a docstring that
    mentions one and must not count. And both allowed strings are found in
    the real file, so the guard is reading the strings it should.
    """
    sample = ('def builder(command):\n'
              '    """Its docstring may say `   # x`."""\n'
              '    return f"{command}   # a tail"\n'
              'def two(command):\n'
              '    return command + "  # two spaces"\n'
              'def tab(command):\n'
              '    return command + "\\t# a tab"\n'
              'def report(plan):\n'
              f'    print(f"{{plan}}{TAIL_ALLOWED["report"]}")\n'
              '    print(f"{plan}   # a second one")\n'
              'def outer():\n'
              '    def report():\n'
              '        return "x   # nested"\n'
              '    return report\n')
    assert [(owner, text) for _, owner, text in
            disallowed(tails_in(sample))] == [
        ("builder", "   # a tail"), ("two", "  # two spaces"),
        ("tab", "\t# a tab"), ("report", "   # a second one"),
        ("outer/report", "x   # nested")]

    found = tails_in((REPO / DOCTOR).read_text(encoding="utf-8"))
    outside = disallowed(found)
    assert not outside, (
        f"{DOCTOR} builds a string with a `   # ` tail at {outside}; an "
        "interactive zsh reads that `#` as a word and runs what follows it "
        "(#277). Pass the sentence as the row's `why=` instead.")
    assert {owner for _, owner, _ in found} == set(TAIL_ALLOWED), found
    assert TAIL_ALLOWED["report"] in [text for _, owner, text in found
                                      if owner == "report"], found
