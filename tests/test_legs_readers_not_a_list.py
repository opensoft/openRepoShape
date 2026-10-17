# SPDX-License-Identifier: Apache-2.0
"""Four more readers of a project manifest's `legs:` read it as the three
gates read it since #714 (#826), and say #714's sentence for it (#832).

EACH ITERATED `legs or []`: the doctor's `Context.legs`, the project's own
`scripts/bootstrap.py`, `bump-leg.py`'s `Project.legs` and `update-shape.py`'s
`pull_request_repository`. So `legs: 5` ended each in `TypeError: 'int'
object is not iterable` -- the doctor's whole report, in `declared_pins`
under its `manifest kinds` row -- and a scalar `openXdox`, a mapping `{a: b}`
or a list `[5]` was walked one character, one key or one entry at a time and
read as a project with no legs: the doctor's `legs` row said "a one-repository
project has none", bootstrap's step (a) "no submodule legs declared",
`bump-leg.py` refused `bump-leg-unknown-leg` with "it declares" and nothing
after it, and `update-shape.py`'s re-run `--pr` "declares no assembly leg".
NOW each says what it found in #714's words, the value spelled as the gates
spell it (`repr`):

    manifest-legs: legs is <value>, expected a list of `role:`,
      `repository:` and `path:` mappings
    manifest-leg: a leg is not a mapping: <entry>

- the doctor's `legs`, `leg shape files` and `placement` rows are `n/a`, say
  the sentence and wait on the `manifest` row (`waits_on`), as a row waits on
  a manifest that does not load (#205), and `--placement-plan` is refused by
  name with nothing written; a list holding legs beside such an entry still
  has its legs checked;
- bootstrap's step (a) says it, places no leg for it and places the legs
  beside it, and step (b)'s validators refuse;
- `bump-leg.py` refuses `bump-leg-manifest-legs`, exit 2, in both runs and
  before anything is fetched, a list holding legs beside such an entry
  included: its own `validate-manifest.py` refuses that list, so the bump
  could never land;
- `update-shape.py`'s `update-pr-no-repository` says it, where the re-run
  `--pr` recognises crashed.

THE GATES' OWN WORDS ARE #826's. A tree without it still has the naming and
pins gates crash on `5` and `validate-manifest.py` call it "missing or
empty", so this file asserts what the four readers say, from one table, and
nothing the gates print beside them; #826's own tests hold the gates to the
same sentence.

THE HARNESS: conftest's `project` for bootstrap and `bump-leg.py`,
`tests/test_shape_doctor.py`'s session standard for the doctor,
`tests/test_update_shape.py`'s upstream for the re-run, and
`tests/test_update_shape_pr_base.py`'s in-process `update-shape.py`.
"""

from __future__ import annotations

import json
import re
import shutil
from types import SimpleNamespace

import pytest

from conftest import git, run_script
from test_bump_leg import bump
from test_manifest_validator import edit
from test_non_list_project_fields import doctored, spelled_as  # noqa: F401
from test_shape_doctor import (  # noqa: F401
    doctor, rows_of, scaffolded_here, standard,
)
from test_update_shape import apply, upstream_and_project  # noqa: F401
from test_update_shape_pr_base import (  # noqa: F401
    gh_calls, update_shape, without_its_words,
)

#: The scaffold writes `legs:` as the manifest's last block.
LEGS_BLOCK = "\nlegs:\n"

#: What #714 says after a `legs:` value that is not a list.
LEGS_TAIL = "expected a list of `role:`, `repository:` and `path:` mappings"

#: `(YAML spelling, the sentence said)`: the issue's four, two more for the
#: entry rule, and a value holding ESC. The value is spelled as the gates
#: spell it, by `repr`, so no control character reaches a terminal raw.
CASES = [
    pytest.param("5", f"manifest-legs: legs is 5, {LEGS_TAIL}", id="number"),
    pytest.param("openXdox", f"manifest-legs: legs is 'openXdox', {LEGS_TAIL}",
                 id="scalar-string"),
    pytest.param("{a: b}", f"manifest-legs: legs is {{'a': 'b'}}, {LEGS_TAIL}",
                 id="mapping"),
    pytest.param("[5]", "manifest-leg: a leg is not a mapping: 5",
                 id="list-number"),
    pytest.param("[openXdox]",
                 "manifest-leg: a leg is not a mapping: 'openXdox'",
                 id="list-string"),
    pytest.param("[null]", "manifest-leg: a leg is not a mapping: None",
                 id="list-null"),
    pytest.param('"\\x1b[31mRED"',
                 f"manifest-legs: legs is '\\x1b[31mRED', {LEGS_TAIL}",
                 id="esc-string"),
]
#: The issue's own four.
ISSUE_CASES = CASES[:4]

