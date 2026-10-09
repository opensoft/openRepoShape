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
           `adoption-plan.yaml`. Paths it cannot honestly call, and every
           path holding one of the source's own submodules, carry
           `leg: null`, `review_required: true` and the QUESTION to ask.
  check    validates a plan against the source: every path covered exactly
           once, no unresolved legs, leg names conforming to the naming
           policy, each leg's mount path one `execute` can mount
           (`spec`, `legs/spec`; never `spec/` or `./spec`, a name Git or
           Windows keeps for itself such as `.git` or `CON`, or a value
           `execute` would refuse; the two never equal or nested, in any
           case), and the source's own submodules kept on one leg with
           their `.gitmodules`, registered there and never in the root. It
           prints what will happen and changes nothing.
  execute  creates the two legs, extracts them with `git filter-repo`, makes
           the one split commit on a branch of the source, sets the
           `xf-project-<id>` topic on all three (skipped for local remotes),
           and then VERIFIES by blob sha that every source path landed in
           exactly one place. The split's `project.yaml` records the leg
           each source submodule kept in a leg was answered into, under
           `submodules:`, for `shape-doctor.py` to check it against.

THE PLAN IS AN ARTIFACT A HUMAN OR AN AI EDITS. That is why it is YAML with
reasons in it rather than a pipe between two processes: the classifier is
right about `openspec/` and cannot be right about `examples/golden-run/`
without knowing whether the specification cites it. `execute` REFUSES while
any `leg:` is still null, and on every other finding `check` reports, before
it has created a leg repository or pushed anything.

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
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from path_classify import PathPolicy, Verdict  # noqa: E402
from repo_shape import (  # noqa: E402
    free_plan_secret_hint,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    SAFE_ARG_RE, VISIBILITY_CHOICES, NamingPolicy, Refusal, YamlError,
    accepts_role, checked_value, git_out, load_yaml, parse_yaml, tree_digest,
)
from shape_materialize import (  # noqa: E402
    ADOPT_MAKEFILE_BLOCK, RULESET_HINT, SHAPE_REPOSITORY,
    CommandFailed, Materialized, collision_follow_up, copy_tree,
    default_reference, election_date, env_commit, git_init_commit,
    materialize_assembly_root, naming_block, run, write_lf,
)
import shape_advisory  # noqa: E402

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
#: How many symlinks one lookup follows before it is a loop: Linux's own
#: limit (MAXSYMLINKS), where `open()` in a checkout gives up with ELOOP.
SYMLINK_HOPS = 40
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
# mappings, block sequences and single-line scalars. Everything it emits is
# read back by `check`, and `tests/test_adopt_plan.py` round-trips a plan
# through both, which is what keeps the writer and the reader honest about
# each other.

_PLAIN_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_./@:+-]*$")

#: `D:\work\Thing` or `D:/work/Thing` — a Windows absolute path, in either
#: spelling. Recognised so that `--source` can tell a path the operator got
#: wrong from a repository name; see `Source.open`.
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


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
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
#: The `git` subcommand that prints one object: a source's `.gitmodules`,
#: and in the split commit a symlink's target and the shape pin.
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


def _registrations(listed: bytes) -> Registrations | str:
    """`git config -z --list` output, read by `Registrations`; or, for a
    `path` or `url` with no value at all, what git's submodule reader dies
    on. `-z` prints such a key with no newline, and git looks for its value
    after it has filtered the name and before it filters the value."""
    registrations = Registrations()
    for record in listed.split(b"\x00"):
        key, newline, value = _git_path(record).partition("\n")
        match = SUBMODULE_KEY_RE.fullmatch(key)
        if not match:
            continue
        if not newline and not _a_name_git_ignores(match["name"]):
            return f"missing value for '{key}'"
        registrations.read(match["name"], match["key"], value)
    return registrations


