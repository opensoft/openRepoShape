# SPDX-License-Identifier: Apache-2.0
"""A `--dry-run` passed through `setup-project.py` makes none of the
preflight's offers (#857).

The help says a `--dry-run` after `--` "ends this run at the plan, creating
nothing", and the plan says "nothing was created". The preflight before it
still offered, on a terminal, each command that fixes what it found missing:
an install of git or gh, `gh auth login`, and `gh auth setup-git`. Every one
of them changes the machine on a typed `yes` - software installed, gh signed
in, a credential helper written into the person's global git config - in a
run that then said nothing was created. And a rehearsal that typed only the
project name waited at the question until it was killed, as five of #777's
tests did on CI.

So a dry run reports what is missing and asks nothing that would change the
machine: where a terminal would have been offered a command, it is told the
offer was not made, and the plan's last line says so. `--preflight` still
makes every offer, whatever follows `--`: it is the run that exists for
them (#59).

The terminal runs are POSIX only (`PTY_SKIP`). Their `gh` is a stub first on
`PATH` that answers what the run asks and writes what the real one would
write: a login state of its own, and the helper `gh auth setup-git` adds to
the file `GIT_CONFIG_GLOBAL` names. The real `gh` is never reached. The
in-process runs fake the terminal and record every command, running none.
"""

from __future__ import annotations

import os
import sys

import pytest

from conftest import DRY_RUN_ENDS_IT, PTY_SKIP, run_in_a_terminal
from test_setup_project_py import (EVERY_MANAGER, SETUP_PROJECT, _answers,
                                   _Runs, _which, entry_point_module, piped,
                                   terminal_env)
from test_setup_project_typed_name import the_refusal

#: What the terminal is told where an offer was not made.
NOT_OFFERED = ("      not offered: --dry-run was passed through. A run "
               "without it offers this here, and so does --preflight.")

#: The plan's last line in a dry run: what it always said, and then that the
#: preflight made no offer.
DRY_RUN_LAST_LINE = (DRY_RUN_ENDS_IT + " The preflight made none of its "
                     "offers; a run without --dry-run makes each one marked "
                     "`not offered` above.")

PREREQ_MISSING = "one or more prerequisites are missing (see above)."

HELPER_WARNING = ("[??] git has no credential helper for github.com, so the "
                  "first push over HTTPS will fail. Fix it once: gh auth "
                  "setup-git")

NOT_SIGNED_IN = "[!!] gh is not authenticated. Run: gh auth login"


# --- in process: every offer, on every platform ------------------------------

#: A machine missing what each offer is for: the programs `shutil.which`
#: finds, what `run` answers, the offers a run without `--dry-run` makes,
#: and the refusal the preflight ends in ("" when it passes).
MACHINES = {
    "install": (EVERY_MANAGER, {}, 2, PREREQ_MISSING),
    "login": (("git", "gh"), {"auth status": (1, "")}, 1, PREREQ_MISSING),
    "helper": (("git", "gh"), {"config --get-all": (1, "")}, 1, ""),
}

#: The commands an offer runs on a `yes`: an install goes through a shell,
#: and the two gh commands are argvs of their own.
OFFERED = (["gh", "auth", "login"], ["gh", "auth", "setup-git"])


def refusal_of(module, opts):
    """What `preflight` refused, or "" when it passed."""
    try:
        module.preflight(opts)
    except module.Refusal as refusal:
        return str(refusal)
    return ""


def ran_an_offer(call):
    return call[:2] in (["bash", "-c"], ["cmd", "/c"]) or call in OFFERED


@pytest.mark.parametrize("machine", MACHINES)
def test_a_dry_run_makes_none_of_the_offers_preflight_makes(
        monkeypatch, capsys, tmp_path, machine):
    """A terminal that types `yes` to anything is asked nothing by a dry
    run, and nothing an offer runs is run: the offers are named as not made,
    and every check still says what is missing. `--preflight -- --dry-run`
    makes the same offers a run without `--dry-run` makes, and the recorder
    runs none of them."""
    present, answers, offers, refused = MACHINES[machine]
    module = entry_point_module()
    monkeypatch.setattr(module.shutil, "which", _which(*present))
    runs = _Runs(answers)
    monkeypatch.setattr(module, "run", runs)
    prompts = _answers(monkeypatch, module, "yes")
    rehearsal = module.parse_args(["Sample", "--org", "demoorg", "--",
                                   "--dry-run"], str(tmp_path))
    assert refusal_of(module, rehearsal) == refused
    assert prompts == [], "a dry run made an offer"
    assert [call for call in runs.calls if ran_an_offer(call)] == []
    assert capsys.readouterr().out.count(NOT_OFFERED) == offers
    module.preflight_only(module.parse_args(["--preflight", "--",
                                             "--dry-run"], str(tmp_path)))
    assert len(prompts) == offers, "--preflight made no offer"
    assert NOT_OFFERED not in capsys.readouterr().out


# --- at a terminal -----------------------------------------------------------

