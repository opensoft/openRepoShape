# SPDX-License-Identifier: Apache-2.0
"""Two expressions that a mutant could change without failing a test (#664).

Both are test gaps found in review, and neither is user-facing: the code is
right, and nothing said so. Each case below fails when its expression is
changed, and passes on the code as it stands.

#434 (PR #633), `templates/assembly-root/scripts/validate-pins.py`. The
workflow scan reads every `.yml` and `.yaml` child of `.github/workflows/`,
and its child check is `_is_a(path, stat.S_ISREG)`: a child that is not a
REGULAR FILE is not a workflow and is skipped, as it always was. A mutant that
replaced the kind with `lambda mode: True` left every validate-pins suite
passing (130 tests on main `8062810d`; the issue counted 102), because no test
put a directory at a workflow's name. Over a root holding a directory named
`.github/workflows/sub.yml` the code says `pins ok`; the mutant read the
directory as a file and said `REFUSED workflow-unreadable:
.github/workflows/sub.yml: cannot be read (Is a directory)`, a refusal of a
tree that has nothing unreadable in it.

THE SYMLINK ROWS ARE CONTROLS OF THE SAME RULE, AND KILL A DIFFERENT MUTANT.
`_is_a` answers False to a `stat` that found nothing to open (ENOENT, ELOOP)
BEFORE it asks the kind, so a dangling or a looping link is skipped whatever
the kind check says, and the `lambda mode: True` mutant passes both. They pin
the other half of the child check: a child whose `stat` finds nothing is still
"no workflow" and not a file that cannot be read. A child check that let that
`OSError` through (a bare `path.stat()` for `_is_a`) refuses `dangling.yml`
as `cannot be read (No such file or directory)` and `loop.yml` as `cannot be
read (Too many levels of symbolic links)`, which only these two rows say.

#454 (PR #642), `templates/family-root/scripts/siblings.py`. Both reports open
with `siblings: <name> (<root>) — N member(s)` and then a `family folder`
line, and every value on them goes through `spelled`: the holder's path is as
much a disk's text as the manifest's `name:`. `test_siblings_family_name.py`
always puts its holder at a plain path (`in_family_folder(family_template,
tmp_path, PLAIN)`), so a mutant that printed the root raw in the placement
header left all 150 of its tests passing. Here the holder stands under a
folder whose name holds a character a terminal must not be handed (U+2028,
U+202E, ESC), the holder stays in a folder named after its repository so the
run still passes its folder check, and each report must print the path with
that character written out and not once raw.

NO NETWORK AND NO GITHUB: a scaffolded assembly root and a family holder from
`family.py init` into local bare remotes, both dry runs, and the session `gh`
guard (`tests/conftest.py`). The validate-pins rows are mode-free, so they run
as root and on every platform; the symlink rows skip where a link cannot be
made.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, git
from test_bootstrap_spelling import (  # noqa: F401
    DASH, NEVER_RAW, family_template,
)
from test_siblings_family_name import (
    MODES, PLAIN, PYTHON_AS_MAKE, in_family_folder, sib,
)
from test_validate_pins_unreadable_workflow import WORKFLOWS, validate
# A fixture is used by being named in this module's namespace, which is what
# these two imports are for: the root with `legs.yml` committed, naming the
# spec leg at its pinned commit, and the project's own `validate-pins.py` as
# a module.
from test_validate_pins_unreadable_workflows_dir import (  # noqa: F401
    with_leg_workflow,
)
from test_validate_pins_without_git import validator  # noqa: F401


# --- #434: a workflow child that is no regular file is skipped ---------------

def make_directory(root: Path, name: str) -> None:
    """A directory at a workflow's name: `stat` answers, and it is no file."""
    (root / WORKFLOWS / name).mkdir()


def link_to(target: str):
    """A maker of a symbolic link at a workflow's name, pointing at `target`
    (relative, so it is read from the link's own directory): skipped where
    this machine allows no link, as Windows does without the privilege."""
    def make(root: Path, name: str) -> None:
        try:
            (root / WORKFLOWS / name).symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"this machine makes no symbolic link: {exc}")
    return make


