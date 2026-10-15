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
           `adoption-plan.yaml`, with that branch as the tracking branch
           unless `--tracking-branch` names another (#479). Paths it cannot
           honestly call, every path holding one of the source's own
           submodules, and every path `execute` will not extract into a leg
           as it is named, carry `leg: null`, `review_required: true` and
           the QUESTION to ask. A question whose rule names a default
           carries that default as its `leg:` instead, still
           `review_required: true`: the source's own `single-repository.yaml`
           record, `drop` (#528).
           A leg path over a path it keeps in the root itself is a NOTE,
           not a refusal: the answer is the person's to change. A
           `--pin <product>@<40 hex>` is read as `scaffold-project.py
           --pin` reads it, its digest included, and recorded in the plan,
           and `execute` writes its `contracts/<product>-pin.yaml`; `check`
           finds, and `execute` refuses, a pin the plan does not record
           whole (#273). Where the source names a repository, `--org` and
           `--project` name that one, compared without case, or `plan`
           refuses them (`adopt-not-the-source`), and `check` finds and
           `execute` refuses a plan edited to name another
           (`plan-not-the-source`): in place, the source IS the assembly
           root, and its own name is renamed first, on GitHub, never
           retyped (#499).
  check    validates a plan against the source: each entry path bound for
           a leg one `execute` will extract, no symlink in the source with
           an empty target (Linux cannot make one, so a clone there checks
           none out, whatever the plan answers), every path covered exactly
           once, no unresolved legs, leg names conforming to the naming
           policy, each leg's mount path one `execute` can mount
           (`spec`, `legs/spec`; never `spec/` or `./spec`, a name Git or
           Windows keeps for itself such as `.git` or `CON`, or a value
           `execute` would refuse; the two never equal or nested, in any
           case; neither equal to, around or inside a path the shape writes
           into the root, `shape/`, or a source path the plan keeps there),
           no path kept in the root where the shape writes (a plain file at
           a directory it writes into, `.github`, `contracts` or `scripts`,
           the source's own `project.yaml`, where it writes its manifest,
           or the source's own path at a copy it writes under `shape/`, in
           any case), every value `execute` writes into the project's YAML
           (`id`, the branch, the leg paths, the pins, the election record)
           one its loader reads back as that same text, which `null`, `true`
           and `2026` are not where a line is written bare (since #259 and
           #514 no line `execute` writes them into is) (#181), and
           the source's own submodules kept on one leg with their
           `.gitmodules`, registered there and never in the root, each
           relative url naming the same repository from the leg as from the
           source, no symlink kept in the root that the shape would write
           one of its files, or that file's copy under `shape/`, through
           where it cannot (one that dangles, loops, or leads out of the
           root or into a leg, one that leads the copy onto something
           already there, or one that carries the shape's scripts anywhere
           but one directory directly under the root), whether the disk
           keeps case or ignores it, the tracking branch a branch of the
           source, which the pull request is opened against, and the split
           branch one `execute` can make: none of its name where the split
           is pushed that the push cannot fast-forward, and none git cannot
           hold beside it there or in the source. Each pin's digest is
           recomputed at its commit in the clone `plan` read it from, where
           that clone is still on this machine, with no network: a partial
           clone (`git clone --filter`), whose `git` would fetch what it
           lacks, is not asked, and a NOTE names each pin it was not
           rechecked for (#449). It prints what will happen and changes
           nothing.
  execute  creates the two legs, extracts them with `git filter-repo`, makes
           the one split commit on a branch of the source, sets the
           `xf-project-<id>` topic on all three and then opens the split's
           pull request against the tracking branch (both skipped for local
           remotes), and then VERIFIES by blob sha that every source path
           landed in exactly one place, and that the root's only submodules
           are the two leg mounts, each at the commit pushed to its leg. The
           split's `project.yaml` records the leg each source submodule kept
           in a leg was answered into, under `submodules:`, for
           `shape-doctor.py` to check it against.

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

THE NEW PROJECT MUST BE ABLE TO HOLD WHAT `execute` WRITES INTO IT (#261).
`execute` puts the plan's values into the root's `project.yaml`, and the
project's own `scripts/validate-manifest.py` judges them at its first
bootstrap. So `plan` refuses, `check` finds and `execute` refuses a value that
validator would refuse -- a blank `elected_by` or `reference`, an `elected_on`
that is not `YYYY-MM-DD`, an organisation name it cannot hold, a `visibility`
other than `private`, `public` or `internal` -- asking the validator itself,
loaded from the template it ships, and not a copy of its rules. A name that
cannot be a directory's (a `--project` that makes a repository name of 256
bytes with its `.git`) is refused the same way.

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
create` refused (`The branch IS pushed`) and the topic would not set (`The
split IS pushed and the pull request IS open`, or beside a refused pull
request, under `The branch IS pushed`). The topic is set first, so a refused
pull request no longer leaves it unset (#481), and both are said in ONE notice
after the table, each with the commands that finish the job by hand; those
commands are the way out: a re-run into fresh legs abandons the pushed pair
for a second. A verification that fails outranks both, with exit 1 and no
command to open the pull request or to set the topic; it says what the run
already put in place, the pull request open for the failed split, which
deleting the split branch closes, and the topic, which stays set (#523).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import itertools
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
    free_plan_secret_hint, REMEDIATION,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, YamlError,
    accepts_role, checked_value, double_quoted, git_out, load_yaml,
    parse_yaml, redacted, remote_is_a_path, remote_key, remote_local_path,
    tree_digest,
)
from shape_materialize import (  # noqa: E402
    PLACEHOLDER_RE, SHAPE_REPOSITORY, SYMLINK_HOPS,
    TEMPLATED, TOO_MANY_SYMLINKS, CommandFailed, Materialized,
    adopt_makefile_block, assembly_root_paths, collision_follow_up, copy_tree,
    default_reference,
    election_date, env_commit, escape_what_stdout_cannot_encode,
    git_init_commit, materialize_assembly_root, naming_block, render, run,
    template_files, write_lf,
    write_paths_listing,
)
# The leg-path rule (#179) is `scaffold-project.py`'s as much as adopt's, so it
# is imported as one unit and not listed among the materializer's names above.
# `tests/test_adopt_leg_paths.py` asks `leg_path_problem` through this module,
# as it did when the rule was defined in it, which is what shows the move
# changed no behaviour; `_plan_fields` asks it too, and `_the_loader_made`
# names a list or a mapping the loader read in `NOT_TEXT_KINDS`'s words, the
# two kinds it has no words of its own for (#181).
from shape_materialize import (  # noqa: E402
    NOT_TEXT_KINDS, WINDOWS_ABSOLUTE_RE, leg_path_problem, leg_path_problems,
    refuse_bad_leg_paths as _refuse_bad_leg_paths,
)
import shape_advisory  # noqa: E402
# #172's shape half, shared with the scaffold since #197 (see that section
# below), under the names this file has always called it by.
from shape_materialize import (  # noqa: E402
    CASE_ASIDE as _CASE_ASIDE, MOVE_THE_LEG, first_and_more as _first_and_more,
    path_overlap as _overlap, shape_path_collisions,
)
# The line-ending block the split appends to a source's own root
# `.gitattributes` (#471): that file's name, which copies the block names,
# the line it writes for one, and the bytes it makes of the source's own.
from shape_materialize import (  # noqa: E402
    ATTRIBUTES, eol_block_paths, eol_line, with_eol_block,
)
# What the project's own `validate-manifest.py` would say of the values written
# into its manifest, and whether a repository's name can be a directory's:
# asked of the plan's values by `plan`, `check` and `execute` (#261).
from shape_materialize import (  # noqa: E402
    MANIFEST_INVALID_REMEDIATION, manifest_judged, manifest_value_problems,
    refuse_manifest_values, refuse_unstorable_names,
)
# Whether a value this tool writes into a file is text a file can hold
# (#255), asked beside `one_printable_line`, the trailer's question.
from shape_materialize import unwritable_reason  # noqa: E402
# Whether git creates a tracking branch as it is written (#283), asked only
# of one the project's loader misreads (`_a_branch_git_creates`, #181).
from shape_materialize import branch_problem  # noqa: E402
# The shape's bootstrap script, which its `make bootstrap` runs: where it
# went beside one the source kept decides what NEXT can name (#480).
from shape_materialize import BOOTSTRAP  # noqa: E402

#: The naming policy this tool classifies leg names against. One constant,
#: because three spellings of the same path is how the second one goes stale.
NAMING_POLICY = SHAPE_ROOT / "contracts" / "repository-naming.yaml"
PATH_POLICY = SHAPE_ROOT / "contracts" / "path-classification.yaml"

#: A DECLARED PIN IS `[owner/]openProduct@<40 hex commit>`, as
#: `scaffold-project.py --pin` takes it, and `execute` writes
#: `contracts/<product lowercased>-pin.yaml` for it, as the scaffold does
#: (#273; Brett Heap, 2026-10-12). This reverses the NAME-only `--pin` of #6
#: (2026-09-03), which recorded no commit and wrote no file, so the adopted
#: root's own `validate-pins.py` refused the declaration as
#: `neutral-pin-missing` on its first run after `execute` said `adoption
#: verified`. `plan` reads each pin with the scaffold's own functions, which
#: live beside the materializer that writes the file: the argument, `--pin-owner`
#: and `--pin-source` mean what they mean there, the digest is read at `plan`
#: time (from `--pin-source`, or `gh api`), and a name with no `@<commit>`, a
#: product named `spec`, `code` or `shape`, or one product twice is refused in
#: the scaffold's words. The plan RECORDS product, repository, commit, digest
#: and how the digest was read, so `check` and `execute` read no network for a
#: pin; `check` finds, and `execute` refuses before any leg exists, a pin the
#: plan does not record whole, a name alone among them (an old plan, or an
#: edit). The manifest lists each product with its owner stripped, as the
#: file is named. Where the clone `plan` read a digest from is still on this
#: machine, and is no partial clone, `check` and `execute` recompute the
#: digest there with `plan`'s own reader (`pin_digest_from_source`), which
#: in such a clone reads no network, and find a commit or a digest edited
#: after `plan` read them (#449).
from shape_materialize import (  # noqa: E402
    PIN_ARG_RE, declared_pin_products, declared_pin_values, neutral_pin_path,
    one_printable_line, pin_collisions, pin_digest_from_source,
    pin_variable_collisions, refuse_colliding_pins,
)
from repo_shape import SHA256_RE, repo_basename  # noqa: E402

#: The keys `plan` records for each pin, in the order it writes them, and the
#: value of `contracts/neutral-product-pin.yaml` each one fills.
PIN_FIELDS = (("product", "PIN_PRODUCT"), ("repository", "PIN_REPOSITORY"),
              ("commit", "PIN_COMMIT"), ("tree_sha256", "PIN_TREE_SHA256"),
              ("digest_source", "PIN_DIGEST_SOURCE"))
#: The two a pin is a fact by. A pin without either is a name.
PIN_RECORDED = ("commit", "tree_sha256")

#: `check`'s findings about the plan's `pins:`, and the last of them about a
#: path the root keeps where `execute` writes a pin: a declared pin's file
#: (#273), or the shape's own pin (#524).
PIN_UNRECORDED = "plan-pin-unrecorded"
PIN_MALFORMED = "plan-pin-malformed"
PIN_COLLIDES = "plan-pin-collides"
ROOT_HOLDS_PIN = "plan-root-holds-pin"
#: And about a pin the clone `plan` read its digest from answers for
#: otherwise, or cannot answer for at all, at the plan's commit (#449).
PIN_DIGEST_MISMATCH = "plan-pin-digest-mismatch"
PIN_SOURCE_UNREADABLE = "plan-pin-source-unreadable"
#: How `declared_pin_values` records where it read a digest: from a clone on
#: this machine, `--pin-source` as typed, or from the forge.
LOCAL_CLONE_RE = re.compile(r"local-clone \((?P<path>.+)\)")
GH_DIGEST_SOURCE = "gh-api-tree-recursive"

#: The comment `plan` writes above `pins:`.
PINS_COMMENT = (
    "# Neutral products this project declares a pin on. A",
    "# `<Domainx><Product>` assembly root is a DESCENDANT only when",
    "# its `open<Product>` is listed here (2026-09-02). Each pin was",
    "# read by `plan --pin <product>@<40 hex commit>`: the commit, and",
    "# the `sorted-ls-tree-r-v1` digest of the product's tree there.",
    "# `execute` writes `contracts/<product lowercased>-pin.yaml` from",
    "# them, as `scaffold-project.py --pin` does, and reads no network",
    "# for them. To change a pin, re-run `plan`: a commit or a digest",
    "# edited here is one nobody read (#273).",
)


def _pin_lines(pins: dict) -> list[str]:
    """`pins:` as `plan` writes it, from `declared_pin_values`: one mapping
    per product, its commit and digest quoted so that no reader takes forty
    digits for a number."""
    if not pins:
        return ["pins: []"]
    lines = ["pins:"]
    for values in pins.values():
        for index, (key, placeholder) in enumerate(PIN_FIELDS):
            value = values[placeholder]
            lines.append(("  - " if index == 0 else "    ") + f"{key}: "
                         + (double_quoted(value) if key in PIN_RECORDED
                            else y(value)))
    return lines


def _pin_products(rows) -> list[str]:
    """The products a plan's `pins:` declares, in its order: each mapping's
    `product:`, or the name an old plan's entry was. The naming policy
    classifies the root by them; whether each entry is a pin `execute` can
    write is `_read_pins`'s question, asked by `check` and `execute`."""
    if not isinstance(rows, list):
        return []
    products = []
    for row in rows:
        if isinstance(row, dict):
            row = row.get("product")
        if isinstance(row, str) and row:
            products.append(row)
    return products


def _pin_row_problem(row: dict) -> tuple[str, str] | None:
    """`(code, why)` for a `pins:` mapping `execute` cannot write a pin file
    from, or None. `why` finishes a sentence about the entry.

    Each value is held to what `plan` writes there: the commit to
    `COMMIT_RE`, the repository and the commit together to the scaffold's own
    `PIN_ARG_RE`, owner-qualified, with the product its name, the digest to
    `SHA256_RE`, and the digest's source to one printable line."""
    missing = [key for key, _ in PIN_FIELDS if row.get(key) in (None, "")]
    unrecorded = [key for key in PIN_RECORDED if key in missing]
    if unrecorded or missing:
        return ((PIN_UNRECORDED if unrecorded else PIN_MALFORMED),
                "records no " + " and no ".join(
                    f"`{key}:`" for key in (unrecorded or missing)))
    not_text = [key for key, _ in PIN_FIELDS
                if not isinstance(row.get(key), str)]
    if not_text:
        return PIN_MALFORMED, "records " + ", ".join(
            f"`{key}: {row[key]!r}`" for key in not_text) + ", which " + (
            "is" if len(not_text) == 1 else "are") + " not text"
    product, repository, commit, digest, how = (
        row[key] for key, _ in PIN_FIELDS)
    if not COMMIT_RE.match(commit):
        return PIN_MALFORMED, (
            f"records `commit: {commit!r}`, which is not 40 hex: a tag, a "
            "branch or an abbreviated oid can be moved, and a commit cannot")
    if not (PIN_ARG_RE.match(f"{repository}@{commit}") and "/" in repository
            and repo_basename(repository) == product):
        return PIN_MALFORMED, (
            f"records `product: {product!r}` and `repository: "
            f"{repository!r}`, and `plan` records the repository as "
            "`<owner>/<openProduct>`, its name the product's")
    if not SHA256_RE.match(digest):
        return PIN_MALFORMED, (f"records `tree_sha256: {digest!r}`, which is "
                               "not 64 hex")
    if not one_printable_line(how):
        return PIN_MALFORMED, (f"records `digest_source: {how!r}`, which is "
                               "not one printable line")
    return None


def _pin_fix(name=None) -> str:
    """How every pin finding ends: the `plan` that records the pin whole,
    naming the product where the entry names one `--pin` would take."""
    if not (isinstance(name, str) and PIN_ARG_RE.match(f"{name}@{'0' * 40}")):
        name = "<openProduct>"
    return (f"re-run `plan` with `--pin {name}@<40 hex commit>`, which reads "
            "the digest there (from `--pin-source <clone>` with no network, "
            "or `gh api`) and records both, as `scaffold-project.py --pin` "
            "takes it")


def _read_pins(plan: "Plan") -> tuple[list, list[str]]:
    """`(pins, findings)` for the plan's `pins:`.

    `pins` is `(said, product, values)` for each entry `execute` can write a
    pin file from, in the plan's order and with a repeat kept, `said` naming
    the entry and `values` the `PIN_*` values its file is rendered from.
    `findings` is one FINDING for each entry it cannot: a name alone (an old
    plan's, or an edit's) or a mapping missing its commit or digest is
    `plan-pin-unrecorded`, and anything else `plan` never writes there is
    `plan-pin-malformed`."""
    rows = plan.get("pins")
    if rows is None:
        return [], []
    if not isinstance(rows, list):
        return [], [f"FINDING {PIN_MALFORMED}: `pins:` is {rows!r}, not a "
                    f"list of pins: {_pin_fix()}."]
    pins, findings = [], []
    for number, row in enumerate(rows, 1):
        if isinstance(row, str):
            # The file is named only for a name `--pin` would take, so that
            # a line break or an escape in an edited entry is never printed
            # raw; `repr` spells the entry itself.
            path = (f"`{neutral_pin_path(repo_basename(row))}` for this one"
                    if PIN_ARG_RE.match(f"{row}@{'0' * 40}") else "one")
            findings.append(
                f"FINDING {PIN_UNRECORDED}: `pins:` entry {number}, "
                f"{row!r}, is a name with no commit and no digest. `execute` "
                f"writes each declared pin's file, {path}, from the commit "
                "and the digest `plan` records, and without it the root's "
                "own `validate-pins.py` refuses the declaration "
                f"(`neutral-pin-missing`): {_pin_fix(row)}.")
            continue
        if not isinstance(row, dict):
            findings.append(
                f"FINDING {PIN_MALFORMED}: `pins:` entry {number} is "
                f"{row!r}, not a pin: {_pin_fix()}.")
            continue
        product = row.get("product")
        said = f"`pins:` entry {number}" + (
            f" ({product!r})" if isinstance(product, str) and product else "")
        problem = _pin_row_problem(row)
        if problem:
            code, why = problem
            findings.append(
                f"FINDING {code}: {said} {why}. `execute` writes the pin file "
                "from the commit and the digest `plan` records, and nothing "
                f"else: {_pin_fix(row.get('repository') or product)}.")
            continue
        pins.append((said, product, {
            placeholder: (row[key].lower() if key in PIN_RECORDED
                          else row[key])
            for key, placeholder in PIN_FIELDS}))
    typed = [(said, product) for said, product, _ in pins]
    findings += [f"FINDING {PIN_COLLIDES}: {collision} `plan` refuses such "
                 "`--pin`s as `adopt-pin-collides`: re-run `plan` with each "
                 "product once, by the name of the repository it pins."
                 for collision in pin_collisions(typed)]
    # Two products one `SHAPE_PIN_SOURCE_<PRODUCT>` names (#275): the question
    # `validate-pins.py` asks, through the same function `plan` refuses with.
    findings += [f"FINDING {PIN_COLLIDES}: {shared} `plan` refuses such "
                 "`--pin`s as `adopt-pin-collides`, and the root's own "
                 "`validate-pins.py` reports them as "
                 "`neutral-pin-source-collides`: re-run `plan` with one "
                 "product of each such group."
                 for shared in pin_variable_collisions(typed)]
    return pins, findings


def _declared_pins(plan: "Plan") -> list[str]:
    """The products of the pins `execute` would write, repeats kept: the
    files a leg mount and a path the root keeps are asked about."""
    return [product for _, product, _ in _read_pins(plan)[0]]


def _recorded_pins(plan: "Plan") -> dict[str, dict[str, str]]:
    """`{product: PIN_* values}` for the materializer, as
    `declared_pin_values` hands it the scaffold's. Read only after `execute`
    has refused every finding `_read_pins` makes."""
    return {product: values for _, product, values in _read_pins(plan)[0]}


def _pin_files(plan: "Plan") -> list[tuple[str, str | None]]:
    """`(path, product)` for each pin file `execute` writes, in the order
    `place` writes them: each declared pin's, once, then the shape's own
    pin, whose product is None (#524)."""
    return [*((neutral_pin_path(product), product)
              for product in dict.fromkeys(_declared_pins(plan))),
            (SHAPE_PIN, None)]


def _kept_pin_findings(plan: "Plan", tree: list) -> list[str]:
    """A FINDING for each pin file a path the plan keeps in the root already
    holds: a declared pin's (#273), or the shape's own pin (#524). The
    materializer writes the pin beside such a path, under `COLLISION_DIR`,
    as it writes any shape file the root holds; for a pin that is no copy to
    merge but the wrong file at the pin's path, which the root reads there:
    its own `validate-pins.py` reads `contracts/<product>-pin.yaml`, and
    `execute`'s verification, `validate-pins.py` and `make bootstrap` read
    `contracts/shape-pin.yaml`. Asked of a disk that keeps case and, where
    that finds nothing, of one that ignores it.

    THE SHAPE'S OWN PIN WAS NEVER ASKED (#524). A file the source keeps at
    `contracts/shape-pin.yaml`, with a pin declared or without, or a link
    there that leads to something, passed `check`; `execute` made and
    pushed both legs, wrote the shape's pin beside it and failed its
    verification as `adopt-shape-pin-unreadable`. A link there that leads
    nowhere, which `place` writes the pin through, is named here too, and
    not again by the walk (`_links_at_a_pin`)."""
    kept = _kept_in_root(plan.entries, tree)
    if not kept:
        return []
    disks = ((_KeptTree(kept, fold=False), ""),
             (_KeptTree(kept, fold=True), _CASE_ASIDE))
    out = []
    for rel, product in _pin_files(plan):
        for disk, aside in disks:
            at = disk.at(rel)
            rows = [row for row in ([at] if at else disk.under(rel))
                    if row[1] != GITLINK_MODE]
            if not rows:
                continue
            path, mode, entry = rows[0]
            under = "" if entry == path else f" under the entry {_spelled(entry)}"
            where = "at" if at else "inside"
            written = (_declared_pin_held(product) if product
                       else _shape_pin_held(mode if at else None))
            out.append(
                f"FINDING {ROOT_HOLDS_PIN}: the plan keeps {_kind_of(mode)} "
                f"{_spelled(path)} in the assembly root{under}, {where} "
                f"`{rel}`{aside}, where `execute` writes {written}: "
                f"{_fix_the_kept_path(entry)}.")
            break
    return out


def _declared_pin_held(product: str) -> str:
    """What `plan-root-holds-pin` says of a declared pin's file (#273)."""
    return (f"the pin the plan declares on `{product}`. The shape's pin would "
            f"be written beside it, under `{COLLISION_DIR}/`, and the root's "
            "own `validate-pins.py` would read the source's file as that pin")


def _shape_pin_held(mode: str | None) -> str:
    """What `plan-root-holds-pin` says of the shape's own pin (#524), where
    the root keeps an entry of `mode` AT it, or, with None, a directory
    there."""
    found = "directory" if mode is None else _kind_of(mode).split()[-1]
    through = (", or written through it where it leads nowhere"
               if mode == SYMLINK_MODE else "")
    return ("the shape's own pin: the openRepoShape commit the root's copies "
            "came from and each copy's digest, which `execute`'s "
            "verification, the root's own `validate-pins.py` and `make "
            "bootstrap` read at that path. The split would hold the source's "
            f"{found} there, and the shape's pin beside it, under "
            f"`{COLLISION_DIR}/`{through}")


def _pin_findings(plan: "Plan", tree: list) -> list[str]:
    """Every FINDING about the plan's pins: each entry `execute` cannot
    write a pin file from, two pins at one file or one at a file the shape
    writes, two whose products one `SHAPE_PIN_SOURCE_<PRODUCT>` names
    (#275), and a path the root keeps where a pin is written, the shape's
    own among them (#524)."""
    return _read_pins(plan)[1] + _kept_pin_findings(plan, tree)


# ---------------------------------------------------------------------------
# A pin's digest, recomputed where `plan` read it (#449)
# ---------------------------------------------------------------------------
#
# `plan` reads each pin's digest and records it beside the commit, and the
# comment it writes above `pins:` says a commit or a digest edited there is one
# nobody read. `check` held the two to the form `plan` writes them in and to
# nothing else, so an edit of either -- a typo, a paste from another pin --
# checked ok, `execute` wrote the pin file from it and said `adoption
# verified`, and the root's own `validate-pins.py` then found
# `neutral-pin-digest-mismatch` on its first run, after both legs existed.
#
# WHERE THE CLONE `plan` READ THE DIGEST FROM IS STILL HERE, the digest is
# recomputed there at the plan's commit, by `plan`'s own reader, so the same
# words answer for the same clone: a digest that differs is
# `plan-pin-digest-mismatch`, and a clone that cannot answer for the commit
# (it does not hold it, or the path is no clone any more) is
# `plan-pin-source-unreadable`. The digest is a function of the commit, so a
# clone that holds the commit recomputes the digest `plan` read, whichever
# clone it is. A commit and a digest both moved to another commit are a pin
# of that commit, and that is the pin `execute` writes.
#
# NOTHING ELSE IS ASKED. `check` and `execute` read no network for a pin, and
# `execute --local-remote-dir` needs no `gh`, so a digest `gh api` read is
# not read again, and a clone no longer at its path is not looked for. Nor is
# a partial clone (`git clone --filter`) asked: `git` there fetches an object
# the clone lacks from its promisor remote, a commit edited into the plan
# among them, so whether it is one is read from its own config, which reads
# no network (`_a_partial_clone`). Each such pin gets one NOTE saying its
# digest was not rechecked here; the root's own `validate-pins.py` recomputes
# it wherever it can read the product. A relative path is read from the
# directory `check` or `execute` runs in, as `plan` read it from the one it
# ran in, and every sentence naming one says where that is
# (`_read_from_here`). Anything else at the path that cannot answer -- a
# commit it lacks, a directory that is no clone, a file -- is
# `plan-pin-source-unreadable`, as `validate-pins.py` finds a source it reads
# that cannot answer. `check` and `execute` ask this through
# `_entry_findings`, the one list.

#: Why a pin's digest `gh api` read was not rechecked.
NOT_RECHECKED_GH = "`plan` read it with `gh api`, and `check` reads no network"


def _recorded_clone(how: str) -> str | None:
    """The path of the clone a pin's `digest_source:` says `plan` read its
    digest from, as `--pin-source` was typed, or None where it names none."""
    clone = LOCAL_CLONE_RE.fullmatch(how)
    return clone["path"] if clone else None


def _read_from_here(clone: str) -> str:
    """` (read from this directory as <absolute path>)` for a relative clone
    path, which `check` and `execute` read from the directory they run in,
    as `plan` read it from the one it ran in; nothing for an absolute one."""
    if Path(clone).is_absolute():
        return ""
    return f" (read from this directory as {_shown(os.path.abspath(clone))})"


def _a_partial_clone(clone: Path) -> bool:
    """Whether `git` in `clone` fetches an object the clone lacks from a
    promisor remote (`git clone --filter`): read from the clone's own
    config, with no network. A path that is no clone is not one."""
    try:
        proc = subprocess.run(
            ["git", "config", "--local", "--get-regexp",
             r"^(extensions\.partialclone|remote\..*\.promisor)$"],
            cwd=str(clone), capture_output=True, check=False)
    except OSError:
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _why_not_rechecked(how: str) -> str | None:
    """Why the digest `plan` read as `how` says cannot be recomputed here, or
    None where the clone it names is still at its path and is no partial
    clone. Only nothing there is gone, what `plan`'s reader calls "no such
    directory": anything else at the path, a file or a directory that cannot
    be entered among it, is asked, and the reader says why it cannot answer.
    A partial clone is not asked, because `git` there would fetch what it
    lacks over the network."""
    clone = _recorded_clone(how)
    if clone is None:
        return (NOT_RECHECKED_GH if how == GH_DIGEST_SOURCE else
                f"`digest_source: {_shown(how)}` names no clone `plan` read "
                "it from")
    try:
        Path(clone).stat()
    except (FileNotFoundError, NotADirectoryError):
        return (f"the clone `plan` read it from is not at {_shown(clone)}"
                f"{_read_from_here(clone)}")
    except OSError:
        # There: `pin_digest_from_source` names why it cannot answer.
        return None
    if _a_partial_clone(Path(clone)):
        return (f"the clone at {_shown(clone)}{_read_from_here(clone)} is a "
                "partial clone (`git clone --filter`), whose `git` fetches "
                "what it lacks over the network, and `check` reads no "
                "network")
    return None


def _recomputed_pin_finding(said: str, values: dict) -> str | None:
    """The FINDING for a pin whose digest the clone `plan` read it from,
    still at its path, recomputes otherwise at the plan's commit or cannot
    recompute there, with `plan`'s own reader; None where it recomputes."""
    clone = _recorded_clone(values["PIN_DIGEST_SOURCE"])
    repository, commit, recorded = (values["PIN_REPOSITORY"],
                                    values["PIN_COMMIT"],
                                    values["PIN_TREE_SHA256"])
    try:
        actual = pin_digest_from_source(Path(clone), commit, repository)
    except Refusal as exc:
        return (f"FINDING {PIN_SOURCE_UNREADABLE}: {said} records `commit: "
                f"{commit}`, and the clone its `digest_source:` names"
                f"{_read_from_here(clone)} cannot answer for it: "
                f"{_shown(exc.detail)}. Either the commit was edited after "
                "`plan` read it, or that path no longer holds the clone "
                "`plan` read it in: run `check` where `plan` ran, or `git "
                f"fetch` in that clone, or {_pin_fix(repository)}.")
    if actual == recorded:
        return None
    return (f"FINDING {PIN_DIGEST_MISMATCH}: {said} records `commit: "
            f"{commit}` and `tree_sha256: {recorded}`, and the clone `plan` "
            f"read the digest from, {_shown(clone)}{_read_from_here(clone)}, "
            f"recomputes {actual} at that commit: one of the two was edited "
            "after `plan` read them, and the root's own `validate-pins.py` "
            "would refuse the pin file `execute` writes from them "
            f"(`neutral-pin-digest-mismatch`): {_pin_fix(repository)}.")


def _pin_digest_findings(plan: "Plan") -> tuple[list[str], list[str]]:
    """`(findings, notes)` for each pin `execute` would write: a FINDING for
    a digest the clone `plan` read it from recomputes otherwise at the
    plan's commit, or cannot recompute there; otherwise one NOTE for `check`
    to print, that the digest recomputes there, or that it was not
    rechecked here and why."""
    findings: list[str] = []
    notes: list[str] = []
    for said, _, values in _read_pins(plan)[0]:
        how = values["PIN_DIGEST_SOURCE"]
        why = _why_not_rechecked(how)
        found = None if why else _recomputed_pin_finding(said, values)
        if why:
            notes.append(f"NOTE {said}: digest NOT rechecked here: {why}. The "
                         "root's own `validate-pins.py` recomputes it "
                         "wherever it can read the product.")
        elif found:
            findings.append(found)
        else:
            clone = _recorded_clone(how)
            notes.append(f"NOTE {said}: digest recomputes at "
                         f"{values['PIN_COMMIT'][:12]} in the clone `plan` "
                         f"read it from, {_shown(clone)}"
                         f"{_read_from_here(clone)}.")
    return findings, notes


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
#: How git and YAML both spell a false boolean: what `git config --type=bool`
#: prints for one, one of the words git reads as false (BOOLEAN_WORDS), and
#: what `y` writes for Python's False.
FALSE_WORD = "false"

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
# of them, not only for the strings a plan happens to hold. A string is
# written plain only where that reader gives the same string back, and `y`
# asks the reader rather than a list of words, so a bare YAML keyword the
# reader takes as None or a bool (`null`, `True`) is quoted as well (#181);
# `tests/test_adopt_plan_yaml_quoting.py` proves that through the reader
# too. Everything it emits is read back by `check`, and
# `tests/test_adopt_plan.py` round-trips a plan through both, which is what
# keeps the writer and the reader honest about each other.

#: Ends at `\Z`, not `$`: `$` also matches before a FINAL newline, and wrote a
#: file named `Icon\n` bare, over two lines of the plan (#199).
_PLAIN_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_./@:+-]*\Z")


def loader_reading(line: str):
    """What the loader makes of the one value on `line`: `key: <value>` or
    `- <value>`, as a plan or a project's YAML spells it.

    THE ONE QUESTION, asked by the plan writer (`_reads_back_as_text`) and by
    the gate on what `execute` writes into the project (`manifest_misreads`),
    of the one loader both are read with: `repo_shape`, which every assembly
    root carries a copy of for its `bootstrap.py` and validators. The answer
    is the value under the key, or the one item, as that loader reads it; a
    line it will not read gives back the `YamlError` it raised, which is no
    string at all.
    """
    try:
        parsed = parse_yaml(line + "\n")
    except YamlError as exc:
        return exc
    held = list(parsed.values()) if isinstance(parsed, dict) else parsed
    return held[0] if isinstance(held, list) and len(held) == 1 else parsed


def _reads_back_as_text(text: str) -> bool:
    """Does the plan's own loader take `text`, written plain, back as `text`?

    ASKED OF THE LOADER, NEVER OF A LIST OF WORDS (#181). `null`, `Null`,
    `true` and `False` were written bare, so `plan --spec-path null` wrote
    `spec_path: null`, which loads as "no value" and mounted the leg at the
    default `spec`, and `--tracking-branch true` came back as a boolean. A
    second, hand-kept list of the words `repo_shape._scalar` treats as
    keywords is a list that goes stale the day that reader learns another one
    (it reads no `yes`, `on` or `.inf` today, and a list copied from YAML 1.1
    would quote them for nothing), so the candidate is round-tripped instead
    and whatever the loader reads as something else gets quoted.

    BOTH PLACES A VALUE IS WRITTEN are asked: after `key: `, and as a `- `
    item, which the reader splits differently (`- a:` is a one-key mapping,
    `k: a:` is not). A line the reader refuses is a value it does not read
    back.
    """
    return all(loader_reading(f"{place}{text}") == text
               for place in ("k: ", "- "))


def y(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else FALSE_WORD
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    text = str(value)
    if text and _PLAIN_RE.match(text) and _reads_back_as_text(text):
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
BOOLEAN_WORDS = ("true", "yes", "on", FALSE_WORD, "no", "off")
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


def _git_quoted(key: str) -> str:
    """`key` as git's own words quote it, between single quotes: `missing
    value for 'submodule.b.update'`; or, where `_spelled` has anything to
    write differently, `_spelled`'s own form, which is how `_refused_value`
    names the same key. A key's `<name>` is the source author's choice, and
    git prints it as it is: an ESC, a carriage return or a byte that is not
    UTF-8 in it reached a finding that way (#328). A key `_spelled` leaves
    as it is keeps git's quotes, so that finding reads exactly as it did.
    It asks `_spelled` and writes no escape of its own, so whatever way
    `_spelled` spells a character, this does too."""
    spelled = _spelled(key)
    return f"'{key}'" if spelled == f"`{key}`" else spelled


def _registrations(listed: bytes) -> Registrations | str:
    """`git config -z --list` output, read by `Registrations`; or what git's
    submodule reader dies on, at the first key in the file it dies on: one
    SUBMODULE_VALUED_KEY_RE names with no value at all, or one whose value
    it refuses (`_refused_value`, #215). `-z` prints a key with no value
    with no newline, and git looks for its value after it has filtered the
    name and before it filters the value. The key is `_git_quoted`, because
    the finding that says what git died on is one line."""
    registrations = Registrations()
    for record in listed.split(b"\x00"):
        key, newline, value = _git_path(record).partition("\n")
        valued = SUBMODULE_VALUED_KEY_RE.fullmatch(key)
        if valued and not newline and not _a_name_git_ignores(valued["name"]):
            return f"missing value for {_git_quoted(key)}"
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
                 commit: str, work_root: Path | None = None,
                 cloned: bool = False):
        self.path = path
        self.repository = repository
        self.branch = branch
        self.commit = commit
        #: The work directory this run opened the source in: where a named
        #: repository is cloned to be read, and where `execute` makes the
        #: assembly's clone, so where a symlink the plan keeps in the root
        #: leads when it climbs above the root (#183).
        self.work_root = work_root
        #: Whether `open` CLONED it, into the work directory, rather than
        #: reading a local path in place: a re-run given the same --work-dir
        #: cannot clone into that directory again (`_cloned_here`).
        self.cloned = cloned

    @classmethod
    def open(cls, spec: str, work_root: Path) -> "Source":
        """`spec` is a local path (used in place) or `org/repo` (cloned)."""
        candidate = Path(spec).expanduser()
        cloned = False
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
            cloned = True
        branch = _default_branch(path)
        commit = git_out(["rev-parse", branch], cwd=path).lower()
        return cls(path, repository, branch, commit, work_root, cloned)

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
    """The `org/repo` the source's `origin` URL ends in; None when it has
    no origin, or one that ends in no such pair.

    NOR DOES A URL THAT IS NOT UTF-8 NAME ONE (#292). git keeps the URL as
    the bytes it was given: a clone of a directory named in a code page that
    is not UTF-8 has that path as its origin, and nobody did anything wrong.
    Read strictly, it ended `plan`, `check` and `execute` in a
    `UnicodeDecodeError` traceback in `Source.open`, before any question was
    asked. Now it is no origin: `plan` takes `--org`, or refuses as
    `adopt-no-org` and asks for it, and `check` and `execute` name the
    source by its path.
    """
    try:
        url = git_out(["remote", "get-url", "origin"], cwd=path)
    except (Refusal, UnicodeDecodeError):
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
    """One row of the plan: a path, the leg proposed for it, and why.

    `default` is the answer the entry's rule names for its question, or
    None, and `review_required` is the verdict's: whether a question was
    asked. The two part only in `with_its_default`, the one place a
    question's `leg:` is filled in, which `cmd_plan` alone calls; `walk`
    leaves every question's `leg` None, so the doctor, which walks a leg
    with it, still reads one as a question (#528).
    """

    def __init__(self, path: str, verdict: Verdict, files: int, size: int):
        self.path = path
        self.leg = verdict.leg
        self.rule = verdict.rule
        self.reason = verdict.reason
        self.confidence = verdict.confidence
        self.question = verdict.question
        self.default = verdict.default
        self.review_required = verdict.review_required
        self.files = files
        self.bytes = size

    def with_its_default(self) -> "Entry":
        """This question with its rule's default written in as its `leg:`,
        still `review_required` and still carrying the question, the rule
        and the reason, so a reader sees what was proposed and why."""
        out = Entry(self.path, Verdict(None, self.rule, self.reason,
                                       self.confidence), self.files,
                    self.bytes)
        out.question = self.question
        out.default = self.default
        out.leg = self.default
        return out

    def write(self, lines: list[str]) -> None:
        lines.append(f"  - path: {y(self.path)}")
        emit(lines, "leg", self.leg, 4)
        emit(lines, "confidence", self.confidence, 4)
        emit(lines, "rule", self.rule, 4)
        emit(lines, "reason", self.reason, 4)
        emit(lines, "files", self.files, 4)
        emit(lines, "bytes", self.bytes, 4)
        emit(lines, "review_required", self.review_required, 4)
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


#: The path policy's rule for the source's own staying-single record (#528).
#: Its question and its default are the record's, so `plan` asks them only
#: of a file that IS the record (`ask_about_a_record_only`).
RECORD_RULE = "ambiguous-single-repository-record"


def ask_about_a_record_only(policy: PathPolicy, entries: list[Entry],
                            source: "Source") -> list[Entry]:
    """`entries`, with a top-level `single-repository.yaml` that is no
    record asked the question the rules below the record's ask (#528).

    `kind:` DECIDES, NOT THE NAME, for the record's one reader, the Triad
    advisory (`shape_advisory.read_record`). A file of that name declaring
    `kind: release-config` silences nothing, and the same `plan` run said
    so in a NOTE while the record's question told the person the file
    records that the repository stays single, and its default would have
    dropped it. So RECORD_RULE answers only a file that declares
    `single-repository-record` in the commit being planned, read as the
    advisory reads it there; any other is classified as if the policy held
    no such rule, which for a top-level YAML file is the general question,
    asked as before. A source with no entry RECORD_RULE answered is not
    read at all.
    """
    if not any(entry.path == shape_advisory.RECORD_FILE
               and entry.rule == RECORD_RULE for entry in entries):
        return entries
    state, _, _ = shape_advisory.read_record(
        shape_advisory.Tree(source.path, source.commit))
    if state == shape_advisory.RECORD_SILENCES:
        return entries
    return [Entry(entry.path,
                  policy.classify_file(entry.path, skip=(RECORD_RULE,)),
                  entry.files, entry.bytes)
            if entry.path == shape_advisory.RECORD_FILE
            and entry.rule == RECORD_RULE else entry
            for entry in entries]


def with_defaults(entries: list[Entry]) -> list[Entry]:
    """`entries`, each question whose rule names a default answer written
    with that default as its `leg:` (#528).

    RULED BY BRETT HEAP ON 2026-10-12: a source's own `single-repository.yaml`
    is asked drop or root, "the default answer is drop". So `plan` writes
    `leg: drop`, and keeps `review_required: true`, the rule and the
    question beside it: `check` passes it, and `execute` drops the path
    unless a person writes `root`. A path with no default is untouched, as
    is every question `ask_about_submodules` or `ask_about_refused_paths`
    asked in place of a rule's, because those carry none: called after
    them, this fills in only what a rule proposed and nothing replaced.
    """
    return [entry.with_its_default() if entry.leg is None and entry.default
            else entry for entry in entries]


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
    # NO DEFAULT, from either rule (#528): the question is the submodules',
    # which no rule's default answers, and one carried here would be
    # written in as the entry's `leg:` by `with_its_default`.
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
    # NO DEFAULT (#528): the rule's was an answer to its own question, and
    # this one is why the name cannot go into a leg, which a person answers.
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
    and so are a backslash and a backtick, so that the spelling reads one way
    only and the backticks still delimit it.

    THE SPELLING IS THE PLAN'S OWN (`_spelled_character`): the byte 0xE9 is
    `\\udce9` and the character U+0085 is `\\x85`, as `path:` writes them
    (`repo_shape.double_quoted`), so that a question or a report that says
    `caf\\udce9` is the entry `"caf\\udce9"` in the plan. Each escape names
    a code point, so a byte and a character never share one. They did: a
    byte was `\\xe9` here, which in YAML is the character U+00E9, and the 32
    C1 controls, U+00A0 and U+00AD were spelled as the bytes of the same
    value, 34 pairs of different names that read alike (#329). A spelling is
    only printed, in a finding, a refusal or a question the plan carries;
    none is read back or handed to git.
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
    """One character of `_spelled`: itself when it is printable, a backslash
    before a backslash or a backtick, and otherwise the escape
    `repo_shape.double_quoted` writes for it in the plan, so the plan's one
    table and not a second one: `\\n` for a line feed, `\\x85` for U+0085,
    `\\u2028` for U+2028, and `\\udc85` for the byte 0x85, which
    `Source.tree` keeps as the surrogate U+DC00 plus the byte."""
    if char in "\\`":
        return "\\" + char
    if char.isprintable():
        return char
    return double_quoted(char)[1:-1]


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
        across = spec_leg_from_code_leg(spec_path, code_path)
        for hit in hits[:8]:
            shown = "".join(map(_spelled_character, hit))
            out.append(
                f"{code_path}/{shown} names `{named}`, which moves to the "
                f"spec leg: it must read across the assembly root — "
                f"`{across}/{named}` relative to `{code_path}/` — or "
                "take the path from the environment")
        if len(hits) > 8:
            out.append(f"… and {len(hits) - 8} more file(s) under the code leg "
                       f"naming `{named}`")
    return out


def spec_leg_from_code_leg(spec_path: str, code_path: str) -> str:
    """The spec leg's mount, `spec_path`, as a path relative to the code
    leg's, `code_path`: `../spec` for the defaults, `../spec` for
    `legs/spec` beside `legs/code`, and `../../spec` for `spec` beside
    `impl/code`.

    ONE `..` PER SEGMENT OF THE CODE LEG'S PATH BELOW WHAT THE TWO SHARE
    (#522, auA-13). The follow-up wrote `../<spec_path>`, which is right only
    while the code leg sits in the root: with `--spec-path legs/spec
    --code-path legs/code` it said `../legs/spec/contracts/` "relative to
    `legs/code/`", a path that leads to `legs/legs/spec`.

    Both are canonical mount paths, asked by `plan` before it writes a
    follow-up and by `execute` before it mounts a leg: `/` between
    segments, and no segment empty, `.` or `..`. So the segments are
    compared as text, and nothing is resolved against a disk. Two segments
    that differ only in case are two segments here, and the comparison stops
    at the first of them: the path climbs one level more than a disk that
    folds case needs for every segment from there to the end of what such a
    disk would call shared (`A/B/spec` beside `a/b/code` climbs two more,
    and so does `A/b/spec`), and still leads to the same directory.
    """
    spec, code = spec_path.split("/"), code_path.split("/")
    shared = 0
    while (shared < min(len(spec), len(code))
           and spec[shared] == code[shared]):
        shared += 1
    return "/".join([".."] * (len(code) - shared) + spec[shared:])


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

    The last one names the base `execute` opens the pull request against as
    the plan's `tracking_branch` (#479). It said "the source's default
    branch" while `execute` used `--base main` whatever that branch was. It
    names the KEY and not its value: this list is written once, by `plan`,
    and a value named here went on naming the old branch after a hand edit
    of `tracking_branch:`, which `plan-tracking-branch-missing`'s
    remediation asks for, in `check`'s output and in the pull request's own
    body (#493's review, F3).

    It is a review, and never "open the split as a pull request" (#523).
    `plan` prints it and the split commit lists it under the FOLLOW-UPS this
    commit does NOT do, which is also the pull request's body, while against
    GitHub `execute` opens that pull request itself, and under
    `--local-remote-dir` opens none. So it says what `execute` does in either
    run, and calls the legs what they are: new repositories `execute` creates
    and pushes before the split, extracted or, with no path, seeded from a
    template. "Seeded", said of both, named an extracted leg by the word kept
    for a template's.

    The Makefile follow-up names the key too, for the spec leg's mount: it
    names `legs.spec_path` and no path. `execute` renders the Makefile's block
    from the plan's CURRENT `legs.spec_path`, and `MOUNT_REMEDIATION` and
    `plan-leg-path-collides` both ask for a hand edit of it, so a path named
    here went on naming the old mount in the split commit's message, the
    pull request's own body, while the Makefile in that commit named the new
    one (#522's review, F1).
    """
    out = cross_leg_references(source, entries, spec_path, code_path)
    if any(e.leg == "spec" and (e.path == "contracts/"
                                or e.path.startswith("contracts/"))
           for e in entries):
        out.append(
            "the root Makefile wires `CONTRACTS_DIR` to the `contracts/` of "
            "the spec leg, where the plan's `legs.spec_path` mounts it, and "
            "exports it, so the code leg's tooling takes the path from the "
            "environment instead of assuming it sits beside it")
    if any(e.path in ("CODEOWNERS", ".github/CODEOWNERS") for e in entries):
        out.append(
            "CODEOWNERS in the assembly root now names paths that live in the "
            "legs; re-scope it here and add one to each leg, since a code "
            "owner rule cannot cross a repository boundary")
    out.extend(collisions)
    out.append(
        f"review the root's diff together with {names['spec']} and "
        f"{names['code']}, the two new repositories `execute` creates and "
        "pushes before the split; against GitHub it opens the split's pull "
        "request itself, whose base is the plan's `tracking_branch`, the "
        "branch the assembly root and both legs track")
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
                pins: dict, follow_ups: list[str],
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
        "# An entry whose rule names a default arrives with it as its `leg:`",
        "# and `execute` takes it as written: confirm it or change it.",
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
    lines += ["", *PINS_COMMENT, *_pin_lines(pins), ""]

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
    quietly as the default -- a value nobody chose. So is an explicit NULL
    (`spec_path: null`, `~`, or the key with nothing after it), which comes
    back as None (#181): before `y` quoted keywords, `plan --spec-path null`
    wrote exactly that, the plan's own follow-ups said `null/contracts`, and
    `check` passed it as a mount at `spec`.

    `legs:` is read only when it is a mapping. The doctor's PLACEMENT plan
    (`shape-doctor.py --placement-plan`) writes `legs:` as a LIST of the
    mounted legs it audited and is handed to `Plan` and `_leg_findings` by
    `tests/test_shape_doctor.py`; a list carries no `spec_path`, and `.get` on
    it is an `AttributeError`, not an answer. For anything that is not a
    mapping nothing is read, so the role's own name comes back, as it does for
    a key the plan does not carry.
    """
    legs = plan.legs
    key = f"{role}_path"
    return legs[key] if isinstance(legs, dict) and key in legs else role


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

def _leg_collision_remediation(neutral_pins=()) -> str:
    """What `plan` tells a person whose leg path collides. The paths are
    `assembly_root_paths(neutral_pins)`, the materializer's own list, each
    declared pin's file among them (#273), as the scaffold lists its own."""
    return (
        "Remediation: nothing here picks a path for you, so pass another one "
        "yourself. A leg path neither is, holds nor lies inside, whatever the "
        "case, a path the shape writes into the assembly root ("
        + ", ".join(f"`{path}`" for path in assembly_root_paths(neutral_pins))
        + f") or `{COLLISION_DIR}`. {SHAPE_DIR_RESERVED}, so a leg path there "
        "is refused even where this source needs no copy. The defaults `spec` "
        "and `code` pass. `check` then asks the same of every source path the "
        "plan keeps in the root."
    )


def _shape_collisions(what: str, value: str, neutral_pins=()) -> list[str]:
    """Where the mount path `value` overlaps what the shape writes: the
    paths of `assembly_root_paths`, each declared pin's file among them
    (#273), asked through the definition this tool shares with
    `scaffold-project.py` (#197), then this tool's own `COLLISION_DIR`,
    which only an adoption writes into."""
    out = shape_path_collisions(what, value, COLLISION_DIR,
                                neutral_pins=neutral_pins)
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


def leg_path_collisions(legs: tuple, kept=(), neutral_pins=()) -> list[str]:
    """Everything each leg's mount path overlaps in the assembly root, as
    sentences; `[]` when nothing.

    `legs` is the two `(what, value)` pairs `leg_path_problems` takes, each
    already a canonical path: an overlap is a statement about two paths. `kept`
    is `(path, mode, entry)` for each source path the plan keeps in the root
    (`_kept_in_root`); with none, only the shape's own paths are asked about,
    which is all `plan` knows. `neutral_pins` are the products whose pin
    files `execute` writes (#273), asked about with the shape's own paths.
    """
    out: list[str] = []
    for what, value in legs:
        out += _shape_collisions(what, value, neutral_pins)
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
                _plan_leg_paths(plan), _kept_in_root(plan.entries, tree),
                _declared_pins(plan))]


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


# ---------------------------------------------------------------------------
# What `execute` writes into the project is read back as written (#181)
# ---------------------------------------------------------------------------
#
# `y` makes the PLAN say what was typed. `execute` then puts the same values
# into the assembly root's templates, and `project.yaml` and the leg pins
# carried most of them bare: `id: {{PROJECT_ID}}`, `path: {{SPEC_PATH}}`,
# `tracking_branch: {{TRACKING_BRANCH}}`. So once the plan kept `null` as the
# text it was, `--spec-path null` ended `adoption verified` and the first
# bootstrap failed on `path is None`, `--id true` on `id is True`, and
# `--tracking-branch true` pushed the legs on `true` while bootstrap put them
# on a local `True` with no upstream. `2026`, `1.5` and `~` already did the
# same on `main` (#187's review).
#
# THE TEMPLATES QUOTE THOSE LINES NOW (#259), and `render` spells a value
# between a YAML template's double quotes with `double_quoted`, which reads
# back as typed: on them the question below finds nothing. Since #514
# (main's e6fbd748) `_neutral_product_pins` quotes an item of the manifest's
# `neutral_product_pins:` list the reader would misread, so a pin's product
# reads back too, and on the shipped templates nothing is left to refuse.
#
# SO THE GATE STAYS, AND REFUSES. `plan` (before the plan is written),
# `check` (a FINDING) and `execute` (through `_entry_findings`, before any
# leg exists) ask the ONE question below and refuse a value the project's
# loader would read back as anything but that same text, on whatever line
# `execute` writes it into: any line a template, or `_template_table`,
# writes bare tomorrow, with no edit here.
#
# THE LOADER DECIDES, AND THE TEMPLATE SAYS WHERE. Each value is put into
# every line of a templated YAML file that carries its placeholder, exactly
# as `execute` would put it there, and `loader_reading` -- the question `y`
# asks -- reads that line back. No list of words, and no list of which
# placeholders are quoted: `elected_by: "{{ELECTED_BY}}"` is asked as the
# line `render` writes, the value spelled by `double_quoted` (#284), so
# `Null` and `CORP\tom` both read back there, as they do after
# `tracking_branch:` since #259, and as `- "Null"` in the pins' list since
# #514; a bare `- Null` there would not.

#: The assembly root's templated files that are YAML: what the project's own
#: loader reads back out of the split commit. The materializer's list, so a
#: templated YAML file added there is asked about here without an edit.
ASSEMBLY_TEMPLATE = SHAPE_ROOT / "templates" / "assembly-root"
TEMPLATED_YAML = tuple(rel for rel in TEMPLATED if rel.endswith(".yaml"))
#: The plan's keys for the election record, as `_template_values` reads them
#: out of the plan and as the tables below ask about them: one spelling.
ELECTED_BY_KEY = "elected_by"
ELECTED_ON_KEY = "elected_on"
REFERENCE_KEY = "reference"
#: The two other plan keys `_execute_gets_to_write` asks about by name.
TRACKING_KEY = "tracking_branch"
VISIBILITY_KEY = "visibility"
#: The placeholder `execute` writes the project's id through, and the one it
#: writes the pins' list through.
ID_PLACEHOLDER = "PROJECT_ID"
PINS_PLACEHOLDER = "NEUTRAL_PRODUCT_PINS"

#: Each plan value `execute` writes into those files, by its key in the plan
#: (and `plan`'s flag of the same name, dashed) and the `_template_values`
#: placeholder that carries it. The id is asked about apart from these,
#: because `execute` derives it when the plan has none; the leg paths are
#: `legs.` keys; the pins are a list.
MANIFEST_FIELDS = {TRACKING_KEY: "TRACKING_BRANCH",
                   VISIBILITY_KEY: "VISIBILITY", ELECTED_BY_KEY: "ELECTED_BY",
                   ELECTED_ON_KEY: "ELECTED_ON", REFERENCE_KEY: "REFERENCE"}
LEG_PATH_PLACEHOLDERS = {"spec": "SPEC_PATH", "code": "CODE_PATH"}
#: How `plan` fills a flag nobody passed: a sentence about the value it fills
#: in names where it came from (`_flag_named`), as `checked_value` names the
#: tracking branch (#479), and never as a flag the person did not type. #181's
#: misread rule asks only about a value the loader can read as something else,
#: and no elector is one: the manifest writes it between double quotes, which
#: `render` spells with `double_quoted` (#284). The validator's rule (#261)
#: asks about every value, so an elector `git config user.name` leaves empty
#: is named by where it came from as well (#529).
FLAG_DEFAULTS = {"id": "--project lowercased",
                 TRACKING_KEY: "the source's default branch",
                 ELECTED_BY_KEY: "`git config user.name`"}
#: How a sentence names the id `execute` derives when the plan sets none:
#: when it has no `id:`, or an `id:` with no value (`null`, `~` or nothing,
#: as `main`'s `plan --id null` wrote it), which `Plan.get` reads alike.
DERIVED_ID = "id (not set in the plan, so legs.assembly lowercased)"
#: How a sentence names one of a plan's `pins:`: the key holds a list of
#: pins, each a mapping since #273, and what `execute` writes into the
#: manifest's list for one is its product.
PIN_IN_PLAN = "the product of a pin in pins"
#: And how `plan` names the same value: the product of a `--pin` it read
#: (`product@<40 hex>`), which is not the whole of what was typed.
PIN_FLAG_PRODUCT = "the product of a --pin"
#: What a sentence calls a character a terminal shows as something else, or
#: not at all, which `_worded` names instead of printing.
CHARACTER_NAMES = {"\t": "a tab", "\n": "a line break",
                   "\r": "a carriage return"}
#: How a sentence joins the last of the things it names, spelled once.
AND = " and "

MANIFEST_MISREAD_REMEDIATION = (
    "Remediation: choose another value for each one named. `execute` writes "
    "these values into the project's own YAML files as they stand, and the "
    "loader the project's own `bootstrap.py` and validators read those files "
    "with would take each one named here as something else: "
    "the run would still end `adoption verified`, and the project would then "
    "be bootstrapped and validated against what was read instead. Quoting it "
    "in the plan does not help, because the plan is not what is misread.")


def _written(placeholder: str, value: str) -> list[tuple[str, str]]:
    """`(file, line)` for each line of a templated YAML file that carries
    `{{placeholder}}`: with `value` in its place, as `execute` writes it, and
    without its indent, which says nothing about how the value is read.

    AS `execute` WRITES IT is what the materializer's own `render` makes of
    the line, asked here as the loader is asked, so no copy of its rules can
    go stale. Between a YAML template's double quotes, `"{{ELECTED_BY}}"`,
    `render` spells the value with `double_quoted`, which the loader reads
    back as typed (#284), and it puts each value in once, never searching
    it again (#260). A copy of those rules in two steps, the second run over
    the first's output, asked `--elected-by '"{{ELECTED_BY}}"'` about a line
    `execute` never writes, and refused it. Every file here is `.yaml`,
    which is what makes `render` take the quoted step.
    """
    token = "{{" + placeholder + "}}"
    lines = [(rel, line.strip())
             for rel in TEMPLATED_YAML
             for line in (ASSEMBLY_TEMPLATE / rel).read_text(
                 encoding="utf-8").splitlines()
             if token in line]
    return [(rel, render(line, {**_as_they_stand(line), placeholder: value},
                         rel))
            for rel, line in lines]


def _as_they_stand(line: str) -> dict[str, str]:
    """A `render` table that gives each placeholder on `line` back as its own
    token. Bare, the token is written as it was; between quotes,
    `double_quoted` spells `{{KEY}}` as `"{{KEY}}"`, as it was. So the line
    `_written` asks about differs from the template's by one value only."""
    return {token[2:-2]: token for token in PLACEHOLDER_RE.findall(line)}


def _field(what: str, placeholder: str, value) -> tuple[str, object, list]:
    """`(what, value, written)` for a value `_template_values` writes as
    `str(value)`. `value` is kept as it was read: out of a plan it need not
    be text (`tracking_branch: 007` is read as 7), and a sentence about it
    says what was read, never `str` of it, which the plan does not say."""
    return what, value, _written(placeholder, str(value))


def _pin_field(what: str, plan: "Plan", product: str,
               naming: NamingPolicy) -> tuple[str, object, list]:
    """`(what, product, written)` for one pin `execute` writes: `written`
    holds the line it writes for the pin's product in the manifest's
    `neutral_product_pins:` list, without the item's indent.

    ASKED OF `_template_table`, THE TABLE `execute` WRITES THAT LIST FROM,
    and never of a copy of how it spells an item: the table
    `_manifest_values` builds from `plan` with this one pin (`execute`'s
    `_template_values` is the same table), put into the template's line by
    `render` (`_written`). Since #514 (main's e6fbd748) `_template_table`
    quotes an item the reader would misread, so this asks the quoted line
    and the gate passes it, with no edit here; written bare again, the line
    is refused. No line where the
    table cannot be built (`_manifest_values` is None), which `plan` and
    `check` report in their own words. Since #273 a product is `parse_pin`'s,
    or a `pins:` entry `_read_pins` accepts, which both hold to
    `PIN_ARG_RE`'s alphabet: it holds no whitespace, and the line loses only
    its indent."""
    # The pin by its product alone, as an old plan's entry names it:
    # `_manifest_values` reads only the products (`Plan.pins`).
    alone = Plan(plan.path, {**plan.data, "pins": [product]})
    table = _manifest_values(alone, naming)
    if table is None:
        return what, product, []
    return what, product, [
        (f"{rel}'s neutral_product_pins", item.strip())
        for rel, written in _written(PINS_PLACEHOLDER,
                                     table[PINS_PLACEHOLDER])
        for item in written.splitlines()[1:]]


def _the_loader_made(reading) -> str:
    """What the loader made of a value, in words: a scalar as it was READ,
    with its kind (`the number 7`, for a line or a plan that says `007`),
    and a list or a mapping by its kind alone."""
    if isinstance(reading, YamlError):
        return f"nothing: it refuses the line ({reading})"
    if reading is None:
        return "no value at all"
    if isinstance(reading, bool):
        # In the words `y` writes it into a plan, which are YAML's own.
        return "the boolean " + y(reading)
    if isinstance(reading, (int, float)):
        return f"the number {reading!r}"
    if isinstance(reading, str):
        return f"the text {_worded(reading)}"
    return NOT_TEXT_KINDS.get(type(reading), "something that is not text")


def _character_name(char: str) -> str:
    return CHARACTER_NAMES.get(char, f"the character U+{ord(char):04X}")


def _worded(text: str) -> str:
    """`text` as a sentence shows it: between backticks as it is typed, with
    each character a terminal shows as something else named outside them,
    in order; `""` when it is empty.

    NOT `repr`, and not `_spelled`, which spells a path so that it reads one
    way only: both show the tab the loader makes of `"CORP\\tom"` as `\\t`,
    the two characters the person typed, and show what they typed with its
    backslash doubled, so each looks like the other. Named, the tab is
    plainly a tab.
    """
    parts: list[str] = []
    for printable, chars in itertools.groupby(text, str.isprintable):
        if printable:
            parts.append(f"`{''.join(chars)}`")
        else:
            parts += map(_character_name, chars)
    return ", then ".join(parts) or '""'


def _named(what: str, value) -> tuple[str, str]:
    """`(subject, text)` for a sentence about `value`: who and what it is,
    and the text the loader does not read back.

    A value read out of a plan that is not text is named by what its loader
    READ, with its kind: `str` of it is not what the plan says
    (`tracking_branch: 007` is read as 7, and `TRUE` as true), so the text is
    then the one `execute` writes, named as such.
    """
    if isinstance(value, str):
        return f"{what} is {_worded(value)}", "that text"
    return (f"{what} was read out of the plan as {_the_loader_made(value)}",
            f"the text {_worded(str(value))}")


def _line_shown(line: str) -> str:
    """`line` as a sentence quotes it: in backticks, or as Python spells it
    when it holds a character a terminal shows as something else (a line
    break, a tab), so that one FINDING stays one line. Not `_shown`, which
    is #199's spelling of a PATH in the plan report, with no backticks."""
    return f"`{line}`" if line.isprintable() else repr(line)


def manifest_misreads(fields) -> list[str]:
    """A sentence for each `(what, value, written)` whose value, written as
    `str(value)`, the project's loader does not read back out of every line
    in `written`; `[]` when it does for all of them.

    `what` is how the caller names the value -- `--tracking-branch` to
    `plan`, `tracking_branch` read out of a plan -- so the sentence points at
    the thing the person has in front of them.
    """
    problems = []
    for what, value, written in fields:
        text = str(value)
        wrong = [(rel, line, loader_reading(line)) for rel, line in written]
        wrong = [row for row in wrong if row[2] != text]
        if wrong:
            where = AND.join(f"into {rel} as {_line_shown(line)}"
                             for rel, line, _ in wrong)
            subject, expected = _named(what, value)
            problems.append(
                f"{subject}, which `execute` writes {where}, where the "
                "project's own YAML loader reads it back as "
                f"{_the_loader_made(wrong[0][2])} and not as {expected}: "
                "choose another value")
    return problems


def _flag_named(key: str, given: set) -> str:
    """`key`'s flag as a sentence names it: `--elected-by` when the person
    passed it (`key` is in `given`), and, where `plan` fills the flag in by
    itself (`FLAG_DEFAULTS`) and nobody passed it, where the value came from:
    `--elected-by (not given, so `git config user.name`)`. A refusal of a
    value `plan` chose must not point at a flag nobody typed (#529)."""
    spelled = "--" + key.replace("_", "-")
    if key in FLAG_DEFAULTS and key not in given:
        spelled += f" (not given, so {FLAG_DEFAULTS[key]})"
    return spelled


def _flag_fields(args, given: set, pins: dict, source: Source,
                 planned: "Plan", naming: NamingPolicy) -> list[tuple]:
    """`plan`'s values as it is about to record them, each named by its flag,
    and by where `plan` took it from when `given` says it was not passed.
    `pins` is `declared_pin_values`' `{product: PIN_* values}`: the product
    is what `execute` writes into the manifest's list (#273), asked of the
    table `execute` writes it from, built from `planned`, the plan `plan` is
    about to write (`_flag_plan`, `_pin_field`).

    Less a tracking branch the loader misreads that `execute` never writes
    in some mode (`_a_branch_execute_writes`): one git will not create, which
    is then no branch of the source, or one `execute` does not push the
    legs to in every mode; `execute` refuses each before any leg exists
    (#479). `plan` records either, and notes one that is no branch of the
    source."""
    def flag(key: str) -> str:
        return _flag_named(key, given)

    fields = [_field(flag("id"), ID_PLACEHOLDER, args.id)]
    fields += [_field(flag(key), placeholder, getattr(args, key))
               for key, placeholder in MANIFEST_FIELDS.items()
               if key != TRACKING_KEY
               or _a_branch_execute_writes(source, flag(key),
                                           getattr(args, key))]
    fields += [_field(f"--{role}-path", placeholder,
                      getattr(args, f"{role}_path"))
               for role, placeholder in LEG_PATH_PLACEHOLDERS.items()]
    return fields + [_pin_field(PIN_FLAG_PRODUCT, planned, product, naming)
                     for product in pins]


def _id_field(plan: Plan) -> tuple:
    """The id as `execute` writes it, named for where it comes from: the
    plan's `id:` as its loader read it, or `legs.assembly` lowercased when
    the plan sets none (`DERIVED_ID`). `Plan.project_id` raises the
    `Refusal` of an id it refuses, which is reported on its own account."""
    project_id = plan.project_id
    set_id = plan.get("id")
    if set_id is None:
        return _field(DERIVED_ID, ID_PLACEHOLDER, project_id)
    return _field("id", ID_PLACEHOLDER, set_id)


#: The plan values `execute` hands to `git` before it writes anything:
#: `_checked_plan_values` checks each with `checked_value`, and refuses one it
#: refuses (`unsafe-value`) before `_refuse_what_check_finds` asks the gate.
GIT_ARGUMENT_KEYS = (TRACKING_KEY,)


def _execute_gets_to_write(key: str, value) -> bool:
    """Does `execute` get as far as writing `value` into the project, in
    EVERY mode it runs in? `check` is not told which one it will be.

    Not for a `git` argument `checked_value` refuses: `_checked_plan_values`
    refuses it as `unsafe-value` before any leg exists, so a sentence saying
    `execute` writes it, and that the run would end `adoption verified`,
    would be false (rv181f's F2).

    Nor for a visibility that is not one of `VISIBILITY_CHOICES`, text or
    not. In gh mode, `execute`'s default, `_create_leg_remotes` hands it to
    `gh repo create` as `--<visibility>` before anything is written, and gh
    creates a repository with no other (rv181f's F2b), so such a sentence
    would be false there. The project's own validator refuses each such
    visibility as the loader reads it (`secret`, `"true"`, `true`,
    `[secret]`), and since #259 quotes the template's `visibility:`, a text
    the loader read there as no value (`"null"`, `""`, `"~"`) or as one of
    the three (`"'private'"`) is that text, which it refuses too: `check`
    names each in the validator's words (`manifest-visibility`, #261,
    `_manifest_findings`), and `execute` refuses the plan before anything
    exists, in either mode. None of the three choices is misread.

    Nor for any other value no file can hold (`unwritable_reason`): `check`
    names it as `plan-unwritable-value`, and `execute` refuses a plan
    holding it before any leg exists (#255), so one wrong value is one
    finding, and none says the run gets further.

    Nor for a tracking branch the loader misreads that git will not create
    (`_a_branch_git_creates`)."""
    if key == VISIBILITY_KEY:
        return str(value) in VISIBILITY_CHOICES
    if key not in GIT_ARGUMENT_KEYS:
        return unwritable_reason(str(value)) is None
    try:
        checked_value(key, value)
    except Refusal:
        return False
    return _a_branch_git_creates(key, value)


def _a_branch_git_creates(what: str, value) -> bool:
    """False for a tracking branch the project's loader misreads that git
    will not create (`branch_problem`, #283): `~`, which the loader reads as
    no value where it is written bare. No source has such a branch, so
    `check` finds it `plan-tracking-branch-missing` and `execute` refuses it
    before any leg exists (#479); before #479 `execute` handed it to `git
    init -b` and died there. Either way a sentence saying `execute` writes
    the branch, and that the run would still end `adoption verified`, would
    be false (rv181f's H1). Since #259 the template quotes the branch, which
    reads `~` back, so on the templates shipped this asks git nothing.

    Git is asked ONLY about a branch the loader misreads. One it reads back
    is no concern of this rule's, and a plan whose values all read back
    starts no process."""
    field = _field(what, MANIFEST_FIELDS[TRACKING_KEY], value)
    return not manifest_misreads([field]) or branch_problem(what, value) is None


def _a_branch_execute_writes(source: Source, what: str, value) -> bool:
    """`_a_branch_git_creates`, asked where the source is in hand (`plan`,
    and `check` and `execute` through `_entry_findings`): False also for a
    tracking branch the loader misreads that `execute` does not push the
    legs to in every mode (`_pushed_in_every_mode`, #479), and refuses
    before any leg exists. As git is, the source is asked ONLY about a
    branch the loader misreads, so one that reads back starts no process."""
    field = _field(what, MANIFEST_FIELDS[TRACKING_KEY], value)
    return not manifest_misreads([field]) or (
        branch_problem(what, value) is None
        and _pushed_in_every_mode(source, str(value)))


def _pushed_in_every_mode(source: Source, tracking: str) -> bool:
    """Does `execute` push the legs to `tracking`, and write it into the
    project, in EVERY mode it runs in, as the source knows its branches?
    `check` is not told which mode it will be (#479).

    In gh mode, `execute`'s default, the split goes to the repository the
    source is a clone of. `check` reads that repository's branches from the
    clone (`_tracking_branch_problem`) and finds a branch it lacks as
    `plan-tracking-branch-missing`, which `execute` refuses before any leg
    exists. Under `--local-remote-dir` the split is pushed back into the
    source itself, and `execute` refuses a branch that is not one of the
    source's OWN before any leg exists, one only its remote `origin` has
    among them (`_refuse_a_tracking_branch_the_remote_lacks`). So a sentence
    saying `execute` writes the branch, and that the run would still end
    `adoption verified`, is true only of a branch both modes have.

    What GitHub has NOW is `execute`'s to ask (`git ls-remote`, before any
    leg): `check` asks nothing of the network, as #479 has it, and reads
    what the clone remembers. The source's own branches are asked as
    `execute --local-remote-dir` asks them, of the source as a remote
    (`_branches_at`); one that cannot be listed is no branch `execute`
    pushes to there."""
    if _tracking_branch_problem(source, TRACKING_KEY, tracking) is not None:
        return False
    try:
        return tracking in _branches_at(str(source.path), source.path)
    except (CommandFailed, OSError):
        return False


def _plan_fields(plan: Plan) -> list[tuple[str, tuple]]:
    """A plan's values as its loader read them, each named by its key in the
    plan, with the lines `_template_values` would write them into: `(the
    placeholder that carries it, the field)`, so that `_misread_findings`
    can leave to the project's own validator a value it judges.

    A key the plan does not carry is left out: `execute` fills it with a
    default of this tool's own (`main`, `private`, today's date), and none of
    those is misread. So is a value `execute` never gets as far as writing
    (`_execute_gets_to_write`): it refuses it first, as `unsafe-value` or as
    #255's `plan-unwritable-value`, or `gh` or `git` does. A leg path is asked about
    only when it is text with no `plan-bad-leg-path` of its own, so one
    wrong value is one finding. An id `Plan.project_id` refuses, or a
    refused leg name it is derived from, is refused on its own account by
    `check` and `execute` alike.
    """
    fields: list[tuple[str, tuple]] = []
    try:
        fields.append((ID_PLACEHOLDER, _id_field(plan)))
    except Refusal:
        pass
    fields += [(placeholder, _field(key, placeholder, plan.get(key)))
               for key, placeholder in MANIFEST_FIELDS.items()
               if plan.get(key) is not None
               and _execute_gets_to_write(key, plan.get(key))]
    for (what, value), placeholder in zip(_plan_leg_paths(plan),
                                          LEG_PATH_PLACEHOLDERS.values()):
        if isinstance(value, str) and leg_path_problem(what, value) is None:
            fields.append((placeholder, _field(what, placeholder, value)))
    # Each pin `execute` writes, by the product it lists in the manifest
    # (`_template_table`), less one no file can hold, which is #255's
    # finding alone. None at all where the plan's `pins:` has a finding of
    # its own (`_read_pins`, #273): `execute` refuses such a plan before any
    # leg exists, and one wrong pin is one finding. A product given twice is
    # one such finding (`plan-pin-collides`), so each is asked about once.
    recorded, pin_findings = _read_pins(plan)
    naming = NamingPolicy.load(NAMING_POLICY)
    return fields + [(PINS_PLACEHOLDER,
                      _pin_field(PIN_IN_PLAN, plan, product, naming))
                     for _, product, _ in ([] if pin_findings else recorded)
                     if _execute_gets_to_write("pins", product)]


def _misread_findings(plan: Plan, unwritten=()) -> list[str]:
    """`check`'s FINDING for each plan value the project's loader would
    misread (#181) and the project's own validator would NOT refuse as the
    loader reads it, of the values `execute` writes in every mode
    (`_execute_gets_to_write`). `unwritten` names the placeholders of values
    the caller knows `execute` does not write in every mode, by a question
    only it can ask, of the source: the tracking branch
    (`_a_branch_execute_writes`, #479).

    THE VALIDATOR IS ASKED FIRST, as `check` asks it (`_manifest_findings`,
    the same `ignore`), and a value it makes a finding about is its alone,
    as on main, and not also this (while the template wrote `id:` bare,
    `id: "007"` was `manifest-id: id is 7` alone). Where it refuses the
    whole file (as a pin `? x` did while the pins' list was written bare,
    before #514) or makes a
    finding about no one value, no value can be said to
    pass it, so every value is its, as on main (rv181f's G1, G2); and where
    it is asked about no manifest (`_manifest_values` is None, as for an
    `elected_on:` `election_date` refuses, #294's finding), this rule names
    no value either.
    That is what makes this rule's remediation true of every value it
    follows: `execute` writes it as it stands, and the run would still end
    `adoption verified`. A leg path is this rule's wherever a template
    writes it bare (none has since #259): `check` leaves the validator's
    leg-path codes to `_leg_findings` (`LEG_PATH_CODES`), and `execute`
    writes it."""
    judged = _validator_judged(plan)
    if judged is None:
        return []
    left = judged | frozenset(unwritten)
    return [f"FINDING plan-manifest-misread: {problem}."
            for placeholder, field in _plan_fields(plan)
            if placeholder not in left
            for problem in manifest_misreads([field])]


# ---------------------------------------------------------------------------
# The tracking branch is a branch of the source (#479)
# ---------------------------------------------------------------------------
#
# `tracking_branch` is three things at once: the branch both legs are pushed
# to, the branch the assembly root's `project.yaml` says the project tracks
# (its `scripts/bootstrap.py` places each leg on it), and the base `execute`
# opens the split's pull request against. It defaulted to `main` whatever the
# source used, so a `master` or `trunk` source was adopted all the way, both
# legs created and pushed and the split pushed and verified, and then `gh pr
# create --base main` was refused (`Base ref must be a branch`), and the way
# out it printed was the same command.
#
# So `plan` records the branch it reads the source at, its default branch
# (`source.default_branch:`), unless `--tracking-branch` names another; and
# `check` finds, and `execute` refuses before any leg exists, a tracking
# branch that is no branch of the source, which an explicit flag or a hand
# edit can still name. `plan` notes it of the value it records.
#
# WHICH BRANCHES. The pull request goes to the repository the source is a
# clone of, and the source knows that repository's branches as its remote
# `origin`'s: `gh repo clone` and `git clone` fetch every branch. A source
# that has fetched none, a repository with no remote, is asked about its own
# branches; `--local-remote-dir` pushes the split back into it. `plan` and
# `check` ask nothing of the network, and a branch made on GitHub after the
# clone is fetched first, as the remediation says.
#
# BUT A CLONE REMEMBERS WHAT ITS REMOTE HAS SINCE LOST. An ordinary `git
# fetch` does not prune, so a branch deleted or renamed on GitHub stays as
# `origin/<branch>`, and a clone made before GitHub renamed `master` to
# `main` keeps `origin/HEAD -> origin/master`, which `plan` takes as the
# default. Such a plan checked ok, and `execute` pushed both legs and the
# split before GitHub refused the base (#493's review, F1). So `execute`
# also asks the remote itself, before any leg exists
# (`_refuse_a_tracking_branch_the_remote_lacks`).

#: `check`'s finding for a tracking branch the source does not have, and
#: what it prints once after it (#479). `execute` refuses under the same code
#: a tracking branch the remote the split goes to does not have.
TRACKING_BRANCH_MISSING = "plan-tracking-branch-missing"
TRACKING_BRANCH_REMEDIATION = (
    "Remediation: set `tracking_branch:` in the plan to a branch the source "
    "has: its default branch, as `source.default_branch:` records it, unless "
    "the project is to track another. Or re-run `plan` without "
    "`--tracking-branch`, which records that default branch. A branch that "
    "is on GitHub and not yet in the source's clone is fetched into it first "
    "(`git fetch origin`), and then `check` is run again.")
#: Where `_branches_of` reads the branches of a source that has fetched any.
ORIGIN_BRANCHES = "refs/remotes/origin/"
#: How many branches a finding names; past it, the rest are counted.
BRANCHES_NAMED = 8


def _branches_of(source: Source) -> tuple[str, list[str]]:
    """`(whose, branches)`: the branches of the repository the split's pull
    request goes to, as the source knows them, and how a finding names
    where they were read: its remote `origin`'s when it has fetched any,
    and otherwise its own. Each name is read as `Source.tree` reads a path,
    so a byte that is not UTF-8 is kept rather than refused."""
    raw = git_out(["for-each-ref", "--format=%(refname)", "refs/heads/",
                   ORIGIN_BRANCHES], cwd=source.path, binary=True)
    refs = [_git_path(line) for line in raw.splitlines()]
    fetched = sorted(ref[len(ORIGIN_BRANCHES):] for ref in refs
                     if ref.startswith(ORIGIN_BRANCHES)
                     and ref != f"{ORIGIN_BRANCHES}HEAD")
    if fetched:
        return "the source's remote `origin`", fetched
    return "the source", sorted(ref[len("refs/heads/"):] for ref in refs
                                if ref.startswith("refs/heads/"))


def _tracking_branch_problem(source: Source, what: str,
                             tracking: str) -> str | None:
    """Why `tracking`, named as `what`, cannot be this adoption's tracking
    branch, as a sentence; None when it is a branch of the source as
    `_branches_of` reads them. ONE TEST, asked by `plan` as a NOTE and by
    `check` and `execute` as `plan-tracking-branch-missing`."""
    whose, branches = _branches_of(source)
    if tracking in branches:
        return None
    named = _listed(branches[:BRANCHES_NAMED]) or "none"
    if len(branches) > BRANCHES_NAMED:
        named += f" and {len(branches) - BRANCHES_NAMED} more"
    return (f"{what} is {_spelled(tracking)}, which is no branch of {whose} "
            f"(its branches: {named}; the source's default branch is "
            f"{_spelled(source.branch)}). `execute` pushes both legs to it, "
            "writes it into the root's `project.yaml` as the branch the "
            "project tracks, and opens the split's pull request against it "
            "once both legs and the split are pushed, where GitHub refuses a "
            "base that is not a branch (`Base ref must be a branch`)")


def _tracking_branch_findings(plan: Plan, source: Source
                              ) -> tuple[list[str], list[str]]:
    """`_tracking_branch_problem` of the plan's tracking branch, as `check`
    prints it, and what it prints once after it. The value is the one
    `execute` takes (`_checked_plan_values`): `main` when the plan has no
    `tracking_branch:`, and as `str` makes it."""
    problem = _tracking_branch_problem(
        source, "`tracking_branch`", str(plan.get("tracking_branch", "main")))
    if problem is None:
        return [], []
    return ([f"FINDING {TRACKING_BRANCH_MISSING}: {problem}"],
            [TRACKING_BRANCH_REMEDIATION])


def _tracking_branch_notes(args, source: Source) -> list[str]:
    """What `plan` says when the tracking branch it records is one `check`
    will find: a NOTE, in the words `check` will use, and a line saying what
    follows. Nothing is refused: the plan is the person's to edit."""
    problem = _tracking_branch_problem(source, "the tracking branch",
                                       args.tracking_branch)
    if problem is None:
        return []
    return [f"\nNOTE {problem}.",
            f"     `check` reports this as `{TRACKING_BRANCH_MISSING}` while "
            "`tracking_branch:` names it; `plan` refuses nothing for it, "
            "because the plan is yours to edit."]


#: `execute`'s refusal of a remote `git ls-remote` cannot read, asked before
#: any leg exists whether it has the tracking branch.
REMOTE_UNREADABLE = "adopt-remote-unreadable"
#: How `_refuse_a_tracking_branch_the_remote_lacks` ends, and the sentence it
#: adds under `--local-remote-dir`, where the source is the remote.
REMOTE_LACKS_REMEDIATION = (
    "Remediation: no leg repository was created and nothing was pushed. "
    "`check` reads the branches the source's clone remembers, and a clone "
    "keeps one its remote has since deleted or renamed: an ordinary `git "
    "fetch` does not prune it, and a clone made before GitHub renamed its "
    "default branch still names the old one. In the source, run `git fetch "
    "--prune origin` and `git remote set-head origin --auto`, and where the "
    "default branch was renamed, rename the clone's own to match, as "
    "GitHub's notice of the rename says (`git branch -m <old> <new>`). Then "
    "re-run `plan` (without `--tracking-branch` it records the default "
    "branch the remote names now) and `check`, and run `execute` again.")
LOCAL_REMOTE_LACKS = (
    " Under `--local-remote-dir` the split is pushed back into the source "
    "itself, so the tracking branch must be one of the source's own "
    "branches, and one only its remote `origin` has is not: `git branch "
    "<name> origin/<name>` makes it one.")


def _refuse_a_tracking_branch_the_remote_lacks(urls: dict, tracking: str,
                                               local: bool) -> None:
    """Refuse a tracking branch the repository the split goes to does not
    have, BEFORE a leg repository exists (#479; #493's review, F1).

    `plan-tracking-branch-missing`, as `check` finds it, reads the branches
    the source's clone remembers its remote by, and asks no network. A clone
    of a repository whose `master` GitHub has since renamed to `main` still
    has `origin/master`, and `origin/HEAD` names it, so `plan` recorded
    `master` and `check` passed it. `execute` then created and pushed both
    legs and the split before `gh pr create` refused the base, `Base ref must
    be a branch`, where the same clone had adopted against `main` before
    #479. A branch named by `--tracking-branch` and deleted on GitHub since
    the clone's last fetch went the same way.

    So the branch is asked of the very remote the split is pushed to, with
    `git ls-remote`, as `_refuse_a_split_branch_left_behind` asks it about
    the split branch: the answer is the one the pull request will get. Under
    `--local-remote-dir` that remote is the source itself, the split's
    destination there, so its own branches are the ones asked. A remote that
    cannot be read is refused as `adopt-remote-unreadable`, at the same
    point: the split push needs it as much, and that came after both legs.
    """
    ref = f"refs/heads/{tracking}"
    remote = _spelled(urls["assembly"])
    try:
        listed = run(["git", "ls-remote", urls["assembly"], ref])
    except (CommandFailed, OSError) as exc:
        why = (f"exit {exc.code}: {' '.join(exc.output.split())}"
               if isinstance(exc, CommandFailed) else str(exc))
        raise Refusal(
            REMOTE_UNREADABLE,
            f"`git ls-remote` could not read {remote}, the repository the "
            f"split is pushed to, to ask whether it has {_spelled(tracking)}, "
            f"the plan's `tracking_branch`: {why}",
            "Remediation: no leg repository was created and nothing was "
            "pushed. `execute` pushes the split to that repository, which "
            "needs it as readable as this question does, so the run stops "
            "here and not once both legs exist. Make it readable from here "
            "-- its url, the network, the credentials git uses for it -- and "
            "run `execute` again.") from exc
    if any(line.split("\t")[-1] == ref for line in listed.splitlines()):
        return
    raise Refusal(
        TRACKING_BRANCH_MISSING,
        f"`tracking_branch` is {_spelled(tracking)}, which {remote}, the "
        "repository the split is pushed to, does not have as `git ls-remote` "
        "reads it now: "
        + ("it is the branch the split is to be merged into there, and the "
           "one the root's `project.yaml` says the project tracks" if local
           else "`execute` opens the split's pull request against it once "
           "both legs and the split are pushed, where GitHub refuses a base "
           "that is not a branch (`Base ref must be a branch`)"),
        REMOTE_LACKS_REMEDIATION + (LOCAL_REMOTE_LACKS if local else ""))


def _checked_plan_inputs(args, source: Source,
                         naming: NamingPolicy) -> tuple[dict, list]:
    """Every value the plan will RECORD, defaulted and checked before one of
    them is written. Returns `(names, pins)`, `pins` being
    `declared_pin_values`'s `{product: PIN_* values}`, each digest read.

    Split out of `cmd_plan` for #138, and the order inside it is the order the
    refusals came in: a run that got as far as naming the three legs before it
    refused an unparseable `--elected-on` would send a reader looking in the
    wrong place for the line that was wrong.
    """
    # Which of the flags `plan` fills in by itself were passed: a value it
    # filled in is named by where it came from, should it be refused below.
    # Not `given`, which #479 binds below to whether `--tracking-branch` was.
    flags_given = {key for key in FLAG_DEFAULTS if getattr(args, key)}
    args.project = checked_value("--project", args.project)
    # THE SOURCE'S OWN BRANCH, UNLESS ONE IS NAMED (#479): the branch `plan`
    # reads the source at is the one its pull request can be opened against.
    # A default this tool filled in is named by where it came from, as
    # `--elected-by` is below, and not as a flag the person never passed.
    given = args.tracking_branch is not None
    args.tracking_branch = checked_value(
        _flag_named(TRACKING_KEY, {TRACKING_KEY} if given else set()),
        args.tracking_branch if given else source.branch)
    # The ONE question first -- spelling, Git's and Windows's names, then the
    # alphabet `checked_value` allows -- so `spec/` is refused here with the
    # spelling to retype, before a plan that `check` and `execute` would have
    # to refuse again is ever written. `checked_value` still runs after it: it
    # is the gate that hands back the text.
    spec, code = legs = _flag_leg_paths(args)
    _refuse_bad_leg_paths("adopt-bad-leg-path", *legs)
    # EACH `--pin`'S FILE AGAINST THE SHAPE'S OWN AND AGAINST EACH OTHER, from
    # the arguments as typed, in the scaffold's words (#241, #273), and
    # before the leg paths, which are asked about every pin's file and would
    # miscount one written over the shape's or listed twice. A name with no
    # `@<commit>` is `parse_pin`'s `pin-malformed`. No digest is read yet.
    args.pin_owner = checked_value("--pin-owner", args.pin_owner)
    refuse_colliding_pins(args.pin, args.pin_owner, "adopt-pin-collides")
    products = list(declared_pin_products(args))
    # Then the paths the shape writes, which are known before any plan is
    # (#172), each pin's file among them (#273). A path the plan keeps in the
    # root is `check`'s to find: the plan's answers are edited after this
    # writes them. `plan` only notes the ones it wrote itself
    # (`_kept_collision_notes`).
    collisions = leg_path_collisions(legs, neutral_pins=products)
    if collisions:
        raise Refusal("adopt-leg-path-collides", " ".join(collisions),
                      _leg_collision_remediation(products))
    args.spec_path = checked_value(*spec)
    args.code_path = checked_value(*code)
    args.id = args.id or args.project.lower()
    if not PROJECT_ID_RE.match(args.id):
        raise Refusal("adopt-bad-id",
                      f"--id {args.id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    # NO ORG IS `adopt-no-org`, asked before `checked_value` (#292). The `-`
    # that once stood in for a missing one reached `checked_value` first,
    # which refused `--org is '-'`, a value nobody passed; this refusal was
    # never reached. A source with no `origin`, one whose URL is not UTF-8,
    # and one whose URL ends in no `org/repo` (`_remote_repository`) all name
    # no org, and the refusal says each of the three: it is asked of a source
    # that HAS an origin as often as of one that has none.
    args.org = args.org or (source.repository or "/").split("/")[0]
    if not args.org:
        raise Refusal(
            "adopt-no-org", "the source's `origin` names no organisation "
            "this tool can read: it has none, its URL is not UTF-8, or its "
            "URL ends in no `org/repo`",
            "Remediation: pass --org <org>.")
    args.org = checked_value("--org", args.org)
    # IN PLACE, THE SOURCE'S OWN NAME (#499), as soon as both halves are
    # known and before any pin's digest is read: `execute` acts on the
    # repository `--org` and `--project` name, so they must be the source.
    _refuse_another_repository(args, source, naming, set(products))
    args.elected_on = args.elected_on or _dt.date.today().isoformat()
    # Read before the plan is written, whether or not it is what chooses the
    # reference: a date the tools cannot parse would reach `execute` as a
    # manifest field instead of as a question.
    election_date(args.elected_on)
    args.reference = args.reference or default_reference(args.elected_on)
    # A value `plan` filled in by itself is named by where it came from, as
    # #181 names one, and not as a flag the person never passed.
    elector = _flag_named(ELECTED_BY_KEY, flags_given)
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
    if args.pin and args.pin_source is not None:
        _refuse_an_unrecordable_pin_source(args.pin_source, products)
    names = _names(args.project)
    pins = declared_pin_values(args)
    _check_names(naming, names, set(pins), source)
    # LAST here, over every value as the plan will record it: `execute`
    # writes them into the project's own YAML. The project's own validator
    # is asked FIRST (#261): a value it refuses is refused in its words
    # alone, as on main (rv181f's G1). Then one its loader would read as
    # something else that the validator accepts is refused before the plan
    # exists (#181); since #259 and #514 that is only a value on a line
    # written bare, so every value that refusal names is one `execute` would
    # write and end `adoption verified` with, as its remediation says.
    planned = _refuse_unholdable_values(args, flags_given, names, pins,
                                        naming)
    _refuse_misread_values(args, flags_given, pins, source, planned, naming)
    return names, pins


def _refuse_misread_values(args, given: set, pins: dict, source: Source,
                           planned: "Plan", naming: NamingPolicy) -> None:
    """`plan`'s refusal, before the plan exists, of each value it is about
    to record that the project's loader would read back as something else
    (#181), named as `_flag_fields` names it. Asked after the project's own
    validator (`_refuse_unholdable_values`), whose refusal is the one a
    value it refuses gets. Apart from `_checked_plan_inputs`, which #479's
    default made as complex as Sonar allows."""
    misread = manifest_misreads(
        _flag_fields(args, given, pins, source, planned, naming))
    if misread:
        raise Refusal("adopt-manifest-misread",
                      " ".join(f"{problem}." for problem in misread),
                      f"{MANIFEST_MISREAD_REMEDIATION} No plan was written.")


def _refuse_an_unrecordable_pin_source(source: Path, products) -> None:
    """`--pin-source` is a path `plan` can record, or this refuses it as
    `adopt-unwritable-value`, before any digest is read and before a plan
    is written.

    `plan` records the path in each pin's `digest_source:`, `execute`
    writes that into the pin file as it stands, and `check` holds it to
    `one_printable_line` (`_pin_row_problem`). A path holding a line break,
    an ESC or a byte that is not UTF-8 was planned, exit 0, and printed raw
    in `plan`'s report -- the line break split it -- and `check` then found
    `plan-pin-malformed` and said to re-run the `plan` that wrote it. So
    `plan` asks `check`'s question of the value it would record, and says
    why in #270's words (`unwritable_reason`) where they name it; the one
    thing `check` refuses that they do not is an invisible formatting
    character, a zero-width joiner among them. The `local-clone (` and `)`
    that `declared_pin_values` puts around the path are printable, so the
    path alone decides.
    """
    text = str(source)
    if one_printable_line(text):
        return
    reason = (unwritable_reason(text)
              or "it holds an invisible formatting character")
    files = ", ".join(f"`{neutral_pin_path(product)}`"
                      for product in products)
    raise Refusal(
        "adopt-unwritable-value",
        f"--pin-source is {text!r}, which `plan` records in each pin's "
        f"`digest_source:` and `execute` writes into {files}, and {reason}.",
        "Remediation: no plan was written. Point --pin-source at a clone "
        "whose path is one line of printable UTF-8 text, or drop "
        "--pin-source and let `gh api` read the forge. `check` refuses a "
        "`digest_source:` that is not one printable line as "
        "`plan-pin-malformed`, because `execute` writes it into the pin file "
        "as it stands.")


# ---------------------------------------------------------------------------
# The project must be able to hold what `execute` writes into it (#261)
# ---------------------------------------------------------------------------
#
# `execute` puts the plan's values into the assembly root's `project.yaml`, and
# the project's own `scripts/validate-manifest.py` then judges them at its
# first bootstrap. Nothing here asked it first, so a blank `--elected-by` or
# `--reference`, `--elected-on 2026-W41-6` or `20261011` (which
# `date.fromisoformat` reads from Python 3.11), `--org test+org`, and a plan
# edited to `visibility: secret` or `elected_by: null`, each ended
# `adoption verified` over a project whose own gate was red, with both legs
# already pushed; the way back was an edit to `project.yaml`, which AGENTS.md
# tells an agent never to make to turn a row green.
#
# `plan` (a flag), `check` (a FINDING) and `execute` (a refusal, through
# `_entry_findings`, before any leg exists) ask ONE question of the values: the
# `project.yaml` `execute` would write from them, put through the validator the
# template ships, through `shape_materialize.manifest_value_problems`, which
# loads that validator rather than copying a rule of it. The table is built by
# `_template_table`, which `execute`'s `_template_values` also calls, so it is
# the one `execute` renders from. Only the validator's question is asked here,
# and it is asked FIRST: a value it refuses is its alone. Whether the
# project's YAML reader reads back as the text it is a value the validator
# accepts -- since #259 and #514, only one on a line written bare -- is
# #181's, asked after (`_misread_findings`), and the scaffold asks both.

#: How `check` and `execute` name each value the manifest records: its key
#: in the plan. The id's placeholder and `MANIFEST_FIELDS` are #181's, so
#: that each placeholder and each key is spelled once; the organisation is a
#: value only the validator is asked about.
MANIFEST_PLAN_KEYS = {
    ID_PLACEHOLDER: "id",
    **{placeholder: key for key, placeholder in MANIFEST_FIELDS.items()},
    "ORG": "org",
}


def _manifest_flag_names(given: set) -> dict[str, str]:
    """How `plan` names each value the manifest records: by the flag that
    gives it, as `_flag_fields` spells #181's, and a value `plan` filled in
    when its flag is not in `given` by where it came from (`_flag_named`,
    #529), so the validator's sentence never points at a flag nobody typed."""
    return {placeholder: _flag_named(key, given)
            for placeholder, key in MANIFEST_PLAN_KEYS.items()}


#: And the same names when the person typed every flag: the key, dashed. No
#: production code asks for this table any more (`_refuse_unholdable_values`
#: asks `_manifest_flag_names` for the flags given); the tests pin it.
MANIFEST_FLAGS = _manifest_flag_names(set(FLAG_DEFAULTS))

#: The validator's findings about a leg's mount path, which `check` already
#: reports as `plan-bad-leg-path` and `plan-leg-path-collides` from the same
#: list (`_leg_findings`): said once, in the words of the rule that judges it.
LEG_PATH_CODES = ("manifest-leg-path", "manifest-leg-path-collision")


def _flag_plan(args, names: dict, pins: dict) -> "Plan":
    """The plan `plan` is about to write, as `Plan` reads one: the values it
    records, under the keys `render_plan` writes them to. `pins` is
    `declared_pin_values`' `{product: PIN_* values}`, recorded as `plan`
    writes each pin since #273: one mapping of `PIN_FIELDS`.

    Built from the values and not read back from the file, which lists every
    path of the source: `plan` asks what `check` will ask of the same keys,
    before a file exists to read. `tests/test_adopt_manifest_values.py` holds
    the two to the same keys.
    """
    return Plan(Path(args.out), {
        "kind": PLAN_KIND, "mode": "in-place", "project": args.project,
        "org": args.org, "id": args.id, "visibility": args.visibility,
        "tracking_branch": args.tracking_branch,
        "elected_by": args.elected_by, "elected_on": args.elected_on,
        "reference": args.reference,
        "legs": {**names, "spec_path": args.spec_path,
                 "code_path": args.code_path},
        "pins": [{key: values[placeholder] for key, placeholder in PIN_FIELDS}
                 for values in pins.values()]})


#: The commit and the tree digest the manifest rendered FOR VALIDATION holds
#: in `shape.commit` and `shape.digests.tree_sha256`, in place of the real
#: ones `execute` reads and writes (`_template_values`). The validator the
#: template ships holds each to its FORM (`COMMIT_RE`, `SHA256_RE`) and
#: compares neither with anything, and no tool names either to a person, so
#: reading the real ones (`git rev-parse HEAD`, then `git ls-tree -r` of the
#: whole standard) bought `plan` and `check` nothing, and made them skip the
#: question silently from a tree with no git revision. Lowercase hex with a
#: letter in it, so that the project's YAML reader reads each as text and never
#: as a number (forty digits would be an integer), quoted or not.
_VALIDATION_SHAPE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_VALIDATION_SHAPE_DIGEST = ("0123456789abcdef0123456789abcdef"
                            "0123456789abcdef0123456789abcdef")


def _manifest_values(plan: Plan, naming: NamingPolicy) -> dict | None:
    """The substitution table `execute` renders the manifest from, as it
    would build it from this plan, FOR VALIDATION AND NEVER FOR WRITING; None
    where the plan's names are not ones the naming policy classifies, which
    `check` and `execute` report in their own words (`_check_names`) and the
    manifest cannot be rendered without, and None where its `elected_on:` is
    a date `election_date` refuses, which `_elected_on_findings` reports in
    the plan key's own words (#294).

    `_template_table` is asked, not copied, and `execute`'s `_template_values`
    is that same table with the real commit and digest, so the table cannot
    differ from `execute`'s. The four leg commits and digests are not known
    before the legs exist and are not in the manifest; the standard's own
    commit and tree digest are replaced by the fixed pair above, so that no
    `git` runs here and a checkout that cannot name its revision is asked the
    same question as any other. A refusal of the plan's own names, id,
    organisation or leg paths is raised here as it is by `check` and `execute`
    a few lines later. The organisation and the id are asked BEFORE the date
    is: a bad date does not change which problem either command names first.
    """
    if not isinstance(plan.legs, dict):
        # The doctor's PLACEMENT plan writes `legs:` as a list (see
        # `_plan_leg_path`): it names no repositories, so there is no
        # manifest to render from it.
        return None
    names = plan.names()
    pins = set(plan.pins)
    try:
        _check_names(naming, names, pins)
    except Refusal:
        return None
    # The organisation and the id are asked BEFORE the date's guard below.
    # `checked_value` refuses an `org:` this tool will not put on a command
    # line (`unsafe-value`; `execute` meets it first, in `_repository_urls`),
    # and `Plan.project_id` refuses an `id:` that is not a project id
    # (`plan-bad-id`; `_template_table` reads it again). After the guard,
    # neither was asked of a plan whose date is a finding: `check` listed the
    # date where `execute` refused the organisation, and refused the id where
    # `execute` refused the date.
    org = checked_value("org", plan.get("org"))
    _ = plan.project_id
    if _elected_on_findings(plan):
        # Reported in the plan key's own words (#294), and the reference the
        # manifest records is chosen BY that date when the plan names none:
        # there is no manifest to ask about until it is one.
        return None
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    (_, spec_path), (_, code_path) = _plan_leg_paths(plan)
    return _template_table(
        plan, names, repositories, {"assembly": ""}, str(spec_path),
        str(code_path), str(plan.get("tracking_branch", "main")), {}, {},
        _VALIDATION_SHAPE_COMMIT, _VALIDATION_SHAPE_DIGEST, pins, naming)


def _manifest_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """What the project's own validator would refuse of this plan's values,
    as `check` prints them (one FINDING each), and what it prints once after
    them. `[]` and `[]` when it would pass, or when the plan's names, or its
    date, are refused in their own words (`_manifest_values`).

    EVERY VALUE IS ASKED, ONE THE PLAN'S READER READ AS NOT TEXT INCLUDED,
    and one #181's misread rule would also call misread: a value this rule
    refuses is this rule's alone, and the misread rule leaves it here
    (`_misread_findings`, rv181f's G1). So `visibility: true` is this
    rule's, as `visibility: secret` is, and one wrong value is one
    finding. (`elected_on: 20260902` is #294's, and this rule is not asked
    about it: `_manifest_values`.) A value read as not text is named by
    what was read (`_named_as_read`), because the sentence goes on to
    quote `str` of it, the text `execute` would write and not what the
    plan says.
    """
    naming = NamingPolicy.load(NAMING_POLICY)
    values = _manifest_values(plan, naming)
    if values is None:
        return [], []
    problems = manifest_value_problems(values, naming, _named_as_read(plan),
                                       misreads=False, ignore=LEG_PATH_CODES)
    if not problems:
        return [], []
    return ([f"FINDING plan-manifest-invalid: {sentence}"
             for _, sentence in problems],
            [f"{MANIFEST_INVALID_REMEDIATION} `execute` writes the plan's "
             "values into the project's `project.yaml` as they stand, so "
             "correct each one named here in the plan, or re-run `plan` with "
             "a value the validator accepts."])


def _validator_judged(plan: Plan) -> frozenset[str] | None:
    """The placeholders whose value the project's own validator makes a
    finding about, asked as `_manifest_findings` asks it; None where no
    value can be said to pass it (`manifest_judged`), or where the plan's
    names are refused in their own words and there is no manifest to ask
    about (`_manifest_values`)."""
    naming = NamingPolicy.load(NAMING_POLICY)
    values = _manifest_values(plan, naming)
    if values is None:
        return None
    return manifest_judged(values, naming, ignore=LEG_PATH_CODES)


def _named_as_read(plan: Plan) -> dict[str, str]:
    """How a sentence of the validator's names each value: by its key in the
    plan, and a value the plan's reader read as something that is not text
    by what was read too (review181's N2), as in `visibility, read out of
    the plan as the boolean true, is 'True'`. A value the plan holds as
    text, or as no value at all, is named by its key alone."""
    named = {}
    for placeholder, key in MANIFEST_PLAN_KEYS.items():
        value = plan.get(key)
        named[placeholder] = (
            key if value is None or isinstance(value, str) else
            f"{key}, read out of the plan as {_the_loader_made(value)},")
    return named


def _refuse_unholdable_values(args, given: set, names: dict, pins: dict,
                              naming: NamingPolicy) -> "Plan":
    """`plan` refuses, before it writes a file, what `check` would find in the
    plan it is about to write (#261): the three repository names it derives,
    held to `checked_value` as `check` holds `legs:` (a `--project` of 251 to
    255 characters planned, then `check` refused `legs.spec`), and the
    manifest's values, through the one question `check` asks of them. It
    returns that plan, built once (`_flag_plan`), for #181's question to ask
    of the same values (`_refuse_misread_values`). `given` says which flags
    the person passed: a value `plan` filled in by itself, an elector
    `git config user.name` left empty, is named by where it came from
    (#529)."""
    plan = _flag_plan(args, names, pins)
    values = _manifest_values(plan, naming)
    if values is not None:
        refuse_manifest_values(
            "adopt", values, naming, _manifest_flag_names(given),
            "No plan was written.", misreads=False)
    return plan


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
                       follow_ups: list, seeded: list, out: Path,
                       pins: dict | None = None) -> None:
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
    # Each pin as the scaffold's plan prints it: what is pinned, at which
    # commit and digest, the file `execute` writes, and how the digest was
    # read (#273), that last `_shown`, as every path this report prints is.
    for product, values in (pins or {}).items():
        print(f"pin        {values['PIN_REPOSITORY']} @ "
              f"{values['PIN_COMMIT'][:12]} tree "
              f"{values['PIN_TREE_SHA256'][:12]}… -> "
              f"{neutral_pin_path(product)} "
              f"({_shown(values['PIN_DIGEST_SOURCE'])})")
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
    for line in _empty_symlink_notes(tree):
        print(line)
    for line in _tracking_branch_notes(args, source):
        print(line)
    unresolved = [e for e in entries if e.leg is None]
    # A default is still a question (#528): it is printed with the question,
    # before the paths `execute` refuses over, which stay last.
    proposed = [e for e in entries if e.leg is not None and e.review_required]
    print(f"\nplan written to {out}")
    if proposed:
        print(f"{len(proposed)} path(s) carry their rule's default answer, "
              "which `execute` takes as written unless it is changed:")
        for entry in proposed:
            print(f"  {_shown(entry.path)} (leg: {entry.leg})\n"
                  f"      {entry.question}")
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

    # The project's own validator is asked inside, before #181's question.
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
    #
    # A `single-repository.yaml` that declares no record is asked as any
    # other top-level data file is, before anything reads the entries
    # (#528). The default a rule names is written into an entry last, after
    # both re-asks: `ask_about_refused_paths` passes over a path answered
    # `drop`, so a default written in first would be taken for a person's
    # answer there. What the rules imply is read without it, and it changes
    # none of what is read from them, because `drop` puts the path in no leg
    # and keeps nothing in the root.
    ruled = ask_about_a_record_only(
        policy, walk(policy, [(path, size) for path, _, _, size in tree]),
        source)
    implied = ask_about_refused_paths(ruled, tree)
    materialized = _predict_collisions(
        implied, attributes_link=any(path == ATTRIBUTES and mode == SYMLINK_MODE
                                     for path, mode, _, _ in tree))
    follow_ups = follow_ups_for(source, implied, names, args.spec_path,
                                args.code_path, materialized)
    seeded = seeded_legs(assigned_paths(implied))
    entries = with_defaults(ask_about_refused_paths(
        ask_about_submodules(policy, ruled, tree), tree))
    out = Path(args.out)
    write_lf(out, render_plan(args, source, entries, names, pins, follow_ups,
                              seeded))

    _print_plan_report(args, source, tree, entries, follow_ups, seeded, out,
                       pins)
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


def _predict_collisions(entries: list[Entry], *,
                        attributes_link: bool = False) -> list[str]:
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

    Each follow-up is told the WHOLE list: the Makefile's names what runs
    until it is merged, and that depends on whether `scripts/bootstrap.py`
    went aside too (#493's review, F2).

    `attributes_link` says the source's root `.gitattributes` is a symlink,
    read from the source tree's mode as `execute` reads it from the index:
    no block is appended to one, and its follow-up says so (#471).
    """
    surviving = {e.path for e in entries if e.leg == "root"}
    beside = {path: f"{COLLISION_DIR}/{path}"
              for path in sorted(set(assembly_root_paths()))
              if path in surviving or f"{path.split('/')[0]}/" in surviving}
    return [collision_follow_up(path, actual, beside,
                                attributes_link=attributes_link)
            for path, actual in beside.items()]


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
        # Each read takes only what `plan` writes, and `_plan_key_findings`
        # names what it leaves out (#386). `legs:` is kept as it stands: the
        # doctor's PLACEMENT plan, handed here by `tests/test_shape_doctor.py`,
        # carries it as a list, and its readers ask its type themselves.
        self.entries = [e for e in _plan_list(data, "paths")
                        if isinstance(e, dict)]
        self.legs = data.get("legs") or {}
        # The products only: what the naming policy classifies by. Whether
        # each entry is a pin `execute` can write is `_read_pins`'s (#273);
        # `_pin_products` reads a list only, as `_plan_list` does.
        self.pins = _pin_products(data.get("pins"))

    @classmethod
    def load(cls, path: Path) -> "Plan":
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("plan-unreadable", f"{path}: not a mapping")
        return cls(path, data)

    @property
    def source(self) -> dict:
        """The plan's `source:` when it is a mapping, as `plan` writes it, and
        `{}` for anything else, which `_plan_key_findings` names (#386)."""
        source = self.data.get("source")
        return source if isinstance(source, dict) else {}

    @property
    def source_commit(self) -> str:
        return str(self.source.get("commit") or "")

    def open_source(self, override: str | None, work_root: Path) -> Source:
        spec = override or self.source.get("local_path") \
            or self.source.get("repository")
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

        Only a `legs:` MAPPING holds them, as `_plan_leg_path` reads it:
        anything else is read as no `legs:` at all, and never with `.get` on
        a number or a list. `check` and `execute` name such a `legs:` first,
        in `_plan_key_findings`, before this is asked (#386).
        """
        legs = self.legs if isinstance(self.legs, dict) else {}
        return {role: checked_value(f"legs.{role}", legs.get(role))
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
        the state the consent exists to be deliberate about.

        Each item of a LIST that is text, as `plan` writes it: text on the
        key's own line is not read one character at a time, and what is left
        out is named by `_plan_key_findings` (#386)."""
        return {role for role in _plan_list(self.data, "allow_empty_legs")
                if isinstance(role, str) and role}

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

    THE QUESTION a finding repeats is the one value of a plan that people and
    AIs edit, so it is `_shown`: as it is, and printed exactly as before,
    unless a character in it is not printable, and then `_spelled` whole. A
    line feed in it ended the finding's line and began another that
    `grep '^FINDING'` read as `check`'s own, and an ESC reached the terminal
    (#328). Every question `plan` writes is printable.
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
                f"question was: {_shown(str(entry.get('question')))}")
        elif str(leg) not in LEG_VALUES:
            findings.append(
                f"FINDING plan-bad-leg: {path} declares leg {leg!r}; it is "
                f"one of {list(LEG_VALUES)}")
    if isinstance(plan.legs, dict):
        findings += _root_shape_findings(plan, tree)
        # THE PINS, LAST (#273): each `pins:` entry `execute` cannot write a
        # pin file from, two pins at one file, and a path the root keeps
        # where a pin is written, the shape's own pin among them (#524).
        # Each finding about an entry names the `plan` that records the pin
        # whole. A leg mounted over a pin's file is
        # `plan-leg-path-collides`, above, with the shape's own paths.
        findings += _pin_findings(plan, tree)
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
# THE MANIFEST HAS NO COPY THAT STANDS IN FOR IT (#305). `project.yaml` is
# the one path where the root holding the source's own is refused outright,
# not asked about its copy: `shape-doctor.py`, the root's validators and
# `make bootstrap` read the manifest at the root itself. Answered `root`
# (which `plan`'s question used to offer), the source's own file stayed
# there, `execute` wrote the shape's manifest beside it as
# `shape/project.yaml`, said "nothing was overwritten" and `adoption
# verified`, and the doctor called the assembly NOT A SHAPE ROOT, its first
# `make bootstrap` failing naming, manifest and pins. A kept path AT it, or
# a kept directory there, is `plan-root-blocks-manifest`; there is then no
# copy to ask about, because the remediation takes the path out of the root.
# A symlink there is one too, even one that leads nowhere, which `place`
# writes the manifest THROUGH and which the doctor on Linux then reads as a
# shape root: a clone that makes no symlinks holds the link as a file naming
# its target, and #183 refuses a link to nothing at a shape path anyway.
# The other paths the shape writes keep the copy and the follow-up to merge
# it, which `plan` already predicts for a `Makefile` or a `README.md` it
# keeps in the root itself.
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
#: And for a kept path where the shape writes its manifest (#305).
ROOT_BLOCKS_MANIFEST = "plan-root-blocks-manifest"
#: The shape's manifest, one of the paths `assembly_root_paths` lists: what
#: `shape-doctor.py`, the root's validators and `make bootstrap` read at the
#: assembly root, and what `contracts/path-classification.yaml` asks about
#: under `ambiguous-project-yaml`, with no `root` among its answers.
SHAPE_MANIFEST = "project.yaml"


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


def _kept_there(disk: _KeptTree, path: str) -> tuple[tuple, list]:
    """What the plan keeps at `path` on `disk`: the group `("at", path)` and
    the row AT it, or `("dir", path)` and the rows below a kept directory
    there. A submodule is never one of them: it is `plan-submodule-root`'s
    (#166), and said once there."""
    at = disk.at(path)
    rows = [row for row in ([at] if at else disk.under(path))
            if row[1] != GITLINK_MODE]
    return ("at" if at else "dir", path), rows


def _shape_blocks(disk: _KeptTree) -> list[tuple]:
    """`(code, shape path, where it is written, group, kept rows)` for each
    path of `assembly_root_paths` that `place` would stop at or overwrite on
    `disk`, in the order it writes them, and for the manifest, which no copy
    stands in for, wherever the root holds it (#305). The disk says both
    whether the root already holds a path, so whether its copy is written at
    all, and whether the place is free: a disk that ignores case holds
    `README.md` for a kept `readme.md`. `group` names the one thing in the
    way, so that what one kept path blocks is one finding."""
    out = []
    for rel in assembly_root_paths():
        above = disk.file_above(rel)
        if above:
            out.append((ROOT_BLOCKS_SHAPE, rel, rel, ("file", above[0]),
                        [above]))
            continue
        if not disk.holds(rel):
            continue
        if rel == SHAPE_MANIFEST:
            group, rows = _kept_there(disk, rel)
            if rows:
                out.append((ROOT_BLOCKS_MANIFEST, rel, rel, group, rows))
            continue
        copy = f"{COLLISION_DIR}/{rel}"
        above = disk.file_above(copy)
        if above:
            out.append((ROOT_BLOCKS_COPY, rel, copy, ("file", above[0]),
                        [above]))
            continue
        group, rows = _kept_there(disk, copy)
        if rows:
            out.append((ROOT_BLOCKS_COPY, rel, copy, group, rows))
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
    if code == ROOT_BLOCKS_MANIFEST:
        relation, aside = _overlap(rels[0], path)
        spot = ("" if relation == "is" and not aside else
                f", {'at' if relation == 'is' else 'inside'} "
                f"{_first_and_more(rels)}{aside}")
        found = ("directory" if relation == "contains"
                 else _kind_of(mode).split()[-1])
        beside = ("`execute` would write the shape's manifest beside it as "
                  f"`{COLLISION_DIR}/{rels[0]}`")
        written = (
            f"Where it leads to something, {beside}, and where it leads "
            "nowhere, through it, which a clone that makes no symlinks "
            "holds as a file naming its target; either way it would say "
            if relation == "is" and mode == SYMLINK_MODE else
            f"{beside} and say ")
        return (
            f"the plan keeps {_kind_of(mode)} {named} in the assembly "
            f"root{under}{spot}, where the shape writes its manifest. No "
            "copy stands in for the manifest: `shape-doctor.py`, the root's "
            f"validators and `make bootstrap` read {_first_and_more(rels)} "
            "at the root itself, and there they would find the source's "
            f"{found}. {written}`adoption verified`, after both leg "
            f"repositories were created and pushed: {fix}.")
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
        disabled a source holding `caf\\udce9.md` was extracted and verified,
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


# ---------------------------------------------------------------------------
# Plan values `execute` read late, asked by `check` before any leg exists
# ---------------------------------------------------------------------------
#
# Each value below was read by `execute` after `check` had said `plan ok`, and
# nothing in between asked what it held. `check` now asks, and `execute`
# refuses what it finds through `_refuse_what_check_finds`, before any leg
# exists.
#
# `follow_ups:` (#293). `plan` writes it as a block list, and every reader
# iterated the value with no test that it was one. A hand-edited
# `follow_ups: 5` (or `true`, `1.5`, `false`) ended `check` in
# `TypeError: 'int' object is not iterable`, a traceback with no FINDING
# naming the key, and on main ended `execute` the same way in
# `_commit_the_split`, after both legs were pushed; `abc` was written into the
# split commit's message as three follow-ups, `a`, `b` and `c`, and an item
# `- true` as `True`.
#
# `elected_on:` (#294). Nothing asked whether it was a date but
# `_template_values`, and only for a plan with no `reference:`:
# `default_reference` asked `election_date` after `_create_leg_remotes` had
# made both legs, and the refusal named `--elected-on`, a flag neither `check`
# nor `execute` takes. With `reference:` kept the date was never asked, and
# `execute` wrote `someday` into the manifest. THE DATE IS ASKED OF
# `election_date`, the rule `plan` asks of `--elected-on` and
# `_template_values` of the plan's date, and of nothing else: what that rule
# admits is #261's to decide, and a tighter rule there is asked here with no
# edit. Only the words are this caller's, because the date came from the plan
# file and not from a flag: the refusal `election_date` raises names
# `--elected-on`, which is right for `plan` and wrong here.

#: `check`'s finding for a `follow_ups:` that is not a list of text, and the
#: code `execute` refuses it under (#293).
BAD_FOLLOW_UPS = "plan-bad-follow-ups"

#: Said once after the `follow_ups:` findings.
FOLLOW_UPS_REMEDIATION = (
    "Remediation: write `follow_ups:` in the plan file as `plan` writes it, "
    "a list with one item of text per follow-up, each on its own line as "
    "`  - \"<what is left to do>\"`, or `follow_ups: []` for none. `execute` "
    "writes each item as one line of the split commit's message, so it takes "
    "nothing else: a number or a boolean is not a list, text on the key's own "
    "line would be written one character per follow-up, and an item that is "
    "not text would be written as Python spells it (`True`, `None`).")


def _read_as(value) -> str:
    """What the plan's reader handed back for a value, in words, spelled as a
    YAML plan spells it where that differs from Python (`true`, `null`)."""
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value!r}"
    if isinstance(value, str):
        return f"the text {value!r}"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return f"a mapping of {len(value)} key(s)"
    if isinstance(value, list):
        return f"a list of {len(value)} item(s)"
    return f"a value of type {type(value).__name__}"


def _plan_follow_ups(plan: Plan) -> list[str]:
    """The plan's follow-ups as `execute` writes them into the split commit's
    message: each item of a `follow_ups:` LIST that is text, and nothing for a
    `follow_ups:` that is absent, bare or anything but a list.

    THE ONE READ, for the three readers (`_plan_values`,
    `_print_what_will_happen`, `_commit_the_split`), so that none of them
    iterates a number or spells a string out one character at a time. What it
    leaves out is never silently dropped from a run: `_follow_ups_findings`
    reports it in `check`, and `execute` has refused it through
    `_refuse_what_check_finds` before the split commit is written.
    """
    value = plan.get("follow_ups", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _follow_ups_findings(plan: Plan) -> list[str]:
    """A FINDING for a `follow_ups:` that is present and not a list, or for
    each item of one that is not text; `[]` for a list of text, an empty
    list and a bare key (#293)."""
    value = plan.get("follow_ups")
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"FINDING {BAD_FOLLOW_UPS}: `follow_ups:` is "
                f"{_read_as(value)}, not a list: `execute` writes each item "
                "of a list into the split commit's message as one follow-up"]
    return [f"FINDING {BAD_FOLLOW_UPS}: item {number} of `follow_ups:` is "
            f"{_read_as(item)}, not text: `execute` writes each item into the "
            "split commit's message as one line of text"
            for number, item in enumerate(value, 1)
            if not isinstance(item, str)]


#: `check`'s finding for an `elected_on:` that `election_date` does not read,
#: and the code `execute` refuses it under: the code `plan` refuses a bad
#: `--elected-on` under, said here of the plan's key (#294).
ELECTION_DATE_MALFORMED = "election-date-malformed"

#: Said once after the `elected_on:` finding. It names the plan file's key and
#: no flag: `check` and `execute` take none for the date.
ELECTED_ON_REMEDIATION = (
    "Remediation: edit `elected_on:` in the plan file to the day the shape "
    "was elected, written as a zero-padded ISO date in quotes, e.g. "
    "`elected_on: \"2026-09-02\"`: not 2026-9-2, and not a word like "
    "'yesterday'. `execute` writes it into the project's `project.yaml`, and "
    "a plan with no `reference:` has its reference chosen BY that date, so "
    "it is read before anything is created.")


def _elected_on_findings(plan: Plan) -> list[str]:
    """A FINDING for an `elected_on:` that `election_date` does not read,
    whether or not the plan has a `reference:` (#294); `[]` for a date it
    reads and for no `elected_on:` at all, which `execute` fills with today's.

    The value asked is the one `_template_values` takes, `str` of what the
    plan holds, so the two cannot answer differently. `election_date`'s own
    refusal is not passed on, because its words are `plan`'s: they name
    `--elected-on`, which neither `check` nor `execute` takes. Only THAT
    refusal is a finding about the date: any other `election_date` raises
    is about something else (a rule it could not ask), and is raised as it
    is.
    """
    elected_on = plan.get("elected_on")
    if elected_on is None:
        return []
    try:
        election_date(str(elected_on))
    except Refusal as refused:
        if refused.code != ELECTION_DATE_MALFORMED:
            raise
        chosen = ("" if plan.get("reference") else
                  ", and, the plan naming no `reference:`, chooses the "
                  "reference by it")
        return [f"FINDING {ELECTION_DATE_MALFORMED}: the plan's `elected_on:` "
                f"is {_read_as(elected_on)}, which is not a day written "
                "YYYY-MM-DD, the form `execute` writes into the project's "
                f"`project.yaml`{chosen}"]
    return []


def _plan_field_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """`_elected_on_findings` and `_follow_ups_findings`, in the order `plan`
    writes the two keys (`elected_on:` before `follow_ups:`), and what `check`
    prints once after them."""
    dated, followed = _elected_on_findings(plan), _follow_ups_findings(plan)
    return (dated + followed,
            ([ELECTED_ON_REMEDIATION] if dated else [])
            + ([FOLLOW_UPS_REMEDIATION] if followed else []))


# ---------------------------------------------------------------------------
# The keys a plan is opened by are the types `plan` writes (#386)
# ---------------------------------------------------------------------------
#
# `Plan` read five keys of a plan file without asking their type. `plan`
# writes `source:` and `legs:` as mappings and `pins:`, `allow_empty_legs:`
# and `paths:` as lists, and the file is edited between `plan` and `execute`
# on purpose. `x or []` rescues only the falsy values: a number or a boolean
# ended `check` and `execute` in a `TypeError` or an `AttributeError`, exit 1,
# naming Python's error and not the key, and text, which is iterable, was read
# one character at a time. `pins: openGlass` passed `check`, adopted, and
# wrote eight one-letter neutral-product pins, `G`, `a`, `e`, `l`, `n`, `o`,
# `p` and `s`, which the project's own `validate-pins.py` then refused.
#
# So each is read through one reader that takes only what `plan` writes
# (`_plan_list`, `Plan.source`, `Plan.names`), and `_plan_key_findings` names
# what the reader left out in #293's words: a code per key, `plan-bad-<key>`
# as `follow_ups:`' is `plan-bad-follow-ups`, `_read_as` for what the file
# holds, and each key's remediation said once.
#
# `pins:` IS #273'S. Since #273, `plan` writes it as a list of MAPPINGS, one
# per pin, recording `product:`, `repository:`, `commit:`, `tree_sha256:`
# and `digest_source:`. `_pin_products` reads the products out of a list
# only, and `_read_pins` judges each entry beside the entries: a name alone
# is `plan-pin-unrecorded`, anything else `plan` never writes there is
# `plan-pin-malformed`, each with the `plan --pin` that records the pin
# whole. So only a `pins:` that is no list at all is asked here, and its
# finding is `_read_pins`' own, so that it is said once and under one code.
#
# THEY ARE ASKED FIRST, right after `Plan.load`, and not in `_entry_findings`
# beside #293's and #294's. These keys are what the rest of the run is built
# from: the source is opened from `source:`, the names `execute` refuses on
# first come from `legs:`, and the constructor builds the entries and the
# pins. Every later finding is a statement about what they say, so a `paths:`
# that is not a list would be reported as every source path uncovered.
# `check` reports them, and stops, exit 1, with #293's and #294's findings
# beside them, so that every key of the plan that is not what `plan` writes
# is named in one run. `execute` refuses the same list, in
# `_refuse_what_check_finds`' shape, before the work directory, the source or
# a leg exists.

#: `check`'s finding for each key below that is not what `plan` writes, and
#: the code `execute` refuses it under (#386). A `pins:` that is no list is
#: `_read_pins`' `plan-pin-malformed` (#273).
BAD_SOURCE = "plan-bad-source"
BAD_LEGS = "plan-bad-legs"
BAD_ALLOW_EMPTY_LEGS = "plan-bad-allow-empty-legs"
BAD_PATHS = "plan-bad-paths"

#: Said once after the findings for each key.
SOURCE_REMEDIATION = (
    "Remediation: write `source:` in the plan file as `plan` writes it, a "
    "mapping whose `local_path:` or `repository:` names the repository to "
    "adopt and whose `commit:` is the one the plan was written against, or "
    "re-run `plan`. `--source` says where to read that repository; it does "
    "not stand in for the plan's record of it.")
LEGS_REMEDIATION = (
    "Remediation: write `legs:` in the plan file as `plan` writes it, a "
    "mapping of the three repository names, `assembly:`, `spec:` and "
    "`code:`, and the two mount paths, `spec_path:` and `code_path:`; or "
    "re-run `plan`.")
PINS_REMEDIATION = (
    "Remediation: `pins:` is the list of pins `plan` wrote, one mapping per "
    "pin of its `product:`, `repository:`, `commit:`, `tree_sha256:` and "
    "`digest_source:`, or `pins: []` for none, which a value on the key's own "
    "line replaced. Restore the block from the plan `plan` wrote, or re-run "
    "`plan` with each `--pin <openProduct>@<40 hex commit>`: `execute` writes "
    "each pin's file from what `plan` recorded, and a commit or a digest "
    "typed by hand is one nobody read.")
ALLOW_EMPTY_LEGS_REMEDIATION = (
    "Remediation: write `allow_empty_legs:` in the plan file as `plan` "
    "writes it, a list of the legs that may be seeded, "
    "`allow_empty_legs: [code]`, or `allow_empty_legs: []` for none; or "
    "re-run `plan` with `--allow-empty-leg code`, or pass that to `execute`. "
    "Each item is `spec` or `code`, the two legs `execute` extracts: text on "
    "the key's own line would be read one character per leg, and consents "
    "to nothing.")
PATHS_REMEDIATION = (
    "Remediation: `paths:` is the list of entries `plan` wrote, a `- path:` "
    "and its `leg:` for each path of the source, which a value on the key's "
    "own line replaced. Restore the block from the plan `plan` wrote, or "
    "re-run `plan` and answer its questions again.")

#: Said first in `execute`'s refusal of these findings.
PLAN_KEY_REFUSAL = (
    "Remediation: no leg repository was created and nothing was pushed: the "
    "plan was refused before the work directory was made or the source was "
    "opened. Correct each key named above in the plan file and run `check` "
    "until it prints `plan ok`, then run `execute` again.")


def _plan_list(data: dict, key: str) -> list:
    """The plan's `key` when it is a LIST, as `plan` writes `paths:` and
    `allow_empty_legs:`, and `[]` for anything else: THE ONE READ of the two,
    so that neither iterates a number or reads text one character at a time.
    What it leaves out is named by `_plan_key_findings` (#386). `pins:` is
    read by `_pin_products` and `_read_pins`, which take a list only (#273)."""
    value = data.get(key)
    return value if isinstance(value, list) else []


def _not_a(code: str, key: str, value, kind: str, why: str) -> str:
    """The finding for a `key:` that holds `value` where `plan` writes a
    `kind`, in `_follow_ups_findings`' words."""
    return (f"FINDING {code}: `{key}:` is {_read_as(value)}, not a {kind}: "
            f"{why}")


def _plan_key_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """A FINDING for each of the five keys `Plan` reads to open the source and
    name the repositories that is present and is not what `plan` writes, in
    the order `plan` writes them, and for each item of `allow_empty_legs:`
    that is not a leg; and what to print once after them (#386).

    A key that is absent or bare is not a finding here, whichever it is: it
    is read as it always was. For `source:` that is `plan-no-source`, unless
    `--source` names the repository.

    `pins:` is asked only whether it is a list, the one thing its readers
    need before anything else is read: the naming policy classifies the
    root by its products, and a `pins:` that is no list has none. The
    finding is `_read_pins`' own `plan-pin-malformed`, and each entry of a
    list, a mapping as `plan` writes it or not, is `_read_pins`' to judge
    beside the entries (#273).
    """
    data = plan.data
    said: list[tuple[list[str], str]] = []

    source, legs = data.get("source"), data.get("legs")
    said.append(([] if source is None or isinstance(source, dict) else [
        _not_a(BAD_SOURCE, "source", source, "mapping",
               "`check` and `execute` open the repository to adopt by its "
               "`local_path:` or `repository:`, and hold it to its "
               "`commit:`")], SOURCE_REMEDIATION))
    said.append(([] if legs is None or isinstance(legs, dict) else [
        _not_a(BAD_LEGS, "legs", legs, "mapping",
               "the three repository names and the two mount paths are read "
               "out of it by their keys")], LEGS_REMEDIATION))

    pins = data.get("pins")
    no_list = pins is not None and not isinstance(pins, list)
    said.append((_read_pins(plan)[1] if no_list else [], PINS_REMEDIATION))

    allowed = data.get("allow_empty_legs")
    if allowed is None:
        found = []
    elif not isinstance(allowed, list):
        found = [_not_a(BAD_ALLOW_EMPTY_LEGS, "allow_empty_legs", allowed,
                        "list", "each item of a list names one leg `execute` "
                        "may seed from the shape's template")]
    else:
        found = [f"FINDING {BAD_ALLOW_EMPTY_LEGS}: item {number} of "
                 f"`allow_empty_legs:` is {_read_as(item)}, not a leg "
                 "`execute` can seed, `spec` or `code`"
                 for number, item in enumerate(allowed, 1)
                 if item not in EXTRACTED_LEGS]
    said.append((found, ALLOW_EMPTY_LEGS_REMEDIATION))

    paths = data.get("paths")
    said.append(([] if paths is None or isinstance(paths, list) else [
        _not_a(BAD_PATHS, "paths", paths, "list",
               "each item of a list is one entry, a path of the source and "
               "the leg it goes to")], PATHS_REMEDIATION))

    return ([finding for found, _ in said for finding in found],
            [remediation for found, remediation in said if found])


def _plan_type_findings(plan: Plan) -> tuple[list[str], list[str]]:
    """What `check` reports, and `execute` refuses, before it opens anything:
    `_plan_key_findings`, and, when there is one, `_plan_field_findings`
    too, so that every key of the plan that is not what `plan` writes is
    named in one run and not the first of them (#386). `([], [])` for a plan
    whose five keys `Plan` reads are what `plan` writes; #293's and #294's
    keys are then asked in `_entry_findings`, beside everything else."""
    findings, remediation = _plan_key_findings(plan)
    if not findings:
        return [], []
    fields, field_remediation = _plan_field_findings(plan)
    return findings + fields, remediation + field_remediation


def _refuse_a_mistyped_plan(plan: Plan) -> None:
    """Refuse what `_plan_type_findings` finds, in the shape
    `_refuse_what_check_finds` refuses `check`'s other findings -- the first
    finding's code, every finding as `check` prints it, capped at
    `REFUSED_FINDINGS_SHOWN` -- but first thing, before `_work_root` makes the
    work directory or the source is opened or cloned (#386)."""
    findings, remediation = _plan_type_findings(plan)
    if not findings:
        return
    # `FINDING <code>: <detail>` is the one shape every finding is written in.
    code = findings[0].split()[1].rstrip(":")
    lines = [f"{len(findings)} finding(s) in {plan.path}, as `check` prints "
             "them:"]
    lines += [f"  {finding}" for finding in findings[:REFUSED_FINDINGS_SHOWN]]
    if len(findings) > REFUSED_FINDINGS_SHOWN:
        lines.append(f"  and {len(findings) - REFUSED_FINDINGS_SHOWN} more")
    raise Refusal(code, "\n".join(lines),
                  "\n".join([PLAN_KEY_REFUSAL, *remediation]))


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


# ---------------------------------------------------------------------------
# A symlink in the source whose target is empty (#303)
# ---------------------------------------------------------------------------
#
# A source tree can hold a symlink whose target is EMPTY: a `120000` entry
# whose blob is the empty blob. A checkout with `core.symlinks=false` writes
# each link as a plain file holding its target, and emptying that file and
# committing records one (git 2.43). `plan` and `check` never read a link's
# target, so `check` said `plan ok`, and what `execute` did next turned on how
# git checks a symlink out where it ran:
#
#   * Linux refuses a symlink to nothing (`symlink("")` fails with ENOENT),
#     so where git makes symlinks there, its default, `execute`'s first
#     clone of the source exited 128, `unable to checkout working tree`,
#     after both leg repositories were created, WHATEVER THE PLAN ANSWERED
#     for the link, `drop` included: `_extract_leg` and `_commit_the_split`
#     each clone the whole source and only then take out what the plan
#     sends elsewhere. Measured with the link in `docs/` (sent
#     to the spec leg) and at the top level answered `root` and `drop`, and
#     with both legs seeded, where the assembly's clone is the only one.
#   * where `core.symlinks` is false, every clone held the link as an empty
#     file and the run said `adoption verified`. The leg or the root the plan
#     kept it in then could not be cloned on Linux where symlinks are made,
#     nor could the assembly recursively; the root's own `validate` workflow
#     runs on `ubuntu-latest`. Only `drop` gave an assembly that clones.
#
# So it is a fact of the SOURCE, readable from its tree before anything
# exists, and no answer in the plan fixes it everywhere: `check` reports each
# such link whatever the plan answers for it, and whatever `core.symlinks`
# says where it runs, and `execute` refuses it before any leg exists (#168),
# because a check that answered differently on another disk would pass a
# plan the next machine cannot adopt. `drop` is not offered as the fix: it
# is one only where symlinks are not made. The remediation is in the source.
#
# No target is read. `Source.tree()` lists each entry with `ls-tree -l`, and
# the size of a symlink's blob is the length of its target, so an empty
# target is a `120000` row of size 0, in a SHA-1 or a SHA-256 repository
# alike. Only the commit being adopted is read: an empty symlink in the
# history alone is never checked out by a clone, and `git filter-repo`
# rewrites the history without a checkout.

#: `check`'s finding for a symlink of the source's whose target is empty.
EMPTY_SYMLINK = "plan-empty-symlink"
#: How many of them `check` names one by one; past it, a count, as
#: `plan-uncovered` counts the paths past its twentieth.
EMPTY_SYMLINKS_NAMED = 20
#: What a plan whose source holds one is told to do. Said by `check`, once
#: after its findings, and by `execute`'s refusal, after its own remediation,
#: which is about correcting the plan: this is about the source.
EMPTY_SYMLINK_REMEDIATION = (
    "Remediation: a symlink's target is a fact of the source, and no answer "
    "in the plan changes it, `drop` included: `execute` clones the whole "
    "source before it takes out anything the plan sends elsewhere, and where "
    "git makes symlinks that clone stops at a symlink to nothing. Give each "
    "such symlink a target in the source, or remove it there, commit, and "
    "re-run `plan`: a plan is written against one commit of the source, and "
    "`check` calls it `plan-stale` once the source has moved.")


def empty_symlinks(tree: list) -> list[str]:
    """The paths of `tree` (`Source.tree()`'s rows) that are symlinks with
    an empty target: mode 120000, and a blob of size 0."""
    return [path for path, mode, _, size in tree
            if mode == SYMLINK_MODE and not size]


def _empty_symlink_sentence(path: str) -> str:
    """What `check` says of the empty symlink at `path`, and `plan` notes."""
    return (f"{_spelled(path)} is a symlink whose target is empty at the "
            "source commit, and Linux cannot make a symlink to nothing. "
            "There, where git makes symlinks by default, each clone "
            "`execute` makes of the source stops at it after both leg "
            "repositories were created, whatever the plan answers for it; "
            "and where `core.symlinks` is false the clone holds it as an "
            "empty file, and the leg or root the plan keeps it in then "
            "cannot be cloned on Linux, where the root's own `validate` "
            "workflow runs")


def _empty_symlink_findings(tree: list) -> tuple[list[str], list[str]]:
    """A FINDING for each symlink of the source whose target is empty
    (#303), as `check` prints it, the first EMPTY_SYMLINKS_NAMED one by one;
    and what to print ONCE after every finding, as `_unsafe_path_findings`
    does. Read from the tree alone: no answer of the plan's changes it."""
    empty = empty_symlinks(tree)
    found = [f"FINDING {EMPTY_SYMLINK}: {_empty_symlink_sentence(path)}."
             for path in empty[:EMPTY_SYMLINKS_NAMED]]
    if len(empty) > EMPTY_SYMLINKS_NAMED:
        found.append(f"FINDING {EMPTY_SYMLINK}: … and "
                     f"{len(empty) - EMPTY_SYMLINKS_NAMED} more symlinks "
                     "whose target is empty")
    return found, [EMPTY_SYMLINK_REMEDIATION] if found else []


def _empty_symlink_notes(tree: list) -> list[str]:
    """What `plan` says of each symlink of the source whose target is empty:
    a NOTE in `check`'s words, and a line saying what follows. `plan` still
    writes the plan, but no answer in it will pass `check`."""
    notes: list[str] = []
    for path in empty_symlinks(tree):
        notes += [f"\nNOTE {_empty_symlink_sentence(path)}.",
                  f"     `check` reports this as `{EMPTY_SYMLINK}` and "
                  "`execute` refuses it, whatever the plan answers: give it "
                  "a target in the source, or remove it there, commit, and "
                  "re-run `plan`."]
    return notes


def _source_path_findings(plan: Plan, tree: list
                          ) -> tuple[list[str], list[str]]:
    """The findings `_entry_findings` lists first, about the source's own
    paths, and what to print once after every finding for them: each entry
    path `execute` will not extract (#196), then each symlink of the source
    whose target is empty (#303)."""
    unsafe, unsafe_remediation = _unsafe_path_findings(plan)
    empty, empty_remediation = _empty_symlink_findings(tree)
    return unsafe + empty, unsafe_remediation + empty_remediation


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
    mount paths and what the root keeps where the shape writes, the pins,
    then each pin's digest the clone `plan` read it from recomputes
    otherwise (#449), then each value `execute` would write into the
    project's YAML for its loader to read back as something else (#181),
    then the source's own submodules,
    then each symlink the plan keeps in the root that a shape file cannot
    be written through (#178, #183), then each value `execute` writes into
    a file that no file can hold (#255), then what the project's own
    `validate-manifest.py` would refuse of the values `execute` writes into
    its manifest (#261), then a tracking branch that is no branch of the
    source (#479), then each relative url of a kept submodule that names
    another repository from its leg (#190), and last each plan value
    `execute` reads late and `_plan_field_findings` asks about (#293, #294).

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
    (#190). And two things about a symlink AT a shape path are asked of the
    disk by each command when it runs (#183): whether anything is at the
    place outside the assembly it leads to, a climb above the root from its
    own work directory; and whether `git` there checks it out as a symlink at
    all, or as a plain file the shape's copy goes beside. The second is asked
    too of a symlink ABOVE a shape path that a finding names, which then
    says the clone holds it as a file (#531).

    `_leg_findings` is handed the TREE, because the paths the plan keeps in
    the root are read out of it (#172, #191): without it a mount path at, or
    beyond, a kept source path checks ok and dies at `git submodule add`
    after both legs are pushed.

    THE PATHS COME FIRST (#196), so that `_refuse_what_check_finds` wears
    `plan-unsafe-path` for a plan that has one: a path that is a `git` option
    is refused as that, and never as the uncovered file it also leaves.

    THEN THE SOURCE'S EMPTY SYMLINKS (#303), which no answer in the plan
    fixes: the fix is a commit in the source, and the fresh `plan` after it
    takes back every answer given before, so they are listed before the
    findings about those answers (`_source_path_findings`). Their
    remediation is said once after the findings, with the others.

    A VALUE NO FILE CAN HOLD IS SAID BEFORE THE VALIDATOR'S WORD ON IT (#255
    before #261). A lone surrogate, a line break or a bidi control in
    `visibility:` or `elected_on:` is both, and `_refuse_what_check_finds`
    then wears `plan-unwritable-value`, as `plan` refuses such a flag as
    `adopt-unwritable-value` before it asks the validator anything. What the
    validator says is said of the manifest the value would be written into,
    which is the value's consequence; the byte, the break or the control is
    what the person retypes. Both are listed, and both refuse before any leg
    exists. The relative urls of #190 still come after both, and last the
    plan values `execute` reads late (#293, #294): an `elected_on:` that
    `election_date` refuses is said there in the plan key's own words, and
    `_manifest_values` does not ask the validator about it as well.

    A VALUE THE VALIDATOR REFUSES IS THE VALIDATOR'S ALONE (rv181f's G1,
    G2). The validator is asked about every value (`_manifest_findings`),
    and #181's `plan-manifest-misread` names a value only where the loader
    misreads it, the validator makes no finding about what the loader
    reads, and `execute` gets to write it in every mode
    (`_execute_gets_to_write`, `_misread_findings`). A manifest the
    validator's own reader refuses, or a finding of its about no one value,
    leaves every value to it. So the two never both name one value, and every
    value #181 names is one `execute` writes as it stands, with the run
    still ending `adoption verified`, as its remediation says.
    Where `_manifest_values` asks the validator about no manifest at all,
    as for an `elected_on:` `election_date` refuses, #181 names no value
    either (`_validator_judged`): the date is one finding, `_plan_field_findings`'s
    (#293, #294).
    In the same way a tracking branch that is no branch of the source is
    `plan-tracking-branch-missing` alone (#479), and one only the source's
    remote `origin` has, which `execute --local-remote-dir` refuses, is
    named by neither (`_a_branch_execute_writes`); and a pin is named only
    where the plan's `pins:` has no finding of #273's (`_plan_fields`).
    """
    tree = source.tree()
    unsafe, unsafe_remediation = _source_path_findings(plan, tree)
    findings = (unsafe
                + _coverage_findings([str(e.get("path"))
                                      for e in plan.entries],
                                     [path for path, _, _, _ in tree])
                + _leg_findings(plan, tree))
    # Beside the pins' other findings, which `_leg_findings` lists last: a
    # digest the clone `plan` read it from recomputes otherwise (#449).
    digest_findings, pin_notes = _pin_digest_findings(plan)
    findings += digest_findings
    (split, split_remediation), (moved, moved_remediation), notes = \
        _submodule_findings(plan, source, tree, local_remote_dir)
    unwritable_findings, unwritable_remediation = _value_findings(plan)
    value_findings, value_remediation = _manifest_findings(plan)
    field_findings, field_remediation = _plan_field_findings(plan)
    tracking_findings, tracking_remediation = _tracking_branch_findings(
        plan, source)
    # Asked after the validator, whose judgement it follows, and of the
    # tracking branch only where `execute` pushes the legs to it in every
    # mode (`_a_branch_execute_writes`, #479), so that a branch the source
    # lacks is `plan-tracking-branch-missing` alone; listed where it always
    # was, after the mount paths. A plan with no `tracking_branch:` gets
    # `main`, which is never misread.
    tracking = plan.get(TRACKING_KEY)
    misread = _misread_findings(
        plan, () if tracking is None
        or _a_branch_execute_writes(source, TRACKING_KEY, str(tracking))
        else (MANIFEST_FIELDS[TRACKING_KEY],))
    return (findings + misread + split
            + _root_symlink_findings(plan, source, tree)
            + unwritable_findings + value_findings + tracking_findings
            + moved + field_findings,
            unsafe_remediation
            + ([MANIFEST_MISREAD_REMEDIATION] if misread else [])
            + split_remediation + unwritable_remediation + value_remediation
            + tracking_remediation + moved_remediation + field_remediation,
            pin_notes + notes)


# ---------------------------------------------------------------------------
# The split branch is a NEW branch where the split is pushed (#320)
# ---------------------------------------------------------------------------
#
# `_commit_the_split` pushes the one split commit to `refs/heads/<adopt_branch>`
# of the repository the split goes to: the source itself under
# `--local-remote-dir` (`_remote_urls`), and otherwise the assembly
# repository on GitHub, which an in-place adoption keeps as the source. And
# `_extract_leg` clones the source, checks that branch out in the clone and
# runs `git filter-repo`, which makes each of the clone's
# `refs/remotes/origin/*` a branch. Two kinds of branch stop it, and `check`
# passed both as `plan ok`:
#
# - THE SPLIT BRANCH ITSELF, where the split is pushed, at a commit the push
#   cannot fast-forward: what an earlier run leaves there, verified or
#   failed after its push. `execute` refuses it as `adopt-branch-exists`
#   before any leg exists (`_refuse_a_split_branch_left_behind`, #188 N1).
#   One at the source commit or behind it is pushed over, and verifies.
# - A BRANCH IN GIT'S WAY OF IT, whose name is a directory of the split
#   branch's, or lies under it: git cannot hold the two side by side. In the
#   source it stops the extraction of either run, at `git filter-repo`;
#   where the split is pushed, it stops that push. Nothing refused it.
#   Measured on main at ec4a7a0 with git 2.43 and `git filter-repo` 2.47.0:
#   a source branch `adopt` or `adopt/three-repo-shape/old` made both legs,
#   two bare repositories or two `gh repo create`s, and the run exited 2 at
#   the filter; a plan seeding both legs from a source holding `adopt`, and a
#   GitHub assembly repository holding `adopt`, made both legs and exited 2
#   at the push of the split.
#
# So `check` reports both, and `execute` refuses the second, before any leg
# exists, as `plan-split-branch-taken`.
#
# ONE CODE FOR ONE SITUATION. `check`'s finding for the split branch itself
# is `adopt-branch-exists`: the code `execute` refuses that branch under, and
# the one `_left_by_the_split` tells a run that pushed its split the re-run
# will meet. It is asked by that refusal's own rule (`_in_the_history_of`),
# so a branch the push fast-forwards is no finding, and the two commands
# cannot disagree about it, as #168 has them agree about every other finding.
# A branch in the way is `plan-split-branch-taken` in both.
#
# WHERE `check` ASKS. It does not know whether `--local-remote-dir` will be
# passed, so it asks the two places it can see without the network, and each
# finding says which run it is about: the source's own branches, and, where
# the source's `origin` is the assembly repository, what that remote held
# when the source last fetched it -- for an `org/repo` source, which
# `Source.open` clones, when it was cloned. A source branch in the way is
# about both runs, said as the extraction's failure, unless the plan seeds
# both legs and extracts nothing. The split branch's own name in the source
# is about the run that pushes there alone: the extraction's `checkout -B`
# shadows it in its clone.
#
# WHERE `execute` ASKS (`_refuse_a_branch_in_the_split_branchs_way`). Right
# after `_refuse_a_split_branch_left_behind`, before `_confirm`: every
# refusal of what an earlier run left keeps its place and its words, the
# work directory first and then the split branch itself, and a leg
# repository still there under `--local-remote-dir`, which
# `_create_leg_remotes` refuses as `leg-remote-exists`, keeps its precedence
# over this refusal as over that one. It lists the repository it pushes to
# with `git ls-remote --heads`, as the push will meet it, and, without
# `--local-remote-dir`, the source's own branches for the extraction,
# reading no network for them.
#
# THE HISTORY SCAN IS NOT CHANGED (#226). `_exported_gitlink` reads
# `--branches`, so a split branch the source keeps is in it, and
# `_extract_leg`'s `git checkout -B` shadows that branch in the extraction's
# clone: the scan can name a commit of it which the extraction never
# exports. `check` names the branch first, before the entries' findings, and
# its remediation says that such a finding stands until the branch is
# deleted. `execute` refuses the scan's finding, in
# `_refuse_what_check_finds`, before `_refuse_a_split_branch_left_behind`
# asks for the branch. With the branch deleted neither holds it, and under
# another `adopt_branch:` `git filter-repo` exports it, and fails on the tip
# `.gitmodules` the scan's finding names (measured with git 2.43 and `git
# filter-repo` 2.47.0).

#: `check`'s finding, and the code of `execute`'s refusal, for a branch in
#: git's way of the split branch where the split is pushed or extracted.
SPLIT_BRANCH_TAKEN = "plan-split-branch-taken"
#: `check`'s finding for the split branch itself where the split is pushed,
#: at a commit the push cannot fast-forward: the code
#: `_refuse_a_split_branch_left_behind` refuses that branch under.
SPLIT_BRANCH_EXISTS = "adopt-branch-exists"
#: How a finding names the run that pushes to each place `check` asks.
LOCAL_RUN = "`execute --local-remote-dir`"
GITHUB_RUN = "`execute` without `--local-remote-dir`"
#: How a finding names the runs that extract a leg from the source: both.
EITHER_RUN = "`execute`, with `--local-remote-dir` or without it,"

#: What `check` says once after its findings when one of them is about the
#: split branch.
SPLIT_BRANCH_REMEDIATION = (
    "Remediation: `execute` pushes its one split commit to the plan's "
    "`adopt_branch:` in the repository the split goes to: the source itself "
    "under `--local-remote-dir`, and otherwise the assembly repository on "
    "GitHub. It moves a branch already there only as a fast-forward, and it "
    "extracts each leg from a clone of the source with that branch checked "
    "out, so a branch git cannot hold beside it, there or in the source, "
    "stops either run. A run leaves its split branch where it pushed it, "
    "verified or not, so an earlier run's split is what "
    "`adopt-branch-exists` names most often: if that run verified and its "
    "pull request is the adoption you want, review that instead. Otherwise "
    "delete each branch a finding names, where it names it, once neither it "
    "nor a pull request from it is wanted, or set `adopt_branch:` to a name "
    "git can create there, and run `check` again. A branch named as the "
    "source's `origin` last fetched it leaves `check`'s findings once `git "
    "fetch --prune origin` in the source finds it gone there. A branch the "
    "source itself holds is also in the history `check` reads for the "
    "source's submodules, and `git filter-repo` exports it once the plan "
    "names another branch, so a finding that names one of its commits "
    "stands until that branch is deleted.")

#: `execute`'s remediation for `plan-split-branch-taken`.
SPLIT_BRANCH_TAKEN_REMEDIATION = (
    "Remediation: no leg repository was created and nothing was pushed. Git "
    "holds no branch whose name is a directory of another's, or lies under "
    "it, so the plan's split branch cannot be made beside a branch named "
    "above, where it is named. Delete that branch there, once neither it "
    "nor a pull request from it is wanted, or set `adopt_branch:` in the "
    "plan to a name git can create there, then run `check` and `execute` "
    "again.")


def _listed_branches(raw: bytes, prefix: str) -> dict[str, str]:
    """`{branch: commit}` from `<oid> TAB <ref>` lines, as `git ls-remote`
    and `git for-each-ref` print them, for each ref under `prefix`. A name
    that is not UTF-8 keeps each byte as a surrogate, as `Source.tree`
    keeps a path's (`_git_path`)."""
    out: dict[str, str] = {}
    for line in raw.splitlines():
        oid, _, ref = line.partition(b"\t")
        name = _git_path(ref)
        if name.startswith(prefix) and name != prefix + "HEAD":
            out[name[len(prefix):]] = oid.decode().strip().lower()
    return out


def _branches_at(url: str, cwd: Path) -> dict[str, str]:
    """Every branch of the repository at `url`, as a push to it meets them:
    `git ls-remote --heads`. One that cannot be listed fails as `run` fails
    a command, `CommandFailed`, and in `execute` before any leg exists:
    `_refuse_a_split_branch_left_behind` has just listed the same
    repository, and a failure there is the same."""
    args = ["git", *FILE_PROTOCOL, "ls-remote", "--heads", "--", url]
    listed = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    if listed.returncode:
        raise CommandFailed(args, cwd, listed.returncode,
                            listed.stderr.decode("utf-8", "replace"))
    return _listed_branches(listed.stdout, "refs/heads/")


def _in_the_way(branches: dict[str, str], branch: str) -> list[tuple]:
    """`(name, commit)` of each of `branches` that stops `refs/heads/<branch>`
    being created as a new branch: `branch` itself, first, then each whose
    name is a directory of it or lies under it, which git cannot hold beside
    it."""
    return sorted(((name, commit) for name, commit in branches.items()
                   if name == branch or name.startswith(branch + "/")
                   or branch.startswith(name + "/")),
                  key=lambda found: (found[0] != branch, found[0]))


def _left_behind(where: str, run: str, branch: str, commit: str,
                 source_commit: str) -> str:
    """One `adopt-branch-exists` finding: `where` already has the split
    branch `branch`, at `commit`, which is neither `source_commit` nor a
    commit behind it, and `run` pushes the split there. Said as
    `_refuse_a_split_branch_left_behind` says it."""
    split = _spelled(branch)
    return (f"{where} already has {split}, the branch {run} pushes its "
            f"split commit to, at {commit[:12]}: neither the source commit "
            f"{source_commit[:12]} nor a commit behind it. The split commit "
            "is made on top of the source commit, and git moves a branch to "
            "it without force only from that commit or one behind it, so "
            "`execute` refuses that run before it creates a leg, as "
            f"`{SPLIT_BRANCH_EXISTS}`. Delete {split} there, or set "
            "`adopt_branch:` in the plan to a name no branch has there.")


def _taken(where: str, run: str, branch: str, name: str,
           commit: str) -> str:
    """One `plan-split-branch-taken` finding about the push: `where` holds
    the branch `name`, at `commit`, which git cannot hold beside the split
    branch `branch`, and `run` pushes the split there."""
    split, held = _spelled(branch), _spelled(name)
    # git's own words, each name spelled as `_spelled` spells it, so a
    # backtick a branch name may hold cannot end the quotation.
    return (f"{where} holds the branch {held}, at {commit[:12]}. {run} "
            f"pushes its split commit to {split} there, after both leg "
            "repositories were created and pushed, and git cannot create "
            f"{split} beside {held}: `'refs/heads/{held[1:-1]}' exists; "
            f"cannot create 'refs/heads/{split[1:-1]}'`. Delete {held} "
            "there, or set `adopt_branch:` in the plan to a branch git can "
            "create there.")


def _in_the_extraction(where: str, branch: str, name: str,
                       commit: str) -> str:
    """One `plan-split-branch-taken` finding: the source, `where`, holds the
    branch `name` at `commit`, which git cannot hold beside the split branch
    `branch`, and `_extract_leg`'s `git filter-repo` makes each branch of
    the source a branch of a clone where `branch` is checked out. Either
    run extracts, so the finding is about both."""
    split, held = _spelled(branch), _spelled(name)
    return (f"{where} holds the branch {held}, at {commit[:12]}. "
            f"{EITHER_RUN} extracts a leg from a clone of the source with "
            f"the plan's split branch {split} checked out in it, after both "
            "leg repositories were created, and `git filter-repo` cannot "
            f"create {held} beside {split} there: git holds no branch whose "
            "name is a directory of another's, or lies under it. Delete "
            f"{held} there, or set `adopt_branch:` in the plan to a branch "
            "git can create there.")


def _split_branch_findings(branch: str | None, places: list,
                           source: Source | None = None) -> list[str]:
    """One FINDING per branch that stops the split branch `branch` in each
    of `places`, `(where, pushed_by, extracted, branches)`.

    `pushed_by` is the run that pushes the split there, or None, and
    `extracted` is whether `_extract_leg` clones it: the source, when a leg
    is extracted. A branch in git's way is `plan-split-branch-taken`: about
    the extraction, for either run, where it is extracted
    (`_in_the_extraction`), and otherwise about the push (`_taken`).

    The split branch's own name is asked only where the split is pushed,
    because the extraction's `checkout -B` shadows it, and only by `check`,
    which hands its `source` in: `adopt-branch-exists`, by
    `_refuse_a_split_branch_left_behind`'s rule, so a branch the push
    fast-forwards is none. `execute` leaves that branch to that function.
    `branch` None is a split branch `execute` refuses as `unsafe-value`,
    and nothing is asked about it here."""
    found = []
    for where, pushed_by, extracted, branches in (places if branch else []):
        for name, commit in _in_the_way(branches, branch):
            if name != branch and extracted:
                found.append(f"FINDING {SPLIT_BRANCH_TAKEN}: "
                             + _in_the_extraction(where, branch, name,
                                                  commit))
            elif name != branch and pushed_by:
                found.append(f"FINDING {SPLIT_BRANCH_TAKEN}: "
                             + _taken(where, pushed_by, branch, name, commit))
            elif (name == branch and pushed_by and source is not None
                  and not _in_the_history_of(source, commit)):
                found.append(f"FINDING {SPLIT_BRANCH_EXISTS}: "
                             + _left_behind(where, pushed_by, branch, commit,
                                            source.commit))
    return found


def _extracts_a_leg(assigned: dict) -> bool:
    """Whether `_build_the_legs` runs `_extract_leg`: not when the plan
    seeds both legs (`seeded_legs`, one definition)."""
    return len(seeded_legs(assigned)) < len(EXTRACTED_LEGS)


def _assembly_repository(plan: Plan) -> str | None:
    """`<org>/<assembly>`, the repository a run without `--local-remote-dir`
    pushes the split to (`_repository_urls`), as the plan names it; None
    where it names no organisation or no assembly root."""
    legs = plan.legs if isinstance(plan.legs, dict) else {}
    org, name = plan.get("org"), legs.get("assembly")
    return f"{org}/{name}" if org and name else None


def _branches_in(path: Path, refs: str) -> dict[str, str]:
    """`_listed_branches` of the refs under `refs` in the repository at
    `path`, read from it with `git for-each-ref`: no network."""
    return _listed_branches(
        git_out(["for-each-ref", "--format=%(objectname)%09%(refname)",
                 refs], cwd=path, binary=True), refs)


def _places_check_asks(plan: Plan, source: Source, extracting: bool) -> list:
    """The places `check` asks for the split branch, `(where, pushed_by,
    extracted, branches)`: the source, which a run with `--local-remote-dir`
    pushes to and either run extracts from while `extracting`, and, where
    the source's `origin` is the assembly repository, that repository's
    branches as the source last fetched them, which a run without it pushes
    to. `check` reads no network for either."""
    places = [(f"the source {_shown(str(source.path))}", LOCAL_RUN,
               extracting, _branches_at(str(source.path), source.path))]
    assembly = _assembly_repository(plan)
    if assembly and (source.repository or "").lower() == assembly.lower():
        places.append((f"`{assembly}` on GitHub, as the source's `origin` "
                       "last fetched it,", GITHUB_RUN, False,
                       _branches_in(source.path, "refs/remotes/origin/")))
    return places


def _check_split_branch(plan: Plan, source: Source
                        ) -> tuple[list[str], list[str]]:
    """`_split_branch_findings` as `check` asks it, the split branch's own
    name included, and what to print ONCE after every finding, as
    `_submodule_findings` returns it. A split branch that is not a value
    `execute` puts on a command line is not asked about: it is `execute`'s
    refusal `unsafe-value`, before any leg exists."""
    try:
        branch = checked_value("adopt_branch",
                               plan.get("adopt_branch", ADOPT_BRANCH))
    except Refusal:
        return [], []
    extracting = _extracts_a_leg(assigned_paths(plan.entries))
    found = _split_branch_findings(
        branch, _places_check_asks(plan, source, extracting), source)
    return found, [SPLIT_BRANCH_REMEDIATION] if found else []


def _refuse_a_branch_in_the_split_branchs_way(
        plan: Plan, source: Source, repositories: dict, urls: dict,
        branch: str, local: bool, extracting: bool) -> None:
    """Refuse a branch git cannot hold beside the split branch, where this
    run pushes the split or, while `extracting`, in the source it extracts
    the legs from, BEFORE a leg repository exists (#320): `check`'s finding
    `plan-split-branch-taken`, which nothing refused.

    `cmd_execute` runs it right after `_refuse_a_split_branch_left_behind`,
    which asks for the split branch's own name, and it keeps that
    function's precedence: a leg repository still there under
    `--local-remote-dir` is `leg-remote-exists`'s to refuse, and this asks
    nothing then.

    Under `--local-remote-dir` the split is pushed to the source, which is
    also what the extraction clones: one listing, `git ls-remote --heads`,
    as the push will meet it, and each finding is `check`'s, word for word.
    Without it, the source's own branches are asked for the extraction,
    reading no network, and each finding is `check`'s, word for word; then
    the assembly repository on GitHub, as the push will meet it, which
    `check` reads as the source's `origin` last fetched it, if at all.
    """
    if local and any(Path(urls[role]).exists() for role in EXTRACTED_LEGS):
        return
    the_source = f"the source {_shown(str(source.path))}"
    if local:
        places = [(the_source, LOCAL_RUN, extracting,
                   _branches_at(urls["assembly"], source.path))]
    else:
        places = [(the_source, None, True,
                   _branches_in(source.path, "refs/heads/"))
                  ] if extracting else []
        places.append((f"`{repositories['assembly']}` on GitHub", GITHUB_RUN,
                       False, _branches_at(urls["assembly"], source.path)))
    found = _split_branch_findings(branch, places)
    if found:
        raise Refusal(SPLIT_BRANCH_TAKEN, "\n".join(
            [f"{len(found)} finding(s) in {plan.path}:",
             *(f"  {finding}" for finding in found)]),
            SPLIT_BRANCH_TAKEN_REMEDIATION)


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
    # A leg path that is not text is a FINDING of its own, and its Python
    # spelling (`None/`, `True/`) names no directory a leg would be mounted at.
    mounts = [_plan_leg_path(plan, role) for role in EXTRACTED_LEGS]
    mounted = (f" at {_shown(mounts[0])}/ and {_shown(mounts[1])}/"
               if all(isinstance(mount, str) for mount in mounts) else "")
    print(f"  ONE split commit on branch "
          f"{_shown(str(plan.get('adopt_branch', ADOPT_BRANCH)))} "
          f"of {names['assembly']}: `git rm -r` those paths, mount the "
          f"legs{mounted}")
    print(f"  {len(stays)} path(s) stay in the assembly root; "
          f"{len(drops)} dropped")
    # Each pin `execute` writes, as the plan records it (#273): a pin it
    # cannot write is a finding, printed after this. Whether its digest was
    # recomputed is said once per pin with the NOTEs `_entry_findings`
    # returns: it recomputes, or it was not rechecked here, where the clone
    # `plan` read it from is gone or partial or `gh api` read it, because
    # `check` and `execute` read no network for a pin (#273's review, S3;
    # #449).
    recorded = _recorded_pins(plan)
    for product, values in recorded.items():
        print(f"  write {neutral_pin_path(product)}: "
              f"{values['PIN_REPOSITORY']} @ {values['PIN_COMMIT'][:12]} tree "
              f"{values['PIN_TREE_SHA256'][:12]}… "
              f"({_shown(values['PIN_DIGEST_SOURCE'])})")
    print("  the source is never deleted, never renamed, never force-pushed")
    print(_topics_line(topic, local))
    for item in _plan_follow_ups(plan):
        print(f"  follow-up: {_shown(item)}")


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
# runs, and `execute` asks before any leg exists. Whether `git` checks a
# symlink out as a symlink at all is asked the same way. Where it does not
# (`core.symlinks` false, Git for Windows' default), a link AT a path the
# shape writes is a plain file in the clone, which `place` finds there and
# writes the copy beside, so nothing about where that link leads is refused
# (B-OFF of #183's re-verify); a link ABOVE one is `execute`'s
# `adopt-symlinks-off`, since nothing can be written beneath a file. A link
# ABOVE one that `check` reports anyway, for where it would lead on a disk
# that holds symlinks, is named there as that file too, as
# `adopt-symlinks-off` names it, and not by where it leads (L1-J3 of #183's
# re-verify, #531): no target makes the file a directory. A target is
# absolute as this machine's `open()` reads it: `C:/x`, a drive letter's
# path, is a place on this disk only on Windows. On Linux and macOS it is a
# relative path, into a directory named `C:`, and it is followed as one, as
# `open()` and the materializer follow it there.
#
# EACH DECLARED PIN'S FILE IS ONE OF THOSE PATHS (#273). `execute` hands the
# materializer `_recorded_pins`, and `place` writes each
# `contracts/<product>-pin.yaml` after the copies and before the shape's own
# pin, so the walk follows `assembly_root_paths` of the same products, read
# as `_leg_collision_findings` reads them (`_declared_pins`). Walked without
# them, a link that only a pin's file runs through passed `check`, and
# `execute` stopped at it after both legs; and a link to a pin's file was
# taken to lead nowhere, though `place` meets the pin there. A symlink AT a
# pin's file is #273's `plan-root-holds-pin`, said once there, and so is one
# AT the shape's own pin, wherever it leads (#524): where it leads to
# something, `place` writes the shape's pin beside it and the root's
# `contracts/shape-pin.yaml` is the source's link, which no walk refuses.

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
#: What the assembly's clone holds in its own `.git` when the shape is
#: written, on git's default configuration (F3 and 2b of #183's re-verify):
#: `.git` and the files git makes in every clone it checks out, and, in
#: CLONE_GIT_TREES, the directories that hold the source's objects and refs,
#: their logs, and the stores of the two legs `execute` has mounted by then,
#: each counted with whatever is under it, which the source and the plan
#: decide and this check does not read. A symlink AT a path the shape writes
#: that leads to one of them, or to anything under one of CLONE_GIT_TREES, is
#: taken to find something there, so `place` writes the shape's copy beside
#: it and keeps the link, as on `main`. Of a name under those directories
#: that is NOT there, that is false, and the link is not refused here: the
#: shape's file is written through it into `.git`, or the run stops there
#: after both legs exist, as on `main` (J1 of #183's re-verify). Nothing
#: else is in that `.git` before the split's commit: a template makes
#: `description`, `hooks` and `info`, and `execute` clones with none (#243).
#: A link that leads the shape to anything else there writes its file INTO
#: `.git`, where no commit holds it. (On a git configured otherwise -- the
#: reftable backend, `core.logAllRefUpdates=false` -- some of these are
#: missing, and a link to one is not refused here: the shape is written
#: through it, or stops there after both legs exist.)
CLONE_GIT = frozenset({".git", ".git/HEAD", ".git/config", ".git/index",
                       ".git/packed-refs"})
#: `CLONE_GIT` as a disk that ignores case finds it.
CLONE_GIT_FOLDED = frozenset(path.casefold() for path in CLONE_GIT)
#: The directories of the clone's `.git` counted with all they hold.
CLONE_GIT_TREES = (".git/objects", ".git/refs", ".git/logs", ".git/modules")


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
    A symlink AT a path the shape writes also finds what the clone's own
    `.git` holds by then (`CLONE_GIT`, and `CLONE_GIT_TREES` counted whole),
    and nothing else in `.git`. Where `git` checks a symlink out as a plain
    file, a symlink AT a path the shape writes is that file, wherever it
    leads: `probe` asks this command's work directory, and only for a link
    a walk cannot follow (`_a_file_here`). The walk itself still follows a
    symlink ABOVE a path the shape writes: `_root_symlink_findings` asks the
    same `probe` of one it reports (`_a_file_above`, #531).
    `walks` adds what the shape itself writes, path by path, as `place` does,
    so `CLAUDE.md -> AGENTS.md` finds the `AGENTS.md` the shape wrote first.
    The paths are those of the pins the plan declares too (`pins`), each
    pin's file written before the shape's own pin (#273).

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
                 probe: _SymlinkProbe, fold: bool = False) -> None:
        self.source = source
        self.probe = probe
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
        # The products whose pin files `execute` writes, each once, in the
        # plan's order: `_recorded_pins` hands the materializer a mapping of
        # the same pins. Only the entries `_read_pins` takes as pins, so a
        # `pins:` that is no list, or an entry that is no pin, adds no path:
        # those are `check`'s findings, and `execute` writes no file for them.
        self.pins = list(dict.fromkeys(_declared_pins(plan)))
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
        """Each path the shape writes, each declared pin's file among them,
        followed, in the order `place` writes them: the path itself, and its
        copy under the collision directory where the path is already
        taken."""
        if self._walks is None:
            self._walks = []
            for path in assembly_root_paths(self.pins):
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
        target, the symlinks whose destination it completes. A symlink AT
        `path` that cannot be followed may be a plain file in the clone
        (`_a_file_here`): then `path` is taken, and nothing stops it."""
        walk = _Walk(path)
        queue = [(part, "", False, ()) for part in path.split("/")]
        done: list[str] = []
        while queue and walk.problem is None:
            done, queue = self._next(walk, done, queue.pop(0), queue)
        if not walk.outside:
            walk.landed = "/".join(done)
            walk.taken = self._has(walk.landed)
        if walk.problem is not None and self._a_file_here(walk):
            walk.problem, walk.empty, walk.outside = None, "", False
            walk.landed, walk.taken = walk.links[0][0], True
        return walk

    def _a_file_here(self, walk: _Walk) -> bool:
        """Whether the clone holds the symlink AT `walk`'s own path as a
        plain file. Where `git` checks a symlink out as one (`core.symlinks`
        false, Git for Windows' default), `place` finds that file there and
        writes the shape's copy beside it, whatever the link leads to, as on
        `main` (B-OFF of #183's re-verify). A link the walk meets first
        ABOVE its path is `execute`'s `adopt-symlinks-off`, or, where `check`
        reports it, `_a_file_above`'s. The disk is asked only for a link the
        walk could not follow, so a plan with none makes no probe."""
        return (bool(walk.links)
                and walk.links[0][0].casefold() == walk.path.casefold()
                and not self.probe.symlinks())

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
        """Whether `place` is taken to find something at `path`: in this
        tree, as `Path.exists()` would say, or in the clone's own `.git`,
        one of `CLONE_GIT` or anything under one of `CLONE_GIT_TREES`, which
        is not read, so a name there that is missing counts too (J1). Only
        this asks the clone's `.git`; `_is_dir` does not, so a link ABOVE a
        path the shape writes still cannot lead it into `.git` (D9)."""
        if self._real(path) is not None or any(
                self._under(path, top) for top in CLONE_GIT_TREES):
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
    copy written THROUGH it, earlier in `_entry_findings`' one list; and one
    AT `project.yaml`, which #305's `plan-root-blocks-manifest` names. Asked
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


def _links_at_a_pin(plan: Plan, tree: list) -> set[str]:
    """Each symlink the plan keeps AT a file a pin is written to, a declared
    pin's `contracts/<product>-pin.yaml` or the shape's own
    `contracts/shape-pin.yaml`, that #273's `plan-root-holds-pin` names
    (`_kept_pin_findings`, #524): the walks follow each pin's file too, and
    the link is not said again by them. Asked as `_kept_pin_findings` asks
    it, in `_leg_findings`, of a plan whose `legs` it can read: of each pin
    file, on a disk that keeps case and, where that finds nothing there, on
    one that ignores it."""
    if not isinstance(plan.legs, dict):
        return set()
    kept = _kept_in_root(plan.entries, tree)
    disks = (_KeptTree(kept, fold=False), _KeptTree(kept, fold=True))
    named: set[str] = set()
    for rel, _ in _pin_files(plan):
        # The disk `_kept_pin_findings` names its row from.
        disk = next((one for one in disks if _holds_a_pin(one, rel)), None)
        at = disk.at(rel) if disk else None
        if at and at[1] == SYMLINK_MODE:
            named.add(at[0])
    return named


def _holds_a_pin(disk: _KeptTree, rel: str) -> bool:
    """Whether `_kept_pin_findings` finds, on `disk`, something the plan
    keeps at the pin's file `rel` or under it, but a submodule."""
    at = disk.at(rel)
    return any(row[1] != GITLINK_MODE
               for row in ([at] if at else disk.under(rel)))


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
    this check's, because #262's rule follows no link. A symlink AT
    `project.yaml` is #305's `plan-root-blocks-manifest`, which
    `_shape_blocks` reports the same way, and is not said again either; nor
    is a symlink AT a declared pin's file or AT the shape's own pin, #273's
    `plan-root-holds-pin` (`_links_at_a_pin`, #524).

    A walk that stops at a symlink with an empty target is #303's to say:
    `plan-empty-symlink` names every such symlink in the source, first in
    `_entry_findings`' list, with the fix in the source, so it is not said
    again here, wherever in the walk's chain that symlink is.

    Where `git` checks a symlink out as a plain file, the link a reported
    walk meets first ABOVE its path is that file in the clone, and the
    finding says so, as `adopt-symlinks-off` does, in place of where the
    link leads (`_a_file_above`, L1-J3 of #183's re-verify, #531). It is
    still the one finding for that link, in the same place in the list, and
    a link the walk follows into something the root keeps is still no
    finding of this check's: `execute` refuses it after this list, as
    `adopt-symlinks-off`.
    """
    findings: list[str] = []
    if not any(mode == SYMLINK_MODE for _, mode, _, _ in tree):
        return findings
    seen = _links_at_a_copy(plan, tree) | _links_at_a_pin(plan, tree)
    probe = _SymlinkProbe(source.work_root)
    for fold in (False, True):
        for walk in _PlannedRoot(plan, source, tree, probe=probe,
                                 fold=fold).walks():
            why = walk.problem or _misplaced_script(walk)
            if why is None or walk.empty or walk.links[0][0] in seen:
                continue
            seen.add(walk.links[0][0])
            findings.append(_root_symlink_finding(
                walk, why, _CASE_ASIDE if fold else "",
                as_a_file=_a_file_above(walk, probe)))
    return findings


def _a_file_above(walk: _Walk, probe: _SymlinkProbe) -> bool:
    """Whether the clone holds the symlink `walk` meets first, ABOVE its own
    path, as a plain file: where `git` checks a symlink out as one
    (`core.symlinks` false, Git for Windows' default), nothing is written
    beneath it, wherever it leads (#531). `_PlannedRoot._a_file_here`'s
    question, of a link above the path rather than at it, and asked of the
    same `probe`. The disk is asked only for a link `check` reports, so a
    plan with none still makes no probe."""
    return (bool(walk.links)
            and walk.links[0][0].casefold() != walk.path.casefold()
            and not probe.symlinks())


def _root_symlink_finding(walk: _Walk, why: str, aside: str, *,
                          as_a_file: bool = False) -> str:
    """The line `check` prints for a symlink `walk` cannot be written
    through, and what to do. A walk that stopped at a symlink with an empty
    target never comes here: that symlink is #303's `plan-empty-symlink`.

    `as_a_file` (`_a_file_above`): the clone holds the link as a plain file.
    That is the reason then, in `adopt-symlinks-off`'s words, and not `why`,
    which is the reason on a disk that holds symlinks; and the fix is in the
    plan, because on that disk no target the link is given makes it a
    directory, and "change where it points" led on to `adopt-symlinks-off`
    (#531)."""
    link, target = walk.links[0]
    fix = (f"Send {_spelled(link)} to a leg or `drop` it, or change where it "
           "points in the source and re-run `plan`.")
    if as_a_file:
        why = ("`git` here checks a symlink out as a plain file "
               "(`core.symlinks` is false), so the assembly's clone would "
               f"hold {_spelled(link)} as a file, wherever it points, and "
               "nothing can be written beneath a file")
        fix = (f"Send {_spelled(link)} to a leg or `drop` it in the plan, "
               "and run `check` again.")
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
    return answer.stdout.strip() != FALSE_WORD


class _SymlinkProbe:
    """`_checks_out_symlinks` of one command's work directory, asked the
    first time a walk needs the answer and then kept, so a plan that never
    needs it makes no probe (B-OFF of #183's re-verify). With no work
    directory -- a `Source` that no command opened -- or one where no
    repository can be made, a symlink is taken to be checked out as a
    symlink."""

    def __init__(self, work_root: Path | None) -> None:
        self.work_root = work_root
        self._answer: bool | None = None

    def symlinks(self) -> bool:
        """Whether `git` checks a symlink out AS a symlink there."""
        if self._answer is None:
            try:
                self._answer = (self.work_root is None
                                or _checks_out_symlinks(self.work_root))
            except OSError:
                # No repository can be made there, as in a `--work-dir` this
                # user cannot write (J4 of #183's re-verify). Taken as a disk
                # that holds symlinks, `check` prints the finding it printed
                # before B-OFF for a link AT a path that a walk cannot follow,
                # and the finding of such a disk for a link ABOVE one (#531),
                # beside `adopt-work-dir-unwritable` (#524), and
                # `_refuse_what_check_finds` refuses with it, where both
                # would otherwise end in a traceback. `execute` itself
                # refuses such a directory before it gets here (#524).
                self._answer = True
        return self._answer


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
    file it is still taken, and the shape's copy goes beside it, as `check`
    counts it too (`_PlannedRoot._a_file_here`). A link ABOVE one that
    `check` reports is refused before this, by `_refuse_what_check_finds`,
    whose line says the same of the file (`_a_file_above`, #531); this
    refuses the rest, which `check` passes. The probe is made only when a
    plan needs it, so an adoption with no such link runs exactly as before.
    """
    tree = source.tree()
    if not any(mode == SYMLINK_MODE for _, mode, _, _ in tree):
        return
    probe = _SymlinkProbe(work_root)
    # A case twin is met only by the walk that ignores case, and is named
    # with `check`'s own aside: on a disk that keeps case the shape path
    # does not run through it at all.
    beneath = [(walk, _CASE_ASIDE if fold else "") for fold in (False, True)
               for walk in _PlannedRoot(plan, source, tree, probe=probe,
                                        fold=fold).walks()
               if walk.links
               and walk.links[0][0].casefold() != walk.path.casefold()]
    if not beneath or probe.symlinks():
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
    # FIRST, before anything is opened: the keys the rest is read from (#386).
    mistyped, mistyped_remediation = _plan_type_findings(plan)
    if mistyped:
        for line in [*mistyped, *mistyped_remediation]:
            print(line, file=sys.stderr)
        print(f"\n{len(mistyped)} finding(s) in {plan.path}", file=sys.stderr)
        return 1
    work_root = _work_root(args)
    # Asked before the source is opened, as `execute` asks it (#524). An
    # `org/repo` source is cloned into the work directory, so where that
    # directory cannot be written there is no source to read: refused as
    # `execute` refuses it, where it ended in a PermissionError traceback.
    unwritable = _unwritable_work_dir(args, work_root)
    try:
        source = plan.open_source(args.source, work_root)
    except OSError:
        if not unwritable:
            raise
        raise Refusal(WORK_DIR_UNWRITABLE, unwritable,
                      f"Remediation: {WORK_DIR_FIX}") from None
    naming = NamingPolicy.load(NAMING_POLICY)
    findings: list[str] = []
    if unwritable:
        findings.append(
            f"FINDING {WORK_DIR_UNWRITABLE}: {unwritable}. {WORK_DIR_FIX}")
    # FIRST, because it is said where work starts; it is never one of the
    # findings below and never moves this command's exit code.
    _print_triad_advisory(source.path,
                          plan.source_commit or source.commit)

    if plan.source_commit and source.commit != plan.source_commit:
        # `commit:` is a plan value people and AIs edit: sliced first, so the
        # spelling stays bounded, and `_shown`, so a real hash reads as it did
        # and a line break or an ESC in it (#328) cannot leave the line.
        findings.append(
            f"FINDING plan-stale: the plan was written against "
            f"{_shown(plan.source_commit[:12])} but "
            f"{_spelled(source.branch)} is now at {source.commit[:12]}. "
            "Re-run `plan`: a coverage check "
            "against a tree that has moved proves nothing about the tree that "
            "will be split.")

    # Before the entries (#320): the history scan their findings make reads
    # a split branch the source keeps, and the branch is named first.
    taken, taken_remediation = _check_split_branch(plan, source)
    findings.extend(taken)
    entry_findings, remediation, notes = _entry_findings(plan, source)
    findings.extend(entry_findings)
    remediation = taken_remediation + remediation

    names = plan.names()
    pins = set(plan.pins)
    # The plan names the source, or `execute` acts on another repository
    # (#499): said before the names' own findings, as `execute` refuses it.
    another = _not_the_source(plan, source, names)
    if another:
        findings.append(f"FINDING {PLAN_NOT_THE_SOURCE}: {another}")
        remediation.append(_own_name_remediation(source, naming, pins, ""))
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
        # `commit:` is `_shown` as `check` shows it (#328).
        raise Refusal(
            "plan-stale",
            f"the plan was written against "
            f"{_shown(plan.source_commit[:12])} and "
            f"{_spelled(source.branch)} is now at {source.commit[:12]}",
            "Remediation: re-run `plan`, re-answer anything new, then "
            "`check`. Splitting a tree the plan has not seen is how a path "
            "goes missing.")


#: The adoption's own ruleset hint (#177). `RULESET_HINT` is the scaffold's,
#: and it stays the scaffold's word for word. A SEED BRANCH AND A PULL
#: REQUEST ARE NAMED ONLY AS WHAT CANNOT FINISH AN ADOPTION (#188 N2). That
#: route pushed the leg to a seed branch and opened a pull request against the
#: tracking branch, but the leg is a repository this run created and its first
#: push was the one refused, so there is no tracking branch for that pull
#: request to target; and even a merged one would resume nothing, since the
#: rest of the adoption (the other leg, the split) is made only by a re-run,
#: into new legs. Nor is it "the scaffold's other exit", as this hint called
#: it until #523: #506 took it out of the scaffold's hint too, which names it
#: only as what cannot finish a scaffold. So an adoption names its one exit, a
#: re-run by somebody holding the bypass right, and the notice printed after
#: this hint (`_nothing_rolled_back`) names what that re-run must clear
#: first. The notice also says to fix what failed before the re-run, and
#: under such a ruleset the bypass IS that fix: the hint says so last, or
#: "fixed", read alone, would invite a change to the ruleset this hint
#: forbids (#188's re-verification, R4).
ADOPT_RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. An adoption has ONE legitimate exit: have an operator
holding the bypass right re-run it, once what the notice below names is
cleared. A seed branch and a pull request cannot finish an adoption:
{repo} has no {tracking} for that pull request to target, and nothing would
run the rest of this adoption after it was merged. Under such a ruleset, that
bypass is the fix the notice below asks for, never a change to the ruleset.
"""

#: What a step that runs once a leg repository exists reports as a REFUSAL,
#: with the notice and exit 2 (#184 P3-1, #188 N3). Beside the failed
#: command, it is a refusal raised on the way (`git_out`'s, the
#: materializer's), which reached `main` with no notice, and the operating
#: system or a decoder saying no -- a read-only work directory, a symlink loop
#: the materializer walks into, `git` gone from PATH, output that is not
#: UTF-8 -- which escaped as a traceback with exit 1, the code this module
#: keeps for findings. Anything else is a defect or an interrupt: it is told
#: what it left behind too, and then re-raised.
LATE_FAILURES = (CommandFailed, Refusal, OSError, UnicodeError)


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


def _interrupted(exc: BaseException) -> bool:
    """Whether `exc` stopped a run that failed at nothing: Ctrl-C.

    Its notice says only to re-run. Anything else that no step anticipates
    -- a defect, a `TypeError` say -- fails the same way on every re-run, so
    its notice says to fix it first, as a refusal's does: "Re-run" alone
    made one more pair of leg repositories per attempt (#188's
    re-verification, R2).
    """
    return isinstance(exc, KeyboardInterrupt)


#: What a run builds in its work directory, `<work_root>/<name>` each, in the
#: order it builds them: each leg, cloned or seeded by `_build_the_legs`, then
#: the split, which `_commit_the_split` clones the source into. Both come
#: after `_create_leg_remotes` has made the two leg repositories.
BUILT_IN = {"spec": "the spec leg", "code": "the code leg",
            "assembly": "the split"}
#: Why a directory of `BUILT_IN` that holds something is refused, by what
#: builds in it. The split and an extracted leg are cloned into theirs; a
#: seeded leg is not, so `git clone` was no reason for its directory
#: (#188's confirmation check, N-1). `_seed_leg` writes its template into
#: the directory and commits there: on main, a person's own files and
#: history left there went into the new leg and were pushed. So a seeded
#: leg's reason is the rule, not a guess at what its first commit would
#: take in: an ignored `.DS_Store`, an empty directory or a repository with
#: no commit would not go in, and the directory is refused all the same
#: (#188's review, N-2).
CLONE_REFUSES = "`git clone` refuses a directory that is not empty"
SEEDS_ONLY_INTO_EMPTY = ("a seeded leg is written and committed in its own "
                         "directory, and only in one that is new or empty")


def _holds_something(path: Path) -> bool:
    """Whether `path` is anything but absent or an empty directory: what `git
    clone` refuses with `destination path ... already exists and is not an
    empty directory`, and what `execute` will not seed a leg into, whether
    or not git would commit any of it (#188's review, N-2). A directory
    that cannot be listed counts, as it does for git."""
    if not (path.exists() or path.is_symlink()):
        return False
    try:
        return not path.is_dir() or any(path.iterdir())
    except OSError:
        return True


def _built_in(work_root: Path, names: dict) -> list[tuple[str, str]]:
    """`(name, what)` for each directory of `BUILT_IN` that already holds
    something in `work_root`: its name there, and what a run builds in it."""
    return [(names[role], what) for role, what in BUILT_IN.items()
            if _holds_something(work_root / names[role])]


def _cloned_here(source: Source | None, work_root: Path) -> list[str]:
    """The source's own clone, as a path in `work_root`, when this run made
    it there: `Source.open` clones an `org/repo` into
    `<work_root>/source-readonly/<repo>`, and a re-run given the same
    --work-dir is refused there, as `source-unclonable` (#188's
    re-verification, R3). A local path is read in place and is no part of
    the work directory.

    It is not one of `BUILT_IN`: the run that cloned it goes on to
    `_refuse_an_occupied_work_dir`, which must not refuse that run for its
    own clone."""
    if source is None or not source.cloned \
            or not _holds_something(source.path):
        return []
    return [source.path.relative_to(work_root).as_posix()]


def _and_listed(items: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`: a few things, as a sentence names them."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _spelled_and_listed(paths: list[str]) -> str:
    """`_and_listed`, each path `_spelled`: what a work directory holds, as
    the notice and `adopt-work-dir-occupied` name it."""
    return _and_listed([_spelled(path) for path in paths])


def _nothing_rolled_back(urls: dict, pushed: list, work_root: Path,
                         names: dict, made=EXTRACTED_LEGS, *,
                         interrupted: bool = False,
                         source: Source | None = None) -> str:
    """The one notice for a failure once a leg repository exists.

    `_create_leg_remotes` refuses a re-run while they exist:
    `leg-remote-exists` under `--local-remote-dir`, and a `gh repo create`
    that finds the name taken against GitHub. Every failure after it
    therefore names the leg repositories this run `made` (both, unless the
    second could not be created, #188 N4), says which legs are already pushed
    (`pushed`, the roles in the order they were pushed), and gives the way
    out. One wording covers every such failure: a leg repository, a leg that
    cannot be built (#171), a leg push that is refused (#177), a split that
    cannot be cloned, mounted, committed or pushed, and a verification that
    fails or cannot be made (#188).

    THE WAY OUT STARTS WITH THE CAUSE (#188's review, F2). A re-run into
    fresh legs while what failed is still there fails the same way, with one
    more pair of leg repositories behind it, so the re-run comes once that
    is fixed. A run that was INTERRUPTED, by Ctrl-C, failed at nothing, and
    is told only how to re-run; a defect fails again on every re-run, and is
    told to fix it first, as any failure is (`_interrupted`).

    THE WAY OUT NAMES THE WORK DIRECTORY when this run built something in it
    (#184 P2-1, and N2 of #188's review): each leg is built in
    `<work_root>/<leg>` and the split cloned into `<work_root>/<assembly>`,
    and `_refuse_an_occupied_work_dir` refuses a run whose work directory
    already holds one, before it creates anything. So does the `source` this
    run cloned there (`_cloned_here`), which a re-run cannot clone again. It
    is read off the disk, so a failure before anything was built or cloned
    (the code leg's repository, N4, from a local source) does not send the
    person away from a work directory a re-run can use. Without `--work-dir`
    every run makes its own, which is why "or none" is a way out too.

    EVERY PATH IT NAMES IS `_spelled` (#212): between backticks, with a
    backslash escape for a backslash, a backtick and any character
    `str.isprintable` refuses, as a finding spells a path. A leg repository
    under `--local-remote-dir` and the work directory are paths a person
    chose, and printed raw, one holding a line break or an ESC split or
    overwrote the one line this notice is.
    """
    one = len(made) == 1
    if one:
        state = "nothing is pushed to it"
    elif not pushed:
        state = "neither leg is pushed"
    elif len(pushed) == 1:
        state = f"the {pushed[0]} leg is pushed"
    else:
        state = "both legs are pushed"
    named = (_spelled(urls[made[0]]) if one else
             f"{_spelled(urls['spec'])} and {_spelled(urls['code'])}")
    exist, them, fresh = (("exists", "it", "a fresh one") if one
                          else ("exist", "them", "fresh ones"))
    rerun = ("Re-run" if interrupted
             else "Once what failed above is fixed, re-run")
    notice = (f"NOTHING has been rolled back: {named} {exist}, and {state}. "
              f"{rerun} the adoption with {them} deleted or with {fresh} (a "
              "new --local-remote-dir, or new leg repositories): a re-run "
              f"that meets {them} is refused, as `leg-remote-exists` under "
              "--local-remote-dir, and against GitHub by `gh repo create`, "
              "which finds the name already taken.")
    built = (_cloned_here(source, work_root)
             + [name for name, _ in _built_in(work_root, names)])
    if built:
        notice += (" Use a fresh --work-dir as well, or none: "
                   f"{_spelled(str(work_root))} holds "
                   f"{_spelled_and_listed(built)} from this run, and "
                   "`execute` refuses a --work-dir that holds them.")
    return notice


def _failed_loudly(step: str, exc: BaseException) -> str:
    """What failed during `step`, as the REFUSED block `CommandFailed` prints.

    `CommandFailed` says it itself. A `Refusal` keeps its code and detail,
    and its own remediation if it has one and it is not the validators'
    generic one, which is about pins: here it would contradict the notice
    printed under it. `git_out` handed every refusal it raised that one, and
    hands them none since #370, which is no line at all rather than an empty
    one. Anything else is named by its type, and is a REFUSAL only if it is
    one of `LATE_FAILURES`; the rest STOPPED the run, and their traceback
    follows.
    """
    if isinstance(exc, CommandFailed):
        return exc.loudly(step)
    if isinstance(exc, Refusal):
        said = f"REFUSED {step}. {exc.code}: {exc.detail}"
        return said if exc.remediation in ("", REMEDIATION) \
            else f"{said}\n{exc.remediation}"
    what = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    if isinstance(exc, LATE_FAILURES):
        return f"REFUSED {step}. {what}"
    return f"STOPPED {step} by {what}."


def _report_late(step: str, exc: BaseException, notice: str) -> None:
    """Report a failure once a leg repository exists (#171, #188).

    Stdout is flushed first, so a merged log keeps the order things ran in;
    then what failed, unless whoever raised it has already said so (a leg
    builder's refused push, with its ruleset hint, is `reported`); then
    `notice`. The exception is left `reported`, so `main` does not print it
    a second time when a caller re-raises it.
    """
    _flush_stdout()
    if not _reported(exc):
        print(_failed_loudly(step, exc), file=sys.stderr)
    print(notice, file=sys.stderr)
    exc.reported = True


def _reported(exc: BaseException) -> bool:
    """Whether a step has already printed `exc`, and what it left behind:
    a leg builder's refused push, or anything `_report_late` has seen."""
    return getattr(exc, "reported", False)


def _branch_deletion(source: Source, urls: dict, branch: str) -> str:
    """The command that deletes the split branch from the assembly.

    Every value is quoted for `sh` (#188 N5): a source or a remote directory
    whose path has a space in it is an ordinary thing to have, and an
    unquoted one pastes as three arguments. It runs in the source because
    `git push` must run inside a repository, and the source is the one
    repository every adoption has, a local path or the clone `Source.open`
    made of an `org/repo`.

    NOT `_spelled`, as the sentence before it is (#212): it is a command to
    paste, and `sh` reads a quoted path, not a spelled one.
    """
    return " ".join(["git", "-C", shlex.quote(str(source.path)), "push",
                     shlex.quote(urls["assembly"]), "--delete",
                     shlex.quote(branch)])


def _refuse_an_occupied_work_dir(work_root: Path, names: dict,
                                 seeded: list[str]) -> None:
    """Refuse a work directory that already holds one of the directories
    this run builds in (`BUILT_IN`), BEFORE a leg repository exists (#188's
    review, F1).

    Each of them is built only after `_create_leg_remotes` has made both
    leg repositories, and `git clone` refuses a directory that is not empty.
    So a run into a `--work-dir` an earlier run had built in made two legs
    (two real repositories, against GitHub) and then stopped at the clone.
    A SEEDED leg (`seeded`, its roles) is not cloned: it is written and
    committed in its own directory, which must be new or empty, so the
    detail gives each directory the reason of what builds in it
    (`CLONE_REFUSES`, `SEEDS_ONLY_INTO_EMPTY`; #188's confirmation check,
    N-1, and its review, N-2).
    The notice says not to reuse such a directory, but one printed way out
    left it unsaid -- `adopt-branch-exists`'s "delete the branch, then run
    `execute` again" -- and followed as written, it looped: a new pair of
    leg repositories per attempt. Refused here, no way out leads past it.

    It is the first refusal of what an earlier run left, before
    `_refuse_a_split_branch_left_behind` and so before `leg-remote-exists`,
    so the re-run either of their ways out leads to meets a work directory
    that holds none of these.

    NEVER A DEFAULT RUN: without `--work-dir`, `_work_root` makes a new,
    empty directory, and a new or empty `--work-dir` holds nothing either.

    Its paths are `_spelled`, as the notice's are (#212).
    """
    built = _built_in(work_root, names)
    if built:
        raise Refusal(
            "adopt-work-dir-occupied",
            f"--work-dir {_spelled(str(work_root))} already holds "
            f"{_spelled_and_listed([name for name, _ in built])}, where this "
            f"run builds {_and_listed([what for _, what in built])}, and only "
            "after it has made both leg repositories: "
            + _why_occupied(built, names, seeded),
            "Remediation: no leg repository was created and nothing was "
            "pushed. Pass a --work-dir that is new or empty, or none: without "
            "one, each run makes a new one.")


#: `check`'s finding, and the code `execute` refuses it under, for a
#: `--work-dir` this user cannot write in (#524); and what both say to do.
WORK_DIR_UNWRITABLE = "adopt-work-dir-unwritable"
WORK_DIR_FIX = ("Pass a --work-dir this user can write in, or none: without "
                "one, each run makes a new one.")


def _unwritable_work_dir(args, work_root: Path) -> str | None:
    """Why this run cannot build in the `--work-dir` it was given, or None:
    a directory made in it, and removed again, could not be (#524).

    `_work_root` only makes the directory, and what `execute` builds there,
    the legs and the split (`BUILT_IN`), it builds only after
    `_create_leg_remotes` has made both leg repositories. So with a
    `--work-dir` this user cannot write in (`chmod 500`), `check` said `plan
    ok`, and `execute` made and pushed both legs and stopped `extracting the
    spec leg`, exit 2, as on main at 8beb3d92 and bfed143. Each command now
    asks the directory itself, as `execute` will use it: `execute` refuses
    it first, before it opens the source (an `org/repo` source is cloned
    there), and `check` names it beside the plan's findings, so the two
    agree. The probe has a name of its own (`tempfile.mkdtemp`), so it
    meets nothing an earlier run left there, and it is removed again.

    Without `--work-dir`, `_work_root` makes a new directory, which this
    user owns and can write in, and nothing is asked."""
    if not getattr(args, "work_dir", None):
        return None
    try:
        os.rmdir(tempfile.mkdtemp(prefix="write-probe-", dir=work_root))
    except OSError as exc:
        return (f"--work-dir {_spelled(str(work_root))} cannot be written: "
                "making a directory in it, and removing it again, failed "
                f"({exc.strerror or exc}), and `execute` builds "
                f"{_and_listed(list(BUILT_IN.values()))} there, only after "
                "it has made both leg repositories")
    return None


def _refuse_an_unwritable_work_dir(args, work_root: Path) -> None:
    """Refuse `_unwritable_work_dir`'s `--work-dir`, before any leg
    repository exists (#524)."""
    unwritable = _unwritable_work_dir(args, work_root)
    if unwritable:
        raise Refusal(WORK_DIR_UNWRITABLE, unwritable,
                      "Remediation: no leg repository was created and "
                      f"nothing was pushed. {WORK_DIR_FIX}")


def _why_occupied(built: list[tuple[str, str]], names: dict,
                  seeded: list[str]) -> str:
    """Why `built`'s directories are refused: each builder's reason once,
    in the order `BUILT_IN` builds them, a seeded leg's
    `SEEDS_ONLY_INTO_EMPTY` and every other's `CLONE_REFUSES`."""
    seeds = {names[role] for role in seeded}
    reasons = [SEEDS_ONLY_INTO_EMPTY if name in seeds else CLONE_REFUSES
               for name, _ in built]
    return ", and ".join(dict.fromkeys(reasons))


def _in_the_history_of(source: Source, tip: str) -> bool:
    """Whether `tip` is the source commit or a commit behind it: the only
    tips a split commit, made on top of the source commit, moves a branch
    from without force (#188's review, N1).

    `git merge-base --is-ancestor` exits 0 for exactly those; 1 for any
    other commit the source holds, and 128 for one it does not hold, which
    is not behind its commit either. A `tip` that is not a hexadecimal
    object name -- `git ls-remote` prints nothing else -- is not asked, so
    nothing it says reaches `git` as an option.
    """
    if not re.fullmatch(r"[0-9a-f]+", tip):
        return False
    asked = subprocess.run(["git", "merge-base", "--is-ancestor", tip,
                            source.commit], cwd=str(source.path),
                           capture_output=True, check=False)
    return asked.returncode == 0


def _refuse_a_split_branch_left_behind(source: Source, urls: dict,
                                       branch: str, local: bool) -> None:
    """Refuse a run whose split branch is already on the assembly, BEFORE a
    leg repository exists (#188 N1).

    An earlier `execute` leaves that branch behind whether its verification
    passed or failed, at a split commit made on top of the source commit.
    A new split commit is never a fast-forward of the old one, so the re-run
    a failed verification prescribed, into fresh legs, created and pushed
    two more legs and was then refused at the split push, every time:
    against GitHub, two more real repositories per attempt. The branch is
    asked of the very remote the split is pushed to, with `git ls-remote`,
    so the answer is the push's own.

    ONLY A BRANCH THE PUSH CANNOT FAST-FORWARD IS REFUSED (#188's review,
    N1). One at the source commit, or behind it, is moved forward by the
    split push, and main always pushed over it and verified; it was
    refused, with a reason that was false for it. The branch's name is a
    plan value (`adopt_branch:`) a person may have pointed at a branch of
    the source's own, so the remediation says what to do then too, and the
    deletion it prints is offered only for an earlier run's branch.

    A leg repository that is still there under `--local-remote-dir` is
    `_create_leg_remotes`' to refuse, as `leg-remote-exists`, and it keeps
    that precedence: this refusal is for the re-run that has cleared its
    legs and not the branch. A work directory an earlier run built in is
    refused before either (`_refuse_an_occupied_work_dir`), so "run `execute`
    again" below meets one that is free.

    The assembly and the branch are `_spelled`, as the notice's split line
    names them (#212); the deletion is a command, quoted for `sh`.
    """
    if local and any(Path(urls[role]).exists() for role in EXTRACTED_LEGS):
        return
    ref = f"refs/heads/{branch}"
    listed = run(["git", "ls-remote", urls["assembly"], ref])
    tips = [line.split("\t")[0] for line in listed.splitlines()
            if line.split("\t")[-1] == ref]
    if not tips or _in_the_history_of(source, tips[0]):
        return
    raise Refusal(
        "adopt-branch-exists",
        f"{_spelled(urls['assembly'])} already has {_spelled(branch)}, the "
        "branch this adoption pushes its split commit to, at "
        f"{tips[0][:12]}: neither the source commit {source.commit[:12]} nor "
        "a commit behind it",
        "Remediation: no leg repository was created and nothing was pushed. "
        "The split commit is made on top of the source commit, git moves a "
        "branch to it without force only from that commit or one behind it, "
        "and this tool never forces a push: a run that kept this branch "
        "would make and push both legs before its split push met it. An "
        "earlier `execute` leaves a branch of that name behind, whether it "
        "verified or not. If it verified and its pull request is the "
        "adoption you want, review that instead of re-running. If the branch "
        "is not an earlier run's (the plan's `adopt_branch:` names one of "
        "the source's own), give `adopt_branch:` a name no branch has. "
        "Otherwise delete it, then run `execute` again:\n    "
        + _branch_deletion(source, urls, branch))


def _create_leg_remotes(plan: Plan, names: dict, repositories: dict,
                        urls: dict, tracking: str, local: bool,
                        work_root: Path, *,
                        source: Source | None = None) -> None:
    """(a) The two NEW repositories. The assembly root is never created here.

    The spec leg's repository is created first, so a failure creating the
    code leg's leaves one repository behind, and the re-run meets it:
    against GitHub as `gh repo create` finding its name taken. That failure
    therefore gets the notice too, naming the one that exists (#188 N4), and
    is re-raised `reported`: `main` exits 2 on any of `LATE_FAILURES` without
    printing it twice, and anything else (Ctrl-C) keeps its traceback. A
    failure on the first leg leaves nothing, and `main` reports it as before.
    `source` is handed on for the notice: nothing is built in the work
    directory yet, but an `org/repo` source is already cloned there.
    """
    print("\ncreating the leg repositories")
    if local:
        Path(urls["spec"]).parent.mkdir(parents=True, exist_ok=True)
    made: list[str] = []
    for role in EXTRACTED_LEGS:
        try:
            _create_leg_remote(plan, names, repositories, urls, tracking,
                               local, role)
        except BaseException as exc:
            if made:
                _report_late(f"creating the {role} leg repository", exc,
                             _nothing_rolled_back(
                                 urls, [], work_root, names, made,
                                 interrupted=_interrupted(exc),
                                 source=source))
            raise
        made.append(role)

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


def _create_leg_remote(plan: Plan, names: dict, repositories: dict,
                       urls: dict, tracking: str, local: bool,
                       role: str) -> None:
    """One leg's repository: `gh repo create`, or a bare one on disk."""
    if not local:
        run(["gh", "repo", "create", repositories[role],
             f"--{plan.get('visibility', 'private')}", "--description",
             f"{names['assembly']} — {role} leg, extracted from "
             f"{repositories['assembly']} with history"])
        print(f"  gh    {repositories[role]}")
        return
    bare = Path(urls[role])
    if bare.exists():
        raise Refusal(
            "leg-remote-exists", f"{bare} already exists",
            "Remediation: choose an empty --local-remote-dir, and a "
            "--work-dir the run that made it did not clone into (a fresh "
            "one, or none): `git clone` refuses a directory it already "
            "cloned into. There is no --force: re-running over a live leg "
            "is not an adoption.")
    run(["git", "init", "-q", "--bare", "-b", tracking, str(bare)])
    print(f"  bare  {bare}")


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
    count = git_out(["rev-list", "--count", "HEAD"], cwd=work)
    digest = tree_digest(work, head)
    _push_the_leg(f"pushing the {role} leg", work, url, tracking, repository)
    print(f"  {role:<5} {len(paths):>3} path(s) -> {head[:12]} "
          f"({count} commits kept) -> {url}")
    return head, digest


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
    digest = tree_digest(work, commit)
    _push_the_leg(f"pushing the seeded {role} leg", work, url, tracking,
                  repository)
    print(f"  {role:<5}   0 path(s) -> {commit[:12]} (SEEDED from "
          f"{SEED_TEMPLATE[role]}/) -> {url}")
    return commit, digest


def _push_the_leg(step: str, work: Path, url: str, tracking: str,
                  repository: str) -> None:
    """Push a built leg to its new repository's tracking branch: the LAST
    thing a leg builder does before it prints the leg and returns.

    Last, because `_build_the_legs` says which legs are pushed from the ones
    whose builder RETURNED (#188). The two builders read the commit count and
    the tree digest before this, so no read that fails afterwards can make
    the notice call a pushed leg unpushed.

    A refused push is the one failure a builder prints itself, with the
    adoption's ruleset hint, and marks `reported` before re-raising it, so
    `_build_the_legs` adds the notice and not a second block for the same
    command (#171, #177).
    """
    try:
        run(["git", "push", "-q", url, f"HEAD:refs/heads/{tracking}"], cwd=work)
    except CommandFailed as exc:
        _flush_stdout()
        print(exc.loudly(step), file=sys.stderr)
        print(ADOPT_RULESET_HINT.format(repo=repository, tracking=tracking),
              file=sys.stderr)
        exc.reported = True
        raise


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
    `\\udcff`, as every other finding does (#212, #329). Decoded with
    `replace`, `a<0xFF>` and `a<0xFE>` both read `a<U+FFFD>`.
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
    tracking = checked_value(TRACKING_KEY, plan.get(TRACKING_KEY, "main"))
    return spec_path, code_path, branch, tracking


def _plan_org(plan: Plan) -> str:
    """The plan's `org:` as `execute` puts it into each repository's name
    and URL: `str()` of whatever the file holds, which is the text
    `checked_value` asks about and hands back. THE ONE READ for
    `_repository_urls` and for `_not_the_source` (#499), so that the
    repository `check` and `execute` compare with the source is the one
    `execute` acts on: `org: 2026`, `org: true`, `org: ~` and no `org:` line
    at all are `2026`, `True` and `None` there, and were let by while the
    comparison read only text (#513's review, SHOULD-1)."""
    return str(plan.get("org"))


def _repository_urls(args, plan: Plan, names: dict,
                     source: Source) -> tuple[bool, dict, dict]:
    """Where the three repositories are: `(local, repositories, urls)`.

    Split out of `cmd_execute` for #138. The assembly root's URL is the SOURCE
    itself under `--local-remote-dir`, because an in-place adoption pushes its
    split branch back to the repository it read.
    """
    org = checked_value("org", _plan_org(plan))
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    local = args.local_remote_dir is not None
    # Each name is a directory's too: the work directory's for all three, and
    # under `--local-remote-dir` a bare `<name>.git` for the two new legs. A
    # name of 247 to 250 characters passed every check and died in
    # `Path.exists` with `File name too long`, a traceback, before any leg
    # existed (#261).
    refuse_unstorable_names(
        "adopt-name-too-long", list(names.values()),
        [names["spec"], names["code"]] if local else [])
    return (local, repositories,
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
    (#178) -- but what the disk says of such a link AT a shape path is asked
    again here, before any leg exists, from this run's own work directory:
    whether anything is where it leads out of the assembly, and whether
    `git` checks it out as a symlink at all (#183).
    The refusal's code is the FIRST finding's own (`plan-uncovered`, ...);
    its detail is every finding as `check` prints it, capped at
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
            + AND.join(f"{role} leg" for role in unconsented)
            + ", so it would be SEEDED from "
            + AND.join(f"{SEED_TEMPLATE[role]}/" for role in unconsented)
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

    Returns `(leg_commits, leg_digests)`, or None when building a leg failed,
    having printed which step, why, and what is left. `run` only RAISES; it
    says nothing, so this is the one place a failed `git filter-repo` (or
    clone, checkout or seeding commit) is ever reported, and an `execute` that
    stopped here after both leg repositories exist must not exit 2 with an
    empty stderr (#171). The notice names the two leg repositories, because
    nothing is rolled back and `_create_leg_remotes` refuses a re-run while
    they exist, and, once a leg was built there, the work directory a re-run
    must not reuse (#184 P2-1).
    A refused PUSH is the one failure its own leg builder already printed,
    with the adoption's ruleset hint, so only the notice follows it (#177).

    EVERY FAILURE HERE GETS THAT REPORT, not only a failed command (#184
    P3-1): a refusal from `git_out` or the template, a read-only work
    directory, `git` gone from PATH, output that is not UTF-8. Each of those
    used to escape to `main`, as a refusal or as a traceback with exit 1, with
    both leg repositories left behind and nothing saying so. They are
    `LATE_FAILURES`, reported and refused with exit 2, as a failed command
    is. Anything else -- Ctrl-C, a defect -- gets the notice and is re-raised,
    traceback and all. Split out of `cmd_execute` for #138.
    """
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role in EXTRACTED_LEGS:
        verb = "seeding" if role in seeded else "extracting"
        step = f"{verb} the {role} leg"
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
        except LATE_FAILURES as exc:
            _report_late(step, exc, _nothing_rolled_back(
                urls, list(leg_commits), work_root, names, source=source))
            return None
        except BaseException as exc:
            _report_late(step, exc, _nothing_rolled_back(
                urls, list(leg_commits), work_root, names,
                interrupted=_interrupted(exc), source=source))
            raise
    return leg_commits, leg_digests


def _pull_request_command(repositories: dict, names: dict, tracking: str,
                          branch: str, message: str) -> list[str]:
    """The `gh pr create` that opens the split's pull request. It carries its
    own title and body, so it runs with no terminal to prompt on: this is what
    `_open_the_pull_request` runs, and what `_finish_by_hand` prints (#304).
    Its base is the tracking branch, which `plan` takes from the source's
    default branch unless told another, and which `check` finds when it is
    no branch of the source (#479)."""
    return ["gh", "pr", "create", "--repo", repositories["assembly"],
            "--base", tracking, "--head", branch,
            "--title", f"Adopt the three-repository shape: "
                       f"{names['spec']} and {names['code']}",
            "--body", message]


def _open_the_pull_request(repositories: dict, names: dict, tracking: str,
                           branch: str, message: str) -> bool:
    """(c″) The pull request, because these organisations are pull-request
    only. It comes after the topic (`_set_the_topic`, #481).

    Returns False when `gh` refused, or could not be run at all (any of
    `LATE_FAILURES`, #188), having printed why. The branch IS pushed by
    the time this runs, so the exit is never "start again". The command
    that finishes the job by hand is `_finish_by_hand`'s, which the caller
    prints AFTER the verification and only once it has passed (#304): until
    then nothing says the split is the one to open a pull request for. Split
    out of `cmd_execute` for #138.
    """
    try:
        url = run(_pull_request_command(repositories, names, tracking, branch,
                                        message))
        print(f"  pull request {url}")
    except LATE_FAILURES as exc:
        _flush_stdout()   # the pushed split is announced on stdout (#188)
        print(_failed_loudly("opening the pull request", exc),
              file=sys.stderr)
        return False
    return True


def _finish_by_hand(passed: bool, refused: list[str] | None, topic: str,
                    unset: list[str], *, opened: str | None = None,
                    carried: list[str] | None = None) -> None:
    """What a refused `gh pr create` and a topic that would not set leave to
    do, said ONCE, after the table, when `execute` knows whether the split it
    pushed is the one the plan asked for (#304, #481).

    `refused` is the `gh pr create` that `gh` refused, as
    `_pull_request_command` built it, and None when the pull request is open
    or none was tried (`--local-remote-dir`); `unset` names each repository
    `_set_the_topic` could not give `topic`. `opened` is the repository the
    split's pull request IS open on, None where none is, and `carried` each
    repository that has the topic: what a failed verification leaves in
    place, and says (#523).

    A split that PASSED verification gets the commands that finish the job:
    a `gh repo edit` for each repository left without the topic, then the
    command that opens the pull request, the one `_open_the_pull_request`
    ran, with its title and body, so that it also runs where there is no
    terminal to prompt on. That command is the LAST thing said, as it was
    before the topic came first. With the pull request open, the topic's
    commands are said under `The split IS pushed and the pull request IS
    open`, as they always were; beside a refused one, under `The branch IS
    pushed`, ahead of it. A refused pull request used to stop the run before
    the topic was tried, and its way out never said so (#481).

    One that did not pass gets the opposite: the refusal printed above names
    the exact command that was tried, and a person who sees only that, with
    findings under it, may paste it. No topic is offered there either: the
    way out is the verification's, and the re-run it names sets the topic.

    WHAT IT LEAVES IN PLACE IS SAID TOO (#523). `execute` sets the topic and
    opens the pull request BEFORE it verifies, so against GitHub a split that
    failed has its pull request open on the source and the topic on every
    repository that took it, and the way out said neither: it said NOTHING
    was deleted from the source, which is true, and AGENTS.md said the source
    was untouched, which is not. So the open pull request is named as one
    for a split that failed, with what closes it, the deletion of its branch
    the way out already names; and the topic as staying set: the re-run sets
    it again on the root and on the legs it makes, and a leg the person
    keeps, re-running into fresh leg repositories rather than deleting it,
    keeps the topic too (#582's review).

    Stdout is flushed first. The table is on it and a pipe holds it in a
    block buffer, so without the flush this would come before the table it
    depends on in a merged log; a stdout that is closed, `| head` and gone,
    must not take the commands down with it (`_flush_stdout`).
    """
    _flush_stdout()
    if not passed:
        said = []
        if refused is not None:
            said.append("No pull request was opened, and none should be: the "
                        "split above did not pass verification.")
        elif opened is not None:
            said.append(f"A pull request for that branch IS open on {opened}, "
                        "for a split that did not pass verification: "
                        "deleting the branch, as above, closes it.")
        if carried:
            said.append(f"The topic {topic} stays set on "
                        f"{_and_listed(carried)}: the re-run sets it again "
                        "on the root and the legs it makes, and a leg left "
                        "behind keeps it.")
        if said:
            print(" ".join(said), file=sys.stderr)
        return
    topics = "".join(f"\n    gh repo edit {repository} --add-topic {topic}"
                     for repository in unset)
    if refused is None:
        if unset:
            print("The split IS pushed and the pull request IS open. Set the "
                  f"topic by hand:{topics}", file=sys.stderr)
        return
    command = " ".join(shlex.quote(argument) for argument in refused)
    print("The branch IS pushed. "
          + (f"Set the topic by hand:{topics}\n" if unset else "")
          + f"Open the pull request by hand:\n    {command}", file=sys.stderr)


#: The repositories `execute` sets the project topic on, in its order.
TOPIC_ROLES = ("assembly", "spec", "code")


def _set_the_topic(repositories: dict, topic: str) -> list[str]:
    """(c′) The topic, on all three, BEFORE the pull request (#481): returns
    the repositories that carry it now, in `TOPIC_ROLES`' order.

    The assembly root pre-existed and is still a repository OF THIS PROJECT:
    `project.yaml` claims `topic: <topic>` either way, and a claim the
    organisation cannot see is the defect being fixed here. Neither the
    topic nor the pull request needs the other, so the topic comes first: a
    refused pull request used to end the run before it was tried, and left
    all three repositories without it.

    EACH REPOSITORY IS ASKED, whatever the one before it answered: a token
    refused on one may be allowed on the next, and `_finish_by_hand` names
    the exact command for each one left without the topic, and for none that
    has it. Each refusal is printed as it happens; the commands are said
    after the table.

    A TOPIC THAT WILL NOT SET DOES NOT SUPPRESS THE VERIFICATION TABLE. The
    split is pushed by now, and the blob-sha accounting for every source path
    is the report a human is told to read back (AGENTS.md step 7); losing it
    to a permission or a rate limit would be the more expensive failure. So
    this RETURNS what it set rather than exiting: the caller reports the
    rest after the table, with the commands to finish by hand, and still
    exits non-zero. That holds for a `gh` that could not be run at all as
    much as for one that refused (`LATE_FAILURES`, #188). Split out of
    `cmd_execute` for #138.
    """
    carried = []
    for role in TOPIC_ROLES:
        try:
            run(["gh", "repo", "edit", repositories[role], "--add-topic",
                 topic])
        except LATE_FAILURES as exc:
            _flush_stdout()   # the split is announced on stdout (#188)
            print(_failed_loudly("setting the project topic", exc),
                  file=sys.stderr)
            continue
        carried.append(repositories[role])
    if len(carried) == len(TOPIC_ROLES):
        print(f"  topic     {topic} set on all three")
    elif carried:
        print(f"  topic     {topic} set on {_and_listed(carried)} only")
    return carried


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

    EVERY PATH AND REASON IS DOUBLE-QUOTED, by `repo_shape.double_quoted`,
    the writer of the escapes the reader resolves (#199). Always quoted,
    unlike `y`: a submodule may sit at `null`, `true` or `0001`, which a
    plain scalar reads back as something that is not a path. And a character
    `str.isprintable` refuses is spelled by its code point: NEL and U+2028
    end a line for the reader, a no-break or zero-width space is another name
    than the one it looks like, and the surrogate a byte that is not UTF-8 is
    kept as cannot be written by `write_lf` at all, where `\\udce9` reads
    back as that surrogate. So every row reads back as the name the doctor
    holds the submodule at to it, and the manifest is written after both
    legs exist. A name with a control character or a byte that is not UTF-8
    in it is one the doctor reads no further: it reports it as a name no
    report can carry.
    """
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    kept = _kept_in_a_leg(_answered_legs(entries, gitlinks), gitlinks)
    if not kept:
        return ""
    resolutions = {str(e.get("path")): _resolution_text(e.get("resolution"))
                   for e in entries}
    lines = list(SUBMODULE_RECORD_PREAMBLE)
    for path, leg, entry in kept:
        lines.append(f"  - path: {double_quoted(path)}")
        lines.append(f"    leg: {leg}")
        if resolutions.get(entry):
            lines.append(
                f"    resolution: {double_quoted(resolutions[entry])}")
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
                      leg_commits: dict) -> tuple[str, str, list] | None:
    """(c) ONE split commit on a branch of the source, pushed.

    Returns `(split_commit, message, collisions)` — the message travels on
    because it is also the pull request's body, and the collisions,
    `(intended, actual)` for each shape file written beside one the source
    kept, because where the shape's Makefile and `scripts/bootstrap.py` went
    decides what `_next_steps` can tell a person to run (#480) — or None
    when making it failed, having printed which step, why and what it leaves
    behind. Split out of `cmd_execute` for #138.

    BOTH LEGS ARE PUSHED BY NOW, so a split that cannot be cloned, mounted,
    committed or pushed leaves the same two leg repositories a leg that
    cannot be built does, and gets the same report (#188). It used to print
    a bare `REFUSED pushing the split branch`, or `main`'s generic `a git or
    gh command failed`, ahead of the `bare` lines in a merged log, and
    nothing told the human why the re-run then met `leg-remote-exists`.
    `step` names what was being done, because the command alone does not say
    it: `git push` is also how a leg is pushed. The exit is still 2.

    Every failure, as in `_build_the_legs`: a materializer that walks into a
    symlink loop or a read-only directory used to escape as a traceback, with
    exit 1 and both legs pushed (#188 N3). The split branch an earlier run
    left behind is refused by `execute` before any leg exists
    (`_refuse_a_split_branch_left_behind`), so a refused push here is not
    that, and the notice is the whole way out.
    """
    step = "cloning the source for the split"
    try:
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
        # pushed root still gets their template from their own `git clone`.
        # Nothing else `execute` makes needs it: the legs' bare remotes and
        # work trees are never mounted into, and the mounts only READ the work
        # trees, a clone copying their objects and refs and never a
        # `.git/modules`. With no template the assembly has no `.git/hooks`, so
        # HOOKS a template installs no longer run on the split's commit and
        # push, as they did before #243; hooks set with `core.hooksPath` still
        # do, and the legs keep their template's hooks.
        run(["git", *FILE_PROTOCOL, "clone", "-q", "--template=",
             str(source.path), str(assembly)])
        run(["git", "checkout", "-q", "-B", branch, source.commit],
            cwd=assembly)
        step = "mounting the legs"
        _mount_the_legs(assembly, work_root, names, urls, paths_for,
                        spec_path, code_path)

        step = "committing the split"
        # The plan's submodule answers outlive the plan only here (#189).
        # An empty record appends nothing, so a source with no submodule
        # gets the manifest it always got. The Makefile's block names the
        # spec leg where this plan mounts it (#522), and a default plan gets
        # the block it always got.
        append = {"Makefile": adopt_makefile_block(spec_path, code_path)}
        record = submodule_record(plan.entries, source.tree(),
                                  source.commit)
        if record:
            append["project.yaml"] = record
        # Each declared pin's file, `contracts/<product>-pin.yaml`, is
        # written by the materializer as the scaffold's is, from the
        # values the plan records (#273); `_refuse_what_check_finds` has
        # refused a pin it does not record whole, and one whose file a
        # kept path holds.
        # A materializer refusal names the source's own symlinks and where
        # they lead, which can hold any character: spelled as every finding
        # is (#212).
        materialized = materialize_assembly_root(
            SHAPE_ROOT, assembly, values, collision_dir=COLLISION_DIR,
            append=append, neutral_pins=_recorded_pins(plan), spell=_spelled)
        for intended, actual in materialized.collisions:
            print(f"  beside  {actual} (the source already has {intended}; "
                  "nothing was overwritten)")
        if materialized.eol_block:
            print(f"  appended to {ATTRIBUTES}: a `text eol=lf` line for "
                  f"each of {len(materialized.eol_block)} pinned copies, so "
                  "every checkout keeps their bytes (#471); none of its own "
                  "lines was changed")

        follow_ups = _plan_follow_ups(plan)
        message = _split_message(names, paths_for, leg_commits, spec_path,
                                 code_path, follow_ups,
                                 materialized.collisions, seeded,
                                 appended=materialized.eol_block)
        _stage_the_split(assembly, materialized)
        env_commit(assembly, message)
        split_commit = git_out(["rev-parse", "HEAD"], cwd=assembly).lower()
        step = "pushing the split branch"
        run(["git", "push", "-q", urls["assembly"],
             f"HEAD:refs/heads/{branch}"], cwd=assembly)
    except LATE_FAILURES as exc:
        _report_late(step, exc, _nothing_rolled_back(
            urls, list(leg_commits), work_root, names, source=source))
        return None
    except BaseException as exc:
        _report_late(step, exc, _nothing_rolled_back(
            urls, list(leg_commits), work_root, names,
            interrupted=_interrupted(exc), source=source))
        raise
    print(f"\n  split {split_commit[:12]} on {branch} -> {urls['assembly']}")
    return split_commit, message, materialized.collisions


def cmd_execute(args) -> int:
    plan = Plan.load(Path(args.plan))
    _refuse_a_mistyped_plan(plan)
    work_root = _work_root(args)
    # Before the source is opened, so before any leg exists (#524).
    _refuse_an_unwritable_work_dir(args, work_root)
    source = plan.open_source(args.source, work_root)
    naming = NamingPolicy.load(NAMING_POLICY)
    _require_filter_repo()

    names = plan.names()
    pins = set(plan.pins)
    _refuse_a_plan_for_another_repository(plan, source, names, naming, pins)
    _check_names(naming, names, pins, source)
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
    # What an earlier run left, the work directory first: a refusal below
    # whose way out is "run `execute` again" then meets one that is free.
    _refuse_an_occupied_work_dir(work_root, names, seeded)
    # The remote's own answer about the tracking branch, which `check` reads
    # only from what the source's clone remembers (#493's review, F1).
    _refuse_a_tracking_branch_the_remote_lacks(urls, tracking, local)
    _refuse_a_split_branch_left_behind(source, urls, branch, local)
    # Then a branch in git's way of the split branch, which no run of this
    # tool leaves behind (#320).
    _refuse_a_branch_in_the_split_branchs_way(
        plan, source, repositories, urls, branch, local,
        _extracts_a_leg(paths_for))
    for line in plan.seeding_record_disagreements(seeded):
        print(line)
    topic = naming.topic_for(plan.project_id)
    print(_topics_line(topic, local))
    _confirm(args, plan, names)

    # The substitution table is built BEFORE the legs, because a SEEDED leg is
    # rendered from `templates/<role>-root/` and needs it. The four leg
    # commit/digest values are the only ones that cannot be known yet; they
    # are filled in below, before the assembly root is materialized. And it
    # is built before the legs' REPOSITORIES too: it can refuse (a
    # checkout of this standard that is not a git repository), and a
    # refusal here used to leave both of them behind with nothing saying
    # so (#188). An `elected_on:` that is not a date no longer reaches it:
    # `_refuse_what_check_finds` has refused it above, as `check` finds it
    # (#294). It prints nothing.
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    values = _template_values(plan, names, repositories, urls, spec_path,
                              code_path, tracking, {}, {},
                              shape_commit, pins, naming)

    # ---- (a) the two legs' remotes ----------------------------------------
    _create_leg_remotes(plan, names, repositories, urls, tracking, local,
                        work_root, source=source)

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
    split_commit, message, collisions = split

    # THE TOPIC FIRST, THEN THE PULL REQUEST (#481). Neither needs the other,
    # and with the pull request first a refused one ended the run before the
    # topic was tried: three repositories without the topic `project.yaml`
    # claims, and a way out that named only `gh pr create`. Neither ends the
    # run here: the legs and the split ARE pushed, and what the person needs
    # to know before finishing either by hand is whether the split is right
    # (#304), so what is left is said once, after the table.
    unset: list[str] = []
    carried: list[str] = []
    refused: list[str] | None = None
    opened: str | None = None
    if not local:
        carried = _set_the_topic(repositories, topic)
        unset = [repositories[role] for role in TOPIC_ROLES
                 if repositories[role] not in carried]
        if _open_the_pull_request(repositories, names, tracking, branch,
                                  message):
            opened = repositories["assembly"]
        else:
            refused = _pull_request_command(repositories, names, tracking,
                                            branch, message)

    # ---- (d) verification, by blob sha ------------------------------------
    verified = _verify(source, assembly, work_root, names, paths_for,
                       split_commit, spec_path, code_path, seeded,
                       urls=urls, branch=branch)
    if not verified and refused is None:
        # Where the shape's Makefile and bootstrap script WENT, as the
        # materializer reports it, and not a second look at the tree (#480);
        # under `--local-remote-dir` no pull request is opened, so NEXT names
        # the split's branch, and the repository it is pushed to (#523).
        _next_steps(names, collisions,
                    (branch, urls["assembly"]) if local else None)
    _finish_by_hand(not verified, refused, topic, unset, opened=opened,
                    carried=carried)
    if verified:
        # A verification mismatch outranks a refused pull request and a
        # missing topic.
        return verified
    return 2 if refused or unset else 0


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
WRITTEN_PLAN_VALUES = {ELECTED_BY_KEY: ROOT_MANIFEST_AND_README,
                       ELECTED_ON_KEY: ROOT_MANIFEST_AND_README,
                       REFERENCE_KEY: ROOT_MANIFEST_AND_README,
                       VISIBILITY_KEY: ROOT_MANIFEST}

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
    by this tool (`private`, today's date) and is left out. The follow-ups
    are `_plan_follow_ups`', the items of text `_commit_the_split` writes; a
    `follow_ups:` that is not a list of text is `plan-bad-follow-ups` (#293),
    and is never iterated here."""
    fields = [(key, str(plan.get(key)), where)
              for key, where in WRITTEN_PLAN_VALUES.items()
              if plan.get(key) is not None]
    fields += [("a `pins:` item", pin, ROOT_MANIFEST) for pin in plan.pins]
    return fields + [("a `follow_ups:` item", item, SPLIT_MESSAGE)
                     for item in _plan_follow_ups(plan)]


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

    THE REMEDIATION MOVES THE SOURCE AND PLANS AGAIN: renaming the directory
    and running `plan` again adopts. A clone of it at a path that is text,
    passed to `execute` with --source, has the old path as its `origin`;
    `_remote_repository` read that as UTF-8 and raised until #292, and now
    reads it as no origin, so that route adopts too.
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


def _neutral_product_pins(pins) -> str:
    """`NEUTRAL_PRODUCT_PINS`, the manifest's list of the products the plan
    pins: `[]`, or one `  - <product>` line for each, sorted, each spelled so
    that the project's own reader reads it back as the text `plan` recorded
    (#514).

    WRITTEN BARE, `  - 007` WAS THE NUMBER 7. `plan` records the product
    quoted (`_pin_lines`), so `check` and `execute` read the text `007`,
    write `contracts/007-pin.yaml` and say `adoption verified`. The root's
    own reader then took the manifest's bare `007` for 7, and `2026` and
    `1.5` for numbers, and its `validate-pins.py` refused the entry as
    `neutral-pin-entry-malformed`, so the project's first CI run was red.

    EACH ENTRY IS SPELLED AS `y` SPELLS THE PLAN'S `product:`. Of the names
    `--pin` takes, `y` writes bare only one that begins with a letter, `_`
    or `.` and that the reader reads back as the same text, after `key: `
    and as a `- ` item alike (#181), so `openGlass` is the line it always
    was, `007` is `"007"`, and `true` and `null` are `"true"` and `"null"`.
    The reader is asked once more of the entry as this list holds it, as
    `family.py` asks it of a member's id (#259), rather than a list of its
    words, and an entry it would not read back as the same text is
    double-quoted all the same. Such a name reaches here from `plan` as
    well as from a plan edited by hand: `plan` records it quoted, and
    `check` passes it. The list is a block placeholder, so `render` writes
    it as it stands, and nothing else quotes it.
    """
    if not pins:
        return "[]"
    return "\n" + "\n".join(f"  - {_neutral_pin_entry(product)}"
                            for product in sorted(pins))


def _neutral_pin_entry(product: str) -> str:
    """One `neutral_product_pins:` entry: `y`'s spelling of `product` where
    the project's reader reads it back as `product`, and `product`
    double-quoted where it does not."""
    spelled = y(product)
    try:
        if parse_yaml(f"neutral_product_pins:\n  - {spelled}\n") \
                == {"neutral_product_pins": [product]}:
            return spelled
    except YamlError:
        # A spelling the reader refuses is not read back as anything.
        pass
    return double_quoted(product)


def _template_values(plan: Plan, names, repositories, urls, spec_path,
                     code_path, tracking, leg_commits, leg_digests,
                     shape_commit, pins, naming) -> dict[str, str]:
    """The substitution table the new project's files are WRITTEN from: the
    standard's real `shape_commit` and the digest of its tree, read here.
    `execute` is the one caller. A table to ask a question about and not to
    write is `_template_table`'s, which reads neither (`_manifest_values`)."""
    return _template_table(plan, names, repositories, urls, spec_path,
                           code_path, tracking, leg_commits, leg_digests,
                           shape_commit, tree_digest(SHAPE_ROOT, shape_commit),
                           pins, naming)


def _template_table(plan: Plan, names, repositories, urls, spec_path,
                    code_path, tracking, leg_commits, leg_digests,
                    shape_commit, shape_digest, pins, naming
                    ) -> dict[str, str]:
    """The substitution table, from the plan and the commit and digest it is
    handed, running nothing: no `git`, no `gh`."""
    project = names["assembly"]
    project_id = plan.project_id
    elected_on = str(plan.get(ELECTED_ON_KEY, _dt.date.today().isoformat()))
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
        "REFERENCE": str(plan.get(REFERENCE_KEY)
                         or default_reference(elected_on)),
        "ELECTED_BY": str(plan.get(ELECTED_BY_KEY, "")),
        "ELECTED_ON": elected_on,
        "TRACKING_BRANCH": tracking,
        "SPEC_PATH": spec_path,
        "CODE_PATH": code_path,
        "ASSEMBLY_REPOSITORY": repositories["assembly"],
        "SPEC_REPOSITORY": repositories["spec"],
        "CODE_REPOSITORY": repositories["code"],
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": shape_digest,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
        "CLONE_URL": urls["assembly"],
        "ASSEMBLY_CLONE_URL": urls["assembly"],
        "SPEC_COMMIT": leg_commits.get("spec", ""),
        "CODE_COMMIT": leg_commits.get("code", ""),
        "SPEC_TREE_SHA256": leg_digests.get("spec", ""),
        "CODE_TREE_SHA256": leg_digests.get("code", ""),
        "NEUTRAL_PRODUCT_PINS": _neutral_product_pins(pins),
        "ASSEMBLY_NAMING": naming_block(naming, names["assembly"], "assembly",
                                        pins),
        "SPEC_NAMING": naming_block(naming, names["spec"], "spec", pins),
        "CODE_NAMING": naming_block(naming, names["code"], "code", pins),
    }


def _split_message(names, paths_for, leg_commits, spec_path, code_path,
                   follow_ups, collisions, seeded=(), *, appended=()) -> str:
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
    if appended:
        # The one source file the split writes into (#471): said with every
        # line it added, so nobody has to diff the file to see what changed.
        lines += ["", f"APPENDED TO {ATTRIBUTES}, after this repository's own "
                  "lines, which are unchanged (each pinned copy outside "
                  f"{COLLISION_DIR}/ checks out with LF, as the pin records "
                  "it):"]
        lines += [f"  {eol_line(path)}" for path in appended]
    if follow_ups:
        lines += ["", "FOLLOW-UPS, which this commit does NOT do:"]
        lines += [f"  - {item}" for item in follow_ups]
    return "\n".join(lines) + "\n"


def _verify(source: Source, assembly: Path, work_root: Path, names,
            paths_for, split_commit: str, spec_path: str, code_path: str,
            seeded=(), *, urls: dict, branch: str) -> int:
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

    A FAILED VERIFICATION IS THE LAST LATE FAILURE, and gets the same report
    (#188 N1): stdout flushed before the findings, which used to head a
    merged log, above even `creating the leg repositories`; then the notice,
    and the split branch, which this run DID push. Its exit used to be a
    re-run into fresh legs alone, which created and pushed two more legs and
    then met that branch at the split push; now the branch is named with the
    command that deletes it, and the work directory with the rest.

    SO IS A VERIFICATION THAT CANNOT BE MADE (#188's review, N3): a `git`
    that will not list a tree, say. It reached `main` as `REFUSED
    git-failed`, with the validators' remediation about pins and no word of
    the two pushed legs, the work directory or the branch. It is reported
    as every late failure is, with the same notice and branch, and exits 2,
    a question that could not be asked; anything else, such as Ctrl-C, gets
    the same report and is re-raised.
    """
    step = "verifying the split"
    try:
        findings = _accounted_for(
            source, assembly, work_root, names, paths_for, split_commit,
            dict(zip((spec_path, code_path), EXTRACTED_LEGS)), seeded)
    except LATE_FAILURES as exc:
        _report_late(step, exc, _left_by_the_split(source, urls, names,
                                                   work_root, branch))
        return 2
    except BaseException as exc:
        _report_late(step, exc, _left_by_the_split(
            source, urls, names, work_root, branch,
            interrupted=_interrupted(exc)))
        raise
    if findings:
        _flush_stdout()   # the table above, and every leg line, is stdout's
        print("\n".join(findings), file=sys.stderr)
        print(f"\n{len(findings)} verification finding(s). NOTHING was "
              "deleted from the source, so the exit is to fix the plan and "
              "re-run, unless a finding above names another exit.\n"
              + _left_by_the_split(source, urls, names, work_root, branch),
              file=sys.stderr)
        return 1
    print("\nadoption verified: every source path is in exactly one place")
    return 0


def _accounted_for(source: Source, assembly: Path, work_root: Path, names,
                   paths_for, split_commit: str, mounts: dict,
                   seeded) -> list[str]:
    """`_verify`'s accounting: print the table, and return every finding.

    `mounts` maps each leg's mount path, as the plan spells it, to the leg
    (`_land_the_root_tree`). Split out of `_verify` so that a failure to
    account at all is reported where the notice and the branch are known.
    """
    print("\nVERIFICATION — every source path at "
          f"{source.commit[:12]}, by blob sha")
    before = {path: oid for path, _, oid, _ in source.tree()}
    after: dict[str, list[str]] = {}
    for role in ("spec", "code"):
        for path, _, oid, _ in _tree_of(work_root / names[role], "HEAD"):
            after.setdefault(path, []).append(f"{role}:{oid}")
    split_tree = _tree_of(assembly, split_commit)
    root_findings = _land_the_root_tree(after, split_tree, before, mounts)
    root_findings += _mount_commit_findings(
        split_tree, mounts, _pushed_commits(work_root, names))
    block = _land_the_eol_block(assembly, split_commit, split_tree, before,
                                after)

    counts, findings = _account_for(before, after, paths_for["drop"])
    findings += _shape_file_findings(assembly, split_commit)
    added = sorted(set(after) - set(before))
    for leg in ("spec", "code", "root", "drop"):
        note = " (seeded from template)" if leg in seeded else ""
        print(f"  {leg:<6} {counts[leg]:>5} of {len(before)} source "
              f"paths{note}")
    print(f"  added  {len(added):>5} new paths (manifest, pins, shape files"
          + (", seeded leg" if seeded else "") + ")")
    if block:
        print(f"  root   {ATTRIBUTES} is the source's own bytes, then the "
              f"shape's block of {block} `text eol=lf` lines (#471)")
    return findings + root_findings


def _land_the_eol_block(assembly: Path, split_commit: str, tree: list,
                        before: dict, after: dict) -> int:
    """Count the source's `.gitattributes` as landed in the root when the
    root holds its bytes followed by exactly the shape's block; return how
    many lines that block has, or 0 when there is none to count.

    THE ONE FILE THE SPLIT WRITES INTO (#471, ruled by Brett Heap at
    2026-10-12T22:48Z), so the one exception to "by blob sha": its blob in the
    root is not the source's, and without this it was `adopt-lost`. It is
    allowed exactly one shape, recomputed here rather than trusted from the
    run that wrote it: the source's bytes, untouched, then
    `shape_materialize.with_eol_block` over the pinned copies outside
    `shape/`, read out of the split's own pin. Anything else -- a source line
    changed, the block short of a copy or holding one too many -- leaves the
    source's blob in no place, and `_account_for` reports it as before.

    The pin is the shape's: under `shape/` when the source kept its own
    `contracts/shape-pin.yaml`, which nothing else can put there
    (`plan-root-blocks-shape-copy`). It is read THROUGH the split's symlinks
    (`_SplitTree`), as `_shape_file_findings` reads it: a source that keeps
    `contracts -> meta` in the root has the pin written through the link, and
    a lookup among the tree's plain files found none, so the appended file
    was `adopt-lost` where main verified it (#471's review, SHOULD-3). A pin
    neither can read counts nothing here, and `_shape_file_findings` reports
    it.
    """
    source_oid = before.get(ATTRIBUTES)
    landed = after.get(ATTRIBUTES, [])
    root = [where for where in landed if where.startswith("root:")]
    if source_oid is None or len(root) != 1 \
            or root[0] == f"root:{source_oid}":
        return 0
    blobs = {path: oid for path, mode, oid, _ in tree if mode in FILE_MODES}
    pin = _pin_through_links(_SplitTree(assembly, split_commit))
    pinned = _pinned_shape_paths(assembly, pin) if pin else None
    if pinned is None or blobs.get(ATTRIBUTES) != root[0].split(":", 1)[1]:
        return 0
    paths = eol_block_paths(pinned, COLLISION_DIR)
    expected = with_eol_block(_blob_bytes(assembly, source_oid), paths)
    if _blob_bytes(assembly, blobs[ATTRIBUTES]) != expected:
        return 0
    after[ATTRIBUTES] = [f"root:{source_oid}" if where == root[0] else where
                         for where in landed]
    return len(paths)


def _pin_through_links(tree: "_SplitTree") -> str | None:
    """The oid of the shape's pin in the split, under `shape/` first, each
    path followed through the tree's links; None when neither leads to a
    file."""
    for path in (f"{COLLISION_DIR}/{SHAPE_PIN}", SHAPE_PIN):
        try:
            return tree.blob_at(path)
        except _NotInTheSplitError:
            continue
    return None


def _blob_bytes(repo: Path, oid: str) -> bytes:
    return git_out([GIT_CAT_FILE, "blob", oid], cwd=repo, binary=True)


def _left_by_the_split(source: Source, urls: dict, names: dict,
                       work_root: Path, branch: str, *,
                       interrupted: bool = False) -> str:
    """What a run whose split is pushed leaves, and the way out: the notice,
    then the split branch with the command that deletes it, which a re-run
    meets as `adopt-branch-exists`. Said by `_verify` after its findings,
    and after a failure to verify at all. The assembly and the branch are
    `_spelled`, as the notice's paths are (#212)."""
    return (_nothing_rolled_back(urls, list(EXTRACTED_LEGS), work_root,
                                 names, interrupted=interrupted,
                                 source=source)
            + f"\nThe split is pushed to {_spelled(urls['assembly'])} too, "
            f"as {_spelled(branch)}, and a re-run is refused "
            "(`adopt-branch-exists`) until that branch is deleted:\n    "
            + _branch_deletion(source, urls, branch))


#: The shape file whose targets `make bootstrap` needs, as the materializer
#: names it in a collision (#480).
SHAPE_MAKEFILE = "Makefile"


def _next_steps(names: dict, collisions: list,
                split: tuple[str, str] | None = None) -> None:
    """What a person does once the split is verified AND its pull request is
    open, or none was tried. Not said after a refused `gh pr create`: there
    the command to open it is the next step (#304).

    `split` is `(branch, url)`, the split's branch and the repository it is
    pushed to, where no pull request was tried: under `--local-remote-dir`,
    where that repository is the source itself. NEXT said "review the pull
    request" there as well, over none (#523, N2), and named a clone of the
    default branch, where the split is not. There it names the split on its
    branch, and a clone of that branch from that repository, each value
    quoted for `sh` as `_branch_deletion` quotes it, so the line pastes as
    printed. The clone carries `FILE_PROTOCOL`: the split's `.gitmodules`
    names each leg by its plain path under `--local-remote-dir`, and git
    clones a submodule over the `file` transport only where it is told to,
    so without it both leg clones die `transport 'file' not allowed`, as
    pasting the line did in #582's review. Without `split`, the block is
    what it was, byte for byte.

    `collisions` is each `(intended, actual)` the materializer wrote beside a
    file the source kept: where the shape's files WENT, and not a second
    look at the tree. `make bootstrap` is a target of the SHAPE's Makefile. A
    source that kept its own `Makefile` in the root has the shape's beside
    it, at `shape/Makefile`, until a person merges the two as the follow-up
    says, and in that root `make bootstrap` exits 2, `No rule to make target
    'bootstrap'` (#480). So the command there is the one `make bootstrap`
    runs, `python3 scripts/bootstrap.py`, and a line says why.

    UNLESS THAT SCRIPT WENT ASIDE TOO (#493's review, F2). A root that kept
    its own `scripts/bootstrap.py` has the shape's at
    `shape/scripts/bootstrap.py`, and there both commands run the SOURCE's
    script, which can exit 0 having placed no leg and validated nothing. So
    no bootstrap command is named: a line says which merges come first, and
    that `make bootstrap` is run after them. Elsewhere the block is what it
    was, byte for byte."""
    aside = dict(collisions)
    script, makefile = aside.get(BOOTSTRAP), aside.get(SHAPE_MAKEFILE)
    bootstrap = ("" if script else
                 "\n    python3 scripts/bootstrap.py" if makefile else
                 "\n    make bootstrap")
    if split is None:
        review = f"the pull request on {names['assembly']}"
        clone = ("git clone --recurse-submodules "
                 f"<{names['assembly']} url>")
    else:
        branch, url = split
        review = (f"the split on its branch in {names['assembly']} (no pull "
                  "request is opened under --local-remote-dir)")
        clone = " ".join(["git", *FILE_PROTOCOL, "clone",
                          "--recurse-submodules", "-b", shlex.quote(branch),
                          shlex.quote(url)])
    print(f"\nNEXT: review {review}, then\n    {clone}{bootstrap}")
    if script:
        kept = [path for path in (SHAPE_MAKEFILE, BOOTSTRAP)
                if path in aside]
        print(f"NOTE the root keeps its own {_and_listed(kept)}, and the "
              f"shape's {'are' if len(kept) > 1 else 'is'} "
              f"{_and_listed([aside[path] for path in kept])}, so neither "
              f"`make bootstrap` nor `python3 {BOOTSTRAP}` runs the "
              "shape's bootstrap yet: merge "
              + _and_listed([f"{aside[path]} into {path}" for path in kept])
              + " first, and then run `make bootstrap`.")
    elif makefile:
        print(f"NOTE the root keeps its own {SHAPE_MAKEFILE} and the shape's "
              f"is {makefile}, so `make bootstrap` and the shape's other make "
              "targets arrive only once the follow-up merges the two; "
              "`python3 scripts/bootstrap.py` is what `make bootstrap` runs.")


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
#: one `_verify`'s footer and AGENTS.md give. It is pointed at, not repeated:
#: "re-run into fresh legs" alone left out the work directory and the split
#: branch, and followed as written it was refused, or made two more legs
#: (#188's review, F1). Anything else is this tool's defect, which no plan
#: answer and no hand edit of the split should paper over.
SHAPE_FILE_EXIT = (
    "If the plan kept in the root a file of the source's own at a shape "
    f"file's path -- its own {SHAPE_PIN} most often, the shape's then beside "
    f"it as {COLLISION_DIR}/{SHAPE_PIN} -- or a symlink on the way to one, "
    "send that path to a leg or `drop` it, and re-run as the end of this "
    "report says. Otherwise the split itself is wrong: do not merge it, and "
    f"report it to {SHAPE_REPOSITORY}")


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
                 pins: set[str], source: Source | None = None) -> None:
    """Each of the three names classifies in the naming policy, in its role.

    `source` is the source an in-place adoption keeps the name of, where it
    names a repository and `names` are made from its name (#499). The
    assembly root's name is then not the person's to retype: a refusal of it
    says that the source cannot be adopted in place under that name, and
    that renaming it comes first (`_rename_first`; at that path, where its
    `origin` is one, `_origin_path`), never that `--project` takes one
    CamelCase token. A leg's name is the plan's own to edit, and keeps the
    remediation it had.
    """
    for role, name in names.items():
        found = policy.classify(name, role, pins)
        renamed = (_rename_first(source.repository, path=_origin_path(source))
                   if role == "assembly" and source is not None
                   and source.repository is not None else None)
        if found is None:
            raise Refusal(
                "naming-unclassified",
                f"{name!r} matches no family in the naming policy",
                renamed or
                "Remediation: --project takes one CamelCase token with no "
                "hyphen, underscore, dot or space.")
        if not accepts_role(found, role):
            raise Refusal(
                "naming-role-mismatch",
                f"{name!r} classifies as {found.family}"
                + (f"/{found.role}" if found.role else "")
                + f", not as the {role!r} form of a project leg "
                f"({found.reason})",
                renamed or
                "Remediation: --project takes one CamelCase token. Two forms "
                "beyond the bare one MAY be the assembly root: a declared "
                "descendant (declare the pin with `--pin "
                "open<Product>@<40 hex commit>` and it classifies as one, "
                "2026-09-02), and an `open<Product>` "
                "neutral product, which may elect the shape and be its own "
                "root (2026-09-05). Neither may be the spec or code leg, and "
                "an `<X>-Install` may be no leg at all.")


# ---------------------------------------------------------------------------
# An in-place adoption keeps the source's own name (#499)
# ---------------------------------------------------------------------------
#
# `--project` names all three repositories (`_names`), and without
# `--local-remote-dir` `execute` acts on `https://github.com/<org>/<name>.git`
# for each (`_remote_urls`): the split branch it asks for and pushes, the pull
# request it opens and the topic it sets are the assembly root's, which in
# place IS the source. Nothing compared the two. `--help` said `--project` is
# the source's own name, and a source named `billing-service` was refused
# `naming-unclassified` with "--project takes one CamelCase token"; the
# `--project BillingService` that steered to planned and checked `plan ok`
# against `acme/billing-service`, and `execute` then ran `git ls-remote` on
# `acme/BillingService`: a raw failure where no such repository exists, and,
# where another one does, both legs made from it, the split pushed to it and
# its pull request opened there. A typo (`Atlsa` for `Atlas`) and an `--org`
# that is not the source's did the same. Under `--local-remote-dir` the split
# goes to the source's own path, so no test met it.
#
# RULED BY BRETT HEAP, 2026-10-13: "Casefold; rename first". Where the source
# names a repository -- its `origin` ends in an `org/repo`
# (`_remote_repository`), or `--source` is one -- `<org>/<project>` must be
# that repository, compared without case, because GitHub resolves `acme/atlas`
# and `acme/Atlas` to one. `plan` refuses another as `adopt-not-the-source`,
# naming both, before it writes anything. `check` finds, and `execute`
# refuses before it asks the naming policy or any remote, a plan whose `org:`
# names another with its `legs.assembly:`, which is what `execute` acts on, or
# with its `project:`, as `plan-not-the-source`: a hand edit is caught too,
# whatever `org:` then holds, because it is read as `execute` reads it
# (`_plan_org`). A source that names no repository (no `origin`, or one that
# ends in no `org/repo`) is asked nothing, as before.
#
# AN `origin` THAT IS A PATH NAMES ITS LAST TWO DIRECTORIES, as `plan` has
# read it for `--org` all along, and is compared like any other: a clone of
# `/srv/git/acme/Atlas.git` is `acme/Atlas`. A clone of `/srv/clones/Atlas.git`
# is then `clones/Atlas`, no repository on GitHub, so the remediation
# says where the name was read from (`_origin_path`) before it offers one,
# and never offers a directory's name as an organisation without saying so.
#
# AND A NAME THE POLICY REFUSES IS RENAMED FIRST, NOT RETYPED. Where the
# source's own name is one the naming policy refuses (`billing-service`), it
# cannot be adopted in place under that name, and no `--project` changes
# that: whether to rename the repository is a human's decision, made first on
# GitHub, or at the path an `origin` that is one names, and `plan` runs again
# after it. So these refusals say that, and `_check_names` says it in place of
# its hint to retype `--project`.

#: `plan`'s refusal of an `--org` and a `--project` that name another
#: repository than the source's (#499).
NOT_THE_SOURCE = "adopt-not-the-source"
#: `check`'s finding, and `execute`'s refusal, of a plan that does.
PLAN_NOT_THE_SOURCE = "plan-not-the-source"


def _is_the_source(repository: str, org: str, name: str) -> bool:
    """Whether `<org>/<name>` is `repository` as GitHub resolves a name:
    without case (#499)."""
    return f"{org}/{name}".casefold() == repository.casefold()


def _rename_first(repository: str, said: str = "",
                  path: str | None = None) -> str:
    """The remediation where the source's own name is one the naming policy
    refuses: it cannot be adopted in place under that name, and renaming it
    is a human's decision that comes first (#499). `said` is what the
    refusal says before that, a sentence or none. THE ONE TEXT of it.

    `path` is the source's `origin` where that is a filesystem path
    (`_origin_path`). The repository is then the one at that path, which
    names none on GitHub by itself, so it is renamed there, or the adoption
    is planned from a clone of the repository on GitHub instead: `gh repo
    rename` renames a repository on GitHub, and sending the person to it
    contradicted the sentence that a path names none there (#513's review,
    NIT-3)."""
    where = (
        "on GitHub (`gh repo rename`); then run `plan` again against the "
        "renamed repository (`--source <org>/<new name>`, or a clone whose "
        "`origin` names it)" if path is None else
        f"where it is kept, and its `origin` is the path {_spelled(path)}, "
        "not a repository on GitHub: rename the repository at that path, or "
        "plan instead from a clone of the repository on GitHub, whose "
        "`origin` names it there; then run `plan` again against the renamed "
        "repository")
    return (f"Remediation: {said}{_shown(repository)} cannot be adopted in "
            "place under that name: an in-place adoption keeps the source's "
            "own name, and `--project` cannot rename it. Whether to rename "
            f"it is a human's decision, made first {where}, with its new "
            "name as `--project`.")


def _origin_path(source: Source) -> str | None:
    """The source's `origin` where `source.repository` was read from it and
    it is a filesystem PATH (`remote_is_a_path`), not a url (#499): the
    repository is then its last two directories, which name no repository
    on GitHub by themselves, and an `--org` read from them may be none. None
    for an `org/repo` source, which names its repository itself."""
    if source.cloned or source.repository is None:
        return None
    url = _config_value(source.path, "remote.origin.url")
    return url if url is not None and remote_is_a_path(url) else None


def _own_name_remediation(source: Source, naming: NamingPolicy,
                          pins: set[str], done: str) -> str:
    """What `adopt-not-the-source` and `plan-not-the-source` say to do:
    `plan` again under the source's own name, or, where the naming policy
    refuses that name, `_rename_first`. `done` is what the refusing command
    left as it was, said first; then, where the name was read from a path
    (`_origin_path`), that it was, so that a directory's name is never
    offered as an organisation without saying where it came from."""
    repository = str(source.repository)
    org, _, name = repository.partition("/")
    path = _origin_path(source)
    if path is not None:
        done += (f"The source's repository, {_shown(repository)}, is read "
                 "from the last two directories of its `origin`, the path "
                 f"{_spelled(path)}, and names no repository on GitHub by "
                 "itself. ")
    try:
        _check_names(naming, _names(name), pins)
    except Refusal as exc:
        return _rename_first(repository, f"{done}The source's own name is no "
                             f"remedy either: {exc.detail}. ", path)
    return (f"Remediation: {done}Run `plan` again with `--project "
            f"{_shown(name)} --org {_shown(org)}`, the source's own name, "
            "which `plan` writes into the plan's `org:`, `project:` and "
            "`legs:`. Any other name is another repository; if "
            f"{_shown(repository)} is not the one to adopt, plan from a clone "
            "of the one that is, or with `--source <org>/<repo>`.")


def _refuse_another_repository(args, source: Source, naming: NamingPolicy,
                               pins: set[str]) -> None:
    """`plan` refuses an `--org` and a `--project` that name another
    repository than the one the source names, as `adopt-not-the-source`,
    before anything is written (#499). `args.org` is settled: given, or read
    from the source."""
    repository = source.repository
    if repository is None or _is_the_source(repository, args.org,
                                            args.project):
        return
    raise Refusal(
        NOT_THE_SOURCE,
        f"--org {args.org} and --project {args.project} name "
        f"{args.org}/{args.project}, and the source is {_shown(repository)}: "
        "an in-place adoption keeps the source's own name, and `execute` "
        "pushes the split to the repository they name, opens its pull "
        "request there and sets its topic on it",
        _own_name_remediation(source, naming, pins, "no plan was written. "))


def _not_the_source(plan: Plan, source: Source,
                    names: dict[str, str]) -> str | None:
    """`plan-not-the-source`'s detail, or None: the plan's `org:` with its
    `legs.assembly:` (`names`, read by `Plan.names`) or with its `project:`
    names another repository than the one the source names (#499).

    `org:` is read as `execute` reads it (`_plan_org`), whatever the file
    holds. While it was compared only when it was text, a number, a
    boolean, a null or a deleted `org:` line checked `plan ok`, and
    `execute` acted on `2026/Atlas`, `True/Atlas` or `None/Atlas` (#513's
    review, SHOULD-1). Where it is not text, the detail says what the file
    holds beside how `execute` spells it. `project:` is read only as text:
    a misread one is not this question's to answer, and `execute` acts on
    `legs.assembly:`."""
    repository = source.repository
    if repository is None:
        return None
    org, held = _plan_org(plan), plan.get("org")
    wrong = [(key, value) for key, value in
             (("legs.assembly", names["assembly"]),
              ("project", plan.get("project")))
             if isinstance(value, str)
             and not _is_the_source(repository, org, value)]
    if not wrong:
        return None
    said = (f"`org: {_shown(org)}`" if isinstance(held, str) else
            f"`org:` ({_read_as(held) if 'org' in plan.data else 'absent'}, "
            f"which `execute` spells {_shown(org)})")
    keys = " and ".join(f"`{key}: {_shown(value)}`" for key, value in wrong)
    named = _and_listed(sorted({f"{_shown(org)}/{_shown(value)}"
                                for _, value in wrong}))
    return (f"the plan's {said} with its {keys} names {named}, "
            f"and the source is {_shown(repository)}: an in-place adoption "
            "keeps the source's own name, and `execute` acts on the "
            "repository `org:` and `legs.assembly:` name")


def _refuse_a_plan_for_another_repository(
        plan: Plan, source: Source, names: dict[str, str],
        naming: NamingPolicy, pins: set[str]) -> None:
    """`execute` refuses `check`'s `plan-not-the-source` before it asks the
    naming policy about the plan's names or any remote anything (#499):
    what it would ask of GitHub it would ask of the repository the plan
    names, and a raw `git ls-remote` failure on that repository was the
    first thing it said."""
    detail = _not_the_source(plan, source, names)
    if detail:
        raise Refusal(
            PLAN_NOT_THE_SOURCE, f"{plan.path}: {detail}",
            _own_name_remediation(
                source, naming, pins,
                "no leg repository was created and nothing was pushed. "))


def _elector() -> str:
    """`git config user.name`, which `plan` records when `--elected-by` is
    not given; "" when it names nobody.

    A BYTE THAT IS NOT UTF-8 IS KEPT, AS `sys.argv` KEEPS ONE (#292). git
    keeps the name as the bytes it was given, and one saved in a legacy code
    page is no UTF-8. Read strictly, it ended `plan` in a `UnicodeDecodeError`
    traceback, exit 1, naming neither the setting nor `--elected-by`. Kept
    as a lone surrogate, it is asked what `_checked_plan_inputs` asks of
    every value `execute` writes (#255), and is refused there as
    `adopt-unwritable-value`, named as `git config user.name`, with
    `--elected-by` as the way past it, before any plan is written.
    """
    try:
        name = git_out([GIT_CONFIG, "user.name"], cwd=SHAPE_ROOT, binary=True)
    except Refusal:
        return ""
    return name.decode("utf-8", "surrogateescape").strip()


def _work_root(args) -> Path:
    root = (args.work_dir.resolve() if getattr(args, "work_dir", None)
            else Path(tempfile.mkdtemp(prefix="openreposhape-adopt-")))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _leg_path_help(leg: str, default: str) -> str:
    """`plan`'s `--help` for `--spec-path` and `--code-path` (#340): what the
    flag is, what the plan records it as, and the two refusals `plan` makes on
    it before it writes a plan, each by the code it prints. The two flags take
    the one rule, so it is said from one place: `leg` is the role and
    `default` the flag's default, which the examples of a spelling Git does
    not keep are written from.

    `tests/test_adopt_plan_leg_path_help.py` holds this to the tool: each
    clause below names the value `plan` refuses for it, and each value the
    help says is refused is. The spelling half is `leg_path_problem`'s, in the
    order it asks (`scripts/shape_materialize.py`): the spelling, then the
    names Git and Windows keep, then the alphabet `checked_value` allows (ASCII
    only, 255 characters, nothing that begins with `-`). The collision half is
    the scaffold's own sentence (#288) plus the half only an adoption has,
    `shape/`, where `execute` writes its copy of a file the root already
    holds. A mount over a source path the plan KEEPS in the root is not said
    here, because `plan` refuses nothing for it (`_kept_collision_notes`).

    THE LIST NEVER SAYS "ONLY". Each clause is a value `plan` refuses, and
    each refusal prints the whole rule under `Remediation:`, where the closing
    sentence sends the reader. A value the project's YAML reader would read
    back as something other than text (`null`, `2026`: #225) is in none of
    them: `plan` writes a plan for it, or refuses it under a clause or a code
    another change adds, and this text is true either way. So it says nothing
    of what `plan` ACCEPTS, because `plan` takes some values and does not
    mount them where they were given (before #181, `null` was mounted at
    the default).
    """
    return (
        f"where the {leg} leg is mounted, as a path in the assembly root "
        f"(default: {default}); the plan records it as `legs.{leg}_path`. "
        "`plan` refuses it, before it writes a plan, as `adopt-bad-leg-path` "
        "when the path is empty or `.`, is absolute, begins with `-` or is "
        "longer than 255 characters; has a `..` segment, a backslash, a "
        "segment that ends in a dot, or a character outside ASCII letters, "
        "digits and `._/@+~-`; is not in Git's own spelling "
        f"(`{default}/`, `./{default}` and `a//b` are not); has a segment "
        "Git or Windows reserves (`.git`, `CON`); or is, holds or lies "
        "inside the other leg's path, whatever the case. As "
        "`adopt-leg-path-collides` it refuses a path that is, holds or lies "
        "inside a FILE the shape writes into the root (`project.yaml` is "
        "one, and `contracts` holds several), or that is at or under "
        "`shape/`, whatever the case. The defaults `spec` and `code` pass. "
        "Either refusal writes no plan and rewrites nothing, and its "
        "`Remediation:` line states the whole rule; you pass the value "
        "again.")


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
    plan.add_argument("--elected-by", default=None,
                      help="the human electing the shape (default: `git "
                           "config user.name`); not blank")
    plan.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    plan.add_argument("--reference", default=None,
                      help="the document the election followed. Default: "
                           "openxFactory's ratified "
                           "docs/project-repo-schema.md for an election on or "
                           "after 2026-09-02, and the staged fragment it was "
                           "ratified from for one dated earlier — so "
                           "--elected-on chooses it.")
    plan.add_argument("--tracking-branch", default=None,
                      help="the branch the assembly root and both legs "
                           "track, and the base of the split's pull request "
                           "(default: the source's default branch, which the "
                           "plan records as `source.default_branch`). "
                           "`check` finds, and `execute` refuses before any "
                           "leg exists, one that is no branch of the source "
                           "(`plan-tracking-branch-missing`).")
    plan.add_argument("--spec-path", default="spec",
                      help=_leg_path_help("spec", "spec"))
    plan.add_argument("--code-path", default="code",
                      help=_leg_path_help("code", "code"))
    plan.add_argument("--pin", action="append", default=[],
                      metavar="openProduct@COMMIT",
                      help="declare a neutral-product pin, as "
                           "scaffold-project.py --pin does, e.g. --pin "
                           "openGlass@<40 hex>. `plan` reads the digest of "
                           "the product's tree at that commit (from "
                           "--pin-source, or `gh api`) and records it in the "
                           "plan; `execute` writes "
                           "contracts/<openproduct>-pin.yaml from it and "
                           "lists the product in the manifest. A name with "
                           "no @<commit>, a product named spec, code or "
                           "shape, and one product twice are refused. "
                           "Repeatable.")
    plan.add_argument("--pin-owner", default=NEUTRAL_PRODUCT_OWNER,
                      help="the organisation an UNQUALIFIED --pin name "
                           "resolves under (default: "
                           f"{NEUTRAL_PRODUCT_OWNER}, where every neutral "
                           "open<Product> lives — never the adopted "
                           "repository's own --org). Name the owner in --pin "
                           "itself (owner/openProduct@<sha>) to override it "
                           "for one pin.")
    plan.add_argument("--pin-source", type=Path, default=None,
                      help="a local clone to compute --pin digests from, "
                           "instead of reading the forge with `gh api` (the "
                           "TEST path; no network)")
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
    # Stdout may still hold what ran before a refusal or a failed command
    # that reaches these handlers -- the plan's lines, the topic line -- so it
    # is flushed first, and a merged log keeps the order (#188). One a step
    # has already reported, with the notice of what it left
    # (`_create_leg_remotes` on its second leg), is not printed again: it
    # only sets the exit.
    try:
        return args.func(args)
    except Refusal as exc:
        _flush_stdout()
        if not _reported(exc):
            print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        _flush_stdout()
        if not _reported(exc):
            print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        # A step that reported one has printed it as REFUSED, with what it
        # left, so it exits as a refusal does; any other is still a defect,
        # and keeps its traceback.
        if not _reported(exc):
            raise
        return 2


if __name__ == "__main__":
    sys.exit(main())
