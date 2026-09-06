# SPDX-License-Identifier: Apache-2.0
"""`plan` classifies, `check` refuses. Both run against local repositories.

NO NETWORK AND NO GITHUB. Every source here is a repository made in a
temporary directory by `conftest.make_source_repo`; the one test that reads
MedxEHR reads a COPY of a read-only clone and never writes to it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, resolve, run_script, write_plan

sys.path.insert(0, str(REPO / "scripts"))
from path_classify import PathPolicy  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

#: A read-only clone of MedxSoft/MedxEHR, if this machine has one. The test
#: that uses it COPIES it first and skips when it is absent, because a suite
#: that only runs on the machine it was written on is not a suite. Read from
#: SHAPE_MEDXEHR_CLONE (this repository's SHAPE_* env-var convention) —
#: deliberately NO default path, because a host-absolute path baked into a
#: committed file is exactly what the estate's Rule 1 forbids (#61).
MEDXEHR = (Path(os.environ["SHAPE_MEDXEHR_CLONE"])
          if os.environ.get("SHAPE_MEDXEHR_CLONE") else None)

POLICY = REPO / "contracts" / "path-classification.yaml"


def entries(plan_path: Path) -> dict:
    plan = load_yaml(plan_path)
    return {str(e["path"]): e for e in plan["paths"]}


# --- the policy itself -----------------------------------------------------

def test_the_path_policy_loads_and_declares_four_classes():
    policy = PathPolicy.load(POLICY)
    assert policy.data["kind"] == "path-classification-policy"
    assert policy.data["legs"] == ["spec", "code", "root", "ambiguous"]
    assert policy.rules


@pytest.mark.parametrize("path,leg", [
    ("openspec/changes/x/proposal.md", "spec"),
    ("specs/001/spec.md", "spec"),
    ("contracts/policy.yaml", "spec"),
    ("docs/decisions/0001-thing.md", "spec"),
    ("docs/api/generated.html", "code"),          # the "except" that runs
    # API contracts are governance content (Brett, 2026-09-04). Each of these
    # would otherwise fall to `extension-majority`, which counts `.yaml` and
    # `.json` as code and proposed exactly that for InkRouter/IRSS `openapi/`.
    ("openapi/v1/ingest.yaml", "spec"),
    ("openapi/README.md", "spec"),
    ("asyncapi/events.yaml", "spec"),
    ("schemas/job-envelope.schema.json", "spec"),
    ("proto/router/v1/router.proto", "spec"),
    ("src/app/main.py", "code"),
    ("tests/test_main.py", "code"),
    ("scripts/harness.py", "code"),
    ("docker/Dockerfile", "code"),
    (".github/workflows/ci.yml", "code"),
    ("pyproject.toml", "code"),
    ("sonar-project.properties", "code"),
    ("README.md", "root"),
    ("LICENSE", "root"),
    (".gitignore", "root"),
    (".specify/scripts/plan.sh", "root"),
    ("AGENTS.md", "root"),
    ("CLAUDE.md", "root"),
    ("GEMINI.md", "root"),
    (".cursor/rules.md", "root"),
    (".roo/config.md", "root"),
    ("Makefile", "root"),
])
def test_a_path_classifies_where_the_rulings_put_it(path, leg):
    verdict = PathPolicy.load(POLICY).classify_file(path)
    assert verdict.leg == leg, f"{path} -> {verdict.leg} ({verdict.rule})"


@pytest.mark.parametrize("path", [
    "examples/golden-run/expected.yaml",
    ".claude/commands/ship.md",
    "release.yaml",
    "notebooks/explore.ipynb",
])
def test_an_ambiguous_path_carries_the_question_and_no_leg(path):
    verdict = PathPolicy.load(POLICY).classify_file(path)
    assert verdict.leg is None
    assert verdict.review_required
    assert verdict.question, "an ambiguous path with no question is a shrug"
    assert verdict.confidence == "review"


def test_a_top_level_yaml_is_ambiguous_but_a_nested_one_is_not():
    """`*` does not cross `/`: the rule is about TOP-LEVEL data files."""
    policy = PathPolicy.load(POLICY)
    assert policy.classify_file("release.yaml").leg is None
    assert policy.classify_file("tests/fixtures/case.yaml").leg == "code"


# --- plan ------------------------------------------------------------------

def test_plan_classifies_a_synthetic_repository(source_repo, tmp_path):
    out = tmp_path / "adoption-plan.yaml"
    result = write_plan(source_repo, out)
    assert result.returncode == 0, result.stderr + result.stdout
    plan = load_yaml(out)
    assert plan["kind"] == "adoption-plan"
    assert plan["schema_version"] == 1
    assert plan["mode"] == "in-place"
    assert plan["source"]["commits"] == 3
    assert plan["legs"] == {"assembly": "Northwind", "spec": "Northwind-spec",
                            "code": "Northwind-code", "spec_path": "spec",
                            "code_path": "code"}
    rows = entries(out)
    assert rows["specs/"]["leg"] == "spec"
    assert rows["contracts/"]["leg"] == "spec"
    assert rows["src/"]["leg"] == "code"
    assert rows["tests/"]["leg"] == "code"
    assert rows[".specify/"]["leg"] == "root"
    assert rows["README.md"]["leg"] == "root"
    assert rows["examples/"]["leg"] is None
    assert rows["examples/"]["review_required"] is True


def test_a_directory_is_one_entry_until_its_children_disagree(source_repo,
                                                              tmp_path):
    """`.github/` splits — workflows to the code leg, CODEOWNERS to the root —
    so the plan descends into it and reports both. `specs/` does not."""
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    rows = entries(out)
    assert ".github/" not in rows
    assert rows[".github/workflows/"]["leg"] == "code"
    assert rows[".github/CODEOWNERS"]["leg"] == "root"
    assert rows["specs/"]["files"] == 2, "specs/ must stay ONE entry"


def test_an_unrecognised_source_package_is_read_by_extension(source_repo,
                                                             tmp_path):
    """`pkg_core/` is named by no rule; two files of three are `.py`."""
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    row = entries(out)["pkg_core/"]
    assert row["leg"] == "code"
    assert row["rule"] == "extension-majority"
    assert row["confidence"] == "medium", (
        "a majority is evidence, not a decision, and the plan must say so")


def test_the_plan_records_the_follow_ups_the_split_makes_necessary(source_repo,
                                                                   tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    follow_ups = " ".join(load_yaml(out)["follow_ups"])
    assert "CONTRACTS_DIR" in follow_ups
    assert "shape/Makefile" in follow_ups
    assert "shape/README.md" in follow_ups
    assert "pull request" in follow_ups
    # PREDICTED, so the human reads it in the plan they approve rather than in
    # output they may never scroll back to — and in the same words `execute`
    # will use, because both callers share one function.
    assert ("add the line `Read AGENTS-shape.md first — the rules of this "
            "repository's shape.` to the existing AGENTS.md") in follow_ups
    assert "root-assistant-instructions" in follow_ups


def test_every_source_file_is_covered_exactly_once(source_repo, tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"],
                            cwd=str(source_repo), capture_output=True,
                            text=True, check=True).stdout.split()
    paths = list(entries(out))
    for path in listed:
        covering = [p for p in paths
                    if p == path or (p.endswith("/") and path.startswith(p))]
        assert len(covering) == 1, f"{path} covered by {covering}"


# --- check -----------------------------------------------------------------

def test_check_refuses_a_plan_with_an_unresolved_leg(source_repo, tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 1
    assert "plan-unresolved" in result.stderr
    assert "examples/" in result.stderr
    assert "acceptance evidence" in result.stderr, (
        "the refusal must carry the QUESTION, not just the path")


def test_check_passes_once_every_question_is_answered(source_repo, tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root")):
        resolve(out, path, leg)
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout
    assert "the source is never deleted, never renamed, never force-pushed" \
        in result.stdout


def test_check_plans_the_topic_on_all_three(source_repo, tmp_path):
    """`check` is where the human reads what will happen, and setting
    `xf-project-<id>` on the adopted root and both legs is part of it. It runs
    against a local source and calls nothing, so the REAL plan line — the `gh`
    one — is assertable without a network."""
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root")):
        resolve(out, path, leg)
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 0, result.stderr
    assert "topics gh repo edit --add-topic xf-project-northwind on all three" \
        in result.stdout


def test_an_id_edited_into_the_plan_is_re_validated_where_it_is_used(
        source_repo, tmp_path):
    """`plan` refuses a bad `--id`, and the plan is edited afterwards ON
    PURPOSE — so the check is made again where the value is USED: the topic
    is derived from it, and reaches a `gh` command line and the manifest."""
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    out.write_text(out.read_text().replace("id: northwind", "id: Northwind"))
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 2
    assert "plan-bad-id" in result.stderr
    assert "topic is derived from it" in result.stderr


def test_check_reports_a_path_that_no_entry_covers(source_repo, tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    text = out.read_text()
    start = text.index("  - path: src/\n")
    end = text.index("  - path: ", start + 10)
    out.write_text(text[:start] + text[end:])
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 1
    assert "plan-uncovered" in result.stderr
    assert "src/app/main.py" in result.stderr


def test_check_reports_a_plan_written_against_an_older_commit(source_repo,
                                                             tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root")):
        resolve(out, path, leg)
    (source_repo / "src" / "app" / "late.py").write_text("LATE = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=str(source_repo), check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "later work"], cwd=str(source_repo),
                   check=True)
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 1
    assert "plan-stale" in result.stderr


def test_a_bad_leg_name_in_the_plan_is_a_finding(source_repo, tmp_path):
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out).returncode == 0
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root")):
        resolve(out, path, leg)
    out.write_text(out.read_text().replace("  - path: specs/\n    leg: spec",
                                           "  - path: specs/\n    leg: specs"))
    result = run_script(ADOPT, "check", "--plan", str(out))
    assert result.returncode == 1
    assert "plan-bad-leg" in result.stderr


def test_a_project_name_that_is_not_a_leg_form_is_refused(source_repo, tmp_path):
    """A naming mistake costs a message, before anything is written."""
    result = write_plan(source_repo, tmp_path / "plan.yaml",
                        project="Atlas-tests")
    assert result.returncode == 2
    assert "naming-unclassified" in result.stderr
    assert not (tmp_path / "plan.yaml").exists()


def test_a_neutral_product_may_be_adopted_as_its_own_assembly_root(source_repo,
                                                                   tmp_path):
    """The 2026-09-05 ruling reaches `adopt` through the same `accepts_role`
    the scaffold uses, because there is one definition of which forms may be a
    root. A live `open<Product>` electing the shape is the case the ruling was
    made for, and it is planned rather than refused."""
    plan_path = tmp_path / "plan.yaml"
    result = write_plan(source_repo, plan_path, project="openDox",
                        org="opensoft")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "naming-role-mismatch" not in result.stderr
    plan = load_yaml(plan_path)
    assert plan["project"] == "openDox"
    assert plan["id"] == "opendox"


def test_an_install_form_is_still_refused_by_adopt(source_repo, tmp_path):
    """The edge, on this path too: `<X>-Install` satisfies no leg form, so
    the remediation names what MAY be a root rather than leaving the reader to
    infer that nothing else can."""
    result = write_plan(source_repo, tmp_path / "plan.yaml",
                        project="Widget-Install")
    assert result.returncode == 2
    assert "naming-role-mismatch" in result.stderr
    assert "may elect the shape" in result.stderr
    assert not (tmp_path / "plan.yaml").exists()


def test_a_project_name_that_is_not_a_lowercase_id_is_refused(source_repo,
                                                              tmp_path):
    result = write_plan(source_repo, tmp_path / "plan.yaml",
                        project="North_Wind")
    assert result.returncode == 2
    assert "adopt-bad-id" in result.stderr


# --- --pin, and --visibility internal ---------------------------------------

def test_a_bare_pin_name_is_declared(source_repo, tmp_path):
    plan_path = tmp_path / "plan.yaml"
    result = write_plan(source_repo, plan_path, extra=("--pin", "openGlass"))
    assert result.returncode == 0, result.stderr
    plan = load_yaml(plan_path)
    assert plan["pins"] == ["openGlass"]


def test_an_owner_qualified_pin_name_is_declared(source_repo, tmp_path):
    plan_path = tmp_path / "plan.yaml"
    result = write_plan(source_repo, plan_path,
                        extra=("--pin", "opensoft/openGlass"))
    assert result.returncode == 0, result.stderr
    plan = load_yaml(plan_path)
    assert plan["pins"] == ["opensoft/openGlass"]


def test_a_pin_carrying_a_commit_is_refused(source_repo, tmp_path):
    """`scaffold-project.py --pin openProduct@<commit>` syntax pasted here by
    habit: adopting a project declares no commit for a neutral-product pin at
    plan time, so this is refused rather than silently written into
    `neutral_product_pins:` as a name nothing will ever match."""
    commit = "0" * 40
    result = write_plan(source_repo, tmp_path / "plan.yaml",
                        extra=("--pin", f"openGlass@{commit}"))
    assert result.returncode == 2
    assert "adopt-pin-malformed" in result.stderr
    assert "openGlass" in result.stderr
    assert "opensoft" in result.stderr
    assert not (tmp_path / "plan.yaml").exists()


def test_visibility_internal_is_accepted(source_repo, tmp_path):
    plan_path = tmp_path / "plan.yaml"
    result = write_plan(source_repo, plan_path,
                        extra=("--visibility", "internal"))
    assert result.returncode == 0, result.stderr
    plan = load_yaml(plan_path)
    assert plan["visibility"] == "internal"


def test_a_bad_visibility_is_refused_by_argparse(source_repo, tmp_path):
    result = write_plan(source_repo, tmp_path / "plan.yaml",
                        extra=("--visibility", "secret"))
    assert result.returncode != 0
    assert "invalid choice: 'secret'" in result.stderr
    assert "'internal'" in result.stderr


# --- the MedxEHR shape, which is what the rulings were made about ----------

@pytest.mark.skipif(
    MEDXEHR is None or not MEDXEHR.is_dir(),
    reason="SHAPE_MEDXEHR_CLONE is unset, or names no directory: the "
           "MedxEHR-backed plan test needs a read-only clone of "
           "MedxSoft/MedxEHR")
def test_plan_on_medxehr_matches_the_rulings(tmp_path):
    """THE WORKED EXAMPLE, against the real tree, on a COPY.

    Decisions (1)-(3) of 2026-09-02, as assertions: `contracts/` to the spec
    leg even though the code reads it, `.specify/` and the assistant stubs in
    the assembly root, the Frappe app in the code leg — and the golden-run
    corpus flagged for a human rather than guessed at.
    """
    source = tmp_path / "MedxEHR"
    shutil.copytree(MEDXEHR, source, symlinks=True)
    out = tmp_path / "adoption-plan.yaml"
    result = write_plan(source, out, project="MedxEHR", org="MedxSoft")
    assert result.returncode == 0, result.stderr + result.stdout
    rows = entries(out)

    assert rows[".specify/"]["leg"] == "root"
    assert rows[".specify/"]["files"] == 43
    assert rows["contracts/"]["leg"] == "spec"
    assert rows["openspec/"]["leg"] == "spec"
    assert rows["specs/"]["leg"] == "spec"
    assert rows["medx_ehr/"]["leg"] == "code"
    assert rows["tests/"]["leg"] == "code"
    assert rows["scripts/"]["leg"] == "code"
    assert rows["docker/"]["leg"] == "code"
    assert rows["sonar-project.properties"]["leg"] == "code"
    assert rows[".github/workflows/"]["leg"] == "code"
    for stub in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", "KIMI.md",
                 "IFLOW.md", "QODER.md", "SHAI.md", "TABNINE.md",
                 "CODEBUDDY.md"):
        assert rows[stub]["leg"] == "root", f"{stub} belongs in the root"
    for stub_dir in (".cursor/", ".roo/", ".junie/", ".kilocode/", ".trae/",
                     ".vibe/", ".windsurf/", ".augment/"):
        assert rows[stub_dir]["leg"] == "root"
    assert rows["Makefile"]["leg"] == "root"

    assert rows["examples/"]["leg"] is None
    assert rows["examples/"]["review_required"] is True
    assert "acceptance evidence" in rows["examples/"]["question"]

    plan = load_yaml(out)
    assert plan["source"]["files"] == 167
    assert plan["source"]["commits"] == 25
    follow_ups = " ".join(plan["follow_ups"])
    assert "scripts/validate.py" in follow_ups, (
        "the harness that reads `contracts/` must be named, not implied")
    assert "CONTRACTS_DIR" in follow_ups
