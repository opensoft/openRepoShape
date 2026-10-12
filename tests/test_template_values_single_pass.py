# SPDX-License-Identifier: Apache-2.0
"""A free-text value is written as typed, whatever placeholder it holds (#260).

`render` replaced the placeholders one key at a time, each over the whole
text, so the text an earlier key put in was searched by every later key.
`--elected-by`, `--reference`, the scaffold's `--name` and the family's
`--name` and `--created-by` are free text, so each could hold another
placeholder's token:

- a token for a key that came LATER was expanded: `adopt-project.py
  --elected-by '{{SPEC_PATH}}'` recorded `elected_by: "spec"` and said
  `adoption verified`;
- a token for a key that came EARLIER, or one no key names, stayed in the
  output, and `render` refused it as `template-unsubstituted`, "a defect in
  the substitution table of the tool you ran", after the legs were pushed.

`render` now reads the template once and puts each value in as it meets
its placeholder, so a value is never searched. It refuses only a placeholder
the TEMPLATE holds and the table has no value for.

NO NETWORK AND NO GITHUB: templates rendered in memory, and every tool run
into local bare remotes (`--local-remote-dir`), with a `gh` on PATH that
records any call. What each run wrote is read back with `git show` from the
repository it pushed to, so no line ending a checkout chose is compared.
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, ORG, REPO, SCAFFOLD, make_source_repo, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402
from shape_materialize import Refusal, render  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
TEMPLATES = REPO / "templates"

#: A placeholder as this test spells one, independent of the module under
#: test: capitals, digits and underscores, starting with a capital.
KEY_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
KEY_NAME = re.compile(r"[A-Z][A-Z0-9_]*")

REMEDIATION = ("Remediation: this is a defect in the substitution table of "
               "the tool you ran, not in your invocation.")


def token(key: str) -> str:
    return "{{" + key + "}}"


def template_files() -> dict[str, str]:
    """Every text file under `templates/`, by its path from the repository."""
    found = {}
    for path in sorted(TEMPLATES.rglob("*")):
        if path.is_file():
            try:
                found[path.relative_to(REPO).as_posix()] = path.read_text(
                    encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return found


TEMPLATE_TEXT = template_files()


def keys_named_by_the_templates() -> set[str]:
    return {key for text in TEMPLATE_TEXT.values()
            for key in KEY_TOKEN.findall(text)}


def keys_spelled_by(tool: Path) -> set[str]:
    """Every capitals string key of a dict the tool's source spells. Its
    substitution table is among them (`ORG` and the family's `FAMILY`
    included, which no template names), and so are a few that are no key of
    any table, which only makes a value hold more tokens."""
    tree = ast.parse(tool.read_text(encoding="utf-8"))
    return {key.value for node in ast.walk(tree) if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
            and KEY_NAME.fullmatch(key.value)}


def every_key(*tools: Path) -> list[str]:
    """Every key of each tool's table, and every key a template names."""
    return sorted(keys_named_by_the_templates().union(
        *(keys_spelled_by(tool) for tool in tools)))


def holding_every_key(prefix: str, *tools: Path) -> str:
    """One value holding every key's token, bare and between double quotes:
    the quoted form is the one a YAML template's quoted field is matched by."""
    return " ".join([prefix] + [f'{token(key)} "{token(key)}"'
                                for key in every_key(*tools)])


def stand_in(key: str) -> str:
    """An ordinary value for `key`: no brace, no quote, no backslash."""
    if "SHA256" in key:
        return "0123456789abcdef" * 4
    if "COMMIT" in key:
        return "c0ffee" * 6 + "abcd"
    if key.endswith("_ON"):
        return "2026-09-02"
    if key.endswith("_NAMING"):
        return "    naming:\n      form: project-leg\n      role: spec"
    if key == "NEUTRAL_PRODUCT_PINS":
        return "[]"
    if key == "SHAPE_FILES":
        return '  - path: Makefile\n    sha256: "' + "ab" * 32 + '"'
    return f"v-{key.lower()} é"


def table(text: str, free: dict[str, str]) -> dict[str, str]:
    """`free` for the free-text keys, FIRST, then an ordinary stand-in for
    every other key `text` names or a tool's table carries. In that order a
    loop of replacements would search each free-text value with every other
    key, as the tools' own tables did with most of theirs."""
    rest = sorted(set(KEY_TOKEN.findall(text)).union(ALL_TOOL_KEYS))
    return {**free, **{key: stand_in(key) for key in rest if key not in free}}


