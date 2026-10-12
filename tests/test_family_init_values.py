# SPDX-License-Identifier: Apache-2.0
"""`family.py init` asks the holder's own programs about the `family.yaml` it
would write, BEFORE anything is created (#307).

`init` rendered `templates/family-root/family.yaml` from `--id`, `--org`,
`--name`, `--created-by`, `--created-on` and `--tracking-branch`, and pushed
the result. The holder reads it with its own YAML reader and its own
`scripts/validate-family.py`, and `init` asked neither: a blank `--created-by`,
`--created-on 20261011`, `--id null` or `--name 'Contoso Group'` exited 0 over a
holder whose gate was red from its first commit (and `init` cannot be run
again over a pushed holder), and `--tracking-branch true`, `007` or `null`
exited 0 over a holder the validator has no rule about, whose manifest read
back as another type.

Two questions, both asked of the TEMPLATE the run is about to render:

  * does the holder's reader read each value back as the same text? A value
    the template writes bare and the reader turns into a boolean, a number or
    nothing is `family-manifest-misread`;
  * does the holder's `validate-family.py` accept the whole manifest? What it
    refuses is `family-manifest-invalid`, in its own words.

#259 decides whether the templates quote their bare placeholders, and until it
lands the first question refuses what a bare line misreads. THE QUESTION IS THE
TEMPLATE'S, so the end-to-end rows below read the real template's own quoting
to say what they expect, and the unit rows run over a copy that is forced bare
and a copy that is forced quoted: the file stays green on either side of that
change, and shows the refusal going away by itself when a line is quoted.

NO NETWORK AND NO GITHUB. Every real run is into `--local-remote-dir`, which
never calls `gh`; the one run that names no local remote is in this process,
with every step that would reach GitHub replaced by one that fails the test.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from argparse import Namespace

import pytest

from conftest import REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import TREE_DIGEST_DEFINITION, load_yaml, parse_yaml  # noqa: E402
from shape_materialize import render  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
TEMPLATE = REPO / "templates" / "family-root"
ORG = "testorg"
HOLDER = "Contoso"

#: The placeholders `family.yaml` writes bare today, as a template line.
BARE_KEYS = ("FAMILY_ID", "ORG", "CREATED_ON", "VISIBILITY", "TRACKING_BRANCH")


def family_module():
    """`scripts/family.py` as a module, for the calls that touch no disk."""
    spec = importlib.util.spec_from_file_location("family_init_values", FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_template_quotes(key: str) -> bool:
    """Does the template this checkout ships write `{{key}}` between double
    quotes? The end-to-end rows ask it, so that they say what they expect of
    whichever state #259 leaves the template in."""
    text = (TEMPLATE / "family.yaml").read_text(encoding="utf-8")
    assert "{{" + key + "}}" in text
    return '"{{' + key + '}}"' in text


def template_copy(tmp_path, name: str, *, quoted: bool):
    """A copy of the family template whose bare placeholders are ALL bare
    (`quoted=False`) or ALL quoted (`quoted=True`), whatever the template of
    this checkout does. The copy carries its own `scripts/validate-family.py`,
    which is the one the questions then load."""
    target = tmp_path / name
    shutil.copytree(TEMPLATE, target,
                    ignore=shutil.ignore_patterns("__pycache__"))
    manifest = target / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    for key in BARE_KEYS:
        text = text.replace('"{{' + key + '}}"', "{{" + key + "}}")
        if quoted:
            text = text.replace("{{" + key + "}}", '"{{' + key + '}}"')
    manifest.write_bytes(text.encode("utf-8"))
    return target


def table(**overrides) -> dict:
    """The whole substitution table `init` renders `family.yaml` from, for a
    holder that is fine, with `overrides` on top."""
    values = {
        "FAMILY": HOLDER, "FAMILY_NAME": HOLDER, "FAMILY_ID": HOLDER.lower(),
        "FAMILY_REPOSITORY": f"{ORG}/{HOLDER}", "ORG": ORG,
        "VISIBILITY": "private", "TRACKING_BRANCH": "main",
        "CREATED_BY": "T H", "CREATED_ON": "2026-09-02",
        "CLONE_URL": "https://example.invalid/Contoso.git",
        "SHAPE_REPOSITORY": "opensoft/openRepoShape",
        "SHAPE_COMMIT": "a" * 40, "SHAPE_TREE_SHA256": "b" * 64,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
    }
    values.update(overrides)
    return values


