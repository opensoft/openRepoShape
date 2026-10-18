# SPDX-License-Identifier: Apache-2.0
"""A `shape/` collision copy merged into the file it collided with (#502).

AN IN-PLACE ADOPTION KEEPS THE SOURCE'S OWN `.gitignore` AND `Makefile`, and
writes the shape's copies of them beside the originals, under `shape/`,
where the shape pin gives each a row. The plan's follow-up says to merge
`shape/X` into `X`, and the natural last act of that merge is to remove the
copy. Its row then named a file that is not there: the project's own
`validate-pins.py`, and with it `bootstrap.py` and CI's `validate`, said
`shape-copy-missing`; `update-shape.py` called the row `copy-missing` and
refused `update-conflict` with a remedy, `--accept-local`, that it refused
in the same words; and no tool removed the row, which left undoing the merge
or the hand edit of the pin that AGENTS.md forbids.

Brett Heap ruled that the row goes (2026-10-12), and how (2026-10-13):
"check names, apply drops". So `check` reports such a row `merged-away`,
`apply` drops it in its re-pin commit behind the same yes as every other
row, the doctor's `shape currency` and `pins` rows name that step, the
plan's follow-up says what happens to the row, and a pinned copy deleted
anywhere else stays `copy-missing`, with a remediation of its own.

ONE REAL ADOPTION, OUT OF THE STANDARD `tests/test_shape_doctor.py` BUILDS,
into local bare remotes, so the pin, the copies and the doctor all name one
commit. Every test works on a private copy of its clone. `execute` needs
`git filter-repo`, so a machine without it skips this file, as
`tests/test_adopt_e2e.py` does.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, clone_just_pushed, git, \
    make_source_repo, run_script
from test_shape_doctor import (  # noqa: F401
    commit_all, doctor, keep_as_committed_link, rows_of, standard,
    standard_ahead, standard_of_another_history, verdict_line,
)
#: A partial clone of the standard one commit on, from the file that owns
#: the doctor's partial-clone question (#683).
from test_doctor_partial_clone import (  # noqa: F401
    doctored, moved, partial_clone_of,
)
from test_update_shape import STATES, next_line_of

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Medx"
SHAPE_PIN = "contracts/shape-pin.yaml"

#: The issue's own source, with a `Makefile` beside its `.gitignore`: two
#: names the shape copies too, so the adoption writes both of its copies
#: under `shape/` and pins them there. `README.md` collides as well, and is
#: rendered rather than copied, so its `shape/README.md` has no row.
SOURCE_TREE = {
    "specs/a.md": "# A\n",
    "src/a.py": "print(1)\n",
    "README.md": "# Medx\n",
    ".gitignore": "build/\n*.log\n",
    "Makefile": "build:\n\t@echo the source's own build\n",
}

#: The pinned collision copies, and the file each was cut for.
MERGED = {"shape/.gitignore": ".gitignore", "shape/Makefile": "Makefile"}

#: The same source keeping a root `.gitattributes` of its own (#471): the
#: shape's copy is pinned beside it as `shape/.gitattributes`, and the split
#: appends its line-ending block to the source's file. A rule that changes
#: no line ending, so every platform checks the clone out as it was written.
ATTRIBUTES = ".gitattributes"
ATTRIBUTES_TREE = {**SOURCE_TREE, ATTRIBUTES: "*.png binary\n"}


@pytest.fixture(scope="module")
def adopted_here(standard, tmp_path_factory) -> dict:
    """`SOURCE_TREE` adopted with the standard's own `adopt-project.py`, its
    pull request merged, and a recursive clone of it."""
    return adopt_and_clone(standard, tmp_path_factory.mktemp("merged-away"),
                           SOURCE_TREE)


@pytest.fixture(scope="module")
def adopted_with_attributes(standard, tmp_path_factory) -> dict:
    """`ATTRIBUTES_TREE`, adopted and cloned as `adopted_here` is."""
    return adopt_and_clone(
        standard, tmp_path_factory.mktemp("merged-away-attributes"),
        ATTRIBUTES_TREE)


def adopt_and_clone(standard: Path, base: Path, tree: dict) -> dict:
    """`tree` adopted with the standard's own `adopt-project.py` in `base`,
    its pull request merged, and a recursive clone of it: the plan and the
    clone."""
    source = make_source_repo(base / PROJECT, tree=tree, edits=())
    plan = base / "adoption-plan.yaml"
    adopt = standard / "adopt-project.py"
    planned = run_script(adopt, "plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--elected-by",
                         "Test Human", "--elected-on", "2026-10-13",
                         "--out", str(plan))
    assert planned.returncode == 0, planned.stdout + planned.stderr
    checked = run_script(adopt, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    executed = run_script(adopt, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(base / "remotes"),
                          "--work-dir", str(base / "work"))
    assert executed.returncode == 0, executed.stdout + executed.stderr
    git("merge", "-q", "--ff-only", "adopt/three-repo-shape", cwd=source)
    clone = base / "clone" / PROJECT
    cloned = clone_just_pushed(source, clone)
    assert cloned.returncode == 0, cloned.stderr
    return {"plan": plan, "clone": clone}


@pytest.fixture
def root(adopted_here, tmp_path) -> Path:
    """A private, mutable copy of the adopted clone."""
    target = tmp_path / PROJECT
    shutil.copytree(adopted_here["clone"], target, symlinks=True)
    return target


def pin_files(root: Path) -> list:
    """`(path, sha256)` per `files:` row, in the order the pin holds them."""
    return [(row["path"], str(row["sha256"]).lower())
            for row in load_yaml(root / SHAPE_PIN)["files"]]


def verdicts(stdout: str) -> dict:
    """`{path: state}` out of `check`'s report, `merged-away` included."""
    states = (*STATES, "merged-away")
    out = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in states and line.startswith("  "):
            out[parts[1]] = parts[0]
    return out


