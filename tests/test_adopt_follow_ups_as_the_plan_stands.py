# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` work the follow-ups out from the plan AS IT STANDS
(#1206).

`plan` wrote its follow-ups once, into the plan's `follow_ups:`, and `check`
and the split commit's message (which is also the pull request's body) read
that list back. The plan is meant to be edited: moving a kept Makefile to the
code leg "is a one-line edit of the plan" (`root-project-makefile`), and every
question is answered by editing `leg:`. Measured on main `3add78e1c`, after
each edit below `check` and the split commit carried what `plan` wrote, and
not what a fresh `plan` of a source whose rules give the edited answer
directly writes:

  * a kept `GNUmakefile` moved to the code leg: the `CONTRACTS_DIR` line
    still said GNU make at the root reads it;
  * `Makefile` and `GNUmakefile` kept, `GNUmakefile` moved to the code leg:
    the `CONTRACTS_DIR` line and the Makefile's collision line both did;
  * a `GNUmakefile/` question answered `root`: the line said the root
    Makefile wires `CONTRACTS_DIR`, where GNU make stops at the directory;
  * a kept `Makefile` moved to the code leg: "merge shape/Makefile into
    Makefile", over a split that wrote no `shape/Makefile`.

Now `plan` stores no `follow_ups:` and still prints its list; `check` and
`execute` work the list out from the entries as they stand; and a plan that
still holds a `follow_ups:` list is refused by name, `plan-bad-follow-ups`,
before any leg exists, and its items are never printed beside the list worked
out. The rows that run `execute` need `git filter-repo` and skip without it.
No network and no GitHub: the legs are bare repositories on disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, run_script,
                      write_plan)
from test_adopt_contracts_dir import (EDITS, PROJECT, SPLIT_BRANCH, TREE,
                                      needs_filter_repo)
from test_adopt_make_bootstrap_followups import policy_keeping_the_directory

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

GNUMAKEFILE = {"GNUmakefile": "build:\n\t@echo source build\n"}
MAKEFILE = {"Makefile": "build:\n\t@echo source build\n"}
GNUMAKEFILE_DIRECTORY = {"GNUmakefile/rules.mk": "build:\n\t@echo source\n"}


def policy_sending(base: Path, path: str, leg: str) -> Path:
    """The shipped policy with one rule above the rest (the first match
    wins) that sends `path` to `leg` and asks nothing."""
    shipped = (REPO / "contracts" / "path-classification.yaml").read_text(
        encoding="utf-8")
    assert shipped.count("\nrules:\n") == 1
    rule = ("rules:\n"
            "  - id: test-sends-it\n"
            "    paths:\n"
            f"      - \"{path}\"\n"
            f"    leg: {leg}\n"
            "    review: false\n"
            "    reason: The test's own answer.\n")
    policy = base / "policy.yaml"
    policy.write_text(shipped.replace("\nrules:\n", "\n" + rule, 1),
                      encoding="utf-8")
    return policy


def edited(plan: Path, path: str, was: str, leg: str) -> None:
    """The plan's entry for `path` edited from `leg: was` to `leg: leg`,
    with a `resolution:`, LF as `plan` wrote it."""
    text = plan.read_text(encoding="utf-8")
    needle = f"  - path: {path}\n    leg: {was}\n"
    assert text.count(needle) == 1, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(needle, (
            f"  - path: {path}\n    leg: {leg}\n"
            f"    resolution: \"the test moves it to the {leg}\"\n")))


def printed_by_plan(stdout: str) -> list[str]:
    """The items of `plan`'s `follow-ups (N):` list, as it prints them."""
    head, _, rest = stdout.partition("\nfollow-ups (")
    assert rest, stdout
    count, _, rest = rest.partition("):\n")
    items = rest.splitlines()[:int(count)]
    assert all(item.startswith("  - ") for item in items), items
    return [item[4:] for item in items]


def printed_by_check(stdout: str) -> list[str]:
    return [line[len("  follow-up: "):] for line in stdout.splitlines()
            if line.startswith("  follow-up: ")]


def in_the_split(source: Path) -> list[str]:
    """The FOLLOW-UPS of the split commit's message, which is also the
    pull request's body."""
    message = git("log", "-1", "--format=%B", SPLIT_BRANCH,
                  cwd=source).stdout
    _, _, tail = message.partition(
        "FOLLOW-UPS, which this commit does NOT do:\n")
    return [line[4:] for line in tail.splitlines() if line.startswith("  - ")]


def adopted(tmp_path: Path, source: Path, plan: Path) -> list[str]:
    """`check`'s follow-ups, after `execute --local-remote-dir` of the
    same plan has passed, and asserting that its split commit lists the
    same ones."""
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    said = printed_by_check(checked.stdout)
    assert in_the_split(source) == said
    return said


