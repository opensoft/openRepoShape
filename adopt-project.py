#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adopt an EXISTING repository into the three-repository shape, IN PLACE.

    ./adopt-project.py plan    --source <path|org/repo> --project <Project>
    ./adopt-project.py check   --plan adoption-plan.yaml
    ./adopt-project.py execute --plan adoption-plan.yaml [--yes]

IN PLACE IS THE WHOLE POSTURE, and it is a ruling (Brett Heap, 2026-09-02):
the repository being adopted KEEPS ITS NAME, ITS IDENTITY AND ITS FULL
HISTORY and becomes the assembly root. `<Project>-spec` and `<Project>-code`
are NEW repositories, extracted with history-preserving filters. The source is
never deleted, never renamed, and never force-pushed: the only change to it is
ONE split commit, which arrives on a BRANCH and by pull request, because the
organisations this is built for apply PR-only rulesets and a tool that needed
a bypass would be a tool that cannot be used where it is needed.

THREE SUBCOMMANDS, BECAUSE THE MIDDLE ONE IS A HUMAN.

  plan     walks the source at its default branch, classifies every top-level
           path against `contracts/path-classification.yaml`, and writes
           `adoption-plan.yaml`. Paths it cannot honestly call, every path
           holding one of the source's own submodules, and every path
           `execute` will not extract into a leg as it is named, carry
           `leg: null`, `review_required: true` and the QUESTION to ask.
           A leg path over a path it keeps in the root itself is a NOTE,
           not a refusal: the answer is the person's to change.
  check    validates a plan against the source: each entry path bound for
           a leg one `execute` will extract, every path covered exactly
           once, no unresolved legs, leg names conforming to the naming
           policy, each leg's mount path one `execute` can mount
           (`spec`, `legs/spec`; never `spec/` or `./spec`, a name Git or
           Windows keeps for itself such as `.git` or `CON`, or a value
           `execute` would refuse; the two never equal or nested, in any
           case; neither equal to, around or inside a path the shape writes
           into the root, `shape/`, or a source path the plan keeps there),
           no path kept in the root where the shape writes (a plain file at
           a directory it writes into, `.github`, `contracts` or `scripts`,
           or the source's own path at a copy it writes under `shape/`, in
           any case), the source's own submodules kept on one leg with
           their `.gitmodules`, registered there and never in the root, each
           relative url naming the same repository from the leg as from the
           source, and no symlink kept in the root that the shape would
           write one of its files, or that file's copy under `shape/`,
           through where it cannot (one that dangles, loops, or leads out of
           the root or into a leg, one that leads the copy onto something
           already there, or one that carries the shape's scripts anywhere
           but one directory directly under the root), whether the disk
           keeps case or ignores it. It prints what will happen and changes
           nothing.
  execute  creates the two legs, extracts them with `git filter-repo`, makes
           the one split commit on a branch of the source, sets the
           `xf-project-<id>` topic on all three (skipped for local remotes),
           and then VERIFIES by blob sha that every source path landed in
           exactly one place, and that the root's only submodules are the
           two leg mounts, each at the commit pushed to its leg.

THE PLAN IS AN ARTIFACT A HUMAN OR AN AI EDITS. That is why it is YAML with
reasons in it rather than a pipe between two processes: the classifier is
right about `openspec/` and cannot be right about `examples/golden-run/`
without knowing whether the specification cites it. `execute` REFUSES while
any `leg:` is still null, and on every other finding `check` reports, before
it has created a leg repository or pushed anything -- a source submodule's
relative url resolved again from the leg remotes it is about to create, which
under `--local-remote-dir` are not the GitHub ones `check` resolves from, and
the place outside the assembly that a symlink kept at a path the shape writes
leads to asked again of the disk, a climb from its own work directory.

WHY `git filter-repo` AND NOT A VENDORED COPY. Extracting history correctly is
a solved problem with one correct implementation, and a vendored copy of it
would be a second implementation that drifts. It is a hard REQUIREMENT here,
preflighted with an exact install hint; the alternative — `git subtree` or a
hand-rolled `filter-branch` — is slower, rewrites author dates, and is exactly
the kind of thing that is discovered to have been wrong a year later.

A LEG WITH NOTHING IN IT IS SEEDED, NOT EXTRACTED. A repository can honestly
have no code yet — InkRouter's IRRS and IRSS are specifications (Brett Heap,
2026-09-04) — and `git filter-repo` over an empty path list yields an empty
HISTORY rather than an empty repository. So a leg no entry assigns a path to
is seeded from `templates/<role>-root/` as one initial commit, the plan
records `seeded_from_template: true` for it, the split still mounts and pins
it, and the verification table reads `code: 0 of N source paths (seeded from
template)`. `check` WARNS; `execute` refuses without `--allow-empty-leg
<leg>`, in the plan or on its command line, because a plan that lost its code
paths to a bad edit looks identical from here.

MODE. `in-place` is the only mode in v0.2. A future `new-root` mode would
create a NEW assembly root and reduce the source to one leg; it is recorded in
the plan's `mode:` field so a plan written today says which posture it took,
rather than being reinterpreted later by a tool that grew a second one.

EXIT CODES: 0 done · 1 findings (a plan that does not check out; a
verification mismatch) · 2 a refusal — the question could not be asked.
`execute` has other exit 2s, once the leg repositories exist (a refused push,
a refused mount). Two of them are GitHub mode's alone, and both come AFTER both
legs and the split branch are pushed and the verification has passed: `gh pr
create` refused (`The branch IS pushed`, printed after the table) and the
topic would not set (`The split IS pushed and the pull request IS open`). Each
prints the command that finishes the job by hand, and that command is the way
out: a re-run into fresh legs abandons the pushed pair for a second. A
verification that fails outranks both, with exit 1 and no command to open the
pull request.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from path_classify import PathPolicy, Verdict  # noqa: E402
from repo_shape import (  # noqa: E402
    free_plan_secret_hint,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, YamlError,
    accepts_role, checked_value, double_quoted, git_out, load_yaml,
    parse_yaml, redacted, remote_is_a_path, remote_key, remote_local_path,
    tree_digest,
)
from shape_materialize import (  # noqa: E402
    ADOPT_MAKEFILE_BLOCK, BOOTSTRAP, RULESET_HINT, SHAPE_REPOSITORY,
    SYMLINK_HOPS, TOO_MANY_SYMLINKS, CommandFailed, Materialized,
    assembly_root_paths,
    collision_follow_up, copy_tree, default_reference, election_date,
    env_commit, escape_what_stdout_cannot_encode, git_init_commit,
    materialize_assembly_root, naming_block, run, template_files, write_lf,
    write_paths_listing,
)
# The leg-path rule (#179) is `scaffold-project.py`'s as much as adopt's, so it
# is imported as one unit and not listed among the materializer's names above.
# `leg_path_problem` is not called here: `tests/test_adopt_leg_paths.py` asks
# it through this module, as it did when the rule was defined in it, which is
# what shows the move changed no behaviour.
from shape_materialize import (  # noqa: E402
    WINDOWS_ABSOLUTE_RE, leg_path_problem, leg_path_problems,
    refuse_bad_leg_paths as _refuse_bad_leg_paths,
)
import shape_advisory  # noqa: E402
# #172's shape half, shared with the scaffold since #197 (see that section
# below), under the names this file has always called it by.
from shape_materialize import (  # noqa: E402
    CASE_ASIDE as _CASE_ASIDE, MOVE_THE_LEG, first_and_more as _first_and_more,
    path_overlap as _overlap, shape_path_collisions,
)
# Whether a value this tool writes into a file is text a file can hold
# (#255), asked beside `one_printable_line`, the trailer's question.
from shape_materialize import unwritable_reason  # noqa: E402

#: The naming policy this tool classifies leg names against. One constant,
#: because three spellings of the same path is how the second one goes stale.
NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
PATH_POLICY = SHAPE_ROOT / "contracts" / "path-classification.yaml"

#: A declared pin here is a NAME, `[owner/]openProduct` — never `@<commit>`.
#: Adopting a project records no commit for a neutral-product pin at plan
#: time (there is no `contracts/<product>-pin.yaml` for one, unlike
#: `scaffold-project.py --pin`), so a value carrying `@` is almost always
#: that OTHER tool's syntax pasted in by habit, and is refused rather than
#: silently written into `neutral_product_pins:` as a name nothing matches.
PIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?$")


def _checked_pin_name(raw: str) -> str:
    name = raw.strip()
    if not PIN_NAME_RE.match(name):
        raise Refusal(
            "adopt-pin-malformed",
            f"--pin {raw!r} is not `[owner/]openProduct`",
            "Remediation: pass --pin openGlass, or name the owner explicitly "
            f"with --pin {NEUTRAL_PRODUCT_OWNER}/openGlass — every neutral "
            f"open<Product> lives under {NEUTRAL_PRODUCT_OWNER} by the "
            "family's rule. Adopting a project declares no commit for a "
            "neutral-product pin at plan time, so drop `@<commit>` if you "
            "copied it from `scaffold-project.py --pin`.",
        )
    return name


PLAN_KIND = "adoption-plan"

#: The OTHER plan kind, declared here beside the one this tool writes so that
#: the two are read together and no third file can invent a third spelling.
#: `shape-doctor.py --placement-plan` writes it for a project that is ALREADY
#: split — its entries name paths inside MOUNTED LEGS — and this tool splits a
#: repository that is not. The entries are these entries exactly, which is the
#: point: a person who has resolved an adoption plan has resolved one of
#: those. What must never happen is one arriving at `execute`, which creates
#: two repositories and rewrites history with `git filter-repo`; the `kind:`
#: is the boundary, and `Plan.load` refuses across it BY NAME rather than by a
#: mismatch a reader has to interpret.
PLACEMENT_PLAN_KIND = "placement-plan"

ADOPT_BRANCH = "adopt/three-repo-shape"
COLLISION_DIR = "shape"
#: The shape's own list of the files it copied into the assembly root.
#: `_shape_file_findings` reads it out of the SPLIT COMMIT and checks every
#: path it names against that commit's tree (#167).
SHAPE_PIN = "contracts/shape-pin.yaml"
#: The mode `git ls-tree` reports for a SYMLINK: its blob is the link's
#: target. `_SplitTree` follows one the way a checkout of the split does.
SYMLINK_MODE = "120000"
#: The modes of a regular file in a tree, executable or not: what a
#: checkout's `is_file()` finds, so the only thing a pinned path may lead to.
FILE_MODES = ("100644", "100755")
LEG_VALUES = ("spec", "code", "root", "drop")
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]
#: The file `git submodule add` records a mount in. `_mount_the_legs` checks,
#: writes, stages and edits it, and `check` and `execute` ask which leg the
#: plan gave the source's own -- named once so those uses cannot spell it
#: differently.
GITMODULES = ".gitmodules"
#: The mode `git ls-tree` reports for a SUBMODULE: a commit of another
#: repository, recorded in this tree as a gitlink rather than as a file.
GITLINK_MODE = "160000"

#: THE SPEC-ONLY CASE. A repository can honestly have nothing for one leg —
#: InkRouter's IRRS and IRSS are specifications with no implementation yet
#: (Brett Heap, 2026-09-04: "We do not have any code yet for either service").
#: A leg that no plan entry assigns a path to CANNOT be extracted: `git
#: filter-repo` over an empty path list rewrites every commit to nothing and
#: leaves an empty history, which is not the same thing as an empty
#: repository and is not something to push at a project. Such a leg is SEEDED
#: from the shape's own leg template as ONE initial commit — the same bytes
#: `scaffold-project.py` would have written for a new project — and the split
#: commit mounts it exactly like an extracted one. It carries no history from
#: the adopted repository because there was none to carry, and the
#: verification table says so rather than reporting a hole.
SEED_TEMPLATE = {"spec": "templates/spec-root", "code": "templates/code-root"}
EXTRACTED_LEGS = ("spec", "code")

FILTER_REPO_HINT = (
    "Remediation: install it — `pip install git-filter-repo`, or "
    "`apt install git-filter-repo`, or `brew install git-filter-repo`; it is "
    "one file on PATH named `git-filter-repo`. It is NOT vendored here on "
    "purpose: history extraction has one correct implementation and a copy of "
    "it is a second one that drifts."
)


# ---------------------------------------------------------------------------
# A very small YAML writer, for the one document this tool emits
# ---------------------------------------------------------------------------
#
# `repo_shape.parse_yaml` reads a SUBSET, so this writes the same subset: block
# mappings, block sequences and single-line scalars: ONE line whatever the
# string, because a quoted one is spelled by `repo_shape.double_quoted` from
# the reader's own escape tables. A name holding a line break (the macOS
# `Icon\r`), a control character or a byte that is not UTF-8 is one line the
# reader gives back unchanged, and `check` can name it (#199);
# `tests/test_adopt_plan_escapes.py` proves that round trip for every code
# point to U+02FF and a sample above it, and for a seeded sample of strings
# of them, not only for the strings a plan happens to hold; not for a bare
# YAML keyword (`null`, `true`, `false`), which `y` writes unquoted and the
# reader takes as None or a bool, #181's to fix. Everything it emits is
# read back by `check`, and `tests/test_adopt_plan.py` round-trips a plan
# through both, which is what keeps the writer and the reader honest about
# each other.

#: Ends at `\Z`, not `$`: `$` also matches before a FINAL newline, and wrote a
#: file named `Icon\n` bare, over two lines of the plan (#199).
_PLAIN_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_./@:+-]*\Z")


def y(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    text = str(value)
    if text and _PLAIN_RE.match(text) and not text.endswith(":"):
        return text
    return double_quoted(text)


def emit(lines: list[str], key: str, value, indent: int = 0) -> None:
    lines.append(f"{' ' * indent}{key}: {y(value)}")


# ---------------------------------------------------------------------------
# The source repository, read ONLY
# ---------------------------------------------------------------------------


#: A `.gitmodules` key as `git config --list` prints it: the section and the
#: variable lower-cased by git, the `<name>` exactly as written. A key with no
#: `<name>` does not match, because git skips one when it clones; an EMPTY
#: `<name>` does, and `_a_name_git_ignores` then ignores it as git does.
SUBMODULE_KEY_RE = re.compile(r"submodule\.(?P<name>.*)\.(?P<key>path|url)")
#: The `git` subcommand that reads and writes a config file: a source's
#: `.gitmodules`, a leg mount's url, the elector's name.
GIT_CONFIG = "config"
#: The `git` subcommand that prints one object: a source's `.gitmodules`
#: and the target of a symlink it keeps in the root, and in the split commit
#: a symlink's target and the shape pin.
GIT_CAT_FILE = "cat-file"


def _git_path(raw: bytes) -> str:
    """A path git printed under `-z`, as `Source.tree()` spells it: UTF-8,
    and a byte that is not UTF-8 kept as a surrogate rather than refused. A
    gitlink and its `.gitmodules` registration are compared as strings, so
    both are decoded here."""
    return raw.decode("utf-8", "surrogateescape")


def _one_line(text: str) -> str:
    """What git said, on one line: `check` prints one FINDING per line."""
    return " ".join(text.split())


def _a_name_git_ignores(name: str) -> bool:
    """git's `check_submodule_name`: a submodule name that is empty, or has a
    `..` component between `/` or `\\` separators on every platform, is
    skipped with `warning: ignoring suspicious submodule name`. Its `path`
    and `url` then register nothing, though `git config` lists both."""
    return not name or ".." in re.split(r"[/\\]", name)


class Registrations:
    """What git's submodule reader (submodule-config.c, `parse_config`) makes
    of a `.gitmodules`: `path in registrations` when the file registers that
    path WITH a url, and `why_not(path)` when an entry names it and git
    registers nothing there.

    `read` takes each `submodule.<name>.path` or `.url` value in the file's
    order and applies it as git does: a name git ignores registers nothing; a
    value starting with `-` is ignored and the one before it stands; a later
    value overrides an earlier one for its name, and a path belongs to the
    LAST name given it. git keeps that path-to-name map by path, so a name
    moved to another path removes whatever its old path held, even when a
    later name had taken the path over -- `_move`'s `pop`, which is git's
    `cache_remove_path`. How a named path came to register nothing is kept
    in words: the person told that a submodule is not registered is looking
    at an entry for it, and is told why git ignores that entry (#166).
    """

    def __init__(self) -> None:
        self._path_of: dict[str, str] = {}
        self._name_at: dict[str, str] = {}
        self._url_of: dict[str, str] = {}
        self._lost: dict[str, str] = {}

    def __contains__(self, path: str) -> bool:
        name = self._name_at.get(path)
        return name is not None and bool(self._url_of.get(name))

    def url(self, path: str) -> str:
        """The url git reads for the submodule registered at `path`; empty
        when it registers none there."""
        name = self._name_at.get(path)
        return "" if name is None else self._url_of.get(name, "")

    def why_not(self, path: str) -> str | None:
        """Why git registers nothing at `path` though an entry names it;
        None when no entry of the file does."""
        name = self._name_at.get(path)
        if name is not None:
            return (f"its {GITMODULES} entry {_spelled(name)} has no url git "
                    "reads")
        return self._lost.get(path)

    def read(self, name: str, key: str, value: str) -> None:
        if _a_name_git_ignores(name):
            self._lose(key, value, f"git ignores its {GITMODULES} entry "
                                   f"{_spelled(name)} as a suspicious name")
        elif value.startswith("-"):
            self._lose(key, value, f"git ignores its {GITMODULES} path, which "
                                   "starts with `-`")
        elif key == "url":
            self._url_of[name] = value
        else:
            self._move(name, value)

    def _lose(self, key: str, path: str, why: str) -> None:
        if key == "path":
            self._lost[path] = why

    def _move(self, name: str, path: str) -> None:
        old = self._path_of.get(name)
        if old is not None and self._name_at.pop(old, None) is not None:
            self._lost[old] = (f"git dropped its path when the {GITMODULES} "
                               f"entry {_spelled(name)} moved to "
                               f"{_spelled(path)}")
        self._path_of[name] = path
        self._name_at[path] = name


#: The keys git's submodule reader dies on when one has no value at all,
#: under a name it does not ignore (submodule-config.c, `parse_config`).
#: Measured for #195 with git 2.43, a `git fast-export` over a gitlink:
#: `path`, `url`, `ignore` and `update` each end it with `missing value for
#: '<key>'`, and `branch` with a crash (SIGSEGV, exit 139) and nothing said;
#: `fetchRecurseSubmodules` and `shallow` with no value are read as true,
#: and nothing dies.
SUBMODULE_VALUED_KEY_RE = re.compile(
    r"submodule\.(?P<name>.*)\.(?:path|url|ignore|update|branch)")
#: The keys git's submodule reader dies on when one has a VALUE it refuses,
#: under a name it does not ignore (#215); `_refused_value` says which
#: values. `ignore` with a value git does not know only warns, and `path`,
#: `url` and `branch` take any value, so none of them is here.
SUBMODULE_TYPED_KEY_RE = re.compile(
    r"submodule\.(?P<name>.*)\.(?P<key>update|shallow|fetchrecursesubmodules)")
#: The values `update` may take in a `.gitmodules` (submodule.c,
#: `parse_submodule_update_type`), as git spells them, case and all.
UPDATE_STRATEGIES = ("checkout", "rebase", "merge", "none")
#: The words git reads as a boolean, in any ASCII case (config.c / parse.c,
#: `git_parse_maybe_bool_text`).
BOOLEAN_WORDS = ("true", "yes", "on", "false", "no", "off")
#: An integer as `git_parse_signed` reads one: `strtoimax(value, &end, 0)`,
#: which skips C whitespace and takes a sign and a hex, octal or decimal
#: number -- and, where the C library reads C23 binary numbers (glibc 2.38
#: or later, for one), a `0b` binary one -- and then a unit, which is all
#: that may follow.
GIT_INTEGER_RE = re.compile(
    r"[ \t\n\v\f\r]*(?P<sign>[+-]?)(?P<digits>0[xX][0-9a-fA-F]+|0[bB][01]+"
    r"|0[0-7]*|[1-9][0-9]*)(?P<unit>[kKmMgG]?)")
#: `get_unit_factor`, by the unit's lower case.
UNIT_FACTORS = {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}
#: The `int` git reads a boolean's number into: 2**31 - 1 is its largest.
GIT_INT_BITS = 31
#: Who refuses a value as a boolean (`_who_refuses_a_boolean`): no git
#: reads it, or only some of the gits `execute` may run do, and why.
EVERY_GIT = "every git"
OLDER_GITS_REFUSE = ("a number git 2.49 and older refuse, and 2.50 and later "
                     "read")
SOME_LIBRARIES_REFUSE = ("a `0b` number, which a git reads only where its C "
                         "library reads C23 binary numbers (glibc 2.38 or "
                         "later, for one)")


def _who_refuses_a_boolean(value: str) -> str | None:
    """None where every git takes `value` as a boolean
    (`git_parse_maybe_bool`): empty, which is false; one of BOOLEAN_WORDS;
    or an integer `git_parse_int` takes, which is true unless it is zero.
    Otherwise EVERY_GIT where no git takes it, or why only some do.

    The integer must fit an `int` once its unit is applied. Where gits
    differ on one, `check` refuses it with the gits that refuse it: a
    refusal there costs an edit to an absurd value, and a git that refuses
    it in the extraction costs both leg repositories. git 2.50 moved the
    bound below zero by one (`(-max - 1) / factor`, where 2.49 and before
    have `-max / factor`), so -2147483648, -2097152k, -2048m and -2g,
    however spelled, are OLDER_GITS_REFUSE: measured with git 2.43, each
    passed `check` and `execute` died after both leg repositories were
    made. A `0b` number, which git reads only where its C library's
    `strtoimax` does, is SOME_LIBRARIES_REFUSE."""
    if not value or (value.isascii() and value.lower() in BOOLEAN_WORDS):
        return None
    number = GIT_INTEGER_RE.fullmatch(value)
    if number is None:
        return EVERY_GIT
    digits = number["digits"]
    binary = digits[1:2] in ("b", "B")
    if digits[1:2] in ("x", "X"):
        size = int(digits[2:], 16)
    elif binary:
        size = int(digits[2:], 2)
    else:
        size = int(digits, 8 if digits.startswith("0") else 10)
    factor = UNIT_FACTORS[number["unit"].lower()]
    every_git_reads = ((1 << GIT_INT_BITS) - 1) // factor
    newer_gits_read = ((1 << GIT_INT_BITS) // factor if number["sign"] == "-"
                       else every_git_reads)
    if size > newer_gits_read:
        return EVERY_GIT
    if binary:
        return SOME_LIBRARIES_REFUSE
    if size > every_git_reads:
        return OLDER_GITS_REFUSE
    return None


def _refused_value(key: str, value: str) -> str | None:
    """What git's submodule reader dies on, in its words with the key and
    the value spelled, when `key` is one SUBMODULE_TYPED_KEY_RE names and
    `value` one git refuses for it; None otherwise (#215).

    git reads the CHECKED-OUT `.gitmodules` through `gitmodules_cb`
    (submodule-config.c), which sets `overwrite`, so `parse_config` reads
    every value, a key given twice included, and dies on the first it
    refuses. Read in the source code of git 2.39.5 through 2.51.0, the
    same in each but for the bound `_who_refuses_a_boolean` names, and
    measured with git 2.43 over `git fast-export`:

      * `update`, `parse_submodule_update_strategy` (submodule.c): one of
        UPDATE_STRATEGIES, or `!` and a command, which `parse_config`
        refuses in a `.gitmodules`; anything else, an empty value too, ends
        it with `invalid value for 'submodule.<name>.update'`.
      * `shallow`, `git_config_bool`: a value `git_parse_maybe_bool` does not
        read ends it with `bad boolean config value '<value>' for '<key>'`.
      * `fetchrecursesubmodules`, `parse_fetch_recurse`, which dies on an
        error for the checked-out file (`die_on_error`): a boolean or
        `on-demand`, exactly; anything else ends it with `bad <key>
        argument: <value>`.

    A number only some gits read as a boolean is refused as the gits that
    refuse it say, and the finding says which gits those are."""
    typed = SUBMODULE_TYPED_KEY_RE.fullmatch(key)
    if typed is None or _a_name_git_ignores(typed["name"]):
        return None
    said = _spelled(value) if value else "an empty value"
    if typed["key"] == "update":
        if value in UPDATE_STRATEGIES:
            return None
        why = (f"a command, which git never takes from a {GITMODULES}"
               if value.startswith("!") else
               f"which is not one of {_listed(list(UPDATE_STRATEGIES))}")
        return f"invalid value for {_spelled(key)}: {said}, {why}"
    refusers = _who_refuses_a_boolean(value)
    if refusers is None:
        return None
    if typed["key"] == "shallow":
        return (f"bad boolean config value {said} for {_spelled(key)}"
                + ("" if refusers == EVERY_GIT else f", {refusers}"))
    if value == "on-demand":
        return None
    return (f"bad {_spelled(key)} argument: {said}, "
            + ("which is neither a boolean nor `on-demand`"
               if refusers == EVERY_GIT else refusers))


def _registrations(listed: bytes) -> Registrations | str:
    """`git config -z --list` output, read by `Registrations`; or what git's
    submodule reader dies on, at the first key in the file it dies on: one
    SUBMODULE_VALUED_KEY_RE names with no value at all, or one whose value
    it refuses (`_refused_value`, #215). `-z` prints a key with no value
    with no newline, and git looks for its value after it has filtered the
    name and before it filters the value."""
    registrations = Registrations()
    for record in listed.split(b"\x00"):
        key, newline, value = _git_path(record).partition("\n")
        valued = SUBMODULE_VALUED_KEY_RE.fullmatch(key)
        if valued and not newline and not _a_name_git_ignores(valued["name"]):
            return f"missing value for '{key}'"
        refused = _refused_value(key, value) if newline else None
        if refused:
            return refused
        match = SUBMODULE_KEY_RE.fullmatch(key)
        if not match:
            continue
        registrations.read(match["name"], match["key"], value)
    return registrations


class InTheHistory(str):
    """What git says of a `.gitmodules` its submodule reader cannot read, as
    `Source.registered_submodules` answers for a source whose TIP holds no
    gitlink and whose history does (#195): a `str`, so that every reader of
    that answer takes it as git's words, and `gitlink`, where the history
    holds one, as `_exported_gitlink` names it."""

    gitlink: str

    def __new__(cls, words: str, gitlink: str) -> "InTheHistory":
        said = super().__new__(cls, words)
        said.gitlink = gitlink
        return said


#: `git log` asked for the diffs `git fast-export` makes, a NUL after each
#: field; `_exported_gitlink` says why each flag is there.
EXPORTED_DIFFS = ["--no-replace-objects", "log", "-z", "--raw", "--root",
                  "--no-renames", "--diff-merges=first-parent",
                  "--ignore-submodules=none", "--no-show-signature",
                  "--no-abbrev", "--no-color", "--format=%H"]


def _exported_gitlink(source: "Source") -> str | None:
    """Where the history `execute`'s extraction rewrites holds a gitlink, as
    a finding names it -- "commit 3feb96f2c1a0 removes `vendor/b`" -- or
    None where it holds none (#195).

    `_extract_leg` clones the source and runs `git filter-repo`, which runs
    `git fast-export --all` in the clone: every branch and tag of the source,
    which is what `git clone` copies, and the commit the plan names. It
    diffs each commit against its first parent, a root against nothing, and
    for every gitlink one of those diffs adds, removes or moves to another
    commit, git's submodule reader reads the clone's CHECKED-OUT
    `.gitmodules`: the plan's commit's, whatever leg the plan gives it.
    Measured with git 2.43 and `git filter-repo` 2.47.0, a tip `.gitmodules`
    that reader cannot read failed the extraction, after both leg
    repositories were made, for a gitlink in the history of the branch being
    adopted, on a side branch merged into it, on a branch never merged, on a
    commit only a tag reaches, in the root commit of a branch of its own,
    one that two merges alone added and removed, and one the source's own
    `git log` does not see for a replacement or a graft.

    A TYPE CHANGE -- a file or a symlink becoming a gitlink, or a gitlink
    becoming one -- is not read that way: git's diff asks the submodule
    reader about a changed path only when both of its sides are gitlinks.
    Measured, a gitlink that only ever entered and left by a type change
    adopted on main beside the same `.gitmodules`, so `_first_gitlink`
    passes a type change by; one that enters by a type change and leaves by
    a removal is found at the removal.

    A BRANCH here is a `refs/heads/` ref of the source, as the clone takes
    it: an `org/repo` source, which `Source.open` clones, has its default
    branch alone, and its other branches, its remote-tracking refs, are no
    more in the extraction's clone than in this scan; neither is a commit
    that only the source's detached HEAD reaches, which `_extract_leg`'s
    checkout of the plan's commit leaves behind. Measured, each of those
    adopted on main beside the same `.gitmodules`.

    So `git log` is asked for those diffs, over those commits, and read
    until the first gitlink in one: a `160000` mode on either side of a
    change that is no type change.
    `--root` and `--diff-merges=first-parent` are fast-export's root and
    merge diffs, which `log.showRoot=false` and a plain `git log` leave out;
    `--no-renames`, its diffs, one path to a change. `--ignore-submodules=
    none`, because `git log` runs the same submodule reader, on the SOURCE's
    checked-out `.gitmodules`, and died on the very file this is asked about
    (exit 128), and because `diff.ignoreSubmodules=all` hides every gitlink.
    `--no-replace-objects`, because a clone copies no `refs/replace/`, and a
    replacement can hide the commit that holds one. `GIT_GRAFT_FILE` naming
    a file that does not exist, because a clone copies no `info/grafts`
    either, a graft can hide that commit too, and `--no-replace-objects`
    leaves grafts on. `--no-show-signature`, because `log.showSignature`
    runs gpg on every signed commit and writes what it says into this
    output, ahead of the commit it names.

    The output is read as it comes and the scan stopped at the first gitlink,
    so a source that holds one is not read to its root. A source that holds
    none is read once, end to end, at about the cost of one `git fast-export
    --no-data` over the same history, which the extraction runs and then
    rewrites: measured here, 100,001 commits in 4.9 to 5.2 s against 4.2 to
    4.5 s for that export, and 5010 commits in 0.15 s. A scan git cannot
    finish is refused as `git-failed`, as `git_out` refuses: a history that
    could not be read has not been shown to hold no gitlink.
    """
    command = ["git", *EXPORTED_DIFFS, source.commit, "--branches", "--tags",
               "--"]
    with tempfile.TemporaryDirectory() as empty:
        no_grafts = {**os.environ,
                     "GIT_GRAFT_FILE": os.path.join(empty, "grafts")}
        with tempfile.TemporaryFile() as said, subprocess.Popen(
                command, cwd=source.path, stdout=subprocess.PIPE,
                stderr=said, env=no_grafts) as log:
            found = _first_gitlink(log.stdout)
            if found is not None:
                log.kill()
            elif log.wait():
                said.seek(0)
                raise Refusal("git-failed", "`{}` in {} exited {}: {}".format(
                    " ".join(command[1:]), source.path, log.returncode,
                    said.read().decode("utf-8", "replace").strip()))
    return found


#: How a finding says what a commit does to the gitlink it names: `git log
#: --raw`'s status letter, a new commit being a change. A type change, `T`,
#: is never named: `_first_gitlink` passes it by (`_exported_gitlink`).
GITLINK_CHANGES = {"A": "adds", "D": "removes"}
#: `git log --raw`'s status letter for a type change.
TYPE_CHANGE = "T"


def _first_gitlink(stream) -> str | None:
    """The first gitlink `git log` writes, as `_exported_gitlink` names it.

    With `-z`, `--format=%H` and `--raw`, each field ends in a NUL: a
    commit, then for each path it changes `:<mode> <mode> <oid> <oid>
    <status>` and the path, raw bytes. A newline before a commit or a
    change is not part of it. So a field after a change is a path, whatever
    it spells, and any other is a commit or a change. A type change to or
    from a gitlink is no gitlink here: git's submodule reader never reads
    `.gitmodules` for one."""
    commit, change, rest = "", None, b""
    for chunk in iter(lambda: stream.read(1 << 16), b""):
        *fields, rest = (rest + chunk).split(b"\x00")
        for field in fields:
            if change is not None:
                if GITLINK_MODE in change[:2] and change[-1] != TYPE_CHANGE:
                    return (f"commit {commit[:12]} "
                            f"{GITLINK_CHANGES.get(change[-1], 'changes')} "
                            f"{_spelled(_git_path(field))}")
                change = None
            elif field.lstrip(b"\n").startswith(b":"):
                change = field.lstrip(b"\n")[1:].decode().split()
            else:
                commit = field.strip().decode()
    return None


def _read_for_the_history(source: "Source", tree: list,
                          words: str) -> InTheHistory | None:
    """`words`, what git says of the source's `.gitmodules`, as an
    `InTheHistory` naming the gitlink the extraction reads that file for;
    None when the history holds none, or when the file at the tip is not a
    file the clone checks out as one, which `_where_git_fails` leaves to
    the clone."""
    if not any(path == GITMODULES and mode in FILE_MODES
               for path, mode, _, _ in tree):
        return None
    gitlink = _exported_gitlink(source)
    return None if gitlink is None else InTheHistory(words, gitlink)


class Source:
    """A repository being read, and nothing more. Nothing here writes to it."""

    def __init__(self, path: Path, repository: str | None, branch: str,
                 commit: str, work_root: Path | None = None):
        self.path = path
        self.repository = repository
        self.branch = branch
        self.commit = commit
        #: The work directory this run opened the source in: where a named
        #: repository is cloned to be read, and where `execute` makes the
        #: assembly's clone, so where a symlink the plan keeps in the root
        #: leads when it climbs above the root (#183).
        self.work_root = work_root

    @classmethod
    def open(cls, spec: str, work_root: Path) -> "Source":
        """`spec` is a local path (used in place) or `org/repo` (cloned)."""
        candidate = Path(spec).expanduser()
        if candidate.exists():
            path = candidate.resolve()
            repository = _remote_repository(path)
        else:
            if ("/" not in spec or WINDOWS_ABSOLUTE_RE.match(spec)
                    or unwritable_reason(spec) or spec.startswith("-")):
                # A DRIVE-LETTER PATH IS A PATH THAT IS NOT THERE, never an
                # `org/repo`. `D:/work/Thing` carries a `/` and would
                # otherwise be handed to `gh repo clone` as an owner named
                # `D:`; `os.path.isabs` cannot be asked instead, because it
                # answers False for that string on Linux and macOS and this
                # refusal must read the same on every platform.
                # NOR IS A NAME THAT IS NOT TEXT (#255). Since #247 a plan's
                # `local_path:` can spell a NUL, a control character or a
                # lone surrogate, and the reader gives it back: a path that
                # cannot exist, which reached `print` (a surrogate raised on
                # a strict stdout) or `subprocess` (a NUL raised there) as a
                # traceback, where main had refused it.
                # NOR IS A NAME THAT BEGINS WITH `-`. It is the first
                # argument `gh repo clone` is given, and gh's own parser
                # reads it as an option: `-u/x` set `--upstream-remote-name`
                # to `/x`. No GitHub owner name begins with `-`, so nothing
                # gh could clone is refused here.
                raise Refusal(
                    "source-unresolvable",
                    f"--source {spec!r} is neither a path that exists nor an "
                    "`org/repo` name",
                    "Remediation: pass a local clone's path, or `org/repo`.")
            repository = spec
            path = work_root / "source-readonly" / spec.split("/")[-1]
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"cloning {spec} (read only) into {path}")
            try:
                run(["gh", "repo", "clone", spec, str(path), "--", "--quiet"])
            except CommandFailed as exc:
                raise Refusal(
                    "source-unclonable",
                    f"could not clone {spec}: {exc.output.strip()[:400]}",
                    "Remediation: check `gh auth status` and the repository "
                    "name, or clone it yourself and pass the path.") from exc
        branch = _default_branch(path)
        commit = git_out(["rev-parse", branch], cwd=path).lower()
        return cls(path, repository, branch, commit, work_root)

    def tree(self) -> list[tuple[str, str, str, int]]:
        """(path, mode, blob sha, size) for every file at the pinned commit."""
        raw = git_out(["ls-tree", "-r", "-l", "-z", self.commit],
                      cwd=self.path, binary=True)
        out = []
        for record in raw.split(b"\x00"):
            if not record:
                continue
            head, _, path = record.partition(b"\t")
            mode, kind, oid, size = head.decode().split(maxsplit=3)
            out.append((_git_path(path), mode, oid,
                        0 if size.strip() == "-" else int(size)))
            del kind
        return sorted(out)

    def registered_submodules(self, tree: list) -> Registrations | str:
        """What the `.gitmodules` at the pinned commit registers, each path
        WITH a url; or, as a string, what git says when it cannot read that
        file for its submodules.

        A REGISTRATION is a `submodule.<name>.path` and a non-empty
        `submodule.<name>.url` under the same name: the path is what git
        looks a gitlink up by, and the url is what it must then find to clone
        it. `tree` is `self.tree()`, which says whether there is a file to
        read at all; with none, nothing is registered.

        READ AS THE LEG WILL READ IT. In the assembly, git reads the
        CHECKED-OUT file, follows no `[include]` in it, and filters what it
        parses (`_registrations` mirrors those filters). So the blob is piped
        into `git config --no-includes --file - --list`, and NOT read with
        `--blob`, which differs twice: it reads bytes through a `char`,
        signed on x86, so a 0xFF byte -- in a Latin-1 comment, say -- reads
        as the end of the file, hiding a registration or an override after
        it (git 2.43 on x86_64, `--list` exits 0); and it follows
        `[include]`, so a relative one is fatal (`relative config includes
        must come from files`) and an absolute one reads a file on this
        machine. `--no-includes` because `--file -` follows includes by
        default, as `--file <path>` does not.

        `--list`, NOT `--get-regexp`: the second exits 1 both when no key
        matches and on a `bad config line`, so a file git cannot read would
        come back as one that registers nothing. `--list` exits 0 on any file
        it parsed, empty or not, and 128 on one it could not, and git's words
        come back instead of paths: a read that failed is not an answer
        (#166), and the person told so is told why. git calls the file it
        read through `--file -` "standard input"; they are told `.gitmodules`.

        A KEY WITH NO VALUE -- one SUBMODULE_VALUED_KEY_RE names, with
        nothing after it -- is fatal to git's submodule reader alone, and git
        runs that reader only for a gitlink: the assembly's clone for one in
        the tree it checks out, and `execute`'s extraction for one that ANY
        commit `git fast-export` diffs adds, removes or moves, where the tip
        `.gitmodules` is the file it reads (#195). So in a tree that holds
        none, the file is read that way only when the history of the
        source's branches and tags holds one (`_exported_gitlink`), and then
        the answer is git's words, an `InTheHistory` naming where: on main,
        `check` passed such a file as registering nothing and `execute` died
        in `git fast-export` with `missing value for 'submodule.b.path'`,
        after both leg repositories were made. Where the history holds none
        either, nothing ever reads the file that way, and it registers
        nothing (#166's S3). A VALUE git's submodule reader refuses --
        `update = bogus`, `shallow = maybe`, `_refused_value` -- is read the
        same way, wherever the gitlink is (#215): `git config --list` exits
        0 on it, and on main `check` passed it while `execute` died in `git
        fast-export` after both leg repositories were made. A line git
        cannot parse at all is another matter: every reader dies on it, and
        the history says only which reader dies first.
        """
        if not any(path == GITMODULES for path, _, _, _ in tree):
            return Registrations()
        blob = subprocess.run(
            ["git", GIT_CAT_FILE, "blob", f"{self.commit}:{GITMODULES}"],
            cwd=self.path, capture_output=True, check=False)
        # A `.gitmodules` that is no blob -- a gitlink, say -- leaves nothing
        # for `git config` to read, and what `cat-file` said is the answer.
        listed = blob if blob.returncode else subprocess.run(
            ["git", GIT_CONFIG, "-z", "--no-includes", "--file", "-",
             "--list"], cwd=self.path, input=blob.stdout, capture_output=True,
            check=False)
        if listed.returncode:
            read = _one_line(listed.stderr.decode(errors="replace")).replace(
                "standard input", GITMODULES)
        else:
            read = _registrations(listed.stdout)
        if not isinstance(read, str) or any(
                mode == GITLINK_MODE for _, mode, _, _ in tree):
            return read
        return _read_for_the_history(self, tree, read) or (
            read if listed.returncode else Registrations())

    def commit_count(self) -> int:
        return int(git_out(["rev-list", "--count", self.commit], cwd=self.path))