def merge_away(root: Path, *names: str) -> None:
    """The plan's follow-up, done as a person does it: each `shape/<name>`
    appended to `<name>`, the copy removed, and the two committed."""
    for name in names:
        original = root / name
        original.write_bytes(original.read_bytes()
                             + (root / "shape" / name).read_bytes())
        git("rm", "-q", "--", f"shape/{name}", cwd=root)
        git("add", "--", name, cwd=root)
    git("commit", "-q", "-m", "Merge the shape's copies into our own",
        cwd=root)


def update_shape(standard: Path, root: Path, *args: str):
    return run_script(standard / "update-shape.py", *args, "--root",
                      str(root), "--upstream", str(standard))


def gate(root: Path, script: str):
    return run_script(root / "scripts" / script, cwd=root)


def test_a_merged_away_copys_row_goes_and_the_project_is_green_again(
        standard, root):
    """The issue's reproduction, then the ruling, end to end.

    Both follow-ups done: the project's own `validate-pins.py` and
    `bootstrap.py` are red. `check` calls both rows `merged-away`, with no
    refusal ahead; the doctor says `DRIFTED (2 merged-away)`, and its `pins`
    row names the `check` its `shape currency` row names. `check`'s NEXT,
    pasted as printed, drops the two rows and moves nothing else in the pin,
    and then the gates are green, the doctor says COMPLIANT and `check` has
    nothing to do.
    """
    before = pin_files(root)
    assert set(MERGED) <= {path for path, _ in before}, before
    assert gate(root, "validate-pins.py").returncode == 0
    merge_away(root, *MERGED.values())

    pins = gate(root, "validate-pins.py")
    assert pins.returncode == 1, pins.stdout + pins.stderr
    for path in MERGED:
        assert (f"FINDING shape-copy-missing: {SHAPE_PIN}: {path} is pinned "
                "but absent") in pins.stdout + pins.stderr
    booted = gate(root, "bootstrap.py")
    assert booted.returncode == 1, booted.stdout + booted.stderr

    checked = update_shape(standard, root, "check")
    assert checked.returncode == 1, checked.stdout + checked.stderr
    states = verdicts(checked.stdout)
    assert {path: states.get(path) for path in MERGED} == {
        path: "merged-away" for path in MERGED}, checked.stdout
    assert "REFUSAL AHEAD" not in checked.stdout, checked.stdout
    for path, original in MERGED.items():
        assert f"merged into {original} and removed" in checked.stdout

    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "DRIFTED (2 merged-away)", payload["verdict"]
    rows = rows_of(result)
    pins_row, currency = rows["pins"], rows["shape-currency"]
    assert pins_row["status"] == "FINDING", pins_row
    assert pins_row["detail"]["merged_away"] == MERGED, pins_row
    assert "update-shape.py" in pins_row["next"], pins_row["next"]
    assert currency["next"].startswith(pins_row["next"]), (pins_row, currency)
    assert "merged-away" in pins_row["reason"], pins_row["reason"]

    line = next_line_of(checked.stdout)
    argv = shlex.split(line[len("NEXT  "):])
    assert argv[1:3] == ["update-shape.py", "apply"], line
    applied = run_script(standard / "update-shape.py", *argv[2:])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    for path in MERGED:
        assert f"  dropped  {path} " in applied.stdout, applied.stdout

    assert pin_files(root) == [row for row in before
                               if row[0] not in MERGED], (
        "the two rows go, and nothing else in the pin moves")
    pinned = load_yaml(root / SHAPE_PIN)
    assert pinned["commit"].lower() == git(
        "rev-parse", "HEAD", cwd=standard).stdout.strip()
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=root).stdout.split())
    assert SHAPE_PIN in committed and committed <= {SHAPE_PIN, "project.yaml"}, \
        committed

    for script in ("validate-pins.py", "bootstrap.py"):
        ran = gate(root, script)
        assert ran.returncode == 0, f"{script}:\n{ran.stdout}{ran.stderr}"
    again = doctor(standard, root)
    assert again.returncode == 0, again.stdout + again.stderr
    assert verdict_line(again).startswith("COMPLIANT   (exit 0)"), again.stdout
    rechecked = update_shape(standard, root, "check")
    assert rechecked.returncode == 0, rechecked.stdout + rechecked.stderr
    assert "nothing to do" in rechecked.stdout


