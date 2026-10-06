#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The Triad advisory: said once where a person starts work, and never a gate.

THE RULING. Brett Heap, 2026-10-06: *"ratify 1249 as recommended"*, ratifying
openxFactory's `prefer-triad-project-shape` on his direction of the same day,
*"the triad should be the prefered structure and should prompt or warn the
user if working on a non Triad repo."* The Triad is this standard's
three-repository shape -- an assembly root with a spec leg and a code leg; a
"three-leg project" and a "three-repository project" are the same thing, and
no machine key was renamed for the word. It is the PREFERRED project shape,
and it stays ELECTIVE and confers NOTHING: no gate, no floor, no grant, no
clearance eligibility, no lifecycle state and no review difference.

WHO SAYS IT, AND HOW OFTEN. Three tools, each once per run, in one or two
lines, beside what it already reports: `scaffold-project.py` names the Triad
as the preferred shape in the plan a person reads before typing yes (it only
ever creates one, so it offers the Triad first by construction);
`adopt-project.py plan` and `check` say it about the repository they read;
and `shape-doctor.py` gives a repository that has not elected it one
`advisory` row. None of them blocks, converts, writes, creates a repository,
or changes an exit status on its account, and NOTHING RECORDS THAT IT WAS
GIVEN: it is a sentence said to a person, not a state, so no later act can
read "was advised" as a fact about a project.

NEVER A GATE AND NEVER A REVIEW INPUT. No review lane, required check,
validator, floor, council or merge gate reads anything this module answers,
and nothing here returns an exit code. A check built on it -- or on the
doctor's `NOT A SHAPE ROOT` verdict -- would make layout a review input,
which the ratified doctrine calls defective; `tests/test_shape_advisory.py`
holds the list of files allowed to import this one to the three tools above.

SILENT WHERE THE SHAPE QUESTION IS ANSWERED OR DOES NOT ARISE, each read from
a DECLARED fact -- the repository's own tree, the naming policy, or the
person's own workspace configuration -- and never inferred:

  * an elected Triad assembly root: `project.yaml` declaring `kind:
    project-manifest`, `schema: project-repo-schema` and `legs:` naming a
    `spec` and a `code` leg -- the same detector the shared agent protocol
    and the workstation bootstrap use;
  * a family holder: `family.yaml` declaring `kind: family-manifest`, with no
    `project.yaml` declaring a project. It pins projects and is not one;
  * a leg clone: a repository whose own name is a `<Project>-spec` or
    `<Project>-code` leg form under `contracts/repository-naming.yaml`, or
    whose `AGENTS.md` is the leg template's, which names the assembly root.
    The existing instruction applies there instead -- work from the root;
  * a `<user>-wip` workspace repository: the `workspace` form of the same
    naming policy, or the path `${AGENT_PROTOCOL_ROOT:-$HOME/.agents}/
    workspace.yaml` names as the person's own workspace clone;
  * a repository carrying `single-repository.yaml` whose `kind` is
    `single-repository-record`.

A directory that is not a repository at all is not advised either: the
sentence begins "this is a single repository", and there is none.

AND NO OTHER CLASS IS GUESSED. An aggregation, a configuration or dotfile
repository and a vendored fork carry no declared fact that says what they
are, so they get the advisory until they migrate or record staying single.
Exempting a class by its name, its layout or its remote would be a rule right
for the repositories its author had in mind and wrong for the next one (the
ratified ruling on OQ-2); the remedy for a class that should be silent is to
give it a declared fact, as `<user>-wip` already has.

THE ONLY READER OF `single-repository.yaml`. That record is OPTIONAL and never
owed -- a project that declines the Triad and writes nothing owes nothing and
is reviewed identically -- and the advisory is its one reader, by the ruling,
which is why it has no validator script of its own: a second reader is
exactly what a record that confers nothing must not acquire. Its schema is
`contracts/single-repository-record.yaml` and its template
`templates/single-repository/single-repository.yaml`. `kind:` DECIDES, not
the filename, as it does for every manifest here: a record that parses and
declares `single-repository-record` silences the advisory; one that does not
parse, or declares anything else, silences nothing and is reported beside the
advisory, and nothing fails on its account. A record that silences but leaves
a field out is still silent; the doctor says which field, as a `note`.

