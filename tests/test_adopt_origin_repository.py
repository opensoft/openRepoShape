# SPDX-License-Identifier: Apache-2.0
"""One reading of a source's `origin` (#521), and an organisation `plan` read
from it named by where it came from (#427).

`adopt-project.py`'s `_remote_repository` read `<org>/<repo>` with one regex,
`[:/]([^/:]+/[^/]+?)(?:\\.git)?$`, which #499's source check then compared
`--org` and `--project` with. Three spellings went wrong:

- a url ending `/` or `.git/` named nothing, so nothing was compared, and a
  mistyped `--project` planned with exit 0;
- a PATH named its last two directories, so a clone of `/srv/clones/Atlas.git`
  was the repository `clones/Atlas`, and the right `--org` was refused
  `adopt-not-the-source`;
- the same path written with backslashes, as Windows writes it, named
  nothing, so it was compared or not by its separator.

Now a url names the `<org>/<repo>` it ends in, however it ends, and a path
names no repository at all, however it is written: it is a directory on this
machine, and the repository `execute` acts on without `--local-remote-dir` is
`https://github.com/<org>/<project>.git`, which no path says anything about.
So `--org` and `--project` are not compared with a path, and `plan` says so
in a NOTE naming the repository `execute` will act on; and a path names no
organisation, so with no `--org` it is `adopt-no-org`.

With no `--org`, `plan` takes the organisation from the url and holds it to
`checked_value`. A value that is refused there is named by where it came
from, as `--elected-by` is when `git config user.name` filled it in, and the
remediation says to pass `--org` (#427).

Nothing here fetches: each `origin` is a string `plan` reads from the source's
own config. The only `gh` run here is `check`'s, in
`test_a_path_origin_is_not_compared_and_plan_says_so`: given no
`--local-remote-dir`, and once nothing before it ends `check` and the plan's
names and `org:` pass, it asks `gh repo view` once of the spec leg's repository
and once of the code leg's (#798), and off Windows the session's guard answers
each as a `gh` with no login does (`tests/gh_guard.py`). A backslash path is
plain text to git on every platform, so its rows run everywhere.
"""

from __future__ import annotations

import pytest

from conftest import git
from repo_shape import load_yaml
from test_adopt_project_is_the_source import (  # noqa: F401 - a fixture
    NOT_THE_SOURCE, PLAN, RETYPE, WHY, adopter, check, plan, source_of)

#: The remote every source here has, or is given.
ORIGIN = "origin"
#: The organisation, the source's own name, and a typo of it.
ORG, OWN, TYPO = "acme", "Atlas", "Atlsa"
#: The source's repository, as every url below names it.
REPOSITORY = f"{ORG}/{OWN}"
#: A name a url with an organisation `plan` refuses ends in.
OTHER = "Northwind"
#: What `plan` says of every `origin` that is a path. `{}` is its spelling.
NOT_COMPARED = (
    "NOTE the source's `origin` is the path `{}`, which names no repository "
    "on GitHub, so `--org` and `--project` were not compared with it.")
#: And the line after it. `{}` is `<org>/<project>`.
ACTED_ON = (
    "     `execute` without `--local-remote-dir` pushes the split to {}, opens "
    "its pull request there and sets its topic on it, so that must be the "
    "source's own repository on GitHub.")
#: `adopt-no-org`, said of every source that names no organisation.
NO_ORG = (
    "REFUSED adopt-no-org: the source's `origin` names no organisation this "
    "tool can read: it has none, its URL is not UTF-8 or ends in no "
    "`org/repo`, or it is a path, which names no repository on GitHub")
#: How `plan` names an organisation it read from the source's `origin`.
ORG_FROM_ORIGIN = ("--org (not given, so the organisation of the source's "
                   "`origin`)")


def with_origin(base, origin: str):
    """A one-commit source whose `origin` is `origin`, as it is written."""
    source = source_of(base, None)
    git("remote", "add", ORIGIN, origin, cwd=source)
    return source


def planned(base, source, project: str, org: str | None = None):
    """`plan` of `source` as `--project <project>`, and `--org <org>` where
    one is given."""
    return plan(base, source, "--project", project,
                *(("--org", org) if org else ()))


def read_as(adopter, source, origin: str) -> str | None:
    """What `_remote_repository` reads of `source` once its `origin` is
    `origin`."""
    git("remote", "set-url", ORIGIN, origin, cwd=source)
    return adopter._remote_repository(source)


# --- the reading -------------------------------------------------------------

@pytest.mark.parametrize("url", [
    f"https://github.com/{REPOSITORY}/",
    f"https://github.com/{REPOSITORY}.git/",
    f"https://github.com/{REPOSITORY}.git//",
    f"ssh://git@ssh.github.com:443/{REPOSITORY}.git/",
    f"git@github.com:{REPOSITORY}/",
    f"https://token@example.invalid:8443/{REPOSITORY}.git/",
    f"[::1]:{REPOSITORY}.git/",
], ids=["https", "https-dot-git", "two-slashes", "ssh-port", "scp",
        "credentials-port", "bracketed-host"])