@pytest.mark.parametrize("name, make", [
    pytest.param("sub.yml", make_directory, id="directory-yml"),
    pytest.param("sub.yaml", make_directory, id="directory-yaml"),
    pytest.param("dangling.yml", link_to("no-such-workflow.yml"),
                 id="dangling-symlink"),
    pytest.param("loop.yml", link_to("loop.yml"), id="looping-symlink"),
])
def test_a_workflow_child_that_is_no_regular_file_is_skipped_not_refused(
        validator, with_leg_workflow, name, make):
    """The scan returns the references it returned before the entry was made,
    the leg's among them and NOTHING MORE, and the run says `pins ok`: a
    directory is no workflow (`S_ISREG`), and a link with nothing at its end
    (dangling, or pointing at itself) is no workflow either (`stat` answers
    ENOENT or ELOOP). None is a file this user cannot read, so none is
    refused. What is read before the entry is made is the control: the leg's
    own reference is one of the references the root has."""
    root = with_leg_workflow
    pinned = git("rev-parse", "HEAD:spec", cwd=root).stdout.strip()
    before = validator._workflow_refs(root)
    assert (root / WORKFLOWS / "legs.yml", f"{ORG}/{PROJECT}-spec",
            pinned) in before, before
    make(root, name)
    assert os.path.lexists(root / WORKFLOWS / name), name
    assert validator._workflow_refs(root) == before
    result = validate(root)
    assert "Traceback" not in result.stderr, result.stderr
    assert "workflow-unreadable" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pins ok" in result.stdout, result.stdout


# --- #454: the holder's root and folder are spelled in both headers ----------

#: ESC is a control character, and Windows refuses one in a file name.
NO_CONTROL_NAMES = pytest.mark.skipif(
    os.name == "nt", reason="Windows refuses a control character in a name")
#: `(a folder name, that name as the header must print it)`. U+2028 and U+202E
#: are legal in a folder name on every disk this runs on. Each is spelled by
#: code point here, so no invisible character sits in this file.
FOLDERS = [
    pytest.param("a\u2028b", "a\\u2028b", id="line-separator"),
    pytest.param("a\u202eb", "a\\u202eb", id="bidi-override"),
    pytest.param("a\x1b[31mb", "a\\x1b[31mb", id="esc",
                 marks=NO_CONTROL_NAMES),
]


@pytest.mark.parametrize("args, last", MODES)
@pytest.mark.parametrize("folder, escaped", FOLDERS)
def test_the_holders_root_and_folder_are_spelled_in_both_headers(
        family_template, tmp_path, folder, escaped, args, last):
    """THE ROOT is the header's own `(<root>)`, and THE FOLDER is its
    `family folder` line: `_run_placement` prints both for `make siblings`,
    and `dispatch_all` for `make park` and `make resume`. The holder sits at
    `<tmp>/<folder>/InkRouter/InkRouter`, so both paths hold the exotic name
    and the folder check, which wants a folder named for the repository,
    passes. Exit 0, nothing on stderr, the first line and the `family folder`
    line each the path with the character written out (`\\u2028`, `\\u202e`,
    `\\x1b`), the run's own last line, and not one character a terminal must
    not be handed anywhere in the output."""
    holder = in_family_folder(family_template, tmp_path / folder, PLAIN)
    code, out, err = sib(holder, *args, tmp_path=tmp_path,
                         changes=PYTHON_AS_MAKE)
    assert code == 0, out + err
    assert err == "", err
    root, parent = str(holder.resolve()), str(holder.resolve().parent)
    assert folder in root, "fixture drift: the holder is not under the folder"
    lines = out.split("\n")
    assert lines[0] == (f"siblings: {PLAIN} ({root.replace(folder, escaped)}) "
                        f"{DASH} 0 member(s)"), out
    assert lines[1] == (f"  family folder   {parent.replace(folder, escaped)}"
                        ), out
    assert out.endswith(last), out
    assert not NEVER_RAW & set(out), out
