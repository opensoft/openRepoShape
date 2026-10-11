# SPDX-License-Identifier: Apache-2.0
"""A `--referent-chain` link between the first and the last names a neutral
product, or the scaffold refuses before anything is created (#251).

`naming_block` writes the chain into `project.yaml` as a plain flow sequence,
`referent_chain: [openXdox, openDox]`, and on main through 150c41d nothing
looked at a MIDDLE link: the scaffold asked the chain's length, a repeat, the
first link (a `--pin` product) and the last (the referent the name claims),
and a link whose tree is not on the disk is declared-unverified, a warning.
`--referent-chain openXdox,a #b,openDox` therefore created all three
repositories, pushed both legs and exited 0, and the project's own
`validate-manifest.py` refused the manifest it had been given as
`yaml-unparsable`: the `#` began a comment. `it's` and `a]b` read back as one
link swallowing the next, `"q"` as `q`, `null` as None and `007` as 7.

A link past the first is read out of the link before its
`neutral_product_pins:`, so it is a neutral product's NAME, and the naming
policy spells one: the `neutral-product` family, `open<Product>`. A name of
that form is one plain YAML word. The first and last links keep the checks
that anchor them, compared casefolded on purpose, and neither can carry YAML
syntax; `test_the_first_and_last_links_are_judged_as_before` holds that line.

The refusals run `main()` in this process with every process start refused,
so they show the refusal comes before `gh api` reads a pin's tree, before git
and before the work directory, under `--dry-run` and without it. The
end-to-end tests run the script against bare remotes under `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from conftest import REPO, SCAFFOLD, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy, load_yaml  # noqa: E402

PROJECT = "codexDox"
ORG = "codexSoft"
UTF8 = "utf-8"
REFUSED = "REFUSED chain-link-malformed"
BASE_ARGS = ("--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
             "--elected-on", "2026-09-05")
#: A commit for a `--pin` the refusal comes before: nothing reads its tree,
#: and with no `--pin-source` the first thing that would is `gh api`.
ANY_COMMIT = "1" * 40

#: Middle links main wrote into the manifest as typed, with what each did
#: there. Each is refused now.
MALFORMED = [
    # The `#` began a comment: validate-manifest.py exited 2.
    pytest.param("a #b", id="hash"),
    # Read back as the one link "it's, openDox".
    pytest.param("it's", id="single-quote"),
    # Read back as the one link "a]b, openDox".
    pytest.param("a]b", id="closing-bracket"),
    pytest.param("a: b", id="colon-space"),
    # Read back as q.
    pytest.param('"q"', id="double-quoted"),
    # Valid repository names the reader resolves as None and 7.
    pytest.param("null", id="null"),
    pytest.param("007", id="digits"),
    # Names, and not a neutral product's: a project-leg form, the
    # organisation login the neutral pattern exists to keep out, and a
    # capitalised spelling that classifies as a project-leg form too.
    pytest.param("Atlas", id="project-leg-form"),
    pytest.param("opensoft", id="organisation-login"),
    pytest.param("OPENYDOX", id="capitals"),
    # The basename is what is judged, as it is what the manifest records.
    pytest.param("opensoft/a #b", id="qualified-hash"),
]


@pytest.fixture(scope="module")
def scaffold():
    """`scaffold-project.py` loaded as a module, so `main()` runs here."""
    module_spec = importlib.util.spec_from_file_location(
        "scaffold_referent_chain_links", SCAFFOLD)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class ProcessStarted(AssertionError):
    """A process was started where the refusal should already have come."""


@pytest.fixture
def no_process(monkeypatch):
    """Every command the scaffold runs, `git` and `gh` alike, starts through
    `subprocess.Popen`. While this holds, starting one fails the test and
    names the command."""
    def refuse(args, *_, **__):
        raise ProcessStarted(f"a process was started: {args!r}")
    monkeypatch.setattr(subprocess, "Popen", refuse)


def layer(tmp_path, name: str, pins: str):
    """A stand-in for a chain link's own repository, declaring `pins` in its
    `project.yaml`, and its commit."""
    path = tmp_path / name
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    (path / "project.yaml").write_bytes(
        ("schema_version: 1\nkind: project-manifest\n"
         f"neutral_product_pins:\n  - {pins}\n").encode(UTF8))
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed",
        cwd=path)
    return path, git("rev-parse", "HEAD", cwd=path).stdout.strip()


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
@pytest.mark.parametrize("link", MALFORMED)
def test_a_middle_link_that_is_not_a_neutral_product_is_refused_first(
        scaffold, capsys, no_process, tmp_path, link, dry_run):
    """Refused by name, with a remediation, before any process starts and
    before the plan is printed, so a dry run refuses as the real run does."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    chain = f"openXdox,{link},openDox"
    code = scaffold.main([*BASE_ARGS, "--pin", f"openXdox@{ANY_COMMIT}",
                          "--referent-chain", chain,
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(work),
                          *(["--dry-run"] if dry_run else [])])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert f"{REFUSED}: --referent-chain {chain!r}: " in err
    assert f"{link!r} is not the name of a neutral product" in err
    assert "\nRemediation: nothing was created." in err
    assert "`open<Product>`" in err and "e.g. openXdox" in err
    assert out == "", "the plan is printed only after every name is judged"
    assert not remotes.exists() and not work.exists()