NOT A SHAPE COPY, DELIBERATELY. `scripts/repo_shape.py` is copied into every
assembly root and family holder and digest-pinned there, so a function added
to it puts an `upstream-changed` row in front of every project for a helper
no project's own copy would ever call -- the argument `shape-doctor.py`'s
`quote_arg` already makes. This module stays in the checkout the three tools
run from, and imports from `repo_shape` rather than adding to it.

STANDARD LIBRARY ONLY, like everything else shipped here. Every sentence is
ASCII, because `shape-doctor.py` prints ASCII and a Windows console in its
ANSI code page reads it.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import NamingPolicy, Refusal, git_out, load_yaml  # noqa: E402

#: The checkout of the standard this file sits in. The naming policy and the
#: record's schema are read from HERE, exactly as the doctor compares a
#: project against the checkout it is run from.
SHAPE_ROOT = Path(__file__).resolve().parents[1]

PROJECT_MANIFEST = "project.yaml"
FAMILY_MANIFEST = "family.yaml"
AGENTS_MD = "AGENTS.md"
NAMING_POLICY = "contracts/repository-naming.yaml"

#: The optional staying-single record, as ruled on OQ-1: its own file at the
#: repository root, never `project.yaml` or a field of it, because
#: `project.yaml` with `kind: project-manifest` and two legs IS the Triad
#: detector and a single repository carrying one would turn every reader of it
#: from a presence test into a content test.
RECORD_FILE = "single-repository.yaml"
RECORD_KIND = "single-repository-record"
RECORD_SCHEMA = "contracts/single-repository-record.yaml"
SCHEMA_KIND = "single-repository-record-schema"
RECORD_TEMPLATE = "templates/single-repository/single-repository.yaml"

#: What `read()` answers. One of them advises; every other one is a row of the
#: ratified list of silences, plus the directory that is not a repository.
ADVISE = "advise"
TRIAD_ROOT = "triad-root"
FAMILY_HOLDER = "family-holder"
LEG_CLONE = "leg-clone"
WORKSPACE = "workspace"
RECORDED_SINGLE = "recorded-single"
NOT_A_REPOSITORY = "not-a-repository"
STATES = (ADVISE, TRIAD_ROOT, FAMILY_HOLDER, LEG_CLONE, WORKSPACE,
          RECORDED_SINGLE, NOT_A_REPOSITORY)

#: The two leg roles. A name the naming policy classifies as `project-leg` in
#: either of them is a leg's name by this standard's own declaration.
LEG_ROLES = ("spec", "code")

#: The two sentences every leg's `AGENTS.md` carries, as
#: `templates/spec-root/` and `templates/code-root/` render it: the opening,
#: which says which leg this is, and the line naming the assembly root the
#: project's rules live in. Spelled here and HELD to the templates by
#: `tests/test_shape_advisory.py`, which renders both and reads them back --
#: so a template reworded without this is a red test, not a leg that quietly
#: starts being advised.
LEG_OPENING_RE = re.compile(r"\AThis is the \*\*(spec|code) leg\*\* of ")
LEG_ROOT_RE = re.compile(r"They are in the assembly root `([^`\s]+)`")

#: A `{{PLACEHOLDER}}` the template carries and a person filling it in by hand
#: left behind. The record's template uses the same spelling as every other
#: template here, and a value still spelled that way is a field nobody wrote.
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# What is said
# ---------------------------------------------------------------------------
#
# THE MEANING IS FIXED AND THE FORM IS THE SURFACE'S. The reference sentence
# the realization brief carries is: "This is a single repository. The Triad
# -- an assembly root with a spec leg and a code leg -- is the preferred
# project shape: openRepoShape's adopt-project.py converts a repository in
# place, and a project that stays single can say so in single-repository.yaml.
# Nothing here changes; work continues." THE POSTURE TRAVELS WITH IT, every
# time: the ratified requirement says that wherever the preference is stated
# "confers nothing" is stated with it, so that no reader meets "preferred"
# without also meeting that.

