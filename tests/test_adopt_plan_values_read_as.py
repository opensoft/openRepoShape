# SPDX-License-Identifier: Apache-2.0
"""A plan value that is not text is said as `_read_as` says what the plan's
reader read, at `plan-wrong-kind`, `plan-unsupported-mode`, `plan-bad-leg`
and `plan-bad-id`, in `check` and in `execute` (#1199, which follows #1114).

Each of the four named the value it refused with `repr`, which spells a number
`7`, a boolean `True`, a null `None`, and a list or a mapping as Python does,
where every other refusal of a plan's value says what the reader read in
words (`_read_as`): "the number 7", "the boolean true", "null", "a list of 2
item(s)", "a mapping of 1 key(s)". A plan with `kind: 7` said "kind is 7",
and one with `id: [a, b]` said "`id:` is \"['a', 'b']\"", a quoted text with
no word that the plan holds a list.

WHAT DID NOT CHANGE. A text value is spelled as Python spells it, quoted, byte
for byte (`kind is 'placement-plan'`, a leg `'Spec'`), under the code each
refusal had, with the remedy it had: the control rows below pass on main. An
`id:` read as a number or a boolean is `_not_text`'s (#902) and says what it
did; `tests/test_adopt_values_as_typed.py` holds it.

A null `kind:` or `mode:` is "null", as `_read_as` says it, and a plan with no
such line is "absent", as `org:` is told apart (`_not_the_source`): `data.get`
gives None for both, and a plan with no line has none to mend.

Each row edits one line of one plan `plan` wrote, then runs `check` and
`execute --yes` on the edited plan, both with the same `--local-remote-dir`:
every run here refuses, so none makes the directory the legs go in, and the
one source is shared by the rows. `execute` asks for `git filter-repo` before
it refuses, so the rows skip where it is not installed.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, run_script, write_plan

UTF8 = "utf-8"
PLAN_FILE = "adoption-plan.yaml"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A source whose `README.md` entry `plan` keeps in the root with no question
#: to answer, so that the plan checks ok as `plan` wrote it: the `leg:` rows
#: edit that entry's line.
TREE = {"README.md": "# Thing\n", "src/b.py": "b = 1\n"}
ENTRY = "  - path: README.md\n    leg: root\n"

#: `repo_shape.PROJECT_ID_RE`, and what an `id:` it refuses is told.
PATTERN = "^[a-z0-9][a-z0-9-]*$"
PLAN_ID_HOLDS = (
    "Remediation: set `id:` in the plan to lowercase letters, digits and "
    "hyphens, starting with a letter or digit, or re-run `plan` with an --id "
    "of that form. The GitHub topic is derived from it.")
#: What a refused `mode:` is told.
MODE_REMEDY = (
    "Remediation: re-run `plan`, which writes `mode: in-place`. A `new-root` "
    "mode is described in the tool's own docstring and is not implemented.")
#: What a `kind:` that is the doctor's placement plan is told: the one wrong
#: kind with a way through of its own.
PLACEMENT_REMEDY_START = "Remediation: this is a PLACEMENT plan, written by "
#: How a leg finding ends: the values a `leg:` takes.
LEG_ONE_OF = "; it is one of ['spec', 'code', 'root', 'drop']"


@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> str:
    """The text of the plan `plan` writes for the source, which checks ok:
    each row edits a copy of it. `check` and `execute` only read the source,
    and every row refuses, so the rows share it."""
    base = tmp_path_factory.mktemp("answered")
    source = make_source_repo(base / "Thing", tree=TREE, edits=())
    plan = base / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stdout + written.stderr
    text = plan.read_bytes().decode(UTF8)
    assert text.count(ENTRY) == 1, text
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    return text


def edited(text: str, key: str, raw: str | None) -> str:
    """`text` with its top-level `key:` line set to `raw`, as the YAML of the
    plan spells it, or deleted where `raw` is None; `leg` is the one entry's
    own line."""
    if key == "leg":
        assert raw is not None
        return text.replace(ENTRY, f"  - path: README.md\n    leg: {raw}\n")
    line = re.compile(rf"^{key}: .*\n", re.M)
    assert len(line.findall(text)) == 1, text
    return line.sub("" if raw is None else f"{key}: {raw}\n", text)


def both_on(text: str, base: Path):
    """`check` and then `execute --yes` on the plan `text`, written at
    `base`, each given the same `--local-remote-dir`: `(the plan's path,
    check's run, execute's run)`. Neither makes the directory the legs go
    in, and neither raised."""
    base.mkdir(parents=True, exist_ok=True)
    plan = base / PLAN_FILE
    plan.write_bytes(text.encode(UTF8))
    remotes = base / "remotes"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--local-remote-dir", str(remotes))
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(base / "work"))
    assert not remotes.exists(), executed.stdout + executed.stderr
    for run in (checked, executed):
        assert "Traceback" not in run.stderr + run.stdout, run.stderr
    return plan, checked, executed


def refused_in_both(answered: str, tmp_path: Path, key: str, raw: str | None,
                    code: str, said: str, remedy: str | None) -> str:
    """`check` and `execute` of the plan with `key:` set to `raw` refuse it
    under `code` in the same words, `REFUSED <code>: <plan>: <said>`, and
    then the remedy where there is one, and nothing else on stderr. Returns
    stderr."""
    plan, checked, executed = both_on(edited(answered, key, raw), tmp_path)
    wanted = [f"REFUSED {code}: {plan}: {said}"]
    if remedy is not None:
        wanted.append(remedy)
    for run in (checked, executed):
        assert run.returncode == 2, run.stdout + run.stderr
        assert run.stderr.splitlines() == wanted, run.stderr
    return checked.stderr


def leg_found_in_both(answered: str, tmp_path: Path, raw: str,
                      said: str) -> str:
    """`check` finds the one entry with `leg: <raw>` as `plan-bad-leg`
    (`said` is what follows "declares leg"), and `execute` refuses with the
    finding as `check` prints it. Returns `check`'s stderr."""
    plan, checked, executed = both_on(edited(answered, "leg", raw), tmp_path)
    finding = ("FINDING plan-bad-leg: `README.md` declares leg "
               f"{said}{LEG_ONE_OF}")
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line for line in checked.stderr.splitlines()
            if line.startswith("FINDING ")] == [finding], checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert executed.stderr.splitlines()[:2] == [
        f"REFUSED plan-bad-leg: 1 finding(s) in {plan}, as `check` prints "
        "them:", f"  {finding}"], executed.stderr
    return checked.stderr