#: The YAML templates with free-text fields: the field, and the key that
#: fills it.
YAML_FREE_TEXT = {
    "templates/assembly-root/project.yaml": {
        "name": "PROJECT_NAME", "elected_by": "ELECTED_BY",
        "reference": "REFERENCE"},
    "templates/family-root/family.yaml": {
        "name": "FAMILY_NAME", "created_by": "CREATED_BY"},
}
FREE_TEXT_KEYS = sorted({key for fields in YAML_FREE_TEXT.values()
                         for key in fields.values()})
#: Every template a person reads rather than the YAML reader that carries a
#: free-text value: the READMEs and the AGENTS.md of each root and leg.
MARKDOWN_FREE_TEXT = sorted(
    rel for rel, text in TEMPLATE_TEXT.items()
    if not rel.endswith((".yaml", ".yml"))
    and set(KEY_TOKEN.findall(text)) & set(FREE_TEXT_KEYS))

ALL_TOOL_KEYS = every_key(SCAFFOLD, ADOPT, FAMILY)


def test_the_templates_under_test_are_found():
    assert "templates/assembly-root/README.md" in MARKDOWN_FREE_TEXT
    assert "templates/spec-root/AGENTS.md" in MARKDOWN_FREE_TEXT
    assert "templates/family-root/README.md" in MARKDOWN_FREE_TEXT
    assert {"PROJECT", "SPEC_PATH", "SPEC_TREE_SHA256", "ORG",
            "FAMILY"} <= set(ALL_TOOL_KEYS)


# --- render ----------------------------------------------------------------

@pytest.mark.parametrize("spelling", ["bare", "quoted"])
@pytest.mark.parametrize("key", [*ALL_TOOL_KEYS, "NOPE"])
def test_a_value_holding_any_placeholder_is_written_as_typed(key, spelling):
    """Each key's token, and one no key names, as every free-text value:
    every YAML template reads it back unchanged, and every README and
    AGENTS.md holds it exactly where it holds an ordinary value."""
    value = token(key) if spelling == "bare" else f'"{token(key)}"'
    for rel, fields in YAML_FREE_TEXT.items():
        text = TEMPLATE_TEXT[rel]
        written = parse_yaml(render(text, table(text, dict.fromkeys(
            FREE_TEXT_KEYS, value)), rel))
        assert {field: written[field] for field in fields} == dict.fromkeys(
            fields, value), rel
    sentinel = "SENTINEL-VALUE-SENTINEL"
    for rel in MARKDOWN_FREE_TEXT:
        text = TEMPLATE_TEXT[rel]
        ordinary = render(text, table(text, dict.fromkeys(
            FREE_TEXT_KEYS, sentinel)), rel)
        assert sentinel in ordinary, rel
        assert render(text, table(text, dict.fromkeys(
            FREE_TEXT_KEYS, value)), rel) == ordinary.replace(sentinel, value)


@pytest.mark.parametrize("source", ["README.md", "project.yaml"])
def test_no_key_reads_what_another_key_wrote(source):
    """Whichever key comes first in the table, neither reads the other's
    value: each is put in where its own placeholder stood, and only there."""
    values = {"A": token("B"), "B": token("A")}
    assert render("{{A}}|{{B}}", values, source) == "{{B}}|{{A}}"
    assert render("{{B}}|{{A}}", values, source) == "{{A}}|{{B}}"
    quoted = render('a: "{{A}}"\nb: "{{B}}"\n', values, source)
    if source.endswith(".yaml"):
        assert parse_yaml(quoted) == {"a": token("B"), "b": token("A")}
    else:
        assert quoted == 'a: "{{B}}"\nb: "{{A}}"\n'