#: The entry the mixed case appends after the scaffold's three legs.
MIXED_ENTRY = "  - 5\n"
MIXED_SAID = "manifest-leg: a leg is not a mapping: 5"


def is_a_list(said: str) -> bool:
    """Is the sentence about an entry of a list, not about `legs:`?"""
    return said.startswith("manifest-leg:")


def legs_are(project, spelled: str) -> None:
    """`legs: <spelled>` in place of the scaffold's legs, the last block."""
    text = (project / "project.yaml").read_text()
    edit(project, text[text.index(LEGS_BLOCK):],
         "\n" + spelled_as("legs", spelled) + "\n")


def legs_and_an_entry_that_is_not_one(project) -> None:
    """The scaffold's three legs, then an entry `5`."""
    text = (project / "project.yaml").read_text()
    block = text[text.index(LEGS_BLOCK):]
    edit(project, block, block + MIXED_ENTRY)


def no_traceback(result) -> None:
    """No traceback, and no ESC: a value is spelled where it is said."""
    out = result.stdout + result.stderr
    assert "Traceback" not in out, out
    assert "\x1b" not in out, out


# --- the doctor --------------------------------------------------------------

#: The rows that read `Context.legs`, and what each says it cannot do.
LEG_ROWS = {
    "legs": "the legs it declares are not known and none is checked against "
            "its pin",
    "leg-shape-files": "there are no legs to compare",
    "placement": "there is no leg to classify a path in",
}


def waiting_reason(said: str, needs: str) -> str:
    what = ("holds an entry that is not a mapping" if is_a_list(said)
            else "is not a list")
    return (f"project.yaml's `legs:` {what} ({said}), so {needs}; the "
            "`manifest` row names the fix")


@pytest.mark.parametrize("spelled,said", CASES)
def test_the_doctors_rows_that_read_the_legs_say_the_sentence_and_wait(
        standard, doctored, spelled, said):
    """`5` ended the report in a `TypeError`; the others made the `legs` row
    say the project is a one-repository one. Each row that reads the legs is
    now `n/a`, says the sentence, and names the `manifest` row it waits on,
    which is a FINDING; the row that crashed answers."""
    legs_are(doctored, spelled)
    result = doctor(standard, doctored, "--json")
    no_traceback(result)
    payload = json.loads(result.stdout)
    # A finding's exit. For `5` the standard's own naming gate crashes until
    # #826 lands, which is CANNOT ANSWER about this checkout: never this row.
    assert payload["exit"] == result.returncode, payload
    assert result.returncode in ({1, 3} if spelled == "5" else {1}), payload
    rows = rows_of(result)
    assert rows["manifest-kinds"]["status"] == "ok", rows["manifest-kinds"]
    assert rows["manifest"]["status"] == "FINDING", rows["manifest"]
    for row_id, needs in LEG_ROWS.items():
        row = rows[row_id]
        assert row["status"] == "n/a", row
        assert row["reason"] == waiting_reason(said, needs), row
        assert row["next"] is None, row
        assert row["detail"]["waits_on"] == "manifest", row
        assert row["detail"]["legs"] == [], row
    assert "one-repository project has none" not in result.stdout
    assert "declares no non-assembly leg" not in result.stdout


@pytest.mark.parametrize("spelled,said", ISSUE_CASES)
def test_a_placement_plan_is_refused_by_name_and_nothing_is_written(
        standard, doctored, tmp_path, spelled, said):
    """`--placement-plan` refuses an `n/a` placement row by name, exit 3, and
    writes nothing: it says the row's sentence, not "declares no leg"."""
    legs_are(doctored, spelled)
    plan = tmp_path / "plan.yaml"
    result = doctor(standard, doctored, "--placement-plan", str(plan))
    no_traceback(result)
    assert result.returncode == 3, result.stdout + result.stderr
    first = result.stderr.splitlines()[0]
    assert first.startswith("REFUSED shape-doctor-no-placement-audit: "), first
    assert first.endswith(
        " has no placement audit to write a plan from: "
        + waiting_reason(said, LEG_ROWS["placement"])), first
    assert not plan.exists()