# --- every site, with every kind of value that is not text ------------------

#: `(the value as the plan spells it, what `_read_as` says of it, what Python
#: spells it as)`, by test id.
KINDS = {
    "number": ("7", "the number 7", "7"),
    "boolean": ("true", "the boolean true", "True"),
    "float": ("1.50", "the number 1.5", "1.5"),
    "list": ("[a, b]", "a list of 2 item(s)", "['a', 'b']"),
    "mapping": ("{k: v}", "a mapping of 1 key(s)", "{'k': 'v'}"),
}
#: The kinds an `id:` is told apart by: a number or a boolean `id:` is
#: refused by `_not_text` before the pattern is asked (#902).
ID_KINDS = ("list", "mapping")

SITES = {
    "kind": ("plan-wrong-kind",
             lambda read: f"kind is {read}, expected 'adoption-plan'", None),
    "mode": ("plan-unsupported-mode",
             lambda read: f"mode is {read}; v0.2 implements `in-place` only",
             MODE_REMEDY),
    "id": ("plan-bad-id",
           lambda read: f"`id:` is {read} and must match {PATTERN}",
           PLAN_ID_HOLDS),
}

ROWS = [pytest.param(key, kind, id=f"{key}-{kind}")
        for key in SITES for kind in KINDS
        if key != "id" or kind in ID_KINDS]


@needs_filter_repo
@pytest.mark.parametrize("key, kind", ROWS)
def test_a_refused_value_that_is_not_text_is_said_as_its_reader_read_it(
        answered, tmp_path, key, kind):
    """`kind:`, `mode:` and `id:`, a number, a boolean, a list or a mapping
    (an `id:` a list or a mapping only): `check` and `execute` refuse it
    under the code each had, with its remedy, naming the value in `_read_as`'s
    words (`kind is the number 7`) and not as Python spells it (`kind is 7`,
    `True`, `['a', 'b']`)."""
    raw, read, python = KINDS[kind]
    code, said, remedy = SITES[key]
    stderr = refused_in_both(answered, tmp_path, key, raw, code, said(read),
                             remedy)
    # What main said: `repr` of the value, and of the text `str` made of an
    # `id:` that is a list or a mapping.
    assert said(repr(python) if key == "id" else python) not in stderr, stderr


@needs_filter_repo
@pytest.mark.parametrize("kind", list(KINDS))
def test_a_leg_that_is_not_text_is_said_as_its_reader_read_it(
        answered, tmp_path, kind):
    """An entry's `leg:` a number, a boolean, a list or a mapping (`str` of it
    is what is asked of the leg values, so `leg: 7` reaches the finding):
    `check` finds it as `plan-bad-leg` naming it in `_read_as`'s words, `leg
    7` no more, and `execute` refuses with the finding as `check` prints
    it."""
    raw, read, python = KINDS[kind]
    stderr = leg_found_in_both(answered, tmp_path, raw, read)
    assert f"declares leg {python}{LEG_ONE_OF}" not in stderr, stderr