def test_every_malformed_middle_link_is_named_in_one_refusal(
        scaffold, capsys, no_process):
    """Two bad links, one refusal naming both, in the order typed; the good
    middle link between them is not named."""
    code = scaffold.main([*BASE_ARGS, "--dry-run",
                          "--pin", f"openXdox@{ANY_COMMIT}",
                          "--referent-chain",
                          "openXdox,it's,openYdox,a #b,openDox"])
    _, err = capsys.readouterr()
    assert code == 2
    assert "\"it's\", 'a #b' are not the name of a neutral product" in err
    assert "'openYdox'" not in err


def test_a_padded_bad_link_is_named_as_it_is_recorded(scaffold, capsys,
                                                      no_process):
    """The check judges the links `_declaration` records, spaces stripped
    (`referent_chain_links`), so the refusal names `'a #b'`, not `' a #b '`,
    and the padded good link beside it is not judged malformed."""
    code = scaffold.main([*BASE_ARGS, "--dry-run",
                          "--pin", f"openXdox@{ANY_COMMIT}",
                          "--referent-chain",
                          "openXdox, openYdox , a #b ,openDox"])
    _, err = capsys.readouterr()
    assert code == 2
    assert "'a #b' is not the name of a neutral product" in err
    assert "' a #b '" not in err


#: A character that would end the refusal's line, or move the cursor, or
#: hide behind the terminal, with how the refusal must spell it.
LINE_BREAKS = [
    pytest.param("\n", "\\n", id="newline"),
    pytest.param("\r", "\\r", id="carriage-return"),
    pytest.param("\x1b", "\\x1b", id="escape"),
    pytest.param("\u2028", "\\u2028", id="line-separator"),
]


@pytest.mark.parametrize("raw,spelled", LINE_BREAKS)
def test_a_link_holding_a_line_break_is_refused_on_one_line(
        scaffold, capsys, no_process, raw, spelled):
    """The chain is the operator's own argument and the refusal prints it:
    a link holding a newline must not end the refusal's line and begin a
    second that reads as a refusal of its own."""
    chain = f"openXdox,a{raw}REFUSED fake,openDox"
    code = scaffold.main([*BASE_ARGS, "--dry-run",
                          "--pin", f"openXdox@{ANY_COMMIT}",
                          "--referent-chain", chain])
    _, err = capsys.readouterr()
    assert code == 2
    lines = err.splitlines()
    assert len(lines) == 2, f"the refusal and its remediation, no more: {lines!r}"
    refusal, remediation = lines
    assert refusal.startswith(f"{REFUSED}: --referent-chain ")
    assert f"a{spelled}REFUSED fake" in refusal
    assert raw not in refusal, "the character itself must not reach the line"
    assert remediation.startswith("Remediation: nothing was created.")


def test_the_remediation_quotes_the_policys_pattern_and_names_a_command(
        scaffold, capsys, no_process):
    """The remediation quotes the naming policy's own pattern for a link and
    names `validate-repository-naming.py --explain <link>`."""
    pattern = NamingPolicy.load(
        REPO / "contracts" / "repository-naming.yaml").family(
        "neutral-product")["pattern"]
    assert pattern.startswith("^open"), pattern
    code = scaffold.main([*BASE_ARGS, "--dry-run",
                          "--pin", f"openXdox@{ANY_COMMIT}",
                          "--referent-chain", "openXdox,a #b,openDox"])
    _, err = capsys.readouterr()
    assert code == 2
    remediation = err.splitlines()[-1]
    assert f"(the naming policy's `{pattern}`, e.g. openXdox)" in remediation
    assert ("`validate-repository-naming.py --explain <link>` says which "
            "form a name is.") in remediation


