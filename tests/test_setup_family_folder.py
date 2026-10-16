# SPDX-License-Identifier: Apache-2.0
"""`setup-project.py` detects the family FOLDER `family.py init` makes,
whatever `name:` the holder's manifest carries (#696).

`scripts/family.py init --family Quill --name QuillWorks` lays out
`Quill/Quill/family.yaml` holding `name: "QuillWorks"` and `repository:
<org>/Quill`: `--family` is the holder REPOSITORY's name and lays the
folders out, and `name:` is only a display name (#629 made `siblings.py` and
the holder's README say so). `setup-project.py`'s `family_folder_here` asked
`name:` instead, so the folder `init` made was not recognised - AGENTS.md's
"standing in a family FOLDER is DETECTED and said in the plan with no flag"
was false for every family made with `--name`: the plan lost its family line
and the hand-over its `family.py add`, and the refusal to nest one family
inside another was never asked. `QuillWorks/QuillWorks`, the layout the
holder's README used to describe and `siblings.py` refuses, WAS recognised.

The rule now is `siblings.py`'s `family_folder_name`: the basename of the
manifest's `repository:`, and `name:` only where there is no `repository:`.
That hand-built old layout is therefore no longer DETECTED (no plan line, no
`family.py add`), but the nested-family REFUSAL is still asked of it, in
main's words, because `--family Quill` typed from inside it would file one
family inside another (`display_name_folder_here`).
The rows go through the function itself (the fast ones) and through the
whole run (the ones that read the plan a person reads), and one row builds
its folder with the real `family.py init` so the fixture cannot drift from
what `init` writes. NO NETWORK: every remote is `--local-remote-dir`.
"""

from __future__ import annotations

import pytest

from conftest import REPO, run_script

from test_setup_project_py import (entry_point_module, make_family_folder,
                                   run_entry)

ORG = "demoorg"
FAMILY_PY = REPO / "scripts" / "family.py"

#: The plan's own line for a detected folder, and the `family.py add` the
#: hand-over names, exactly as `resolve_family` and `family_next_command`
#: print them. Searched for as a whole line / a whole command.
STANDING = ("family       standing in the %s family folder; the project "
            "lands beside its holder")
ADD = "scripts/family.py add --family-root %s --member demoorg/Sample"


def family_folder(root, folder: str, name: str, repository: str | None = None):
    """`<root>/<folder>/<folder>/family.yaml`, with `repository:` when given.

    Built on `test_setup_project_py.make_family_folder`, which writes the
    `kind:` and the `name:`, so the one fixture stays the one the rest of the
    family-folder tests read; the `repository:` line `init` writes after
    them is appended. Returns the family FOLDER, which is what a person
    stands in and what `--into` is pointed at.
    """
    made = make_family_folder(root, family=folder, name=name)
    if repository:
        manifest = made / folder / "family.yaml"
        manifest.write_text(manifest.read_text(encoding="utf-8")
                            + "repository: %s\n" % repository,
                            encoding="utf-8")
    return made


def setup_in(folder, tmp_path, *flags: str):
    """The whole run from inside `folder`, stopped by nothing: `--yes`."""
    return run_entry("Sample", "--yes", "--org", ORG, *flags,
                     "--local-remote-dir", str(tmp_path / "remotes"),
                     "--into", str(folder))


#: `(id, folder, name:, repository:, what the function says)`. The first
#: three are the issue's own layouts; the rest are the edges of the rule.
LAYOUTS = [
    # What `init --family Quill --name QuillWorks` makes: the repository
    # names the folder, `name:` is a display name.
    ("init-layout-with-a-display-name", "Quill", "QuillWorks",
     "demoorg/Quill", "Quill"),
    # The layout the holder's README used to tell a person to make: the
    # folder is the DISPLAY name, which `siblings.py` refuses, so setup does
    # not call it a family folder either.
    ("old-display-name-layout", "QuillWorks", "QuillWorks",
     "demoorg/Quill", ""),
    # The usual family: `name:` and the repository are one string.
    ("name-is-the-repository", "InkRouter", "InkRouter",
     "demoorg/InkRouter", "InkRouter"),
    # A bare repository, as `repo_basename` reads one.
    ("bare-repository", "Quill", "QuillWorks", "Quill", "Quill"),
    # No `repository:` to ask: `name:` answers, as it always did.
    ("no-repository-name-agrees", "InkRouter", "InkRouter", None,
     "InkRouter"),
    ("no-repository-name-differs", "Quill", "QuillWorks", None, ""),
    # `siblings.py` compares the basename as written, so setup does too: a
    # different case, or a repository with a trailing slash, is no folder.
    ("repository-case-differs", "quill", "Quill", "demoorg/Quill", ""),
    ("repository-trailing-slash", "Quill", "QuillWorks", "demoorg/Quill/", ""),
]


@pytest.mark.parametrize("folder,name,repository,expected",
                         [row[1:] for row in LAYOUTS],
                         ids=[row[0] for row in LAYOUTS])