def given(**given_flags) -> Namespace:
    """The arguments `init` was run with: each flag its value, or nothing."""
    flags = {"id": None, "name": None, "created_by": None, "created_on": None}
    flags.update(given_flags)
    return Namespace(**flags)


#: Every flag a run is given but the one under test, in the order they are given.
BASE = {"--org": ORG, "--family": HOLDER, "--created-by": "T H",
        "--created-on": "2026-09-02"}


def init(tmp_path, *flags: str, dry_run: bool = False, without=()):
    """`init` into local bare remotes under `tmp_path`: the base flags but
    those `without` (the ones `flags` gives itself), then `flags`."""
    base = [part for pair in BASE.items() if pair[0] not in without
            for part in pair]
    return run_script(
        FAMILY, "init", *base, *flags,
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"),
        *(["--dry-run"] if dry_run else []))


def nothing_was_created(tmp_path) -> None:
    assert not (tmp_path / "remotes").exists(), "a remote was created"
    assert not (tmp_path / "work").exists(), "a work directory was made"


def holder_of(tmp_path):
    return tmp_path / "work" / HOLDER


def validates(root):
    return run_script(root / "scripts" / "validate-family.py", cwd=root)


# ---------------------------------------------------------------------------
# End to end: the rows of the issue, through `--dry-run` and a real run
# ---------------------------------------------------------------------------

#: `(flag, value, the placeholder it lands in, what the run says while that
#: placeholder is written BARE, what it says once it is QUOTED)`; each is
#: `(refusal, a fragment of its sentence)`, or None for a run that is fine.
#: The first column of each is the issue's own table.
ROWS = [
    pytest.param("--created-by", " ", "CREATED_BY",
                 ("family-manifest-invalid", "family-created-by"),
                 ("family-manifest-invalid", "family-created-by"),
                 id="created-by-blank"),
    pytest.param("--created-on", "20261011", "CREATED_ON",
                 ("family-manifest-misread", "the number 20261011"),
                 ("family-manifest-invalid", "family-created-on"),
                 id="created-on-basic-date"),
    pytest.param("--created-on", "2026-W41-6", "CREATED_ON",
                 ("family-manifest-invalid", "family-created-on"),
                 ("family-manifest-invalid", "family-created-on"),
                 id="created-on-iso-week"),
    pytest.param("--created-on", "tomorrow", "CREATED_ON",
                 ("family-manifest-invalid", "family-created-on"),
                 ("family-manifest-invalid", "family-created-on"),
                 id="created-on-word"),
    pytest.param("--created-on", "'2026-09-02", "CREATED_ON",
                 ("family-manifest-misread", "because it refuses the line"),
                 ("family-manifest-invalid", "family-created-on"),
                 id="created-on-unclosed-quote"),
    pytest.param("--id", "null", "FAMILY_ID",
                 ("family-manifest-misread", "no value at all"), None,
                 id="id-null"),
    pytest.param("--id", "true", "FAMILY_ID",
                 ("family-manifest-misread", "the boolean true"), None,
                 id="id-true"),
    pytest.param("--id", "false", "FAMILY_ID",
                 ("family-manifest-misread", "the boolean false"), None,
                 id="id-false"),
    pytest.param("--org", "null", "ORG",
                 ("family-manifest-misread", "no value at all"), None,
                 id="org-null"),
    pytest.param("--name", "Contoso Group", "FAMILY_NAME",
                 ("family-manifest-invalid", "naming-unclassified"),
                 ("family-manifest-invalid", "naming-unclassified"),
                 id="name-two-words"),
    pytest.param("--tracking-branch", "true", "TRACKING_BRANCH",
                 ("family-manifest-misread", "the boolean true"), None,
                 id="branch-true"),
    pytest.param("--tracking-branch", "007", "TRACKING_BRANCH",
                 ("family-manifest-misread", "the number 7"), None,
                 id="branch-007"),
    pytest.param("--tracking-branch", "null", "TRACKING_BRANCH",
                 ("family-manifest-misread", "no value at all"), None,
                 id="branch-null"),
    pytest.param("--tracking-branch", "2026", "TRACKING_BRANCH",
                 ("family-manifest-misread", "the number 2026"), None,
                 id="branch-2026-works-only-by-accident"),
]