def test_the_doctor_checks_the_legs_beside_an_entry_that_is_not_one(
        standard, doctored):
    """THE OTHER SIDE: where the list holds legs too, the rows check them, as
    `validate-pins.py` checks the rest past such an entry, and the entry is
    the `manifest` row's alone."""
    legs_and_an_entry_that_is_not_one(doctored)
    result = doctor(standard, doctored, "--json")
    no_traceback(result)
    rows = rows_of(result)
    assert rows["manifest"]["status"] == "FINDING", rows["manifest"]
    assert MIXED_SAID in rows["manifest"]["reason"], rows["manifest"]
    legs = rows["legs"]
    assert legs["status"] == "ok", legs
    assert legs["reason"] == "2 leg(s) mounted and checked out at their pins"
    assert [leg["role"] for leg in legs["detail"]["legs"]] == ["spec", "code"]
    for row_id in LEG_ROWS:
        assert "waits_on" not in rows[row_id]["detail"], rows[row_id]


# --- bootstrap.py, the project's own copy ------------------------------------

STEP_A = "\n(a) legs on tracking branches, pins untouched\n"
STEP_B = "\n(b) neutral validators\n"


def step_a(stdout: str) -> list[str]:
    """The lines step (a) printed, whole."""
    _, opened, rest = stdout.partition(STEP_A)
    assert opened, stdout
    lines, closed, _ = rest.partition(STEP_B)
    assert closed, stdout
    return lines.splitlines()


def step_a_says(said: str) -> str:
    if is_a_list(said):
        return (f"  {said}; it is not placed, and the validators below "
                "refuse until it is a mapping")
    return (f"  {said}; no leg is placed, and the validators below refuse "
            "until `legs:` is a list")


def bootstrap(project, *args: str):
    return run_script(project / "scripts" / "bootstrap.py", *args,
                      cwd=project)


@pytest.mark.parametrize("spelled,said", CASES)
def test_bootstraps_step_a_says_the_sentence_and_places_no_leg(project,
                                                               spelled, said):
    """`5` ended `make bootstrap` in a `TypeError` before step (a); the others
    made step (a) say "no submodule legs declared", as of a one-repository
    project. Step (a) is now the sentence alone. `--skip-validators`, so
    nothing a gate prints is read."""
    legs_are(project, spelled)
    result = bootstrap(project, "--skip-validators")
    no_traceback(result)
    assert result.returncode == 0, result.stdout + result.stderr
    assert step_a(result.stdout) == [step_a_says(said)], result.stdout
    assert "no submodule legs declared" not in result.stdout


#: Each gate's exit for these four: 1 with #826, which says the sentence, and
#: 2 or a traceback's 1 without it. Bootstrap reports each as it ends.
FAILED = re.compile(r"bootstrap FAILED: naming \(exit [12]\), manifest "
                    r"\(exit 1\), pins \(exit [12]\)")