TRIAD = ("The Triad -- an assembly root with a spec leg and a code leg -- is "
         "the preferred project shape")
POSTURE = ("preferred, not required: it confers nothing, and a single "
           "repository is reviewed identically")


def advisory_lines() -> list[str]:
    """The advisory as a work-start surface says it: two lines."""
    return [
        f"This is a single repository. {TRIAD}; {POSTURE}.",
        "openRepoShape's adopt-project.py converts a repository in place when "
        "a person deciding for this project runs it, and a project that stays "
        f"single can say so in {RECORD_FILE}. Nothing here changes; work "
        "continues.",
    ]


def adopt_lines() -> list[str]:
    """The same meaning, said by the tool that IS the conversion.

    `adopt-project.py` cannot tell a person to run itself, so the second line
    says what it actually does about the advice: nothing until `execute`, and
    that only on the word of a person deciding for the project.
    """
    return [
        f"This is a single repository. {TRIAD}, and this tool is how a "
        f"repository reaches it, in place; {POSTURE}.",
        "Nothing converts until `execute`, on the word of a person deciding "
        "for this project, and a project that stays single can say so in "
        f"{RECORD_FILE} instead. `plan` and `check` change nothing in it.",
    ]


def scaffold_lines() -> list[str]:
    """What the scaffold's plan says: the Triad OFFERED FIRST.

    `scaffold-project.py` has no single-repository mode -- every run creates
    an assembly root and two legs -- so the offer is the tool itself, and the
    plan a person reads before typing yes names it as the preferred shape,
    with the posture beside it. Nothing here is about a repository that
    already exists, so nothing here is conditional.
    """
    return [
        "the Triad -- an assembly root with a spec leg and a code leg -- is "
        "what this creates, and the preferred project shape",
        f"{POSTURE}; a project kept in one repository owes no declaration",
    ]


def record_report(problems) -> list[str]:
    """One line per reason a present `single-repository.yaml` silences
    nothing. Reported beside the advisory, and nothing fails on its account.
    """
    return [f"{RECORD_FILE} does not silence this: {problem} (its schema is "
            f"openRepoShape's {RECORD_SCHEMA}); nothing fails on its account."
            for problem in problems]


def leg_instruction(leg: dict) -> str:
    """The existing instruction a leg clone gets INSTEAD of the advisory.

    It is the leg templates' own "Clone the assembly root, not this
    repository", said by the tool that found the leg. The leg IS part of a
    Triad, so advising it to become one would be false.
    """
    root = leg.get("assembly")
    named = f"`{root}`" if root else "the assembly root that mounts it"
    return (f"this is a clone of the {leg['role']} leg of a Triad "
            f"({leg['how']}), so the Triad advisory does not apply here: work "
            f"from its assembly root {named}, cloned with `git clone "
            "--recurse-submodules` and `make bootstrap`, where the manifest "
            "and both legs are -- rather than adopting or scaffolding this "
            "leg")


# ---------------------------------------------------------------------------
# What is read
# ---------------------------------------------------------------------------


class Reading:
    """What `read()` found about one directory, and why -- never a verdict.

    `state` is one of `STATES`. `why` is the declared fact that decided it,
    in a sentence. `record_problems` are the reasons a PRESENT
    `single-repository.yaml` silences nothing, reported beside the advisory;
    `field_problems` are what a record that DOES silence leaves out. `leg` is
    set for a leg clone and says which leg and how it was known.
    """

    def __init__(self, state: str, why: str, record_problems=(),
                 field_problems=(), leg: dict | None = None):
        assert state in STATES, state
        self.state = state
        self.why = why
        self.record_problems = tuple(record_problems)
        self.field_problems = tuple(field_problems)
        self.leg = leg

    @property
    def advise(self) -> bool:
        """Is the advisory given here? The ONE question its callers ask."""
        return self.state == ADVISE

    def as_dict(self) -> dict:
        return {"state": self.state, "why": self.why,
                "advise": self.advise,
                "record_problems": list(self.record_problems),
                "field_problems": list(self.field_problems),
                "leg": self.leg}