def test_a_url_names_its_repository_however_it_ends(adopter, tmp_path,
                                                    url):
    """#521's third row: `$` came after `[^/]+?`, so a url ending `/` named
    nothing, and was not compared. It names what it names without the
    `/`."""
    source = with_origin(tmp_path, url)

    assert adopter._remote_repository(source) == REPOSITORY


@pytest.mark.parametrize("spellings", [
    (f"/srv/git/{REPOSITORY}.git",),
    (f"/srv/clones/{OWN}.git",),
    (f"../{REPOSITORY}.git",),
    (f"./{REPOSITORY}", REPOSITORY),
    (f"C:/src/{REPOSITORY}.git", f"C:\\src\\{ORG}\\{OWN}.git"),
    (f"//server/share/{REPOSITORY}.git",
     f"\\\\server\\share\\{ORG}\\{OWN}.git"),
    (f"file:///srv/git/{REPOSITORY}.git",),
], ids=["absolute", "no-org-repo-at-its-end", "relative", "bare-relative",
        "drive", "unc", "file-url"])
def test_a_path_names_no_repository_however_it_is_written(adopter, tmp_path,
                                                          spellings):
    """#521's first two rows: a path named its last two directories when
    written with `/`, and nothing when written with `\\`. It is a directory
    on this machine, which names no repository on GitHub, so it names none
    in either spelling."""
    source = with_origin(tmp_path, spellings[0])

    read = [read_as(adopter, source, origin) for origin in spellings]

    assert read == [None] * len(spellings)


# --- `plan`, `--org` given ---------------------------------------------------

@pytest.mark.parametrize("project", [OWN, TYPO],
                         ids=["right-name", "mistyped"])
def test_a_path_origin_is_not_compared_and_plan_says_so(tmp_path, project):
    """#521's first row: a clone of `.../clones/Atlas.git` was refused
    `adopt-not-the-source` with the right `--org`, and sent to `--org
    clones`, a directory's name. It plans, with any `--project`, because a
    path says nothing of the repository on GitHub, and the NOTE says that
    nothing was compared and names the repository `execute` acts on. `check`
    reads the `origin` as `plan` does."""
    origin = (tmp_path / "clones" / f"{OWN}.git").as_posix()
    source = with_origin(tmp_path, origin)

    written = planned(tmp_path, source, project, ORG)

    assert written.returncode == 0, written.stdout + written.stderr
    assert (f"\n{NOT_COMPARED.format(origin)}\n"
            f"{ACTED_ON.format(f'{ORG}/{project}')}\n") in written.stdout, \
        written.stdout
    recorded = load_yaml(tmp_path / PLAN)
    assert (recorded["org"], recorded["source"]["repository"]) == (ORG, None)
    checked = check(tmp_path / PLAN)
    assert "\nplan ok\n" in checked.stdout, checked.stdout + checked.stderr


@pytest.mark.parametrize("origin, spelled", [
    (f"C:\\src\\{ORG}\\{OWN}.git", f"C:\\\\src\\\\{ORG}\\\\{OWN}.git"),
    (f"C:/src/{REPOSITORY}.git", f"C:/src/{REPOSITORY}.git"),
], ids=["backslashes", "slashes"])
def test_a_windows_path_origin_reads_alike_in_either_separator(
        tmp_path, origin, spelled):
    """#521's second row: `C:\\src\\acme\\Atlas.git` named no repository
    and `C:/src/acme/Atlas.git` named `acme/Atlas`, so a mistyped
    `--project` planned silently under one and was refused under the other.
    Both are the one path: each plans, and says it compared nothing. The
    NOTE spells a backslash as `_spelled` spells it."""
    source = with_origin(tmp_path, origin)

    written = planned(tmp_path, source, TYPO, ORG)

    assert written.returncode == 0, written.stdout + written.stderr
    assert f"\n{NOT_COMPARED.format(spelled)}\n" in written.stdout, \
        written.stdout


@pytest.mark.parametrize("url", [f"https://github.com/{REPOSITORY}/",
                                 f"https://github.com/{REPOSITORY}.git/"],
                         ids=["slash", "dot-git-slash"])
def test_a_url_ending_in_a_slash_is_the_repository_it_names(tmp_path, url):
    """#521's third row, through `plan`: `--project Atlsa --org acme`
    planned with exit 0. It is refused as `adopt-not-the-source`, naming
    `acme/Atlas`, and with no `--org` the organisation is `acme`, where it
    was `adopt-no-org`."""
    source = with_origin(tmp_path, url)

    refused = planned(tmp_path, source, TYPO, ORG)
    written = planned(tmp_path, source, OWN)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines()[0] == (
        f"REFUSED {NOT_THE_SOURCE}: --org {ORG} and --project {TYPO} name "
        f"{ORG}/{TYPO}, and the source is {REPOSITORY}: {WHY}")
    assert written.returncode == 0, written.stdout + written.stderr
    assert load_yaml(tmp_path / PLAN)["org"] == ORG