#: A `gh` that logs each call, answers the preflight and the plan's three
#: questions, and writes what the real one writes. Signed in where its
#: folder holds `signed-in`.
STUB_GH = (b"#!/bin/sh\n"
           b'here=$(dirname "$0")\n'
           b'printf "%s\\n" "$*" >> "$here/calls.log"\n'
           b'case "$*" in\n'
           b'  --version) echo "gh version 2.50.0 (stub)" ;;\n'
           b'  "auth status") [ -e "$here/signed-in" ] || exit 1 ;;\n'
           b'  "auth login") : > "$here/signed-in" ;;\n'
           b'  "auth setup-git") printf \'[credential "https://github.com"]'
           b'\\n\\thelper =\\n\\thelper = !gh auth git-credential\\n\' '
           b'>> "${GIT_CONFIG_GLOBAL:?}" ;;\n'
           b"  api*) echo tester ;;\n"
           b'  "repo view"*) echo "GraphQL: Could not resolve to a '
           b'Repository with the name x." >&2; exit 1 ;;\n'
           b'  *) echo "stub gh: refused $*" >&2; exit 97 ;;\n'
           b"esac\n")

#: The person's global git config: a name, and no credential helper.
GLOBAL_CONFIG = b"[user]\n\tname = Tester\n"

#: The same, with the helper `gh auth setup-git` writes.
GLOBAL_CONFIG_WITH_A_HELPER = (GLOBAL_CONFIG
                               + b'[credential "https://github.com"]\n'
                               b"\thelper =\n"
                               b"\thelper = !gh auth git-credential\n")


class Rehearsal:
    """`setup-project.py Sample --org demoorg ... -- --dry-run` at a
    terminal that types `yes` to the first `Type yes to continue:` it is
    shown, under `STUB_GH`, signed in or not, and a global git config of the
    run's own: what the run did, and the files it could have changed.

    Its git reads no config but that file and an empty system one: the
    environment's `GIT_CONFIG_COUNT` and `-c` pairs are dropped, and it runs
    from a folder that is no repository, so no checkout's config gives it a
    helper either."""

    def __init__(self, tmp_path, signed_in, global_config, entry="py"):
        stub = tmp_path / "ghbin"
        stub.mkdir()
        (stub / "gh").write_bytes(STUB_GH)
        (stub / "gh").chmod(0o755)
        self.signed_in = stub / "signed-in"
        if signed_in:
            self.signed_in.write_bytes(b"")
        self.global_config = tmp_path / "global.gitconfig"
        self.global_config.write_bytes(global_config)
        system = tmp_path / "system.gitconfig"
        system.write_bytes(b"")
        (tmp_path / "gh-config").mkdir()
        env = {key: value for key, value in terminal_env().items()
               if key not in ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS")}
        env.update({"PATH": str(stub) + os.pathsep + env["PATH"],
                    "GH_CONFIG_DIR": str(tmp_path / "gh-config"),
                    "GIT_CONFIG_GLOBAL": str(self.global_config),
                    "GIT_CONFIG_SYSTEM": str(system)})
        self.into = tmp_path / "into"
        flags = ["Sample", "--org", "demoorg", "--elected-by", "Tester",
                 "--into", str(self.into), "--", "--dry-run"]
        argv = {"py": [sys.executable, str(SETUP_PROJECT), *flags],
                "piped": piped("", *flags)}[entry]
        self.status, self.screen, self.answered = run_in_a_terminal(
            argv, cwd=tmp_path, env=env, answers=["yes\n"], timeout=60)
        log = stub / "calls.log"
        self.calls = (log.read_text(encoding="utf-8").splitlines()
                      if log.exists() else [])

    def assert_asked_nothing(self):
        assert self.answered == 0, f"it made an offer:\n{self.screen}"
        assert "Type yes to continue" not in self.screen, self.screen
        assert not self.into.exists()


@PTY_SKIP
@pytest.mark.parametrize("entry", ["py", "piped"])
def test_a_dry_run_leaves_git_with_no_helper_as_it_found_it(tmp_path, entry):
    """Signed in, and git has no credential helper: the preflight warns, says
    `gh auth setup-git` was not offered, and goes on to the plan, which ends
    the run. The global git config is the bytes it was."""
    run = Rehearsal(tmp_path, True, GLOBAL_CONFIG, entry)
    run.assert_asked_nothing()
    assert run.status == 0, run.screen
    assert HELPER_WARNING + "\n" + NOT_OFFERED + "\n" in run.screen
    assert DRY_RUN_LAST_LINE in run.screen
    assert run.global_config.read_bytes() == GLOBAL_CONFIG
    assert "auth setup-git" not in run.calls


@PTY_SKIP
def test_a_dry_run_does_not_sign_gh_in(tmp_path):
    """Not signed in: the preflight says `gh auth login` was not offered and
    refuses as it does with nothing to ask on. gh is not signed in. Git has a
    helper, so the login is the one offer at stake."""
    run = Rehearsal(tmp_path, False, GLOBAL_CONFIG_WITH_A_HELPER)
    run.assert_asked_nothing()
    assert run.status == 2, run.screen
    assert NOT_SIGNED_IN + "\n" + NOT_OFFERED + "\n" in run.screen
    assert the_refusal(run.screen) == "REFUSED: " + PREREQ_MISSING
    assert not run.signed_in.exists()
    assert "auth login" not in run.calls
