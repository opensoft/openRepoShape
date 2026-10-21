# SPDX-License-Identifier: Apache-2.0
"""What the comment above `visibility:` says the field records (#913, U039).

`templates/assembly-root/project.yaml` said "For a scaffolded project this is
all three repositories' visibility". It is not wherever a repository was
reused: the run records the visibility IT asked for (`--visibility`, which is
`private` unless the run was given another, or the reused root's own where it
was given none), and a repository it reuses keeps the visibility it has,
because no run changes one. `family.yaml` is the same for the holder: a reused
PUBLIC holder under the default `--visibility private` records `private`, as
`test_free_plan_hint_reads.py` holds.

Brett Heap ruled on 2026-10-21T10:39:44Z that the WORDS change and no code
does ("U039 and U037: take your recommendations"): `visibility:` is "the
visibility this run asked for". The behaviour the words describe is pinned
where it is run, by `test_reuse_visibility.py` (the reused root's own is
inherited, and an explicit `--visibility` wins) and by
`test_free_plan_hint_reads.py` (a family keeps the run's); this file pins the
words, which no test did. The comments are copied into every project and
family this tool makes, so a word that goes back says again what a reused
repository does not do.

NO NETWORK, NO GITHUB, NO PROCESS: the two templates, read as text.
"""

from __future__ import annotations

import pytest

from conftest import REPO

ASSEMBLY = REPO / "templates" / "assembly-root" / "project.yaml"
FAMILY = REPO / "templates" / "family-root" / "family.yaml"
BOTH = pytest.mark.parametrize("path", [ASSEMBLY, FAMILY],
                               ids=["project.yaml", "family.yaml"])

#: The line the comment sits on.
FIELD = 'visibility: "{{VISIBILITY}}"'


def comment_above_visibility(path) -> str:
    """The comment block directly above `visibility:`, its `#` and its line
    breaks gone, so a phrase is found whichever line it was wrapped on."""
    lines = path.read_text(encoding="utf-8").splitlines()
    at = lines.index(FIELD)
    block: list[str] = []
    for line in reversed(lines[:at]):
        if not line.startswith("#"):
            break
        block.append(line.lstrip("#").strip())
    return " ".join(reversed(block))


@BOTH
def test_visibility_is_what_the_run_asked_for(path):
    """The key claim of #913's ruling, in both manifests: what is recorded
    is what the run was asked for, not a reading of any repository, and a
    reused repository keeps its own, which no run changes."""
    comment = comment_above_visibility(path)
    for phrase in ("ASKED FOR", "not a reading of any repository",
                   "`--visibility`", "`private`",
                   "REUSES keeps the visibility it already has",
                   "changes no repository's visibility"):
        assert phrase in comment, (phrase, comment)


@BOTH
def test_visibility_is_not_called_the_repositories_visibility(path):
    """The sentence the ruling replaced, in the words it used."""
    comment = comment_above_visibility(path)
    assert "this is all three repositories' visibility" not in comment
    assert "all three repositories" not in comment, comment


@BOTH
def test_github_is_still_the_source_of_truth(path):
    comment = comment_above_visibility(path)
    assert "NOT ENFORCED HERE" in comment, comment
    assert "GitHub is the source of truth" in comment, comment


def test_the_scaffold_comment_says_a_reused_root_is_inherited():
    """The default is `private` only where there is no reused root GitHub
    gave a visibility for, as `_leg_visibility` has it."""
    comment = comment_above_visibility(ASSEMBLY)
    assert ("the visibility of an existing assembly root the run reuses, "
            "as GitHub gave it") in comment, comment


def test_the_in_place_adoption_sentence_holds():
    """Adoption creates the two legs at `plan --visibility` and keeps the
    source's root as it is, which is what the sentence says and the ruling
    left standing."""
    comment = comment_above_visibility(ASSEMBLY)
    for phrase in ("For an in-place adoption it is the value the two NEW "
                   "legs were created with",
                   "keeps whatever visibility it already had on GitHub, "
                   "unchanged by this tool"):
        assert phrase in comment, (phrase, comment)


def test_the_family_comment_says_it_is_the_holders_alone():
    """`family.yaml` records the HOLDER's, as `family.py init` fills it from
    `--visibility`; a member is a project, with a `visibility:` of its own."""
    comment = comment_above_visibility(FAMILY)
    assert "It is the HOLDER's alone" in comment, comment
    assert "a holder the run REUSES keeps" in comment, comment