def _read_mapping(path: Path):
    """`path` as a YAML mapping, or None -- never a refusal.

    The advisory is a sentence, not a check, so a manifest it cannot read is
    a manifest it does not see; the doctor's own rows are where a broken
    manifest is a finding.
    """
    if not path.is_file():
        return None
    try:
        data = load_yaml(path)
    except (Refusal, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_triad(manifest) -> bool:
    """Does this `project.yaml` declare the Triad?

    The detector the ratified rule names, and the one the shared agent
    protocol and the workstation bootstrap already use: `kind:
    project-manifest`, `schema: project-repo-schema`, and `legs:` naming a
    `spec` and a `code` leg. A project manifest that declares fewer legs is
    not a Triad, whatever its file is called.
    """
    if not isinstance(manifest, dict):
        return False
    if manifest.get("kind") != "project-manifest" \
            or manifest.get("schema") != "project-repo-schema":
        return False
    legs = manifest.get("legs")
    roles = {str(leg.get("role")) for leg in (legs if isinstance(legs, list)
                                              else [])
             if isinstance(leg, dict)}
    return set(LEG_ROLES) <= roles


def repository_name(url: str) -> str | None:
    """The repository name at the end of a remote url, case preserved.

    `git@github.com:Org/Atlas-spec.git`, `https://github.com/Org/brett-wip`
    and `/srv/remotes/Atlas-spec.git` all end in the name a person gave the
    repository, which is what the naming policy classifies. Only the last
    segment is read -- the organisation is part of no naming family, as
    `validate-repository-naming.py` says of a qualified name.
    """
    text = url.strip().replace("\\", "/").rstrip("/")
    name = re.split(r"[/:]", text)[-1]
    if name.lower().endswith(".git"):
        name = name[:-4]
    return name or None


def repository_names(root: Path) -> list[str]:
    """The names this repository goes by: its directory's, then `origin`'s.

    `origin` is asked only when `root` ITSELF carries a `.git`: git walks up
    to an ancestor otherwise, and an ancestor's name is not this directory's
    -- the trap `shape-doctor.py`'s `repo_local_origin_name` guards against.
    """
    names = [root.name]
    if (root / ".git").exists():
        try:
            url = git_out(["remote", "get-url", "origin"], cwd=root)
        except (Refusal, OSError):
            url = ""
        name = repository_name(url) if url else None
        if name and name not in names:
            names.append(name)
    return names


def _naming_policy(shape: Path) -> NamingPolicy | None:
    try:
        return NamingPolicy.load(shape / NAMING_POLICY)
    except (Refusal, OSError, UnicodeDecodeError):
        return None


def _leg_by_name(names: list[str], policy: NamingPolicy | None) -> dict | None:
    """A leg named as one: `<Project>-spec` or `<Project>-code`."""
    if policy is None:
        return None
    for name in names:
        found = policy.classify(name)
        if found is not None and found.family == "project-leg" \
                and found.role in LEG_ROLES:
            return {"role": found.role,
                    "assembly": name[:-len(f"-{found.role}")],
                    "how": f"`{name}` is the {found.role}-leg form of "
                           f"{NAMING_POLICY}"}
    return None


def _leg_by_agents_md(root: Path) -> dict | None:
    """A leg that says so in its own `AGENTS.md`, as the templates write it."""
    try:
        text = (root / AGENTS_MD).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    opening = LEG_OPENING_RE.match(text)
    if opening is None:
        return None
    named = LEG_ROOT_RE.search(" ".join(text.split()))
    return {"role": opening.group(1),
            "assembly": named.group(1) if named else None,
            "how": f"its {AGENTS_MD} is the {opening.group(1)} leg's, as "
                   f"templates/{opening.group(1)}-root/ writes it"}


def workspace_paths(env=None) -> list[Path]:
    """The checkouts the person's own workspace configuration names.

    `${AGENT_PROTOCOL_ROOT:-$HOME/.agents}/workspace.yaml` -- the one file the
    README says names a person's `<user>-wip` -- carries a top-level `path:`
    and, optionally, an `orgs:` map whose entries carry a `path:` of their
    own (the shape `opensoft/openRepoTools`' `resume` reads). Read only;
    a file that is absent or does not parse names nothing.
    """
    env = os.environ if env is None else env
    base = env.get("AGENT_PROTOCOL_ROOT") or os.path.join(
        os.path.expanduser("~"), ".agents")
    config = _read_mapping(Path(base) / "workspace.yaml")
    if config is None:
        return []
    raw = [config.get("path")]
    orgs = config.get("orgs")
    if isinstance(orgs, dict):
        raw += [entry.get("path") for entry in orgs.values()
                if isinstance(entry, dict)]
    found: list[Path] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            found.append(Path(os.path.expanduser(value.strip())).resolve())
        except (OSError, RuntimeError):
            continue
    return found


def _workspace(root: Path, names: list[str], policy: NamingPolicy | None,
               env) -> str | None:
    """Why this is a `<user>-wip` workspace repository, or None."""
    if policy is not None:
        for name in names:
            found = policy.classify(name)
            if found is not None and found.family == "workspace":
                return (f"`{name}` is the workspace (<user>-wip) form of "
                        f"{NAMING_POLICY}")
    try:
        here = root.resolve()
    except (OSError, RuntimeError):
        return None
    if here in workspace_paths(env):
        return ("the person's own workspace.yaml names this checkout as "
                "their workspace repository")
    return None


# -- the staying-single record ----------------------------------------------

#: What reading `single-repository.yaml` can come to.
RECORD_ABSENT = "absent"
RECORD_SILENCES = "silences"
RECORD_SILENCES_NOTHING = "silences-nothing"


def record_schema(shape: Path = SHAPE_ROOT) -> dict:
    """The record's schema, as data. A refusal when it cannot be read: it
    ships beside this file, so a checkout without it is the STANDARD being
    short, which the caller reports rather than guesses around."""
    data = load_yaml(shape / RECORD_SCHEMA)
    if not isinstance(data, dict) or data.get("kind") != SCHEMA_KIND:
        raise Refusal("record-schema-wrong-kind",
                      f"{RECORD_SCHEMA} does not declare kind {SCHEMA_KIND!r}")
    return data


def _value_problem(value, field: dict) -> str | None:
    """Why ONE present field's value is not what the schema says, or None."""
    expected = field.get("type")
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"is {value!r}, not a whole number"
    elif expected in ("string", "date"):
        if not isinstance(value, str) or not value.strip():
            return f"is {value!r}, not text"
        if PLACEHOLDER_RE.search(value):
            return f"still carries the template's placeholder {value!r}"
        if expected == "date":
            try:
                ok = bool(DATE_RE.match(value)) and \
                    _dt.date.fromisoformat(value) is not None
            except ValueError:
                ok = False
            if not ok:
                return f"is {value!r}, not an ISO date (YYYY-MM-DD)"
    if "value" in field and value != field["value"]:
        return f"is {value!r}; the schema fixes it at {field['value']!r}"
    return None


def field_problems(record: dict, shape: Path = SHAPE_ROOT) -> list[str]:
    """What a record of the right `kind` leaves out or gets wrong, by its
    schema. Reported as a note; the record is silent either way, because
    `kind:` is what decides and a person who wrote the file meant it."""
    try:
        schema = record_schema(shape)
    except (Refusal, OSError, UnicodeDecodeError) as exc:
        detail = exc.detail if isinstance(exc, Refusal) else str(exc)
        return [f"its schema could not be read to check the fields: {detail}"]
    fields = [field for field in (schema.get("fields") or [])
              if isinstance(field, dict) and field.get("name")]
    problems: list[str] = []
    for field in fields:
        name = str(field["name"])
        if record.get(name) is None:
            if field.get("required"):
                problems.append(f"`{name}` is missing")
            continue
        problem = _value_problem(record[name], field)
        if problem:
            problems.append(f"`{name}` {problem}")
    known = {str(field["name"]) for field in fields}
    problems += [f"`{key}` is not a field of the record"
                 for key in record if str(key) not in known]
    return problems


def read_record(root: Path, shape: Path = SHAPE_ROOT) -> tuple:
    """`(what the record comes to, why it silences nothing, its field notes)`.

    `kind:` DECIDES. A file that parses as a mapping declaring
    `single-repository-record` silences the advisory, and its field problems
    are notes. Anything else that is present -- unreadable, unparsable, not a
    mapping, another kind, not a file at all -- silences nothing and says
    why, so the person who wrote it learns that it is not being read.
    """
    path = root / RECORD_FILE
    if not path.exists():
        return RECORD_ABSENT, [], []
    if not path.is_file():
        return RECORD_SILENCES_NOTHING, ["it is not a file"], []
    try:
        data = load_yaml(path)
    except Refusal as exc:
        return RECORD_SILENCES_NOTHING, [f"it could not be read "
                                         f"({exc.code})"], []
    except (OSError, UnicodeDecodeError) as exc:
        return RECORD_SILENCES_NOTHING, [f"it could not be read "
                                         f"({type(exc).__name__})"], []
    if not isinstance(data, dict):
        return RECORD_SILENCES_NOTHING, ["it is not a YAML mapping"], []
    kind = data.get("kind")
    if kind != RECORD_KIND:
        return RECORD_SILENCES_NOTHING, [
            f"it declares kind {kind!r}, not {RECORD_KIND!r}"], []
    return RECORD_SILENCES, [], field_problems(data, shape)


# -- the reading -------------------------------------------------------------


def read(root, shape: Path = SHAPE_ROOT, env=None) -> Reading:
    """Is the advisory given in `root`, and if not, which declared fact says so?

    THE ORDER IS THE RATIFIED LIST'S, and only the advisory's own sentence
    depends on it: every silence is a silence however it was reached. The
    record is read LAST because a repository that is already a Triad, a
    holder, a leg or a workspace has the shape question answered whatever a
    stray `single-repository.yaml` in it says.
    """
    root = Path(root)
    project = _read_mapping(root / PROJECT_MANIFEST)
    if is_triad(project):
        return Reading(TRIAD_ROOT, f"{PROJECT_MANIFEST} declares the Triad: "
                                   "the schema, a spec leg and a code leg")
    family = _read_mapping(root / FAMILY_MANIFEST)
    if (family or {}).get("kind") == "family-manifest" \
            and (project or {}).get("kind") != "project-manifest":
        return Reading(FAMILY_HOLDER, f"{FAMILY_MANIFEST} declares a family "
                                      "holder, which pins projects and is "
                                      "not one")
    if not (root / ".git").exists():
        return Reading(NOT_A_REPOSITORY, "there is no repository here to "
                                         "advise about")
    policy = _naming_policy(shape)
    names = repository_names(root)
    leg = _leg_by_name(names, policy) or _leg_by_agents_md(root)
    if leg is not None:
        return Reading(LEG_CLONE, leg["how"], leg=leg)
    workspace = _workspace(root, names, policy, env)
    if workspace is not None:
        return Reading(WORKSPACE, workspace)
    state, silences_nothing, notes = read_record(root, shape)
    if state == RECORD_SILENCES:
        return Reading(RECORDED_SINGLE, f"{RECORD_FILE} records that this "
                                        "project stays a single repository",
                       field_problems=notes)
    return Reading(ADVISE, "a repository that has not elected the Triad and "
                           "has recorded nothing", silences_nothing)