def expected_of(key, when_bare, when_quoted):
    return when_quoted if real_template_quotes(key) else when_bare


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("flag, value, key, when_bare, when_quoted", ROWS)
def test_init_asks_the_holders_own_programs_before_anything_is_created(
        tmp_path, flag, value, key, when_bare, when_quoted, dry_run):
    expected = expected_of(key, when_bare, when_quoted)
    if expected is None:
        pytest.skip("this template quotes the placeholder: the run is fine, "
                    "and test_a_quoted_value_is_held_as_typed runs it")
    result = init(tmp_path, f"{flag}={value}", dry_run=dry_run,
                  without=(flag,))
    refusal, fragment = expected
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {refusal}:" in result.stderr
    assert f"{flag} is {value!r}" in result.stderr
    assert fragment in result.stderr
    assert "Nothing was created, and `--dry-run` refuses the same." \
        in result.stderr
    # Refused BEFORE the plan is printed, and before any remote or directory.
    assert "landing" not in result.stdout
    nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value, key, when_bare, when_quoted", [
    row for row in ROWS if row.values[4] is None])
def test_a_quoted_value_is_held_as_typed(
        tmp_path, flag, value, key, when_bare, when_quoted):
    """Once the template quotes the placeholder, the value reads back exactly
    and the run is fine; while it is bare the run is refused (the test above)."""
    if not real_template_quotes(key):
        pytest.skip("this template writes the placeholder bare: the run is "
                    "refused, and the test above asserts it")
    result = init(tmp_path, f"{flag}={value}", without=(flag,))
    assert result.returncode == 0, result.stderr + result.stdout
    assert validates(holder_of(tmp_path)).returncode == 0
    field = {"FAMILY_ID": "id", "ORG": "org",
             "TRACKING_BRANCH": "tracking_branch"}[key]
    assert load_yaml(holder_of(tmp_path) / "family.yaml")[field] == value


CONTROLS = [
    pytest.param(("--tracking-branch=main",), {"tracking_branch": "main"},
                 id="branch-main"),
    pytest.param(("--tracking-branch=release-2026",),
                 {"tracking_branch": "release-2026"}, id="branch-text"),
    pytest.param(("--name=ContosoGroup",), {"name": "ContosoGroup"},
                 id="name-one-token"),
    pytest.param(("--id=contoso-group",), {"id": "contoso-group"},
                 id="id-hyphenated"),
    pytest.param(("--created-by=Robert \"Bob\" Smith",),
                 {"created_by": 'Robert "Bob" Smith'}, id="created-by-quotes"),
]


@pytest.mark.parametrize("flags, reads_back", CONTROLS)
def test_a_value_the_holder_can_hold_is_created_pushed_and_valid(
        tmp_path, flags, reads_back):
    """The controls: nothing the new refusals touch. The holder is created
    and pushed, its own `validate-family.py` is green, and `family.yaml`
    reads back as typed."""
    result = init(tmp_path, *flags,
                  without=[flag.split("=")[0] for flag in flags])
    assert result.returncode == 0, result.stderr + result.stdout
    root = holder_of(tmp_path)
    checked = validates(root)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    manifest = load_yaml(root / "family.yaml")
    for field, value in reads_back.items():
        assert manifest[field] == value
    assert (tmp_path / "remotes" / f"{HOLDER}.git").is_dir()