def test_a_path_origin_gives_no_rename_first_remedy(tmp_path):
    """#513's review, NIT-3, read the other way: the rename-first remedy for
    a path `origin` said to rename the repository at that path. A path now
    names no repository, so the source's own name is unknown, and a name
    the policy refuses is refused as for a source with no `origin`, with the
    hint to retype `--project`, not `adopt-not-the-source` against
    `clones/billing-service`."""
    origin = (tmp_path / "clones" / "billing-service.git").as_posix()
    source = with_origin(tmp_path, origin)

    refused = planned(tmp_path, source, "billing-service", ORG)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    detail, remediation = refused.stderr.splitlines()[:2]
    assert detail.startswith("REFUSED naming-unclassified: "), detail
    assert RETYPE in remediation, remediation
    assert "gh repo rename" not in refused.stderr


# --- `plan`, no `--org` (#427) -----------------------------------------------

@pytest.mark.parametrize("origin, org", [
    (f"https://example.invalid/caf%C3%A9/{OTHER}.git", "caf%C3%A9"),
    (f"https://example.invalid/caf\u00e9/{OTHER}.git", "caf\u00e9"),
    (f"https://example.invalid/my org/{OTHER}.git", "my org"),
    (f"git@example.invalid:-evil/{OTHER}.git", "-evil"),
], ids=["percent-encoded", "not-ascii", "space", "leading-dash"])
def test_an_org_read_from_origin_is_refused_by_where_it_came_from(
        tmp_path, origin, org):
    """#427: with no `--org`, `checked_value` refused the organisation the
    url names as `--org is 'café'`, a flag nobody passed, and its remedy
    never said to pass one. The refusal and its exit code stay; it names
    the value by where it came from and says to pass `--org`."""
    source = with_origin(tmp_path, origin)

    refused = planned(tmp_path, source, OTHER)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    detail, remediation = refused.stderr.splitlines()[:2]
    assert detail == (
        f"REFUSED unsafe-value: {ORG_FROM_ORIGIN} is {org!r}, which is not a "
        "value this tool will put on a `git` or `gh` command line")
    assert remediation.startswith(
        "Remediation: pass --org <org>; without it, `plan` reads the "
        "organisation from the source's `origin`. A leading `-` is refused "
        "because git reads its own arguments"), remediation
    assert not (tmp_path / PLAN).exists()


@pytest.mark.parametrize("org, named", [(None, ORG_FROM_ORIGIN),
                                        ("~x", "--org")],
                         ids=["read-from-origin", "passed"])
def test_an_org_the_validator_refuses_is_named_by_where_it_came_from(
        tmp_path, org, named):
    """L1-39, #427's pattern in the validator's refusal: a url can end in an
    organisation `checked_value` takes and the project's own validator
    refuses, `~x`, and with no `--org` that refusal said `--org is '~x'`, a
    flag nobody passed. It names the value by where it came from, in the
    words `checked_value`'s refusal above uses; a `--org ~x` that was
    passed is named as the flag."""
    source = with_origin(tmp_path, f"https://example.invalid/~x/{OTHER}.git")

    refused = planned(tmp_path, source, OTHER, org)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines()[0].startswith(
        f"REFUSED adopt-manifest-invalid: {named} is '~x', which the "
        "project's own validate-manifest.py refuses: "), refused.stderr
    assert not (tmp_path / PLAN).exists()


@pytest.mark.parametrize("directory", ["caf\u00e9", "my repos"],
                         ids=["not-ascii", "space"])
def test_a_path_origin_names_no_organisation(tmp_path, directory):
    """#427's path rows: a clone of `.../café/Northwind.git` was refused
    `--org is 'café'`, a directory's name `plan` took for an organisation.
    A path names no organisation: it is `adopt-no-org`, which says to pass
    `--org`; and with `--org testorg`, #427's control, it plans, where #499
    refused it against `café/Northwind`."""
    origin = (tmp_path / "x" / directory / f"{OTHER}.git").as_posix()
    source = with_origin(tmp_path, origin)

    refused = planned(tmp_path, source, OTHER)
    written = planned(tmp_path, source, OTHER, "testorg")

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines()[:2] == [
        NO_ORG, "Remediation: pass --org <org>."], refused.stderr
    assert written.returncode == 0, written.stdout + written.stderr
    assert load_yaml(tmp_path / PLAN)["org"] == "testorg"


def test_a_mistyped_project_names_the_org_nobody_passed_by_its_source(
        tmp_path):
    """#427's pattern in #499's refusal: with no `--org`, a mistyped
    `--project` was refused as `--org acme and --project Atlsa name ...`,
    a flag nobody passed. It names `--project` alone, with the organisation
    of the source's `origin`."""
    source = source_of(tmp_path, REPOSITORY)

    refused = planned(tmp_path, source, TYPO)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert refused.stderr.splitlines()[0] == (
        f"REFUSED {NOT_THE_SOURCE}: --project {TYPO}, with the organisation "
        f"of the source's `origin` (`--org` not given), names {ORG}/{TYPO}, "
        f"and the source is {REPOSITORY}: {WHY}")