@pytest.mark.parametrize("spelled,said", ISSUE_CASES)
def test_bootstrap_fails_on_its_validators_after_saying_the_sentence(
        project, spelled, said):
    """With the validators: step (a) says the sentence, step (b)'s gates
    refuse, and bootstrap fails, exit 1, with no traceback of its own."""
    legs_are(project, spelled)
    result = bootstrap(project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert step_a(result.stdout) == [step_a_says(said)], result.stdout
    assert 'bootstrap.py", line' not in result.stderr, result.stderr
    last = result.stderr.splitlines()[-1]
    assert FAILED.fullmatch(last), last


def test_bootstrap_places_the_legs_beside_an_entry_that_is_not_one(project):
    """THE OTHER SIDE: the entry is said first, and the two legs beside it
    are placed as ever."""
    legs_and_an_entry_that_is_not_one(project)
    result = bootstrap(project, "--skip-validators")
    no_traceback(result)
    assert result.returncode == 0, result.stdout + result.stderr
    said, spec, code = step_a(result.stdout)
    assert said == step_a_says(MIXED_SAID)
    assert spec.startswith("  [spec] spec: "), spec
    assert code.startswith("  [code] code: "), code


# --- bump-leg.py -------------------------------------------------------------

BUMP_REMEDY = (
    "Remediation: each entry of `legs:` is one leg, a mapping with `role:`, "
    "`repository:` and `path:`. The project's own "
    "`scripts/validate-manifest.py` names this same fault; a leg is not "
    "pinned around a manifest defect, so that comes first, then this "
    "command again.\n")

RUNS = [pytest.param(("--dry-run",), id="dry-run"),
        pytest.param((), id="real-run")]


def assert_bump_refused(project, scaffolded, said: str, extra) -> None:
    """`bump-leg-manifest-legs`, exit 2, before anything is fetched or
    written: only the manifest edit the test made is in `git status`."""
    to = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    result = bump(project, scaffolded, to, *extra)
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    manifest = project.resolve() / "project.yaml"
    assert result.stderr == (f"REFUSED bump-leg-manifest-legs: {manifest}: "
                             f"{said}\n{BUMP_REMEDY}"), result.stderr
    status = git("status", "--porcelain", cwd=project).stdout
    assert status.splitlines() == [" M project.yaml"], status


@pytest.mark.parametrize("extra", RUNS)
@pytest.mark.parametrize("spelled,said", CASES)
def test_bump_leg_refuses_a_legs_it_cannot_read_by_name_in_both_runs(
        project, scaffolded, spelled, said, extra):
    """`5` was a `TypeError`; the others were `bump-leg-unknown-leg`, "it
    declares" with nothing after it, and the remedy of a `--leg` that was
    not wrong."""
    legs_are(project, spelled)
    assert_bump_refused(project, scaffolded, said, extra)


@pytest.mark.parametrize("extra", RUNS)
def test_bump_leg_refuses_legs_beside_an_entry_that_is_not_one(
        project, scaffolded, extra):
    """The dry run previewed the move, exit 0, and the real run was refused
    `bump-leg-validators-red` on `validate-manifest.py`'s `manifest-leg`
    finding and rolled back: both runs are now refused first, alike."""
    legs_and_an_entry_that_is_not_one(project)
    assert_bump_refused(project, scaffolded, MIXED_SAID, extra)


# --- update-shape.py ---------------------------------------------------------

def why_none(said: str) -> str:
    """`pull_request_repository`'s `why_none` for the sentence."""
    if is_a_list(said):
        return ("project.yaml declares no assembly leg, so there is no "
                f"repository to open a pull request against: {said}")
    return ("project.yaml's `legs:` is not a list, so it names no assembly "
            "leg and there is no repository to open a pull request against: "
            f"{said}")


@pytest.mark.parametrize("spelled,said", CASES)
def test_update_shape_names_no_repository_in_the_sentence(
        update_shape, tmp_path, capsys, gh_calls, spelled, said):
    """`--pr` refuses `update-pr-no-repository` in the sentence's words, no
    `gh` is asked, and the `NEXT` line keeps the placeholder it prints for
    any manifest naming no repository."""
    (tmp_path / "project.yaml").write_text(
        spelled_as("legs", spelled) + "\n", encoding="utf-8")
    manifest = update_shape.load_yaml(tmp_path / "project.yaml")
    assert update_shape.pull_request_repository(manifest) == (
        "", why_none(said))
    with pytest.raises(update_shape.Refusal) as raised:
        update_shape.pull_request_target(tmp_path, update_shape.PROJECT_KIND)
    assert str(raised.value) == f"REFUSED update-pr-no-repository: " \
                                f"{why_none(said)}"
    assert gh_calls == []
    args = SimpleNamespace(branch="shape/x", push=True, pr=False)
    update_shape.next_line(tmp_path, args, [], "0" * 40, [],
                           update_shape.PROJECT_KIND)
    assert without_its_words(capsys.readouterr().out.strip()) == (
        "NEXT  gh pr create --repo <org>/<Project> --base main --head shape/x")


def test_update_shape_reads_the_assembly_leg_beside_an_entry_that_is_not_one(
        update_shape):
    """THE OTHER SIDE: the assembly leg's repository is read past such an
    entry; the validators `apply` runs before any landing say it."""
    manifest = {"legs": [5, {"role": "assembly",
                             "repository": "acme/Atlas"}]}
    assert update_shape.pull_request_repository(manifest)[0] == "acme/Atlas"


@pytest.mark.parametrize("spelled,said", ISSUE_CASES)
def test_the_rerun_that_opens_the_missing_pull_request_refuses_by_name(
        upstream_and_project, tmp_path, spelled, said):
    """THE PATH THAT CRASHED: the re-run `--pr` recognises, with nothing to
    write, reads the manifest's repository before `gh` is asked. `5` ended
    it in a `TypeError`; now each value is refused in the sentence."""
    root = tmp_path / "Atlas"
    shutil.copytree(upstream_and_project["clone"], root, symlinks=True)
    first = apply(root, upstream_and_project, "--branch", "shape/x")
    assert first.returncode == 0, first.stdout + first.stderr
    legs_are(root, spelled)
    git("commit", "-q", "-m", "legs", "--", "project.yaml", cwd=root)
    result = apply(root, upstream_and_project, "--branch", "shape/x", "--pr")
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout.startswith("nothing to write: "), result.stdout
    assert result.stderr == (f"REFUSED update-pr-no-repository: "
                             f"{why_none(said)}\n"), result.stderr
