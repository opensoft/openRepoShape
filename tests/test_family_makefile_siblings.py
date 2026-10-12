# SPDX-License-Identifier: Apache-2.0
"""A holder cut before `scripts/siblings.py` existed, updated the way AGENTS.md
prescribes, keeps working make targets (#489).

THE DEFECT. `update-shape.py check` on a family holder cut before 2026-09-09
(#76) reports `scripts/siblings.py` as `upstream-added` and the holder's
`Makefile` as `upstream-changed`. AGENTS.md's default is to take an added file
only on the human's word, per file (`apply --add scripts/siblings.py`). But
`apply` without `--add` copies the new Makefile all the same, and that
Makefile's `siblings`, `park` and `resume` targets run `scripts/siblings.py`.
`apply` exited 0, `validate-family.py` was green, only `note ... not added` was
printed, and then `make siblings` died on `python3: can't open file
'.../scripts/siblings.py'`; so did `make park` and `make resume`.

THE FIX KEEPS PER-FILE CONSENT. `apply` still refuses nothing and still adds
nothing it was not told to. What changed is the Makefile: each of the three
targets asks make itself whether the script is there, and when it is not it
refuses BY NAME, saying what is missing and which commands take it. And
`check` and `apply` say, on the line that already reports the file, that the
Makefile they copy calls it.

THE HOLDER IS CUT FROM A STANDARD BEFORE #76, built here rather than read out
of history: a clone of this repository whose family-root template has no
`scripts/siblings.py` (and no copy-list entry for it) and carries the
Makefile of v0.4 (d0df8d32), the one a holder cut on 2026-09-09 at 0170edd3
holds. That is C1, and `family.py init` run from it cuts the holder. C2 puts
the real files back, byte for byte out of the checkout under test, so the
update goes from the old standard to this one. A fixture that took the real
commit instead would pass on a checkout with no history, which `git clone`
of a shallow checkout is.

`tests/test_update_shape_add.py` keeps the NEWER Makefile in its holder at C1,
so its `scripts/siblings.py` row never meets a Makefile that has to change,
which is why it did not cover this.

Skipped only where `make` is absent, like the other tests that run it. No
network and no GitHub: bare repositories in a temporary directory, and a `gh`
guard first on PATH (`tests/conftest.py`).
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from shape_materialize import (  # noqa: E402
    FAMILY_COPIED_VERBATIM, FAMILY_EXECUTABLE)

MAKE = shutil.which("make")

pytestmark = pytest.mark.skipif(MAKE is None, reason="needs `make` on PATH")

UPDATE = REPO / "update-shape.py"
FAMILY = "InkRouter"
SIBLINGS = "scripts/siblings.py"
MATERIALIZER = "scripts/shape_materialize.py"
TEMPLATE = Path("templates") / "family-root"
#: The three targets that run the script, in the order the Makefile has them.
VERBS = ("siblings", "park", "resume")

#: The family-root Makefile as v0.4 shipped it (d0df8d32, 2026-09-03), the one
#: every holder cut before #76 holds: three targets and no `siblings`, `park`
#: or `resume`. Written out so the fixture needs no history.
OLD_MAKEFILE = r"""# The three targets a family holder ships. Copied verbatim from
# openRepoShape and digest-pinned in `contracts/shape-pin.yaml`.
#
# `bootstrap` and the member half of `validate` are done by
# `scripts/bootstrap.py` rather than by a shell loop here: it must resolve a
# credential for PRIVATE members before `git submodule update --init
# --recursive`, and it must report a member that is not initialised instead
# of failing the loop. A Makefile cannot do either honestly.
PYTHON ?= python3
.DEFAULT_GOAL := help

.PHONY: help bootstrap validate pins

help:
	@echo 'make bootstrap   fetch every member and its legs, then run each'
	@echo '                 member'\''s own make bootstrap'
	@echo 'make validate    the family validator, then each member'\''s make validate'
	@echo 'make pins        the family lockstep check alone (gitlink == pin)'

bootstrap:
	$(PYTHON) scripts/bootstrap.py