@pytest.mark.parametrize("source, text, values, missing", [
    pytest.param("README.md", "By {{ELECTED_BY}}, for {{NOPE}}.\n",
                 {"ELECTED_BY": "{{ALSO_NOPE}} {{ELECTED_BY}} {{NOPE}}"},
                 ["{{NOPE}}"], id="markdown"),
    pytest.param("project.yaml", 'elected_by: "{{ELECTED_BY}}"\nx: {{NOPE}}\n',
                 {"ELECTED_BY": "{{ALSO_NOPE}} {{ELECTED_BY}}"},
                 ["{{NOPE}}"], id="yaml"),
    pytest.param("project.yaml", 'x: "{{NOPE}}"\ny: "{{ELECTED_BY}}"\n',
                 {"PROJECT": "Atlas", "ELECTED_BY": "{{PROJECT}}"},
                 ["{{NOPE}}"], id="yaml-quoted-placeholder"),
    pytest.param("contracts/spec-pin.yaml",
                 'tree_sha256: "{{SPEC_TREE_SHA256}}"\n', {},
                 ["{{SPEC_TREE_SHA256}}"], id="a-key-with-digits"),
])
def test_the_refusal_names_what_the_template_lacks_and_nothing_a_value_holds(
        source, text, values, missing):
    """A placeholder the TEMPLATE holds and the table has no value for is
    still refused, before anything is written, and the refusal names those
    and only those: never a token that came in with a value. A key with
    digits, `{{SPEC_TREE_SHA256}}`, is a placeholder like any other, where
    it used to be left in the output with nothing said."""
    with pytest.raises(Refusal) as caught:
        render(text, values, source)
    assert caught.value.code == "template-unsubstituted"
    assert caught.value.detail == f"{source}: no value for {missing}"
    assert caught.value.remediation == REMEDIATION


def test_text_that_is_no_placeholder_is_left_alone():
    """A workflow's own `${{ github.x }}` and a Python f-string's doubled
    braces hold a space or a lower-case letter: neither is a placeholder,
    so neither is replaced nor refused. The value beside them, which holds
    its own key's token, is written as typed."""
    text = ("run: echo ${{ github.repository_owner }}\n"
            'ref: f"{commit}^{{commit}}" {{ELECTED_BY}}\n')
    value = "{{x}} {{ELECTED_BY}}"
    assert render(text, {"ELECTED_BY": value}, "validate.yml") == (
        "run: echo ${{ github.repository_owner }}\n"
        'ref: f"{commit}^{{commit}}" ' + value + "\n")


@pytest.mark.parametrize("template", sorted(
    rel for rel, text in TEMPLATE_TEXT.items() if KEY_TOKEN.search(text)))
def test_an_ordinary_value_renders_as_a_plain_substitution(template):
    """For values with no brace, quote or backslash, one pass writes exactly
    what replacing each key in turn wrote, in every template that holds a
    placeholder, so no project's files change by a byte."""
    text = TEMPLATE_TEXT[template]
    values = table(text, {})
    plain = text
    for key, value in values.items():
        plain = plain.replace(token(key), value)
    assert render(text, values, template) == plain


# --- the tools, end to end ---------------------------------------------------