#: `(id, what the source keeps beside TREE, the entry edited, its leg as
#: `plan` writes it, the leg it is edited to, the rule a fresh plan's
#: policy gives instead)`. `None` for the rule is `tests/
#: test_adopt_make_bootstrap_followups.py`'s `a-rule-keeps-it` policy.
EDITS_OF_THE_PLAN = [
    pytest.param(GNUMAKEFILE, "GNUmakefile", "root", "code",
                 ("GNUmakefile", "code"), id="a-kept-gnumakefile-to-code"),
    pytest.param({**MAKEFILE, **GNUMAKEFILE}, "GNUmakefile", "root", "code",
                 ("GNUmakefile", "code"),
                 id="beside-a-makefile-the-gnumakefile-to-code"),
    pytest.param(GNUMAKEFILE_DIRECTORY, "GNUmakefile/", "null", "root", None,
                 id="a-gnumakefile-directory-answered-root"),
    pytest.param(MAKEFILE, "Makefile", "root", "code", ("Makefile", "code"),
                 id="a-kept-makefile-to-code"),
]


@needs_filter_repo
@pytest.mark.parametrize("kept, path, was, leg, rule", EDITS_OF_THE_PLAN)
def test_after_an_edit_the_follow_ups_are_a_fresh_plans(tmp_path, kept, path,
                                                        was, leg, rule):
    """A hand edit of one entry's `leg:`, then `check` and `execute`: the
    follow-ups `check` prints and the split commit's message lists are the
    ones a fresh `plan` prints, and `check` and `execute` of it carry, for a
    source whose rules give the edited answer directly. And what `plan`
    printed before the edit differs from them, so the row is about the
    edit: on main both surfaces carried what `plan` printed."""
    edits = tmp_path / "edits"
    source = make_source_repo(edits / "Thing", {**TREE, **kept}, edits=EDITS)
    plan = edits / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    before = printed_by_plan(written.stdout)
    edited(plan, path, was, leg)
    after = adopted(edits, source, plan)

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    ruled = make_source_repo(fresh / "Thing", {**TREE, **kept}, edits=EDITS)
    policy = (policy_keeping_the_directory(fresh) if rule is None
              else policy_sending(fresh, *rule))
    planned = fresh / "adoption-plan.yaml"
    written = write_plan(ruled, planned, project=PROJECT,
                         extra=("--path-policy", str(policy)))
    assert written.returncode == 0, written.stderr + written.stdout
    expected = printed_by_plan(written.stdout)

    assert after == expected
    assert adopted(fresh, ruled, planned) == expected
    assert before != expected