def test_the_command_the_remediation_names_says_which_form_a_name_is():
    """`--explain <link>` is the remediation's pointer, so it must answer."""
    explained = run_script(REPO / "scripts" / "validate-repository-naming.py",
                           "--explain", "openYdox")
    assert explained.returncode == 0, explained.stderr + explained.stdout
    assert "openYdox: neutral-product" in explained.stdout


@pytest.mark.parametrize("raw,links", [
    pytest.param("openXdox,openYdox,openDox",
                 ("openXdox", "openYdox", "openDox"), id="plain"),
    pytest.param("openXdox, openYdox ,\topenDox\n",
                 ("openXdox", "openYdox", "openDox"), id="padded"),
    pytest.param("openXdox,,openYdox, ,openDox,",
                 ("openXdox", "openYdox", "openDox"), id="empty-links"),
    pytest.param("", (), id="empty"),
    pytest.param(" , ,", (), id="only-commas"),
])
def test_referent_chain_links_strips_each_link_and_drops_an_empty_one(
        scaffold, raw, links):
    """The one reading of the argument, for the check and for the manifest."""
    assert scaffold.referent_chain_links(raw) == links


@pytest.mark.parametrize("chain", ["openXdox,a #b,openDox",
                                   "openXdox,it's,openDox"],
                         ids=["hash", "single-quote"])
def test_the_issue_reproduction_creates_no_repository(tmp_path, chain):
    """#251's own rows, end to end: on main each exited 0 with three
    repositories, both legs pushed and the root pushed with that line."""
    source, commit = layer(tmp_path, "openXdox", "openDox")
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, *BASE_ARGS,
                        "--pin", f"openXdox@{commit}",
                        "--pin-source", str(source),
                        "--referent-chain", chain,
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr
    assert not remotes.exists(), "no repository may exist after a refusal"
    assert not work.exists()


@pytest.mark.parametrize("chain", [
    pytest.param("openXdox,openYdox,openDox", id="bare"),
    pytest.param("openXdox,opensoft/openYdox,openDox", id="qualified"),
    # The commonest way to type the argument, and an empty link: both are
    # read once (`referent_chain_links`), for the check and the manifest.
    pytest.param("openXdox, openYdox ,openDox", id="padded"),
    pytest.param("openXdox,,openYdox,openDox,", id="empty-links"),
])
def test_a_neutral_product_middle_link_scaffolds_and_validates(tmp_path,
                                                               chain):
    """The rule refuses only what is not a neutral product's name. A
    three-link chain whose every link is read from its own tree scaffolds,
    records the links as names, and passes the project's own gate."""
    first, commit = layer(tmp_path, "openXdox", "openYdox")
    second, _ = layer(tmp_path, "openYdox", "openDox")
    #: Where each link's own tree is, for the scaffold and the project's
    #: gate alike, so every link is VERIFIED rather than declared-unverified.
    trees = {"SHAPE_PIN_SOURCE_OPENXDOX": str(first),
             "SHAPE_PIN_SOURCE_OPENYDOX": str(second)}
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, *BASE_ARGS,
                        "--pin", f"openXdox@{commit}",
                        "--pin-source", str(first),
                        "--referent-chain", chain,
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work), env=trees)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "declared pin chain openXdox → openYdox → openDox" \
        in result.stdout
    assert "declared-unverified" not in result.stderr + result.stdout
    assert "is broken" not in result.stderr

    root = work / PROJECT
    manifest = load_yaml(root / "project.yaml")
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "domain-descendant"
    assert assembly["naming"]["referent_chain"] == [
        "openXdox", "openYdox", "openDox"]
    for validator, args in (("validate-manifest.py", []),
                            ("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-pins.py", [])):
        check = run_script(root / "scripts" / validator, *args, cwd=root,
                           env=trees)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"
        assert "declared-unverified" not in check.stderr + check.stdout


@pytest.mark.parametrize("chain", ["OPENXDOX,openDox",
                                   "opensoft/openXdox,openDox",
                                   "openXdox,OPENDOX"],
                         ids=["first-capitals", "first-qualified",
                              "last-capitals"])
def test_the_first_and_last_links_are_judged_as_before(tmp_path, chain):
    """The first link is a `--pin` product and the last the referent, both
    compared casefolded, which this change leaves alone: each of these
    planned on main and plans here."""
    source, commit = layer(tmp_path, "openXdox", "openDox")
    result = run_script(SCAFFOLD, *BASE_ARGS, "--dry-run",
                        "--pin", f"openXdox@{commit}",
                        "--pin-source", str(source),
                        "--referent-chain", chain,
                        "--local-remote-dir", str(tmp_path / "remotes"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "chain-link-malformed" not in result.stderr
    assert "--dry-run: nothing was created." in result.stdout
