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

import json
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from conftest import REPO, clone_just_pushed, git, make_source_repo, \
    run_script
from test_shape_doctor import (  # noqa: F401
    doctor, rows_of, standard, verdict_line,
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


@pytest.fixture(scope="module")
def adopted_here(standard, tmp_path_factory) -> dict:
    """`SOURCE_TREE` adopted with the standard's own `adopt-project.py`, its
    pull request merged, and a recursive clone of it."""
    base = tmp_path_factory.mktemp("merged-away")
    source = make_source_repo(base / PROJECT, tree=SOURCE_TREE, edits=())
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
    summary = currency["reason"].split(" (pinned ", 1)[0]
    assert summary.endswith(" / 1 merged-away"), currency["reason"]
    said = {state: int(count) for count, state in
            (part.split(" ", 1) for part in summary.split(" / "))}
    assert sum(said.values()) == sum(currency["detail"]["counts"].values()), \
        (said, currency["detail"]["counts"])


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