def test_family_folder_here_asks_the_repository_not_the_display_name(
        tmp_path, folder, name, repository, expected):
    """THE ISSUE'S THREE ROWS, and the edges of the rule, asked of the
    function itself: it answers with the folder's name or with nothing."""
    parent = family_folder(tmp_path / "work", folder, name, repository)
    module = entry_point_module()
    assert module.family_folder_here(REPO, parent) == expected


def test_the_plan_says_the_folder_init_made_is_a_family_folder(tmp_path):
    """The plan line and the `family.py add` the hand-over names, for a
    family whose `name:` is not its repository's. Neither was printed."""
    folder = family_folder(tmp_path / "work", "Quill", "QuillWorks",
                           "demoorg/Quill")
    result = setup_in(folder, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert STANDING % "Quill" in result.stdout
    assert ADD % (folder / "Quill") in result.stdout
    assert "no family.yaml there yet" not in result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()
    assert not (folder / "Quill" / "Sample").exists(), (
        "the project was filed inside the holder clone")


def test_the_old_display_name_layout_is_a_plain_directory(tmp_path):
    """`QuillWorks/QuillWorks` holding `repository: demoorg/Quill`: the
    manifest's repository is not this folder's name, so it is another
    family's folder and not this one's - no plan line, no `family.py add`,
    the clone beside the folder's content. What `--family` typed from
    inside it does is the next test's."""
    folder = family_folder(tmp_path / "work", "QuillWorks", "QuillWorks",
                           "demoorg/Quill")
    result = setup_in(folder, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    # `[ok] family` is the plan's own line; a bare `family` would match the
    # naming validator's `--explain` table, which names every form.
    assert "[ok] family" not in result.stdout
    assert "scripts/family.py add" not in result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()


#: `(id, folder, name:, repository:, --family)`: where a person stands, and
#: the family they name from there. The first two stand in the folder
#: `init --name` made, naming another family and naming the DISPLAY name
#: (the likeliest mistake: main nested both, `Quill/Other/Sample` and
#: `Quill/QuillWorks/Sample`, with three remotes). The last two stand in the
#: hand-built old layout, which is not detected but is still refused.
NESTED = [
    ("init-layout-another-family", "Quill", "QuillWorks", "demoorg/Quill",
     "Other"),
    ("init-layout-the-display-name", "Quill", "QuillWorks", "demoorg/Quill",
     "QuillWorks"),
    ("old-layout-the-holders-own-name", "QuillWorks", "QuillWorks",
     "demoorg/Quill", "Quill"),
    ("old-layout-another-family", "QuillWorks", "QuillWorks",
     "demoorg/Quill", "Other"),
]


@pytest.mark.parametrize("folder,name,repository,family",
                         [row[1:] for row in NESTED],
                         ids=[row[0] for row in NESTED])
def test_a_family_is_refused_inside_a_family_folder(tmp_path, folder, name,
                                                    repository, family):
    """The nested-family refusal, in main's own words: both names, both ways
    out, exit 2, and nothing created - asked of the folder `init` made and,
    since #696 stopped detecting it, still asked of the old display-name
    layout, where `--family Quill` or `--family Other` would otherwise file a
    second family inside the first and make three repositories."""
    stood_in = family_folder(tmp_path / "work", folder, name, repository)
    result = setup_in(stood_in, tmp_path, "--family", family)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "--family %s, but " % family in result.stderr
    assert "%s family folder" % folder in result.stderr
    assert "never nested inside a family" in result.stderr
    assert "`cd` out of %s" % folder in result.stderr
    assert "drop --family and let Sample land beside %s's holder" % folder \
        in result.stderr
    assert not (tmp_path / "remotes").exists()
    assert not (stood_in / family).exists()
    assert not (stood_in / "Sample").exists()


def test_a_manifest_of_another_name_refuses_nothing(tmp_path):
    """The refusal asks the old layout only where the manifest's `name:` IS
    the folder's: `Zephyr/Zephyr/family.yaml` holding `name: Other` is not a
    family folder by either rule, so `--family Orbit` from inside it is the
    plain-directory run it always was and lands one level down."""
    folder = family_folder(tmp_path / "work", "Zephyr", "Other")
    result = setup_in(folder, tmp_path, "--family", "Orbit")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (folder / "Orbit" / "Sample" / "project.yaml").is_file()


def test_a_folder_made_by_family_py_init_with_a_name_is_detected(tmp_path):
    """The layout from the tool that makes it, not from a fixture: `family.py
    init --family Quill --name QuillWorks`, then the scaffold from inside
    the folder it made."""
    work = tmp_path / "work"
    work.mkdir()
    made = run_script(FAMILY_PY, "init", "--org", ORG, "--family", "Quill",
                      "--name", "QuillWorks", "--created-by", "Test Human",
                      "--created-on", "2026-10-16", "--into", str(work),
                      "--local-remote-dir", str(tmp_path / "init-remotes"))
    assert made.returncode == 0, made.stderr + made.stdout
    folder = work / "Quill"
    assert (folder / "Quill" / "family.yaml").is_file()
    result = setup_in(folder, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert STANDING % "Quill" in result.stdout
    assert ADD % (folder / "Quill") in result.stdout
    assert (folder / "Sample" / "project.yaml").is_file()