@pytest.mark.parametrize("family", ["Null", "True", "False"])
def test_an_id_the_family_name_would_derive_is_named_by_where_it_came_from(
        tmp_path, family):
    """`--family Null` derives the id `null`. No flag supplied it, so the
    refusal says where it came from instead of pointing at a flag nobody
    typed (the holder's `id:` is bare, or the run is fine)."""
    if real_template_quotes("FAMILY_ID"):
        pytest.skip("this template quotes `id:`: the derived id reads back")
    result = run_script(
        FAMILY, "init", "--org", ORG, "--family", family,
        "--created-by", "T H", "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED family-manifest-misread:" in result.stderr
    assert (f"--id (not given, so --family lowercased) is "
            f"{family.lower()!r}") in result.stderr
    nothing_was_created(tmp_path)


def test_two_bad_values_are_one_refusal_that_names_each(tmp_path):
    result = init(tmp_path, "--created-by= ", "--name=Contoso Group",
                  without=("--created-by",))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.count("REFUSED ") == 1
    assert "--created-by is ' '" in result.stderr
    assert "--name is 'Contoso Group'" in result.stderr
    nothing_was_created(tmp_path)


def test_a_dry_run_of_a_holder_it_can_hold_still_plans_and_creates_nothing(
        tmp_path):
    result = init(tmp_path, "--tracking-branch=release-2026", dry_run=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--dry-run: nothing was created." in result.stdout
    nothing_was_created(tmp_path)


def test_the_refusal_comes_before_any_step_that_reaches_github(
        monkeypatch, capsys):
    """Against GitHub, `_create_holder_remote` runs `gh repo create` before
    the manifest was ever rendered. No local remote here: the refusal must
    come before the question whether the repository exists, before the
    remote and before the worktree, so each is replaced by a step that
    fails the test, and `main` returns the refusal's own exit code."""
    module = family_module()

    def reached(*args, **kwargs):
        raise AssertionError("a step past the manifest question was reached")

    for name in ("_remote_is_empty", "_checked_reuse", "_create_holder_remote",
                 "_create_holder_worktree", "_prepare_landing_dir", "run"):
        monkeypatch.setattr(module, name, reached)
    for flags in (["--created-by", " "], ["--created-on", "tomorrow"],
                  ["--name", "Contoso Group"]):
        for dry_run in ([], ["--dry-run"]):
            code = module.main(["init", "--org", ORG, "--family", HOLDER,
                                "--created-by", "T H", *flags, *dry_run])
            assert code == 2
            captured = capsys.readouterr()
            assert "REFUSED family-manifest-invalid:" in captured.err
            assert "landing" not in captured.out


# ---------------------------------------------------------------------------
# End to end over a checkout whose template is FORCED bare, or forced quoted
# ---------------------------------------------------------------------------


def forged_shape(tmp_path, *, quoted: bool):
    """A one-commit checkout of the standard's own `scripts/`, `templates/`
    and `contracts/` (what `init` reads) whose `family.yaml` writes its bare
    placeholders bare, or quoted, as asked. Its `scripts/family.py` is the
    copy under test, so a run of it asks the template it sits beside: the end
    to end half of what #259 will change, run today."""
    shape = tmp_path / ("shape-quoted" if quoted else "shape-bare")
    for name in ("scripts", "templates", "contracts"):
        shutil.copytree(REPO / name, shape / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    manifest = shape / "templates" / "family-root" / "family.yaml"
    text = manifest.read_text(encoding="utf-8")
    for key in BARE_KEYS:
        text = text.replace('"{{' + key + '}}"', "{{" + key + "}}")
        if quoted:
            text = text.replace("{{" + key + "}}", '"{{' + key + '}}"')
    manifest.write_bytes(text.encode("utf-8"))
    git("init", "-q", "-b", "main", ".", cwd=shape)
    git("add", "-A", cwd=shape)
    git("-c", "user.name=T", "-c", "user.email=t@example.invalid",
        "commit", "-qm", "A one-commit checkout of the standard", cwd=shape)
    return shape


def init_in(shape, tmp_path, *flags: str, dry_run: bool = False):
    return run_script(
        shape / "scripts" / "family.py", "init", "--org", ORG, "--family",
        HOLDER, "--created-by", "T H", "--created-on", "2026-09-02", *flags,
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"),
        *(["--dry-run"] if dry_run else []))


#: The flag, the value and the field of `family.yaml` it lands in.
TEXT_ROWS = [
    pytest.param("--id", "null", "id", id="id-null"),
    pytest.param("--id", "true", "id", id="id-true"),
    pytest.param("--id", "false", "id", id="id-false"),
    pytest.param("--org", "null", "org", id="org-null"),
    pytest.param("--tracking-branch", "true", "tracking_branch",
                 id="branch-true"),
    pytest.param("--tracking-branch", "007", "tracking_branch",
                 id="branch-007"),
    pytest.param("--tracking-branch", "null", "tracking_branch",
                 id="branch-null"),
    pytest.param("--tracking-branch", "2026", "tracking_branch",
                 id="branch-2026"),
]


@pytest.fixture(scope="module")
def bare_shape(tmp_path_factory):
    return forged_shape(tmp_path_factory.mktemp("bare"), quoted=False)


@pytest.fixture(scope="module")
def quoted_shape(tmp_path_factory):
    return forged_shape(tmp_path_factory.mktemp("quoted"), quoted=True)


@pytest.mark.parametrize("flag, value, field", TEXT_ROWS)
def test_a_bare_template_refuses_the_value_before_anything_is_created(
        bare_shape, tmp_path, flag, value, field):
    for dry_run in (True, False):
        result = init_in(bare_shape, tmp_path, f"{flag}={value}",
                         dry_run=dry_run)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "REFUSED family-manifest-misread:" in result.stderr
        assert f"{flag} is {value!r}" in result.stderr
        nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value, field", TEXT_ROWS)
def test_a_quoted_template_holds_the_same_value_as_typed(
        quoted_shape, tmp_path, flag, value, field):
    """THE ADAPTATION, END TO END (#259): the same run over a template that
    quotes the placeholder is not refused. It creates the holder, pushes the
    branch as typed, and the holder's own reader reads the value back as that
    text, so nothing here needed an edit once the line was quoted."""
    planned = init_in(quoted_shape, tmp_path, f"{flag}={value}", dry_run=True)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    nothing_was_created(tmp_path)
    result = init_in(quoted_shape, tmp_path, f"{flag}={value}")
    assert result.returncode == 0, result.stderr + result.stdout
    root = holder_of(tmp_path)
    checked = validates(root)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    reading = load_yaml(root / "family.yaml")[field]
    assert reading == value and isinstance(reading, str)
    pushed = git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                 cwd=tmp_path / "remotes" / f"{HOLDER}.git").stdout.split()
    assert pushed == [value if field == "tracking_branch" else "main"]


def test_a_quoted_template_still_asks_the_validator(quoted_shape, tmp_path):
    """Quoting answers the first question and not the second: a date that
    reads back as the text `20261011` is still a date the holder's own
    validate-family.py refuses, in its words."""
    for dry_run in (True, False):
        result = init_in(quoted_shape, tmp_path, "--created-on=20261011",
                         dry_run=dry_run)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "REFUSED family-manifest-invalid:" in result.stderr
        assert "family-created-on" in result.stderr
        nothing_was_created(tmp_path)


# ---------------------------------------------------------------------------
# The questions themselves, over a template that is bare and one that is quoted
# ---------------------------------------------------------------------------

#: A value for each bare placeholder that the holder's reader would read as
#: another type: the flag that carries it, and what it comes back as.
MISREAD = [
    ("FAMILY_ID", "null", None), ("FAMILY_ID", "true", True),
    ("FAMILY_ID", "false", False), ("FAMILY_ID", "~", None),
    ("ORG", "null", None), ("ORG", "true", True),
    ("TRACKING_BRANCH", "true", True), ("TRACKING_BRANCH", "007", 7),
    ("TRACKING_BRANCH", "null", None), ("TRACKING_BRANCH", "2026", 2026),
    ("TRACKING_BRANCH", "1.5", 1.5), ("TRACKING_BRANCH", "~", None),
    ("CREATED_ON", "20261011", 20261011),
]
FIELD = {"FAMILY_ID": "id", "ORG": "org", "TRACKING_BRANCH": "tracking_branch",
         "CREATED_ON": "created_on"}


@pytest.mark.parametrize("key, value, reading", MISREAD)
def test_a_bare_placeholder_misreads_and_is_refused_template_relatively(
        tmp_path, key, value, reading):
    module = family_module()
    bare = template_copy(tmp_path, "bare", quoted=False)
    values = table(**{key: value})
    flags = module.MANIFEST_FLAGS
    sentences = module.family_manifest_misreads(values, flags, bare)
    assert len(sentences) == 1
    assert sentences[0].startswith(f"{flags[key]} is {value!r}, which is "
                                   "written into family.yaml as `")
    assert "where the holder's own YAML reader reads it back as" in sentences[0]
    # What the reader makes of the very manifest `init` would write.
    manifest = parse_yaml(render((bare / "family.yaml").read_text(
        encoding="utf-8"), values, "family.yaml"))
    assert manifest[FIELD[key]] == reading
    assert manifest[FIELD[key]] != value


@pytest.mark.parametrize("key, value, reading", MISREAD)
def test_the_same_value_in_a_quoted_template_reads_back_exactly_and_is_accepted(
        tmp_path, key, value, reading):
    """THE ADAPTATION (#259): the refusal is the TEMPLATE's. Quote the
    placeholder and the very value above is read back as typed, so the first
    question refuses nothing, with no edit to `family.py`."""
    module = family_module()
    quoted = template_copy(tmp_path, "quoted", quoted=True)
    values = table(**{key: value})
    assert module.family_manifest_misreads(
        values, module.MANIFEST_FLAGS, quoted) == []
    manifest = parse_yaml(render((quoted / "family.yaml").read_text(
        encoding="utf-8"), values, "family.yaml"))
    assert manifest[FIELD[key]] == value
    assert isinstance(manifest[FIELD[key]], str)


def test_the_real_template_is_asked_by_default():
    """No copy: the default is the template this checkout ships, so the
    answer for it is whichever its quoting makes."""
    module = family_module()
    for key, value in (("FAMILY_ID", "null"), ("TRACKING_BRANCH", "007")):
        said = module.family_manifest_misreads(table(**{key: value}),
                                               module.MANIFEST_FLAGS)
        assert bool(said) is (not real_template_quotes(key))


def test_a_value_the_template_always_quotes_is_never_a_misread(tmp_path):
    module = family_module()
    for template in (template_copy(tmp_path, "bare", quoted=False),
                     template_copy(tmp_path, "quoted", quoted=True)):
        for key, value in (("CREATED_BY", "true"), ("CREATED_BY", " "),
                           ("CREATED_BY", 'Robert "Bob" Smith'),
                           ("CREATED_BY", "C:\\new"),
                           ("FAMILY_NAME", "null"), ("FAMILY_NAME", "007"),
                           ("FAMILY_NAME", "Contoso Group")):
            assert module.family_manifest_misreads(
                table(**{key: value}), module.MANIFEST_FLAGS, template) == []


def test_a_placeholder_nobody_asked_about_is_not_asked(tmp_path):
    """`what` names the values to ask about: the rest of the table (the shape
    pin's commit, the repository) is the tool's own and is not the person's."""
    module = family_module()
    bare = template_copy(tmp_path, "bare", quoted=False)
    values = table(TRACKING_BRANCH="true")
    assert module.family_manifest_misreads(values, {"FAMILY_ID": "--id"},
                                           bare) == []


def test_the_validator_asked_is_the_one_in_the_template(tmp_path):
    """No rule is copied into `family.py`: edit the validator a template
    carries and the answer follows it, in its words. This copy's validator
    accepts only a creation date in 2027."""
    module = family_module()
    template = template_copy(tmp_path, "bare", quoted=False)
    validator = template / "scripts" / "validate-family.py"
    source = validator.read_text(encoding="utf-8")
    old = 'DATE_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")'
    assert old in source
    validator.write_bytes(source.replace(
        old, 'DATE_RE = re.compile(r"^2027-\\d{2}-\\d{2}$")').encode("utf-8"))
    values = table(CREATED_ON="2026-09-02")
    sentences = module.family_manifest_invalid(
        values, module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS, template)
    assert len(sentences) == 1
    assert sentences[0].startswith(
        "--created-on is '2026-09-02', which the holder's own "
        "validate-family.py refuses: family-created-on: ")
    # The validator this checkout ships accepts the same table.
    assert module.family_manifest_invalid(
        values, module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS) == []


def test_a_rule_the_validator_learns_later_is_refused_in_its_own_words(
        tmp_path):
    """A finding that is about none of the values `init` was handed is still
    a refusal, with no flag to point at."""
    module = family_module()
    template = template_copy(tmp_path, "bare", quoted=False)
    validator = template / "scripts" / "validate-family.py"
    with validator.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "\n_original_check_envelope = _check_envelope\n\n\n"
            "def _check_envelope(manifest, policy, report):\n"
            "    _original_check_envelope(manifest, policy, report)\n"
            "    report.finding('family-new-rule', 'a rule learned later')\n")
    sentences = module.family_manifest_invalid(
        table(), module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS, template)
    assert sentences == [
        "the manifest this run would write is one the holder's own "
        "validate-family.py refuses: family-new-rule: a rule learned later."]


def test_misread_is_asked_first_and_alone(tmp_path):
    """`--id null` fails the validator as `id is None`, which is only the
    misread's consequence: the sentence worth reading is the first one. A
    value the validator alone refuses is asked once the reader has no
    complaint, and the quoted template has none."""
    module = family_module()
    bare = template_copy(tmp_path, "bare", quoted=False)
    quoted = template_copy(tmp_path, "quoted", quoted=True)
    args = given(id="null", created_by=" ")
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(
            args, table(FAMILY_ID="null", CREATED_BY=" "), bare)
    assert caught.value.code == "family-manifest-misread"
    assert "--id is 'null'" in caught.value.detail
    assert "--created-by" not in caught.value.detail
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(
            args, table(FAMILY_ID="null", CREATED_BY=" "), quoted)
    assert caught.value.code == "family-manifest-invalid"
    assert "--created-by is ' '" in caught.value.detail
    assert "--id" not in caught.value.detail


@pytest.mark.parametrize("key, value, flag, source", [
    ("FAMILY_ID", "true", "--id", "--family lowercased"),
    ("FAMILY_NAME", "Contoso Group", "--name", "--family"),
    ("CREATED_BY", " ", "--created-by",
     "GIT_AUTHOR_NAME or `git config user.name`"),
    ("CREATED_ON", "tomorrow", "--created-on", "today"),
])
def test_a_value_no_flag_supplied_is_named_by_where_it_came_from(
        tmp_path, key, value, flag, source):
    """The refusal never points at a flag nobody typed."""
    module = family_module()
    template = template_copy(tmp_path, "bare", quoted=False)
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(), table(**{key: value}),
                                          template)
    assert f"{flag} (not given, so {source}) is {value!r}" \
        in caught.value.detail
    typed = given(id="x", name="x", created_by="x", created_on="x")
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(typed, table(**{key: value}),
                                          template)
    assert f"{flag} is {value!r}" in caught.value.detail
    assert "not given" not in caught.value.detail