def test_a_shape_copy_removed_with_its_original_stays_copy_missing(
        standard, root):
    """Nothing says a merge happened where the file the copy was cut for is
    gone too, so the row stays `copy-missing` and is refused. The refusal's
    remedy is that state's own, with or without `--accept-local`: the copy
    goes back from history, never the re-run with `--accept-local` that was
    refused in the same words. The doctor's `pins` row keeps the gate.

    It no longer says this command never records a deletion (review of PR
    #512, NIT-1): `apply` records one, a merged-away row's, so the sentence
    says which deletion it never records."""
    git("rm", "-q", "--", "shape/.gitignore", ".gitignore", cwd=root)
    git("commit", "-q", "-m", "Remove both", cwd=root)
    before = pin_files(root)

    checked = update_shape(standard, root, "check")
    assert verdicts(checked.stdout)["shape/.gitignore"] == "copy-missing"
    assert "REFUSAL AHEAD" in checked.stdout, checked.stdout

    for extra in ((), ("--accept-local", "shape/.gitignore")):
        refused = update_shape(standard, root, "apply", "--yes", *extra)
        assert refused.returncode == 2, refused.stdout + refused.stderr
        assert "REFUSED update-conflict" in refused.stderr, refused.stderr
        assert ("Remediation: shape/.gitignore is pinned and gone from the "
                "root, so --accept-local has no bytes to keep, and this "
                "command never records the deletion of a copy the project "
                "still needs.") in refused.stderr, refused.stderr
        assert "never records a deletion" not in refused.stderr
        assert "re-run this with --accept-local" not in refused.stderr
        assert pin_files(root) == before

    rows = rows_of(doctor(standard, root, "--json"))
    assert "merged_away" not in rows["pins"]["detail"], rows["pins"]
    assert "update-shape.py" not in rows["pins"]["next"], rows["pins"]