# --- the whole sentence, as a person reads it -------------------------------


@needs_filter_repo
def test_the_whole_refusal_for_a_number_kind(answered, tmp_path):
    """The issue's own `kind: 7`, word for word, in `check` and in `execute`:
    no remedy line follows, as there never was one."""
    plan, checked, executed = both_on(edited(answered, "kind", "7"),
                                      tmp_path)
    for run in (checked, executed):
        assert run.returncode == 2, run.stdout + run.stderr
        assert run.stderr == (
            f"REFUSED plan-wrong-kind: {plan}: kind is the number 7, "
            "expected 'adoption-plan'\n"), run.stderr


@needs_filter_repo
def test_the_whole_refusal_for_a_list_id(answered, tmp_path):
    """A list `id:`, which `str` made the quoted text `"['a', 'b']"` and
    refused as that: it says the plan holds a list, and the remedy says what
    an id may hold."""
    plan, checked, executed = both_on(edited(answered, "id", "[a, b]"),
                                      tmp_path)
    for run in (checked, executed):
        assert run.returncode == 2, run.stdout + run.stderr
        assert run.stderr == (
            f"REFUSED plan-bad-id: {plan}: `id:` is a list of 2 item(s) and "
            f"must match {PATTERN}\n{PLAN_ID_HOLDS}\n"), run.stderr


# --- a null or an absent kind and mode --------------------------------------

NULLISH = [pytest.param(key, raw, read, id=f"{key}-{name}")
           for key in ("kind", "mode")
           for name, raw, read in (("null", "null", "null"),
                                   ("bare", "", "null"),
                                   ("absent", None, "absent"))]


@needs_filter_repo
@pytest.mark.parametrize("key, raw, read", NULLISH)
def test_a_null_or_absent_kind_or_mode_is_said_so(answered, tmp_path, key,
                                                  raw, read):
    """`kind: null` and a bare `kind:` are "null", as `_read_as` says a null,
    where main said `None`; a plan with no `kind:` line at all is "absent",
    where main said the same `None`, and there is no line to look for. The
    same for `mode:`."""
    code, said, remedy = SITES[key]
    refused_in_both(answered, tmp_path, key, raw, code, said(read), remedy)


# --- controls: a text, byte for byte, on main and after ---------------------

TEXTS = {
    "kind": ("'x'", "kind is 'x', expected 'adoption-plan'"),
    "kind-escape": ('"a\\tb"', "kind is 'a\\tb', expected 'adoption-plan'"),
    "mode": ("new-root", "mode is 'new-root'; v0.2 implements `in-place` "
                         "only"),
    "id": ('"North Wind"', f"`id:` is 'North Wind' and must match {PATTERN}"),
}


@needs_filter_repo
@pytest.mark.parametrize("name", list(TEXTS))
def test_a_text_is_spelled_as_it_always_was(answered, tmp_path, name):
    """Control, which passes on main: a text `kind:`, `mode:` or `id:` is
    quoted as Python spells it, byte for byte, under the same code and with
    the same remedy (a tab as `\\t`, which `repr` escapes)."""
    key = name.split("-")[0]
    raw, said = TEXTS[name]
    code, _, remedy = SITES[key]
    refused_in_both(answered, tmp_path, key, raw, code, said, remedy)


@needs_filter_repo
def test_a_text_leg_is_spelled_as_it_always_was(answered, tmp_path):
    """Control, which passes on main: a text `leg:` the values refuse is
    quoted (`'Spec'`), and one with a character `repr` escapes is escaped."""
    leg_found_in_both(answered, tmp_path, "Spec", "'Spec'")
    leg_found_in_both(answered, tmp_path / "escape", '"Sp\\tec"',
                      "'Sp\\tec'")


@needs_filter_repo
def test_the_placement_plan_kind_keeps_its_own_remedy(answered, tmp_path):
    """Control, which passes on main: `kind: placement-plan` is the doctor's
    file, so the refusal names the text as it did and says where the file
    goes."""
    plan, checked, executed = both_on(
        edited(answered, "kind", "placement-plan"), tmp_path)
    for run in (checked, executed):
        assert run.returncode == 2, run.stdout + run.stderr
        lines = run.stderr.splitlines()
        assert lines[0] == (f"REFUSED plan-wrong-kind: {plan}: kind is "
                            "'placement-plan', expected 'adoption-plan'")
        assert lines[1].startswith(PLACEMENT_REMEDY_START), run.stderr