def test_a_manifest_that_is_not_a_mapping_is_a_sentence_and_not_a_trace(
        tmp_path):
    module = family_module()
    template = template_copy(tmp_path, "bare", quoted=False)
    (template / "family.yaml").write_bytes(b"- one\n- two\n")
    assert module.family_manifest_invalid(
        table(), module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS, template) == [
        "the manifest this run would write is not a mapping, which is what "
        "the holder's own YAML reader makes of it."]


def test_a_manifest_the_holders_reader_refuses_is_a_sentence_and_not_a_trace(
        tmp_path):
    module = family_module()
    template = template_copy(tmp_path, "bare", quoted=False)
    with (template / "family.yaml").open("a", encoding="utf-8",
                                         newline="\n") as stream:
        stream.write("anchored: &anchor 1\n")
    sentences = module.family_manifest_invalid(
        table(), module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS, template)
    assert len(sentences) == 1
    assert sentences[0].startswith(
        "the manifest this run would write is a file the holder's own YAML "
        "reader refuses: ")


# ---------------------------------------------------------------------------
# A validator that cannot be asked is a named refusal, and nothing was created
# ---------------------------------------------------------------------------

BREAKS = [
    pytest.param(None, "could not be loaded", id="missing"),
    pytest.param("def broken(:\n", "could not be loaded", id="syntax-error"),
    pytest.param("raise RuntimeError('nope')\n", "could not be loaded",
                 id="raises-on-import"),
    pytest.param("import sys\nsys.exit(3)\n", "could not be loaded",
                 id="exits-on-import"),
    pytest.param("class Report:\n    pass\n", "it has no `_check_envelope`",
                 id="lacks-the-question"),
    pytest.param(
        "class Report:\n    findings = []\n\n\n"
        "def _check_envelope(manifest, policy, report):\n"
        "    raise RuntimeError('boom')\n",
        "raised when it was asked", id="raises-when-asked"),
]


@pytest.mark.parametrize("body, says", BREAKS)
def test_a_validator_that_cannot_be_asked_is_refused_by_name(
        tmp_path, body, says):
    module = family_module()
    template = template_copy(tmp_path, "broken", quoted=False)
    validator = template / "scripts" / "validate-family.py"
    if body is None:
        validator.unlink()
    else:
        validator.write_bytes(body.encode("utf-8"))
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(), table(), template)
    assert caught.value.code == "family-validator-unusable"
    assert says in caught.value.detail
    assert "nothing was created" in caught.value.remediation


def test_asking_the_validator_leaves_no_bytecode_of_it_in_the_template():
    """The template is a tree other readers walk: a `.pyc` of the validator
    in it is a file nobody put there. (Other tools that run a template script
    may leave their own cache; only the validator's is asked about.)"""
    module = family_module()
    cached = TEMPLATE / "scripts" / "__pycache__"
    before = set(cached.glob("validate-family*")) if cached.is_dir() else set()
    module.family_manifest_invalid(
        table(), module.NamingPolicy.load(module.NAMING_POLICY),
        module.MANIFEST_FLAGS)
    after = set(cached.glob("validate-family*")) if cached.is_dir() else set()
    assert after == before == set()