validate:
	$(PYTHON) scripts/validate-family.py
	$(PYTHON) scripts/bootstrap.py --no-fetch --members-make validate

pins:
	$(PYTHON) scripts/validate-family.py --pins
"""


def make(root: Path, *args: str) -> tuple[int, str, str]:
    """`make` in `root` with this interpreter as `PYTHON`: (code, stdout,
    stderr), decoded leniently.

    `PYTHON=<sys.executable>` for the reason `conftest.run_script` uses it. A
    make this process was started under would hand its own flags down through
    `MAKEFLAGS`, so those are dropped: what is under test is one make run.
    """
    env = {name: value for name, value in os.environ.items()
           if name not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}
    proc = subprocess.run([MAKE, *args, f"PYTHON={sys.executable}"],
                          cwd=str(root), capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def blob(repo: Path, commit: str, rel: str) -> bytes:
    """The bytes `commit` holds at `rel`: what `apply` copies, and what a
    working-tree comparison cannot promise on Windows."""
    proc = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=str(repo),
                          capture_output=True, check=True)
    return proc.stdout


# --- the Makefile alone -----------------------------------------------------

@pytest.fixture
def bare_holder(tmp_path) -> Path:
    """The template Makefile and nothing else: no `scripts/` at all."""
    root = tmp_path / FAMILY
    root.mkdir()
    shutil.copyfile(REPO / TEMPLATE / "Makefile", root / "Makefile")
    return root


def write_stub(root: Path) -> Path:
    """A `scripts/siblings.py` that says how it was called and exits 0."""
    script = root / SIBLINGS
    script.parent.mkdir(exist_ok=True)
    script.write_text("import sys\nprint('siblings.py ran with:', "
                      "sys.argv[1:])\n", encoding="utf-8")
    return script


@pytest.mark.parametrize("verb", VERBS)
def test_each_target_refuses_by_name_when_the_script_is_not_there(
        bare_holder, verb):
    """The three targets stop BEFORE running anything, with make's own exit 2,
    and the message names the file, says it is `update-shape.py`'s per-file
    rule that left it out, and gives the two steps that take it."""
    code, out, err = make(bare_holder, verb)
    both = out + err
    assert code == 2, both
    assert f"make {verb} needs {SIBLINGS}, which this holder does not have" \
        in err
    assert "only on the human's word" in err
    assert "update-shape.py check --root" in err
    assert 'check --root "' in err and bare_holder.name in err, (
        "the check command names THIS holder, ready to paste")
    assert "upstream-added" in err
    assert f"--add {SIBLINGS}" in err
    assert "can't open file" not in both and "No such file" not in both, (
        "the point of the guard: not python's own failure")
    assert SIBLINGS not in out, (
        "nothing ran: make would have echoed the command it ran on stdout")


def test_the_three_refusals_are_one_message(bare_holder):
    """One message, three targets, so they cannot drift apart: what differs is
    the verb and the line the refusal came from."""
    messages = {}
    for verb in VERBS:
        _, _, err = make(bare_holder, verb)
        text = re.sub(r"^Makefile:\d+: \*\*\* ", "", err.strip())
        messages[verb] = text.replace(f"make {verb} needs", "make V needs")
    assert len(set(messages.values())) == 1, messages


@pytest.mark.parametrize("verb", VERBS)
def test_the_refusal_needs_no_shell(bare_holder, verb):
    """The portability claim, asked as behaviour: the question is make's
    `$(wildcard)` and the refusal its `$(error)`, so with a SHELL that does
    not exist the answer is still the refusal. A `test -f` or an `echo` in
    the recipe would die on the missing shell with some other message."""
    code, _, err = make(bare_holder, verb, "SHELL=/nonexistent/openreposhape")
    assert code == 2, err
    assert f"make {verb} needs {SIBLINGS}" in err


@pytest.mark.parametrize("verb", VERBS)
def test_a_dry_run_makes_the_same_refusal(bare_holder, verb):
    """`make -n` is how a person asks what a target would do. Printing the
    python command for a target that cannot run would be the same wrong
    answer the broken Makefile gave."""
    code, out, err = make(bare_holder, "-n", verb)
    assert code == 2, out + err
    assert f"make {verb} needs {SIBLINGS}" in err


EXPECTED_ARGV = {
    "siblings": "[]",
    "park": "['--make', 'park', '--make-arg', 'ARGS=--dry-run']",
    "resume": "['--make', 'resume', '--make-arg', 'ARGS=--dry-run']",
}


@pytest.mark.parametrize("verb", VERBS)
def test_with_the_script_there_each_target_runs_it_as_it_always_did(
        bare_holder, verb):
    """The guard adds nothing to a holder that has the file: the same command
    line, the same arguments, no refusal and no extra output."""
    write_stub(bare_holder)
    code, out, err = make(bare_holder, verb, "ARGS=--dry-run")
    assert code == 0, out + err
    assert f"siblings.py ran with: {EXPECTED_ARGV[verb]}" in out
    assert "needs" not in err, err
    command = [line for line in out.splitlines()
               if line.startswith(sys.executable)]
    assert command and command[0].startswith(
        f"{sys.executable} {SIBLINGS}"), out


def test_the_other_targets_do_not_ask_for_the_script(bare_holder):
    """`make help`, `bootstrap`, `validate` and `pins` never ran the script, so
    a holder without it can still use them: they get as far as the command
    they always ran."""
    code, out, err = make(bare_holder, "help")
    assert code == 0, err
    for verb in ("bootstrap", "siblings", "validate", "pins", "park",
                 "resume"):
        assert f"make {verb}" in out
    for target, script in (("bootstrap", "scripts/bootstrap.py"),
                           ("validate", "scripts/validate-family.py"),
                           ("pins", "scripts/validate-family.py")):
        code, out, err = make(bare_holder, "-n", target)
        assert code == 0, err
        assert f"{sys.executable} {script}" in out
        assert SIBLINGS not in err


def test_the_makefile_still_names_every_target_once_as_phony():
    """A guard is a new recipe line, not a new target: the six names and the
    one `.PHONY` line `tests/test_park_resume_targets.py` reads are as they
    were."""
    text = (REPO / TEMPLATE / "Makefile").read_text(encoding="utf-8")
    phony = [line for line in text.splitlines() if line.startswith(".PHONY:")]
    assert len(phony) == 1, phony
    assert phony[0].split()[1:] == ["help", "bootstrap", "siblings",
                                    "validate", "pins", "park", "resume"]


# --- update-shape.py's own words --------------------------------------------

@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, by path (its name has a hyphen)."""
    spec = importlib.util.spec_from_file_location(
        "openreposhape_update_shape_489", UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(us, path: str, state: str):
    made = us.Row(path, "")
    made.state = state
    return made


def test_a_changed_makefile_without_the_script_is_said_to_leave_dead_targets(
        update_shape):
    clause = update_shape.left_dead_by(
        SIBLINGS, [row(update_shape, "Makefile", update_shape.UPSTREAM_CHANGED)])
    assert clause == ("the Makefile that `apply` copies calls it, so `make "
                      "siblings`, `make park` and `make resume` cannot run "
                      "until it is added")


@pytest.mark.parametrize("state", ["UNCHANGED", "LOCALLY_MODIFIED", "BOTH"])
def test_only_a_makefile_apply_will_copy_is_said_to_leave_anything(
        update_shape, state):
    """`unchanged` is already the standard's; `locally-modified` is kept and
    `both` is refused. None is a Makefile this run puts in front of a file it
    does not add, and a note about one would be about something else."""
    rows = [row(update_shape, "Makefile", getattr(update_shape, state))]
    assert update_shape.left_dead_by(SIBLINGS, rows) == ""


def test_no_makefile_row_and_no_other_path_says_nothing(update_shape):
    assert update_shape.left_dead_by(SIBLINGS, []) == ""
    changed = [row(update_shape, "Makefile", update_shape.UPSTREAM_CHANGED)]
    assert update_shape.left_dead_by("scripts/other.py", changed) == ""
    assert update_shape.left_dead_by(".gitattributes", changed) == ""


def test_the_table_is_true_of_the_templates(update_shape):
    """`CALLED_BY_A_COPY` is a fact about the standard's own files, so it is
    held to them: the caller is a family copy, it names the added file, and
    the added file is a family copy too (or the table says nothing true)."""
    assert SIBLINGS in update_shape.CALLED_BY_A_COPY
    for added, (caller, what) in update_shape.CALLED_BY_A_COPY.items():
        assert added in FAMILY_COPIED_VERBATIM
        assert caller in FAMILY_COPIED_VERBATIM
        text = (REPO / TEMPLATE / caller).read_text(encoding="utf-8")
        assert added in text, f"{caller} does not call {added}"
        for verb in VERBS:
            assert f"`make {verb}`" in what


# --- the holder, end to end -------------------------------------------------

def strip_siblings_entries(source: bytes) -> bytes:
    """The materializer's copy lists as they read before #76: the entry gone
    from `FAMILY_COPIED_VERBATIM` and `FAMILY_EXECUTABLE`. Bytes in and out,
    and `\\r?\\n` in the pattern: a checkout made under a CRLF `autocrlf` has
    CRLF throughout."""
    return re.sub(rb'^    "scripts/siblings\.py",\r?\n', b"", source,
                  flags=re.MULTILINE)


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at C1 (the standard before #76), a holder cut from it, and C2
    (this checkout's own bytes) above them."""
    base = tmp_path_factory.mktemp("family-makefile-siblings")
    upstream = base / "openRepoShape"
    proc = subprocess.run(["git", "clone", "-q", str(REPO), str(upstream)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr

    # ---- C1 ---------------------------------------------------------------
    template = upstream / TEMPLATE
    (template / "scripts" / "siblings.py").unlink()
    (template / "Makefile").write_bytes(OLD_MAKEFILE.encode("utf-8"))
    source = upstream / MATERIALIZER
    before = source.read_bytes()
    stripped = strip_siblings_entries(before)
    assert stripped != before and b'"scripts/siblings.py"' not in stripped, (
        "the copy lists still name scripts/siblings.py, which this fixture "
        "just removed")
    source.write_bytes(stripped)
    git("add", "-A", cwd=upstream)
    git("commit", "-q", "-m", "The standard before #76: no siblings.py and "
        "the v0.4 family Makefile", cwd=upstream)
    c1 = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()

    created = run_script(
        upstream / "scripts" / "family.py", "init", "--org", FAMILY,
        "--family", FAMILY, "--created-by", "Test Human",
        "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    holder = base / "fam" / FAMILY
    assert not (holder / SIBLINGS).exists(), "fixture: a holder cut before #76"
    assert "siblings:" not in (holder / "Makefile").read_text(encoding="utf-8")

    # ---- C2: this checkout's own bytes, back in -----------------------------
    for rel in (f"{TEMPLATE.as_posix()}/Makefile",
                f"{TEMPLATE.as_posix()}/{SIBLINGS}", MATERIALIZER):
        (upstream / rel).parent.mkdir(parents=True, exist_ok=True)
        (upstream / rel).write_bytes((REPO / rel).read_bytes())
    git("add", "-A", cwd=upstream)
    git("commit", "-q", "-m", "The standard as this checkout has it",
        cwd=upstream)
    c2 = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()
    assert c1 != c2
    return {"upstream": upstream, "holder": holder, "c1": c1, "c2": c2}


def cut(standard, tmp_path_factory, name: str) -> Path:
    """A private copy of the holder as it was cut."""
    target = tmp_path_factory.mktemp(name) / FAMILY
    shutil.copytree(standard["holder"], target, symlinks=True)
    return target


def apply(standard, root: Path, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["c2"], *extra)


@pytest.fixture(scope="module")
def without_add(standard, tmp_path_factory):
    """The holder after `apply` WITHOUT `--add`: AGENTS.md's default."""
    root = cut(standard, tmp_path_factory, "without-add")
    return root, apply(standard, root)


@pytest.fixture(scope="module")
def with_add(standard, tmp_path_factory):
    """The holder after `apply --add scripts/siblings.py`: on the human's
    word."""
    root = cut(standard, tmp_path_factory, "with-add")
    return root, apply(standard, root, "--add", SIBLINGS)


def test_check_reports_the_pair_and_says_what_they_leave(standard):
    """The state the issue describes, read before anything is written: the
    holder's Makefile `upstream-changed`, the script `upstream-added`, and a
    human told, before they say yes, that the Makefile calls the script."""
    result = run_script(UPDATE, "check", "--root", str(standard["holder"]),
                        "--upstream", str(standard["upstream"]),
                        "--at", standard["c2"])
    assert result.returncode == 1, result.stdout + result.stderr
    states = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and line.startswith("  "):
            states[parts[1]] = parts[0]
    assert states["Makefile"] == "upstream-changed", result.stdout
    assert states[SIBLINGS] == "upstream-added", result.stdout
    clause = ("the Makefile that `apply` copies calls it, so `make siblings`, "
              "`make park` and `make resume` cannot run until it is added")
    assert result.stdout.count(clause) == 1, result.stdout
    assert f"--add {SIBLINGS}" in result.stdout
    assert not (standard["holder"] / SIBLINGS).exists(), "`check` writes nothing"


def test_apply_without_add_still_copies_and_does_not_refuse(
        without_add, standard):
    """`apply` keeps per-file consent: the Makefile is copied, the script is
    not, and the run exits 0 as it always did. What it adds is the sentence."""
    root, result = without_add
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / "Makefile").read_bytes() == blob(
        standard["upstream"], standard["c2"], f"{TEMPLATE.as_posix()}/Makefile")
    assert not (root / SIBLINGS).exists()
    note = [line for line in result.stdout.splitlines()
            if line.startswith("  note") and SIBLINGS in line]
    assert len(note) == 1, result.stdout
    assert (f"{SIBLINGS} is new upstream; not added; pass --add {SIBLINGS} "
            "(the Makefile that `apply` copies calls it, so `make siblings`, "
            "`make park` and `make resume` cannot run until it is added)"
            ) in note[0]
    assert "family ok:" in result.stdout, "validate-family stays green"


@pytest.mark.parametrize("verb", VERBS)
def test_after_apply_without_add_each_target_says_what_to_do(
        without_add, verb):
    """THE REPORTED FAILURE: `make siblings` after an update that followed
    AGENTS.md. On the unfixed Makefile this is `python3: can't open file`."""
    root, _ = without_add
    code, out, err = make(root, verb)
    both = out + err
    assert code == 2, both
    assert f"make {verb} needs {SIBLINGS}, which this holder does not have" \
        in err
    assert "update-shape.py check --root" in err
    assert f"--add {SIBLINGS}" in err
    assert "can't open file" not in both and "No such file" not in both


@pytest.mark.parametrize("verb", VERBS)
def test_after_apply_with_add_each_target_runs(with_add, verb):
    """On the human's word, `--add scripts/siblings.py` takes the file and the
    three targets run the real script, as they did before the guard."""
    root, result = with_add
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / SIBLINGS).is_file()
    assert "not added" not in result.stdout
    code, out, err = make(root, verb)
    assert code == 0, out + err
    assert f"needs {SIBLINGS}" not in out + err
    assert "siblings ok:" in out, out
    if verb != "siblings":
        assert f"`make {verb}` ran in 0 member(s)" in out


def test_the_script_the_holder_takes_is_the_standards(with_add, standard):
    """`--add` copies the standard's file, not a paraphrase of it, and the
    copy lists name it executable like the two beside it."""
    root, _ = with_add
    assert (root / SIBLINGS).read_bytes() == blob(
        standard["upstream"], standard["c2"],
        f"{TEMPLATE.as_posix()}/{SIBLINGS}")
    assert SIBLINGS in FAMILY_EXECUTABLE
    if os.name != "nt":
        assert os.access(root / SIBLINGS, os.X_OK)