def _remote_repository(path: Path) -> str | None:
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=path)
    except Refusal:
        return None
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def _default_branch(path: Path) -> str:
    """The branch the adoption reads, in the order a reader would guess it."""
    for args in (["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                 ["symbolic-ref", "--short", "HEAD"]):
        try:
            name = git_out(args, cwd=path)
        except Refusal:
            continue
        if name:
            return name.split("/", 1)[1] if name.startswith("origin/") else name
    return "main"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


class Entry:
    """One row of the plan: a path, the leg proposed for it, and why."""

    def __init__(self, path: str, verdict: Verdict, files: int, size: int):
        self.path = path
        self.leg = verdict.leg
        self.rule = verdict.rule
        self.reason = verdict.reason
        self.confidence = verdict.confidence
        self.question = verdict.question
        self.files = files
        self.bytes = size

    def write(self, lines: list[str]) -> None:
        lines.append(f"  - path: {y(self.path)}")
        emit(lines, "leg", self.leg, 4)
        emit(lines, "confidence", self.confidence, 4)
        emit(lines, "rule", self.rule, 4)
        emit(lines, "reason", self.reason, 4)
        emit(lines, "files", self.files, 4)
        emit(lines, "bytes", self.bytes, 4)
        emit(lines, "review_required", self.leg is None, 4)
        if self.question:
            emit(lines, "question", self.question, 4)


def walk(policy: PathPolicy, files: list[tuple[str, int]],
         prefix: str = "") -> list[Entry]:
    """Classify a level of the tree, descending ONLY where children disagree.

    `files` are `(path relative to prefix, size)`; `prefix` is what to put back
    in front when an entry is written. One entry per top-level name is the
    goal: a reader has to read this, and 167 rows for 167 files would bury the
    four decisions that actually need a human.
    """
    here = [(p, s) for p, s in files if "/" not in p]
    groups: dict[str, list[tuple[str, int]]] = {}
    for path, size in files:
        if "/" in path:
            head, _, rest = path.partition("/")
            groups.setdefault(head, []).append((rest, size))

    entries: list[Entry] = []
    for path, size in sorted(here):
        full = prefix + path
        entries.append(Entry(full, policy.classify_file(full), 1, size))
    for name, children in sorted(groups.items()):
        directory = f"{prefix}{name}/"
        verdicts = [policy.classify_file(directory + child)
                    for child, _ in children]
        folded = policy.fold(verdicts, [c for c, _ in children])
        if folded is not None:
            entries.append(Entry(directory, folded, len(children),
                                 sum(s for _, s in children)))
        else:
            entries.extend(walk(policy, children, directory))
    return sorted(entries, key=lambda e: e.path)


def ask_about_submodules(policy: PathPolicy, entries: list[Entry],
                         tree: list) -> list[Entry]:
    """`entries`, with every entry that holds a gitlink of the source's
    ASKED the `.gitmodules` question instead of answered by its rule (#166).

    `walk` sees paths, not modes, so it classifies a gitlink as the file its
    path looks like: a submodule vendored at `.specify/vendored` or `.cursor`
    comes out `root` by the 2026-09-02 ruling, one under `docs/` comes out
    `spec`, and neither is asked. `check` refuses the first and may find the
    second split from its `.gitmodules`, and `plan` must never propose what
    `check` refuses. So each entry that covers a gitlink, WHATEVER RULE
    MATCHED IT, gets `leg: null` and the question `.gitmodules` itself is
    asked, naming the submodules it holds and the rule it is no longer
    classified by. The ruling still roots the FILES under those paths, and
    one of several submodules may be dropped on its own, so an entry holding
    more than one path NAMES THE ENTRIES THAT REPLACE IT, each submodule one
    of its own (`_own_entries`), or past SPLIT_ENTRIES_NAMED says how to
    make them: splitting it is the only edit that answers those paths
    apart, because an entry added beside it for a path it already covers is
    `plan-covered-twice`. `walk`'s folding is left alone; only the covering
    entry is replaced. A source with no gitlink, the common case, gets its
    entries back untouched.
    """
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    if not gitlinks:
        return entries
    paths = [path for path, _, _, _ in tree]
    asked = policy.classify_file(GITMODULES)
    out = []
    for entry in entries:
        held = [path for path in gitlinks if _covering([entry.path], path)]
        out.append(_asked_about(entry, held, asked,
                                _own_entries(entry.path, paths, held))
                   if held else entry)
    return out


def _own_entries(entry: str, paths: list[str], gitlinks: list[str]
                 ) -> list[str]:
    """The plan entries that replace `entry` so that each of `gitlinks` it
    covers is an entry of its own: one per child of the directory, and
    descending only into a child directory that holds one of them. An entry
    that is not a directory is already its own."""
    if not entry.endswith("/"):
        return [entry]
    out: list[str] = []
    for child in sorted({_child_of(entry, path) for path in paths
                         if path.startswith(entry)}):
        if child.endswith("/") and any(path.startswith(child)
                                       for path in gitlinks):
            out += _own_entries(child, paths, gitlinks)
        else:
            out.append(child)
    return out


def _child_of(directory: str, path: str) -> str:
    """The entry one level below `directory` that covers `path`: the file
    itself, or the directory it is in, with its slash."""
    head, slash, _ = path[len(directory):].partition("/")
    return directory + head + slash


#: How many of the entries that replace a directory entry holding a
#: submodule its question names one by one. Past it, the question says
#: which directories' paths they are and counts them, as `plan-unresolved`
#: names eight paths and counts the rest: four hundred files beside one
#: submodule would otherwise be four hundred names on one line of the plan,
#: and again in `check`'s `plan-unresolved` finding (#166's R5-2).
SPLIT_ENTRIES_NAMED = 8


def _asked_about(entry: Entry, held: list[str], asked: Verdict,
                 own: list[str]) -> Entry:
    """`entry` as `ask_about_submodules` writes it: the `.gitmodules`
    verdict, whose `leg:` is null, and its question naming `held` and, when
    it holds more than one path, the `own` entries that replace it, and
    which of those `execute` will not extract as they are named
    (`_refused_replacements`, #319). Each path is `_spelled`, because the
    question is a line of the plan, and the question is set on the entry
    as it is written: `Verdict` folds each run of spaces in a question to
    one, and a name holding two, `src/a  b.md`, was named `src/a b.md`, an
    entry that covers nothing."""
    question = (f"{asked.question} " if asked.question else "") + (
        f"This entry holds the submodule(s) {_listed(held)}: it is asked "
        f"this question, not classified by its rule `{entry.rule}`.")
    if len(own) > 1:
        question += (" Split the entry if its paths do not all belong in one "
                     f"leg: replace it with "
                     f"{_replacements(entry.path, held, own)}, each with its "
                     "own `leg:`. An entry added beside this one for a path "
                     "it covers is `plan-covered-twice`."
                     + _refused_replacements(own, held))
    out = Entry(entry.path, Verdict(None, asked.rule, asked.reason,
                                    asked.confidence), entry.files,
                entry.bytes)
    out.question = question
    return out


def _refused_replacements(own: list[str], held: list[str]) -> str:
    """What the question `_asked_about` writes says of the entries `own`
    that replace a directory entry, when `execute` will not extract one of
    them into a leg as it is named (`entry_path_problem`, #319): each such
    entry by name, with the reason, and that `root` or `drop` is its only
    answer -- `drop` for a submodule, which the assembly root never keeps.
    Past SPLIT_ENTRIES_NAMED of them the rest are counted. Empty when there
    is none, so the question is what it was.

    Under the directory entry such a name is never written on its own, and
    `check` judges nothing below it; as an entry of its own, the edit the
    question names, it is judged, and `check` refused the answer `spec` or
    `code` as `plan-unsafe-path` though this question had offered both."""
    refused = [(path, entry_path_problem(path)) for path in own]
    refused = [(path, problem) for path, problem in refused if problem]
    if not refused:
        return ""
    if len(refused) == 1:
        [(path, problem)] = refused
        answer = ("`drop` is the only answer for it: the assembly root keeps "
                  "no submodule of the source's" if path in held else
                  "`root` or `drop` is the only answer for it")
        return (f" Of those entries, `execute` will not extract "
                f"{_spelled(path)} into a leg as it is named, because "
                f"{problem}; so {answer}.")
    submodule = (", and `drop` for a submodule, which the assembly root "
                 "never keeps" if any(path in held for path, _ in refused)
                 else "")
    named = "; ".join(f"{_spelled(path)}, because {problem}"
                      for path, problem in refused[:SPLIT_ENTRIES_NAMED])
    more = len(refused) - SPLIT_ENTRIES_NAMED
    if more > 0:
        named += (f"; and {more} more, each `plan-unsafe-path` in `check` "
                  "if it is answered `spec` or `code`")
    return (" Of those entries, `execute` will not extract these into a leg "
            "as they are named, so `root` or `drop` is the only answer for "
            f"each{submodule}: {named}.")


def ask_about_refused_paths(entries: list[Entry], tree: list) -> list[Entry]:
    """`entries`, with every one `execute` will not extract into a leg as it
    is named ASKED, rather than answered `spec` or `code` (#319).

    `entry_path_problem` is the one test `check` and `execute` ask of an
    entry's path (#196), and `plan` asked it nothing: a source holding
    `-notes.md`, `notes\\t.md`, `a\\rb.md`, `a\\nb.md`, `a==>b.md` or a name
    that is not UTF-8 was planned `leg: spec`, `review_required: false`, no
    question, and the first anybody heard of it was `check`'s
    `plan-unsafe-path`: an answer `plan` chose for the person, refused one
    command later. `Icon\\r`, which no rule places, was asked the policy's
    question, which offers `spec` and `code` as well.

    So each entry the test refuses that is not answered `root` -- the rules
    put it in a leg, or ask -- gets `leg: null` and a question that says why
    `execute` will not extract it, in the test's words, and that `root` or
    `drop` is the only answer for it, as UNSAFE_PATH_REMEDIATION says after
    `check`'s finding; renaming it in the source is the way into a leg. An
    entry that holds a submodule is told `drop`: the assembly root keeps no
    submodule of the source's (`plan-submodule-root`). A question the entry
    carries already -- the policy's, or `.gitmodules`' -- is kept, and this
    one follows it. An entry answered `root` is left as it is: it is never
    extracted (NOT_EXTRACTED), and `check` and `execute` take it. The rule
    and the reason stay the classifier's, so the plan still says where the
    rules would have put it.

    `check` and `execute` are not changed: they ask the same test of
    whatever the person answers, as they always did. The question is set on
    the entry as it is written, as `_asked_about` sets one, so no run of
    spaces in a name it spells is folded.
    """
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    out = []
    for entry in entries:
        problem = (None if entry.leg in NOT_EXTRACTED
                   else entry_path_problem(entry.path))
        if problem is None:
            out.append(entry)
            continue
        held = any(_covering([entry.path], path) for path in gitlinks)
        out.append(_refused_as_named(entry, problem, held))
    return out


def _refused_as_named(entry: Entry, problem: str, held: bool) -> Entry:
    """`entry` as `ask_about_refused_paths` writes it: `leg: null`, its rule
    and reason, and the question, after any it carries already."""
    if entry.leg is not None:
        lead = (f"The rules put this path in the {entry.leg} leg (rule "
                f"`{entry.rule}`), but `execute` will not extract it")
    else:
        lead = (f"{entry.question} But " if entry.question else "") \
            + "`execute` will not extract this path"
    answer = ("`drop` is the only answer `execute` takes for this entry as it "
              "stands: `root` would keep a submodule in the assembly root, "
              "which keeps none of the source's" if held else
              "`root` or `drop` is the only answer `execute` takes for it")
    out = Entry(entry.path, Verdict(None, entry.rule, entry.reason,
                                    entry.confidence), entry.files,
                entry.bytes)
    out.question = (f"{lead} into a leg as it is named, because {problem}. "
                    f"So {answer}. To put it in a leg, rename it in the "
                    "source, commit, and re-run `plan`.")
    return out


def _replacements(entry: str, held: list[str], own: list[str]) -> str:
    """The entries `own` that replace the directory entry `entry`, as its
    question names them: each one while there are few, and past
    SPLIT_ENTRIES_NAMED the directories they are the paths of -- `entry`
    and each one `_own_entries` opened on the way to a submodule in `held`,
    which are no entries themselves -- and how many there are."""
    if len(own) <= SPLIT_ENTRIES_NAMED:
        return f"an entry for each of {_listed(own)}"
    opened = sorted({path[:end + 1] for path in held
                     for end in range(len(entry) - 1, len(path))
                     if path[end] == "/"})
    where = (_listed(opened) if len(opened) == 1 else
             f"one of {_listed(opened)}, other than those directories")
    return f"an entry for each path directly in {where}, {len(own)} in all"


def _listed(paths: list[str]) -> str:
    return ", ".join(_spelled(path) for path in paths)


def _spelled(path: str) -> str:
    """`path` between backticks, as a question or a finding names it.

    The plan is UTF-8 text, one value to a line, and a path is bytes:
    `Source.tree` keeps one that is not UTF-8 as a surrogate, which no UTF-8
    file can hold -- written raw, it raised mid-write and left `--out` empty
    (#166's NEW-2) -- and a name may hold a newline, which would end the
    line. So a character that is not printable is spelled with a backslash,
    `\\xe9` for the byte 0xE9 and `\\n` for a newline, and so are a
    backslash and a backtick, so that the spelling reads one way only and
    the backticks still delimit it. The plan's own `path:` spells that byte
    `\\udce9`, not `\\xe9` (`repo_shape.double_quoted`), because in YAML
    `\\xe9` is the character U+00E9, which is another name: a question or a
    report that says `caf\\xe9` is the entry `"caf\\udce9"` in the plan.
    """
    return "`" + "".join(map(_spelled_character, path)) + "`"


def _shown(path: str) -> str:
    """`path` in `plan`'s and `check`'s terminal report: as it is, unless a
    character in it is not printable, and then `_spelled`. The plan file
    holds such a name escaped (`repo_shape.double_quoted`); printed raw, a
    carriage return sends the cursor back over the row and hides the name, a
    line break splits the row, and a byte that is not UTF-8 (a surrogate
    here) raised `UnicodeEncodeError` on a terminal strict about its
    encoding -- macOS, a UTF-8 Linux locale, a Windows code page -- after the
    plan was written (#199). The same holds for the source directory a local
    `--source` names, which the report prints too. Every other name prints
    exactly as it did."""
    return path if path.isprintable() else _spelled(path)


def _spelled_character(char: str) -> str:
    if char in "\\`":
        return "\\" + char
    if char.isprintable():
        return char
    if "\udc80" <= char <= "\udcff":
        return f"\\x{ord(char) - 0xDC00:02x}"
    return ascii(char)[1:-1]


def cross_leg_references(source: "Source", entries: list["Entry"],
                        spec_path: str, code_path: str) -> list[str]:
    """Files that will move to the CODE leg and name a path in the SPEC leg.

    Found by asking git, not by guessing: `git grep -l` over the source commit,
    restricted to the paths the plan sends to the code leg, for the name of
    each directory the plan sends to the spec leg. That is how a follow-up ends
    up saying `scripts/validate.py` instead of "something may read contracts".

    This is the 2026-09-02 ruling made operational: `contracts/*.yaml` go to
    the spec leg, and the code that reads them reads ACROSS the assembly root
    mount. The read is one relative path from the code leg — but only once
    somebody edits it, so the plan says which file and the human decides when.

    EVERY NAME IS A NAME (#216). Both inputs are source paths, and git reads
    each as something else unless told not to. A spec directory passed bare
    sits where git reads OPTIONS: `-notes/` was a usage error (exit 129, no
    follow-up), and `-O<cmd>/` was `--open-files-in-pager`, which git runs
    through a shell -- argv and `shell=False` stop Python running a shell,
    not git -- so `-e` makes it the pattern. The code entries are pathspecs:
    `:cache` read as the pathspec `cache` and `*` matched files in the spec
    leg, so `--literal-pathspecs`. `-l` C-quoted a name outside printable
    ASCII (`"src/\\303\\234bersicht.py"`), so `-z`, read as `Source.tree`
    reads names, and each hit is spelled as a question spells a path, with
    no backticks: one line of UTF-8 whatever its bytes; so is the spec
    directory's own name. `--no-color`, because `color.grep=always` wraps
    each name in escapes. A grep that FAILS is said, never read as "no file
    names it", and so is one that cannot be asked: `-F` splits a pattern at
    a line feed.
    """
    code_paths = [e.path.rstrip("/") for e in entries if e.leg == "code"]
    spec_dirs = [e.path for e in entries
                 if e.leg == "spec" and e.path.endswith("/")]
    if not code_paths or not spec_dirs:
        return []
    out: list[str] = []
    for spec_dir in spec_dirs:
        named = "".join(map(_spelled_character, spec_dir))
        if "\n" in spec_dir:
            # `-F` reads a pattern holding a line feed as one pattern per
            # line: `a<LF>b/` was searched as `a` OR `b/` and named files
            # that never mention it, the way `*` did.
            out.append(_search_by_hand(
                named, "`git grep` reads each line of a pattern as a pattern "
                "of its own, so it cannot search for this name"))
            continue
        proc = subprocess.run(
            ["git", "--literal-pathspecs", "grep", "--no-color", "-z", "-l",
             "-I", "-F", "-e", spec_dir, source.commit, "--", *code_paths],
            cwd=str(source.path), capture_output=True, check=False)
        if proc.returncode not in (0, 1):
            why = _one_line(proc.stderr.decode("utf-8", "replace"))[:300]
            out.append(_search_by_hand(
                named, f"`git grep` exited {proc.returncode}: {why}"))
            continue
        # `<commit>:<path>` per record; the commit is hex, so the first `:`
        # ends it and the rest is the path, raw.
        hits = [_git_path(record.partition(b":")[2])
                for record in proc.stdout.split(b"\x00") if b":" in record]
        # Fixtures last. A test fixture that mentions `contracts/` is usually
        # quoting a path rather than reading one, and burying the harness that
        # DOES read it under twenty of them is how a follow-up list stops
        # being read at all.
        hits.sort(key=lambda h: ("fixture" in h or h.startswith("tests/"), h))
        for hit in hits[:8]:
            shown = "".join(map(_spelled_character, hit))
            out.append(
                f"{code_path}/{shown} names `{named}`, which moves to the "
                f"spec leg: it must read across the assembly root — "
                f"`../{spec_path}/{named}` relative to `{code_path}/` — or "
                "take the path from the environment")
        if len(hits) > 8:
            out.append(f"… and {len(hits) - 8} more file(s) under the code leg "
                       f"naming `{named}`")
    return out


def _search_by_hand(named: str, why: str) -> str:
    """The follow-up for a spec directory git did not search for: the
    reason, and what to look for instead."""
    return (f"git could not search the files moving to the code leg for "
            f"`{named}` ({why}); find the ones that name it by hand: each "
            f"must read across the assembly root once `{named}` moves to the "
            "spec leg")


def follow_ups_for(source: "Source", entries: list["Entry"], names: dict,
                   spec_path: str, code_path: str,
                   collisions: list[str]) -> list[str]:
    """The code changes an in-place split MAKES NECESSARY, named in the plan.

    A split that moved `contracts/` into the spec leg and said nothing about
    the harness that reads it would have handed somebody a red build and no
    explanation.
    """
    out = cross_leg_references(source, entries, spec_path, code_path)
    if any(e.leg == "spec" and (e.path == "contracts/"
                                or e.path.startswith("contracts/"))
           for e in entries):
        out.append(
            f"the root Makefile wires `CONTRACTS_DIR ?= $(CURDIR)/{spec_path}/"
            "contracts` and exports it, so the code leg's tooling takes the "
            "path from the environment instead of assuming it sits beside it")
    if any(e.path in ("CODEOWNERS", ".github/CODEOWNERS") for e in entries):
        out.append(
            "CODEOWNERS in the assembly root now names paths that live in the "
            "legs; re-scope it here and add one to each leg, since a code "
            "owner rule cannot cross a repository boundary")
    out.extend(collisions)
    out.append(
        "open the split as a pull request against the source's default "
        f"branch; the legs {names['spec']} and {names['code']} are seeded "
        "before it, so review the root's diff and the two new repositories "
        "together")
    return out


def summary_of(entries: list[Entry]) -> dict[str, dict[str, float]]:
    total_files = sum(e.files for e in entries) or 1
    total_bytes = sum(e.bytes for e in entries) or 1
    out: dict[str, dict[str, float]] = {}
    for leg in ("spec", "code", "root", "drop", "unresolved"):
        rows = [e for e in entries
                if (e.leg or "unresolved") == leg]
        if not rows and leg in ("drop",):
            continue
        files = sum(e.files for e in rows)
        size = sum(e.bytes for e in rows)
        out[leg] = {
            "files": files, "bytes": size,
            "file_share": round(files / total_files, 4),
            "byte_share": round(size / total_bytes, 4),
        }
    return out


def seeded_legs(assigned: dict) -> list[str]:
    """The legs no path is assigned to, in the order the tool reports them.

    ONE DEFINITION, consulted by `plan`, `check` and `execute`, because three
    answers to "is this leg empty?" is how the plan starts describing a split
    the tool does not perform. `assigned` maps a leg to the paths the entries
    give it; a leg with none is seeded.
    """
    return [role for role in EXTRACTED_LEGS if not assigned.get(role)]


def assigned_paths(entries) -> dict[str, list[str]]:
    """`{leg: [path, ...]}` from plan `Entry` objects OR from loaded rows."""
    out: dict[str, list[str]] = {leg: [] for leg in LEG_VALUES}
    for entry in entries:
        if isinstance(entry, dict):
            leg, path = entry.get("leg"), entry.get("path")
        else:
            leg, path = entry.leg, entry.path
        if leg is not None and str(leg) in out:
            out[str(leg)].append(str(path))
    return out


def render_plan(args, source: Source, entries: list[Entry], names: dict,
                pins: list[str], follow_ups: list[str],
                seeded: list[str]) -> str:
    lines = [
        "schema_version: 1",
        f"kind: {PLAN_KIND}",
        "",
        "# Written by `adopt-project.py plan`. IT IS MEANT TO BE EDITED.",
        "# Every entry with `review_required: true` carries a `question:`; a",
        "# human or an AI answers it by setting `leg:` to spec, code, root or",
        "# drop and adding one line of `resolution:` beside it. `check` then",
        "# has to pass, and `execute` REFUSES while any leg is still null.",
        "",
        f"generated_on: {_dt.date.today().isoformat()}",
        f"tool: {SHAPE_REPOSITORY} adopt-project.py",
        "",
        "source:",
    ]
    emit(lines, "repository", source.repository, 2)
    emit(lines, "local_path", str(source.path), 2)
    emit(lines, "default_branch", source.branch, 2)
    emit(lines, "commit", source.commit, 2)
    emit(lines, "files", sum(e.files for e in entries), 2)
    emit(lines, "bytes", sum(e.bytes for e in entries), 2)
    emit(lines, "commits", source.commit_count(), 2)
    lines += ["", "# The adopted repository KEEPS its name, its identity and",
              "# its history and becomes the assembly root. `new-root` — a new",
              "# root with the source reduced to one leg — is not implemented",
              "# in v0.2; the field records which posture this plan took.",
              "mode: in-place", ""]
    emit(lines, "project", args.project)
    emit(lines, "org", args.org)
    emit(lines, "id", args.id)
    emit(lines, "visibility", args.visibility)
    emit(lines, "tracking_branch", args.tracking_branch)
    emit(lines, "adopt_branch", ADOPT_BRANCH)
    emit(lines, "elected_by", args.elected_by)
    emit(lines, "elected_on", args.elected_on)
    emit(lines, "reference", args.reference)
    lines.append("")
    lines.append("legs:")
    emit(lines, "assembly", names["assembly"], 2)
    emit(lines, "spec", names["spec"], 2)
    emit(lines, "code", names["code"], 2)
    emit(lines, "spec_path", args.spec_path, 2)
    emit(lines, "code_path", args.code_path, 2)
    lines += ["",
              "# Neutral products this project declares a pin on. A",
              "# `<Domainx><Product>` assembly root is a DESCENDANT only when",
              "# its `open<Product>` is listed here (2026-09-02).",
              "pins: [" + ", ".join(pins) + "]", ""]

    lines += [
        "# A leg that NO entry below assigns a path to is SEEDED from the",
        "# shape's own leg template as one initial commit, instead of being",
        "# extracted: `git filter-repo` over an empty path list yields an",
        "# empty HISTORY, which is not an empty repository. The split still",
        "# mounts it. This block RECORDS what the entries said when the plan",
        "# was written; `check` and `execute` re-derive it from the entries,",
        "# which are edited afterwards, and the entries always win.",
        "seeding:",
    ]
    for role in EXTRACTED_LEGS:
        lines.append(f"  {role}:")
        emit(lines, "seeded_from_template", role in seeded, 4)
        if role in seeded:
            emit(lines, "template", SEED_TEMPLATE[role], 4)
            emit(lines, "reason",
                 f"no entry assigns a path to the {role} leg", 4)
    lines += [
        "",
        "# Seeding a leg is EXPLICIT HUMAN INTENT, so `execute` refuses to do",
        "# it unless the leg is named here (or on its own command line) with",
        "# `--allow-empty-leg <leg>`. A repository that turns out to have no",
        "# code is a fact worth confirming; a plan that lost every code path",
        "# to a bad edit looks exactly the same from here.",
        "allow_empty_legs: ["
        + ", ".join(sorted(getattr(args, "allow_empty_leg", None) or []))
        + "]",
        "", "paths:"]
    for entry in entries:
        entry.write(lines)
    lines += ["", "follow_ups:"]
    for item in follow_ups:
        lines.append(f"  - {y(item)}")
    lines += ["", "summary:"]
    for leg, row in summary_of(entries).items():
        lines.append(f"  {leg}:")
        for key, value in row.items():
            emit(lines, key, value, 4)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reading a leg's mount path out of the plan
# ---------------------------------------------------------------------------
#
# The rule itself -- what a canonical, mountable leg path is, the sentence a
# refusal says and the spelling it offers -- is `shape_materialize`'s, because
# `scaffold-project.py` asks the same question (#179) and one definition is how
# the two tools keep refusing the same values. What is adopt's own is where
# the value comes FROM: the plan's `legs:` block.


def _plan_leg_path(plan: Plan, role: str):
    """What the plan carries for `role`'s mount path.

    A key the plan does not carry is the default, the role's own name, as
    `execute` has always read it. An EXPLICIT empty value is not a missing
    one: it comes back as it stands and is refused, where it used to be read
    quietly as the default -- a value nobody chose.

    `legs:` is read only when it is a mapping. The doctor's PLACEMENT plan
    (`shape-doctor.py --placement-plan`) writes `legs:` as a LIST of the
    mounted legs it audited and is handed to `Plan` and `_leg_findings` by
    `tests/test_shape_doctor.py`; a list carries no `spec_path`, and `.get` on
    it is an `AttributeError`, not an answer. For anything that is not a
    mapping nothing is read, so the role's own name comes back, as it does for
    a key the plan does not carry.
    """
    legs = plan.legs
    value = legs.get(f"{role}_path") if isinstance(legs, dict) else None
    return role if value is None else value


def _plan_leg_paths(plan: Plan) -> tuple[tuple, tuple]:
    """The two `(what, value)` pairs `leg_path_problems` takes, read out of the
    plan: the ONE place that names them `legs.spec_path` and `legs.code_path`,
    so `check` and `execute` cannot name them two ways."""
    return (("legs.spec_path", _plan_leg_path(plan, "spec")),
            ("legs.code_path", _plan_leg_path(plan, "code")))


# ---------------------------------------------------------------------------
# A leg's mount path overlaps nothing the assembly root holds (#172)
# ---------------------------------------------------------------------------
#
# `--spec-path contracts` is canonical, so #169 passed it and `check` said
# `plan ok`. `execute` then made and pushed both legs, mounted one at
# `contracts`, wrote the shape's `contracts/spec-pin.yaml` INTO the mounted
# leg, and died staging the split: `Pathspec 'contracts/spec-pin.yaml' is in
# submodule 'contracts'`. `--code-path scripts`, `.github` and `shape` died
# the same way. `--code-path project.yaml` was worse: the shape's manifest
# went beside the mount as `shape/project.yaml`, "the source already has
# project.yaml" (it had not), the run said `adoption verified`, and the
# doctor calls the assembly it made NOT A SHAPE ROOT. A mount at a path the
# PLAN keeps in the root (`--spec-path src`, `src/` kept) died at `git
# submodule add`, also after both legs were pushed.
#
# So a leg's mount path is refused when it EQUALS, CONTAINS or LIES INSIDE
#
#   * a path the shape writes into the assembly root: `assembly_root_paths`,
#     read from the materializer's own lists, and `COLLISION_DIR`, where
#     `execute` writes the shape's copy of a file the root already holds; or
#   * a SOURCE PATH the plan keeps in the root, a path of the source tree a
#     `leg: root` entry covers. A mount inside a kept DIRECTORY that holds
#     nothing at the mount (`docs/spec`, with `docs/` kept and no `docs/spec`
#     in the source) overlaps no source path. It mounts, verifies and
#     bootstraps on `main`, and it is not refused here.
#
# Compared WITHOUT REGARD TO CASE, as #169 compares the two legs: a macOS or
# Windows disk keeps `Scripts` and `scripts` as one directory.
#
# `plan` refuses the first half, which it knows before a plan exists. The
# second half is a question about the plan's answers, which are edited after
# `plan` writes them, so `check` reports both halves as
# `plan-leg-path-collides` and `execute` refuses them with every other
# finding of `check`'s, before any leg exists (#168). `plan` NOTES the second
# half for the `leg: root` answers it wrote itself, and refuses nothing for
# it: those answers are the person's to change.

# The question about `assembly_root_paths` -- `path_overlap`,
# `first_and_more`, `shape_path_collisions` and the phrases they share --
# moved to `scripts/shape_materialize.py` for #197, because
# `scaffold-project.py` asks it of its own leg paths. `_shape_collisions`
# below asks it with this tool's `COLLISION_DIR` and adds the `shape/` half,
# and `leg_path_collisions` adds the root-kept half: only an adoption has
# either.

#: Why a mount at or under `COLLISION_DIR` is refused where no copy would land
#: there (#172's review, P3-3): the directory is the shape's, whatever this
#: source needs today, so whether a path there collides never depends on
#: which of the root's files the source happens to hold.
SHAPE_DIR_RESERVED = (f"`{COLLISION_DIR}/` is reserved for the shape's own "
                      "copies of files the root already holds")

LEG_COLLISION_REMEDIATION = (
    "Remediation: nothing here picks a path for you, so pass another one "
    "yourself. A leg path neither is, holds nor lies inside, whatever the "
    "case, a path the shape writes into the assembly root ("
    + ", ".join(f"`{path}`" for path in assembly_root_paths())
    + f") or `{COLLISION_DIR}`. {SHAPE_DIR_RESERVED}, so a leg path there is "
    "refused even where this source needs no copy. The defaults `spec` and "
    "`code` pass. `check` then asks the same of every source path the plan "
    "keeps in the root."
)


def _shape_collisions(what: str, value: str) -> list[str]:
    """Where the mount path `value` overlaps what the shape writes: the
    paths of `assembly_root_paths`, asked through the definition this tool
    shares with `scaffold-project.py` (#197), then this tool's own
    `COLLISION_DIR`, which only an adoption writes into."""
    out = shape_path_collisions(what, value, COLLISION_DIR)
    beside = _overlap(value, COLLISION_DIR)
    if beside:
        relation, aside = beside
        example = assembly_root_paths()[0]
        out.append(
            f"{what} {value!r} {relation} `{COLLISION_DIR}`{aside}. `execute` "
            f"writes there the shape's copy of each of its files the assembly "
            f"root already holds (`{example}` as "
            f"`{COLLISION_DIR}/{example}`), and {SHAPE_DIR_RESERVED}, so no "
            f"leg is mounted at or under it, even where this source needs no "
            f"copy: {MOVE_THE_LEG}.")
    return out


def _kind_of(mode: str) -> str:
    """What a source tree entry of `mode` is, in a reader's words: a file, a
    symlink, or else a submodule, the only other entry a recursive `ls-tree`
    lists (mode 160000, a gitlink)."""
    if mode in FILE_MODES:
        return "the file"
    return "the symlink" if mode == SYMLINK_MODE else "the submodule"


def _kept_collisions(what: str, value: str, kept: list) -> list[str]:
    """Where the mount path `value` overlaps a source path the plan keeps in
    the root: one sentence per `leg: root` entry, naming its first such path
    and counting the rest."""
    hits: dict[str, list[tuple[str, str]]] = {}
    for path, mode, entry in kept:
        if _overlap(value, path):
            hits.setdefault(entry, []).append((path, mode))
    out: list[str] = []
    for entry, found in hits.items():
        path, mode = found[0]
        relation, aside = _overlap(value, path)
        named = _first_and_more([p for p, _ in found], _spelled)
        them = "them" if len(found) > 1 else "it"
        under = ("" if entry == path else
                 f" under the entry {_spelled(entry)}")
        out.append(
            f"{what} {value!r} {relation} {_kind_of(mode)} {named}{aside}. "
            f"The plan keeps {them} in the assembly root{under}, and Git "
            "cannot mount a leg at a path the root's own tree holds, or "
            "beyond a file, symlink or submodule it holds on the way there: "
            f"{MOVE_THE_LEG}, or send {_spelled(entry)} to a leg or `drop` "
            "it.")
    return out


def leg_path_collisions(legs: tuple, kept=()) -> list[str]:
    """Everything each leg's mount path overlaps in the assembly root, as
    sentences; `[]` when nothing.

    `legs` is the two `(what, value)` pairs `leg_path_problems` takes, each
    already a canonical path: an overlap is a statement about two paths. `kept`
    is `(path, mode, entry)` for each source path the plan keeps in the root
    (`_kept_in_root`); with none, only the shape's own paths are asked about,
    which is all `plan` knows.
    """
    out: list[str] = []
    for what, value in legs:
        out += _shape_collisions(what, value)
        out += _kept_collisions(what, value, kept)
    return out


def _kept_in_root(entries: list, tree) -> list[tuple[str, str, str]]:
    """`(path, mode, entry)` for each path of `tree` (`Source.tree()`'s rows)
    that a `leg: root` entry of the plan covers, with that entry's path."""
    roots = assigned_paths(entries)["root"]
    kept = []
    for path, mode, _, _ in tree:
        covering = _covering(roots, path)
        if covering:
            kept.append((path, mode, covering[0]))
    return kept


#: `check`'s finding for a collision, named once: `plan`'s note says which
#: finding it foretells.
LEG_COLLIDES = "plan-leg-path-collides"


def _leg_collision_findings(plan: Plan, tree) -> list[str]:
    """`leg_path_collisions` over the plan's two mount paths, as `check`
    prints them. Asked only of a plan whose mount paths are canonical."""
    return [f"FINDING {LEG_COLLIDES}: {collision}"
            for collision in leg_path_collisions(
                _plan_leg_paths(plan), _kept_in_root(plan.entries, tree))]


def _flag_leg_paths(args) -> tuple[tuple, tuple]:
    """The two `(what, value)` pairs `leg_path_problems` takes, read off
    `plan`'s command line: the one place they are named `--spec-path` and
    `--code-path` beside their values, as `_plan_leg_paths` names the
    plan's."""
    return (("--spec-path", args.spec_path), ("--code-path", args.code_path))


def _kept_collision_notes(args, entries: list, tree: list) -> list[str]:
    """What `plan` says when a leg path overlaps a source path that `plan`
    ITSELF keeps in the root (#172's review, P3-2): one NOTE per collision,
    in the words `check` will use, and a line saying what follows.

    `plan` refuses only the shape's half: the plan's answers are edited
    after it writes them, so a path the plan keeps is `check`'s to find. But
    an answer `plan` wrote itself is one it already holds -- `--spec-path
    .specify` beside the `.specify/` the rules keep in the root -- and a plan
    that exits 0 only for `check` to reject its own default tells the person
    nothing until the next command. Nothing is refused: the entry's answer is
    theirs to change, and then nothing collides. `entries` are the ones the
    plan file carries, so an entry asked about again for a submodule it holds
    (`leg: null`) keeps nothing in the root and is not noted.
    """
    kept = _kept_in_root(entries, tree)
    notes: list[str] = []
    for what, value in _flag_leg_paths(args):
        for collision in _kept_collisions(what, value, kept):
            notes += [f"\nNOTE {collision}",
                      f"     `check` reports this as `{LEG_COLLIDES}` while "
                      "the leg path and that `leg: root` both stand; `plan` "
                      "refuses nothing for it, because the answer is yours "
                      "to change."]
    return notes


def _checked_plan_inputs(args, source: Source,
                         naming: NamingPolicy) -> tuple[dict, list]:
    """Every value the plan will RECORD, defaulted and checked before one of
    them is written. Returns `(names, pins)`.

    Split out of `cmd_plan` for #138, and the order inside it is the order the
    refusals came in: a run that got as far as naming the three legs before it
    refused an unparseable `--elected-on` would send a reader looking in the
    wrong place for the line that was wrong.
    """
    args.project = checked_value("--project", args.project)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    # The ONE question first -- spelling, Git's and Windows's names, then the
    # alphabet `checked_value` allows -- so `spec/` is refused here with the
    # spelling to retype, before a plan that `check` and `execute` would have
    # to refuse again is ever written. `checked_value` still runs after it: it
    # is the gate that hands back the text.
    spec, code = legs = _flag_leg_paths(args)
    _refuse_bad_leg_paths("adopt-bad-leg-path", *legs)
    # Then the paths the shape writes, which are known before any plan is
    # (#172). A path the plan keeps in the root is `check`'s to find: the
    # plan's answers are edited after this writes them. `plan` only notes
    # the ones it wrote itself (`_kept_collision_notes`).
    collisions = leg_path_collisions(legs)
    if collisions:
        raise Refusal("adopt-leg-path-collides", " ".join(collisions),
                      LEG_COLLISION_REMEDIATION)
    args.spec_path = checked_value(*spec)
    args.code_path = checked_value(*code)
    args.id = args.id or args.project.lower()
    if not PROJECT_ID_RE.match(args.id):
        raise Refusal("adopt-bad-id",
                      f"--id {args.id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    args.org = checked_value(
        "--org", args.org or (source.repository or "/").split("/")[0] or "-")
    if not args.org:
        raise Refusal(
            "adopt-no-org", "the source has no `origin` to read an "
            "organisation from", "Remediation: pass --org <org>.")
    args.elected_on = args.elected_on or _dt.date.today().isoformat()
    # Read before the plan is written, whether or not it is what chooses the
    # reference: a date the tools cannot parse would reach `execute` as a
    # manifest field instead of as a question.
    election_date(args.elected_on)
    args.reference = args.reference or default_reference(args.elected_on)
    # A value `plan` filled in by itself is named by where it came from, as
    # #181 names one, and not as a flag the person never passed.
    elector = ("--elected-by" if args.elected_by else
               "--elected-by (not given, so `git config user.name`)")
    args.elected_by = args.elected_by or _elector()
    # Before the plan is written, in the words `check` would use (#255): a
    # value `execute` writes into a file must be text one can hold. The
    # date has had its answer above, `election_date`.
    unwritable = unwritable_values(
        ((elector, args.elected_by, ROOT_MANIFEST_AND_README),
         ("--reference", args.reference, ROOT_MANIFEST_AND_README)))
    if unwritable:
        raise Refusal("adopt-unwritable-value",
                      " ".join(f"{problem}." for problem in unwritable),
                      "Remediation: no plan was written. Pass each value "
                      "named again, retyped; when `--elected-by` is not "
                      "given, `plan` reads `git config user.name`, so pass "
                      "the flag or correct that. " + WRITTEN_AS_TEXT)
    names = _names(args.project)
    pins = [_checked_pin_name(p) for p in (args.pin or []) if p.strip()]
    _check_names(naming, names, set(pins))
    return names, pins


def _print_triad_advisory(path: Path, commit: str | None = None) -> None:
    """The Triad advisory, once, about the repository this run reads.

    RULED BY BRETT HEAP ON 2026-10-06 ("ratify 1249 as recommended",
    openxFactory `prefer-triad-project-shape`): the Triad is the preferred
    project shape, it stays elective and confers nothing, and this tool's
    `plan` and `check` say so beside what they already print. THIS TOOL IS
    THE CONVERSION, so it names the preference rather than sending anybody to
    itself, and says what it does about it: nothing until `execute`, on a
    person's word for this project. `scripts/shape_advisory.py` decides where
    it is silent -- an elected Triad, a family holder, a `<user>-wip`
    workspace, a project that recorded staying single -- and a leg clone gets
    the existing instruction to work from its assembly root instead.

    PRINTED, NEVER WRITTEN. Nothing goes into the plan file, the split commit
    or the manifest on its account, and no exit code changes: the advisory is
    a sentence said to a person and not a fact about their project.

    ABOUT THE COMMIT BEING PLANNED. `commit` is the one this plan is written
    against, and the record, the manifests and a leg's `AGENTS.md` are read
    out of it rather than out of the working tree: a `single-repository.yaml`
    that exists only on a feature branch, or only uncommitted, is not in the
    repository being split and silences nothing about it.

    AND IT CANNOT FAIL THE RUN. Every line is flattened to ASCII first, as
    `shape-doctor.py` flattens its rows -- a record's `kind:` is a person's
    text, and a console that cannot encode it would otherwise raise in the
    middle of `plan`, after the plan file is already written -- and anything
    left is swallowed: a run that lost the advisory has lost one optional
    sentence, and one that crashed on it would have changed an exit status,
    which the ratified rule forbids.
    """
    try:
        reading = shape_advisory.read(path, commit=commit)
        if reading.state == shape_advisory.LEG_CLONE:
            lines = [f"NOTE {shape_advisory.leg_instruction(reading.leg)}"]
        elif reading.advise:
            first, second = shape_advisory.adopt_lines()
            lines = [f"triad      {first}", f"           {second}"]
            lines += [f"NOTE {line}" for line in
                      shape_advisory.record_report(reading.record_problems)]
        else:
            return
        print("\n".join(shape_advisory.printable(line) for line in lines))
    except Exception:  # noqa: BLE001 - see the docstring
        return


def _print_plan_report(args, source: Source, tree: list, entries: list,
                       follow_ups: list, seeded: list, out: Path) -> None:
    """What `plan` says to the terminal once the file is on disk.

    Split out of `cmd_plan` for #138. THE UNRESOLVED PATHS ARE LAST on
    purpose: they are the one part of this report somebody has to act on, and
    a question printed above a summary table is a question that gets scrolled
    past.
    """
    print(f"source     {source.repository or _shown(str(source.path))} @ "
          f"{source.commit[:12]} ({source.branch}), "
          f"{len(tree)} files, {source.commit_count()} commits")
    print(f"project    {args.project} ({args.id}) in {args.org}, mode in-place")
    _print_triad_advisory(source.path, source.commit)
    _print_entries(entries)
    _print_summary(entries)
    print(f"\nfollow-ups ({len(follow_ups)}):")
    for item in follow_ups:
        print(f"  - {item}")
    for line in seeding_warnings(seeded, set(args.allow_empty_leg or [])):
        print(line)
    for line in _kept_collision_notes(args, entries, tree):
        print(line)
    unresolved = [e for e in entries if e.leg is None]
    print(f"\nplan written to {out}")
    if unresolved:
        print(f"{len(unresolved)} path(s) need a human or an AI to answer a "
              "question before `execute` will run:")
        for entry in unresolved:
            print(f"  {_shown(entry.path)}\n      {entry.question}")


def cmd_plan(args) -> int:
    work_root = _work_root(args)
    source = Source.open(args.source, work_root)
    policy = PathPolicy.load(args.path_policy or PATH_POLICY)
    naming = NamingPolicy.load(NAMING_POLICY)

    names, pins = _checked_plan_inputs(args, source, naming)

    tree = source.tree()
    # WHAT THE RULES IMPLY is read from `walk`'s entries, BEFORE
    # `ask_about_submodules` asks again on the ones that hold a submodule: the
    # shape files a rooted path will collide with, the follow-ups, and the
    # legs a split would seed. Asking takes back no rule's answer for the
    # files under such an entry; read after it, a `leg: null` dropped main's
    # follow-up for a harness under `src/` that reads `contracts/`, and
    # called the code leg empty, so the plan recorded it as seeded and told
    # the person to re-run with `--allow-empty-leg code`, which it never
    # needed (#166's NEW-1). A source with no submodule plans as it did.
    #
    # A path `execute` will not extract as it is named is the other way
    # round (#319): `root` and `drop` are the only answers it takes, so the
    # path is in no leg whatever the person says, and what the rules imply
    # is read with it ASKED. A follow-up about a code path no leg will hold,
    # or naming it as a spec directory, would be about nothing, and a leg it
    # alone fed is seeded -- which the plan records, as `check` will say of
    # the plan as written. A source with no such path plans as it did.
    ruled = walk(policy, [(path, size) for path, _, _, size in tree])
    implied = ask_about_refused_paths(ruled, tree)
    materialized = _predict_collisions(implied)
    follow_ups = follow_ups_for(source, implied, names, args.spec_path,
                                args.code_path, materialized)
    seeded = seeded_legs(assigned_paths(implied))
    entries = ask_about_refused_paths(
        ask_about_submodules(policy, ruled, tree), tree)
    out = Path(args.out)
    write_lf(out, render_plan(args, source, entries, names, pins, follow_ups,
                              seeded))

    _print_plan_report(args, source, tree, entries, follow_ups, seeded, out)
    return 0


def seeding_warnings(seeded: list[str], allowed: set) -> list[str]:
    """What `plan` and `check` say about a leg that will be seeded.

    A WARNING AND NOT A FINDING. A repository with no implementation yet is a
    legitimate thing to adopt — the InkRouter services are specifications with
    no code (2026-09-04) — so `check` must be able to pass on one. What it
    must never do is let the seeding happen unremarked: the same empty leg is
    also what a plan looks like after somebody deletes the entries that fed
    it, and only a human can tell those two apart. Hence the consent flag,
    named here rather than discovered when `execute` refuses.
    """
    out: list[str] = []
    for role in seeded:
        out.append(
            f"\nWARNING the {role} leg will be SEEDED from "
            f"{SEED_TEMPLATE[role]}/, not extracted:\n"
            f"        no entry assigns a path to it, and `git filter-repo` "
            f"over an empty\n        path list yields an empty history rather "
            f"than an empty repository.\n        The leg is created, mounted "
            f"and pinned like any other; it simply\n        carries no history "
            f"from the adopted repository, because there is none.")
        if role not in allowed:
            out.append(
                f"        `execute` REFUSES until a human says so: re-run "
                f"`plan` with\n        --allow-empty-leg {role}, or pass it to "
                f"`execute` itself.")
        else:
            out.append(f"        --allow-empty-leg {role} is declared, so "
                       "`execute` will proceed.")
    return out


def _print_entries(entries: list[Entry]) -> None:
    print(f"\n{'path':<34} {'leg':<10} {'conf':<7} {'files':>6} {'rule'}")
    for entry in entries:
        print(f"{_shown(entry.path):<34} {(entry.leg or 'REVIEW'):<10} "
              f"{entry.confidence:<7} {entry.files:>6} {entry.rule}")


def _print_summary(entries: list[Entry]) -> None:
    print()
    for leg, row in summary_of(entries).items():
        print(f"{leg:<10} {int(row['files']):>4} files  "
              f"{int(row['bytes']):>9} bytes  "
              f"{row['file_share']:>6.1%} of files  "
              f"{row['byte_share']:>6.1%} of bytes")


def _predict_collisions(entries: list[Entry]) -> list[str]:
    """Which shape files will not be able to take their own names.

    Known BEFORE `execute` runs, because the plan says which paths survive in
    the root, so the follow-up is in the plan the human reads rather than in
    output they may never scroll back to.

    The WORDING comes from `shape_materialize.collision_follow_up`, the same
    function `execute` reports its actual collisions through — including the
    one collision whose answer is not "merge": an `AGENTS.md` or `CLAUDE.md`
    the source already holds needs ONE LINE ADDED, not a merge.

    The PATHS come from `assembly_root_paths`, the list #172's mount rule
    reads, so the two cannot list different files. The list this function
    kept itself lacked `contracts/shape-pin.yaml`, which `execute` also
    writes beside a copy the source keeps, and names in the split commit.
    """
    surviving = {e.path for e in entries if e.leg == "root"}
    out = []
    for path in sorted(set(assembly_root_paths())):
        if path in surviving or f"{path.split('/')[0]}/" in surviving:
            out.append(collision_follow_up(path, f"{COLLISION_DIR}/{path}"))
    return out


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class Plan:
    """A loaded `adoption-plan.yaml`, with the source it names."""

    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data
        if data.get("kind") != PLAN_KIND:
            detail = (f"{path}: kind is {data.get('kind')!r}, expected "
                      f"{PLAN_KIND!r}")
            if data.get("kind") == PLACEMENT_PLAN_KIND:
                # A REFUSAL THAT SAYS WHERE THE FILE GOES INSTEAD. This one is
                # reachable by an honest mistake -- the two files look alike,
                # because their entries ARE alike -- and "expected
                # 'adoption-plan'" alone would leave a reader holding a
                # correct file with no command to run it through.
                raise Refusal(
                    "plan-wrong-kind", detail,
                    "Remediation: this is a PLACEMENT plan, written by "
                    "`shape-doctor.py --placement-plan` for a project that is "
                    "ALREADY split; its entries name paths inside mounted "
                    "legs. This tool splits a repository that is not, so "
                    "`execute` here would be aimed at an assembly root. "
                    "Resolve every `resolution:` and hand it back to the "
                    "doctor.")
            raise Refusal("plan-wrong-kind", detail)
        if data.get("mode") != "in-place":
            raise Refusal(
                "plan-unsupported-mode",
                f"{path}: mode is {data.get('mode')!r}; v0.2 implements "
                "`in-place` only",
                "Remediation: re-run `plan`, which writes `mode: in-place`. "
                "A `new-root` mode is described in the tool's own docstring "
                "and is not implemented.")
        self.entries = [e for e in (data.get("paths") or [])
                        if isinstance(e, dict)]
        self.legs = data.get("legs") or {}
        self.pins = [str(p) for p in (data.get("pins") or []) if p]

    @classmethod
    def load(cls, path: Path) -> "Plan":
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("plan-unreadable", f"{path}: not a mapping")
        return cls(path, data)

    @property
    def source_commit(self) -> str:
        return str((self.data.get("source") or {}).get("commit") or "")

    def open_source(self, override: str | None, work_root: Path) -> Source:
        spec = override or (self.data.get("source") or {}).get("local_path") \
            or (self.data.get("source") or {}).get("repository")
        if not spec:
            raise Refusal("plan-no-source",
                          f"{self.path}: `source:` names neither a local path "
                          "nor a repository")
        return Source.open(str(spec), work_root)

    def names(self) -> dict[str, str]:
        """The three repository names the plan declares, validated as values.

        They reach `gh repo create` and a push URL, so they are checked here
        rather than trusted because they came out of a file this tool wrote:
        the file is edited between `plan` and `execute`, on purpose.
        """
        return {role: checked_value(f"legs.{role}", self.legs.get(role))
                for role in ("assembly", "spec", "code")}

    @property
    def project_id(self) -> str:
        """The lowercase machine name, RE-VALIDATED here.

        The GitHub topic is derived from it, both for the manifest's `TOPIC`
        and for `gh repo edit --add-topic`, so it is read in ONE place rather
        than spelled out at each. `plan` refuses an `--id` that is not this
        shape, but the plan is edited between `plan` and `execute` on purpose,
        so the check is repeated where the value is USED: it reaches a `gh`
        command line and a written manifest, and a topic that does not match
        `contracts/repository-naming.yaml` is one `validate-repository-naming.py`
        will refuse in the project's own gate, long after the run that set it.
        """
        project_id = str(self.get("id", self.names()["assembly"].lower()))
        if not PROJECT_ID_RE.match(project_id):
            raise Refusal(
                "plan-bad-id",
                f"{self.path}: `id:` is {project_id!r} and must match "
                f"{PROJECT_ID_RE.pattern}",
                "Remediation: fix `id:` in the plan, or re-run `plan` with an "
                "explicit lowercase --id. The GitHub topic is derived from it.")
        return project_id

    def get(self, key, default=None):
        value = self.data.get(key)
        return default if value is None else value

    def allowed_empty_legs(self) -> set[str]:
        """The legs this PLAN consents to having seeded. `execute` unions it
        with its own `--allow-empty-leg`, so consent can be given at either
        end — but it is never inferred from the entries being empty, which is
        the state the consent exists to be deliberate about."""
        return {str(role) for role in (self.data.get("allow_empty_legs") or [])
                if role}

    def seeding_record_disagreements(self, seeded: list[str]) -> list[str]:
        """Where the plan's `seeding:` record and its own entries disagree.

        A NOTE, NOT A FINDING, and the entries win. The record is written by
        `plan`; the entries are edited afterwards, and resolving an ambiguous
        path INTO the code leg is exactly the edit that makes a recorded
        `seeded_from_template: true` stale. Refusing there would punish the
        human for answering the question the plan asked them.
        """
        record = self.data.get("seeding")
        if not isinstance(record, dict):
            return []
        out: list[str] = []
        for role in EXTRACTED_LEGS:
            row = record.get(role)
            if not isinstance(row, dict) or "seeded_from_template" not in row:
                continue
            recorded = bool(row.get("seeded_from_template"))
            if recorded != (role in seeded):
                out.append(
                    f"NOTE the `seeding:` record says the {role} leg would be "
                    f"{'seeded' if recorded else 'extracted'}, but the entries "
                    f"now say {'seeded' if role in seeded else 'extracted'}. "
                    "The entries win; the record is stale because the plan was "
                    "edited after it was written, which is what a plan is for.")
        return out


def _covering(entry_paths: list[str], path: str) -> list[str]:
    """Every plan entry that covers `path` — a file entry or an ancestor."""
    return [p for p in entry_paths
            if p == path or (p.endswith("/") and path.startswith(p))]


def _coverage_findings(entry_paths: list[str], tree_paths: list[str]) -> list[str]:
    """Every source path covered EXACTLY once, and every entry covering something.

    Both halves matter and they fail differently: an uncovered path is a file
    the split would silently drop, and an entry covering nothing is a plan
    describing a tree that no longer exists.

    Every path is `_spelled`, as a question names it. Printed raw, a source
    name holding a line break, an ESC or any other character
    `str.isprintable` refuses split or overwrote the line it was on (#212).
    """
    findings: list[str] = []
    duplicates = sorted({p for p in entry_paths if entry_paths.count(p) > 1})
    for path in duplicates:
        findings.append(f"FINDING plan-duplicate-path: {_spelled(path)} "
                        f"appears {entry_paths.count(path)} times")
    uncovered, multiple = [], []
    for path in tree_paths:
        covering = _covering(entry_paths, path)
        if not covering:
            uncovered.append(path)
        elif len(covering) > 1:
            multiple.append((path, covering))
    for path in uncovered[:20]:
        findings.append(f"FINDING plan-uncovered: {_spelled(path)} is in the "
                        "source tree and in no plan entry")
    if len(uncovered) > 20:
        findings.append(f"FINDING plan-uncovered: … and {len(uncovered) - 20} "
                        "more uncovered paths")
    for path, covering in multiple[:20]:
        findings.append(f"FINDING plan-covered-twice: {_spelled(path)} is "
                        f"covered by {_listed(covering)}")
    used = {p for path in tree_paths for p in _covering(entry_paths, path)}
    for path in sorted(set(entry_paths) - used):
        findings.append(f"FINDING plan-empty-entry: {_spelled(path)} covers "
                        "nothing in the source tree at this commit")
    return findings


def _leg_findings(plan: Plan, tree: list | None) -> list[str]:
    """`leg:` is answered with one of the four words, each leg's mount path
    is canonical (#169), and neither overlaps a path the assembly root holds
    (#172); and the root keeps nothing where the shape writes (#262, #263).

    The path findings live HERE, and not in `cmd_check`, so that whatever
    reads this function reports a bad path from the one place that knows what
    a canonical one is. `tree` is the source's, as `Source.tree()` lists it:
    the paths the plan keeps in the root are read out of it.

    `tree` HAS NO DEFAULT, on purpose. With one, `()`, #166's
    `_entry_findings` called this with no tree, the merge of the two
    branches ran, and the root-kept half went quiet: a mount at a path the
    plan keeps in the root checked ok again (#172's review, P3-1). A lost
    argument is now a `TypeError`. `None` says there is NO source tree,
    which is true only of the doctor's PLACEMENT plan, whose `legs:` is a
    list with no mount path to ask about; beside a `legs:` mapping it raises
    too, rather than reading as a source that keeps nothing in the root.
    """
    findings: list[str] = []
    # Only a `legs:` MAPPING has mount paths to check. The doctor's PLACEMENT
    # plan is the caller whose `legs:` is a LIST (one record per audited leg,
    # no `spec_path`), and it asks this function only about its entries; a
    # finding about leg paths there would name a key the plan never had.
    if isinstance(plan.legs, dict):
        if tree is None:
            raise TypeError(
                "_leg_findings: a plan with mount paths is asked about the "
                "source paths it keeps in the root, so it needs the source "
                "tree, and was given None")
        findings = [f"FINDING plan-bad-leg-path: {problem}"
                    for problem in leg_path_problems(*_plan_leg_paths(plan))]
        # An overlap is a statement about two PATHS, so it is asked only of
        # canonical ones, as #169 compares the two legs only then.
        if not findings:
            findings = _leg_collision_findings(plan, tree)
    for entry in plan.entries:
        leg = entry.get("leg")
        path = _spelled(str(entry.get("path")))
        if leg is None:
            findings.append(
                f"FINDING plan-unresolved: {path} still has `leg: null`. The "
                f"question was: {entry.get('question')}")
        elif str(leg) not in LEG_VALUES:
            findings.append(
                f"FINDING plan-bad-leg: {path} declares leg {leg!r}; it is "
                f"one of {list(LEG_VALUES)}")
    if isinstance(plan.legs, dict):
        findings += _root_shape_findings(plan, tree)
    return findings


# ---------------------------------------------------------------------------
# What the plan keeps in the root is not where the shape writes (#262, #263)
# ---------------------------------------------------------------------------
#
# `execute` clones the source and writes the shape's files into the clone
# with `place`, which writes a file at its own path, or beside it under
# `shape/` where something is already there, and asks nothing else of the
# disk. A path the plan keeps in the root can stand where `place` writes, and
# `check` said `plan ok` to both ways of it. `execute` then made and pushed
# both legs, and `place` died, or overwrote, in the split:
#
#   * a FILE where the shape needs a DIRECTORY (#263): the source's own file
#     named `.github`, `contracts` or `scripts`, the directories the shape
#     writes into. `.github/workflows/validate.yml` under a file `.github`
#     died in `NotADirectoryError`, `contracts/spec-pin.yaml` under a file
#     `contracts` in `FileExistsError`;
#   * a path where the shape writes its COPY of a file the root holds (#262):
#     the source's own `shape/`, kept in the root. A real `shape/README.md`
#     was overwritten by the shape's README on the line after `execute` said
#     nothing was overwritten, and the verification ended `adopt-lost`; a
#     directory `shape/Makefile/` died in `IsADirectoryError`, and a file
#     named `shape` in `FileExistsError`.
#
# Both are known before any leg exists. The plan says which source paths stay
# in the root (`_kept_in_root`, which #172's mount rule reads too), and
# `assembly_root_paths` lists what the shape writes in the order `place`
# writes it, so `check` plays `place` over the first with the second and
# reports where it would stop or overwrite; `execute` refuses the same plan
# with every other finding of `check`'s (#168). The materializer refuses the
# overwrite and the stop itself too (`shape_materialize.copy_in_the_way`), for
# a caller that skipped `check`.
#
# WHAT `place` DOES, AND SO WHAT IS PLAYED. For each shape path: if a kept
# FILE stands where a directory is needed on the way to it, it cannot be
# written (#263). Else, if the root already holds the path -- a kept path, or
# a kept directory with something under it, as `Path.exists()` reads it --
# its copy goes to `shape/<path>`, which must then be free: nothing kept AT
# it, no kept directory there, and no kept FILE on the way (#262).
#
# A SYMLINK OR A SUBMODULE is never a file on the way: a symlink above a shape
# path or its copy is followed, or refused, by what #183 adds, and a submodule
# the root keeps is `plan-submodule-root` (#166). Neither is a file where a
# directory is needed. AT the copy, a submodule (or a directory there that
# holds nothing but submodules) is `plan-submodule-root`'s too and is not said
# again: it is not written over -- in a clone a submodule is an empty
# directory, and `place` stops at it. A symlink AT the copy is found here,
# and as a write THROUGH it, because nothing else on main says it.
#
# A SYMLINK AT A SHAPE PATH counts as the root holding it, though
# `Path.exists()` follows a link and is false of one that leads nowhere. A
# tree row is a path, a mode and a blob, so the target is not at hand, and
# whether a link leads anywhere is #183's question. Counting it is the
# over-approximation that never says `plan ok` to a plan `place` would stop
# at, and a plan with a link that leads nowhere is refused either way (here,
# and there).
#
# Asked of a disk that keeps case AND of one that ignores it, as #172 asks
# its mount paths and for the same reason: a source file `Scripts` is a file
# where the shape needs `scripts/` on a macOS or Windows disk, and the
# assembly is cloned there. EACH disk answers both questions, whether the
# root holds a path, so that a copy is written at all, and whether a place is
# free: `place` asks `Path.exists()` for the first, which ignores case on
# those disks, so a kept `readme.md` is `README.md` there, the copy goes to
# `shape/README.md`, and what the source keeps at that path is in the way.
# A finding that holds on the second disk alone says so.

#: `check`'s finding for a kept FILE where the shape writes into a directory
#: (#263), and for a kept path where the shape writes its copy of a file the
#: root holds (#262).
ROOT_BLOCKS_SHAPE = "plan-root-blocks-shape"
ROOT_BLOCKS_COPY = "plan-root-blocks-shape-copy"


class _KeptTree:
    """The source paths the plan keeps in the root, looked up as a disk looks
    them up: `fold` is a disk that ignores case, `False` one that keeps it.
    `kept` is `_kept_in_root`'s `(path, mode, entry)` rows.

    A DIRECTORY is a prefix of a kept path: git records files, so a directory
    the plan keeps holds at least one of them."""

    def __init__(self, kept: list, fold: bool) -> None:
        self.rows = kept
        self._fold = fold
        self._at: dict[str, tuple[str, str, str]] = {}
        self._dirs: set[str] = set()
        for row in kept:
            parts = row[0].split("/")
            self._at.setdefault(self._key(row[0]), row)
            self._dirs.update(self._key("/".join(parts[:end]))
                              for end in range(1, len(parts)))

    def _key(self, path: str) -> str:
        return path.casefold() if self._fold else path

    def at(self, path: str) -> tuple[str, str, str] | None:
        """The kept row AT `path`, a file, symlink or submodule."""
        return self._at.get(self._key(path))

    def holds(self, path: str) -> bool:
        """Whether something is at `path`, as `Path.exists()` says: a kept
        row, or a kept directory. A symlink row counts without being
        followed (see the comment above): the row holds no target."""
        return self._key(path) in self._at or self._key(path) in self._dirs

    def file_above(self, path: str) -> tuple[str, str, str] | None:
        """The kept FILE a directory on the way to `path` would have to be,
        the topmost: `mkdir` stops there. A symlink or a submodule is not
        one; see the comment above."""
        parts = path.split("/")
        for end in range(1, len(parts)):
            row = self.at("/".join(parts[:end]))
            if row and row[1] in FILE_MODES:
                return row
        return None

    def under(self, path: str) -> list[tuple[str, str, str]]:
        """Every kept row below the directory `path`."""
        prefix = self._key(path) + "/"
        return [row for row in self.rows
                if self._key(row[0]).startswith(prefix)]


def _shape_blocks(disk: _KeptTree) -> list[tuple]:
    """`(code, shape path, where it is written, group, kept rows)` for each
    path of `assembly_root_paths` that `place` would stop at or overwrite on
    `disk`, in the order it writes them. The disk says both whether the root
    already holds a path, so whether its copy is written at all, and whether
    the place is free: a disk that ignores case holds `README.md` for a kept
    `readme.md`. `group` names the one thing in the way, so that what one
    kept path blocks is one finding."""
    out = []
    for rel in assembly_root_paths():
        above = disk.file_above(rel)
        if above:
            out.append((ROOT_BLOCKS_SHAPE, rel, rel, ("file", above[0]),
                        [above]))
            continue
        if not disk.holds(rel):
            continue
        copy = f"{COLLISION_DIR}/{rel}"
        above = disk.file_above(copy)
        if above:
            out.append((ROOT_BLOCKS_COPY, rel, copy, ("file", above[0]),
                        [above]))
            continue
        at = disk.at(copy)
        # A submodule is `plan-submodule-root`'s (#166), and said once there.
        rows = [row for row in ([at] if at else disk.under(copy))
                if row[1] != GITLINK_MODE]
        if rows:
            out.append((ROOT_BLOCKS_COPY, rel, copy,
                        ("at" if at else "dir", copy), rows))
    return out


#: How a verb of `path_overlap`'s relations reads of several paths.
_PLURAL_RELATION = {"is": "are", "contains": "contain",
                    "is inside": "are inside"}


def _fix_the_kept_path(entry: str) -> str:
    """What every finding of this kind says to do, as `_kept_collisions` ends
    its own: the entry is the plan's to change, or the source's."""
    return (f"send {_spelled(entry)} to a leg, `drop` it, or rename it in "
            "the source and re-run `plan`")


def _blocked_sentence(code: str, rels: list[str], copies: list[str],
                      rows: list, held_aside: str = "") -> str:
    """One finding's sentence: what the shape writes, the kept path in the
    way and how, and what to do. `rels` are the shape paths it blocks,
    `copies` where each is written, `rows` the kept paths in the way, and
    `held_aside` says of a copy that the root holds the path it stands in
    for only once case is ignored."""
    path, mode, entry = rows[0]
    many = len(rels) > 1
    named = _first_and_more([row[0] for row in rows], _spelled)
    them = "them" if len(rows) > 1 else "it"
    under = "" if entry == path else f" under the entry {_spelled(entry)}"
    fix = _fix_the_kept_path(entry)
    if code == ROOT_BLOCKS_SHAPE:
        relation, aside = _overlap(rels[0], path)
        return (
            f"the shape writes {_first_and_more(rels)}, which "
            f"{_PLURAL_RELATION[relation] if many else relation} the file "
            f"{named}{aside}. The plan keeps it in the assembly root{under}, "
            "and `execute` cannot make a directory where a file is, so it "
            "would stop writing the shape's files after both leg "
            f"repositories were created and pushed: {fix}.")
    relation, aside = _overlap(copies[0], path)
    consequence = {
        "is": "`execute` would write the copy "
              f"{'through' if mode == SYMLINK_MODE else 'over'} {them}",
        "contains": "`execute` cannot write a file where a directory is, "
                    "so it would stop",
        "is inside": "`execute` cannot make a directory where a file is, "
                     "so it would stop"}[relation]
    return (
        f"the shape's {'copies' if many else 'copy'} of "
        f"{_first_and_more(rels)} {'are' if many else 'is'} written to "
        f"{_first_and_more(copies)}, because the root already holds "
        f"{'each of them' if many else _first_and_more(rels)}{held_aside}. "
        f"{'Those paths' if many else 'That path'} "
        f"{_PLURAL_RELATION[relation] if many else relation} "
        f"{_kind_of(mode)} {named}{aside}. The plan keeps {them} in the "
        f"assembly root{under}, and {consequence} after both leg "
        f"repositories were created and pushed. {SHAPE_DIR_RESERVED}: {fix}.")


def _root_shape_findings(plan: Plan, tree: list) -> list[str]:
    """`check`'s findings for a path the plan keeps in the root where the
    shape writes (#262, #263): one per kept path in the way, naming the
    first shape path it blocks and counting the rest. Asked of a disk that
    keeps case and then of one that ignores it; a finding the first disk
    already made is not made again, and one only the second makes says so,
    and so does a copy only the second writes."""
    kept = _kept_in_root(plan.entries, tree)
    if not kept:
        return []
    keeps_case = _KeptTree(kept, fold=False)
    seen: set[tuple] = set()
    # `(code, group)` -> the shape paths it blocks, where each is written,
    # the kept rows in the way, and the shape paths the root holds only once
    # case is ignored.
    blocked: dict[tuple, tuple[list, list, list, list]] = {}
    for disk in (keeps_case, _KeptTree(kept, fold=True)):
        for code, rel, copy, group, rows in _shape_blocks(disk):
            if (code, rel, group) in seen:
                continue
            seen.add((code, rel, group))
            rels, copies, _, folded = blocked.setdefault(
                (code, group), ([], [], rows, []))
            rels.append(rel)
            copies.append(copy)
            if code == ROOT_BLOCKS_COPY and not keeps_case.holds(rel):
                folded.append(rel)
    return [f"FINDING {code}: " + _blocked_sentence(
                code, rels, copies, rows, _CASE_ASIDE if folded else "")
            for (code, _), (rels, copies, rows, folded) in blocked.items()]


#: What a plan that splits a source's own submodules is told to do instead.
#: Said by `check`, once after its findings, and by `execute`'s refusal; the
#: `question:` of `.gitmodules`, and of every entry holding a submodule,
#: states the rule.
SUBMODULE_REMEDIATION = (
    "Remediation: send `.gitmodules` and every submodule it registers to ONE "
    "leg, spec or code, or `drop` them together. Any one submodule may also "
    "be dropped on its own: its registration stays behind in the leg "
    "`.gitmodules` went to, inert, because git looks a registration up only "
    "for a gitlink it finds. A submodule the source does not register -- no "
    "`.gitmodules` entry with its path and a url -- cannot be kept in a leg "
    "at all: a top-level `git clone --recurse-submodules` skips it, but the "
    "assembly's clone fails on it inside the leg. `drop` it, or register it "
    "in the source (that entry, committed) and re-run `plan`; a "
    "`.gitmodules` git cannot read for its submodules is repaired in the "
    "source and re-planned the same way (dropping it is enough in a source "
    "with no submodule at its tip or in the history of its branches and "
    "tags). "
    "To answer a submodule apart from the rest of the directory entry that "
    "holds it, REPLACE that entry with an entry for each of its children, "
    "the submodule's own path among them, as that entry's `question:` lists "
    "them: an entry for the submodule added BESIDE the directory's covers it "
    "twice, which is `plan-covered-twice`. The "
    "assembly root never keeps a submodule of the source's: its "
    "`.gitmodules` is reserved for its two leg mounts, and its `validate` "
    "workflow reads every URL in that file as a leg.")

#: Why a kept gitlink with no URL beside it is refused, said in the same
#: words by the two rules that find one.
NO_URL_IN_THE_LEG = ("so the leg that holds the gitlink holds no URL for it "
                     "and the assembly's recursive clone fails there")
#: Why a kept gitlink is not registered, when no entry of `.gitmodules`
#: names its path at all; `Registrations.why_not` says it otherwise.
NO_ENTRY_NAMES_IT = (f"no {GITMODULES} entry in the source registers its "
                     "path with a url")
#: Where git fails on a `.gitmodules` it cannot read for its submodules:
#: the two ends of `_where_git_fails`, each said only where it is true.
FAILS_IN_THE_EXTRACTION = (
    "and the source holds a submodule, so `git filter-repo` fails on that "
    "file when `execute` extracts a leg, wherever the plan sends the two")
FAILS_IN_THE_CLONE = (
    "so which submodules it registers is unknown, and the plan keeps it or a "
    "submodule in a leg, where the assembly's recursive clone fails on it")
#: The first end again, for a source whose tip holds no submodule and whose
#: history does (`_where_the_history_fails`, #195); `{}` is where.
FAILS_IN_THE_HISTORY = (
    "and the source's tip holds no submodule but the history `git "
    "filter-repo` rewrites does -- every branch and tag of the source, where "
    "{} -- so it fails on that file when `execute` extracts a leg, wherever "
    "the plan sends it")


def _answered_legs(entries: list, paths: list[str]) -> dict:
    """`{path: (leg, entry)}` for each path ONE answered plan entry covers.

    A path covered by no entry or by two, or by an entry whose `leg:` is null
    or not one of the four words, is LEFT OUT. Each of those is already a
    finding of `check`'s own -- `plan-uncovered`, `plan-covered-twice`,
    `plan-unresolved`, `plan-bad-leg` -- and a question nobody has answered
    yet cannot have been answered inconsistently. `execute` refuses all four
    too: the null one in `_refuse_an_unrunnable_plan`, the other three in
    #168's `_refuse_what_check_finds`.
    """
    entry_paths = [str(e.get("path")) for e in entries]
    legs = {str(e.get("path")): str(e.get("leg")) for e in entries}
    out: dict[str, tuple[str, str]] = {}
    for path in paths:
        covering = _covering(entry_paths, path)
        if len(covering) == 1 and legs[covering[0]] in LEG_VALUES:
            out[path] = (legs[covering[0]], covering[0])
    return out


def _as_entry(path: str, entry: str) -> str:
    """`path`, and the plan entry to edit when that is a directory above it,
    each `_spelled`: a submodule's path is a source name, and the finding
    that names it is one line (#212)."""
    named = _spelled(path)
    return named if entry == path else f"{named} (entry {_spelled(entry)})"


def submodule_plan_problems(entries: list, tree: list,
                            registered: Registrations | str
                            ) -> list[tuple[str, str]]:
    """`(code, detail)` for each way the plan splits the source's OWN submodules.

    ONE DEFINITION, in the one list of findings `check` prints and `execute`
    refuses (`_entry_findings`), so that `execute` refuses every SUBMODULE
    problem `check` finds, in its words (#166). An entry `check` rejects for
    another reason -- uncovered, covered twice, a misspelled leg -- is left
    out here (see `_answered_legs`): it is in that list by its own finding.
    `tree` is `Source.tree()`: a gitlink is visible only by its mode,
    which no path glob in `contracts/path-classification.yaml` can see.
    `registered` is `Source.registered_submodules(tree)`: what the source's
    `.gitmodules` registers, or, as a string, what git said when it could
    not read that file for its submodules. The caller reads both, so this is
    a function of its arguments alone.

    A SUBMODULE IS ONE FACT IN TWO PLACES: the gitlink in the tree and its
    registration in `.gitmodules`. A plan that sent the two to different legs
    used to run to the end and say `adoption verified` -- every blob was
    accounted for -- and leave an assembly whose `git clone
    --recurse-submodules` exits 128 on `No url found for submodule path`. So,
    in the order the problems are listed:

      * `root` is not an answer for `.gitmodules` or for any gitlink
        (`plan-submodule-root`). The assembly root has exactly two mounts and
        its `.gitmodules` is reserved for them -- `execute` writes a fresh one
        when the source's moves to a leg or is dropped -- and the shape's own
        `validate.yml` reads every URL in that file as a leg. A plan that
        slipped one past this would still fail verification whatever it
        registers, which compares a root-kept `.gitmodules` byte for byte
        after the mount has appended to it, and finds every submodule of the
        source's the root keeps (#165).
      * A `.gitmodules` git cannot read for its submodules is never taken to
        register nothing (`plan-gitmodules-unreadable`, saying what git
        said, and where git fails on it: `_where_git_fails`). Beside a
        submodule it fails the extraction of either leg, wherever the plan
        sends the two, and so it does in a source whose history alone holds
        one (`_where_the_history_fails`, #195); otherwise it is a problem
        where the plan keeps it, or a gitlink, in a leg the assembly's clone
        then recurses into.
      * Every gitlink the plan KEEPS, in the spec or the code leg, must be
        REGISTERED (`plan-submodule-unregistered`). A leg is WORSE than the
        source for one that is not: a top-level `git clone
        --recurse-submodules` of the source skips a gitlink with no URL, but
        the assembly's clone recurses INTO the leg with `--init` and dies on
        it. That holds for an orphan with no `.gitmodules` at all, as `git
        add` of an embedded clone leaves one, and for a gitlink beside a
        `.gitmodules` that registers other paths. Dropped, it is fine.
      * Every REGISTERED gitlink the plan keeps goes where `.gitmodules` goes
        (`plan-submodule-split`) -- which is also why `.gitmodules` cannot be
        dropped while one is kept.
      * A gitlink DROPPED beside a `.gitmodules` that went to a leg is
        allowed. Its registration stays behind in that leg, inert: git walks
        the gitlinks in the INDEX and looks each one up in `.gitmodules`,
        never the other way round, so a registration with no gitlink is never
        cloned and never fails. Dropping all of them with the file is allowed
        too.

    THE ORDER IS THE ORDER TO FIX THEM IN, and a refusal they begin is named
    by the first: a `.gitmodules` in the root makes every registered gitlink
    kept in a leg a split, an unreadable one hides which gitlinks are
    registered, and an unregistered gitlink may be fixed in the SOURCE, by a
    commit and a fresh `plan`, which discards any answer given to a split
    before it.

    A source with neither -- the common case -- returns nothing at once, so
    `check` and `execute` say exactly what they said before.
    """
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    registry = [path for path, _, _, _ in tree if path == GITMODULES]
    if not gitlinks and not registry:
        return []
    answered = _answered_legs(entries, registry + gitlinks)
    problems = [
        ("plan-submodule-root",
         f"{_as_entry(path, entry)} has leg: root, and the assembly root keeps "
         f"no submodule of the source's: its {GITMODULES} is reserved for its "
         "two leg mounts")
        for path, (leg, entry) in answered.items() if leg == "root"]
    registry_leg = answered.get(GITMODULES, (None, None))[0]
    kept = _kept_in_a_leg(answered, gitlinks)
    if not isinstance(registered, str):
        return problems + _kept_submodule_problems(kept, registered,
                                                   registry_leg)
    failure = (_where_the_history_fails(entries, registered)
               or _where_git_fails(entries, tree, registry_leg, kept))
    if failure:
        problems.append((
            "plan-gitmodules-unreadable",
            f"git cannot read the source's {GITMODULES} for its submodules "
            f"({registered}), {failure}"))
    return problems


def _where_git_fails(entries: list, tree: list, registry_leg: str | None,
                     kept: list) -> str | None:
    """Where git fails on a source `.gitmodules` it cannot read for its
    submodules, as the plan answers it; None where nothing reads it so.

    Measured end to end with git 2.43 (#166's S3), the first failure first:

      * `git filter-repo` runs `git fast-export`, which reads the CHECKED-OUT
        `.gitmodules` for each gitlink in the history it exports: every
        commit of every branch and tag of the source, not the tip alone. So
        such a FILE fails the extraction of either leg, wherever the plan
        sends it -- after both leg repositories were made -- in a source
        whose tree holds a submodule (here), and in one whose tree holds
        none and whose history does (`_where_the_history_fails`, asked
        first; #195, where `check` used to pass it). A plan that extracts no
        leg, every path rooted or dropped, is the only one that escapes it.
      * Otherwise the assembly's recursive clone fails in a leg the plan
        keeps the file in, or a gitlink: on a line git cannot parse, even
        with no gitlink in the leg, and on a `.gitmodules` that is itself a
        gitlink, which the clone checks out as a directory and which
        registers nothing.

    A key with no value, or a value git refuses (#215), is fatal to git's
    submodule reader alone, which git runs only for a gitlink, so
    `Source.registered_submodules` reads it as registering nothing where
    neither the tree nor the history `git fast-export` diffs holds one, and
    it reaches here only where one of them does.
    """
    a_file = any(path == GITMODULES and mode in FILE_MODES
                 for path, mode, _, _ in tree)
    beside = any(mode == GITLINK_MODE for _, mode, _, _ in tree)
    if a_file and beside and any(str(e.get("leg")) in EXTRACTED_LEGS
                                 for e in entries):
        return FAILS_IN_THE_EXTRACTION
    if kept or registry_leg in EXTRACTED_LEGS:
        return FAILS_IN_THE_CLONE
    return None


def _where_the_history_fails(entries: list,
                             registered: Registrations | str) -> str | None:
    """`_where_git_fails`' first end, for a source whose tip holds no
    gitlink: FAILS_IN_THE_HISTORY, naming where the history holds one, when
    `registered` is an `InTheHistory` and the plan extracts a leg; None
    otherwise, and `_where_git_fails` is asked as before.

    The plan's answers cannot help here. `_extract_leg` checks the plan's
    commit out whole before `git filter-repo` runs, so the file it reads is
    there whether the plan sends `.gitmodules` to a leg or drops it, and a
    gitlink in the history is not a path the plan can answer (#195)."""
    if isinstance(registered, InTheHistory) and any(
            str(e.get("leg")) in EXTRACTED_LEGS for e in entries):
        return FAILS_IN_THE_HISTORY.format(registered.gitlink)
    return None


def _kept_in_a_leg(answered: dict, gitlinks: list[str]) -> list[tuple]:
    """`(path, leg, entry)` for each gitlink `answered` keeps in a leg."""
    return [(path, *answered[path]) for path in gitlinks
            if path in answered and answered[path][0] in EXTRACTED_LEGS]


def _kept_submodule_problems(kept: list, registered: Registrations,
                             registry_leg: str | None
                             ) -> list[tuple[str, str]]:
    """The last two rules of `submodule_plan_problems`, for the gitlinks the
    plan keeps in a leg: `(path, leg, entry)` each.

    A gitlink is unregistered or split, never both. With no registration it
    has no URL in ANY leg, and moving `.gitmodules` would not give it one.
    An unregistered one is told why: an entry of `.gitmodules` may name its
    path and still register nothing, and saying "no entry" beside it would
    send the person looking for one that is there. `registry_leg` is None
    when `.gitmodules` is absent or not yet answered, which leaves no leg
    for a gitlink to be split from.
    """
    problems = [
        ("plan-submodule-unregistered",
         f"the submodule {_as_entry(path, entry)} has leg: {leg} but "
         f"{registered.why_not(path) or NO_ENTRY_NAMES_IT}, "
         + NO_URL_IN_THE_LEG)
        for path, leg, entry in kept if path not in registered]
    if registry_leg is not None:
        problems += [
            ("plan-submodule-split",
             f"the submodule {_as_entry(path, entry)} has leg: {leg} but the "
             f"source's {GITMODULES} has leg: {registry_leg}, "
             + NO_URL_IN_THE_LEG)
            for path, leg, entry in kept
            if path in registered and leg != registry_leg]
    return problems


# ---------------------------------------------------------------------------
# A kept submodule's RELATIVE url, resolved from the leg that holds it (#190)
# ---------------------------------------------------------------------------
#
# git resolves a submodule url that begins `./` or `../` against the remote of
# the repository whose `.gitmodules` holds it: that repository's default
# remote, or, with none, its own directory (`git help submodule`). Before the
# split that is the SOURCE; after it, the file is in a LEG, so it is the leg's
# remote. `url = ../dependency` names a sibling of the source before and a
# sibling of the leg after, and on main the run said `adoption verified` and
# the assembly's `git clone --recurse-submodules` then failed wherever the
# dependency did not happen to sit beside the leg: under `--local-remote-dir`,
# or with an `--org` other than the source's.
#
# REFUSED, NEVER REWRITTEN. Writing the absolute url into the leg's
# `.gitmodules` would change a blob the verification accounts for by sha, in
# every commit of the leg's history that holds one, and put in the leg a url
# nobody committed. So a url whose two resolutions differ is a finding of
# `check` and a refusal of `execute` before any leg exists, and the person
# commits the absolute url in the source or drops the submodule. Where both
# name the same repository -- legs made in the source's own GitHub
# organisation, or on disk beside the dependency -- nothing changes, and the
# verification has nothing new to account for.
#
# ASKED OF GIT. Each resolution is `git submodule init`'s, run in a scratch
# repository whose `origin` is the remote in question: the code the
# assembly's recursive clone runs, not a copy of it. `repo_shape.join_remote`
# is a copy, and git's arithmetic differs from it where it matters here: git
# takes `..\` for a relative url on every platform and strips it on Windows
# alone, and it fails on a `..` too many where the copy consumes nothing. A
# url that is not relative is never resolved, because git copies it as it
# stands, so a source with no submodule, or none with a relative url, starts
# no git process here.

RELATIVE_URL = "plan-submodule-relative-url"
#: git's own test for a url it resolves against a remote
#: (`starts_with_dot_slash`, `starts_with_dot_dot_slash`): `./` or `../`,
#: with either separator on every platform.
RELATIVE_URL_RE = re.compile(r"\.\.?[/\\]")
#: What a plan that keeps a relative url git resolves elsewhere from its leg
#: is told: by `check`, once after its findings, and by `execute`'s refusal.
RELATIVE_URL_REMEDIATION = (
    "Remediation for a relative submodule url: git resolves it against the "
    "remote of the repository whose `.gitmodules` holds it -- in the "
    "assembly, the leg -- so it must name the same repository from the leg "
    "as from the source. Commit the submodule's absolute url in the source's "
    "`.gitmodules` and re-run `plan`, or `drop` the submodule: its "
    "registration then stays behind in the leg, inert. `check` resolves it "
    "from the GitHub remotes the plan's `org:` names and `execute` from the "
    "remotes it is about to create, before it creates any; under "
    "`--local-remote-dir` those are bare repositories on disk, where "
    "`check`'s `plan ok` settles nothing about it.")


class _Resolution:
    """One relative url as git resolved it from one repository: `url`, or,
    when git could not, `said`, which is what git said."""

    def __init__(self, url: str | None, said: str = "") -> None:
        self.url = url
        self.said = said

    def same_as(self, other: "_Resolution") -> bool:
        """Both resolved, to one repository however each is spelled.

        `remote_key` is the standard's one rule for when two spellings are
        one repository: the source's `origin` may be
        `git@github.com:Org/Thing.git` and a leg's is
        `https://github.com/org/...`. It compares two filesystem paths by
        their text alone, so they are then asked of this machine, whose
        symlinks -- and the `..` of a relative answer joined to the source's
        working tree (`_default_remote`) -- may make two spellings one
        directory: the order `same_repository_here` asks them in, so the
        disk can add an answer and never take one away.
        """
        if self.url is None or other.url is None:
            return False
        if remote_key(self.url) == remote_key(other.url):
            return True
        paths = [remote_local_path(url) for url in (self.url, other.url)]
        return None not in paths \
            and os.path.realpath(paths[0]) == os.path.realpath(paths[1])

    def __str__(self) -> str:
        # `redacted`: a source's remote may carry a token, and so does every
        # url resolved against it.
        return (f"to {_spelled(redacted(self.url))}" if self.url is not None
                else f"not at all ({self.said})")


def _kept_relative_urls(entries: list, tree: list,
                        registered: Registrations | str
                        ) -> tuple[str | None, list[tuple[str, str, str]]]:
    """`(leg, [(path, entry, url), ...])`: each submodule the plan keeps in
    the leg its `.gitmodules` goes to, registered with a relative url, and
    that leg. A submodule kept anywhere else, or not registered, is already
    a finding of `submodule_plan_problems`; a dropped one is inert; and a
    `.gitmodules` git cannot read has no url to read."""
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    if not gitlinks or isinstance(registered, str):
        return None, []
    answered = _answered_legs(entries, [GITMODULES, *gitlinks])
    leg = answered.get(GITMODULES, (None, None))[0]
    return leg, [(path, entry, registered.url(path)) for path, kept, entry
                 in _kept_in_a_leg(answered, gitlinks)
                 if kept == leg and path in registered
                 and RELATIVE_URL_RE.match(registered.url(path))]


def _default_remote(source: Source) -> tuple[str, str, Path | None]:
    """`(base, which, working_tree)`: what git resolves the source's relative
    urls against, how a finding names it, and where the clone opens git's
    answer when that answer is a relative path. git's rule -- the
    checked-out branch's remote, else `origin`; that remote's url, else,
    with none, the repository's own directory -- asked of the branch being
    ADOPTED, which a clone of the source checks out, and not of whatever
    branch this working copy happens to have checked out.

    A RELATIVE REMOTE GIVES A RELATIVE ANSWER. Against `../src/Thing.git`,
    `git submodule init` resolves `../dependency` to `../src/dependency` and
    keeps it so, and `git submodule update` opens that from the top of the
    working tree. Compared as git leaves it, it equalled no leg's answer,
    and a layout whose clone works was refused (#190, P3-2). So
    `working_tree` is the source's own for such a remote -- a path, and not
    an absolute one (`remote_local_path` names absolute paths only), which
    is git's own test for the answers it leaves relative -- and None for
    every other base."""
    name = _config_value(source.path, f"branch.{source.branch}.remote") \
        or "origin"
    url = _config_value(source.path, f"remote.{name}.url")
    if url is None:
        return (source.path.as_posix(),
                f"its own directory, as it has no remote {_spelled(name)}",
                None)
    if remote_is_a_path(url) and remote_local_path(url) is None:
        return (url, f"its remote {_spelled(name)}, relative to its working "
                "tree", source.path)
    return url, f"its remote {_spelled(name)}", None


def _config_value(repository: Path, key: str) -> str | None:
    """`key` in `repository`'s git config, as git reads it -- the last
    value, when there are several; None when unset."""
    got = subprocess.run(["git", GIT_CONFIG, "-z", "--get", key],
                         cwd=repository, capture_output=True, check=False)
    return None if got.returncode else _git_path(got.stdout.rstrip(b"\x00"))


def _resolved(base: str, urls: list[str],
              working_tree: Path | None = None) -> list[_Resolution]:
    """Each of `urls` as `git submodule init` resolves it in a repository
    whose `origin` is `base`, in a scratch repository made for the purpose
    and removed after it; and, given a `working_tree`, git's relative answer
    joined to it, which is what the clone opens (`_default_remote`). A url
    git cannot resolve is what git said: that is where the clone fails."""
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-url-"))
    try:
        run(["git", "init", "-q", str(scratch)])
        run(["git", GIT_CONFIG, "remote.origin.url", base], cwd=scratch)
        for index, url in enumerate(urls):
            for key, value in (("path", f"u{index}"), ("url", url)):
                run(["git", GIT_CONFIG, "-f", GITMODULES,
                     f"submodule.u{index}.{key}", value], cwd=scratch)
        # A gitlink names a commit nobody fetches here; any object id of the
        # repository's own format will do, and this one is at hand.
        oid = run(["git", "hash-object", GITMODULES], cwd=scratch)
        for index in range(len(urls)):
            run(["git", "update-index", "--add", "--cacheinfo",
                 f"{GITLINK_MODE},{oid},u{index}"], cwd=scratch)
        # One `init` per url, because git stops at the first it cannot
        # resolve and each finding names its own.
        return [_resolution_of(scratch, f"u{index}", working_tree)
                for index in range(len(urls))]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _resolution_of(scratch: Path, name: str,
                   working_tree: Path | None) -> _Resolution:
    """`name`'s url, as `git submodule init` copies it into the config, and
    joined to `working_tree` when there is one."""
    init = subprocess.run(["git", "submodule", "init", "-q", "--", name],
                          cwd=scratch, capture_output=True, check=False)
    if init.returncode:
        return _Resolution(None, _one_line(init.stderr.decode(
            errors="replace")))
    url = _config_value(scratch, f"submodule.{name}.url")
    if working_tree is None or url is None:
        return _Resolution(url)
    # Not normalised: `..` after a symlink is the disk's to resolve, and
    # `same_as` asks the disk (`realpath`) for exactly that.
    return _Resolution((working_tree / url).as_posix())


def _relative_url_findings(plan: Plan, source: Source, tree: list,
                           registered: Registrations | str,
                           local_remote_dir: Path | None
                           ) -> tuple[list[str], list[str]]:
    """`(findings, notes)` for the relative urls of the submodules the plan
    keeps in a leg: a `plan-submodule-relative-url` FINDING for each that
    git resolves to another repository from its leg than from the source,
    or cannot resolve from one of them; and, when there is none of those,
    the one NOTE `check` prints about what it could not know.

    THE LEG'S REMOTE IS THE ONE `execute` WOULD CREATE: under
    `local_remote_dir`, the bare repository there; otherwise the GitHub
    repository the plan's `org:` and leg name give. `check` takes no
    `--local-remote-dir`, so it decides on GitHub's, and `execute` decides
    again on the remotes it is about to create, before it creates any. They
    are read only when there is a relative url to resolve, and the NOTE
    says, where `check` resolved them all alike, that it was GitHub's it
    asked: a plan it passes can still be refused by `execute
    --local-remote-dir`."""
    leg, kept = _kept_relative_urls(plan.entries, tree, registered)
    if not kept:
        return [], []
    remote = _remote_urls(checked_value("org", plan.get("org")), plan.names(),
                          local_remote_dir, source)[leg]
    base, which, working_tree = _default_remote(source)
    urls = [url for _, _, url in kept]
    found, alike = [], []
    for (path, entry, url), here, there in zip(
            kept, _resolved(base, urls, working_tree),
            _resolved(remote, urls)):
        if here.same_as(there):
            alike.append(f"{_spelled(url)} of {_spelled(path)}, {there}")
            continue
        found.append(
            f"FINDING {RELATIVE_URL}: the submodule {_as_entry(path, entry)} "
            f"has leg: {leg}, and its url in the source's {GITMODULES} is the "
            f"relative {_spelled(url)}, which git resolves against the remote "
            "of the repository holding that file: from the source, at "
            f"{_spelled(redacted(base))} ({which}), {here}, and from the "
            f"{leg} leg, at {_spelled(remote)}, {there}; the assembly's "
            "recursive clone resolves it from the leg")
    if found or local_remote_dir is not None:
        return found, []
    return [], [
        f"NOTE `check` resolved the relative url of each submodule the plan "
        f"keeps in the {leg} leg from that leg's GitHub remote, "
        f"{_spelled(remote)}, and each names the same repository from there "
        f"as from the source: {'; '.join(alike)}. `execute "
        "--local-remote-dir` resolves it again from the bare repository it "
        "would create instead, and refuses there, before it creates any leg, "
        "a url that names another repository."]


def _submodule_findings(plan: Plan, source: Source, tree: list,
                        local_remote_dir: Path | None = None
                        ) -> tuple[tuple[list[str], list[str]],
                                   tuple[list[str], list[str]], list[str]]:
    """`(findings, remediation)` for `submodule_plan_problems`, one FINDING
    each and SUBMODULE_REMEDIATION when there is one; the same for each
    `_relative_url_findings` one, with RELATIVE_URL_REMEDIATION; and the
    NOTEs `check` prints. A remediation is printed ONCE after every finding.
    The two come back apart because `_entry_findings` lists the relative
    urls last, after the values #255 finds. `check` is where the person is
    told to fix the plan, so it says how, in the words `execute`'s refusal
    would use one step later."""
    registered = source.registered_submodules(tree)
    found = [f"FINDING {code}: {detail}" for code, detail
             in submodule_plan_problems(plan.entries, tree, registered)]
    moved, notes = _relative_url_findings(plan, source, tree, registered,
                                          local_remote_dir)
    return ((found, [SUBMODULE_REMEDIATION] if found else []),
            (moved, [RELATIVE_URL_REMEDIATION] if moved else []), notes)


#: The answers that never extract an entry into a leg. A path answered
#: `root` stays in the assembly root and reaches no `git` command but as a
#: line of the split commit's message; one answered `drop` reaches only
#: `git rm`, as a literal path after `--`, and that message. Neither is ever
#: a line of the path list `git filter-repo` reads, so `entry_path_problem`
#: does not judge them (#196).
NOT_EXTRACTED = ("root", "drop")

#: Two characters Python's `str.splitlines` ends a line at that are not
#: control characters. `entry_path_problem` refuses them with the control
#: characters, as policy.
LINE_SEPARATORS = "\u2028\u2029"

#: The surrogates `surrogateescape` reads a byte that is not UTF-8 as, and
#: writes back as that byte (`Source.tree`, `write_paths_listing`): a path's
#: byte 0x80 to 0xFF is one of these. `entry_path_problem` refuses them as
#: policy, and every other surrogate as a misreading.
NOT_UTF8_BYTES = frozenset(map(chr, range(0xDC80, 0xDD00)))

#: What every policy refusal says of git and `git filter-repo`, because it is
#: true of each of them, measured: a policy refusal is not a misreading.
TAKEN_LITERALLY = "though git and `git filter-repo` would take it literally"


def entry_path_problem(path: str) -> str | None:
    """Why `execute` will not extract the entry path `path` into a leg, or
    None.

    ONE TEST, asked by `check`, which reports what it finds as the finding
    `plan-unsafe-path`, and by `execute`, which refuses that finding in
    `check`'s words through `_refuse_what_check_finds` before any leg exists
    (#196). On main at e4decfb `check` asked nothing of an entry's path and
    `execute` asked `checked_value`, so a source holding `My Notes.md`
    checked `plan ok` and `execute` refused it as `unsafe-value`.

    AN ENTRY'S PATH IS A FACT OF THE SOURCE, NOT AN OPTION. `plan` writes it
    from the tree, and a tree legitimately holds a space, a letter outside
    ASCII, `#`, `$`, `(`, `'`, `"`, `;`, `&`, `[`, `*`: none of them is the
    threat, as `repo_shape.SAFE_PATH_RE` says of a path the operator names.
    Every command is argv with `shell=False`, and in `execute` an entry's
    path reaches `git` in two places, each spelled so git reads it
    LITERALLY:

      * as one `literal:` line of the path list `git filter-repo
        --paths-from-file` reads (`_extract_leg`). Without the prefix a line
        starting with `#` is a comment and one starting with `regex:`,
        `glob:` or `literal:` is that directive, so `#notes.md` was left out
        of its leg -- removed from the root by the split, then found nowhere;
      * as a pathspec after `--` to `git --literal-pathspecs rm`
        (`_mount_the_legs`). After `--` a path is no option, but it is still
        a pathspec: `*` and `?` are wildcards and a leading `:` is magic, and
        `git rm -- ':!keep.md'` removes every other path in the tree.

    Two kinds of path are refused, and each finding says which kind, and
    why. First, `_misread`: a path one of those two places, or this tool's
    own write of the list, would NOT carry as it stands. Then
    `_refused_by_policy`: a path both would carry, measured, that this tool
    still will not move into a leg. A path with a reason of each kind is
    told the misreading.

    THE VALUES THAT ARE OPTIONS ARE ANOTHER MATTER: a leg's mount path, a
    branch, a repository name, the organisation. They stay under
    `checked_value`'s narrow alphabet and are refused as `unsafe-value`
    (#168, #169).
    """
    return _misread(path) or _refused_by_policy(path)


def _misread(path: str) -> str | None:
    """Why `path`, as a `literal:` line or a literal pathspec, would not reach
    git or `git filter-repo` as the path it is. Measured with git 2.43 and
    git-filter-repo 2.47.0, whose `get_paths_from_file` reads its list a line
    at a time, strips `\\r` and `\\n` from each line's end, skips a blank
    line, and looks for `==>` before anything else:

      * an empty path: a `literal:` line with nothing after it matches every
        path, and the leg took the whole tree (and `git rm` refuses an empty
        pathspec);
      * a line feed, anywhere: it ends the path's line, and the rest is read
        as a line of its own -- `docs\\nregex:.*` kept every path;
      * a carriage return at the END: stripped, so `Icon\\r` -- the macOS
        folder-icon file -- was read as `Icon`, and the leg took that file
        instead. A name of carriage returns alone leaves `literal:` with
        nothing after it, which, as for the empty path, kept every path. A
        carriage return elsewhere is carried, and is policy's;
      * a NUL, which no command line can carry (`subprocess` raises), and
        which git records in no path;
      * a lone surrogate (category Cs) outside U+DC80 to U+DCFF, such as a
        hand-edited `\\ud800`. `Source.tree` reads a byte that is not UTF-8
        as one of U+DC80 to U+DCFF (`surrogateescape`), so no path of the
        source holds any other, and `_extract_leg`'s `write_paths_listing`
        cannot write one: it raised `UnicodeEncodeError`, measured. (Such an
        entry also covers nothing, so `check` reports `plan-empty-entry`
        beside it.) A byte that is not UTF-8 is policy's;
      * `==>`, which `git filter-repo` reads as a RENAME wherever it is on a
        line, before it looks for `literal:`, and which nothing escapes:
        `literal:a==>b.md` beside `literal:keep.md` extracted only
        `keep.md`.
    """
    if not path:
        return ("it is empty: a `literal:` line with nothing after it "
                "matches every path, so `git filter-repo` would put the "
                "whole tree in the leg")
    if "\n" in path:
        return ("it holds a line feed (`\\n`), which ends its line of the "
                "path list `git filter-repo` reads, so the rest of the name "
                "would be read as a line of its own")
    if path.endswith("\r"):
        rest = path.rstrip("\r")
        named = (f"would name {_spelled(rest)}, another path" if rest
                 else "would be `literal:` alone, which matches every path, "
                      "so `git filter-repo` would put the whole tree in the "
                      "leg")
        return ("it ends in a carriage return (`\\r`), which `git "
                "filter-repo` strips from the end of each line of the path "
                f"list it reads, so its line {named}")
    if "\x00" in path:
        return ("it holds a NUL (`\\x00`), which no command line can carry "
                "and git records in no path")
    for char in path:
        if "\ud800" <= char <= "\udfff" and char not in NOT_UTF8_BYTES:
            return (f"it holds `{_spelled_character(char)}`, a surrogate no "
                    "byte of a path is read as, so it names no path of the "
                    "source, and the path list `git filter-repo` reads cannot "
                    "be written with it")
    if "==>" in path:
        return ("it holds `==>`, which `git filter-repo --paths-from-file` "
                "reads as a rename wherever it is on the line, and nothing "
                "on the line escapes it")
    return None


def _refused_by_policy(path: str) -> str | None:
    """Why this tool will not move `path` into a leg although git and `git
    filter-repo` would take it literally. MEASURED, each as one `literal:`
    line and as `git --literal-pathspecs rm -r -q -- <path>`: a tab, `\\x01`,
    ESC, DEL, `\\x85`, `\\x0b`, `\\x0c`, `\\x1c`, U+2028, a carriage return
    that does not end the name, `-n.md`, ` ` and three spaces were each
    extracted, and removed, as exactly that path and nothing else. So each
    finding below says it is policy, and never that a line would break:

      * a name that is nothing but whitespace, which shows as blank wherever
        a name is printed. (`git commit` even strips a line of spaces from
        the split commit's message, which lists the moved paths.)
      * a control character (C0, DEL, C1) or a line separator: a name that
        holds one is almost never meant, and printed as it stands -- as
        `git log` prints a commit message, ESC and `\\x01` raw, measured --
        it cannot be seen for what it is;
      * a byte that is not UTF-8, which `Source.tree` keeps as one of
        U+DC80 to U+DCFF (`surrogateescape`). Since #199 (PR #247)
        `write_paths_listing` writes it as that byte, and with this refusal
        disabled a source holding `caf\\xe9.md` was extracted and verified,
        the byte in the leg, measured. It is held until adopting such a name
        end to end is measured on macOS and Windows: a name that holds one
        prints as an escape, never as itself, and the split commit's message
        lists it with a `?` for the byte (`env_commit`);
      * a leading `-`, the threat model's first rule
        (`repo_shape.checked_value`), held although neither place in
        `entry_path_problem` takes it as an option: a line of the filter's
        path list is none, and `git rm` is given it after `--`.
    """
    if not path.strip():
        return ("it is nothing but whitespace, which `execute` refuses as "
                f"policy, {TAKEN_LITERALLY}: such a name shows as blank "
                "wherever a name is printed")
    for char in path:
        if ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F \
                or char in LINE_SEPARATORS:
            kind = ("line separator" if char in LINE_SEPARATORS
                    else "control character")
            return (f"it holds the {kind} `{_spelled_character(char)}`, "
                    f"which `execute` refuses as policy, {TAKEN_LITERALLY}: "
                    "a name that holds one is almost never meant, and "
                    "printed as it stands, as `git log` prints a commit "
                    "message, it cannot be seen for what it is")
    for char in path:
        if char in NOT_UTF8_BYTES:
            return (f"it holds `{_spelled_character(char)}`, which is not "
                    "UTF-8 and which `execute` refuses as policy, "
                    f"{TAKEN_LITERALLY}: a name that holds one prints as an "
                    "escape and never as itself, the split commit's message "
                    "would list it with a `?` for that byte, and adopting "
                    "one is not yet measured on macOS or Windows")
    if path.startswith("-"):
        return ("it begins with `-`, which `execute` refuses as policy, "
                f"{TAKEN_LITERALLY} (a line of the filter's path list is no "
                "option, and `git rm` is given it after `--`): no value this "
                "tool hands git may begin with `-`, the threat model's first "
                "rule")
    return None


#: What a plan whose entry `entry_path_problem` refuses is told to do. Said by
#: `check`, once after its findings, and by `execute`'s refusal.
UNSAFE_PATH_REMEDIATION = (
    "Remediation: an entry's `path:` names a path in the source tree, so the "
    "plan cannot respell it: the respelled entry would cover nothing and the "
    "path itself would be uncovered. Rename the path in the source, commit, "
    "and re-run `plan`. Or, if it belongs in no leg, answer the entry `root` "
    "or `drop`: a path that stays in the assembly root reaches no `git` "
    "command, and a dropped one reaches only `git rm`, as a literal path "
    "after `--`. Only a path the plan names as an entry is judged: a name "
    "below a directory entry is extracted with that directory and never "
    "written on its own.")


def _unsafe_path_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """`entry_path_problem` for each entry not answered `root` or `drop`, as
    `check` prints it, one FINDING each; and what to print ONCE after every
    finding, as `_submodule_findings` does. An unanswered entry is judged
    too, so the person answering its question knows what `spec` or `code`
    would meet."""
    found = []
    for entry in plan.entries:
        if str(entry.get("leg")) in NOT_EXTRACTED:
            continue
        path = str(entry.get("path"))
        problem = entry_path_problem(path)
        if problem:
            found.append(f"FINDING plan-unsafe-path: {_spelled(path)} has "
                         f"leg: {y(entry.get('leg'))}, and `execute` will "
                         f"not extract it into a leg: {problem}")
    return found, [UNSAFE_PATH_REMEDIATION] if found else []


def _entry_findings(plan: Plan, source: Source,
                    local_remote_dir: Path | None = None
                    ) -> tuple[list[str], list[str], list[str]]:
    """Every FINDING `check` prints about the plan's ENTRIES, in its order,
    what it prints once after them, and the NOTEs it prints beside them:
    each entry's path, then coverage, then each entry's `leg:`, the two
    mount paths and what the root keeps where the shape writes, then the
    source's own submodules, then each symlink the plan keeps in the root
    that a shape file cannot be written through (#178, #183), then each
    value `execute` writes into a file that no file can hold (#255), and
    last each relative url of a kept submodule that names another
    repository from its leg (#190).

    ONE LIST, read by `check` and by `execute`'s `_refuse_what_check_finds`.
    #168 and #166 each added findings to `check` and a refusal to `execute`
    while both were open, and composed them separately so as not to edit the
    same lines; three compositions then disagreed, and a plan `check`
    rejected as uncovered AND split was refused by `execute` for the split
    alone, to be refused again for the rest once that was fixed. Composed
    once, the two commands cannot differ about a plan -- but in the two
    places something outside the plan decides it. `local_remote_dir` is
    `execute`'s, and a relative submodule url is resolved from the leg
    remotes it names, where `check` has none and resolves from GitHub's
    (#190). And whether anything is at the place outside the assembly that
    a symlink AT a shape path leads to is asked of the disk by each command
    when it runs, a climb above the root from its own work directory (#183).

    `_leg_findings` is handed the TREE, because the paths the plan keeps in
    the root are read out of it (#172, #191): without it a mount path at, or
    beyond, a kept source path checks ok and dies at `git submodule add`
    after both legs are pushed.

    THE PATHS COME FIRST (#196), so that `_refuse_what_check_finds` wears
    `plan-unsafe-path` for a plan that has one: a path that is a `git` option
    is refused as that, and never as the uncovered file it also leaves.
    """
    tree = source.tree()
    unsafe, unsafe_remediation = _unsafe_path_findings(plan)
    findings = (unsafe
                + _coverage_findings([str(e.get("path"))
                                      for e in plan.entries],
                                     [path for path, _, _, _ in tree])
                + _leg_findings(plan, tree))
    (split, split_remediation), (moved, moved_remediation), notes = \
        _submodule_findings(plan, source, tree, local_remote_dir)
    unwritable_findings, unwritable_remediation = _value_findings(plan)
    return (findings + split + _root_symlink_findings(plan, source, tree)
            + unwritable_findings + moved,
            unsafe_remediation + split_remediation + unwritable_remediation
            + moved_remediation, notes)


def _topics_line(topic: str, local: bool) -> str:
    """The `topics` plan line, the one `scaffold-project.py` also prints.

    A project's repositories carry `xf-project-<id>` so the organisation can
    be listed by project; the adopted assembly root is the project's own root
    and gets it exactly as the two new legs do.
    """
    return "  topics " + ("skipped for local remotes" if local else
                          f"gh repo edit --add-topic {topic} on all three")


def _print_what_will_happen(plan: Plan, source: Source, names: dict,
                            topic: str, local: bool = False) -> None:
    moved = [e for e in plan.entries if str(e.get("leg")) in ("spec", "code")]
    stays = [e for e in plan.entries if str(e.get("leg")) == "root"]
    drops = [e for e in plan.entries if str(e.get("leg")) == "drop"]
    seeded = seeded_legs(assigned_paths(plan.entries))
    where = source.repository or _shown(str(source.path))
    print(f"\nWHAT WILL HAPPEN, against {where} @ {source.commit[:12]}:")
    # Every value below that is the plan's own is `_shown`, as a name is:
    # since #247 the reader gives back a lone surrogate, which raised on a
    # strict stdout before the FINDING about it was printed (#255).
    print(f"  create {names['spec']} and {names['code']} "
          f"({_shown(str(plan.get('visibility', 'private')))})")
    print(f"  extract {len(moved)} path(s) with `git filter-repo`, history "
          "preserved")
    for role in seeded:
        print(f"  SEED the {role} leg from {SEED_TEMPLATE[role]}/ — no path is "
              "assigned to it")
    print(f"  ONE split commit on branch "
          f"{_shown(str(plan.get('adopt_branch', ADOPT_BRANCH)))} "
          f"of {names['assembly']}: `git rm -r` those paths, mount the legs at "
          f"{_shown(str(_plan_leg_path(plan, 'spec')))}/ and "
          f"{_shown(str(_plan_leg_path(plan, 'code')))}/")
    print(f"  {len(stays)} path(s) stay in the assembly root; "
          f"{len(drops)} dropped")
    print("  the source is never deleted, never renamed, never force-pushed")
    print(_topics_line(topic, local))
    for item in plan.get("follow_ups", []):
        print(f"  follow-up: {_shown(str(item))}")


# ---------------------------------------------------------------------------
# A symlink the plan keeps in the root, and the shape writes through (#178)
# ---------------------------------------------------------------------------
#
# The shape's files are written into the assembly by plain path, so a symlink
# the plan keeps in the root at or above one of those paths is followed.
# Before #178, `check` asked nothing about such a link. One that led out of
# the tree made `execute` write the shape's `validate.yml` outside the
# assembly. One that led to nothing, into a leg, or round a loop made it die
# in a traceback. Both happened AFTER both leg remotes had been pushed, so
# the corrected plan then met `leg-remote-exists`.
#
# WHAT THE MATERIALIZER WILL DO decides each path, in the order it writes
# them (#183's review, B1). `place` first asks whether something is already
# at the path, following every symlink on the way. Where something is, the
# shape's copy goes beside it under `shape/`, and the link is never written
# through: `CLAUDE.md` linked to a personal file by its absolute path, on a
# machine that has that file, is adopted exactly as `main` adopts it. Where
# nothing is, the shape writes through every link on the way, so a link
# that dangles, loops or leads out of the assembly is refused. A symlink
# ABOVE a path the shape writes is a directory the shape writes into, so it
# must lead to a directory the root holds, whatever this machine holds
# elsewhere. And `place` asks where the shape's copy under `shape/` lands
# only of the disk, after both legs exist (#262's `copy_in_the_way`), while
# #262's `check` rule follows no link, so a symlink that leads the COPY onto
# something already there is refused here too (B2).
#
# Whether something is at a place OUTSIDE the assembly is a fact of the
# machine, so `check` and `execute` each ask their own disk: an absolute
# target as it stands, and a climb above the root from the work directory,
# where `execute` makes the assembly's clone. Each says what is true where it
# runs, and `execute` asks before any leg exists. A target is absolute as
# this machine's `open()` reads it: `C:/x`, a drive letter's path, is a place
# on this disk only on Windows. On Linux and macOS it is a relative path,
# into a directory named `C:`, and it is followed as one, as `open()` and the
# materializer follow it there.

#: The finding for a symlink the plan keeps in the root that the shape cannot
#: write through.
ROOT_SYMLINK = "plan-root-symlink"
#: The directory the shape's scripts are written to, read off the
#: materializer's own name for one of them.
SHAPE_SCRIPTS = PurePosixPath(BOOTSTRAP).parent.as_posix()
#: The `leg:` answers that take a path out of the assembly root.
NOT_IN_THE_ROOT = (*EXTRACTED_LEGS, "drop")
#: What a symlink with an absolute target leads to.
ON_THIS_MACHINE = ("an absolute path: a place on this machine, not in the "
                   "assembly")
#: The parts of a path that name no entry, and leave a walk where it is.
HERE = ("", ".")
#: What the assembly's clone holds in its own `.git` whatever the git
#: version: `execute` clones with no template (#243), and git makes these in
#: every repository. A symlink AT a path the shape writes that leads to one
#: of them finds something there, so `place` writes the shape's copy beside
#: it and keeps the link, as on main. Nothing else under `.git` is counted:
#: what else is there depends on git's version and configuration, and a
#: link that leads the shape INTO `.git` writes where no commit holds it.
CLONE_GIT = frozenset({".git", ".git/HEAD", ".git/config", ".git/objects",
                       ".git/refs"})
#: `CLONE_GIT` as a disk that ignores case finds it.
CLONE_GIT_FOLDED = frozenset(path.casefold() for path in CLONE_GIT)


def _absolute_here(target: str) -> bool:
    """Whether this machine's `open()` reads the symlink target `target` as
    an absolute path: one from `/` anywhere, and a drive letter's (`C:/x`)
    on Windows only."""
    return target.startswith("/") or (
        os.name == "nt" and WINDOWS_ABSOLUTE_RE.match(target) is not None)


class _Walk:
    """One path the shape writes, followed through a `_PlannedRoot` as the
    materializer's `open()` will follow it: the symlinks met on the way, in
    order, as `(path, target)`; where it lands, and whether that is outside
    the assembly; whether something is already there, so that `place`
    writes the shape's copy beside it under `shape/`; the symlink with an
    empty target it met, if any; and, once a symlink has been met, what
    stops it, or None."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.links: list[tuple[str, str]] = []
        self.landed = ""
        self.outside = False
        self.taken = False
        self.empty = ""
        self.problem: str | None = None


class _PlannedRoot:
    """The assembly root as the materializer will find it, read out of the
    plan and the source tree BEFORE any leg exists (#178, #183).

    It holds every source path the plan keeps in the root, each symlink with
    the target its blob holds; the `.gitmodules` the mounts write; each leg's
    mount, holding what that leg will hold (the source paths the plan sends
    to it, at their own paths, or the shape's template for a seeded leg); and
    an empty directory for each submodule, because the assembly's clone is
    not recursive. It does not hold a path the plan sends to a leg or drops:
    the mount's `git rm` has removed it by the time the shape is written.
    A symlink AT a path the shape writes also finds what every clone's own
    `.git` holds (`CLONE_GIT`), and nothing else in `.git`.
    `walks` adds what the shape itself writes, path by path, as `place` does,
    so `CLAUDE.md -> AGENTS.md` finds the `AGENTS.md` the shape wrote first.

    A path is followed the way `open()` follows it in a checkout: each
    symlink from its own directory, `..` only from a directory, and a link
    out of the assembly onto this machine's disk. A file the shape writes
    through a dangling link is only reachable through that link, and Git
    reads `.gitattributes` and `.gitignore` only as files, never through a
    symlink, so the shape's copy there would do nothing: such a link is
    refused, as one that leads out of the assembly is.

    `fold` follows paths as a macOS or Windows disk does, where `.GitHub`
    and `.github` are one name. `_root_symlink_findings` asks both ways, so
    a case twin is refused on every disk, as #169, #198 and #200 refuse
    theirs.
    """

    def __init__(self, plan: Plan, source: Source, tree: list, *,
                 fold: bool = False) -> None:
        self.source = source
        self.fold = fold
        self.entries: dict[str, tuple[str, str]] = {
            GITMODULES: (FILE_MODES[0], "")}
        self.gone: dict[str, str] = {}
        self.mounts: dict[str, str] = {}
        self.legs: dict[str, str] = {}
        self._keep(plan, tree)
        self._mount(plan, tree)
        self.dirs: set[str] = set()
        self._folded: dict[str, str] = {}
        for path in [*self.entries, *self.mounts]:
            self._add(path)
        self.dirs.update(self.mounts)
        self.dirs.update(path for path, (mode, _) in self.entries.items()
                         if mode == GITLINK_MODE)
        self.assembly, self.beside = _work_dir_names(plan)
        self._targets: dict[str, str] = {}
        self._walks: list[_Walk] | None = None

    def _keep(self, plan: Plan, tree: list) -> None:
        """Each source path: kept in the root, or gone to a leg or `drop`."""
        entry_paths = [str(e.get("path")) for e in plan.entries]
        legs = {str(e.get("path")): str(e.get("leg")) for e in plan.entries}
        for path, mode, oid, _ in tree:
            covering = _covering(entry_paths, path)
            leg = legs[covering[0]] if len(covering) == 1 else ""
            if leg in NOT_IN_THE_ROOT:
                self.gone[path] = leg
            else:
                self.entries[path] = (mode, oid)
        # A kept entry that is neither a file nor a symlink is a gitlink: a
        # directory in a checkout, holding another repository.
        self.mounts = {path: f"it enters {_spelled(path)}, a submodule the "
                             "plan keeps in the root"
                       for path, (mode, _) in self.entries.items()
                       if mode not in (*FILE_MODES, SYMLINK_MODE)}

    def _mount(self, plan: Plan, tree: list) -> None:
        """Each leg's mount, and what the leg will hold under it."""
        spec, code = _plan_leg_paths(plan)
        if leg_path_problems(spec, code):
            return
        seeded = seeded_legs(assigned_paths(plan.entries))
        for (_, mount), role in ((spec, "spec"), (code, "code")):
            self.mounts[mount] = (f"it enters {_spelled(mount)}, where the "
                                  f"plan mounts the {role} leg")
            self.legs[mount] = role
            held = ([(rel, FILE_MODES[0], "") for rel in template_files(
                SHAPE_ROOT / SEED_TEMPLATE[role])] if role in seeded else
                    [(path, mode, oid) for path, mode, oid, _ in tree
                     if self.gone.get(path) == role])
            for path, mode, oid in held:
                self.entries[f"{mount}/{path}"] = (mode, oid)

    def _add(self, path: str) -> None:
        """`path` and the directories above it, as lookups find them."""
        parts = path.split("/")
        for end in range(1, len(parts) + 1):
            here = "/".join(parts[:end])
            if end < len(parts):
                self.dirs.add(here)
            self._folded.setdefault(here.casefold(), here)

    def walks(self) -> list[_Walk]:
        """Each path the shape writes, followed, in the order `place` writes
        them: the path itself, and its copy under the collision directory
        where the path is already taken."""
        if self._walks is None:
            self._walks = []
            for path in assembly_root_paths():
                self._place(path)
        return self._walks

    def _place(self, path: str) -> None:
        """What `place` will do with `path`: follow it, or, where something
        is already there, follow the shape's copy of it under the collision
        directory. What it writes is added to this tree."""
        walk = self.walk(path)
        self._walks.append(walk)
        if walk.problem is None and walk.taken:
            walk = self.walk(f"{COLLISION_DIR}/{path}")
            self._walks.append(walk)
            if walk.problem is None and walk.links and walk.taken:
                walk.problem = self._over(walk)
        if walk.problem is None and not walk.taken:
            self.entries[walk.landed] = (FILE_MODES[0], "")
            self._add(walk.landed)

    def walk(self, path: str) -> _Walk:
        """`path` followed through this tree. Each part on the queue carries
        the symlink whose target it came from; whether that symlink is the
        LAST thing the path is followed through, so that the shape writes AT
        its destination rather than beneath it; and, on the last part of a
        target, the symlinks whose destination it completes."""
        walk = _Walk(path)
        queue = [(part, "", False, ()) for part in path.split("/")]
        done: list[str] = []
        while queue and walk.problem is None:
            done, queue = self._next(walk, done, queue.pop(0), queue)
        if not walk.outside:
            walk.landed = "/".join(done)
            walk.taken = self._has(walk.landed)
        return walk

    def _next(self, walk: _Walk, done: list[str], item: tuple,
              queue: list) -> tuple[list[str], list]:
        """`done` and the queue after one part of the path."""
        part, origin, last, ends = item
        link = self._link("/".join([*done, part]), part)
        if link is not None:
            return done, self._through(walk, link, ends, queue)
        if part == ".." and not done:
            return done, self._above(walk, origin, last, queue)
        done = self._step(walk, done, part, last, bool(queue))
        if ends and walk.problem is None:
            walk.problem = self._arrival(done, ends[0][0], queue)
        return done, queue

    def _real(self, path: str) -> str | None:
        """How this tree spells `path`, or None where nothing is there: the
        path itself, or, folding case, the twin a disk that ignores case
        would find."""
        if not path or path in self.entries or path in self.dirs:
            return path
        return self._folded.get(path.casefold()) if self.fold else None

    def _has(self, path: str) -> bool:
        """Whether something is at `path`, as `Path.exists()` would say: in
        this tree, or in the clone's own `.git` (`CLONE_GIT`). Only this
        asks the clone's `.git`; `_is_dir` does not, so a link ABOVE a path
        the shape writes still cannot lead it into `.git` (D9)."""
        if self._real(path) is not None:
            return True
        return (path.casefold() in CLONE_GIT_FOLDED if self.fold
                else path in CLONE_GIT)

    def _is_dir(self, path: str) -> bool:
        real = self._real(path)
        return real is not None and (not real or real in self.dirs)

    def _is_file(self, path: str) -> bool:
        mode = self.entries.get(self._real(path) or "", ("", ""))[0]
        return mode in FILE_MODES

    def _link(self, at: str, part: str) -> tuple[str, str] | None:
        """The symlink this tree holds at `at`, as `(its path, its target)`,
        or None."""
        if part in (*HERE, ".."):
            return None
        real = self._real(at)
        mode, oid = self.entries.get(real or "", ("", ""))
        if mode != SYMLINK_MODE:
            return None
        if real not in self._targets:
            self._targets[real] = _git_path(git_out(
                [GIT_CAT_FILE, "blob", oid], cwd=self.source.path,
                binary=True))
        return real, self._targets[real]

    def _through(self, walk: _Walk, link: tuple[str, str], ends: tuple,
                 queue: list) -> list:
        """The parts of the symlink's target, to be walked next; none, and
        a problem or a place outside, when it is one hop more than `open()`
        follows, has nothing to lead to, or leaves the assembly."""
        at, target = link
        walk.links.append(link)
        if len(walk.links) > SYMLINK_HOPS:
            walk.problem = (f"it follows too many symlinks at {_spelled(at)}: "
                            f"{TOO_MANY_SYMLINKS}")
            return []
        if not target:
            walk.empty = at
            walk.problem = (f"the symlink {_spelled(at)} has an empty target, "
                            "which leads nowhere")
            return []
        last = not queue
        if _absolute_here(target):
            leads = (f"the symlink {_spelled(at)} leads to "
                     f"{_spelled(target)}, {ON_THIS_MACHINE}")
            if last:
                self._outside(walk, target, f"{leads}, and nothing is there")
            else:
                walk.problem = leads
            return []
        parts = target.split("/")
        return ([(part, at, last, ()) for part in parts[:-1]]
                + [(parts[-1], at, last, ((at, target), *ends))] + queue)

    @staticmethod
    def _outside(walk: _Walk, place: str, missing: str) -> None:
        """`walk` leaves the assembly for `place` on this machine's disk:
        taken where something is there, else `missing` is what stops it.
        Windows may spell a place with backslashes; it is named with
        slashes, as every other path is."""
        walk.outside, walk.landed = True, Path(place).as_posix()
        walk.taken = os.path.exists(place)
        if not walk.taken:
            walk.problem = missing

    def _above(self, walk: _Walk, origin: str, last: bool,
               queue: list) -> list:
        """The queue after a `..` that climbs above the assembly root, from
        the target of the symlink `origin`. Beneath a path the shape writes,
        that is a directory outside the assembly. AT one, it leads into the
        work directory: back into the assembly's own clone by its name, into
        something else `execute` makes there after this check, or onto the
        disk."""
        climbs = f"at the symlink {_spelled(origin)} it climbs above the " \
                 "assembly root"
        work = self.source.work_root
        if not last or work is None:
            walk.problem = climbs
            return []
        names = [part for part, *_ in queue]
        skip = next((n for n, part in enumerate(names) if part not in HERE),
                    len(names))
        name = names[skip] if skip < len(names) else ""
        if self._named(name, self.assembly):
            return queue[skip + 1:]
        made = next((what for made, what in self.beside.items()
                     if self._named(name, made)), None)
        if made:
            walk.problem = (f"{climbs} into "
                            f"{_spelled((work / name).as_posix())}, {made}")
            return []
        # Joined as text, not as a `Path`: a `Path` drops a trailing `/`,
        # which `open()` takes only from a directory.
        place = os.path.join(str(work), *names)
        self._outside(walk, place, f"{climbs}, to "
                      f"{_spelled(Path(place).as_posix())}, where nothing is")
        return []

    def _named(self, name: str, made: str) -> bool:
        """Whether `name` is `made`, as this tree compares names."""
        if not name or not made:
            return False
        return name == made or (self.fold
                                and name.casefold() == made.casefold())

    def _step(self, walk: _Walk, done: list[str], part: str, last: bool,
              more: bool) -> list[str]:
        """`done` after one part that is not a symlink."""
        if part in HERE:
            return done
        if part == "..":
            here = "/".join(done)
            if not self._is_dir(here):
                walk.problem = (f"it passes through {_spelled(here)}, which "
                                "is not a directory in the assembly root")
            return done[:-1]
        done = [*done, part]
        if walk.links:
            walk.problem = self._entered("/".join(done), last, more)
        return done

    def _entered(self, here: str, last: bool, more: bool) -> str | None:
        """What is wrong with going on beneath `here` through a symlink, or
        None: a submodule, a file, or a leg's mount, which only a symlink the
        shape writes AT may enter, since the shape then writes nothing in
        it where something is already there."""
        if not more:
            return None
        real = self._real(here) or ""
        if real in self.mounts and not (last and real in self.legs):
            return self.mounts[real]
        if self._is_file(here):
            return f"it passes through {_spelled(here)}, which is a file"
        return None

    def _arrival(self, done: list[str], link: str,
                 queue: list) -> str | None:
        """None when the destination of the symlink `link` is in this tree,
        a directory where the path goes on beneath it; else where it is
        instead."""
        here = "/".join(done)
        held = self._is_dir(here) if queue else self._has(here)
        return None if held else self._dangling(link, here)

    def _dangling(self, link: str, here: str) -> str:
        """Where the destination `here` of the symlink `link` is, instead of
        in this tree: past what a leg's mount holds, in a leg, dropped, or
        nowhere."""
        lead = (f"the symlink {_spelled(link)} leads to {_spelled(here)}, "
                "which ")
        mount = next((mount for mount in self.legs
                      if self._under(here, mount)), None)
        if mount:
            return (f"{lead}the {self.legs[mount]} leg, mounted at "
                    f"{_spelled(mount)}, does not hold")
        legs = sorted({leg for path, leg in self.gone.items()
                       if self._under(path, here)})
        where = [f"to the {leg} leg" if leg in EXTRACTED_LEGS
                 else f"to `{leg}`" for leg in legs]
        if where:
            return (f"{lead}the plan sends "
                    + (f"{', '.join(where[:-1])} and {where[-1]}"
                       if len(where) > 1 else where[0]))
        return f"{lead}is not in the source tree"

    def _under(self, path: str, top: str) -> bool:
        """Whether `path` is `top` or lies beneath it, as this tree compares
        paths."""
        if self.fold:
            path, top = path.casefold(), top.casefold()
        return f"{path}/".startswith(f"{top}/")

    def _over(self, walk: _Walk) -> str:
        """Why the shape's copy cannot be written where a symlink leads it:
        onto something already there. `place` stops there (#262's
        `copy_in_the_way`), after both legs exist; before #262 it wrote the
        copy over a file, and raised IsADirectoryError on a directory."""
        landed = _spelled(walk.landed)
        is_dir = (os.path.isdir(walk.landed) if walk.outside
                  else self._is_dir(walk.landed))
        what = "a directory" if is_dir else "a file"
        return (f"it lands on {landed}, {what} that is already there, where "
                "the shape's copy cannot be written")


def _work_dir_names(plan: Plan) -> tuple[str, dict[str, str]]:
    """The name of the assembly's clone in `execute`'s work directory, and
    of everything else `execute` makes there after `check` and before the
    shape is written, with what it is: each leg's clone, and the path list
    each leg is extracted with. Nothing where the plan's names are not ones
    `execute` takes: `check` refuses those on its own."""
    try:
        names = plan.names()
    except Refusal:
        return "", {}
    made: dict[str, str] = {}
    for role in EXTRACTED_LEGS:
        made[names[role]] = (f"where `execute` makes the {role} leg's clone "
                             "after this check")
        made[f"{role}-paths.txt"] = (f"where `execute` writes the {role} "
                                     "leg's path list after this check")
    return names["assembly"], made


def _misplaced_script(walk: _Walk) -> str | None:
    """Why a shape script carried through a symlink cannot run where it
    lands, or None.

    Each script looks for the assembly root, and for
    `contracts/repository-naming.yaml`, from the directory above its own
    resolved location (`Path(__file__).resolve().parents[1]`). From two
    directories down, `validate-repository-naming.py` reads the policy from
    the wrong `contracts/`; from the root itself, `bootstrap.py` looks for
    `.git` above the clone. A script whose path is taken is not written
    there at all: its copy goes under `shape/`.
    """
    if (not walk.links or walk.taken
            or not walk.path.startswith(f"{SHAPE_SCRIPTS}/")):
        return None
    where = PurePosixPath(walk.landed).parent
    if len(where.parts) == 1:
        return None
    named = _spelled(where.as_posix()) if where.parts else "the root itself"
    return (f"it lands at {_spelled(walk.landed)}, and the shape's scripts "
            "look for the assembly root, and for "
            "contracts/repository-naming.yaml, from the directory above "
            "their own, so they run only from a directory directly under "
            f"the root, which {named} is not")


def _links_at_a_copy(plan: Plan, tree: list) -> set[str]:
    """Each symlink the plan keeps AT the copy under `shape/` of a path the
    root holds: #262's `plan-root-blocks-shape-copy` names it, the shape's
    copy written THROUGH it, earlier in `_entry_findings`' one list. Asked
    as `_leg_findings` asks it, of a plan whose `legs` it can read, on a
    disk that keeps case and on one that ignores it."""
    if not isinstance(plan.legs, dict):
        return set()
    kept = _kept_in_root(plan.entries, tree)
    named: set[str] = set()
    for fold in (False, True):
        for _, _, copy, group, rows in _shape_blocks(_KeptTree(kept, fold)):
            if group == ("at", copy) and rows[0][1] == SYMLINK_MODE:
                named.add(rows[0][0])
    return named


def _root_symlink_findings(plan: Plan, source: Source,
                           tree: list) -> list[str]:
    """A FINDING for each symlink the plan keeps in the root that a path the
    shape writes runs through and cannot be written through (#178, #183).

    One finding per symlink, naming the first shape path that meets it. A
    symlink no shape path runs through is not this check's business: the
    split keeps it exactly as the source had it. The paths are followed as a
    disk that keeps case does, and again as one that ignores it; what only
    the second refuses says so. `tree` is `Source.tree()`, read once by
    `_entry_findings` for every finding it composes.

    A symlink AT the copy of a path the root holds is #262's to say
    (`_links_at_a_copy`), and is not said again here: one link, one
    finding. The copy is still walked, and a link the walk meets ABOVE it,
    or AT the copy of a path the root holds only through a symlink, is
    this check's, because #262's rule follows no link.
    """
    findings: list[str] = []
    if not any(mode == SYMLINK_MODE for _, mode, _, _ in tree):
        return findings
    seen = _links_at_a_copy(plan, tree)
    for fold in (False, True):
        for walk in _PlannedRoot(plan, source, tree, fold=fold).walks():
            why = walk.problem or _misplaced_script(walk)
            if why is None or walk.links[0][0] in seen:
                continue
            seen.add(walk.links[0][0])
            findings.append(_root_symlink_finding(
                walk, why, _CASE_ASIDE if fold else ""))
    return findings


def _root_symlink_finding(walk: _Walk, why: str, aside: str) -> str:
    """The line `check` prints for a symlink `walk` cannot be written
    through, and what to do.

    A symlink with an empty target is fixed in the source. Both of the
    clones `execute` makes of the source check every path out, wherever the
    plan sends it, and Linux cannot hold a symlink to nothing: there `git
    clone` stops at it ("unable to create symlink") after the leg
    repositories exist. Where `core.symlinks` is false the clone holds a
    plain file instead, so the sentence says only what is true on every
    disk."""
    link, target = walk.links[0]
    fix = (f"Give {_spelled(walk.empty)} a target in the source, or remove "
           "it there, and re-run `plan`: Linux cannot hold a symlink to "
           "nothing, and every clone `execute` makes of the source checks it "
           "out, wherever the plan sends it."
           if walk.empty else
           f"Send {_spelled(link)} to a leg or `drop` it, or change where it "
           "points in the source and re-run `plan`.")
    return (f"FINDING {ROOT_SYMLINK}: the plan keeps {_spelled(link)} in the "
            f"root, a symlink to {_spelled(target)}, and "
            f"{_spelled(walk.path)}, a path the shape writes, runs through "
            f"it{aside}, but {why}. {fix}")


def _checks_out_symlinks(work_root: Path) -> bool:
    """Whether `git` checks a symlink out AS a symlink in a repository made
    in `work_root`, which is where the assembly's clone is made (#183).

    It asks a throwaway repository rather than the configuration alone.
    `git init` writes `core.symlinks = false` into a repository whose
    filesystem cannot hold a symlink, and a global, system or `GIT_CONFIG_*`
    setting can say false on one that can.
    """
    probe = Path(tempfile.mkdtemp(prefix="symlinks-probe-", dir=work_root))
    try:
        run(["git", "init", "-q", str(probe)])
        answer = subprocess.run(
            ["git", "config", "--type=bool", "--get", "core.symlinks"],
            cwd=str(probe), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    return answer.stdout.strip() != "false"


def _refuse_symlinks_checked_out_as_files(plan: Plan, source: Source,
                                          work_root: Path) -> None:
    """Refuse, before any leg exists, a plan whose shape files are written
    BENEATH a symlink the plan keeps, where `git` would check that symlink
    out as a plain file (#183).

    `core.symlinks=false` is Git for Windows' default, and what `git init`
    writes on a filesystem that cannot hold a symlink. The assembly's clone
    would then hold the link as a file, and the materializer cannot make a
    directory where a file is. It used to die there in a traceback after
    both legs were pushed. A symlink AT a shape path is unaffected: as a
    file it is still taken, and the shape's copy goes beside it. The probe is
    made only when a plan needs it, so an adoption with no such link runs
    exactly as before.
    """
    tree = source.tree()
    if not any(mode == SYMLINK_MODE for _, mode, _, _ in tree):
        return
    # A case twin is met only by the walk that ignores case, and is named
    # with `check`'s own aside: on a disk that keeps case the shape path
    # does not run through it at all.
    beneath = [(walk, _CASE_ASIDE if fold else "") for fold in (False, True)
               for walk in _PlannedRoot(plan, source, tree, fold=fold).walks()
               if walk.links
               and walk.links[0][0].casefold() != walk.path.casefold()]
    if not beneath or _checks_out_symlinks(work_root):
        return
    walk, aside = beneath[0]
    link, target = walk.links[0]
    raise Refusal(
        "adopt-symlinks-off",
        f"the plan keeps {_spelled(link)} in the root, a symlink to "
        f"{_spelled(target)}, and {_spelled(walk.path)}, a path the shape "
        f"writes, runs through it{aside}, but `git` here checks a symlink out "
        "as a plain file: "
        f"`core.symlinks` is false for a repository made in {work_root}. The "
        f"assembly's clone would hold {_spelled(link)} as a file, and nothing "
        "can be written beneath a file.",
        "Remediation: no leg repository was created and nothing was pushed. "
        "Run `execute` where `git` checks a symlink out as a symlink -- "
        "`core.symlinks` true, on a filesystem that can hold one -- or send "
        f"{_spelled(link)} to a leg or `drop` it in the plan and run `check` "
        "again.")


def cmd_check(args) -> int:
    plan = Plan.load(Path(args.plan))
    work_root = _work_root(args)
    source = plan.open_source(args.source, work_root)
    naming = NamingPolicy.load(NAMING_POLICY)
    findings: list[str] = []
    # FIRST, because it is said where work starts; it is never one of the
    # findings below and never moves this command's exit code.
    _print_triad_advisory(source.path,
                          plan.source_commit or source.commit)

    if plan.source_commit and source.commit != plan.source_commit:
        findings.append(
            f"FINDING plan-stale: the plan was written against "
            f"{plan.source_commit[:12]} but {_spelled(source.branch)} is now "
            f"at {source.commit[:12]}. Re-run `plan`: a coverage check "
            "against a tree that has moved proves nothing about the tree that "
            "will be split.")

    entry_findings, remediation, notes = _entry_findings(plan, source)
    findings.extend(entry_findings)

    names = plan.names()
    pins = set(plan.pins)
    try:
        _check_names(naming, names, pins)
        for role, name in names.items():
            found = naming.classify(name, role, pins)
            print(f"  {role:<9} {name:<28} {found.family}"
                  + (f"/{found.role}" if found.role else ""))
    except Refusal as exc:
        findings.append(f"FINDING {exc.code}: {exc.detail}")

    _print_what_will_happen(plan, source, names,
                            naming.topic_for(plan.project_id))

    seeded = seeded_legs(assigned_paths(plan.entries))
    for line in seeding_warnings(seeded, plan.allowed_empty_legs()):
        print(line)
    for line in plan.seeding_record_disagreements(seeded):
        print(line)
    for line in notes:
        print(line)

    for line in [*findings, *remediation]:
        print(line, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} finding(s) in {plan.path}", file=sys.stderr)
        return 1
    print("\nplan ok")
    return 0


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


def _require_filter_repo() -> None:
    if shutil.which("git-filter-repo") is None:
        probe = subprocess.run(["git", "filter-repo", "--version"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=False)
        if probe.returncode != 0:
            raise Refusal(
                "filter-repo-missing",
                "`git filter-repo` is not on PATH, and history extraction "
                "will not be attempted without it",
                FILTER_REPO_HINT)


def _confirm(args, plan: Plan, names: dict) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise Refusal(
            "adopt-unconfirmed",
            "this is not an interactive terminal and --yes was not passed, so "
            "there is nobody to ask. Creating two repositories and rewriting a "
            "third's default branch by pull request is not something to do on "
            "an assumption.",
            "Remediation: run it where a human can answer, or pass --yes once "
            "they have read the plan and the follow-ups.")
    print(f"\nThis creates {names['spec']} and {names['code']} and pushes a "
          f"split branch to {names['assembly']}.")
    try:
        answer = input("Type yes to proceed: ").strip().lower()
    except EOFError:
        # A stream that claims to be a terminal and then ends is a place
        # nobody can be asked either: on Windows an inherited console handle
        # reports isatty() True even under CI, where the isatty() check above
        # cannot catch it. Same refusal, same wording, same exit code.
        raise Refusal(
            "adopt-unconfirmed",
            "this is not an interactive terminal and --yes was not passed, so "
            "there is nobody to ask. Creating two repositories and rewriting a "
            "third's default branch by pull request is not something to do on "
            "an assumption.",
            "Remediation: run it where a human can answer, or pass --yes once "
            "they have read the plan and the follow-ups.")
    if answer != "yes":
        raise Refusal("adopt-declined", f"answered {answer!r}, not 'yes'",
                      "Remediation: nothing was created. Re-run when ready.")


def _refuse_an_unrunnable_plan(plan: Plan, source: Source) -> None:
    """The two states a plan can be in that must not be executed.

    An unanswered question is never an implicit `root`, and a plan written
    against a tree that has since moved proves nothing about the tree that
    would be split — which is how a path goes missing.
    """
    unresolved = [e for e in plan.entries if e.get("leg") is None]
    if unresolved:
        raise Refusal(
            "plan-unresolved",
            f"{len(unresolved)} path(s) still have `leg: null`: "
            + _listed([str(e.get("path")) for e in unresolved[:8]]),
            "Remediation: answer each entry's `question:` by setting `leg:` "
            "and adding a `resolution:` line, then run `check`. An unanswered "
            "question is never an implicit `root`.")
    if plan.source_commit and source.commit != plan.source_commit:
        raise Refusal(
            "plan-stale",
            f"the plan was written against {plan.source_commit[:12]} and "
            f"{_spelled(source.branch)} is now at {source.commit[:12]}",
            "Remediation: re-run `plan`, re-answer anything new, then "
            "`check`. Splitting a tree the plan has not seen is how a path "
            "goes missing.")


def _flush_stdout() -> None:
    """Flush stdout before a failure is written to stderr (#171, #177, #188).

    `execute` announces each leg repository, each pushed leg and the split on
    stdout. Piped, stdout is block-buffered and stderr is not, so without
    this a log that merges the two (`> log 2>&1`) shows the failure BEFORE the
    lines it is about. A stdout nobody reads any more, such as a closed pipe,
    must not turn the report into a BrokenPipeError, so that error is
    swallowed: the report on stderr is what the human needs.
    """
    with contextlib.suppress(OSError):
        sys.stdout.flush()


def _create_leg_remotes(plan: Plan, names: dict, repositories: dict,
                        urls: dict, tracking: str, local: bool) -> None:
    """(a) The two NEW repositories. The assembly root is never created here."""
    print("\ncreating the leg repositories")
    if local:
        Path(urls["spec"]).parent.mkdir(parents=True, exist_ok=True)
    for role in ("spec", "code"):
        if not local:
            run(["gh", "repo", "create", repositories[role],
                 f"--{plan.get('visibility', 'private')}", "--description",
                 f"{names['assembly']} — {role} leg, extracted from "
                 f"{repositories['assembly']} with history"])
            print(f"  gh    {repositories[role]}")
            continue
        bare = Path(urls[role])
        if bare.exists():
            raise Refusal(
                "leg-remote-exists", f"{bare} already exists",
                "Remediation: choose an empty --local-remote-dir. There is no "
                "--force: re-running over a live leg is not an adoption.")
        run(["git", "init", "-q", "--bare", "-b", tracking, str(bare)])
        print(f"  bare  {bare}")

    # A private or internal leg is unreadable to the `validate` workflow's
    # default GITHUB_TOKEN — the defect on the first real adoption
    # (MedxSoft/MedxEHR #7).
    visibility = plan.get("visibility", "private")
    if not local and visibility in ("private", "internal"):
        print(f"NOTE {repositories['spec']} and {repositories['code']} are "
              f"{visibility}: give {repositories['assembly']} a way to "
              "read them — a GitHub App (SHAPE_LEGS_APP_ID + "
              "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
              "PAT (contents:read on the legs, fallback) — or the `validate` "
              "check cannot check them out.")
        hint = free_plan_secret_hint(
            plan.get("org", ""), repositories["assembly"],
            f"{repositories['spec']} and {repositories['code']} are")
        if hint:
            print(hint)


def _extract_leg(role: str, source: Source, work: Path, paths: list[str],
                 listing: Path, branch: str, url: str, tracking: str,
                 repository: str) -> tuple[str, str]:
    """(b) One leg, with its history: clone, filter, push. Returns commit+digest.

    A FRESH clone every time, because `git filter-repo` rewrites the whole
    object graph and is documented to want one; the branch is reset to the
    PLAN's commit rather than to whatever the default branch is now, so the
    extraction and the coverage check are about the same tree.
    """
    run(["git", *FILE_PROTOCOL, "clone", "-q", str(source.path), str(work)])
    run(["git", "checkout", "-q", "-B", branch, source.commit], cwd=work)
    # LF, on every platform. `git filter-repo --paths-from-file` matches a
    # line against a path, and a CRLF-terminated line ends in a character no
    # path contains - so on Windows every pattern would match nothing, the
    # filter would succeed, and the leg would be pushed EMPTY. A silent
    # extraction of nothing is the worst shape this failure could take.
    # `literal:` on every line (#196): filter-repo reads a line starting with
    # `#` as a comment and one starting with `regex:`, `glob:` or `literal:`
    # as that directive, so a source file named `#notes.md` was left out of
    # its leg after both legs existed. The prefix takes the rest of the line
    # as it stands; what no line can carry, `entry_path_problem` refuses.
    # And byte-exact: a path that is not UTF-8 is written as the bytes
    # git records, where `write_lf` raised after both legs existed.
    write_paths_listing(listing, [f"literal:{path}" for path in paths])
    run(["git", "filter-repo", "--paths-from-file", str(listing), "--force"],
        cwd=work)
    head = git_out(["rev-parse", "HEAD"], cwd=work).lower()
    try:
        run(["git", "push", "-q", url, f"HEAD:refs/heads/{tracking}"], cwd=work)
    except CommandFailed as exc:
        print(exc.loudly(f"pushing the {role} leg"), file=sys.stderr)
        print(RULESET_HINT.format(work=work, repo=repository, role=role),
              file=sys.stderr)
        raise
    count = git_out(["rev-list", "--count", "HEAD"], cwd=work)
    print(f"  {role:<5} {len(paths):>3} path(s) -> {head[:12]} "
          f"({count} commits kept) -> {url}")
    return head, tree_digest(work, head)


def _seed_leg(role: str, work: Path, values: dict, branch: str, url: str,
              tracking: str, repository: str, display: str) -> tuple[str, str]:
    """(b′) A leg with NO extracted path: seeded from the shape's template.

    The same bytes `scaffold-project.py` writes for a new project's leg, as
    ONE initial commit with the identity this invocation carries. It is not an
    extraction and does not pretend to be: the commit message says the leg was
    seeded and why, so a reader of that repository's own history is never left
    wondering which commits of the adopted repository went missing.

    `branch` is accepted and ignored on purpose — a seeded leg has no branch of
    the source to reset to. `tracking` is the branch it is pushed to, exactly
    as an extracted leg is.

    THE TEMPLATE'S FILES ARE STAGED BY NAME (#175). `git add -A` honours the
    operator's own excludes, and a machine whose global ones say `.*` or `src/`
    committed and pushed a seeded leg without its `.gitignore` or its
    `src/.gitkeep`, files the template ships and the leg needs. So the list
    `copy_tree` returns goes to `git_init_commit`, which forces exactly those
    paths past an exclude rule; see `shape_materialize.stage_written`. The
    split's commit is another path (`_commit_the_split`, #167), not touched.
    """
    del branch
    written = copy_tree(SHAPE_ROOT / SEED_TEMPLATE[role], work, values)
    commit = git_init_commit(
        work,
        f"Seed the {role} leg of {display}\n\n"
        f"No path of {display} was assigned to the {role} leg by the adoption "
        f"plan, so this leg is SEEDED from {SHAPE_REPOSITORY}'s "
        f"{SEED_TEMPLATE[role]}/ rather than extracted with `git filter-repo`: "
        "a filter over an empty path list yields an empty HISTORY, which is "
        "not an empty repository.\n\nIt carries no history from the adopted "
        "repository because there was none to carry. The assembly root mounts "
        "and pins it exactly as it does the extracted leg.\n",
        tracking, written).lower()
    try:
        run(["git", "push", "-q", url, f"HEAD:refs/heads/{tracking}"], cwd=work)
    except CommandFailed as exc:
        print(exc.loudly(f"pushing the seeded {role} leg"), file=sys.stderr)
        print(RULESET_HINT.format(work=work, repo=repository, role=role),
              file=sys.stderr)
        raise
    print(f"  {role:<5}   0 path(s) -> {commit[:12]} (SEEDED from "
          f"{SEED_TEMPLATE[role]}/) -> {url}")
    return commit, tree_digest(work, commit)


#: What an index entry's mode, an octal number, says holds a path, for
#: `adopt-mount-occupied`. Any other mode is a file's.
INDEX_ENTRY_KINDS = {0o160000: "a submodule", 0o120000: "a symlink"}

#: Both mount refusals come at the same point of the run, so they say the
#: same thing about what exists and how to start again. The work directory is
#: named because the refused run leaves its clones of both legs in it, and
#: `_build_the_legs` clones into `<work>/<name>`: a re-run over them cannot,
#: and has by then made two new, empty leg repositories.
MOUNT_REMEDIATION = (
    "Remediation: both leg repositories were made and pushed before the "
    "mount, and nothing was committed to the source or pushed to it. Change "
    "`legs.spec_path` or `legs.code_path`, or the `leg:` of the entry in the "
    "way, so that the legs mount at two different paths that nothing the "
    "plan keeps in the root holds, with no file, symlink or submodule it "
    "keeps there on the way to them. Then run `execute` again with fresh "
    "leg repositories (delete the two this run made, or choose an empty "
    "`--local-remote-dir`: a leg that already exists meets "
    "`leg-remote-exists`, or a `gh repo create` that finds the name taken) "
    "and an empty `--work-dir`, or none: a `--work-dir` this run was given "
    "still holds its clones of both legs, and the next run cannot clone "
    "into them.")

#: How the index is described in the refusals below.
ASSEMBLY_INDEX = "the assembly's index"


def _index_entries(assembly: Path,
                   pathspecs: list[str]) -> list[tuple[str, str]]:
    """`(kind, path)` of every index entry the `pathspecs` select.

    A pathspec selects the entry AT it and every entry under it, which is why
    the caller compares paths. Always `--icase-pathspecs`, whatever this
    disk's `core.ignorecase` says: the assembly is cloned on macOS and Windows
    too, where `Spec` and `spec` are ONE path, so it is refused on every disk,
    as #169 refuses case-only twins of the two leg paths. `-z`, for a path
    git would otherwise quote. A name that is not UTF-8 keeps each byte as a
    surrogate, as `Source.tree` keeps it, so the refusal spells the byte 0xFF
    `\\xff`, as every other finding does (#212). Decoded with `replace`,
    `a<0xFF>` and `a<0xFE>` both read `a<U+FFFD>`.
    """
    raw = git_out(["--icase-pathspecs", "ls-files", "-s", "-z", "--",
                   *pathspecs], cwd=assembly, binary=True)
    entries = []
    for record in raw.split(b"\x00"):
        if record:
            head, _, name = record.partition(b"\t")
            kind = INDEX_ENTRY_KINDS.get(int(head.split()[0], 8), "a file")
            entries.append((kind, name.decode("utf-8",
                                              "surrogateescape")))
    return entries


def _entry_named(entry: tuple[str, str]) -> str:
    """The index entry and its kind. Its name is a source name the plan kept
    in the root, so it is `_spelled`, as every path a finding names (#212)."""
    kind, name = entry
    return f"{_spelled(name)} ({kind})"


def _occupied(detail: str) -> Refusal:
    return Refusal("adopt-mount-occupied", detail, MOUNT_REMEDIATION)


def _refusal_for_held(path: str, held: list[tuple[str, str]]) -> Refusal:
    """The refusal for the entries AT or UNDER the mount path. An entry at it
    is named first; with only entries under it, the path is a directory the
    root keeps files in, and the first of them is named."""
    at_it = [entry for entry in held if entry[1].casefold() == path.casefold()]
    named = _entry_named((at_it or held)[0])
    more = f" and {len(held) - 1} more" if len(held) > 1 else ""
    where = (f"the leg mount path {path}" if at_it
             else f"paths under {path}, the leg mount path")
    return _occupied(f"{ASSEMBLY_INDEX} already holds {where}: {named}{more}")


def _refuse_an_unmountable_path(assembly: Path, path: str) -> None:
    """Refuse a mount path `git submodule add --force` would misuse (#174).

    `--force` is what gets a mount past a source `.gitignore` (see the loop
    in `_mount_the_legs`), and it also turns off two of git's own refusals.
    Each is made here instead, BEFORE the add, as a named refusal, and the
    index is asked a third question that git answers only in a raw failure:

    - A path the index already holds. Without `--force` git refuses any
      entry there; with it, only one that is NOT a gitlink, and when a
      repository is already checked out at the path it is REUSED, not
      cloned. With `spec_path` equal to `code_path` that repository is the
      spec leg, mounted a moment before: the code leg was never mounted and
      the run said `adoption verified`, where without `--force` it died at
      the second add. So ANY entry at the path, or under it, is refused
      here, with what holds it. The question is asked case-insensitively on
      every disk (`_index_entries`), so a root-kept `SPEC/notes.md` beside a
      `spec` mount is refused on Linux as it would be on a macOS clone.
    - git's own `git add --dry-run` of the path, made before it clones the
      leg. That is what refuses a path beyond a symlink or inside a
      submodule; without it, `legs/spec` under a root-kept `legs ->
      /elsewhere` had the leg cloned THROUGH the link, outside the work
      directory, before git refused. The dry run is made here with `-f`,
      so an ignore rule still passes it.
    - A FILE on the way: `docs` kept in the root as a file, with `spec_path:
      docs/spec`. The dry run passes it, and git dies after both legs are
      pushed, "could not create leading directories", with or without
      `--force`. An entry that is exactly a proper prefix of the path is
      refused whatever its kind; one that only has paths under it (a
      root-kept `docs/`) is a directory, and a mount beside its files is
      what `docs/spec` asks for.

    Every case above is the plan's to refuse, at `check` and in `execute`
    before any leg exists: equal and nested leg paths by #169, and a mount
    path that a path the plan keeps in the root is, holds or lies beyond --
    a file, a symlink, a submodule, a case-only twin -- by #172
    (`plan-leg-path-collides`). So this guard is defence in depth: the same
    answer where the mount is made, for a run that got here anyway, after
    both legs were pushed.
    """
    parts = path.split("/")
    on_the_way = {"/".join(parts[:end]).casefold()
                  for end in range(1, len(parts))}
    entries = _index_entries(assembly, [path, *sorted(on_the_way)])
    wanted = path.casefold()
    held = [entry for entry in entries
            if entry[1].casefold() == wanted
            or entry[1].casefold().startswith(wanted + "/")]
    if held:
        raise _refusal_for_held(path, held)
    try:
        run(["git", "add", "--dry-run", "--ignore-missing", "-f",
             "--no-warn-embedded-repo", "--", path], cwd=assembly)
    except CommandFailed as exc:
        raise Refusal(
            "adopt-mount-unaddable",
            f"git will not add the leg mount path {path}: {exc.output}",
            MOUNT_REMEDIATION) from exc
    for entry in entries:
        if entry[1].casefold() in on_the_way:
            raise _occupied(f"{ASSEMBLY_INDEX} holds {_entry_named(entry)} "
                            f"where the leg mount path {path} needs a "
                            "directory")


def _mount_the_legs(assembly: Path, work_root: Path, names: dict, urls: dict,
                    paths_for: dict, spec_path: str, code_path: str) -> None:
    """(c, first half) `git rm` what moved, then mount the two legs.

    The submodule is added from the LEG'S WORKING TREE and its recorded URL is
    then rewritten to the canonical remote, exactly as the scaffold does: the
    adoption never depends on a push having propagated.
    """
    removed = sorted((p.rstrip("/") for p in (paths_for["spec"]
                                              + paths_for["code"]
                                              + paths_for["drop"])),
                     key=lambda p: (p != GITMODULES, p))
    # `--literal-pathspecs` (#196): after `--` a path is no option, but it is
    # still a pathspec, where `*` and `?` are wildcards and a leading `:` is
    # magic -- `git rm -- ':!keep.md'` removes every other path in the tree.
    for path in removed:
        run(["git", "--literal-pathspecs", "rm", "-r", "-q", "--", path],
            cwd=assembly)
    # The plan moved (or dropped) the source's own .gitmodules, so its deletion
    # is staged, and `git submodule add` refuses to write into a file the index
    # says is going away. Give the assembly a fresh, EMPTY, staged one for its
    # two mounts: `-f` because a source `.gitignore` such as `.*` would hide it
    # from `git add`, and only in this case, so a source with no submodules is
    # mounted exactly as it was before. It is removed FIRST above because
    # `git rm` of a submodule edits the file that registers it. #166 ruled
    # that the assembly root keeps no submodule of the source's: a plan that
    # keeps `.gitmodules` or a gitlink here, or splits one from its
    # registration, is a `check` finding, and `execute` refuses every
    # finding of `check` before this runs (#168).
    # Appending the mounts to a `.gitmodules` left here, rather than
    # replacing it, is MOUNT DEFENCE IN DEPTH for a plan that slipped past
    # both, not a shape a plan may choose: the verification fails such a
    # split, on that file's bytes (`adopt-lost`) and on every submodule of
    # the source's the root keeps (`adopt-root-submodule`, #165).
    if GITMODULES in removed:
        write_lf(assembly / GITMODULES, "")
        run(["git", "add", "-f", "--", GITMODULES], cwd=assembly)
    for role, path in (("spec", spec_path), ("code", code_path)):
        # `--force`, git's documented way past an ignore rule, for the reason
        # the fresh `.gitmodules` above is added with `-f` (#162): a source
        # `.gitignore` of `*` + `!.gitignore`, or one naming `spec` or `code`,
        # matches the MOUNT PATH, and git refused the mount AFTER both legs
        # were pushed, so a corrected re-run met `leg-remote-exists` (#174).
        # That source is a legitimate one to adopt, not one to refuse, and a
        # gitlink once added is tracked, so the rule never touches it again.
        # `--force` also lets through a path the index holds with a gitlink,
        # reusing the repository there, and skips git's check for a path
        # beyond a symlink: `_refuse_an_unmountable_path` refuses both first.
        # With that, the two paths are distinct, and the assembly was cloned
        # with NO TEMPLATE (`_commit_the_split`, #243), so `.git/modules`
        # holds nothing before the first mount and only that mount's store
        # at the second: no `.git/modules/<name>` is there for `--force` to
        # reactivate. (An operator's template could plant one, and the mount
        # then took the stranger's commit.) Whatever else put a different
        # commit at a mount, `_verify` compares each gitlink with the commit
        # pushed to its leg (`adopt-mount-commit`). A newer git's renaming of
        # a name already in use can only meet a `.gitmodules` the plan KEPT
        # here, which verification never passes (#165).
        _refuse_an_unmountable_path(assembly, path)
        run(["git", *FILE_PROTOCOL, "submodule", "add", "--force", "-q",
             str(work_root / names[role]), path], cwd=assembly)
        run(["git", GIT_CONFIG, "-f", GITMODULES, f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)


def _checked_plan_values(plan: Plan) -> tuple[str, str, str, str]:
    """The four plan values that reach a `git` command line as arguments:
    `(spec_path, code_path, branch, tracking)`.

    Split out of `cmd_execute` for #138, in the order the refusals came in.
    """
    spec_leg, code_leg = _plan_leg_paths(plan)
    # Before ANY leg exists: `check` finds a bad path and `execute` refuses it
    # on its own account, not because `check` happened to be run first (#169).
    _refuse_bad_leg_paths("plan-bad-leg-path", spec_leg, code_leg)
    spec_path = checked_value(*spec_leg)
    code_path = checked_value(*code_leg)
    branch = checked_value("adopt_branch", plan.get("adopt_branch",
                                                    ADOPT_BRANCH))
    tracking = checked_value("tracking_branch",
                             plan.get("tracking_branch", "main"))
    return spec_path, code_path, branch, tracking


def _repository_urls(args, plan: Plan, names: dict,
                     source: Source) -> tuple[bool, dict, dict]:
    """Where the three repositories are: `(local, repositories, urls)`.

    Split out of `cmd_execute` for #138. The assembly root's URL is the SOURCE
    itself under `--local-remote-dir`, because an in-place adoption pushes its
    split branch back to the repository it read.
    """
    org = checked_value("org", plan.get("org"))
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    return (args.local_remote_dir is not None, repositories,
            _remote_urls(org, names, args.local_remote_dir, source))


def _remote_urls(org: str, names: dict, local_remote_dir: Path | None,
                 source: Source) -> dict:
    """The url of each of the three repositories, by role: what `execute`
    pushes to, and what a relative submodule url kept in a leg is resolved
    from (#190), which `check` asks with no `local_remote_dir`."""
    if local_remote_dir is None:
        return {role: f"https://github.com/{org}/{name}.git"
                for role, name in names.items()}
    # NOT created yet: nothing exists on disk until the human has said yes,
    # so a refused run leaves the directory it would have used absent rather
    # than empty.
    remote_dir = local_remote_dir.resolve()
    urls = {role: str(remote_dir / f"{name}.git")
            for role, name in names.items()}
    urls["assembly"] = str(source.path)
    return urls


def _leg_paths(plan: Plan) -> dict:
    """Every plan entry's path, by the leg it was assigned to.

    COLLECTED, NOT JUDGED (#196). An entry's path is a fact of the source,
    not an option, and what `execute` cannot hand to `git` is
    `entry_path_problem`'s to say: `check`'s finding `plan-unsafe-path`,
    which `_refuse_what_check_finds` refuses on the next line of
    `cmd_execute`, before any of these paths is used and before any leg
    exists. Judging them here as well would be a second refusal, composed
    apart from `check`'s list and said before it. Split out of `cmd_execute`
    for #138.
    """
    return {leg: [str(e.get("path"))
                  for e in plan.entries if str(e.get("leg")) == leg]
            for leg in LEG_VALUES}


#: How many of `check`'s findings the one refusal below spells out; the rest
#: are a count, as `plan-unresolved` names eight paths and not every one.
REFUSED_FINDINGS_SHOWN = 8


def _refuse_what_check_finds(plan: Plan, source: Source,
                             local_remote_dir: Path | None = None) -> None:
    """Refuse a plan `check` rejects, BEFORE a leg repository exists (#168).

    Of `check`'s findings, `execute` used to refuse only `plan-unresolved`,
    `plan-stale` and the naming findings (`_check_names`). A plan `check`
    rejected for any other reason -- `plan-uncovered`, `plan-bad-leg`,
    `plan-covered-twice`, `plan-duplicate-path`, `plan-empty-entry` -- went on
    into `_create_leg_remotes`, which made both legs. As reproduced for #168
    on main at 7f84ca4, it then ended one of three ways:

    - `plan-uncovered` and `plan-bad-leg`, on a source with no submodule: the
      run VERIFIED and exited 0, the uncovered paths, or the paths whose
      `leg:` is not one of the four words, left in the assembly root;
    - `plan-covered-twice`, `plan-duplicate-path` and `plan-empty-entry`: the
      run died at `git rm` of the offending entry, after both legs were
      pushed;
    - a source with a submodule, #168's three cases (the submodule's entry
      deleted; the submodule's entry, or `.gitmodules`, given a `leg:` that is
      not one of the four words): the verification failed as `adopt-lost`.

    In every one the legs existed afterwards, so the corrected plan could not
    make them again: it met `leg-remote-exists` under `--local-remote-dir`,
    and without it asked `gh repo create` for names the first run had already
    taken. There is no `--force`, deliberately. AGENTS.md step 4 has a human
    say yes after `check`, but `execute` is the one gate that cannot be
    skipped, so it says no to the same findings.

    THE FINDINGS ARE `check`'S OWN: `_entry_findings`, the one list `check`
    prints, so the two commands cannot disagree about what a plan covers, or
    about a symlink the plan keeps in the root and the shape writes through
    (#178) -- but where such a link, AT a shape path, leads out of the
    assembly: whether anything is there is asked of the disk again here,
    before any leg exists, and a climb from this run's own work directory
    (#183). The refusal's code is the FIRST finding's own (`plan-uncovered`,
    ...); its detail is every finding as `check` prints it, capped at
    `REFUSED_FINDINGS_SHOWN` with an "and N more" tail; its remediation is
    this one, then whatever `check` prints after its findings -- #166's
    submodule remediation, when one of them is a submodule problem. A leg
    mount path that overlaps a path the root holds is one of them,
    `plan-leg-path-collides` from `_leg_findings` (#172): before #172 it was
    refused only by `git`, after both legs were pushed, or not at all.

    THE ORDER IS PART OF THE FIX. This runs AFTER `_refuse_an_unrunnable_plan`:
    `_leg_findings` also reports `plan-unresolved`, which that function has
    already refused in its own words, and a plan written against a tree that
    has since moved is `plan-stale`, not whatever its stale coverage happens
    to lack. A VALUE THAT IS AN OPTION AND A PATH THAT IS A FACT ARE TWO
    TESTS (#196). A leg's mount path, a branch, a repository name and the
    organisation are options: `checked_value` refuses them as `unsafe-value`
    in `_checked_plan_values` and `_repository_urls`, before this runs. An
    entry's path is a fact of the source, judged by `entry_path_problem` as
    `check`'s own finding `plan-unsafe-path`, which `_entry_findings` lists
    FIRST: a path that is a `git` option is refused as that, and never as the
    uncovered file it also leaves. `_leg_paths` collects the entries' paths
    without judging them, and nothing uses one before this has run. It runs
    BEFORE `_refuse_unconsented_seeding`,
    `_confirm` and `_create_leg_remotes`, so no leg repository is created and
    nothing is pushed until every refusal has passed. (`_work_root` has
    already made the work directory and an `org/repo` source has already been
    cloned into it: they come first, and neither is a leg.)

    ONE LIST. While #168 and #166 were both open, each composed its own
    findings, so that the two branches would not edit the same functions;
    #166 refused its submodule problems in `_refuse_an_unrunnable_plan`.
    With both merged, `check` and this function read `_entry_findings` and
    nothing else, and `_refuse_an_unrunnable_plan` is back to its two
    states: a plan `check` rejects as uncovered and split is refused for
    both at once, and a submodule problem is refused here like any other,
    after the entries' paths, which are the first of these findings.

    BUT FROM THE REMOTES THIS RUN WOULD CREATE (#190). A relative submodule
    url kept in a leg is resolved from that leg's remote, and under
    `local_remote_dir` that is a bare repository `check` cannot know of: such
    a finding is this run's own, and the refusal says so. A url `check` finds
    from GitHub's remotes may name the same repository from these, and one it
    passes may not.
    """
    findings, remediation, _ = _entry_findings(plan, source, local_remote_dir)
    if not findings:
        return
    # `FINDING <code>: <detail>` is the one shape both functions write.
    code = findings[0].split()[1].rstrip(":")
    lines = [f"{len(findings)} finding(s) in {plan.path}, as `check` prints "
             f"them{_as_resolved_here(findings, local_remote_dir)}:"]
    lines += [f"  {finding}" for finding in findings[:REFUSED_FINDINGS_SHOWN]]
    if len(findings) > REFUSED_FINDINGS_SHOWN:
        lines.append(f"  and {len(findings) - REFUSED_FINDINGS_SHOWN} more")
    raise Refusal(
        code, "\n".join(lines), "\n".join([
            "Remediation: no leg repository was created and nothing was "
            "pushed. Correct the plan -- answer each entry's `leg:`, cover "
            "every source path exactly once, mount neither leg over a path "
            "the assembly root holds, and keep in the root no path where the "
            "shape writes a file or its copy -- and run `check` until it "
            "prints `plan ok`, then run `execute` again. A leg made from a "
            "plan `check` rejects is one the corrected plan cannot make "
            "again: under `--local-remote-dir` it meets `leg-remote-exists`.",
            *remediation]))


def _as_resolved_here(findings: list[str],
                      local_remote_dir: Path | None) -> str:
    """What the refusal's first line adds when a finding in it is not one
    `check` prints: a relative url resolved from `local_remote_dir`'s
    remotes, where `check` resolves it from GitHub's. Nothing otherwise."""
    if local_remote_dir is None or not any(
            finding.startswith(f"FINDING {RELATIVE_URL}:")
            for finding in findings):
        return ""
    return (", but with each relative submodule url resolved from the leg "
            "remotes this run would create under --local-remote-dir, where "
            "`check` resolves it from GitHub's")


def _refuse_unconsented_seeding(args, plan: Plan, seeded: list) -> None:
    """A leg with no path is SEEDED, and seeding takes a human's word.

    Split out of `cmd_execute` for #138. `seeded` is derived from the ENTRIES,
    never from the plan's own `seeding:` record: the entries are what the
    split is actually made of.
    """
    allowed = plan.allowed_empty_legs() | set(args.allow_empty_leg or [])
    unconsented = [role for role in seeded if role not in allowed]
    if unconsented:
        raise Refusal(
            "adopt-empty-leg-unconsented",
            "no path is assigned to the "
            + " and ".join(f"{role} leg" for role in unconsented)
            + ", so it would be SEEDED from "
            + " and ".join(f"{SEED_TEMPLATE[role]}/" for role in unconsented)
            + " instead of extracted, and no `--allow-empty-leg` says that is "
            "intended",
            "Remediation: a repository that genuinely has no "
            + "/".join(unconsented) + " yet is adopted with "
            + " ".join(f"--allow-empty-leg {role}" for role in unconsented)
            + " — on this command, or recorded in the plan by re-running "
            "`plan` with the same flag. A plan that lost its "
            + "/".join(unconsented) + " paths to a bad edit looks identical "
            "from here, which is why this is a human's word and not an "
            "inference.")


def _build_the_legs(source: Source, names: dict, repositories: dict,
                    urls: dict, values: dict, work_root: Path,
                    paths_for: dict, seeded: list, branch: str,
                    tracking: str) -> tuple[dict, dict] | None:
    """(b) Each leg, extracted with its history or seeded from the template.

    Returns `(leg_commits, leg_digests)`, or None when a `git` or `gh` command
    failed — `run` has already said which and why. Split out of `cmd_execute`
    for #138.
    """
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role in EXTRACTED_LEGS:
        try:
            if role in seeded:
                leg_commits[role], leg_digests[role] = _seed_leg(
                    role, work_root / names[role], values, branch, urls[role],
                    tracking, repositories[role], names["assembly"])
            else:
                leg_commits[role], leg_digests[role] = _extract_leg(
                    role, source, work_root / names[role], paths_for[role],
                    work_root / f"{role}-paths.txt", branch, urls[role],
                    tracking, repositories[role])
        except CommandFailed:
            return None
    return leg_commits, leg_digests


def _pull_request_command(repositories: dict, names: dict, tracking: str,
                          branch: str, message: str) -> list[str]:
    """The `gh pr create` that opens the split's pull request. It carries its
    own title and body, so it runs with no terminal to prompt on: this is what
    `_open_the_pull_request` runs, and what `_open_it_by_hand` prints (#304)."""
    return ["gh", "pr", "create", "--repo", repositories["assembly"],
            "--base", tracking, "--head", branch,
            "--title", f"Adopt the three-repository shape: "
                       f"{names['spec']} and {names['code']}",
            "--body", message]


def _open_the_pull_request(repositories: dict, names: dict, tracking: str,
                           branch: str, message: str) -> bool:
    """(c′) The pull request, because these organisations are pull-request
    only.

    Returns False when `gh` refused, having printed why. The branch IS pushed
    by the time this runs, so the exit is never "start again". The command
    that finishes the job by hand is `_open_it_by_hand`'s, which the caller
    prints AFTER the verification and only once it has passed (#304): until
    then nothing says the split is the one to open a pull request for. Split
    out of `cmd_execute` for #138.
    """
    try:
        url = run(_pull_request_command(repositories, names, tracking, branch,
                                        message))
        print(f"  pull request {url}")
    except CommandFailed as exc:
        print(exc.loudly("opening the pull request"), file=sys.stderr)
        return False
    return True


def _open_it_by_hand(repositories: dict, names: dict, tracking: str,
                     branch: str, message: str, passed: bool) -> None:
    """What a refused `gh pr create` leaves to do, said once `execute` knows
    whether the split it pushed is the one the plan asked for (#304).

    A split that PASSED verification gets the command that opens its pull
    request, the same command `_open_the_pull_request` ran, with its title and
    body, so that it also runs where there is no terminal to prompt on. One
    that did not gets the opposite: the refusal printed above names the exact
    command that was tried, and a person who sees only that, with findings
    under it, may paste it. Stdout is flushed first. The table is on it and a
    pipe holds it in a block buffer, so without the flush this would come
    before the table it depends on in a merged log; a stdout that is closed,
    `| head` and gone, must not take the command down with it (`_flush_stdout`).
    """
    _flush_stdout()
    if not passed:
        print("No pull request was opened, and none should be: the split "
              "above did not pass verification.", file=sys.stderr)
        return
    command = " ".join(shlex.quote(argument) for argument in
                       _pull_request_command(repositories, names, tracking,
                                             branch, message))
    print(f"The branch IS pushed. Open the pull request by hand:\n    "
          f"{command}", file=sys.stderr)


def _set_the_topic(repositories: dict, topic: str) -> bool:
    """(c″) The topic, on all three.

    The assembly root pre-existed and is still a repository OF THIS PROJECT:
    `project.yaml` claims `topic: <topic>` either way, and a claim the
    organisation cannot see is the defect being fixed here.

    A TOPIC THAT WILL NOT SET DOES NOT SUPPRESS THE VERIFICATION TABLE. The
    split is pushed and the pull request is open by now, and the blob-sha
    accounting for every source path is the report a human is told to read
    back (AGENTS.md step 7); losing it to a permission or a rate limit would
    be the more expensive failure. So this RETURNS False rather than exiting:
    the caller reports it after the table, with the commands to finish by
    hand, and still exits non-zero. Split out of `cmd_execute` for #138.
    """
    try:
        for role in ("assembly", "spec", "code"):
            run(["gh", "repo", "edit", repositories[role], "--add-topic",
                 topic])
        print(f"  topic     {topic} set on all three")
    except CommandFailed as exc:
        print(exc.loudly("setting the project topic"), file=sys.stderr)
        print("The split IS pushed and the pull request IS open. Set the "
              "topic by hand:\n"
              + "\n".join(f"    gh repo edit {repositories[role]} "
                          f"--add-topic {topic}"
                          for role in ("assembly", "spec", "code")),
              file=sys.stderr)
        return False
    return True


def _stage_the_split(assembly: Path, materialized: Materialized) -> None:
    """Stage what the mount removed or edited, then what the shape wrote.

    `git add -A -- .` is what stages the deletions the mount made and any edit
    to a tracked file, and it HONOURS THE SOURCE'S `.gitignore`: with the
    common `.*` + `!.gitignore` it SKIPS every NEW file whose name starts with
    a dot -- `.gitattributes` and `.github/workflows/validate.yml` among them
    -- so the split used to land without files `contracts/shape-pin.yaml`
    pins, `execute` said `adoption verified`, and the assembly's first `make
    bootstrap` refused with `shape-copy-missing` (#167). The shape's own files
    are therefore staged BY NAME with `-f`.

    ONLY THOSE PATHS, NEVER `-f .`: a file the source itself ignored is the
    source's decision, and forcing the whole tree would stage any ignored
    file that is in it -- the build artefact or the secret a `.gitignore` is
    written to keep out of a commit.
    `written` carries each path where it LANDED -- a copy beside a source file
    under `shape/`, and the Makefile with the adopt block appended -- and in
    POSIX spelling on every platform (`root_key`), which is the spelling `git`
    takes as a pathspec on Windows too.

    THROUGH A SYMLINK, the path git tracks is not the one written. A source
    whose plan keeps `.github -> ci` in the root has the shape's workflow
    written through the link, to `ci/workflows/validate.yml`, and git refuses
    the written spelling as a pathspec "beyond a symbolic link". So each path
    is staged as `_where_it_landed` spells it, and one whose link leads OUT of
    the assembly is not staged at all: it is not in this repository, and the
    verification reports the pinned file missing.

    AND EACH ONE IS A PATH, NOT A PATHSPEC (#216). A path that landed
    through a link is the link's target, a name the SOURCE chose, and after
    `--` git still reads a name as a pathspec: `:ci/workflows/validate.yml`
    is the magic `:` and the path `ci/...`, which matches nothing and fails
    the add (`fatal: pathspec ... did not match any files`) after both legs
    are pushed; `:!ci/...` is an EXCLUDE, which forces nothing by that name,
    so a file the source's `.gitignore` hides is left out of the split; and
    `ga[0]/...` is a glob, which forces an ignored `ga0/...` too. So
    `--literal-pathspecs`: every name is the path it spells.
    """
    run(["git", "add", "-A", "--", "."], cwd=assembly)
    landed = (_where_it_landed(assembly, written)
              for written in materialized.written)
    run(["git", "--literal-pathspecs", "add", "-f", "--",
         *(path for path in landed if path)], cwd=assembly)


def _where_it_landed(assembly: Path, written: str) -> str | None:
    """`written` as git tracks it: the same path when no symlink is on the way
    to it, else the path the symlinks inside the assembly lead to, and None
    when they lead out of it.

    A path with no symlink on the way is passed through as it is, never
    resolved: resolving could only respell it (a short name, or a letter's
    case, on Windows) and change what reaches git for nothing.
    """
    parts = written.split("/")
    if not any(assembly.joinpath(*parts[:end]).is_symlink()
               for end in range(1, len(parts) + 1)):
        return written
    root = assembly.resolve()
    landed = (assembly / written).resolve()
    return landed.relative_to(root).as_posix() \
        if landed.is_relative_to(root) else None


def _commit_the_split(plan: Plan, source: Source, assembly: Path,
                      names: dict, urls: dict, values: dict, work_root: Path,
                      paths_for: dict, seeded: list, spec_path: str,
                      code_path: str, branch: str,
                      leg_commits: dict) -> tuple[str, str] | None:
    """(c) ONE split commit on a branch of the source, pushed.

    Returns `(split_commit, message)` — the message travels on because it is
    also the pull request's body — or None when the push was REFUSED, having
    already said so. Split out of `cmd_execute` for #138.
    """
    # NO TEMPLATE (#243), as the scaffold's `git init` takes none (#229).
    # `git clone` copies the operator's template (`init.templateDir`, or
    # `GIT_TEMPLATE_DIR`) into `.git`, and one that holds a `modules/<leg
    # path>` store, as a copy of a working Triad root's `.git` does, plants
    # `.git/modules/<leg path>`. `git submodule add --force` in
    # `_mount_the_legs` REACTIVATES a store that is already there where it
    # would refuse without `--force`, so each mount took the STRANGER's
    # store: exit 0, a pushed split whose gitlinks were that store's commit
    # and not the legs' tips, `adoption verified` over it, and a recursive
    # clone that exits 128. The empty `--template=` is git's documented way
    # to use none. The assembly is a build directory this tool fills and
    # pushes, so no template content belongs in it, and whoever clones the
    # pushed root still gets their template from their own `git clone`. Nothing
    # else `execute` makes needs it: the legs' bare remotes and work trees are
    # never mounted into, and the mounts only READ the work trees, a clone
    # copying their objects and refs and never a `.git/modules`. With no
    # template the assembly has no `.git/hooks`, so HOOKS a template installs
    # no longer run on the split's commit and push, as they did before #243;
    # hooks set with `core.hooksPath` still do, and the legs keep their
    # template's hooks.
    run(["git", *FILE_PROTOCOL, "clone", "-q", "--template=",
         str(source.path), str(assembly)])
    run(["git", "checkout", "-q", "-B", branch, source.commit], cwd=assembly)
    _mount_the_legs(assembly, work_root, names, urls, paths_for, spec_path,
                    code_path)

    # A materializer refusal names the source's own symlinks and where they
    # lead, which can hold any character: spelled as every finding is (#212).
    materialized = materialize_assembly_root(
        SHAPE_ROOT, assembly, values, collision_dir=COLLISION_DIR,
        append={"Makefile": ADOPT_MAKEFILE_BLOCK}, spell=_spelled)
    for intended, actual in materialized.collisions:
        print(f"  beside  {actual} (the source already has {intended}; nothing "
              "was overwritten)")

    follow_ups = [str(f) for f in plan.get("follow_ups", [])]
    message = _split_message(names, paths_for, leg_commits, spec_path,
                             code_path, follow_ups, materialized.collisions,
                             seeded)
    _stage_the_split(assembly, materialized)
    env_commit(assembly, message)
    split_commit = git_out(["rev-parse", "HEAD"], cwd=assembly).lower()
    try:
        run(["git", "push", "-q", urls["assembly"],
             f"HEAD:refs/heads/{branch}"], cwd=assembly)
    except CommandFailed as exc:
        print(exc.loudly("pushing the split branch"), file=sys.stderr)
        return None
    print(f"\n  split {split_commit[:12]} on {branch} -> {urls['assembly']}")
    return split_commit, message


def cmd_execute(args) -> int:
    plan = Plan.load(Path(args.plan))
    work_root = _work_root(args)
    source = plan.open_source(args.source, work_root)
    naming = NamingPolicy.load(NAMING_POLICY)
    _require_filter_repo()

    names = plan.names()
    pins = set(plan.pins)
    _check_names(naming, names, pins)
    _refuse_an_unrunnable_plan(plan, source)

    # THE PLAN IS UNTRUSTED INPUT. It is a file a human or an AI edited, and
    # every value below becomes an argument to `git` or `gh`, so each one is
    # validated before it is used rather than after something has gone wrong.
    spec_path, code_path, branch, tracking = _checked_plan_values(plan)
    local, repositories, urls = _repository_urls(args, plan, names, source)
    _refuse_an_unwritable_clone_url(urls["assembly"])
    paths_for = _leg_paths(plan)
    _refuse_what_check_finds(plan, source, args.local_remote_dir)
    _refuse_symlinks_checked_out_as_files(plan, source, work_root)

    seeded = seeded_legs(paths_for)
    _refuse_unconsented_seeding(args, plan, seeded)
    for line in plan.seeding_record_disagreements(seeded):
        print(line)
    topic = naming.topic_for(plan.project_id)
    print(_topics_line(topic, local))
    _confirm(args, plan, names)

    # ---- (a) the two legs' remotes ----------------------------------------
    _create_leg_remotes(plan, names, repositories, urls, tracking, local)

    # The substitution table is built BEFORE the legs, because a SEEDED leg is
    # rendered from `templates/<role>-root/` and needs it. The four leg
    # commit/digest values are the only ones that cannot be known yet; they
    # are filled in below, before the assembly root is materialized.
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    values = _template_values(plan, names, repositories, urls, spec_path,
                              code_path, tracking, {}, {},
                              shape_commit, pins, naming)

    # ---- (b) history-preserving extraction, or a seeded leg ---------------
    legs = _build_the_legs(source, names, repositories, urls, values,
                           work_root, paths_for, seeded, branch, tracking)
    if legs is None:
        return 2
    leg_commits, leg_digests = legs
    values.update({
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    })

    # ---- (c) ONE split commit on a branch of the source -------------------
    assembly = work_root / names["assembly"]
    split = _commit_the_split(plan, source, assembly, names, urls, values,
                              work_root, paths_for, seeded, spec_path,
                              code_path, branch, leg_commits)
    if split is None:
        return 2
    split_commit, message = split

    # A pull request `gh` refused does not end the run here: the legs and the
    # split ARE pushed, and what the person needs to know before they open it
    # is whether the split is right (#304). The topic is not tried after a
    # refused pull request, because what it says is that the pull request IS
    # open.
    pull_request_refused = topics_failed = False
    if not local:
        pull_request_refused = not _open_the_pull_request(
            repositories, names, tracking, branch, message)
        if not pull_request_refused:
            topics_failed = not _set_the_topic(repositories, topic)

    # ---- (d) verification, by blob sha ------------------------------------
    verified = _verify(source, assembly, work_root, names, paths_for,
                       split_commit, spec_path, code_path, seeded)
    if pull_request_refused:
        _open_it_by_hand(repositories, names, tracking, branch, message,
                         not verified)
    elif not verified:
        _next_steps(names)
    if verified:
        # A verification mismatch outranks a refused pull request and a
        # missing topic.
        return verified
    return 2 if pull_request_refused or topics_failed else 0


# ---------------------------------------------------------------------------
# What `execute` writes into a file is text a file can hold (#255)
# ---------------------------------------------------------------------------
#
# `_template_values` puts `elected_by`, `elected_on`, `reference`,
# `visibility`, each pin and the assembly root's clone URL into the templates
# as they stand, and `write_lf` writes the result as strict UTF-8;
# `_commit_the_split` puts each follow-up into the split commit's message.
# Since #247 a plan can carry a lone surrogate -- a byte that is not UTF-8,
# as `sys.argv` and `os.fsdecode` keep one -- and the reader gives it back.
# So `plan` and `check` passed `--elected-by b'Jos\xe9'`, and `execute`
# created and pushed both legs before `write_lf` raised `UnicodeEncodeError`.
# Before #247, `plan` raised on it and nothing was made. A line break or a
# NUL in the plan went on into the manifest, and a bidi override or isolate
# went into the README, which then showed the rest of its line reversed.
#
# So `unwritable_reason` is asked of each such value before anything exists.
# `plan` refuses `--elected-by` and `--reference` as
# `adopt-unwritable-value`, and writes no plan (`--elected-on` is a date, and
# `election_date` refuses anything else). `check` reports each plan value as
# `plan-unwritable-value`, and `execute` refuses those findings through
# `_refuse_what_check_finds`, before `_create_leg_remotes`. Every other value
# the templates take is a `checked_value`, the project id, or one of this
# tool's own.
#
# THE CLONE URL IS `execute`'S OWN. Under `--local-remote-dir` it is the
# source's path, and `check` has no such flag to know it will be written.
# Against GitHub it is `https://github.com/<org>/<name>.git`, and the path is
# written nowhere. So `execute` refuses an unwritable one itself, right
# after `_repository_urls`, and `plan` and `check` still pass a source
# directory whose name is not UTF-8, as #247 made them.

#: `check`'s finding, and the code `execute` refuses it under.
UNWRITABLE_VALUE = "plan-unwritable-value"

#: Where `execute` writes the values it is asked about.
ROOT_MANIFEST = "the assembly root's `project.yaml`"
ROOT_MANIFEST_AND_README = "the assembly root's `project.yaml` and `README.md`"
SPLIT_MESSAGE = "the split commit's message"

#: Each plan value `_template_values` substitutes as it stands, by its key,
#: and where it lands. `pins` and `follow_ups` are lists, asked item by item.
WRITTEN_PLAN_VALUES = {"elected_by": ROOT_MANIFEST_AND_README,
                       "elected_on": ROOT_MANIFEST_AND_README,
                       "reference": ROOT_MANIFEST_AND_README,
                       "visibility": ROOT_MANIFEST}

#: Why such a value must be text, said after every refusal of one.
WRITTEN_AS_TEXT = (
    "`execute` writes each one as it stands, into the assembly root's files "
    "or the split commit's message, so it must be one line of UTF-8 text. A "
    "byte that is not UTF-8, or a lone surrogate, cannot be written at all; "
    "a line break or a control character would be written raw into a value "
    "that is read back as one line; and a bidirectional embedding, override "
    "or isolate control would show the rest of the line it is written into "
    "in another order than it is written. A byte that is not UTF-8 reaches a "
    "command line from a terminal or a script whose encoding is not the "
    "locale's.")

PLAN_VALUE_REMEDIATION = ("Remediation: correct each value named in the plan, "
                          "or re-run `plan` with it retyped. "
                          + WRITTEN_AS_TEXT)


def unwritable_values(fields) -> list[str]:
    """A sentence for each `(what, value, where)` whose `value` is not text
    a file can hold; `[]` when every one is.

    `what` names the value as the person has it in front of them --
    `--elected-by` to `plan`, `elected_by` read out of a plan -- and `where`
    is the file `execute` writes it into. The value is spelled as Python
    spells it, as `unsafe-value` spells one, so the sentence stays one line
    of text whatever the value holds.
    """
    out = []
    for what, value, where in fields:
        reason = unwritable_reason(value)
        if reason:
            out.append(f"{what} is {value!r}, which `execute` writes into "
                       f"{where}, and {reason}")
    return out


def _plan_values(plan: Plan) -> list[tuple[str, str, str]]:
    """`(what, value, where)` for each value of the plan's that `execute`
    writes into a file, as `str` makes it, which is how `_template_values`
    and `_commit_the_split` take it. A key the plan does not carry is filled
    by this tool (`private`, today's date) and is left out."""
    fields = [(key, str(plan.get(key)), where)
              for key, where in WRITTEN_PLAN_VALUES.items()
              if plan.get(key) is not None]
    fields += [("a `pins:` item", pin, ROOT_MANIFEST) for pin in plan.pins]
    return fields + [("a `follow_ups:` item", str(item), SPLIT_MESSAGE)
                     for item in plan.get("follow_ups", [])]


def _value_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """`unwritable_values` of the plan as `check` prints them, one FINDING
    each, and what to print once after every finding: how to correct them
    when there is one, nothing when there is none."""
    found = [f"FINDING {UNWRITABLE_VALUE}: {problem}"
             for problem in unwritable_values(_plan_values(plan))]
    return found, [PLAN_VALUE_REMEDIATION] if found else []


def _refuse_an_unwritable_clone_url(url: str) -> None:
    """Refuse the assembly root's clone URL when no file can hold it, before
    any leg exists.

    Only a local one can be refused: under `--local-remote-dir` the URL is
    the source's own path, which the assembly root's `README.md` names (and
    a seeded leg's), so a source directory whose name is not UTF-8 pushed
    both legs and then raised in `write_lf` (#255), and one whose name holds
    a bidi override was written into the README raw.

    THE REMEDIATION MOVES THE SOURCE AND PLANS AGAIN. A clone of it at a
    path that is text, passed to `execute` with --source, still has the old
    path as its `origin`, and `_remote_repository` reads that as UTF-8 and
    raises; renaming the directory and running `plan` again adopts.
    """
    reason = unwritable_reason(url)
    if reason:
        raise Refusal(
            "adopt-unwritable-value",
            "under --local-remote-dir the assembly root's clone URL is the "
            f"source's own path, {url!r}, which `execute` writes into its "
            f"`README.md`, and {reason}",
            "Remediation: nothing was created. Rename or move the source "
            "repository so that its path is one line of UTF-8 text with no "
            "control character in it, then run `plan --source <its new "
            "path>`, `check` and `execute` again; or adopt against GitHub, "
            "without --local-remote-dir, where the clone URL is "
            "`https://github.com/<org>/<name>.git`.")


def _template_values(plan: Plan, names, repositories, urls, spec_path,
                     code_path, tracking, leg_commits, leg_digests,
                     shape_commit, pins, naming) -> dict[str, str]:
    project = names["assembly"]
    project_id = plan.project_id
    elected_on = str(plan.get("elected_on", _dt.date.today().isoformat()))
    # `.get(role, "")` because this table is built BEFORE the legs exist, so
    # that a SEEDED leg's template can be rendered from it. The four values
    # are filled in by the caller as soon as each leg has a commit, and the
    # assembly root — the only tree whose templates name them — is
    # materialized after that.
    return {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": project,
        "ORG": str(plan.get("org")),
        "TOPIC": naming.topic_for(project_id),
        "VISIBILITY": str(plan.get("visibility", "private")),
        # A plan that omits `reference:` — one written by hand, or by a tool
        # older than this rule — is resolved from ITS OWN `elected_on`, not
        # from the day `execute` happens to run. The plan carries the human's
        # act; the calendar of the machine running the split does not.
        "REFERENCE": str(plan.get("reference")
                         or default_reference(elected_on)),
        "ELECTED_BY": str(plan.get("elected_by", "")),
        "ELECTED_ON": elected_on,
        "TRACKING_BRANCH": tracking,
        "SPEC_PATH": spec_path,
        "CODE_PATH": code_path,
        "ASSEMBLY_REPOSITORY": repositories["assembly"],
        "SPEC_REPOSITORY": repositories["spec"],
        "CODE_REPOSITORY": repositories["code"],
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": tree_digest(SHAPE_ROOT, shape_commit),
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
        "CLONE_URL": urls["assembly"],
        "ASSEMBLY_CLONE_URL": urls["assembly"],
        "SPEC_COMMIT": leg_commits.get("spec", ""),
        "CODE_COMMIT": leg_commits.get("code", ""),
        "SPEC_TREE_SHA256": leg_digests.get("spec", ""),
        "CODE_TREE_SHA256": leg_digests.get("code", ""),
        "NEUTRAL_PRODUCT_PINS": ("[]" if not pins else
                                 "\n" + "\n".join(f"  - {p}"
                                                  for p in sorted(pins))),
        "ASSEMBLY_NAMING": naming_block(naming, names["assembly"], "assembly",
                                        pins),
        "SPEC_NAMING": naming_block(naming, names["spec"], "spec", pins),
        "CODE_NAMING": naming_block(naming, names["code"], "code", pins),
    }


def _split_message(names, paths_for, leg_commits, spec_path, code_path,
                   follow_ups, collisions, seeded=()) -> str:
    def none_line(role: str) -> list[str]:
        if role not in seeded:
            return ["  (none)"]
        return [f"  (none — this leg was SEEDED from {SHAPE_REPOSITORY}'s "
                f"{SEED_TEMPLATE[role]}/, because no path of this repository "
                f"was assigned to it. It is mounted and pinned like the other "
                f"leg and carries no history from here, there being none.)"]

    lines = [
        f"Adopt the three-repository shape: {names['spec']} and "
        f"{names['code']}",
        "",
        f"{names['assembly']} keeps its name, its identity and its full "
        "history and becomes the assembly root of the project. The two legs "
        "are NEW repositories extracted with `git filter-repo`, so every "
        "moved file keeps the commits that made it. Nothing was deleted: what "
        "leaves this tree arrives in a leg at the same path, mounted back "
        f"here at {spec_path}/ and {code_path}/.",
        "",
        f"MOVED TO THE SPEC LEG ({names['spec']} @ {leg_commits['spec'][:12]}):",
    ]
    lines += [f"  {path}" for path in sorted(paths_for["spec"])] \
        or none_line("spec")
    lines += ["",
              f"MOVED TO THE CODE LEG ({names['code']} @ "
              f"{leg_commits['code'][:12]}):"]
    lines += [f"  {path}" for path in sorted(paths_for["code"])] \
        or none_line("code")
    if paths_for["drop"]:
        lines += ["", "DROPPED (in no leg and no longer here):"]
        lines += [f"  {path}" for path in sorted(paths_for["drop"])]
    lines += ["", "STAYS IN THE ASSEMBLY ROOT:"]
    lines += [f"  {path}" for path in sorted(paths_for["root"])]
    if collisions:
        lines += ["", "WRITTEN BESIDE, NOT OVER (this repository had the name "
                  "first):"]
        lines += [f"  {actual}  <- the shape's {intended}"
                  for intended, actual in collisions]
    if follow_ups:
        lines += ["", "FOLLOW-UPS, which this commit does NOT do:"]
        lines += [f"  - {item}" for item in follow_ups]
    return "\n".join(lines) + "\n"


def _verify(source: Source, assembly: Path, work_root: Path, names,
            paths_for, split_commit: str, spec_path: str, code_path: str,
            seeded=()) -> int:
    """Every source blob is in exactly one place afterwards, or this fails.

    THE ONE CHECK THAT MAKES THE REST TRUSTWORTHY. Counting paths would pass a
    split that silently truncated a file; comparing BLOB SHAs cannot. A path
    that is in two places is as much a finding as a path that is in none —
    the second is data loss and the first is two owners for one file.

    A SEEDED LEG DOES NOT WEAKEN IT. Its files are template bytes that were
    never in the source, so they cannot match a source blob and are counted as
    added, exactly like the manifest and the pins. The leg's row therefore
    reads `0 of N source paths (seeded from template)` — which is the honest
    number, and still leaves every source path to be accounted for somewhere.

    ONLY THE TWO LEG MOUNTS ARE PASSED OVER, never every gitlink (#165). The
    legs' own trees account for what is behind `spec_path` and `code_path`;
    any OTHER gitlink in the root tree is a path like a blob, and skipping
    them all hid a source submodule kept here (reported lost), one the split
    failed to remove (in a leg AND here, never seen twice) and one nobody
    asked for (not even counted as added). Each is also a finding of its own,
    because the root keeps no gitlink but the two mounts: this check fails
    closed on one, and does not lean on `check`'s refusals to keep it out.
    `_land_the_root_tree` says which.

    EACH MOUNT IS THE COMMIT THAT WAS PUSHED TO ITS LEG (#243). The legs'
    trees account for the source's blobs whichever commit the root mounts, so
    a mount at ANOTHER commit passed every check above: a module store `git
    submodule add --force` reactivated (an operator's template planted one)
    made a split whose gitlinks were a stranger's commit, which was pushed
    and said `adoption verified`. `_mount_commit_findings` compares each
    gitlink with the `HEAD` of its leg's work directory: the commit pushed,
    and the tree read above. It does not undo the push, as no finding does;
    the clone's `--template=` is what keeps a planted store out.
    """
    print("\nVERIFICATION — every source path at "
          f"{source.commit[:12]}, by blob sha")
    before = {path: oid for path, _, oid, _ in source.tree()}
    after: dict[str, list[str]] = {}
    for role in ("spec", "code"):
        for path, _, oid, _ in _tree_of(work_root / names[role], "HEAD"):
            after.setdefault(path, []).append(f"{role}:{oid}")
    mounts = dict(zip((spec_path, code_path), EXTRACTED_LEGS))
    split_tree = _tree_of(assembly, split_commit)
    root_findings = _land_the_root_tree(after, split_tree, before, mounts)
    root_findings += _mount_commit_findings(
        split_tree, mounts, _pushed_commits(work_root, names))

    counts, findings = _account_for(before, after, paths_for["drop"])
    findings += _shape_file_findings(assembly, split_commit)
    added = sorted(set(after) - set(before))
    for leg in ("spec", "code", "root", "drop"):
        note = " (seeded from template)" if leg in seeded else ""
        print(f"  {leg:<6} {counts[leg]:>5} of {len(before)} source "
              f"paths{note}")
    print(f"  added  {len(added):>5} new paths (manifest, pins, shape files"
          + (", seeded leg" if seeded else "") + ")")
    findings += root_findings
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} verification finding(s). The legs and the "
              "branch exist; NOTHING was deleted from the source, so the exit "
              "is to fix the plan and re-run into a fresh --local-remote-dir "
              "or fresh leg repositories, unless a finding above names "
              "another exit.", file=sys.stderr)
        return 1
    print("\nadoption verified: every source path is in exactly one place")
    return 0


def _next_steps(names: dict) -> None:
    """What a person does once the split is verified AND its pull request is
    open. Not said where there is none to review: after a refused `gh pr
    create`, the command to open it is the next step (#304)."""
    print(f"\nNEXT: review the pull request on {names['assembly']}, then\n"
          f"    git clone --recurse-submodules <{names['assembly']} url>\n"
          "    make bootstrap")


def _account_for(before: dict, after: dict, drops: list[str]) -> tuple[dict, list]:
    """Where each source blob landed: exactly one place, or a finding.

    A path in TWO places is as much a finding as a path in none — the second
    is data loss and the first is two repositories owning one file.
    """
    dropped = {p.rstrip("/") for p in drops}
    counts = {"spec": 0, "code": 0, "root": 0, "drop": 0}
    findings: list[str] = []
    for path, oid in sorted(before.items()):
        landings = [where for where in after.get(path, [])
                    if where.split(":", 1)[1] == oid]
        if len(landings) == 1:
            counts[landings[0].split(":", 1)[0]] += 1
        elif landings:
            findings.append(f"FINDING adopt-duplicated: {_spelled(path)} is "
                            "in " + ", ".join(landings))
        elif any(path == d or path.startswith(d + "/") for d in dropped):
            counts["drop"] += 1
        else:
            findings.append(f"FINDING adopt-lost: {_spelled(path)} "
                            f"({oid[:12]}) is in no leg, not in the root "
                            "tree, and not listed as drop")
    return counts, findings


#: How each root-tree gitlink finding ends. EVERY ONE MEANS THE SPLIT IS
#: WRONG: the plan values known to reach them are refused by `execute`
#: before any leg exists, so the person is not sent back to the plan.
#: `git submodule add` records a mount at its path's canonical spelling, so a
#: `legs.spec_path` of `spec/` once mounted the leg at `spec` and fired both
#: mount findings; since #169 that value is `plan-bad-leg-path`. A source
#: submodule kept in the root is `plan-submodule-root` since #166, and one
#: left with no leg is `plan-uncovered` or `plan-bad-leg` since #168
#: (`plan-unresolved` always was).
SPLIT_IS_WRONG = ("so the split itself is wrong: do not merge it, and report "
                  f"it to {SHAPE_REPOSITORY}")
#: The exit of `adopt-unexpected-gitlink` and `adopt-mount-missing`.
SPLIT_DEFECT = (
    "this is not how the plan spells its leg paths: `execute` refuses "
    "before any leg exists a leg path git would record at another spelling "
    f"(`plan-bad-leg-path`), {SPLIT_IS_WRONG}")
#: The exit of `adopt-mount-commit`: a plan never says which commit a mount is.
MOUNT_COMMIT_DEFECT = (
    "no plan chooses a mount's commit: each leg is mounted from its own work "
    "directory, and a module store already under `.git/modules/<name>`, which "
    "`git submodule add --force` reactivates, is the known way another "
    f"repository's commit is mounted instead, {SPLIT_IS_WRONG}")
#: The exit of `adopt-root-submodule`.
ROOT_SUBMODULE_DEFECT = (
    "`execute` refuses before any leg exists a plan that keeps a submodule "
    "of the source's in the root (`plan-submodule-root`) or leaves one with "
    "no leg (`plan-unresolved`, `plan-uncovered`, `plan-bad-leg`), "
    f"{SPLIT_IS_WRONG}")


def _land_the_root_tree(after: dict, tree: list, before: dict,
                        mounts: dict[str, str]) -> list[str]:
    """Land the split commit's tree in `after` as `root`; return what is wrong.

    `mounts` maps each leg's mount path, AS THE PLAN SPELLS IT, to the leg:
    `{spec_path: "spec", code_path: "code"}`. THE SHAPE ADDS
    EXACTLY TWO GITLINKS to the root, and those two are the only entries
    passed over. Every other gitlink lands like a blob, so a source submodule
    the root kept at its own commit is counted `root` and one the split
    failed to remove is `adopt-duplicated` with its leg. Three findings are
    this function's own, because no source path can report them:

      * EVERY OTHER GITLINK, whatever it is (`_root_gitlink_finding`): the
        source's own submodule at its own commit (`adopt-root-submodule`),
        or anything else (`adopt-unexpected-gitlink`). The root keeps no
        gitlink but the two mounts (#166), and this check FAILS CLOSED on
        the rest rather than trusting the plan checks before it to have
        refused them. Counting the source's own as a `root` landing and
        nothing more says `adoption verified` over an assembly whose fresh
        `.gitmodules` does not register it: its recursive clone leaves that
        directory empty, and `git submodule status` exits 128.
      * `adopt-mount-missing`: a mount path holding no gitlink. The root
        pins a leg it does not mount, and its recursive clone gets no leg.

    They name the mount paths as the plan spells them, which since #169 is
    the one spelling git records a mount at. The gitlink a finding names is
    `_spelled`, as every path a finding names is (#212): its path is a source
    or split name, where a mount path is a leg path, which `checked_value`'s
    alphabet already keeps printable.

    THE ROOT `.gitmodules` IS STILL COMPARED BYTE FOR BYTE, deliberately, and
    not by its registrations. The source's own cannot reach here: `check`
    finds, and `execute` refuses, a plan that keeps it in the root (#166) or
    leaves it in no entry at all (#168). The fresh one `_mount_the_legs`
    writes is the SHAPE'S file, not a source landing: it is counted as added
    in a source that had none, and beside a source `.gitmodules` the plan
    moved or dropped it matches no source blob and is passed over. Accounting
    registrations would verify a path no plan `execute` runs can take, and
    would read the source's registrations into a file the shape reserves for
    its two mounts.
    """
    findings: list[str] = []
    mounted: set[str] = set()
    for path, mode, oid, _ in tree:
        gitlink = mode == GITLINK_MODE
        if gitlink and path in mounts:
            mounted.add(path)
            continue
        after.setdefault(path, []).append(f"root:{oid}")
        if gitlink:
            findings.append(_root_gitlink_finding(path, oid, before, mounts))
    findings += [f"FINDING adopt-mount-missing: the root tree has "
                 f"{_what_is_at(tree, path)} at {path} as the plan spells "
                 f"it, where the gitlink that mounts the {role} leg belongs; "
                 + SPLIT_DEFECT
                 for path, role in sorted(mounts.items())
                 if path not in mounted]
    return findings


def _root_gitlink_finding(path: str, oid: str, before: dict,
                          mounts: dict[str, str]) -> str:
    """The finding for a gitlink in the root tree at a path no leg is
    mounted at. There is one for EVERY such gitlink (#165); this says which.

    The source's own submodule is matched by path AND commit. Matching the
    path alone would call a submodule moved to another commit the source's
    own, when it is as foreign to the source as one at a new path.
    """
    if before.get(path) == oid:
        return (f"FINDING adopt-root-submodule: {_spelled(path)} is a "
                f"gitlink to {oid[:12]} in the root tree, the source's own "
                "submodule at its own commit, and the assembly root keeps no "
                f"submodule of the source's: its {GITMODULES} is reserved for "
                f"its two leg mounts; {ROOT_SUBMODULE_DEFECT}")
    return (f"FINDING adopt-unexpected-gitlink: {_spelled(path)} is a "
            f"gitlink to {oid[:12]} in the root tree, and neither a leg mount "
            f"as the plan spells their paths ({', '.join(sorted(mounts))}) "
            f"nor the source's own submodule at that commit; {SPLIT_DEFECT}")


def _what_is_at(tree: list, path: str) -> str:
    """What a mount path holds instead of its gitlink, for the finding."""
    for entry, mode, _, _ in tree:
        if entry == path:
            return f"a blob (mode {mode})"
        if entry.startswith(path + "/"):
            return "a directory"
    return "nothing"


def _mount_commit_findings(tree: list, mounts: dict[str, str],
                           pushed: dict[str, str]) -> list[str]:
    """`adopt-mount-commit` for each mount whose gitlink names any commit but
    the one pushed to its leg (#243); `mounts` is `_land_the_root_tree`'s and
    `pushed` is `_pushed_commits`'.

    The pin the split wrote names the pushed commit, and a mount at another
    leaves a recursive clone unable to satisfy both: it fails (exit 128), or
    checks out a tree nobody pushed there. The question is ASKED OF A GITLINK
    ONLY: a mount path that holds none is `adopt-mount-missing`
    (`_land_the_root_tree`), and said once. It is asked here, beside that
    function, because that one lands paths and knows nothing of what was
    pushed.
    """
    return [f"FINDING adopt-mount-commit: {path} is a gitlink to {oid[:12]} "
            f"in the root tree, where the {mounts[path]} leg was pushed at "
            f"{pushed[mounts[path]][:12]}, so the mount is not the leg this "
            "run pushed and a recursive clone of the split checks out the "
            f"wrong commit or cannot fetch one; {MOUNT_COMMIT_DEFECT}"
            for path, mode, oid, _ in tree
            if mode == GITLINK_MODE and path in mounts
            and oid != pushed[mounts[path]]]


def _pushed_commits(work_root: Path, names: dict) -> dict[str, str]:
    """The commit `execute` pushed to each leg: the `HEAD` of its work
    directory, which `_extract_leg` and `_seed_leg` push as
    `HEAD:refs/heads/<tracking>` and whose tree `_verify` accounts for."""
    return {role: git_out(["rev-parse", "HEAD"],
                          cwd=work_root / names[role]).lower()
            for role in EXTRACTED_LEGS}


def _tree_of(repo: Path, rev: str) -> list[tuple[str, str, str, int]]:
    raw = git_out(["ls-tree", "-r", "-z", rev], cwd=repo, binary=True)
    out = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        head, _, path = record.partition(b"\t")
        mode, kind, oid = head.decode().split()
        out.append((path.decode("utf-8", "surrogateescape"), mode, oid, 0))
        del kind
    return out


class _NotInTheSplitError(Exception):
    """A pinned path that leads to no file of the split commit. Its text
    finishes the finding's sentence about that path."""


class _SplitTree:
    """The split commit's tree, read the way a CHECKOUT of it reads (#167).

    `validate-pins.py` opens each pinned path in a clone, and the filesystem
    follows every symlink on the way, the last one included: a source whose
    plan keeps `.github -> ci` in the root has the shape's workflow at
    `ci/workflows/validate.yml`, and a clone finds it by its pinned name. A
    lookup of that name in `git ls-tree` would call the file missing, so a
    symlink entry here (mode 120000, its blob the target) is followed too --
    inside the tree, and only there. A link that leads out of the tree, or
    round a loop, does NOT lead to the file: a clone holds nothing outside
    itself, and a checkout's `open()` gives up on a loop with ELOOP.
    """

    def __init__(self, assembly: Path, commit: str) -> None:
        self.assembly = assembly
        self.commit = commit[:12]
        self.entries = {path: (mode, oid)
                        for path, mode, oid, _ in _tree_of(assembly, commit)}
        #: The mounted legs: a directory in a checkout, so `..` may leave one.
        self.mounts = {path for path, (mode, _) in self.entries.items()
                       if mode == GITLINK_MODE}
        self._dirs: set[str] | None = None

    def blob_at(self, path: str) -> str:
        """The oid of the FILE `path` leads to; `_NotInTheSplitError` when it
        leads to none."""
        mode, oid = self.entries.get(self._resolve(path), ("", ""))
        if mode not in FILE_MODES:
            # Absent, or a mounted leg's gitlink: nothing `is_file()` finds.
            raise _NotInTheSplitError(
                f"is not in the split commit {self.commit}")
        return oid

    def _resolve(self, path: str) -> str:
        """`path` with each symlink on the way followed, as `open()` does."""
        parts, done, via, hops = self._parts(path, ""), [], "", 0
        while parts:
            part = parts.pop(0)
            if part == "..":
                done = self._up(done, via)
                continue
            at = "/".join([*done, part])
            target = self._target_of(at)
            if target is None:
                done.append(part)
                continue
            hops, via = hops + 1, f" at the symlink {_spelled(at)}"
            if hops > SYMLINK_HOPS:
                raise _NotInTheSplitError(
                    f"follows too many symlinks at {_spelled(at)} in the "
                    f"split commit {self.commit}")
            parts = self._parts(target, via) + parts
        return "/".join(done)

    def _parts(self, target: str, via: str) -> list[str]:
        if target.startswith("/"):
            raise _NotInTheSplitError(
                f"leads out of the split commit {self.commit}{via}, to "
                f"{_spelled(target)}")
        return [part for part in target.split("/") if part not in ("", ".")]

    def _up(self, done: list[str], via: str) -> list[str]:
        """`..`, which a checkout takes from a directory, and never above the
        root of the clone."""
        if not done:
            raise _NotInTheSplitError(
                "climbs above the root of the split commit "
                f"{self.commit}{via}")
        here = "/".join(done)
        if not self._is_dir(here):
            raise _NotInTheSplitError(
                f"passes through {_spelled(here)}, which is not a directory "
                f"in the split commit {self.commit}")
        return done[:-1]

    def _is_dir(self, path: str) -> bool:
        if self._dirs is None:
            self._dirs = set(self.mounts)
            for entry in self.entries:
                parts = entry.split("/")
                self._dirs.update("/".join(parts[:end])
                                  for end in range(1, len(parts)))
        return path in self._dirs

    def _target_of(self, at: str) -> str | None:
        mode, oid = self.entries.get(at, ("", ""))
        if mode != SYMLINK_MODE:
            return None
        return git_out([GIT_CAT_FILE, "blob", oid], cwd=self.assembly,
                       binary=True).decode("utf-8", "surrogateescape")


def _pinned_shape_paths(assembly: Path, pin: str) -> list[str] | None:
    """The `path:` of every row of the pin whose blob is `pin`, or None when
    it is not a `files:` list of paths.

    None is a FINDING for the caller and never an empty answer: a pin that
    names nothing would otherwise make the check below vacuously pass, which is
    the one outcome it exists to prevent.
    """
    try:
        loaded = parse_yaml(git_out([GIT_CAT_FILE, "blob", pin],
                                    cwd=assembly))
    except (YamlError, UnicodeDecodeError):
        return None
    rows = loaded.get("files") if isinstance(loaded, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    paths = [row.get("path") if isinstance(row, dict) else None
             for row in rows]
    return paths if all(isinstance(path, str) and path for path in paths) \
        else None


#: What a shape-file finding tells the human to do. Once `_stage_the_split`
#: forces the shape's files, a source `.gitignore` cannot keep one out; what
#: still can is a PLAN ANSWER -- the source's own file at a shape path, or a
#: symlink on the way to one, kept in the root -- and the exit for that is the
#: one `_verify`'s footer and AGENTS.md give. Anything else is this tool's
#: defect, which no plan answer and no hand edit of the split should paper
#: over.
SHAPE_FILE_EXIT = (
    "If the plan kept in the root a file of the source's own at a shape "
    f"file's path -- its own {SHAPE_PIN} most often, the shape's then beside "
    f"it as {COLLISION_DIR}/{SHAPE_PIN} -- or a symlink on the way to one, "
    "send that path to a leg or `drop` it, and re-run into fresh legs. "
    "Otherwise the split itself is wrong: do not merge it, and report it to "
    f"{SHAPE_REPOSITORY}")


def _missing_shape_file(path: str, why: str, refusal: str) -> str:
    """`refusal` is what the first bootstrap's `validate-pins.py` says about
    it: `shape-pin-missing` for the pin itself, `shape-copy-missing` for a
    file the pin names. `path` is `_spelled`, as every path a finding names
    is, and so is each path `why` names (#212)."""
    return (f"FINDING adopt-shape-file-missing: {_spelled(path)} {why}, so "
            f"the assembly's first `make bootstrap` refuses with {refusal}. "
            + SHAPE_FILE_EXIT)


def _pinned_file_finding(tree: _SplitTree, path: str) -> str | None:
    try:
        tree.blob_at(path)
    except _NotInTheSplitError as why:
        return _missing_shape_file(path, f"is named by {SHAPE_PIN} but {why}",
                                   "shape-copy-missing")
    return None


def _shape_file_findings(assembly: Path, split_commit: str) -> list[str]:
    """A FINDING for every file `contracts/shape-pin.yaml` names that the split
    commit does not contain (#167).

    `_account_for` accounts for the SOURCE's paths and never for the paths the
    SHAPE ADDED, so a file a source `.gitignore` hid from `git add` was in no
    count at all and the run said `adoption verified`. The pin is the shape's
    own list of what it copied, so it is the list to check -- read out of the
    SPLIT COMMIT and compared with that commit's tree, never with the disk: the
    assembly's working tree still HAS the ignored file, which is exactly why a
    disk check would pass over the gap. Presence only; `validate-pins.py`
    recomputes the digests at the first bootstrap. Each path is looked up the
    way that bootstrap opens it, through the tree's symlinks (`_SplitTree`),
    so the two agree on the same assembly.

    A pin that is absent from the commit, or that is not a `files:` list, is
    one finding of its own and nothing else is checked: there is no list to
    check against, and passing an unreadable one would be a silent success.
    """
    tree = _SplitTree(assembly, split_commit)
    try:
        pin = tree.blob_at(SHAPE_PIN)
    except _NotInTheSplitError as why:
        return [_missing_shape_file(
            SHAPE_PIN, f"is the pin that lists the shape's files and {why}",
            "shape-pin-missing")]
    pinned = _pinned_shape_paths(assembly, pin)
    if pinned is None:
        return [f"FINDING adopt-shape-pin-unreadable: {SHAPE_PIN} in the split "
                f"commit {split_commit[:12]} is not a `files:` list of paths, "
                "so no file the shape wrote could be checked. "
                + SHAPE_FILE_EXIT]
    return [finding for finding in (_pinned_file_finding(tree, path)
                                    for path in pinned) if finding]


# ---------------------------------------------------------------------------
# shared
# ---------------------------------------------------------------------------


def _names(project: str) -> dict[str, str]:
    return {"assembly": project, "spec": f"{project}-spec",
            "code": f"{project}-code"}


def _check_names(policy: NamingPolicy, names: dict[str, str],
                 pins: set[str]) -> None:
    for role, name in names.items():
        found = policy.classify(name, role, pins)
        if found is None:
            raise Refusal(
                "naming-unclassified",
                f"{name!r} matches no family in the naming policy",
                "Remediation: --project takes one CamelCase token with no "
                "hyphen, underscore, dot or space.")
        if not accepts_role(found, role):
            raise Refusal(
                "naming-role-mismatch",
                f"{name!r} classifies as {found.family}"
                + (f"/{found.role}" if found.role else "")
                + f", not as the {role!r} form of a project leg "
                f"({found.reason})",
                "Remediation: --project takes one CamelCase token. Two forms "
                "beyond the bare one MAY be the assembly root: a declared "
                "descendant (declare the pin with `--pin open<Product>` and it "
                "classifies as one, 2026-09-02), and an `open<Product>` "
                "neutral product, which may elect the shape and be its own "
                "root (2026-09-05). Neither may be the spec or code leg, and "
                "an `<X>-Install` may be no leg at all.")


def _elector() -> str:
    try:
        return git_out([GIT_CONFIG, "user.name"], cwd=SHAPE_ROOT)
    except Refusal:
        return ""


def _work_root(args) -> Path:
    root = (args.work_dir.resolve() if getattr(args, "work_dir", None)
            else Path(tempfile.mkdtemp(prefix="openreposhape-adopt-")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="classify a source repository")
    plan.add_argument("--source", required=True,
                      help="a local path (read only) or `org/repo` to clone")
    plan.add_argument("--project", required=True,
                      help="the assembly-root name; for an in-place adoption "
                           "it is the source repository's own name")
    plan.add_argument("--org", default=None)
    plan.add_argument("--id", default=None)
    plan.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                      default="private")
    plan.add_argument("--elected-by", default=None)
    plan.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    plan.add_argument("--reference", default=None,
                      help="the document the election followed. Default: "
                           "openxFactory's ratified "
                           "docs/project-repo-schema.md for an election on or "
                           "after 2026-09-02, and the staged fragment it was "
                           "ratified from for one dated earlier — so "
                           "--elected-on chooses it.")
    plan.add_argument("--tracking-branch", default="main")
    plan.add_argument("--spec-path", default="spec")
    plan.add_argument("--code-path", default="code")
    plan.add_argument("--pin", action="append", default=[],
                      help="a neutral product this project declares a pin on "
                           "— a NAME only, e.g. --pin openGlass or --pin "
                           f"{NEUTRAL_PRODUCT_OWNER}/openGlass to name the "
                           "owner explicitly. Adopting a project pins no "
                           "commit at plan time, so a trailing @<commit> "
                           "(scaffold-project.py's syntax) is refused.")
    plan.add_argument("--allow-empty-leg", action="append", default=[],
                      choices=EXTRACTED_LEGS,
                      help="record in the plan that this leg having NO path "
                           "is intended, so it may be SEEDED from the shape's "
                           "template instead of extracted. The InkRouter "
                           "services are specifications with no code yet "
                           "(2026-09-04): `--allow-empty-leg code`. "
                           "Repeatable.")
    plan.add_argument("--path-policy", type=Path, default=None)
    plan.add_argument("--out", default="adoption-plan.yaml")
    plan.add_argument("--work-dir", type=Path, default=None)
    plan.set_defaults(func=cmd_plan)

    check = subparsers.add_parser("check", help="validate a plan")
    check.add_argument("--plan", required=True)
    check.add_argument("--source", default=None,
                       help="override the source the plan names")
    check.add_argument("--work-dir", type=Path, default=None)
    check.set_defaults(func=cmd_check)

    execute = subparsers.add_parser("execute", help="carry the plan out")
    execute.add_argument("--plan", required=True)
    execute.add_argument("--source", default=None)
    execute.add_argument("--local-remote-dir", type=Path, default=None,
                         help="create the legs as bare repositories here "
                              "instead of calling `gh` (the TEST path)")
    execute.add_argument("--allow-empty-leg", action="append", default=[],
                         choices=EXTRACTED_LEGS,
                         help="proceed even though NO path is assigned to this "
                              "leg, seeding it from the shape's template. "
                              "Unioned with the plan's own `allow_empty_legs:`; "
                              "without one of the two, execute refuses.")
    execute.add_argument("--yes", action="store_true",
                         help="the human has read the plan and the follow-ups")
    execute.add_argument("--work-dir", type=Path, default=None)
    execute.set_defaults(func=cmd_execute)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