class Source:
    """A repository being read, and nothing more. Nothing here writes to it."""

    def __init__(self, path: Path, repository: str | None, branch: str,
                 commit: str):
        self.path = path
        self.repository = repository
        self.branch = branch
        self.commit = commit

    @classmethod
    def open(cls, spec: str, work_root: Path) -> "Source":
        """`spec` is a local path (used in place) or `org/repo` (cloned)."""
        candidate = Path(spec).expanduser()
        if candidate.exists():
            path = candidate.resolve()
            repository = _remote_repository(path)
        else:
            if "/" not in spec or WINDOWS_ABSOLUTE_RE.match(spec):
                # A DRIVE-LETTER PATH IS A PATH THAT IS NOT THERE, never an
                # `org/repo`. `D:/work/Thing` carries a `/` and would
                # otherwise be handed to `gh repo clone` as an owner named
                # `D:`; `os.path.isabs` cannot be asked instead, because it
                # answers False for that string on Linux and macOS and this
                # refusal must read the same on every platform.
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
        return cls(path, repository, branch, commit)

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

        A KEY WITH NO VALUE -- `path` or `url` with nothing after it -- is
        fatal to git's submodule reader alone, and git runs that reader only
        for a gitlink. So in a tree that holds none, nothing ever reads the
        file that way, the assembly's clone and `execute` pass over it as
        main always did, and it registers nothing (#166's S3). A line git
        cannot parse at all is another matter: every reader dies on it.
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
            return _one_line(listed.stderr.decode(errors="replace")).replace(
                "standard input", GITMODULES)
        read = _registrations(listed.stdout)
        if isinstance(read, str) and not any(
                mode == GITLINK_MODE for _, mode, _, _ in tree):
            return Registrations()
        return read

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
    it holds more than one path, the `own` entries that replace it. Each
    path is `_spelled`, because the question is a line of the plan."""
    question = (f"{asked.question or ''} This entry holds the submodule(s) "
                f"{_listed(held)}: it is asked this question, not "
                f"classified by its rule `{entry.rule}`.")
    if len(own) > 1:
        question += (" Split the entry if its paths do not all belong in one "
                     f"leg: replace it with "
                     f"{_replacements(entry.path, held, own)}, each with its "
                     "own `leg:`. An entry added beside this one for a path "
                     "it covers is `plan-covered-twice`.")
    return Entry(entry.path, Verdict(None, asked.rule, asked.reason,
                                     asked.confidence, question),
                 entry.files, entry.bytes)


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
    the backticks still delimit it.
    """
    return "`" + "".join(map(_spelled_character, path)) + "`"


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
    """
    code_paths = [e.path.rstrip("/") for e in entries if e.leg == "code"]
    spec_dirs = [e.path for e in entries
                 if e.leg == "spec" and e.path.endswith("/")]
    if not code_paths or not spec_dirs:
        return []
    out: list[str] = []
    for spec_dir in spec_dirs:
        proc = subprocess.run(
            ["git", "grep", "-l", "-I", "-F", spec_dir, source.commit, "--",
             *code_paths],
            cwd=str(source.path), capture_output=True, text=True, check=False)
        hits = [line.split(":", 1)[1] for line in proc.stdout.splitlines()
                if ":" in line]
        # Fixtures last. A test fixture that mentions `contracts/` is usually
        # quoting a path rather than reading one, and burying the harness that
        # DOES read it under twenty of them is how a follow-up list stops
        # being read at all.
        hits.sort(key=lambda h: ("fixture" in h or h.startswith("tests/"), h))
        for hit in hits[:8]:
            out.append(
                f"{code_path}/{hit} names `{spec_dir}`, which moves to the "
                f"spec leg: it must read across the assembly root — "
                f"`../{spec_path}/{spec_dir}` relative to `{code_path}/` — or "
                "take the path from the environment")
        if len(hits) > 8:
            out.append(f"… and {len(hits) - 8} more file(s) under the code leg "
                       f"naming `{spec_dir}`")
    return out


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
# A leg's mount path is CANONICAL, or it is refused (#169)
# ---------------------------------------------------------------------------
#
# `plan --spec-path spec/` used to be accepted, written into the plan and
# passed by `check`. `execute` then ran `git submodule add ... spec/`, which
# Git records at `spec`, and `git config -f .gitmodules submodule.spec/.url`,
# which writes a SECOND section literally named `spec/` that no mount owns: the
# registration the real mount carries still pointed at the operator's local
# work directory, and on `main` the run ended `adoption verified`. A broken
# assembly passed as a good one.
#
# THE FIX IS TO REFUSE, NEVER TO REWRITE. A plan is a file a human or an AI
# edits on purpose, and a value quietly changed on its way to `git` is a value
# nobody chose: `spec/` silently becoming `spec` would be right today and the
# next spelling would not be. So the three places that read a leg path --
# `plan` (the flag), `check` (a finding) and `execute` (a refusal) -- ask the
# ONE question below, and where a canonical spelling exists the answer NAMES it
# so the person is a retype away from a plan that passes.
#
#   CANONICAL = a relative POSIX path of one or more segments, each non-empty
#   and neither `.` nor `..`: no leading `/` or `./` (nor a drive letter), no
#   trailing `/`, no `//`, no backslash. The two legs also take DIFFERENT
#   paths, neither inside the other (`legs` and `legs/spec`): Git records one
#   gitlink at the outer path and cannot record a mount inside it. Two paths
#   that differ only in case are ONE path on a macOS or Windows disk, so
#   `Spec` and `spec`, or `Legs/spec` and `legs`, are equal or nested too.
#
# A canonical path can still be one Git cannot mount a leg at, so it is also
# refused, and offered no spelling (it names no place Git can record, and
# picking another for the person is the rewrite this refuses):
#
#   * a segment that is `.git`, `git~1` (its Windows 8.3 short name) or
#     `.gitmodules`, in any case. `git submodule add` refuses `.git`, `.GIT`,
#     `git~1` and `.gitmodules`, and at `legs/.git` it exits 0 and records NO
#     gitlink, so the run ends `adoption verified` over an assembly with no
#     mount for that leg;
#   * a segment Windows cannot check out as written: one ending in a dot or a
#     space, which it strips, or a device name (`CON`, `PRN`, `AUX`, `NUL`,
#     `COM1`-`COM9`, `LPT1`-`LPT9`, with or without an extension);
#   * a value `checked_value` would refuse (whitespace, non-ASCII text, a
#     leading `-`, `C:spec`, a shell metacharacter), so that `plan` and
#     `check` say what `execute` was always going to say instead of `check`
#     passing a plan `execute` then refuses. The alphabet is `checked_value`'s
#     own (`SAFE_ARG_RE`): it is asked here, not copied.

#: Git's own names, casefolded: a leg cannot be mounted at a segment spelled
#: like one. `git~1` is how an NTFS disk shortens `.git`.
GIT_OWN_NAMES = frozenset({".git", "git~1", ".gitmodules"})

#: A Windows device name, with or without an extension: `CON`, `nul`,
#: `COM1.txt`. A file or directory called one cannot be created there.
WINDOWS_DEVICE_RE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?",
                               re.IGNORECASE)

#: What a plan's non-text `spec_path` was read as. The YAML reader keeps no raw
#: text (`007` is read as 7, `true` and `True` as one boolean, `1.50` as 1.5),
#: so a sentence that echoed the parsed value would show something the file
#: never said; it names the KIND the reader made of it instead.
NOT_TEXT_KINDS = {bool: "true or false", int: "a number", float: "a number",
                  list: "a list", dict: "a mapping"}

LEG_PATH_REMEDIATION = (
    "Remediation: nothing here rewrites a path for you, so correct the value "
    "yourself. A leg path is relative and POSIX: one or more plain segments "
    "such as `spec` or `legs/spec`, with no leading `/` or `./`, no trailing "
    "`/`, no `//`, no `..` and no backslash; no segment is one of Git's own "
    "names (`.git`, `git~1`, `.gitmodules`, in any case), ends in a dot or a "
    "space, or is a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, "
    "`COM1`-`COM9`, `LPT1`-`LPT9`, with or without an extension); the whole "
    f"value matches {SAFE_ARG_RE.pattern} and does not begin with `-`; and "
    "the two legs take different paths, neither inside the other, whatever "
    "the case."
)


def _spelling_reason(text: str) -> str | None:
    """Why `text` is not a CANONICAL spelling of a leg path, or None."""
    if not text:
        return "it is empty"
    if text.startswith("/") or WINDOWS_ABSOLUTE_RE.match(text):
        return ("it is absolute (`/spec` on every platform, `C:/spec` on "
                "Windows), and a leg is mounted INSIDE the assembly root, so "
                "its path is relative to it")
    if "\\" in text:
        return "it has a backslash, and a path here is written with `/`"
    segments = text.split("/")
    if ".." in segments:
        return ("it has a `..` segment, so it names a different place than it "
                "spells and can climb out of the assembly root")
    if all(segment in ("", ".") for segment in segments):
        return ("it names the assembly root itself, and a leg is mounted "
                "INSIDE the root, not at it")
    if "" in segments or "." in segments:
        return ("Git records a mount without its `.` segments (a leading "
                "`./`), a trailing `/` or a doubled `/`, so the mount and its "
                "`.gitmodules` entry would name two different paths")
    return None


def _unmountable_reason(text: str) -> str | None:
    """Why a leg cannot be mounted at `text`, a path that is already
    canonical: a name Git keeps for itself, or one Windows cannot check out as
    written. None when it can."""
    for segment in text.split("/"):
        if segment.casefold() in GIT_OWN_NAMES:
            return (f"`{segment}` is one of Git's own names (`.git`, its "
                    "Windows short name `git~1`, `.gitmodules`, in any case), "
                    "and Git either refuses to mount a leg at it or records "
                    "no mount there")
        if segment.endswith((".", " ")):
            return (f"`{segment}` ends in a dot or a space, which Windows "
                    "strips, so the mount would be checked out there under "
                    "another name")
        if WINDOWS_DEVICE_RE.fullmatch(segment):
            return (f"`{segment}` is a Windows device name (with or without "
                    "an extension), which cannot be created there")
    return None


def _canonical_spelling(text: str) -> str | None:
    """The canonical spelling of `text`, where one exists, else None.

    Only a SPELLING is offered: dropping empty and `.` segments says the same
    relative path in the one form Git keeps. A backslash becomes `/` because
    that is the one thing a person who typed it can mean: on Git for Windows
    it IS a separator, while on POSIX it is an ordinary filename character and
    the same string names another path, so the `/` spelling is offered for
    retyping and is not a claim that the two are equal everywhere. An absolute
    path and one with a `..` have no such spelling -- they name another place,
    and picking it for the person is the rewrite this refuses -- and neither
    has a result this check, or `checked_value`, would itself refuse
    (`./.git` is not answered `.git`, nor `-x/` `-x`).
    """
    if text.startswith(("/", "\\")):
        return None
    kept = [s for s in text.replace("\\", "/").split("/")
            if s not in ("", ".")]
    if not kept or ".." in kept:
        return None
    candidate = "/".join(kept)
    if _unmountable_reason(candidate) is not None:
        return None
    try:
        return checked_value("leg path", candidate)
    except Refusal:
        return None


def leg_path_problem(what: str, value) -> str | None:
    """One leg's mount path: None when it is one `execute` will mount, else
    the sentence that says what is wrong with it and, where one exists, what
    to write instead.

    Asked in this order: the SPELLING (canonical or not), then the NAMES Git
    and Windows keep, then the alphabet `checked_value` allows on a command
    line, so that `plan`, `check` and `execute` refuse the same values.

    `what` is how the caller names the value -- `--spec-path`, or
    `legs.spec_path` for one read out of a plan -- so the sentence points at
    the thing the person has in front of them.
    """
    if not isinstance(value, str):
        kind = NOT_TEXT_KINDS.get(type(value), "something that is not text")
        return (f"{what} is not text: its value was read as {kind}, and a "
                "path is written as text, so quote it")
    spelling = _spelling_reason(value)
    if spelling:
        offered = _canonical_spelling(value)
        return (f"{what} is {value!r}, which is not a canonical leg path: "
                f"{spelling}." + (f" Write {offered!r}." if offered else ""))
    unmountable = _unmountable_reason(value)
    if unmountable:
        return (f"{what} is {value!r}, which a leg cannot be mounted at: "
                f"{unmountable}.")
    try:
        checked_value(what, value)
    except Refusal as exc:
        return f"{exc.detail}."
    return None


def leg_path_problems(spec: tuple, code: tuple) -> list[str]:
    """Everything wrong with the two leg paths, as sentences; `[]` when none.

    `spec` and `code` are `(what, value)` pairs. The pair is compared only
    when each path is fine on its own, because "equal" and "inside" are
    statements about paths and mean nothing for two strings that are not one.
    They are compared WITHOUT regard to case: a macOS or Windows disk keeps
    one of `Spec` and `spec`, and the second mount would collide there AFTER
    both leg repositories exist.
    """
    problems = [p for p in (leg_path_problem(*spec), leg_path_problem(*code))
                if p]
    if problems:
        return problems
    (spec_what, spec_path), (code_what, code_path) = spec, code
    if spec_path == code_path:
        return [f"{spec_what} and {code_what} are both {spec_path!r}, and two "
                "legs cannot be mounted at one path."]
    if spec_path.casefold() == code_path.casefold():
        return [f"{spec_what} {spec_path!r} and {code_what} {code_path!r} "
                "differ only in case, which a macOS or Windows disk keeps as "
                "ONE path, so two legs cannot be mounted at them."]
    for (inner_what, inner), (outer_what, outer) in ((spec, code),
                                                    (code, spec)):
        if inner.casefold().startswith(outer.casefold() + "/"):
            aside = ("" if inner.startswith(outer + "/") else
                     " once case is ignored, as a macOS or Windows disk does")
            return [f"{inner_what} {inner!r} is inside {outer_what} "
                    f"{outer!r}{aside}, and Git records ONE gitlink at the "
                    "outer path, so the inner leg cannot be mounted there."]
    return []


def _refuse_bad_leg_paths(refusal: str, spec: tuple, code: tuple) -> None:
    """Raise `Refusal(refusal)` naming every problem found in the two paths."""
    problems = leg_path_problems(spec, code)
    if problems:
        raise Refusal(refusal, " ".join(problems), LEG_PATH_REMEDIATION)


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
    _refuse_bad_leg_paths("adopt-bad-leg-path",
                          ("--spec-path", args.spec_path),
                          ("--code-path", args.code_path))
    args.spec_path = checked_value("--spec-path", args.spec_path)
    args.code_path = checked_value("--code-path", args.code_path)
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
    args.elected_by = args.elected_by or _elector()
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
    print(f"source     {source.repository or source.path} @ "
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
    unresolved = [e for e in entries if e.leg is None]
    print(f"\nplan written to {out}")
    if unresolved:
        print(f"{len(unresolved)} path(s) need a human or an AI to answer a "
              "question before `execute` will run:")
        for entry in unresolved:
            print(f"  {entry.path}\n      {entry.question}")


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
    ruled = walk(policy, [(path, size) for path, _, _, size in tree])
    materialized = _predict_collisions(ruled)
    follow_ups = follow_ups_for(source, ruled, names, args.spec_path,
                                args.code_path, materialized)
    seeded = seeded_legs(assigned_paths(ruled))
    entries = ask_about_submodules(policy, ruled, tree)
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
        print(f"{entry.path:<34} {(entry.leg or 'REVIEW'):<10} "
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
    """
    surviving = {e.path for e in entries if e.leg == "root"}
    from shape_materialize import COPIED_FROM_SHAPE, COPIED_VERBATIM, TEMPLATED
    shape_paths = [dst for _, dst in COPIED_FROM_SHAPE] + \
        list(COPIED_VERBATIM) + list(TEMPLATED)
    out = []
    for path in sorted(set(shape_paths)):
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
    """
    findings: list[str] = []
    duplicates = sorted({p for p in entry_paths if entry_paths.count(p) > 1})
    for path in duplicates:
        findings.append(f"FINDING plan-duplicate-path: {path} appears "
                        f"{entry_paths.count(path)} times")
    uncovered, multiple = [], []
    for path in tree_paths:
        covering = _covering(entry_paths, path)
        if not covering:
            uncovered.append(path)
        elif len(covering) > 1:
            multiple.append((path, covering))
    for path in uncovered[:20]:
        findings.append(f"FINDING plan-uncovered: {path} is in the source "
                        "tree and in no plan entry")
    if len(uncovered) > 20:
        findings.append(f"FINDING plan-uncovered: … and {len(uncovered) - 20} "
                        "more uncovered paths")
    for path, covering in multiple[:20]:
        findings.append(f"FINDING plan-covered-twice: {path} is covered by "
                        f"{covering}")
    used = {p for path in tree_paths for p in _covering(entry_paths, path)}
    for path in sorted(set(entry_paths) - used):
        findings.append(f"FINDING plan-empty-entry: {path} covers nothing in "
                        "the source tree at this commit")
    return findings


def _leg_findings(plan: Plan) -> list[str]:
    """`leg:` is answered with one of the four words, and each leg's mount
    path is canonical (#169).

    The path findings live HERE, and not in `cmd_check`, so that whatever
    reads this function reports a bad path from the one place that knows what
    a canonical one is.
    """
    findings: list[str] = []
    # Only a `legs:` MAPPING has mount paths to check. The doctor's PLACEMENT
    # plan is the caller whose `legs:` is a LIST (one record per audited leg,
    # no `spec_path`), and it asks this function only about its entries; a
    # finding about leg paths there would name a key the plan never had.
    if isinstance(plan.legs, dict):
        findings = [f"FINDING plan-bad-leg-path: {problem}"
                    for problem in leg_path_problems(*_plan_leg_paths(plan))]
    for entry in plan.entries:
        leg = entry.get("leg")
        if leg is None:
            findings.append(
                f"FINDING plan-unresolved: {entry.get('path')} still has "
                f"`leg: null`. The question was: {entry.get('question')}")
        elif str(leg) not in LEG_VALUES:
            findings.append(
                f"FINDING plan-bad-leg: {entry.get('path')} declares leg "
                f"{leg!r}; it is one of {list(LEG_VALUES)}")
    return findings


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
    "source and re-planned the same way (in a source with no submodule, "
    "dropping it is enough). "
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
    """`path`, and the plan entry to edit when that is a directory above it."""
    return path if entry == path else f"{path} (entry {entry})"


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
        `validate.yml` reads every URL in that file as a leg; a root
        `.gitmodules` the plan kept fails verification today whatever it
        registers (#165).
      * A `.gitmodules` git cannot read for its submodules is never taken to
        register nothing (`plan-gitmodules-unreadable`, saying what git
        said, and where git fails on it: `_where_git_fails`). Beside a
        submodule it fails the extraction of either leg, wherever the plan
        sends the two; otherwise it is a problem where the plan keeps it, or
        a gitlink, in a leg the assembly's clone then recurses into.
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
    failure = _where_git_fails(entries, tree, registry_leg, kept)
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
        `.gitmodules` for each gitlink in the history it exports. So such a
        FILE in a source that holds a submodule fails the extraction of
        either leg, wherever the plan sends the two -- after both leg
        repositories were made. A plan that extracts no leg, every path
        rooted or dropped, is the only one that escapes it.
      * Otherwise the assembly's recursive clone fails in a leg the plan
        keeps the file in, or a gitlink: on a line git cannot parse, even
        with no gitlink in the leg, and on a `.gitmodules` that is itself a
        gitlink, which the clone checks out as a directory and which
        registers nothing.

    A key with no value is fatal to git's submodule reader alone, which
    git runs only for a gitlink, so `Source.registered_submodules` reads it
    as registering nothing in a tree with none, and it never reaches here
    without one.
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


def _submodule_findings(plan: Plan, source: Source,
                        tree: list) -> tuple[list[str], list[str]]:
    """`submodule_plan_problems` as `check` prints them, one FINDING each,
    and what to print ONCE after every finding: SUBMODULE_REMEDIATION when
    there is one of these, nothing when there is none. `check` is where the
    person is told to fix the plan, so it says how, in the words `execute`'s
    refusal would use one step later."""
    found = [f"FINDING {code}: {detail}" for code, detail
             in submodule_plan_problems(plan.entries, tree,
                                        source.registered_submodules(tree))]
    return found, [SUBMODULE_REMEDIATION] if found else []


def _entry_findings(plan: Plan, source: Source
                    ) -> tuple[list[str], list[str]]:
    """Every FINDING `check` prints about the plan's ENTRIES, in its order,
    and what it prints once after them: coverage, then each entry's `leg:`,
    then the source's own submodules.

    ONE LIST, read by `check` and by `execute`'s `_refuse_what_check_finds`.
    #168 and #166 each added findings to `check` and a refusal to `execute`
    while both were open, and composed them separately so as not to edit the
    same lines; three compositions then disagreed, and a plan `check`
    rejected as uncovered AND split was refused by `execute` for the split
    alone, to be refused again for the rest once that was fixed. Composed
    once, the two commands cannot differ about a plan.
    """
    tree = source.tree()
    findings = (_coverage_findings([str(e.get("path")) for e in plan.entries],
                                   [path for path, _, _, _ in tree])
                + _leg_findings(plan))
    submodule_findings, remediation = _submodule_findings(plan, source, tree)
    return findings + submodule_findings, remediation


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
    print(f"\nWHAT WILL HAPPEN, against {source.repository or source.path} @ "
          f"{source.commit[:12]}:")
    print(f"  create {names['spec']} and {names['code']} "
          f"({plan.get('visibility', 'private')})")
    print(f"  extract {len(moved)} path(s) with `git filter-repo`, history "
          "preserved")
    for role in seeded:
        print(f"  SEED the {role} leg from {SEED_TEMPLATE[role]}/ — no path is "
              "assigned to it")
    print(f"  ONE split commit on branch {plan.get('adopt_branch', ADOPT_BRANCH)} "
          f"of {names['assembly']}: `git rm -r` those paths, mount the legs at "
          f"{_plan_leg_path(plan, 'spec')}/ and "
          f"{_plan_leg_path(plan, 'code')}/")
    print(f"  {len(stays)} path(s) stay in the assembly root; "
          f"{len(drops)} dropped")
    print("  the source is never deleted, never renamed, never force-pushed")
    print(_topics_line(topic, local))
    for item in plan.get("follow_ups", []):
        print(f"  follow-up: {item}")


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
            f"{plan.source_commit[:12]} but {source.branch} is now at "
            f"{source.commit[:12]}. Re-run `plan`: a coverage check against a "
            "tree that has moved proves nothing about the tree that will be "
            "split.")

    entry_findings, remediation = _entry_findings(plan, source)
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
                               capture_output=True, text=True, check=False)
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
            + ", ".join(str(e.get("path")) for e in unresolved[:8]),
            "Remediation: answer each entry's `question:` by setting `leg:` "
            "and adding a `resolution:` line, then run `check`. An unanswered "
            "question is never an implicit `root`.")
    if plan.source_commit and source.commit != plan.source_commit:
        raise Refusal(
            "plan-stale",
            f"the plan was written against {plan.source_commit[:12]} and "
            f"{source.branch} is now at {source.commit[:12]}",
            "Remediation: re-run `plan`, re-answer anything new, then "
            "`check`. Splitting a tree the plan has not seen is how a path "
            "goes missing.")


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
    write_lf(listing, "\n".join(paths) + "\n")
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
    """
    del branch
    copy_tree(SHAPE_ROOT / SEED_TEMPLATE[role], work, values)
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
        tracking).lower()
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
    for path in removed:
        run(["git", "rm", "-r", "-q", "--", path], cwd=assembly)
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
    # both, not a shape a plan may choose; such a file still fails
    # verification (#165).
    if GITMODULES in removed:
        write_lf(assembly / GITMODULES, "")
        run(["git", "add", "-f", "--", GITMODULES], cwd=assembly)
    for role, path in (("spec", spec_path), ("code", code_path)):
        run(["git", *FILE_PROTOCOL, "submodule", "add", "-q",
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
    local = args.local_remote_dir is not None
    org = checked_value("org", plan.get("org"))
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    if local:
        # NOT created yet: nothing exists on disk until the human has said
        # yes, so a refused run leaves the directory it would have used
        # absent rather than empty.
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
        urls["assembly"] = str(source.path)
    else:
        urls = {role: f"https://github.com/{org}/{name}.git"
                for role, name in names.items()}
    return local, repositories, urls


def _leg_paths(plan: Plan) -> dict:
    """Every plan entry's path, by the leg it was assigned to.

    Each one is checked because it reaches `git filter-repo` as an argument.
    Split out of `cmd_execute` for #138.
    """
    return {leg: [checked_value("a plan path", e.get("path"))
                  for e in plan.entries if str(e.get("leg")) == leg]
            for leg in LEG_VALUES}


#: How many of `check`'s findings the one refusal below spells out; the rest
#: are a count, as `plan-unresolved` names eight paths and not every one.
REFUSED_FINDINGS_SHOWN = 8


def _refuse_what_check_finds(plan: Plan, source: Source) -> None:
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
    prints, so the two commands cannot disagree about what a plan covers.
    The refusal's code is the FIRST finding's own (`plan-uncovered`, ...);
    its detail is every finding as `check` prints it, capped at
    `REFUSED_FINDINGS_SHOWN` with an "and N more" tail; its remediation is
    this one, then whatever `check` prints after its findings -- #166's
    submodule remediation, when one of them is a submodule problem.

    THE ORDER IS PART OF THE FIX. This runs AFTER `_refuse_an_unrunnable_plan`:
    `_leg_findings` also reports `plan-unresolved`, which that function has
    already refused in its own words, and a plan written against a tree that
    has since moved is `plan-stale`, not whatever its stale coverage happens
    to lack. And it runs AFTER `_leg_paths` has checked, as a safe `git`
    argument, the path of every entry whose `leg:` is one of the four words,
    because a path that is an option is `unsafe-value` and must stay that, not
    become an uncovered file. An entry with any other `leg:` is not checked
    there and reaches no `git` command; it is refused here, under whichever
    finding `check` lists first. It runs BEFORE `_refuse_unconsented_seeding`,
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
    after `_leg_paths` has checked every path as a `git` argument.
    """
    findings, remediation = _entry_findings(plan, source)
    if not findings:
        return
    # `FINDING <code>: <detail>` is the one shape both functions write.
    code = findings[0].split()[1].rstrip(":")
    lines = [f"{len(findings)} finding(s) in {plan.path}, as `check` prints "
             "them:"]
    lines += [f"  {finding}" for finding in findings[:REFUSED_FINDINGS_SHOWN]]
    if len(findings) > REFUSED_FINDINGS_SHOWN:
        lines.append(f"  and {len(findings) - REFUSED_FINDINGS_SHOWN} more")
    raise Refusal(
        code, "\n".join(lines), "\n".join([
            "Remediation: no leg repository was created and nothing was "
            "pushed. Correct the plan -- answer each entry's `leg:` and cover "
            "every source path exactly once -- and run `check` until it "
            "prints `plan ok`, then run `execute` again. A leg made from a "
            "plan `check` rejects is one the corrected plan cannot make "
            "again: under `--local-remote-dir` it meets `leg-remote-exists`.",
            *remediation]))


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


def _open_the_pull_request(repositories: dict, names: dict, tracking: str,
                           branch: str, message: str) -> bool:
    """(c′) The pull request, because these organisations are pull-request
    only.

    Returns False when `gh` refused, having printed why and the command that
    finishes the job by hand — the branch IS pushed by the time this runs, so
    the exit is never "start again". Split out of `cmd_execute` for #138.
    """
    try:
        url = run(["gh", "pr", "create", "--repo", repositories["assembly"],
                   "--base", tracking, "--head", branch,
                   "--title", f"Adopt the three-repository shape: "
                              f"{names['spec']} and {names['code']}",
                   "--body", message])
        print(f"  pull request {url}")
    except CommandFailed as exc:
        print(exc.loudly("opening the pull request"), file=sys.stderr)
        print("The branch IS pushed. Open the pull request by hand:\n"
              f"    gh pr create --repo {repositories['assembly']} "
              f"--base {tracking} --head {branch}", file=sys.stderr)
        return False
    return True


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
    """
    run(["git", "add", "-A", "--", "."], cwd=assembly)
    landed = (_where_it_landed(assembly, written)
              for written in materialized.written)
    run(["git", "add", "-f", "--", *(path for path in landed if path)],
        cwd=assembly)


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


#: The key `execute` appends to the assembly's `project.yaml` (#189). The
#: doctor reads it by this name through the module it loads, and the
#: project's own `validate-manifest.py`, which imports nothing of this tool's,
#: spells it once more.
SUBMODULE_RECORD = "submodules"

#: The comment above that block, in the manifest itself, because the
#: manifest is read by people who never saw the plan it came from.
SUBMODULE_RECORD_PREAMBLE = (
    "",
    "# THE SOURCE'S OWN SUBMODULES, and the leg each one was ANSWERED into",
    "# when this repository was adopted (#189). Written once, by",
    "# `adopt-project.py execute`, from the adoption plan: one row per",
    "# submodule the split kept in a leg, its path inside that leg, the",
    "# `resolution:` the plan gave the entry that covered it, and the source",
    "# commit the plan was answered at. `shape-doctor.py` checks each",
    "# submodule a leg holds against it. Like every field here, it confers",
    "# nothing.",
    f"{SUBMODULE_RECORD}:",
)


def _quoted(text: str) -> str:
    """`text` as a double-quoted scalar of `repo_shape.parse_yaml`'s subset.

    ALWAYS QUOTED, unlike `y`: a submodule may sit at `null`, `true` or
    `0001`, which a plain scalar would read back as something that is not
    a path. A newline and a tab are escaped as the reader resolves them,
    and any other character that is not printable is SPELLED, `\\x07` or
    `\\xe9` for a byte that is not UTF-8, because `write_lf` writes UTF-8
    and a surrogate in the text would stop `execute` after both legs exist.
    A spelled path is one the doctor does not read either: it reports such
    a name as one no report can carry.
    """
    out = []
    for char in text:
        if char in '\\"':
            out.append("\\" + char)
        elif char in "\n\t":
            out.append("\\n" if char == "\n" else "\\t")
        elif char.isprintable():
            out.append(char)
        elif "\udc80" <= char <= "\udcff":
            out.append(f"\\x{ord(char) - 0xDC00:02x}")
        else:
            out.append(ascii(char)[1:-1])
    return '"' + "".join(out) + '"'


def submodule_record(entries: list, tree: list, commit: str) -> str:
    """The `submodules:` block `execute` appends to `project.yaml`, or ""
    when the split keeps no submodule of the source's in a leg (#189).

    WHY THE ANSWER IS WRITTEN DOWN. Which leg holds a source submodule is a
    human's answer under #166 -- `plan` asks it of every entry that covers a
    gitlink, whatever rule its name matches -- and the plan that carries the
    answer is not committed anywhere. Without a record, the assembly holds
    `.cursor` in the code leg and nothing else, and `shape-doctor.py` cannot
    tell that answer from a submodule added by hand, so the most it can say
    is a note. With one, a submodule in the leg recorded is placed and one in
    the other leg is MISPLACED, with the manifest as the evidence.

    ONE ROW PER GITLINK KEPT IN A LEG, from `_answered_legs`, the reading
    `check` holds the plan to: by the time `execute` calls this,
    `_refuse_what_check_finds` has refused a gitlink no entry covers, one
    covered twice, one left unanswered and one answered `root`. A gitlink
    answered `drop` is in no leg, so nothing can be checked against it, and
    one added at that path later is a gitlink no record covers. The path is
    the gitlink's path in the source, which `git filter-repo` keeps as its
    path in the leg. `resolution:` is written when the plan's entry has one;
    a directory entry's answer covers every gitlink under it, so each row
    carries that entry's line.

    A SOURCE WITH NO SUBMODULE GETS "" and so the `project.yaml` -- and the
    split -- it always got, byte for byte.
    """
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    kept = _kept_in_a_leg(_answered_legs(entries, gitlinks), gitlinks)
    if not kept:
        return ""
    resolutions = {str(e.get("path")): _resolution_text(e.get("resolution"))
                   for e in entries}
    lines = list(SUBMODULE_RECORD_PREAMBLE)
    for path, leg, entry in kept:
        lines.append(f"  - path: {_quoted(path)}")
        lines.append(f"    leg: {leg}")
        if resolutions.get(entry):
            lines.append(f"    resolution: {_quoted(resolutions[entry])}")
        lines.append(f'    source_commit: "{commit}"')
    return "\n".join(lines) + "\n"


def _resolution_text(resolution) -> str | None:
    """A plan entry's `resolution:` as the text the record carries, or None.

    A scalar is written as the plan's reader returned it. A blank one is no
    reason, and a mapping or a list under the key is not one line of text,
    so neither is written: the record's `resolution:` is optional, and a row
    without one still says where the submodule was answered into.
    """
    if resolution is None or isinstance(resolution, (dict, list)):
        return None
    text = str(resolution)
    return text if text.strip() else None


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
    run(["git", *FILE_PROTOCOL, "clone", "-q", str(source.path), str(assembly)])
    run(["git", "checkout", "-q", "-B", branch, source.commit], cwd=assembly)
    _mount_the_legs(assembly, work_root, names, urls, paths_for, spec_path,
                    code_path)

    # The plan's submodule answers outlive the plan only here (#189). An
    # empty record appends nothing, so a source with no submodule gets the
    # manifest it always got.
    append = {"Makefile": ADOPT_MAKEFILE_BLOCK}
    record = submodule_record(plan.entries, source.tree(), source.commit)
    if record:
        append["project.yaml"] = record
    materialized = materialize_assembly_root(
        SHAPE_ROOT, assembly, values, collision_dir=COLLISION_DIR,
        append=append)
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
    paths_for = _leg_paths(plan)
    _refuse_what_check_finds(plan, source)

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

    topics_failed = False
    if not local:
        if not _open_the_pull_request(repositories, names, tracking, branch,
                                      message):
            return 2
        topics_failed = not _set_the_topic(repositories, topic)

    # ---- (d) verification, by blob sha ------------------------------------
    verified = _verify(source, assembly, work_root, names, paths_for,
                       split_commit, seeded)
    if verified:
        return verified   # a verification mismatch outranks a missing topic
    return 2 if topics_failed else 0


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
            paths_for, split_commit: str, seeded=()) -> int:
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
    """
    print("\nVERIFICATION — every source path at "
          f"{source.commit[:12]}, by blob sha")
    before = {path: oid for path, _, oid, _ in source.tree()}
    after: dict[str, list[str]] = {}
    for role in ("spec", "code"):
        for path, _, oid, _ in _tree_of(work_root / names[role], "HEAD"):
            after.setdefault(path, []).append(f"{role}:{oid}")
    for path, mode, oid, _ in _tree_of(assembly, split_commit):
        if mode == "160000":
            continue
        after.setdefault(path, []).append(f"root:{oid}")

    counts, findings = _account_for(before, after, paths_for["drop"])
    findings += _shape_file_findings(assembly, split_commit)
    added = sorted(set(after) - set(before))
    for leg in ("spec", "code", "root", "drop"):
        note = " (seeded from template)" if leg in seeded else ""
        print(f"  {leg:<6} {counts[leg]:>5} of {len(before)} source "
              f"paths{note}")
    print(f"  added  {len(added):>5} new paths (manifest, pins, shape files"
          + (", seeded leg" if seeded else "") + ")")
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} verification finding(s). The legs and the "
              "branch exist; NOTHING was deleted from the source, so the exit "
              "is to fix the plan and re-run into a fresh --local-remote-dir "
              "or fresh leg repositories.", file=sys.stderr)
        return 1
    print("\nadoption verified: every source path is in exactly one place")
    print(f"\nNEXT: review the pull request on {names['assembly']}, then\n"
          f"    git clone --recurse-submodules <{names['assembly']} url>\n"
          "    make bootstrap")
    return 0


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
            findings.append(f"FINDING adopt-duplicated: {path} is in "
                            + ", ".join(landings))
        elif any(path == d or path.startswith(d + "/") for d in dropped):
            counts["drop"] += 1
        else:
            findings.append(f"FINDING adopt-lost: {path} ({oid[:12]}) is in no "
                            "leg, not in the root tree, and not listed as drop")
    return counts, findings


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
            hops, via = hops + 1, f" at the symlink {at}"
            if hops > SYMLINK_HOPS:
                raise _NotInTheSplitError(
                    f"runs round a symlink loop at {at} in the split commit "
                    f"{self.commit}")
            parts = self._parts(target, via) + parts
        return "/".join(done)

    def _parts(self, target: str, via: str) -> list[str]:
        if target.startswith("/"):
            raise _NotInTheSplitError(
                f"leads out of the split commit {self.commit}{via}, to "
                f"{target}")
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
                f"passes through {here}, which is not a directory in the "
                f"split commit {self.commit}")
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
    file the pin names."""
    return (f"FINDING adopt-shape-file-missing: {path} {why}, so the "
            f"assembly's first `make bootstrap` refuses with {refusal}. "
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