def test_a_pinned_copy_deleted_elsewhere_stays_copy_missing(standard, root):
    """`.gitattributes` took its own name, so its deletion is no merge: it
    stays `copy-missing` beside a merged-away `shape/.gitignore`, and the
    refusal names it alone, with its own remedy. The `pins` row keeps the
    gate, because the step it would name does not clear that finding."""
    merge_away(root, ".gitignore")
    git("rm", "-q", "--", ".gitattributes", cwd=root)
    git("commit", "-q", "-m", "Remove a pinned copy", cwd=root)

    checked = update_shape(standard, root, "check")
    states = verdicts(checked.stdout)
    assert states["shape/.gitignore"] == "merged-away", checked.stdout
    assert states[".gitattributes"] == "copy-missing", checked.stdout
    (ahead,) = [line for line in checked.stdout.splitlines()
                if line.startswith("REFUSAL AHEAD")]
    assert ahead.endswith(" .gitattributes"), ahead
    assert "shape/.gitignore" not in ahead, ahead

    refused = update_shape(standard, root, "apply", "--yes")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "    .gitattributes: pinned but absent" in refused.stderr
    assert "    shape/.gitignore" not in refused.stderr, refused.stderr
    assert "Remediation: .gitattributes is pinned and gone" in refused.stderr
    assert "re-run this with --accept-local" not in refused.stderr

    result = doctor(standard, root, "--json")
    assert json.loads(result.stdout)["verdict"] == \
        "DRIFTED (1 copy-missing, 1 merged-away)", result.stdout
    pins_row = rows_of(result)["pins"]
    assert "merged_away" not in pins_row["detail"], pins_row
    assert "update-shape.py" not in pins_row["next"], pins_row


@WINDOWS_SKIP
@pytest.mark.parametrize("linked", [
    pytest.param("contracts/shape-pin.yaml", id="pin-at-a-link"),
    pytest.param("contracts", id="contracts-directory-link"),
    pytest.param("project.yaml", id="manifest-at-a-link"),
])
def test_the_pins_row_keeps_the_gate_while_check_refuses_a_linked_record(
        standard, root, tmp_path, linked):
    """Both copies merged away in a root that keeps its pin, the
    `contracts` directory above it, or its manifest as a committed symlink
    (#286). `check` refuses such a root, `update-rewrite-symlink`, before it
    classifies a row, so the `pins` row named a `check` that exits 2 and
    said it was the step the `shape currency` row names, while that row
    named replacing the link. The `pins` row keeps the gate; with the link
    replaced and committed, the doctor run again names `check`."""
    merge_away(root, *MERGED.values())
    end = keep_as_committed_link(root, linked, tmp_path)

    checked = update_shape(standard, root, "check")
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert "REFUSED update-rewrite-symlink" in checked.stderr, checked.stderr

    rows = rows_of(doctor(standard, root, "--json"))
    pins_row, currency = rows["pins"], rows["shape-currency"]
    assert pins_row["status"] == "FINDING", pins_row
    assert "merged_away" not in pins_row["detail"], pins_row
    assert "update-shape.py" not in pins_row["next"], pins_row["next"]
    assert "merged-away" not in pins_row["reason"], pins_row["reason"]
    assert currency["detail"]["error"] == "update-rewrite-symlink", currency
    # No NEXT: replacing the link is a person's act, said in the `why` (#548).
    assert currency["next"] is None, currency
    assert currency["why"].startswith(f"replace {linked} "), currency["why"]

    (root / linked).unlink()
    shutil.move(str(end), str(root / linked))
    commit_all(root, f"keep {linked} where it stands, not as a link")
    pins_row = rows_of(doctor(standard, root, "--json"))["pins"]
    assert pins_row["detail"]["merged_away"] == MERGED, pins_row
    assert "update-shape.py" in pins_row["next"], pins_row["next"]