def test_plan_stores_no_follow_ups_and_prints_them(tmp_path):
    """The plan file has no `follow_ups:`, and says where they are; `plan`
    prints its list, and `check` of the plan as written prints the same."""
    source = make_source_repo(tmp_path / "Thing", {**TREE, **MAKEFILE},
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    assert "follow_ups" not in load_yaml(plan)
    assert "\n# The follow-ups are NOT stored here: `check` prints them" in \
        plan.read_text(encoding="utf-8")
    printed = printed_by_plan(written.stdout)
    assert [item for item in printed
            if item.startswith("merge shape/Makefile into Makefile")]
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert printed_by_check(checked.stdout) == printed


#: A `follow_ups:` list as `plan` wrote one before #1206 for a source that
#: kept a `Makefile`, after the hand move of that `Makefile` to the code leg:
#: the collision line it stored, and an item a person added by hand.
STALE = ("merge shape/Makefile into Makefile: the source repository already "
         "has that name, so the shape's copy was written beside it and "
         "NOTHING was overwritten")
OWN = "re-point the deploy job at the code leg"
STORED = f'follow_ups:\n  - "{STALE}"\n  - "{OWN}"\n'

#: The two ways of saying none, which hold nothing to lose and pass.
NONE_STORED = {"empty-list": "follow_ups: []\n", "bare-key": "follow_ups:\n"}


def an_old_plan(tmp_path: Path, block: str) -> tuple[Path, Path]:
    """A plan for a source that keeps a `Makefile`, the `Makefile` moved to
    the code leg by hand, and `block` added as a plan written before #1206
    held it."""
    source = make_source_repo(tmp_path / "Thing", {**TREE, **MAKEFILE},
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    edited(plan, "Makefile", "root", "code")
    with plan.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n" + block)
    return source, plan


def test_check_refuses_an_old_plans_follow_ups_by_name(tmp_path):
    """One FINDING, `plan-bad-follow-ups`, that says the follow-ups are no
    longer stored and are worked out from the plan as it stands, exit 1;
    the remediation says to delete the key, and to copy an item of one's
    own out first, for the pull request. Neither stored item is printed:
    `check`'s follow-ups are the ones worked out, which name no
    `shape/Makefile`."""
    _, plan = an_old_plan(tmp_path, STORED)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    found = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert found == [
        "FINDING plan-bad-follow-ups: the plan holds `follow_ups:`, a list "
        "of 2 item(s), and the follow-ups are no longer stored in the plan: "
        "`check` and `execute` work them out from the plan as it stands, "
        "and no command reads this list"], checked.stderr
    remedy = " ".join(checked.stderr.split())
    assert ("Remediation: the follow-ups are no longer stored in the plan, "
            "so delete `follow_ups:` and every item under it") in remedy
    assert ("An item you wrote there yourself is no longer carried into the "
            "split commit's message, which is also the pull request's body: "
            "copy it out first, and add it to the pull request yourself."
            ) in remedy
    said = printed_by_check(checked.stdout)
    assert said, checked.stdout
    assert STALE not in said and OWN not in said
    assert not [item for item in said if "shape/Makefile" in item], said


@needs_filter_repo
def test_execute_refuses_an_old_plans_follow_ups_before_any_leg(tmp_path):
    """Through `_refuse_what_check_finds`, under the finding's own code,
    before any leg exists; with the key deleted, the same plan adopts, and
    its split commit lists the follow-ups worked out, neither stored item
    among them."""
    source, plan = an_old_plan(tmp_path, STORED)
    remotes = tmp_path / "remotes"
    refused = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                         "--local-remote-dir", str(remotes),
                         "--work-dir", str(tmp_path / "work"))
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert "REFUSED plan-bad-follow-ups: " in refused.stderr
    assert not remotes.exists() or not any(remotes.iterdir())
    text = plan.read_text(encoding="utf-8")
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\n" + STORED, ""))
    said = adopted(tmp_path, source, plan)
    assert STALE not in said and OWN not in said
    assert not [item for item in said if "shape/Makefile" in item], said


@pytest.mark.parametrize("block", sorted(NONE_STORED))
def test_a_follow_ups_that_holds_nothing_passes(tmp_path, block):
    """`follow_ups: []` and a bare key, which the old remediation offered
    for none, hold nothing a person could lose: `check` passes, and prints
    the follow-ups worked out."""
    _, plan = an_old_plan(tmp_path, NONE_STORED[block])
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert printed_by_check(checked.stdout)


#: Two entries a hand edit can write that no command line can carry: a spec
#: directory and a code file whose names hold a NUL, a double-quoted YAML
#: scalar's `\x00` escape. Each is `check`'s `plan-unsafe-path`.
NUL_ENTRIES = ('  - path: "a\\x00b/"\n    leg: spec\n'
               '  - path: "c\\x00d"\n    leg: code\n')


def test_an_entry_git_cannot_be_handed_is_read_in_no_follow_up(tmp_path):
    """`check` of a plan with a code file and a spec directory that hold a
    NUL (and the entries `plan` wrote): exit 1, one `plan-unsafe-path`
    FINDING for each, and no traceback. The follow-ups are asked from the
    plan as it stands and one of them runs `git grep`, which a NUL in an
    argument ends in `ValueError: embedded null byte` before git runs, so
    `_follow_ups_as_it_stands` leaves such an entry out; main's `check` ran
    no `git grep`, and ended in findings. The entries `plan` wrote are
    still read: the code file that names `contracts/` still gets its
    read-across line."""
    source = make_source_repo(tmp_path / "Thing", {**TREE, **MAKEFILE},
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_text(encoding="utf-8")
    assert text.count("\npaths:\n") == 1, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\npaths:\n",
                                  "\npaths:\n" + NUL_ENTRIES, 1))
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert "Traceback" not in checked.stderr + checked.stdout, checked.stderr
    assert checked.returncode == 1, checked.stderr + checked.stdout
    found = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING plan-unsafe-path: ")]
    assert len(found) == 2, checked.stderr
    assert found[0].startswith("FINDING plan-unsafe-path: `a\\x00b/` has leg: "
                               "spec"), found
    assert found[1].startswith("FINDING plan-unsafe-path: `c\\x00d` has leg: "
                               "code"), found
    said = printed_by_check(checked.stdout)
    assert [item for item in said
            if "must read across the assembly root" in item], said


def test_a_command_line_git_cannot_be_run_with_is_a_search_by_hand(tmp_path):
    """One hand-edited code entry of 140000 characters, more than the
    kernel's limit on one argument: `git grep` cannot be run (`OSError:
    [Errno 7] Argument list too long`, which ended `check` in a traceback
    before it printed a finding), so each spec directory it would have
    searched for is the follow-up that says to look by hand, as for a grep
    that exits 128. `check` prints its findings, among them the entry
    that covers nothing, and exits 1; `execute` refuses that plan first."""
    source = make_source_repo(tmp_path / "Thing", {**TREE, **MAKEFILE},
                              edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_text(encoding="utf-8")
    assert text.count("\npaths:\n") == 1, text
    entry = f'  - path: "{"a" * 140000}"\n    leg: code\n'
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\npaths:\n", "\npaths:\n" + entry, 1))
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert "Traceback" not in checked.stderr + checked.stdout, \
        checked.stderr[-600:]
    assert checked.returncode == 1, checked.stderr[-600:]
    assert [line for line in checked.stderr.splitlines()
            if line.startswith("FINDING plan-empty-entry")], checked.stderr
    said = printed_by_check(checked.stdout)
    by_hand = [item for item in said
               if item.startswith("git could not search the files moving to "
                                  "the code leg for ")]
    assert len(by_hand) == 2, said
    assert all("`git grep` could not be run: " in item for item in by_hand)