def shown(repository: Path, spec: str) -> str:
    """`git show <spec>` in `repository`, as UTF-8 text: the bytes the run
    committed and pushed, not a checkout's copy of them."""
    proc = subprocess.run(["git", "show", spec], cwd=str(repository),
                          capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return proc.stdout.decode("utf-8")


@pytest.fixture
def gh_stub(tmp_path) -> tuple[dict, Path]:
    """A `gh` first on PATH that records any call and fails. Every run here
    is into local bare remotes, which calls no `gh`; the log says so. It is a
    `#!` script, so only a POSIX host runs it; on Windows it is inert."""
    bin_dir, log = tmp_path / "bin", tmp_path / "gh.log"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_bytes(b'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$GH_STUB_LOG"\n'
                     b"exit 1\n")
    stub.chmod(0o755)
    return ({"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
             "GH_STUB_LOG": str(log)}, log)


def assert_gh_never_ran(log: Path) -> None:
    assert not log.exists(), log.read_bytes().decode("utf-8", "replace")


def free_text_values(kind: str, prefixes: tuple, tool: Path) -> list[str]:
    if kind == "every-key":
        return [holding_every_key(prefix, tool) for prefix in prefixes]
    return [token("NOPE")] * len(prefixes)


KINDS = ["every-key", "nope"]


@pytest.mark.parametrize("kind", KINDS)
def test_the_scaffold_records_each_free_text_value_as_typed(kind, tmp_path,
                                                            gh_stub):
    """`--name`, `--elected-by` and `--reference`, each holding every key's
    token or `{{NOPE}}`: the scaffold exits 0, the manifest it pushed holds
    each value as typed and passes its own validator, and the README and
    both legs' AGENTS.md hold them too."""
    env, log = gh_stub
    name, elected_by, reference = free_text_values(
        kind, ("Name", "By", "Ref"), SCAFFOLD)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Atlas",
                        "--name", name, "--elected-by", elected_by,
                        "--reference", reference,
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert_gh_never_ran(log)

    root = remotes / "Atlas.git"
    manifest = parse_yaml(shown(root, "main:project.yaml"))
    assert (manifest["name"], manifest["elected_by"], manifest["reference"]) \
        == (name, elected_by, reference)
    readme = shown(root, "main:README.md").splitlines()
    assert readme[0] == f"# {name}"
    assert any(line.endswith(f". Elected by {elected_by} on 2026-09-02, "
                             "against") for line in readme), readme[:12]
    assert f"`{reference}`." in readme
    for leg in ("spec", "code"):
        agents = shown(remotes / f"Atlas-{leg}.git", "main:AGENTS.md")
        assert agents.startswith(
            f"This is the **{leg} leg** of {name} (`atlas`): "), agents[:300]

    check = run_script(work / "Atlas" / "scripts" / "validate-manifest.py",
                       cwd=work / "Atlas")
    assert check.returncode == 0, check.stderr + check.stdout


@pytest.mark.skipif(shutil.which("git-filter-repo") is None,
                    reason="git filter-repo is not installed: "
                           "`pip install git-filter-repo`")
@pytest.mark.parametrize("kind", KINDS)
def test_adopt_records_each_free_text_value_as_typed(kind, tmp_path, gh_stub):
    """`--elected-by` and `--reference`, each holding every key's token or
    `{{NOPE}}`: `plan` and `check` pass, `execute` exits 0 with `adoption
    verified`, and the split commit's manifest and README hold each value
    as typed."""
    env, log = gh_stub
    elected_by, reference = free_text_values(kind, ("By", "Ref"), ADOPT)
    source = make_source_repo(
        tmp_path / "Thing", tree={"src/app.py": "print(1)\n",
                                  "docs/spec.md": "# Spec\n"}, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    planned = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", "Northwind", "--org", ORG,
                         "--elected-by", elected_by, "--reference", reference,
                         "--elected-on", "2026-09-02", "--out", str(plan),
                         env=env)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan), env=env)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    assert_gh_never_ran(log)

    split = "adopt/three-repo-shape"
    manifest = parse_yaml(shown(source, f"{split}:project.yaml"))
    assert (manifest["elected_by"], manifest["reference"]) == (elected_by,
                                                               reference)
    readme = shown(source, f"{split}:README.md").splitlines()
    assert readme[0] == "# Northwind"
    assert any(line.endswith(f". Elected by {elected_by} on 2026-09-02, "
                             "against") for line in readme), readme[:12]
    assert f"`{reference}`." in readme


@pytest.mark.parametrize("kind", KINDS)
def test_a_family_records_its_creator_as_typed(kind, tmp_path, gh_stub):
    """`family.py init --created-by`, holding every key's token or
    `{{NOPE}}`: the holder it pushed holds the value as typed in
    `family.yaml` and passes its own validator.

    `--name` is left to its default here. The holder's validator asks
    `name` to classify as a family holder, one CamelCase token, so a free
    text name is refused there whatever `render` does; the unit tests above
    hold `{{FAMILY_NAME}}` in `family.yaml`, the README and AGENTS.md."""
    env, log = gh_stub
    (created_by,) = free_text_values(kind, ("By",), FAMILY)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(FAMILY, "init", "--org", ORG, "--family", "Contoso",
                        "--created-by", created_by,
                        "--created-on", "2026-09-04",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert_gh_never_ran(log)

    family = parse_yaml(shown(remotes / "Contoso.git", "main:family.yaml"))
    assert (family["name"], family["created_by"]) == ("Contoso", created_by)

    check = run_script(work / "Contoso" / "scripts" / "validate-family.py",
                       cwd=work / "Contoso")
    assert check.returncode == 0, check.stderr + check.stdout