def test_a_deletion_not_yet_committed_comes_back_from_head(standard, root):
    """`rm`, then `apply`: the common way to meet `copy-missing` (review of
    PR #512, NIT-2). No commit removed the copy, so the parent of the commit
    that removed it is no exit, and `git log -1 -- <path>` names the commit
    that ADDED it. The remediation names both exits, and the one for a
    deletion not yet committed, run as it names it, puts the copy back:
    `check` then has nothing to do, and nothing was written before."""
    (root / ".gitattributes").unlink()
    before = pin_files(root)
    head = git("rev-parse", "HEAD", cwd=root).stdout
    manifest = (root / "project.yaml").read_bytes()

    refused = update_shape(standard, root, "apply", "--yes")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "REFUSED update-conflict" in refused.stderr, refused.stderr
    assert "    .gitattributes: pinned but absent" in refused.stderr
    assert ("Put each copy back from this project's own history: a deletion "
            "not yet committed comes back with `git checkout HEAD -- <path>` "
            "in the project, and a committed one from the parent of the "
            "commit that removed it, which `git log -1 -- <path>` names.") \
        in refused.stderr, refused.stderr
    after = (pin_files(root), git("rev-parse", "HEAD", cwd=root).stdout,
             (root / "project.yaml").read_bytes())
    assert after == (before, head, manifest), \
        "the refused apply wrote something"

    git("checkout", "HEAD", "--", ".gitattributes", cwd=root)
    checked = update_shape(standard, root, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "nothing to do" in checked.stdout, checked.stdout


def test_the_currency_rows_counts_name_a_merged_away_row(standard, root):
    """The `shape currency` row's reason counts a merged-away row (review of
    PR #512, NIT-3): it counted the five original states alone, so one such
    row read `10 unchanged / 0 upstream-changed / ...` over eleven rows and
    named its path under no count, in the row whose `apply` drops it. Its
    counts now sum to the rows."""
    merge_away(root, ".gitignore")
    currency = rows_of(doctor(standard, root, "--json"))["shape-currency"]
    assert_the_counts_sum_to_the_rows(currency, " / 1 merged-away")


def assert_the_counts_sum_to_the_rows(currency: dict, tail: str) -> None:
    """The `shape currency` row's printed counts end with `tail` and add up
    to every row `check` classified (`detail.counts`)."""
    summary = currency["reason"].split(" (pinned ", 1)[0]
    assert summary.endswith(tail), currency["reason"]
    said = {state: int(count) for count, state in
            (part.split(" ", 1) for part in summary.split(" / "))}
    assert sum(said.values()) == sum(currency["detail"]["counts"].values()), \
        (said, currency["detail"]["counts"])


#: A pinned copy at its own name that nothing reads as it runs, so keeping
#: it as a link changes no gate's answer: `check` calls it `copy-is-link`.
LINKED_COPY = "AGENTS-shape.md"


@pytest.fixture
def linked_beside_merged(standard, root, tmp_path) -> dict:
    """#676's root: `shape/Makefile` merged away and `AGENTS-shape.md` kept
    as a committed symlink to the same bytes. The gate's one finding is the
    merged-away row's; `check` says REFUSAL AHEAD over the link, which this
    asserts first, and the doctor's `--json` rows."""
    merge_away(root, "Makefile")
    keep_as_committed_link(root, LINKED_COPY, tmp_path)
    checked = update_shape(standard, root, "check")
    states = verdicts(checked.stdout)
    assert states["shape/Makefile"] == "merged-away", checked.stdout
    assert states[LINKED_COPY] == "copy-is-link", checked.stdout
    assert f"REFUSAL AHEAD: `apply` will refuse while these are unresolved " \
        f"— {LINKED_COPY}" in checked.stdout, checked.stdout
    return rows_of(doctor(standard, root, "--json"))


def assert_the_pins_row_keeps_its_gate(pins_row: dict, ahead: dict) -> None:
    """The `pins` row beside a REFUSAL AHEAD `ahead` (#676): its NEXT is the
    gate, not `check`, its reason names what `check` says, merged-away and
    REFUSAL AHEAD both, and no `apply` that drops a row."""
    assert pins_row["detail"]["refusal_ahead"] == ahead, pins_row
    assert "update-shape.py" not in pins_row["next"], pins_row["next"]
    assert "the `apply` it prints drops" not in pins_row["reason"], \
        pins_row["reason"]
    said = ", ".join(f"{path} ({why})" for path, why in ahead.items())
    assert f"reports it `merged-away`, but it also says REFUSAL AHEAD over " \
        f"{said}" in pins_row["reason"], pins_row["reason"]


@WINDOWS_SKIP
def test_the_pins_row_keeps_the_gate_beside_a_copy_kept_as_a_link(
        linked_beside_merged):
    """A pinned COPY kept as a link beside a merged-away row (#676): no
    record `linked_record` asks about, so the `pins` row named `check` and
    said the `apply` it prints drops the row, while `check` says REFUSAL
    AHEAD over the link and that `apply` exits 2 writing nothing."""
    assert_the_pins_row_keeps_its_gate(linked_beside_merged["pins"],
                                       {LINKED_COPY: "copy-is-link"})


@WINDOWS_SKIP
def test_the_currency_rows_counts_name_every_state_check_counts(
        linked_beside_merged):
    """The `shape currency` reason counted the five original states and
    `merged-away` alone (#676): over this root it read `... / 1 merged-away`
    over twelve rows, eleven counted, where `check` prints `merged-away 1
    copy-is-link 1`. Every state of `ORDER` with a count now follows the
    five, in that order."""
    assert_the_counts_sum_to_the_rows(linked_beside_merged["shape-currency"],
                                      " / 1 merged-away / 1 copy-is-link")


def test_the_pins_row_keeps_the_gate_beside_a_hard_linked_pin(standard, root,
                                                              tmp_path):
    """The other half of `check`'s REFUSAL AHEAD (#422): the pin, which the
    re-pin rewrites, with a second name. `apply` refuses it,
    `update-rewrite-hardlink`, so it drops no merged-away row either."""
    merge_away(root, "Makefile")
    os.link(root / SHAPE_PIN, tmp_path / "pin-elsewhere.yaml")
    checked = update_shape(standard, root, "check")
    assert "REFUSAL AHEAD: `apply` will refuse to rewrite these in place" \
        in checked.stdout, checked.stdout
    rows = rows_of(doctor(standard, root, "--json"))
    assert_the_pins_row_keeps_its_gate(rows["pins"], {SHAPE_PIN: "hard-link"})


def test_the_pins_row_keeps_the_gate_where_check_would_fetch(standard, root,
                                                             moved, tmp_path):
    """Run from a partial clone of the standard one commit on, which lacks
    the pinned commit's copy of the Makefile template (#683), the source
    of `shape/Makefile`, a row `check` reads: its question cannot be asked
    without fetching, so the `pins` row keeps its gate and says nothing
    of `apply`, and nothing is fetched."""
    merge_away(root, ".gitignore")
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial")
    result, before, after = doctored(clone, root)
    assert after == before, "the doctor fetched"
    assert_the_pins_row_is_the_gate(rows_of(result)["pins"])


def assert_the_pins_row_is_the_gate(pins_row: dict) -> None:
    """The `pins` row as the gate printed it: no `merged_away`, and a NEXT
    that is not `update-shape.py` (#676, #755)."""
    assert "merged_away" not in pins_row["detail"], pins_row
    assert "update-shape.py" not in pins_row["next"], pins_row["next"]


def test_the_pins_row_keeps_the_gate_where_check_refuses_the_standard(
        standard, root, tmp_path):
    """Run from a standard of another history, which does not carry the
    commit the pin names: `check` refuses it, `update-revision-unresolvable`,
    before it classifies a row, so `refusals_ahead` cannot ask its question
    and the `pins` row keeps its gate (#755). Answered as "nothing ahead",
    the row named a `check` that exits 2."""
    merge_away(root, "Makefile")
    stranger = standard_of_another_history(standard, tmp_path)
    checked = update_shape(stranger, root, "check")
    assert "REFUSED update-revision-unresolvable" in checked.stderr, \
        checked.stdout + checked.stderr
    assert_the_pins_row_is_the_gate(
        rows_of(doctor(stranger, root, "--json"))["pins"])


#: The pinned copy the `both` and `upstream-removed` cases move upstream,
#: and the file the `unmapped` case pins that no upstream path maps to.
MOVED_COPY = "AGENTS-shape.md"
OWN_FILE = "notes-of-our-own.md"


def pinned_as_it_stands(root: Path, path: str) -> None:
    """`path`'s row in the shape pin records the root's bytes as they stand,
    a row added where the pin has none, and committed: what `apply
    --accept-local` leaves for a kept edit, written here without it. The
    project's own `validate-pins.py` then sees the row match."""
    pin = root / SHAPE_PIN
    digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
    row = f'  - path: {path}\n    sha256: "{digest}"\n'.encode()
    held = pin.read_bytes()
    pattern = (rb'(?m)^  - path: "?' + re.escape(path.encode())
               + rb'"?\n    sha256: "?[0-9a-f]{64}"?\n')
    written, count = re.subn(pattern, lambda _found: row, held)
    if not count:
        assert held.count(b"\nfiles:\n") == 1, held
        written = held.replace(b"\nfiles:\n", b"\nfiles:\n" + row)
    pin.write_bytes(written)
    commit_all(root, f"Pin {path} as it stands")


def both_beside(standard: Path, root: Path, tmp_path: Path) -> Path:
    """The project's kept edit of a copy, pinned as it stands, and the
    standard's own edit of that copy one commit on: `both`."""
    copy = root / MOVED_COPY
    copy.write_bytes(copy.read_bytes() + b"\nA line the project kept.\n")
    pinned_as_it_stands(root, MOVED_COPY)
    return standard_ahead(standard, tmp_path,
                          f"templates/assembly-root/{MOVED_COPY}",
                          "\nA line the standard added.\n",
                          "The standard edits a copy the project kept")


def upstream_removed_beside(standard: Path, root: Path,
                            tmp_path: Path) -> Path:
    """The standard one commit on, without a copy the pin names:
    `upstream-removed`."""
    ahead = tmp_path / "standard-ahead"
    shutil.copytree(standard, ahead, symlinks=True)
    git("rm", "-q", "--", f"templates/assembly-root/{MOVED_COPY}",
        cwd=ahead)
    commit_all(ahead, "The standard removes a copy")
    return ahead


def unmapped_beside(standard: Path, root: Path, tmp_path: Path) -> Path:
    """A pin row for a file of the project's own, which no path of the
    standard's maps to: `unmapped`."""
    (root / OWN_FILE).write_bytes(b"# Notes of our own\n")
    pinned_as_it_stands(root, OWN_FILE)
    return standard


#: Each conflict `check` names beside a merged-away row, as `(the builder
#: that makes it and returns the standard to run from, the pinned path)`.
CONFLICTS_BESIDE = {
    "both": (both_beside, MOVED_COPY),
    "upstream-removed": (upstream_removed_beside, MOVED_COPY),
    "unmapped": (unmapped_beside, OWN_FILE),
}


@pytest.mark.parametrize("state", list(CONFLICTS_BESIDE))
def test_the_pins_row_keeps_the_gate_beside_each_conflict_check_names(
        standard, root, tmp_path, state):
    """`both`, `upstream-removed` and `unmapped` beside a merged-away row
    (#755): `check` names each under REFUSAL AHEAD, so the `pins` row keeps
    its gate and names it, and the `apply` `check` prints, pasted, exits 2,
    `update-conflict`, as the row says. Only `copy-is-link` was tested, so
    a `refusals_ahead` that counted it alone passed every test."""
    merge_away(root, "Makefile")
    build, path = CONFLICTS_BESIDE[state]
    upstream = build(standard, root, tmp_path)
    checked = update_shape(upstream, root, "check")
    assert verdicts(checked.stdout)[path] == state, checked.stdout
    rows = rows_of(doctor(upstream, root, "--json"))
    assert_the_pins_row_keeps_its_gate(rows["pins"], {path: state})
    line = next_line_of(checked.stdout)
    argv = shlex.split(line[len("NEXT  "):])
    applied = run_script(upstream / "update-shape.py", *argv[2:])
    assert applied.returncode == 2, applied.stdout + applied.stderr
    assert "REFUSED update-conflict" in applied.stderr, applied.stderr


def test_the_plans_follow_up_says_what_happens_to_the_row(adopted_here):
    """The follow-up for each pinned collision copy says that its row goes,
    and by which step; `shape/README.md`, a rendered file with no row, is
    told nothing about one."""
    follow_ups = load_yaml(adopted_here["plan"])["follow_ups"]
    for path, original in MERGED.items():
        (said,) = [item for item in follow_ups
                   if item.startswith(f"merge {path} into {original}")]
        assert (f"Then remove {path}: `update-shape.py check` reports its "
                "pin row `merged-away`, and `apply` drops the row") in said, \
            said
    (readme,) = [item for item in follow_ups
                 if item.startswith("merge shape/README.md into README.md")]
    assert "pin row" not in readme, readme


def test_a_merged_away_attributes_copys_row_goes_and_the_root_file_stays(
        standard, adopted_with_attributes, tmp_path):
    """The `.gitattributes` copy, end to end (#471, #502). A source keeping
    its own root `.gitattributes` gets the shape's copy pinned beside it as
    `shape/.gitattributes`, and its follow-up said to merge the rest of that
    copy only if the whole project should check out with LF, then returned
    before the sentence every other pinned copy's follow-up carries, so
    nothing said what removing the copy does to its row. It says it now, in
    the same words, and they hold: the copy merged into the root file and
    removed, `check` calls its row `merged-away`, its NEXT pasted drops that
    row and nothing else, the root file stays as the merge left it, block
    and all, and the gate and the doctor are green."""
    copy = f"shape/{ATTRIBUTES}"
    follow_ups = load_yaml(adopted_with_attributes["plan"])["follow_ups"]
    opening = f"keep the block at the end of {ATTRIBUTES}"
    (said,) = [item for item in follow_ups if item.startswith(opening)]
    assert said.endswith(
        "should check out with LF, and only then remove "
        f"{copy}: `update-shape.py check` reports its pin row `merged-away`, "
        "and `apply` drops the row"), said

    root = tmp_path / PROJECT
    shutil.copytree(adopted_with_attributes["clone"], root, symlinks=True)
    before = pin_files(root)
    assert copy in {path for path, _ in before}, before
    assert ATTRIBUTES not in {path for path, _ in before}, before
    merge_away(root, ATTRIBUTES)
    merged = git("show", f"HEAD:{ATTRIBUTES}", cwd=root).stdout

    checked = update_shape(standard, root, "check")
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert verdicts(checked.stdout)[copy] == "merged-away", checked.stdout
    assert "REFUSAL AHEAD" not in checked.stdout, checked.stdout
    line = next_line_of(checked.stdout)
    argv = shlex.split(line[len("NEXT  "):])
    assert argv[1:3] == ["update-shape.py", "apply"], line
    applied = run_script(standard / "update-shape.py", *argv[2:])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert f"  dropped  {copy} " in applied.stdout, applied.stdout

    assert pin_files(root) == [row for row in before if row[0] != copy], \
        "the copy's row goes, and nothing else in the pin moves"
    committed = set(git("show", "--name-only", "--format=", "HEAD",
                        cwd=root).stdout.split())
    assert ATTRIBUTES not in committed, committed
    assert git("show", f"HEAD:{ATTRIBUTES}", cwd=root).stdout == merged
    ran = gate(root, "validate-pins.py")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    again = doctor(standard, root)
    assert verdict_line(again).startswith("COMPLIANT   (exit 0)"), again.stdout
