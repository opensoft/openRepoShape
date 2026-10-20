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
           `execute` refuses a plan edited to name another repository than
           the source names, or, where it names none, than the plan
           recorded for it (`plan-not-the-source`, #716): in place, the
           source IS the assembly root, and its own name is renamed first,
           on GitHub, never retyped (#499). An `origin` that is a url names
           the `org/repo` it ends in, with or without a trailing `/`; one
           that is a path, in any separator, names none, and `plan` says it
           compared nothing (#521). An organisation read from the url and
           refused is named by where it came from (#427).
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
           relative url naming the same repository from the leg -- its
           GitHub remote, or, given `--local-remote-dir`, the bare
           repository `execute --local-remote-dir` would create there
           (#417) -- as from the source, and each url a leg keeps that
           names a place on this machine's disk one where `git ls-remote`
           reaches a repository (a url on a network is never asked, and a
           NOTE says so) (#418), no
           symlink kept in the root that the shape would write
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
           rechecked for (#449). Last, it asks what `execute` asks before
           it makes either leg (#798): given `--local-remote-dir`, whether
           each leg's bare repository is already there and whether that
           directory can be made and written in, and without it, with `gh
           repo view --json nameWithOwner`, whether GitHub already has
           either leg's name, where a name GitHub only redirects (a
           repository renamed or moved away) is free -- a NOTE and no
           finding where gh cannot answer, so that `check` stays usable
           offline. Before that, it asks what `execute` asks of the three
           names, the organisation and the topic (#863): a name the disk
           cannot hold, and without `--local-remote-dir` a name, an
           `org:` or a topic GitHub will not take, each a finding under
           `execute`'s code; after a name or an `org:` found there, whose
           fix renames both legs, the legs are not asked about, and after
           a topic they are. It prints what will happen and changes
           nothing.
  execute  asks about both legs before it makes either (#798), then
           creates the two legs, extracts them with `git filter-repo`, makes
           the one split commit on a branch of the source, sets the
           `xf-project-<id>` topic on all three and then opens the split's
           pull request against the tracking branch (both skipped for local
           remotes), and then VERIFIES by blob sha that every source path
           landed in exactly one place, and that the root's only submodules
           are the two leg mounts, each at the commit pushed to its leg. The
           split's `project.yaml` records the leg each source submodule kept
           in a leg was answered into, under `submodules:`, for
           `shape-doctor.py` to check it against, and under
           `answered_paths:` the leg each entry covering a path the policy
           asked about, or put in another leg, was answered into, so the
           doctor neither asks it again nor calls it misplaced.

THE PLAN IS AN ARTIFACT A HUMAN OR AN AI EDITS. That is why it is YAML with
reasons in it rather than a pipe between two processes: the classifier is
right about `openspec/` and cannot be right about `examples/golden-run/`
without knowing whether the specification cites it. `execute` REFUSES while
any `leg:` is still null, and on every other finding `check` reports, before
it has created a leg repository or pushed anything -- a source submodule's
relative url resolved again from the leg remotes it is about to create, which
under `--local-remote-dir` are the bare repositories `check` resolves from
only when it is given the same `--local-remote-dir` (#417), and asked there
whether it answers, and
the place outside the assembly that a symlink kept at a path the shape writes
leads to asked again of the disk, a climb from its own work directory.
And last, before it makes either leg, it refuses at once everything that
stands in their way (#798), as `check` finds it: a leg repository already
there, on the disk or on GitHub, a `--local-remote-dir` that cannot hold
them, and a `gh repo view` that fails otherwise than gh's not-found answer
or answers with no `nameWithOwner` to read.

THE NEW PROJECT MUST BE ABLE TO HOLD WHAT `execute` WRITES INTO IT (#261).
`execute` puts the plan's values into the root's `project.yaml`, and the
project's own `scripts/validate-manifest.py` judges them at its first
bootstrap. So `plan` refuses, `check` finds and `execute` refuses a value that
validator would refuse -- a blank `elected_by` or `reference`, an `elected_on`
that is not `YYYY-MM-DD`, an organisation name it cannot hold, a `visibility`
other than `private`, `public` or `internal` -- asking the validator itself,
loaded from the template it ships, and not a copy of its rules. A name that
cannot be a directory's (a `--project` that makes a repository name of 256
bytes with its `.git`) is refused the same way. Without `--local-remote-dir`
`execute` also refuses, before either leg exists, what GitHub will not take
(#838): a leg's name over GitHub's 100 characters (`adopt-name-too-long`), an
`org:` over the 39 it keeps an organisation's name to (`adopt-org-too-long`),
and an id whose `xf-project-<id>` topic is over its 50
(`adopt-topic-too-long`), which `gh repo edit --add-topic` refused only once
both legs and the split were pushed; and an `org:` holding a character GitHub
gives no organisation (`.`), ending in a hyphen or holding two in a row
(`adopt-bad-org`, #863). `check` finds each of these, the disk's included,
under the same code: `execute` passed what `check` had called `plan ok`
(#863). Both read one list, `_what_cannot_be_held`. Its first question is
the one the scaffold asks of its `--project` (#989): an assembly root no
Windows disk can make a folder of (`NUL`, `Con`, `com1`, `Lpt9`), which
`plan` refuses as `--project` before anything exists, and `check` and
`execute` find in `legs.assembly` (`adopt-bad-project-name`, #1014).

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
it, and the verification table's `code` row reads `0 of N source paths (seeded
from template)`. `check` WARNS; `execute` refuses without `--allow-empty-leg
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
import errno
import itertools
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from path_classify import PathPolicy, Verdict  # noqa: E402
from repo_shape import (  # noqa: E402
    REMEDIATION,
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, YamlError,
    accepts_role, checked_value, double_quoted, git_out, load_yaml,
    parse_yaml, redacted, remote_is_a_path, remote_key, remote_local_path,
    shown_path, spelled as spelled_as_git_out, tree_digest,
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
# The copies the shape pins, in the pin's order, and which paths a
# `.gitattributes` line can name literally: asked of a `.gitattributes` the
# plan keeps below the root, over a pinned copy (#530).
from shape_materialize import (  # noqa: E402
    COPIED_FROM_SHAPE, COPIED_VERBATIM, EOL_PATH_RE,
)
# What the project's own `validate-manifest.py` would say of the values written
# into its manifest, and whether a repository's name can be a directory's:
# asked of the plan's values by `plan`, `check` and `execute` (#261).
from shape_materialize import (  # noqa: E402
    KIND_NOT_A_MAPPING, PROJECT_MANIFEST, manifest_judged,
    manifest_value_problems, refuse_manifest_values, refuse_unstorable_names,
)
# What GitHub keeps a repository's name, a topic and an organisation's name
# to, asked by `execute` before either leg exists where GitHub is (#838).
from shape_materialize import (  # noqa: E402
    GITHUB_ID_MAX, GITHUB_LIMITS, GITHUB_NAME_MAX, GITHUB_OWNER_MAX,
    GITHUB_PROJECT_MAX, GITHUB_TOPIC_MAX, refuse_a_topic_github_cannot_set,
    refuse_an_owner_github_cannot_have,
)
# And the characters GitHub gives an organisation's name (#863).
from shape_materialize import refuse_an_owner_github_cannot_spell  # noqa: E402
# Whether a Windows disk can make a folder of a name (#1014): the one question
# the scaffold asks of its `--project` and `family.py init` of `--family`.
from shape_materialize import refuse_an_unholdable_name  # noqa: E402
# Whether a value this tool writes into a file is text a file can hold
# (#255), asked beside `one_printable_line`, the trailer's question.
from shape_materialize import unwritable_reason  # noqa: E402
# Whether git creates a tracking branch as it is written (#283), asked of one
# the project's loader misreads (`_a_branch_git_creates`, #181), of `plan`'s
# `--tracking-branch`, and of both branch names a plan gives `execute`
# (`_branch_name_refusal`, #420, #520). `BRANCH_REMEDIATION` is the remedy
# it gives a name git judged, worded for a flag.
from shape_materialize import (  # noqa: E402
    BRANCH_REMEDIATION, branch_problem, refuse_bad_branch,
)
# The shape's bootstrap script, which its `make bootstrap` runs: where it
# went beside one the source kept decides what NEXT can name (#480).
from shape_materialize import BOOTSTRAP  # noqa: E402
# `run`'s own check of a command line, for the one command `run` cannot run:
# `_git_rm`, whose path goes to git as the bytes the tree holds (#527).
from shape_materialize import check_program  # noqa: E402
# How a `gh repo view --json visibility` answer is read, and what the
# Free-plan secrets note says of the root, as the scaffold and `family.py`
# say it of theirs (#660).
from shape_materialize import (  # noqa: E402
    free_plan_secrets_note, visibility_in,
)
# What `execute` asks of both leg repositories before it makes either, and
# `check` with it (#798): the folder `--local-remote-dir` names, asked as the
# scaffold and `family.py` ask theirs, and gh's not-found answer, the one
# failure of `gh repo view` that means a repository is absent (#609); the
# other is an answer naming another repository, a redirect.
from shape_materialize import (  # noqa: E402
    CANNOT_WRITE_IN, GH_NOT_FOUND_WORDS, folder_in_the_way,
)

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
#: after `plan` read them (#449). So the plan, a file on this machine that
#: nothing commits, records where that clone is, `local-clone (<path>)`
#: (`_as_planned`); the pin file `execute` commits says only how the digest
#: was read, `local-clone` or `gh-api-tree-recursive`, and never where
#: (`_recorded_pins`, #540). The commit `plan` records is the one the id
#: names: an annotated tag's own id is peeled, and any other id that names
#: no commit refused, and `check` asks the same clone that question
#: (`commit_in_clone`, #651).
from shape_materialize import (  # noqa: E402
    DIGEST_FROM_CLONE, DIGEST_FROM_GH, PIN_ARG_RE, commit_in_clone,
    declared_pin_products, declared_pin_values, neutral_pin_path,
    one_printable_line, pin_collisions, pin_digest_from_source,
    pin_source_path, pin_variable_collisions, refuse_an_unread_pin_source,
    refuse_colliding_pins,
)
#: How `plan`'s refusals of a `--pin-source` begin their remediation.
PLAN_NOT_WRITTEN = "no plan was written."
from repo_shape import SHA256_RE, repo_basename  # noqa: E402
# Whether a recorded `--pin-source` is a clone's top level, asked as `plan`
# asks it (#800).
from shape_materialize import pin_source_not_top_level  # noqa: E402
# One reading of an `origin`, shared with `shape-doctor.py` (#521).
from repo_shape import origin_is_a_path, url_repository  # noqa: E402
# The one spelling of a `neutral_product_pins:` entry, which
# `scaffold-project.py` calls too, and the plain scalar it and `y` write a
# text bare by (#924).
from shape_materialize import (  # noqa: E402
    PLAIN_SCALAR_RE, neutral_pin_entry as _neutral_pin_entry,
)

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
#: otherwise, or cannot answer for at all, at the plan's commit (#449), or
#: holds as something other than a commit (#651).
PIN_DIGEST_MISMATCH = "plan-pin-digest-mismatch"
PIN_SOURCE_UNREADABLE = "plan-pin-source-unreadable"
PIN_NOT_A_COMMIT = "plan-pin-not-a-commit"
#: And about a clone `plan` read a digest from that is no clone's top level,
#: which `plan` now refuses as `pin-source-not-a-clone` (#800).
PIN_SOURCE_NOT_A_CLONE = "plan-pin-source-not-a-clone"
#: How `plan` records where it read a digest (`_as_planned`): from a clone on
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


#: What a finding about a `pins:` mapping says `execute` writes the pin
#: file from, and nothing else; and what one says that names the entry's
#: `digest_source:`, which the pin file says too, as `local-clone` or
#: `gh-api-tree-recursive` (`_digest_source_written`, #901).
PIN_WRITTEN_FROM = "the commit and the digest `plan` records"
PIN_WRITTEN_FROM_AND_HOW = f"{PIN_WRITTEN_FROM}, and how it was read"


def _pin_written_from(keys) -> str:
    """What a finding about the `pins:` keys `keys` says `execute` writes
    the pin file from: `PIN_WRITTEN_FROM_AND_HOW` where one of them is
    `digest_source:`, and `PIN_WRITTEN_FROM` otherwise. A finding about
    the digest's source ended "from the commit and the digest `plan`
    records, and nothing else", though `execute` writes the field it is
    about into the pin file as well (#901)."""
    return (PIN_WRITTEN_FROM_AND_HOW if "digest_source" in keys
            else PIN_WRITTEN_FROM)


def _pin_row_problem(row: dict) -> tuple[str, str, str] | None:
    """`(code, why, written_from)` for a `pins:` mapping `execute` cannot
    write a pin file from, or None. `why` finishes a sentence about the
    entry, and `written_from` says what `execute` writes the pin file from
    (`_pin_written_from`), for the sentence after it.

    Each value is held to what `plan` writes there: the commit to
    `COMMIT_RE`, the repository and the commit together to the scaffold's own
    `PIN_ARG_RE`, owner-qualified, with the product its name, the digest to
    `SHA256_RE`, and the digest's source to `_a_digest_source`.

    THE DIGEST'S SOURCE IS ONE OF THREE SPELLINGS (#540). It was held to one
    printable line, and `execute` wrote it into the root's pin file as it
    stood, so `plan`'s `local-clone (<the --pin-source path>)` committed the
    directory a clone sat in on the machine that planned, and a hand edit
    could commit any line at all. The plan still records the path, because
    `check` recomputes the digest in that clone (#449), but the field is
    now held to a closed set, and `execute` writes the pin file's from it
    (`_digest_source_written`): `gh-api-tree-recursive` as it is, and
    `local-clone` for both `local-clone` and `local-clone (<path>)`. So no
    value of the plan's reaches the committed file but those two words, and
    any other is `plan-pin-malformed`, with the `plan` that records the pin
    whole."""
    missing = [key for key, _ in PIN_FIELDS if row.get(key) in (None, "")]
    unrecorded = [key for key in PIN_RECORDED if key in missing]
    if unrecorded or missing:
        named = unrecorded or missing
        return ((PIN_UNRECORDED if unrecorded else PIN_MALFORMED),
                "records no " + " and no ".join(f"`{key}:`" for key in named),
                _pin_written_from(named))
    not_text = [key for key, _ in PIN_FIELDS
                if not isinstance(row.get(key), str)]
    if not_text:
        why = "records " + ", ".join(
            f"`{key}: {row[key]!r}`" for key in not_text) + ", which " + (
            "is" if len(not_text) == 1 else "are") + " not text"
        return PIN_MALFORMED, why, _pin_written_from(not_text)
    product, repository, commit, digest, how = (
        row[key] for key, _ in PIN_FIELDS)
    if not COMMIT_RE.match(commit):
        return PIN_MALFORMED, (
            f"records `commit: {commit!r}`, which is not 40 hex: a tag, a "
            "branch or an abbreviated oid can be moved, and a commit cannot"
        ), PIN_WRITTEN_FROM
    if not (PIN_ARG_RE.match(f"{repository}@{commit}") and "/" in repository
            and repo_basename(repository) == product):
        return PIN_MALFORMED, (
            f"records `product: {product!r}` and `repository: "
            f"{repository!r}`, and `plan` records the repository as "
            "`<owner>/<openProduct>`, its name the product's"
        ), PIN_WRITTEN_FROM
    if not SHA256_RE.match(digest):
        return PIN_MALFORMED, (
            f"records `tree_sha256: {digest!r}`, which is not 64 hex"
        ), PIN_WRITTEN_FROM
    if not _a_digest_source(how):
        return PIN_MALFORMED, (
            f"records `digest_source: {how!r}`, and `plan` records "
            f"`{DIGEST_FROM_GH}`, or `{DIGEST_FROM_CLONE} (<the clone's "
            "path>)` on one printable line, and nothing else"
        ), PIN_WRITTEN_FROM_AND_HOW
    return None


def _a_digest_source(how: str) -> bool:
    """Whether a pin's `digest_source:` is one `check` passes (#540): one
    of the two words the pin file says, `gh-api-tree-recursive` and
    `local-clone`, or `local-clone (<path>)` as `LOCAL_CLONE_RE` reads it,
    the clone `check` recomputes the digest in (#449).

    THE PATH IS HELD TO ONE PRINTABLE LINE, as the whole field was before
    #540, and as `plan` holds `--pin-source` before it records it
    (`_refuse_an_unrecordable_pin_source`). `LOCAL_CLONE_RE` takes any
    character but a line break, a NUL among them, and the plan's reader
    makes one of the escape `\\x00`; `Path.stat` raises `ValueError` on
    such a path, where `_why_not_rechecked` waits for an `OSError`."""
    if how in (DIGEST_FROM_CLONE, DIGEST_FROM_GH):
        return True
    return (LOCAL_CLONE_RE.fullmatch(how) is not None
            and one_printable_line(how))


def _digest_source_written(how: str) -> str:
    """What the pin file `execute` commits says for a `digest_source:`
    `check` passed (`_a_digest_source`): how the digest was read, and never
    where (#540). `check`'s `write` line and `plan`'s `pin` line say the
    same, so neither prints a clone's path as what is written."""
    return DIGEST_FROM_CLONE if LOCAL_CLONE_RE.fullmatch(how) else how


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
    `plan-pin-malformed`. A `pins:` that is no list is said as `_read_as`
    says what the plan's reader read, as each other key a plan is opened by
    is (`_plan_key_findings`, #901): `pins: true` is the boolean true, and
    not Python's `True`."""
    rows = plan.get("pins")
    if rows is None:
        return [], []
    if not isinstance(rows, list):
        return [], [f"FINDING {PIN_MALFORMED}: `pins:` is {_read_as(rows)}, "
                    f"not a list of pins: {_pin_fix()}."]
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
            code, why, written_from = problem
            findings.append(
                f"FINDING {code}: {said} {why}. `execute` writes the pin file "
                f"from {written_from}, and nothing else: "
                f"{_pin_fix(row.get('repository') or product)}.")
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
    `declared_pin_values` hands it the scaffold's: the digest's source as
    the pin file says it, `local-clone` and no clone's path
    (`_digest_source_written`, #540). Read only after `execute` has refused
    every finding `_read_pins` makes. `check`'s `write` line prints these
    values, so it says what is written."""
    return {product: {**values, "PIN_DIGEST_SOURCE": _digest_source_written(
                values["PIN_DIGEST_SOURCE"])}
            for _, product, values in _read_pins(plan)[0]}


def _pin_files(plan: "Plan") -> list[tuple[str, str | None]]:
    """`(path, product)` for each pin file `execute` writes, in the order
    `place` writes them: each declared pin's, then the shape's own pin,
    whose product is None (#524).

    EACH PATH ONCE (#651, L1-06 of #457). Two declared pins at one file,
    `openGlass` and `OpenGlass`, or one whose file is the shape's own pin,
    a product named `Shape`, are `plan-pin-collides`; a path the root keeps
    there was named by `plan-root-holds-pin` once for each pin, two lines
    for one file. The file is the first pin's, and the shape's own where it
    is the shape's pin, which `execute` writes there whatever is declared."""
    files: dict[str, str | None] = {}
    for product in _declared_pins(plan):
        files.setdefault(neutral_pin_path(product), product)
    files.pop(SHAPE_PIN, None)
    return [*files.items(), (SHAPE_PIN, None)]


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
# commit it lacks, a file -- is `plan-pin-source-unreadable`, as
# `validate-pins.py` finds a source it reads that cannot answer. `check` and
# `execute` ask this through `_entry_findings`, the one list.
#
# A DIRECTORY THAT IS NO CLONE'S TOP LEVEL is asked about FIRST (#800), before
# a partial clone's NOTE: a folder inside a clone, or a directory that is no
# clone at all, is `plan-pin-source-not-a-clone`, as `plan` refuses it
# `pin-source-not-a-clone`. In a folder `git ls-tree` lists only what is
# under it, so the digest recomputed there was the wrong one `plan` read,
# and `check` said it recomputes; inside a partial clone it said only that
# it was not asked. The question reads no object, so it reads no network.

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
            ["git", GIT_CONFIG, "--local", "--get-regexp",
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
    recompute there, with `plan`'s own reader; None where it recomputes.

    THE COMMIT IS ASKED FIRST, as `plan` asks it (#651): a recorded id the
    clone holds as an annotated tag, a tree or a blob is
    `plan-pin-not-a-commit`. A tag's digest recomputes, because `git
    ls-tree` peels it, so a plan whose `commit:` was a tag's id, written by
    a `plan` from before #651 or edited in, checked ok and `execute` wrote
    that id under the pin file's `revision_kind: commit`."""
    clone = _recorded_clone(values["PIN_DIGEST_SOURCE"])
    repository, commit, recorded = (values["PIN_REPOSITORY"],
                                    values["PIN_COMMIT"],
                                    values["PIN_TREE_SHA256"])
    named, why = commit_in_clone(Path(clone), commit)
    if why or named != commit:
        return (f"FINDING {PIN_NOT_A_COMMIT}: {said} records `commit: "
                f"{commit}`, which "
                f"{why or f'is an annotated tag of commit {named}'} in the "
                f"clone `plan` read its digest from, {_shown(clone)}"
                f"{_read_from_here(clone)}, not a commit. The pin file "
                "`execute` writes from it says `revision_kind: commit`, and "
                "`plan` records the commit an annotated tag names and "
                f"refuses an id that names none: {_pin_fix(repository)}.")
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


def _not_a_top_level_finding(said: str, how: str,
                             repository: str) -> str | None:
    """The FINDING for a pin whose `digest_source:` names a directory that is
    no clone's top level (#800), asked as `plan` asks a `--pin-source`
    (`pin_source_not_top_level`); None for a top level, and for a path that
    is no directory or that cannot be entered, which the questions after
    this one name as they always did."""
    clone = _recorded_clone(how)
    try:
        found = (pin_source_not_top_level(Path(clone))
                 if clone is not None and Path(clone).is_dir() else None)
    except OSError:
        return None
    if found is None:
        return None
    why, top = found
    fix = (f"re-run `plan` with `--pin-source {_shown(str(top))}`, its top "
           "level" if top is not None else _pin_fix(repository))
    return (f"FINDING {PIN_SOURCE_NOT_A_CLONE}: {said} records that `plan` "
            f"read its digest from {_shown(clone)}{_read_from_here(clone)}, "
            f"which is not a clone's top level: {why}. `plan` refuses such a "
            f"--pin-source as `pin-source-not-a-clone`: {fix}.")


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
        found = _not_a_top_level_finding(said, how, values["PIN_REPOSITORY"])
        why = None if found else _why_not_rechecked(how)
        if not (found or why):
            found = _recomputed_pin_finding(said, values)
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

#: In install.sh's order (#595): with the pipx or uv already there, else
#: brew's, else pipx from apt or dnf, else Arch's own package. No `pip
#: install --user`: Debian 12, Ubuntu 23.04 and Arch mark their own Python
#: externally managed (PEP 668) and refuse it. The openreposhape package
#: depends on git-filter-repo and puts it on PATH for the `adopt-project` it
#: places, but not for this file run by its path (#563).
FILTER_REPO_HINT = (
    "Remediation: install it — `pipx install git-filter-repo==2.47.0`, or "
    "`uv tool install git-filter-repo==2.47.0` where there is no pipx; with "
    "neither, `brew install git-filter-repo`, or `sudo apt-get install -y "
    "pipx && pipx install git-filter-repo==2.47.0 && pipx ensurepath` (`dnf` "
    "for `apt-get` on Fedora), or `sudo pacman -S --needed git-filter-repo` "
    "on Arch; it is one file on PATH named `git-filter-repo`. `pipx install "
    "openreposhape` brings it for the `adopt-project` command it places. It "
    "is NOT vendored here on purpose: history extraction has one correct "
    "implementation and a copy of it is a second one that drifts."
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

#: `shape_materialize`'s plain scalar since #924, the rule `neutral_pin_entry`
#: writes a pin's product bare by, so the manifest's `neutral_product_pins:`
#: entry is bare only where `y` writes the plan's `product:` bare. It ends
#: at `\Z`, not `$` (#199).
_PLAIN_RE = PLAIN_SCALAR_RE


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
#: a symlink's target and the shape pin. With `--batch`, it prints the
#: target of every symlink of the source whose blob is not empty, in one
#: pass (#388).
GIT_CAT_FILE = "cat-file"


def _git_path(raw: bytes) -> str:
    """A path git printed under `-z`, as `Source.tree()` spells it: UTF-8,
    and a byte that is not UTF-8 kept as a surrogate rather than refused. A
    gitlink and its `.gitmodules` registration are compared as strings, so
    both are decoded here."""
    return raw.decode("utf-8", "surrogateescape")


def _path_argument(path: str) -> str | bytes:
    """A path `_git_path` decoded, as `subprocess` must be handed it for git
    to receive the bytes the tree holds, under any locale (#527).

    BYTES ON POSIX: `_git_path` undone, UTF-8 with `surrogateescape`, so the
    NFC and the NFD spelling of a name stay two paths, and a byte that is
    not UTF-8 is that byte again. Handed a `str`, `subprocess` encodes it
    with the filesystem encoding, which is the locale's codec when Python is
    not in UTF-8 mode: under `LC_ALL=C PYTHONUTF8=0` that is ASCII, and
    `git rm` of `caf\\u00e9.md` raised `UnicodeEncodeError` after both legs
    were pushed. A `bytes` argument reaches the command line as it is.

    TEXT ON WINDOWS, as before. `subprocess` hands `CreateProcessW` the
    command line as UTF-16, which no locale codec touches, and git for
    Windows turns it into the UTF-8 its index holds. Python would turn a
    `bytes` argument back into text there first, with `os.fsdecode`
    (`subprocess.list2cmdline`), which raises on a byte that is not UTF-8.

    ONLY FOR A PATH READ FROM GIT, or text spelled as one (`_run_exact`). A
    path read from the disk -- `Path`, `os.readlink`, `Path.resolve` -- is
    text `os.fsdecode` made, and the `os.fsencode` that `subprocess` applies
    to it gives back the same bytes in any locale, so `_stage_the_split`
    hands git such paths as they are.
    """
    return path if os.name == "nt" else path.encode("utf-8", "surrogateescape")


def _git_spelling(path: str) -> str:
    """`path`, text `os.fsdecode` made of a path on the disk, spelled as
    `_git_path` spells a path git printed: the same bytes, so that
    `_path_argument` hands git the bytes the disk holds (#653).

    Where a path from the disk meets a url git printed -- the base
    `_resolved` resolves a relative submodule url against, and the working
    tree git's relative answer is joined to -- both must reach git spelled
    one way. Under a UTF-8 locale the two spellings are one, and under
    `LC_ALL=C PYTHONUTF8=0` `os.fsdecode` keeps each byte outside ASCII as
    the surrogate `_path_argument` writes back as that byte; but under a
    locale of one byte per character, Latin-1 say, it reads the two bytes
    of `\\u00e9` as two characters, which `_path_argument` would write as
    four. Text on Windows, which `_path_argument` leaves as it is.
    """
    return path if os.name == "nt" else _git_path(os.fsencode(path))


def _the_locale_hands_it_alike(argument: str) -> bool:
    """Whether `subprocess`, encoding `argument` with the locale's codec,
    hands the program the bytes `_path_argument` makes of it: under every
    UTF-8 locale, and for text that is all ASCII under any."""
    try:
        return os.fsencode(argument) == _path_argument(argument)
    except UnicodeEncodeError:
        return False


def _run_exact(command: list[str], cwd: Path | None = None) -> str:
    """`run(command, cwd)`, with each argument handed to `git` or `gh` as
    the UTF-8 bytes it spells, under any locale (#653).

    `run` hands `subprocess` text, which it encodes with the locale's codec
    when Python is not in UTF-8 mode: under `LC_ALL=C PYTHONUTF8=0` that is
    ASCII, so the em dash in `gh repo create --description` raised
    `UnicodeEncodeError` before any leg existed, for every source, and so
    did a url `_resolved` handed `git config` with a character outside
    ASCII. Every argument here is text git and gh read as UTF-8: a path or
    url git printed, a path `_git_spelling` spelled, or text this tool
    wrote. NEVER a path `os.fsdecode` made, which `run` hands git exactly.

    `run` ITSELF WHEREVER THE LOCALE HANDS EVERY ARGUMENT ALIKE, which is
    every run under a UTF-8 locale: nothing there changes, a stand-in for
    `run` included. Elsewhere `subprocess` is handed `_path_argument` of
    each argument, and the rest is `run`'s: only `git` and `gh`
    (`check_program`, asked of the command as the person reads it), what
    the program printed back as text, stripped, and a refusal raised as
    `CommandFailed` naming that command.
    """
    if os.name == "nt" or all(map(_the_locale_hands_it_alike, command)):
        # As each caller called `run` before: no `cwd` where it gave none.
        return run(command) if cwd is None else run(command, cwd=cwd)
    check_program(command)
    proc = subprocess.run([_path_argument(argument) for argument in command],
                          cwd=str(cwd) if cwd else None, capture_output=True,
                          check=False)
    if proc.returncode != 0:
        raise CommandFailed(command, cwd, proc.returncode,
                            (proc.stderr + proc.stdout).decode("utf-8",
                                                               "replace"))
    return proc.stdout.decode("utf-8", "replace").strip()


def _git_out_exact(args: list[str], cwd: Path) -> str:
    """`git_out(args, cwd)`, with each argument handed to git as the UTF-8
    bytes it spells, under any locale (#653): what `_run_exact` is to `run`.

    `git_out` is `scripts/repo_shape.py`'s, a shape copy every project
    pins, and it hands git text: `Source.open`'s `git rev-parse` of a
    default branch named `caf\\u00e9` raised `UnicodeEncodeError` under
    `LC_ALL=C PYTHONUTF8=0`, and `plan`, `check` and `execute` died before
    anything was said of the branch. So `git_out` itself wherever the locale
    hands every argument alike, and elsewhere git is run here, and a git
    that refuses is refused as `git_out` refuses it: `git-failed`, naming
    the command as the person reads it.

    THE REFUSAL IS `git_out`'S, WORD FOR WORD, AND MUST STAY IN STEP WITH
    IT: the folder named with `shown_path` and what git printed `spelled`
    as one line (#610). Raw, a folder named with a line break began a line
    the tool never printed, under the C locale alone. A change to
    `git_out`'s words is a change here too, and
    `tests/test_adopt_c_locale_bytes.py` compares the two.
    """
    if os.name == "nt" or all(map(_the_locale_hands_it_alike, args)):
        return git_out(args, cwd=cwd)
    proc = subprocess.run(["git", *map(_path_argument, args)], cwd=str(cwd),
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise Refusal("git-failed", "`git {}` in {} exited {}: {}".format(
            " ".join(args), shown_path(cwd), proc.returncode,
            spelled_as_git_out(
                proc.stderr.decode("utf-8", "replace").strip())))
    return proc.stdout.decode("utf-8").strip()


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
    could not be read has not been shown to hold no gitlink. Its two
    untrusted parts are spelled as `git_out` spells them (#900): the source
    folder with `shown_path`, and what git printed `spelled`, as one line.
    Raw, a folder named with a line break began a line the tool never
    printed and an ESC in its name reached the terminal, and git, which
    echoes the folder (`invalid gitfile format: <folder>/.git`), passes a
    line break and a C1 control through.
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
                    " ".join(command[1:]), shown_path(source.path),
                    log.returncode, spelled_as_git_out(
                        said.read().decode("utf-8", "replace").strip())))
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


# ---------------------------------------------------------------------------
# Whether something is at a path, or the system would not say (#430)
# ---------------------------------------------------------------------------

#: The `OSError`s that `Path.is_file()` and `Path.is_dir()` answered False to
#: on Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name to open: no such file, a part of the path that is
#: not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". Every other one was raised.
#: `scripts/bump-leg.py`'s set (#383), and the one every copy is held to.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)


def _absent(exc: OSError) -> bool:
    """Whether `exc`, from a `stat`, means nothing is at the name
    (`_ABSENT_ERRNOS`, `_ABSENT_WINERRORS`), and not that the operating
    system would not say (#430)."""
    return (exc.errno in _ABSENT_ERRNOS
            or getattr(exc, "winerror", None) in _ABSENT_WINERRORS)


def _is_a(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `stat.S_ISDIR`),
    raising the `OSError` of a `stat` the operating system REFUSED (#430),
    as `scripts/bump-leg.py`'s `_is_a` asks it (#383).

    NOT `Path.exists()`, `is_file()` OR `is_dir()`, whose answer depends on
    the Python. Up to 3.13 they raised a refused `stat` (`PermissionError`)
    and answered False only when nothing was there; from 3.14 they call
    `os.path.exists` and the like, which answer False to ANY `OSError`. So a
    `--source` under a directory this user cannot search ended `plan` in a
    traceback on 3.12, and on 3.14 was "neither a path that exists nor an
    `org/repo`", or, spelled `org/repo`, was cloned from GitHub; and a plan's
    recorded clone there "no longer exists" and was cloned again. Asked
    here, every Python answers as 3.9 to 3.13 did, and the caller names a
    refused `stat`. A name the operating system cannot take at all (a NUL
    in it) is nothing there, as `exists()` answered it.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if _absent(exc):
            return False
        raise
    except ValueError:
        # a name the operating system cannot take at all (a NUL in it)
        return False
    return kind(mode)


def _is_there(path: Path) -> bool:
    """Whether anything is at `path`, following a symlink as `Path.exists()`
    does, asked as `_is_a` asks it: the `OSError` of a refused `stat` is
    raised, never read as nothing there (#430)."""
    return _is_a(path, lambda _mode: True)


def _os_reason(exc: OSError) -> str:
    """The operating system's own words for `exc` (`Permission denied`), or
    the exception's name where it gave none, as `validate-pins.py`'s
    `_cannot_read` words them."""
    return exc.strerror or type(exc).__name__


# ---------------------------------------------------------------------------
# What a `--source` names, and where its clone goes (#652)
# ---------------------------------------------------------------------------

#: Where `Source.clone` clones a repository, in the work directory.
SOURCE_READONLY = "source-readonly"
#: The one host `gh repo clone` is asked to clone from.
GITHUB_HOST = "github.com"
#: The refusal of a `--source` that is both a path here and a GitHub name.
SOURCE_AMBIGUOUS = "source-ambiguous"
#: The refusal of a plan's `source.local_path` that is gone, or no longer a
#: whole clone, where nothing clones it again, or that names no path; and
#: its way out.
PLAN_SOURCE_GONE = "plan-source-gone"
PLAN_SOURCE_GONE_REMEDY = (
    "Remediation: pass the source again with --source: the path its clone is "
    "at now; or, where `plan` cloned it from GitHub, the `org/repo` it "
    "cloned, which clones it again. Either is held to the plan's `commit:`.")
#: The refusal of a `--source` that names nothing, as `Source.open` words it.
SOURCE_UNRESOLVABLE = "source-unresolvable"
#: The refusal of a local source that is no repository's top-level
#: directory: a file, or a directory inside a repository (#796).
SOURCE_NOT_TOP_LEVEL = "source-not-top-level"
#: The refusal of a `--source`, or a plan's `source.local_path`, whose path
#: this user cannot reach: its `stat` refused for another reason than that
#: nothing is there (#430). Never read as a path that is not there.
SOURCE_UNREADABLE = "source-unreadable"
#: What `source-unreadable` says to do, by the cause: a permission is put
#: right by the mode or the owner, in `validate-pins.py`'s words for a
#: directory (`_unreadable_file`), and no `chmod` puts right any other
#: reason the operating system gave (an I/O error, a name too long).
SOURCE_UNREADABLE_PERMISSION = (
    "Make it readable by this user: `chmod u+rx` on the directory and on "
    "every directory above it, or fix who owns them. ")
SOURCE_UNREADABLE_OTHER = (
    "The operating system gave another reason than permission, which no "
    "`chmod` puts right: put right what it names. ")
#: What `source-not-top-level` says a source is, and its way out, for a
#: `--source` and a plan's `source.local_path` alike.
TOP_LEVEL_ONLY = "a source is the top-level directory of a repository"
TOP_LEVEL_REMEDY = (
    "Remediation: pass --source the repository's top-level directory, which "
    "`git rev-parse --show-toplevel` prints in any directory of it, or its "
    "`org/repo`.")
#: GitHub's host as a browser's address bar spells it, read as
#: `GITHUB_HOST` (#796): on main it was refused as another host.
WWW_GITHUB_HOST = f"www.{GITHUB_HOST}"
#: One segment of a GitHub `owner/repo` as `gh` reads it. `.` and `..` match
#: it and are refused apart, so the clone directory is always one name.
GITHUB_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]+")
#: A `--source` written as a path, whatever is there: from the root, a home
#: directory, the current directory or its parent, or a Windows share.
PATH_SPELLING_RE = re.compile(r"[/~]|\.{1,2}(?:[/\\]|$)|\\\\")
#: A `--source` written as a URL that names a repository on a host: a scheme
#: and its host, git's `user@host:` form, or `github.com/` with no scheme,
#: which `gh` itself reads as `HOST/OWNER/REPO`, or `www.github.com/` (#796).
#: `path` is the rest.
SOURCE_URL_RE = re.compile(
    r"(?:(?:https?|ssh|git)://(?:[^@/]+@)?(?P<host>[^/:@]+)(?::\d*)?/"
    r"|[^@/:]+@(?P<scp>[^/:]+):"
    r"|(?P<bare>(?:www\.)?github\.com)/)(?P<path>.*)",
    re.IGNORECASE | re.DOTALL)


def _github_name(written: str) -> str | None:
    """The `owner/repo` that `written` names, or None where it names none.

    A SPELLING IS NORMALISED FIRST (#652): any trailing `/` and an empty
    segment are dropped, as `Path` drops them, and one trailing `.git`, as
    `url_repository` drops it from a url (#521). On main `acme/Atlas/` was
    cloned into `source-readonly/` itself, its last segment being empty, and
    `acme//Atlas`, `acme/Atlas.git` and a url were each handed to `gh` as
    typed and refused after the clone, or before it with a remedy about `gh
    auth status`. Two segments must be left, each one `gh` takes, neither
    `.` nor `..`, and the owner beginning with neither `.`, which no
    GitHub owner does, nor `-`, which gh's parser reads as an option: `-u/x`
    set its `--upstream-remote-name` (S8705). Case is kept as typed.

    NOR IS THE REPOSITORY `.git` (#796), in any case, as `owner/.git`,
    `owner/.GIT` and `owner/.git.git` leave it: on main `gh` was handed
    `owner/.git`, to clone into `source-readonly/.git`, and refused it
    `source-unclonable`, with a remedy about `gh auth status`. GitHub reads
    a repository's name without regard to case, and so does a disk that
    ignores case, where `source-readonly/.GIT` is `source-readonly/.git`;
    so the trailing `.git` is dropped in any case too."""
    segments = [part for part in written.split("/") if part]
    if len(segments) != 2:
        return None
    owner, repo = segments
    if repo.lower().endswith(".git") and len(repo) > len(".git"):
        repo = repo[:-len(".git")]
    if owner.startswith(("-", ".")) or repo.lower() == ".git" or not all(
            GITHUB_SEGMENT_RE.fullmatch(part) and part not in (".", "..")
            for part in (owner, repo)):
        return None
    return f"{owner}/{repo}"


def _ambiguous(spec: str, name: str) -> Refusal:
    """`source-ambiguous`: `spec` is a path here and names `name` on GitHub."""
    here = "./" + spec.rstrip("/")
    return Refusal(
        SOURCE_AMBIGUOUS,
        f"--source {spec!r} names both the path {_spelled(here)} here and the "
        f"GitHub repository `{name}`",
        f"Remediation: pass {_spelled(here)}, or its absolute path, to read "
        f"that directory in place; or `https://{GITHUB_HOST}/{name}` to "
        "clone the repository from GitHub.")


def _source_unreadable(named: str, exc: OSError, untold: str,
                       instead: str = "") -> Refusal:
    """`source-unreadable` (#430): `named` (`--source '<it>'`, or the plan's
    `source.local_path`) is a path whose `stat` the operating system refused
    for another reason than that nothing is there, `<named>: cannot be read
    (<reason>)`, as `validate-pins.py`'s `_cannot_read` words it; `untold` is
    what that leaves unknown, which is not guessed. The way out follows the
    cause (`SOURCE_UNREADABLE_PERMISSION`, `SOURCE_UNREADABLE_OTHER`), and
    `instead`, another way to name the source, ends it."""
    advice = (SOURCE_UNREADABLE_PERMISSION if isinstance(exc, PermissionError)
              else SOURCE_UNREADABLE_OTHER)
    return Refusal(
        SOURCE_UNREADABLE,
        f"{named}: cannot be read ({_os_reason(exc)}), so {untold} cannot be "
        "told",
        "Remediation: a path this user cannot reach is never read as one "
        "that is not there, and nothing was cloned. " + advice
        + "Then run the same command again"
        + (f"; or {instead}." if instead else "."))


def _source_there(spec: str, candidate: Path, name: str | None) -> bool:
    """Whether anything is at `candidate`, the path `--source spec` names
    here, asked as `_is_a` asks it; `name` is the GitHub repository the
    same spelling names, or None (#430).

    A REFUSED `stat` IS `source-unreadable`, NEVER "NOT THERE". On Python
    3.9 to 3.13 `Path.exists()` raised it out of `plan`, `check` and
    `execute`, a `PermissionError` traceback; on 3.14 it answered False, so
    a path under a directory this user cannot search was "neither a path
    that exists nor an `org/repo`", and a spelling that is also a name
    (`acme/Atlas` beside an unsearchable `./acme`) was cloned from GitHub,
    where `source-ambiguous` refuses it once the path can be seen. Which of
    the two it names cannot be told, so neither is read, and the url is
    offered for the repository, as `source-ambiguous` offers it."""
    try:
        return _is_there(candidate)
    except OSError as exc:
        if name is None:
            raise _source_unreadable(f"--source {spec!r}", exc,
                                     "whether a repository is there") from exc
        here = _spelled("./" + spec.rstrip("/"))
        raise _source_unreadable(
            f"--source {spec!r}", exc,
            f"whether it names the path {here} here, or only the GitHub "
            f"repository `{name}`,",
            f"pass `https://{GITHUB_HOST}/{name}` to clone the repository "
            "from GitHub") from exc


def _repository_in_url(spec: str, url: re.Match, candidate: Path) -> str:
    """The `owner/repo` a url `--source` names (`SOURCE_URL_RE`'s `url`):
    refused where its host is not GitHub's, where it names no `owner/repo`,
    and, for `github.com/<owner>/<repo>` written with no scheme, where it is
    a path here as well (`candidate`), as `_source_spec` refuses a name.
    `www.github.com` is GitHub's host, as a browser spells it (#796)."""
    host = (url["host"] or url["scp"] or url["bare"]).lower()
    if host == WWW_GITHUB_HOST:
        host = GITHUB_HOST
    name = _github_name(url["path"])
    if host != GITHUB_HOST:
        raise Refusal(
            SOURCE_UNRESOLVABLE,
            f"--source {spec!r} names a repository on {host}, and `gh repo "
            f"clone` clones from {GITHUB_HOST} alone",
            "Remediation: clone it yourself and pass the clone's path.")
    if name is None:
        raise Refusal(
            SOURCE_UNRESOLVABLE,
            f"--source {spec!r} names no `owner/repo` on {GITHUB_HOST}",
            "Remediation: pass a local clone's path, or `org/repo`.")
    if url["bare"] and _source_there(spec, candidate, name):
        raise _ambiguous(spec, name)
    return name


def _source_spec(spec: str) -> tuple[Path | None, str | None]:
    """What a `--source` names: `(path, None)`, a path read in place, or
    `(None, "owner/repo")`, a GitHub repository `Source.clone` clones.

    WHICH IT IS IS DECIDED BY ITS SPELLING FIRST, AND NEVER BY WHAT IS HERE
    ALONE (#652). On main a path that existed won: with `./acme/Atlas` in
    the current directory, `plan --source acme/Atlas` planned that
    directory, cloned nothing and exited 0, and the plan then recorded the
    `origin`'s name as the repository. So, in order:
    - a path by its spelling (`/`, `~`, `./`, `../`, a drive or a share) is
      read in place, or refused below where it is not there;
    - a url, or `github.com/<owner>/<repo>`, names a repository on GitHub,
      and a url on another host is refused: `gh repo clone` asks GitHub;
    - a name `_github_name` reads as `owner/repo` is cloned, unless it is
      ALSO a path here, which is refused as `source-ambiguous`, naming both
      spellings: guessing either reads a repository nobody named;
    - anything else is a path, read in place where it exists.
    Whether a path is there is asked of the disk by `_source_there`, which
    refuses a `stat` the operating system refused for another reason than
    that nothing is there as `source-unreadable` (#430): a path this user
    cannot reach is neither "a path that does not exist" nor proof that a
    name is only GitHub's.

    A DRIVE-LETTER PATH IS A PATH THAT IS NOT THERE, never an `org/repo`.
    `D:/work/Thing` carries a `/` and would otherwise be handed to `gh repo
    clone` as an owner named `D:`; `os.path.isabs` cannot be asked instead,
    because it answers False for that string on Linux and macOS and this
    refusal must read the same on every platform. NOR IS A NAME THAT IS NOT
    TEXT (#255), which `_github_name` never reads as one, NOR ONE THAT BEGINS
    WITH `-`, the first argument `gh repo clone` is given, which gh's own
    parser reads as an option. A one-segment name (`Atlas`) is a path, as on
    main, where it never reached `gh`.

    A PATH IS A REPOSITORY'S TOP-LEVEL DIRECTORY, OR IT IS REFUSED (#796),
    by name and before git reads anything else in it: the path is given
    back resolved by `_top_level`. On main a file ended `plan`, `check` and
    `execute` in a `NotADirectoryError` traceback, and a directory inside a
    repository, or `.` run in one, was planned, exit 0, holding only what
    is under it. An EMPTY value names no path, and is refused as
    `pin-source-no-path` refuses an empty `--pin-source`: as a `Path` it is
    `.`, so `--source "$SRC"` with `SRC` unset planned the directory it ran
    in. A `~user` is expanded as `os.path.expanduser` expands it, which
    leaves one this machine has not as typed, a path that is not there:
    `Path.expanduser` raised `RuntimeError` for one mistyped user name,
    which bash passes through unchanged."""
    if not spec:
        raise Refusal(
            SOURCE_UNRESOLVABLE,
            "--source '' names no path: an empty one would be read as the "
            "directory this runs in",
            "Remediation: pass the repository's top-level directory (`.` for "
            "this directory), or its `org/repo`. Without --source, `check` "
            "and `execute` read the plan's own source.")
    candidate = Path(os.path.expanduser(spec))
    written_as_a_path = bool(PATH_SPELLING_RE.match(spec)
                             or WINDOWS_ABSOLUTE_RE.match(spec))
    url = None if written_as_a_path else SOURCE_URL_RE.fullmatch(spec)
    if url is not None:
        return None, _repository_in_url(spec, url, candidate)
    name = (None if written_as_a_path or "\\" in spec
            else _github_name(spec))
    if _source_there(spec, candidate, name):
        if name is not None:
            raise _ambiguous(spec, name)
        return _top_level(candidate, f"--source {spec!r}"), None
    if name is None:
        raise Refusal(
            SOURCE_UNRESOLVABLE,
            f"--source {spec!r} is neither a path that exists nor an "
            "`org/repo` name",
            "Remediation: pass a local clone's path, or `org/repo`.")
    return None, name


def _top_level(path: Path, named: str) -> Path:
    """`path`, a local source that exists, resolved, where it is the
    top-level directory of a repository; refused as `source-not-top-level`
    where it is not a directory, or is a directory inside a repository
    (#796). `named` is how the refusal names it: `--source '<it>'`, or the
    plan's `source.local_path`, which `Plan._recorded_source` reads.

    BEFORE GIT READS ANYTHING ELSE IN IT. A file is asked of the disk, and
    git is never run in it: `subprocess` raised `NotADirectoryError` for
    one, a traceback. A directory is asked `git rev-parse
    --is-inside-git-dir` first: a git directory itself (`<repo>/.git`, a
    bare repository, `.git/modules/<m>`, `.git/worktrees/<w>`) is read
    whole, as on main, and a directory below one (`.git/objects`, a bare
    repository's `refs/`) is refused, naming the git directory `git
    rev-parse --absolute-git-dir` gives. On main `plan` planned the whole
    repository from `.git/objects`, exit 0, and recorded that directory,
    which `check` then refused at `git ls-remote` of it, and `execute` as
    `adopt-remote-unreadable`. Then `git rev-parse --show-prefix`, which
    prints nothing at the top level, of a work tree or a git directory, and
    the path of the directory below it otherwise; only then is
    `--show-toplevel` asked, for the refusal to name. A directory git reads
    no repository from is refused `git-failed` here, in git's own words, as
    a later read refused it on main. On main a directory inside a
    repository was read as the source: `git ls-tree` there lists what is
    under it alone, so `plan` planned that, exit 0, and the plan recorded
    it."""
    resolved = Path(os.path.realpath(path))
    if not resolved.is_dir():
        raise Refusal(SOURCE_NOT_TOP_LEVEL,
                      f"{named} is not a directory, and {TOP_LEVEL_ONLY}",
                      TOP_LEVEL_REMEDY)
    if git_out(["rev-parse", "--is-inside-git-dir"], cwd=resolved) == "true":
        git_dir = os.fsdecode(git_out(["rev-parse", "--absolute-git-dir"],
                                      cwd=resolved, binary=True).rstrip(b"\n"))
        if Path(os.path.realpath(git_dir)) != resolved:
            raise Refusal(
                SOURCE_NOT_TOP_LEVEL,
                f"{named} is inside the git directory {_spelled(git_dir)}, "
                f"and {TOP_LEVEL_ONLY}", TOP_LEVEL_REMEDY)
    prefix = os.fsdecode(git_out(["rev-parse", "--show-prefix"],
                                 cwd=resolved, binary=True).rstrip(b"\n"))
    if prefix:
        top = os.fsdecode(git_out(["rev-parse", "--show-toplevel"],
                                  cwd=resolved, binary=True).rstrip(b"\n"))
        raise Refusal(
            SOURCE_NOT_TOP_LEVEL,
            f"{named} is {_spelled(prefix)} inside the repository at "
            f"{_spelled(top)}, and {TOP_LEVEL_ONLY}: read from there, it "
            f"would be only what is under {_spelled(prefix)}",
            TOP_LEVEL_REMEDY)
    return resolved


def _occupied_clone_target(work_root: Path, path: Path, repository: str,
                           taken: str = "", done: str = "") -> Refusal:
    """`adopt-work-dir-occupied` for a clone target `path` that already
    holds something (#652). `taken` is said first where it is the plan's own
    clone, no longer whole, and the way out then begins with deleting it.
    `done` is `execute`'s word that nothing exists yet (`NO_LEG_YET`), said
    first in the way out as its other early refusals say it; `execute` keeps
    the clone it makes, so the way out says that too."""
    held = path.relative_to(work_root).as_posix()
    # An empty directory is refused too, since #803: the run that made it
    # may be cloning into it now (#457's L1-98).
    empty = "" if _holds_something(path) else "an empty directory, "
    why = ("a run clones only into a directory it has just made, so that it "
           "never takes another run's for its own" if empty else
           "`git clone` clones only into a directory that is new or empty")
    detail = (f"--work-dir {_spelled(str(work_root))} already holds "
              f"{_spelled(held)}, {empty}where this run clones {repository}, "
              f"and {why}")
    remedy = f"Pass {ANOTHER_WORK_DIR}"
    if empty:
        remedy += (f" Or, where no run is using {_spelled(held)}, delete it: "
                   "a run that was killed can leave it empty.")
    if taken:
        detail = f"{taken}; and {detail}"
        remedy = (f"It is no longer a whole clone: delete {_spelled(held)} "
                  "and run the command again, which clones it there anew; "
                  f"or pass {ANOTHER_WORK_DIR}")
    if done:
        remedy += (" An earlier `execute` given this --work-dir keeps the "
                   "clone it made there: where that is what it holds, delete "
                   "it once nothing in it is needed.")
    return Refusal("adopt-work-dir-occupied", detail,
                   f"Remediation: {done}{remedy}")


#: The refusal of a `--work-dir`, or of the `source-readonly/` in it, that
#: another user can rename or replace entries in (#803).
WORK_DIR_SHARED = "adopt-work-dir-shared"
#: The way out of a `--work-dir` that holds something in the clone's way.
ANOTHER_WORK_DIR = ("a --work-dir that does not hold it, or none: without "
                    "one, each run makes a new one.")
#: The way out of a `--work-dir` another user can rename entries in, or
#: rename it from a directory above it.
WORK_DIR_OWN = ("Pass a --work-dir this user owns, that no other user can "
                "write in, and that has no directory above it another user "
                "can rename in, or none: without one, each run makes a new "
                "one.")
#: How a refusal names a file it found where it looked (#803: one spelling
#: for the three refusals that say it).
A_FILE = "a file"
#: Whether `_remove_a_tree` removes a clone relative to a descriptor of the
#: `source-readonly/` it was made in, never through its path (#803): what
#: `shutil.rmtree(dir_fd=)` does from Python 3.11, where this platform's
#: `rmtree` walks by descriptor (`avoids_symlink_attacks`): Linux and macOS,
#: never Windows.
FD_REMOVAL = (sys.version_info >= (3, 11)
              and shutil.rmtree.avoids_symlink_attacks
              and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"))
#: Why a clone this run made is not removed where its path leads to another
#: directory now (`_NotTheClone`).
NOT_THE_CLONE = ("what that path leads to now is not the directory this run "
                 "made, so nothing is removed through it")


class _Claim(NamedTuple):
    """The directory `Source.clone` made for a clone, with an exclusive
    `mkdir`, and what `_remove_a_tree` holds its removal to (#803): its
    path as the run spells it; its real path and its identity (`st_dev`,
    `st_ino`), read right after the `mkdir`; the identity of the
    `source-readonly/` it is in; and whether this run made that too."""
    path: Path
    made_at: str
    identity: tuple
    parent_identity: tuple
    made_parent: bool


class _NotTheClone(Exception):
    """A clone's path that no longer leads to the directory this run made,
    and why, in words (#803). Nothing is removed through it."""


def _identity(status: os.stat_result) -> tuple:
    return status.st_dev, status.st_ino


def _same_spelling(path: str, other: str) -> bool:
    """Whether two real paths name one entry as this platform compares
    names: `os.path.normcase` on both, so that on Windows the disk's case,
    `Source-Readonly` as `ntpath.realpath` returns it, is the recorded
    `source-readonly` (#803, #457's L1-102)."""
    return os.path.normcase(path) == os.path.normcase(other)


def _owner(uid: int) -> str:
    """The user `uid` names, in backticks, or the id where none does. POSIX
    only, as `_shared_with_another_user` asks it."""
    import pwd
    try:
        return _spelled(pwd.getpwuid(uid).pw_name)
    except KeyError:
        return f"user id {uid}"


def _shared_with_another_user(status: os.stat_result) -> str | None:
    """Why another user can rename or replace what is in the directory
    `status` describes, an `os.lstat`, in words; None where nobody else can
    (#803). A user other than this one or root owns it; or every user can
    write in it, and its sticky bit, which keeps each entry to its owner as
    in `/tmp`, is not set. ROOT IS TRUSTED, as OpenSSH's StrictModes trusts
    it: root can do anything here anyway, and a directory an earlier `sudo`
    run left is then `adopt-work-dir-unwritable`, which is true, and not a
    claim that another user could write in it. GROUP WRITE IS NOT ASKED:
    under `umask 002` every directory a user makes is group-writable, for a
    group of that user alone. NOR IS ANYTHING ON WINDOWS, where neither the
    owner nor the mode bits say it."""
    if not hasattr(os, "geteuid"):
        return None
    if status.st_uid not in (os.geteuid(), 0):
        return (f"is owned by {_owner(status.st_uid)}, not by this user or "
                "root")
    if status.st_mode & stat.S_IWOTH and not status.st_mode & stat.S_ISVTX:
        return "can be written in by every user, without the sticky bit"
    return None


def _made_0755(path: Path, parents: bool = True) -> None:
    """`path` made a directory where it is missing, and each missing
    directory above it, as `Path.mkdir(parents=True, exist_ok=True)` makes
    them and fails, but each with `os.mkdir(..., 0o755)` (#803): under
    `umask 000` a work directory made 0777 would be refused as
    `adopt-work-dir-shared` by the run that made it. The umask still narrows
    it: under `umask 077` it is 0700. One another run made meanwhile is
    taken, and is asked with the others above the work directory."""
    try:
        os.mkdir(path, 0o755)
    except FileNotFoundError:
        if not parents or path.parent == path:
            raise
        _made_0755(path.parent)
        _made_0755(path, parents=False)
    except OSError:
        if not path.is_dir():
            raise


def _shared_above(root: Path) -> tuple[Path, str, bool] | None:
    """The first directory above `root`, from `/` down, that another user
    can rename in (`_shared_with_another_user`), why, and whether it is this
    user's own; None where there is none (#803). `root` is the real path
    `_work_root` read, and from then on the run uses it alone. Each entry
    above it is asked down to the deepest one that is a directory: where
    one is missing, or is no directory -- a file, or a symlink `realpath`
    could not follow, such as a loop -- the walk stops there, and
    `_made_0755` refuses it as #650 does, `adopt-work-dir-unwritable`. A
    symlink always reads as mode 0777, and a file another user owns would
    otherwise be named as a directory they can rename in (#843's
    re-verification, N1).

    THIS IS THE RULE OpenSSH's StrictModes HOLDS `authorized_keys` TO, but
    for two things: the sticky bit counts, which is what keeps `/tmp` open,
    and group write is not asked. A user who can rename in a directory above
    the work directory can swap the work directory itself between this
    run's claim and the identity it reads, so that the removal is held to
    that user's directory (#843's review: a second process won 5 of 20 runs
    on Python 3.12), and git's own cleanup of a failed clone removes by
    path."""
    if not hasattr(os, "geteuid"):
        return None
    for above in reversed(root.parents):
        try:
            status = os.lstat(above)
        except OSError:
            return None
        if not stat.S_ISDIR(status.st_mode):
            return None
        shared = _shared_with_another_user(status)
        if shared:
            return above, shared, status.st_uid == os.geteuid()
    return None


def _refuse_a_shared_chain(root: Path, done: str) -> None:
    """`adopt-work-dir-shared` for a `--work-dir` that has a directory above
    it another user can rename in (`_shared_above`), naming that directory
    and why. Where that directory is this user's, its mode is the reason,
    and the way out also names its sticky bit: set, it keeps each entry in
    the directory its owner's, and takes nothing from this user (#843's
    re-verification)."""
    found = _shared_above(root)
    if not found:
        return
    above, shared, mine = found
    remedy = WORK_DIR_OWN
    if mine:
        remedy += (f" Or, since {_spelled(str(above))} is this user's, set "
                   "its sticky bit "
                   f"({_spelled('chmod +t ' + shlex.quote(str(above)))}): "
                   "each entry in it then stays its owner's.")
    raise _shared_work_dir(
        f"--work-dir {_spelled(str(root))} is under {_spelled(str(above))}, "
        f"which {shared}, so another user could rename "
        f"{_spelled(str(root))}, or a directory between them, and turn this "
        "run's removal onto another directory", done, remedy)


def _shared_work_dir(detail: str, done: str, remedy: str) -> Refusal:
    """`adopt-work-dir-shared` for `detail`; `done` is said first in the way
    out, as `_work_dir_refusal` says it."""
    return Refusal(WORK_DIR_SHARED, detail, f"Remediation: {done}{remedy}")


def _what_is_there(held: Path, status: os.stat_result, leads: str) -> str:
    """What is at `held`, a `source-readonly` that is no directory of the
    work directory's own, in words: a symlink and what it holds, a file, or
    a directory that leads elsewhere, as a Windows junction does."""
    if stat.S_ISLNK(status.st_mode):
        with contextlib.suppress(OSError):
            return f"a symlink to {_spelled(os.readlink(held))}"
        return "a symlink"
    if stat.S_ISREG(status.st_mode):
        return A_FILE
    if stat.S_ISDIR(status.st_mode):
        return f"a directory that leads to {_spelled(leads)}"
    return "neither a file nor a directory"


def _source_readonly_refusal(work_root: Path, repository: str,
                             done: str) -> Refusal | None:
    """Why `<work_root>/source-readonly` cannot hold the clone of
    `repository`, as the refusal; None where it can, or is not there yet
    (#803). Asked before the NOTE, and before anything is made there.

    It must be a directory of the work directory's own: no symlink, which
    leads the clone and its removal elsewhere (#457's L1-99), and no file,
    which ended each command in a `FileExistsError` traceback (L1-65), both
    `adopt-work-dir-occupied`. No other user may be able to rename in it
    (`_shared_with_another_user`): in a work directory every user can write
    in, the user who made it first owns the clone's parent, and could turn
    the clone, or its removal, onto another directory. That is
    `adopt-work-dir-shared`. And this user must be able to make the clone's
    directory in it, or it is `adopt-work-dir-unwritable`."""
    held = work_root / SOURCE_READONLY
    shown = _spelled(str(work_root))
    try:
        status = os.lstat(held)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return _work_dir_refusal(
            f"--work-dir {shown} cannot hold `{SOURCE_READONLY}`, where this "
            f"run clones {repository}: reading it failed "
            f"({exc.strerror or exc})", done)
    leads = os.path.realpath(held)
    if not stat.S_ISDIR(status.st_mode) or not _same_spelling(
            leads, os.path.join(os.path.realpath(work_root), SOURCE_READONLY)):
        return Refusal(
            "adopt-work-dir-occupied",
            f"--work-dir {shown} already holds `{SOURCE_READONLY}`, "
            f"{_what_is_there(held, status, leads)}, where this run clones "
            f"{repository} into a directory of its own",
            f"Remediation: {done}Pass {ANOTHER_WORK_DIR}")
    shared = _shared_with_another_user(status)
    if shared:
        return _shared_work_dir(
            f"--work-dir {shown} holds `{SOURCE_READONLY}`, which {shared}, "
            "so another user could rename or replace the clone this run "
            "makes in it", done, f"Pass {ANOTHER_WORK_DIR}")
    if not os.access(held, os.W_OK | os.X_OK):
        return _work_dir_refusal(
            f"--work-dir {shown} holds `{SOURCE_READONLY}`, where this run "
            f"clones {repository}, and this user cannot make a directory in "
            "it", done)
    return None


def _made_source_readonly(work_root: Path, parent: Path, repository: str,
                          done: str) -> bool:
    """Make `parent`, `source-readonly/`, where nothing is there, and say
    whether this run made it (#803). One another run made meanwhile is
    asked as `_source_readonly_refusal` asks it, and any other failure is
    `adopt-work-dir-unwritable`, by name, where it was a traceback (#457's
    L1-65). Made 0755 whatever the umask: under `umask 0` it would be one
    every user can rename in. The work directory above it is made where it
    is missing, as on main: `_work_root` makes it for every command, so
    only a caller of `Source.open` that names another one meets that."""
    if os.path.lexists(parent):
        return False
    try:
        _made_0755(work_root)
        os.mkdir(parent, 0o755)
        return True
    except FileExistsError:
        refused = _source_readonly_refusal(work_root, repository, done)
    except OSError as exc:
        refused = _work_dir_refusal(
            f"--work-dir {_spelled(str(work_root))} cannot hold "
            f"`{SOURCE_READONLY}`, where this run clones {repository}: "
            f"making it failed ({exc.strerror or exc})", done)
    if refused:
        raise refused
    return False


def _claimed(work_root: Path, path: Path, repository: str,
             done: str) -> _Claim:
    """`path`, the directory `repository` is cloned into, made by THIS run
    with an exclusive `mkdir` before `gh` runs (`git clone` clones into an
    empty directory), and `source-readonly/` above it where it is not there:
    the claim `_remove_a_tree` holds a removal to (#803).

    ON MAIN THE TARGET WAS LISTED WHERE IT DID NOT EXIST YET, and made by
    `git clone`. So two runs given one `--work-dir` could both list it: the
    one whose clone failed removed the other's, which that run's plan
    recorded (#457's L1-98). Now the `mkdir` decides which run it is, and
    one made meanwhile by another run is refused as
    `adopt-work-dir-occupied`. Made 0755 whatever the umask."""
    made_parent = _made_source_readonly(work_root, path.parent, repository,
                                        done)
    try:
        os.mkdir(path, 0o755)
    except OSError as exc:
        if made_parent:
            with contextlib.suppress(OSError):
                os.rmdir(path.parent)
        if isinstance(exc, FileExistsError):
            raise _occupied_clone_target(work_root, path, repository,
                                         done=done) from None
        raise _work_dir_refusal(
            f"--work-dir {_spelled(str(work_root))} holds "
            f"`{SOURCE_READONLY}`, where this run clones {repository}, and "
            f"making `{path.name}` in it failed ({exc.strerror or exc})",
            done) from None
    return _Claim(path, os.path.realpath(path), _identity(os.lstat(path)),
                  _identity(os.lstat(path.parent)), made_parent)


def _not_a_whole_clone(path: Path, commit: str) -> str | None:
    """Why the clone `plan` made at `path`, which exists, is no longer one
    the plan's source can be read from, in words; None where it is (#652).

    It must be a directory that is the top of a repository of its own, and
    hold the plan's `commit`. The second catches a clone emptied inside
    another repository, which git reads as that one; the third a removed
    pack, which a clone holds all its objects in. Only what a cleaner
    leaves is asked: whether every object is whole is `git fsck`'s question,
    which a large source would pay for on every run."""
    if not path.is_dir():
        return "it is not a directory"
    try:
        top = os.fsdecode(git_out(["rev-parse", "--show-toplevel"],
                                  cwd=path, binary=True).strip())
    except (Refusal, OSError):
        return "git finds no repository there"
    if os.path.realpath(top) != os.path.realpath(path):
        return f"git reads it as part of the repository at {_spelled(top)}"
    if COMMIT_RE.match(commit):
        try:
            git_out([GIT_CAT_FILE, "-e", f"{commit}^{{commit}}"], cwd=path)
        except Refusal:
            return f"it no longer holds the plan's commit {commit[:12]}"
    return None


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
        #: Whether THIS RUN cloned it, into the work directory, rather than
        #: reading a local path in place: a re-run given the same --work-dir
        #: cannot clone into that directory again (`_cloned_here`). `plan`
        #: records it as `source.cloned` (#652).
        self.cloned = cloned
        #: Each symlink blob `symlink_targets` has read, by blob id: a blob
        #: is immutable, so the one `git cat-file --batch` of a command
        #: serves every later question about a link's target (#908). A blob
        #: git did not have is kept as None, and not asked for again.
        self.link_targets: dict[str, bytes | None] = {}

    @classmethod
    def open(cls, spec: str, work_root: Path, unwritable: str | None = None,
             made: list | None = None, done: str = "",
             instead: str | None = None) -> "Source":
        """`spec`, a `--source`, as `_source_spec` reads it: a local path,
        read in place, or a GitHub repository, cloned (`clone`, which takes
        `unwritable`, `made` and `done`). `instead` is `_default_branch`'s:
        the branch to read it at where its remote's default branch is no
        branch of its own."""
        return cls.of(_source_spec(spec), work_root, unwritable, made, done,
                      instead)

    @classmethod
    def of(cls, named: tuple[Path | None, str | None], work_root: Path,
           unwritable: str | None = None, made: list | None = None,
           done: str = "", instead: str | None = None) -> "Source":
        """The source `named` names, `_source_spec`'s answer, which `plan`
        asks before it makes its work directory (#796): the top-level
        directory it gave back, read in place, or the repository, cloned.
        `instead` is as `open` takes it."""
        path, repository = named
        if repository is not None:
            return cls.clone(repository, work_root, unwritable, made,
                             done=done, instead=instead)
        return cls.in_place(path, work_root, instead)

    @classmethod
    def in_place(cls, path: Path, work_root: Path,
                 instead: str | None = None) -> "Source":
        """The repository at `path`, read where it is, named by its
        `origin`. `path` is a top-level directory `_top_level` gave back,
        resolved (#796)."""
        return cls._at(path, _remote_repository(path), work_root, False,
                       instead)

    @classmethod
    def clone(cls, repository: str, work_root: Path,
              unwritable: str | None = None, made: list | None = None, *,
              note: str = "", taken: str = "", done: str = "",
              instead: str | None = None) -> "Source":
        """`repository`, an `owner/repo` `_github_name` gave, cloned with
        `gh repo clone` into `<work_root>/source-readonly/<repo>`, and read
        there. Every clone of a source goes through here.

        `unwritable` is why `work_root` cannot be written
        (`_unwritable_work_dir`), or None. It is refused as
        `adopt-work-dir-unwritable` before any directory is made or any clone
        is said (#650): `plan` ended in a PermissionError traceback at
        `source-readonly`. Then a target that is already there is refused as
        `adopt-work-dir-occupied` (#652, #803): `git clone` refuses one that
        holds something,
        and the refusal was `source-unclonable` with a remedy about `gh auth
        status`. `taken` is what that refusal says first, when the occupant
        is the plan's own clone (`Plan.open_source`), and `done` what
        `execute` says first in its way out. Only then is `note`, the NOTE
        that says why the plan's clone is made again, printed.

        `made` is the list a command keeps of the clones it made, for
        `_leave_the_clones`. THE TARGET IS CLAIMED BEFORE `gh` RUNS (#803):
        `source-readonly/` must be a directory of the work directory's own
        that no other user can rename in (`_source_readonly_refusal`), asked
        with the writable check and before the NOTE; ANY target already
        there is refused, an empty one included; and this run then makes it
        with an exclusive `mkdir` (`_claimed`). Only that `_Claim` goes on
        `made`, and `_remove_a_tree` removes only the directory it names.
        `execute` lists none and keeps its clone, but where the clone ends
        any other way than in a clone -- `gh` failing, Ctrl-C, no `gh` at
        all -- it removes the directory its own `mkdir` made, after the same
        checks, and then raises what ended it: so that the run given the
        same --work-dir again is not refused at an empty directory. Only a
        kill or a power loss can still leave one, and its refusal says to
        delete it where no run is using it."""
        path = work_root / SOURCE_READONLY / repository.split("/")[1]
        if unwritable:
            raise _work_dir_refusal(unwritable)
        refused = _source_readonly_refusal(work_root, repository, done)
        if refused:
            raise refused
        if os.path.lexists(path):
            raise _occupied_clone_target(work_root, path, repository, taken,
                                         done)
        if note:
            print(note)
        claim = _claimed(work_root, path, repository, done)
        if made is not None:
            made.append(claim)
        try:
            print(f"cloning {repository} (read only) into {path}")
            run(["gh", "repo", "clone", repository, str(path), "--",
                 "--quiet"])
        except BaseException as exc:
            if made is None:
                with contextlib.suppress(OSError, _NotTheClone):
                    _remove_a_tree(claim)
            if not isinstance(exc, CommandFailed):
                raise
            raise Refusal(
                "source-unclonable",
                f"could not clone {repository}: {exc.output.strip()[:400]}",
                "Remediation: check `gh auth status` and the repository "
                "name, or clone it yourself and pass the path.") from exc
        return cls._at(path, repository, work_root, True, instead)

    @classmethod
    def _at(cls, path: Path, repository: str | None, work_root: Path,
            cloned: bool, instead: str | None = None) -> "Source":
        branch = _default_branch(path, instead)
        # The branch's own commit, read by its full name and nothing else
        # (#797): `git rev-parse refs/heads/<b>` looks further, and a tag
        # named `refs/heads/<b>` answers it. As the bytes git keeps the name,
        # under any locale (#653).
        commit = _git_out_exact(["show-ref", "--verify", "--hash",
                                 f"{BRANCH_REFS}{branch}"], path).lower()
        return cls(path, repository, branch, commit, work_root, cloned)

    def tree(self) -> list[tuple[str, str, str, int]]:
        """(path, mode, blob sha, size) for every file at the pinned commit.

        A SIZE IS `-` OR DIGITS, OR THE SOURCE HAS LOST AN OBJECT (#796).
        `git ls-tree -l` prints `BAD` for the size of a blob it cannot read
        and still exits 0, and on main `int('BAD')` ended `plan`, `check`
        and `execute` in a `ValueError` traceback. It is refused, naming
        the path and `git fsck`, which names every object a repository
        lacks."""
        command = ["ls-tree", "-r", "-l", "-z", self.commit]
        raw = git_out(command, cwd=self.path, binary=True)
        out = []
        for record in raw.split(b"\x00"):
            if not record:
                continue
            head, _, path = record.partition(b"\t")
            mode, kind, oid, size = head.decode().split(maxsplit=3)
            size = size.strip()
            if size != "-" and not (size.isascii() and size.isdigit()):
                raise Refusal(
                    "git-failed",
                    f"`git {' '.join(command)}` in {shown_path(self.path)} "
                    f"gives no size for {_spelled(_git_path(path))}, whose "
                    f"blob {oid} it cannot read: it prints {_spelled(size)}",
                    f"Remediation: run `git fsck` in "
                    f"{shown_path(self.path)}: it names each object the "
                    "repository lacks. Restore them, or pass a clone that "
                    "holds them all, and run the command again.")
            out.append((_git_path(path), mode, oid,
                        0 if size == "-" else int(size)))
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
    """The `org/repo` the source's `origin` names (`url_repository`, the one
    reading `shape-doctor.py` shares); None when it has no origin, or one
    that names no such pair: a path names none (#521)."""
    url = _origin_url(path)
    return None if url is None else url_repository(url)


def _origin_url(path: Path) -> str | None:
    """The source's `origin` as git hands it to a fetch, `git remote get-url
    origin`: its first url, with any `url.<base>.insteadOf` applied. None
    when it has none. THE ONE READ of it, so that what `plan` compares and
    what it says it did not compare are one url (#521).

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
        return git_out(["remote", "get-url", "origin"], cwd=path)
    except (Refusal, UnicodeDecodeError):
        return None


#: Where git keeps the default branch of the source's remote `origin`, as
#: `git clone` and `git remote set-head` record it.
ORIGIN_HEAD = "refs/remotes/origin/HEAD"
#: How `Source.open` refuses a source whose default branch is no branch of
#: its own, and the way through it, in `plan`, `check` and `execute` alike
#: (#797).
DEFAULT_BRANCH_NOT_LOCAL = "source-default-branch-not-local"
#: How each of its details ends, after "the source".
NOT_IN_ITS_PLACE = ("is read at a branch of its own, never at another "
                    "nobody named in its place")


def _default_branch(path: Path, instead: str | None = None) -> str:
    """The branch the adoption reads, in the order a reader would guess it:
    the default branch of the source's remote `origin`, as its `origin/HEAD`
    names it; else the branch its HEAD is on; else `main`. The name of a
    branch of the source's own, which `Source._at` reads by its full name.

    BY FULL NAME, AND WHOLE (#797). `git symbolic-ref --short` gave a name
    with `origin/` to take off, and it was taken off HEAD's too, so a HEAD
    on a branch of the source's own named `origin/x` read `x`; a tag named
    like the branch made HEAD's short name `heads/main`, which `plan`
    recorded as the tracking branch; and the name `origin/HEAD` gave,
    `main`, was read with `git rev-parse main`, which a tag `main` answers
    first. The name was also stripped once decoded, which takes U+00A0 off
    `main<U+00A0>`, and the branch `main` beside it was read. So the full
    name is read (`_symbolic_ref`), and only its own prefix comes off. An
    `origin/HEAD` set by hand to a ref outside `refs/remotes/origin/`
    names no branch of `origin`: it is passed over for HEAD's branch, in a
    NOTE that names it.

    A BYTE THAT IS NOT UTF-8 IS KEPT, AS `sys.argv` KEEPS ONE (#425). git
    keeps a branch's name as the bytes it was given: `git branch caf<e9>` is
    legal, and a name typed in a Latin-1 terminal is one. Read strictly, it
    ended `plan`, `check` and `execute` in a `UnicodeDecodeError` traceback
    from `Source.open`, with no plan written and nothing said of the branch.
    Kept as a lone surrogate, it is the tracking branch `plan` would take
    (#479) and refuses as `unsafe-value`, before any plan is written, with
    `--tracking-branch` as the way past it; and it is the default branch
    `check` and `execute` name, as `plan-tracking-branch-missing`, when the
    plan tracks one the source no longer has. Where the plan tracks a branch
    that is text, the source is read at this one and adopted.

    ONLY A BRANCH OF THE SOURCE'S OWN IS EVER READ (#797). A clone made
    with `git clone -b dev`, or one whose `main` was deleted, has
    `origin/HEAD` naming `main` and no `main` of its own, and `git rev-parse
    main` ended `plan`, `check` and `execute` as `git-failed`, in git's
    words, whatever `--tracking-branch` said. A detached HEAD's guessed
    `main` and an orphan HEAD's branch with no commit yet can be no branch
    either, and `git rev-parse refs/heads/<b>` then looks further, so a tag
    named `refs/heads/main` answered for it. Such a source is read at
    `instead` where that is a branch of its own: `plan`'s
    `--tracking-branch`, or the branch a plan records reading it at, for
    `check` and `execute`. Otherwise it is refused by name, with the ways
    through (`_no_branch_of_its_own`), and never read at HEAD's branch or
    any other in its place."""
    named = _symbolic_ref(path, ORIGIN_HEAD)
    origins = _branch_under(named, ORIGIN_BRANCHES)
    if named is not None and origins is None:
        print(f"NOTE the source's `origin/HEAD` names {_spelled(named)}, "
              "which is no branch of its remote `origin`, so it is passed "
              "over, and the branch its HEAD is on is read instead.")
    head = None if origins else _branch_under(_symbolic_ref(path, "HEAD"),
                                              BRANCH_REFS)
    branch = origins or head or "main"
    branches = _branch_names(path, BRANCH_REFS)
    if branch in branches:
        return branch
    if instead in branches:
        return instead
    if origins:
        raise _no_branch_of_its_own(path, branch, "origin", instead, branches)
    raise _no_branch_of_its_own(path, branch, "head" if head else None,
                                instead, branches)


def _no_branch_of_its_own(path: Path, branch: str, where: str | None,
                          instead: str | None, branches: list) -> Refusal:
    """`source-default-branch-not-local`: the source's default branch,
    `branch`, is no branch of its own, nor is `instead`. `where` is what
    named it: `origin` (its `origin/HEAD`), `head` (HEAD, on a branch with
    no commit yet), or None (no `origin/HEAD` and a detached HEAD, so the
    `main` this tool reads then). Each way through is said: the branch
    made, or HEAD moved, and `--tracking-branch`."""
    nor = "" if instead in (None, branch) else \
        f", nor one named {_spelled(instead)}"
    held = f"{nor} (its branches: {_branches_named(branches)})"
    if where == "origin":
        detail = (f"the source's `origin/HEAD` names {_spelled(branch)}, the "
                  "default branch its remote `origin` had when it was last "
                  f"asked, and the source has no branch {_spelled(branch)} of "
                  f"its own{held}. A clone made with `git clone -b <branch>` "
                  "has none, nor does one whose own was deleted, and the "
                  f"source {NOT_IN_ITS_PLACE}")
        first = _from_the_remote(path, branch)
    else:
        named = (f"its HEAD is on {_spelled(branch)}, which has no commit "
                 "yet, so it is no branch" if where == "head" else
                 "it has no `origin/HEAD` naming a branch of its remote "
                 "`origin`, its HEAD is detached, and it has no branch "
                 "`main`, which this tool reads then")
        detail = f"the source names no branch of its own to read: {named}" \
            f"{held}. The source {NOT_IN_ITS_PLACE}"
        first = ("Remediation: check out the branch to adopt, in the source "
                 "(`git switch <branch>`).")
    return Refusal(
        DEFAULT_BRANCH_NOT_LOCAL, detail,
        f"{first} Or run `plan` with `--tracking-branch` naming a branch "
        "the source has, and the source is read at that branch; `check` "
        "and `execute` then read it at that branch while the source has "
        f"no branch {_spelled(branch)} of its own.")


def _from_the_remote(path: Path, branch: str) -> str:
    """The first way through for `origin/HEAD`'s `branch`: made the
    source's own from its remote's, where the source has fetched that; and
    where it has not, as after the remote renamed its default branch, the
    remote asked again (`git remote set-head origin --auto`). A command is
    printed with the name in it only where the name is printable, which a
    lone surrogate never is: a name holding U+0085 or U+2028 broke the line,
    and #425's `caf\\udce9` printed a command git refuses. Otherwise the name
    is `_spelled` and the step said in words."""
    if branch not in _branch_names(path, ORIGIN_BRANCHES):
        return ("Remediation: its remote `origin` has no branch "
                f"{_spelled(branch)} either, as the source last fetched it: "
                "ask `origin` for its default branch again, `git remote "
                "set-head origin --auto`, run in the source.")
    made = (f"`git branch {shlex.quote(branch)} "
            f"{shlex.quote('origin/' + branch)}`" if branch.isprintable()
            else f"a branch named {_spelled(branch)} made from `origin`'s "
            "branch of that name")
    return ("Remediation: make it a branch of the source's own, from its "
            f"remote's: {made}, run in the source; where `origin` may have "
            "changed its default branch since, run `git remote set-head "
            "origin --auto` first.")


def _symbolic_ref(path: Path, ref: str) -> str | None:
    """The full name of the ref the symbolic ref `ref` names; None where
    `ref` is no symbolic ref.

    Read as bytes and decoded as #425 decodes them, with only git's line end
    taken off first, from the bytes: `str.strip` after decoding took U+00A0,
    which a branch's name may end in, for white space (#797)."""
    try:
        full = git_out(["symbolic-ref", "-q", ref], cwd=path, binary=True)
    except Refusal:
        return None
    return full.removesuffix(b"\n").decode("utf-8", "surrogateescape")


def _branch_under(name: str | None, prefix: str) -> str | None:
    """`name` with exactly `prefix` taken off; None where it is not a name
    under `prefix`."""
    if name is not None and name.startswith(prefix) \
            and len(name) > len(prefix):
        return name[len(prefix):]
    return None


def _branch_names(path: Path, prefix: str) -> list[str]:
    """The names of the source's refs under `prefix` (`BRANCH_REFS`, its own
    branches; `ORIGIN_BRANCHES`, its remote's as it last fetched them), each
    as `Source.tree` reads a path, so a byte that is not UTF-8 is kept
    rather than refused."""
    raw = git_out(["for-each-ref", "--format=%(refname)", prefix], cwd=path,
                  binary=True)
    return sorted(ref[len(prefix):]
                  for ref in map(_git_path, raw.splitlines()))


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
    # The rule id is a path policy's, which nothing asks to be printable:
    # `_spelled`, as a path is (#900).
    question = (f"{asked.question} " if asked.question else "") + (
        f"This entry holds the submodule(s) {_listed(held)}: it is asked "
        f"this question, not classified by its rule "
        f"{_spelled(str(entry.rule))}.")
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
        # The rule id `_spelled`, as `_asked_about` names it (#900).
        lead = (f"The rules put this path in the {entry.leg} leg (rule "
                f"{_spelled(str(entry.rule))}), but `execute` will not "
                "extract it")
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
    and so are a backslash, a double quote and a backtick, so that the
    spelling reads one way only and the backticks still delimit it.

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

    A BACKTICK IS `\\x60` AND A DOUBLE QUOTE `\\"` (#900), the plan's own
    escapes for them, so that EVERY spelled name, copied between the plan's
    double quotes, is that entry. A backtick was written after a
    backslash, which is no escape the plan's reader resolves: it kept the
    backslash, and so read another entry. A double quote was written as it
    is, which ended the quoting, and the plan no longer read at all.
    `\\x60` holds no backtick, so the two that wrap the name are still the
    only ones.
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
    exactly as it did.

    SO IS A PRINTABLE TEXT THAT BEGINS AND ENDS WITH A BACKTICK (#900).
    `_spelled` writes every name between two backticks and none inside
    them, so the name `` `x` ``, printed as it is, read exactly as the
    spelling of the name `x`: spelled, it is `` `\\x60x\\x60` ``. A text
    printed as it is now never begins and ends with a backtick, and a
    spelling always does, so no two texts print alike. AND SO IS ONE THAT
    ENDS IN A SPACE, which reads as nothing: `git commit` strips it from
    the end of each line of the split commit's message, which lists names
    `_shown`, so `trail.md ` was listed as `trail.md`, and `plan`'s table
    pads `trail.md ` and `trail.md` to the same row."""
    if (path.isprintable() and not path.endswith(" ")
            and not (path.startswith("`") and path.endswith("`"))):
        return path
    return _spelled(path)


#: How `_spelled` writes a backtick: the plan's code-point escape for one,
#: which holds no backtick itself (#900).
SPELLED_BACKTICK = "\\x60"


def _spelled_character(char: str) -> str:
    """One character of `_spelled`: the escape `repo_shape.double_quoted`
    writes for it in the plan, so the plan's one table and not a second
    one -- itself when it is printable, `\\\\` for a backslash, `\\"` for a
    double quote, `\\n` for a line feed, `\\x85` for U+0085, `\\u2028` for
    U+2028, and `\\udc85` for the byte 0x85, which `Source.tree` keeps as
    the surrogate U+DC00 plus the byte -- except a backtick, which the plan
    holds as it is and `_spelled` wraps a name in: `SPELLED_BACKTICK`, the
    escape the plan's reader takes for one (#900)."""
    if char == "`":
        return SPELLED_BACKTICK
    return double_quoted(char)[1:-1]


def cross_leg_references(source: "Source",
                        entries: list["Entry"]) -> list[str]:
    """Files that will move to the CODE leg and name a path in the SPEC leg.

    Found by asking git, not by guessing: `git grep -l` over the source commit,
    restricted to the paths the plan sends to the code leg, for the name of
    each directory the plan sends to the spec leg. That is how a follow-up ends
    up saying `scripts/validate.py` instead of "something may read contracts".

    This is the 2026-09-02 ruling made operational: `contracts/*.yaml` go to
    the spec leg, and the code that reads them reads ACROSS the assembly root
    mount. The read is one relative path from the code leg — but only once
    somebody edits it, so the plan says which file and the human decides when.

    IT NAMES THE TWO MOUNT KEYS, `legs.code_path` AND `legs.spec_path`, AND NO
    PATH OF EITHER (#600), so it takes neither path. `plan` writes the list
    once; `MOUNT_REMEDIATION` and `plan-leg-path-collides` ask a person to
    change those keys afterwards; `check`, the split commit's message and the
    pull request's body read the line back. It said `code/src/app/main.py` and
    `../spec/contracts/` "relative to `code/`" for legs mounted elsewhere. The
    file is named as the code leg holds it and the directory as the spec leg
    does: both are paths in the SOURCE, which no edit of the plan moves. The
    Makefile follow-up (#522's review, F1) and the tracking branch's (#493's
    review, F3) are written the same way. The path from the code leg to the
    spec leg, and to its `contracts/` where it holds one, which a person has
    then to work out from the two mounts, is printed next to the CURRENT
    mounts by the two sentences that name them (`contracts_from_code_leg`,
    #600's review, F1; #906).

    EVERY NAME IS A NAME (#216). Both inputs are source paths, and git reads
    each as something else unless told not to. A spec directory passed bare
    sits where git reads OPTIONS: `-notes/` was a usage error (exit 129, no
    follow-up), and `-O<cmd>/` was `--open-files-in-pager`, which git runs
    through a shell -- argv and `shell=False` stop Python running a shell,
    not git -- so `-e` makes it the pattern. The code entries are pathspecs:
    `:cache` read as the pathspec `cache` and `*` matched files in the spec
    leg, so `--literal-pathspecs`. `-l` C-quoted a name outside printable
    ASCII (`"src/\\303\\234bersicht.py"`), so `-z`, read as `Source.tree`
    reads names, and each hit is named as `plan`'s table and the split
    message's listing name it (`_shown`, #900), and the spec directory as a
    sentence names a path, between backticks: one line of UTF-8 whatever
    its bytes. `--no-color`, because `color.grep=always` wraps
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
        # The name and the code paths as the bytes the tree holds (#653):
        # as text, `Übersicht/` raised `UnicodeEncodeError` under
        # `LC_ALL=C PYTHONUTF8=0`, and `plan` wrote no plan.
        proc = subprocess.run(
            ["git", "--literal-pathspecs", "grep", "--no-color", "-z", "-l",
             "-I", "-F", "-e", _path_argument(spec_dir), source.commit, "--",
             *map(_path_argument, code_paths)],
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
            shown = _shown(hit)
            out.append(
                f"{shown} in the code leg names `{named}`, which moves to "
                "the spec leg: it must read across the assembly root — from "
                "the code leg, where the plan's `legs.code_path` mounts it, "
                f"to `{named}` in the spec leg, where `legs.spec_path` "
                "mounts it — or take the path from the environment")
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

    It is asked of the plan's CURRENT mounts, when a sentence that prints
    them is rendered, and never of the two a plan was written with (#600's
    review, F1): `contracts_from_code_leg` below.

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


#: What each read-across follow-up says of what the file must do: both the
#: line `cross_leg_references` writes for a file that names a spec directory,
#: and `_search_by_hand`'s for a name git could not search for (#906).
READ_ACROSS = "read across the assembly root"


def holds_a_read_across(follow_ups) -> bool:
    """Whether `follow_ups` holds a read-across follow-up: a line that says
    a file must `READ_ACROSS`. Asked of the plan's own list, as the plan
    stands, and not of a `git grep`, which `check` and the split message
    never run (#906)."""
    return any(isinstance(item, str) and READ_ACROSS in item
               for item in follow_ups)


def contracts_from_code_leg(spec_path, code_path, spec_leg_paths,
                            follow_ups=()) -> str:
    """What the two sentences that print the plan's CURRENT mounts end with:
    ", so from the code leg the spec leg is `../spec/`" where the plan holds a
    read-across follow-up, and ", so from the code leg the spec leg's
    `contracts/` is `../spec/contracts/`" where the spec leg holds
    `contracts/`, both joined by " and " where both are true; or "" when
    there is nothing true to say (#600's review, F1; #906).

    THE READ-ACROSS FOLLOW-UP NAMES `legs.code_path` AND `legs.spec_path` AND
    NO PATH, so no hand edit of either can contradict it, and it leaves the
    path itself to the two mounts printed beside it. That path is the one
    #522's review (auA-13) showed a person gets wrong for nested legs by
    hand, and `CONTRACTS_DIR` is the root Makefile's alone. So it is printed
    where the mounts are, computed from the values the surface itself prints:
    `check`'s `mount the legs at X/ and Y/`, from the plan as it stands, and
    the split message's `mounted back here at X/ and Y/`, from the mounts
    `execute` made. It is never stored in `follow_ups:`, so it cannot go stale
    between a hand edit and the next `check`, and it needs no `git grep`.

    THE SPEC LEG'S OWN PATH, NOT ONLY ITS `contracts/` (#906). The follow-up
    is written for a code file that names ANY directory the plan sends to
    the spec leg, `specs/` as much as `contracts/`, and a person finishing
    it needs the path to that directory. It gave one only where the spec leg
    held `contracts/`, so a file naming `specs/` got the key-form line and no
    ready path, where v1.0.1 printed `../spec/specs/`. The spec leg's own
    path is the one every such directory lies below: from it the person
    reaches `specs/` or any other. It is printed wherever `follow_ups` holds
    a read-across line (`holds_a_read_across`), `contracts/` or not, and the
    `contracts/` clause stays for the spec leg that holds one.

    NOTHING, in three cases. The plan holds no read-across follow-up and no
    path of the spec leg is `contracts/` or lies under it (the Makefile
    follow-up's own condition), so there is nothing to lead to. A mount is
    not text, or the two are not mount paths `execute` accepts, or they
    overlap or differ only in case: `check` says so as a finding, and a path
    computed from two strings that are not two mounts leads nowhere.
    `spec_leg_paths` are the paths the plan assigns to the spec leg, as
    `_leg_paths` reads them, and `follow_ups` the plan's, as
    `_plan_follow_ups` reads them.
    """
    holds_contracts = any(path == "contracts/" or path.startswith("contracts/")
                          for path in spec_leg_paths)
    reads_across = holds_a_read_across(follow_ups)
    if not (holds_contracts or reads_across):
        return ""
    if leg_path_problems(("legs.spec_path", spec_path),
                         ("legs.code_path", code_path)):
        return ""
    across = spec_leg_from_code_leg(spec_path, code_path)
    said = []
    if reads_across:
        said.append(f"the spec leg is `{across}/`")
    if holds_contracts:
        said.append(f"the spec leg's `contracts/` is `{across}/contracts/`")
    return ", so from the code leg " + " and ".join(said)


def _search_by_hand(named: str, why: str) -> str:
    """The follow-up for a spec directory git did not search for: the
    reason, and what to look for instead."""
    return (f"git could not search the files moving to the code leg for "
            f"`{named}` ({why}); find the ones that name it by hand: each "
            f"must read across the assembly root once `{named}` moves to the "
            "spec leg")


def _root_keeps(surviving: set[str], path: str, *,
                fold: bool = False) -> bool:
    """Whether the root keeps `path`: as its own entry, or inside a
    directory it keeps there. `surviving` is each path the plan's entries
    send to the root.

    ONE DEFINITION, for `_predict_collisions`, which moves the shape's copy
    of a path the root keeps under `shape/`, and for `follow_ups_for`, whose
    Makefile line says where the block waits when that copy is the one that
    moved (#906). Two readings of "the source keeps its own `Makefile`" is
    how a follow-up says the root wires what `shape/Makefile` holds.

    `fold` asks it as a disk that ignores case finds a path, where `place`'s
    `Path.exists()` holds a kept `makefile` to be `Makefile` (#977), as
    `_KeptTree` asks it for `check`.
    """
    if fold:
        surviving = {kept.casefold() for kept in surviving}
        path = path.casefold()
    return path in surviving or f"{path.split('/')[0]}/" in surviving


#: The names GNU make looks for when no `-f` is given, in its order: it reads
#: the first it finds, and only that one.
GNU_MAKE_READS = ("GNUmakefile", "makefile", "Makefile")


def _makefile_follow_up(surviving: set[str]) -> str:
    """The follow-up that says which Makefile wires `CONTRACTS_DIR`, where
    the shape's is written, and, where the source keeps a file GNU make reads
    before it, which one. `surviving` is each path the plan's entries send
    to the root.

    WHERE THE ROOT KEEPS A `Makefile` OF THE SOURCE'S OWN, the shape's goes
    beside it as `shape/Makefile` with the block in it, and the root's is
    the source's, untouched (#906).

    GNU MAKE READS THE FIRST OF `GNUmakefile`, `makefile` AND `Makefile` IT
    FINDS (#977). #906 asked only whether the source keeps `Makefile`, byte
    for byte, so a source that keeps `makefile` or `GNUmakefile` got "the
    root Makefile wires `CONTRACTS_DIR`": the root's `Makefile` is the
    shape's, with the block, and `make` there reads the source's file and
    never it, so `make contracts-dir` answered `No rule to make target`. The
    line names that file wherever the source keeps one, beside a `Makefile`
    of its own or not, and says what it takes for `make` at the root to
    export `CONTRACTS_DIR`.

    AND ON A DISK THAT IGNORES CASE the source's `makefile` is `Makefile`:
    `place` finds the name taken and writes the shape's as `shape/Makefile`,
    so the line says the shape's is written as the root's `Makefile` where
    case is kept, and as `shape/Makefile` where it is not, naming the kept
    path that takes the name there. Whether GNU make itself reads a name by
    its case there is its build's to say, so nothing more is said of it.
    """
    aside = _root_keeps(surviving, SHAPE_MAKEFILE)
    folded = (not aside
              and _root_keeps(surviving, SHAPE_MAKEFILE, fold=True))
    twins = sorted(kept.rstrip("/") for kept in surviving
                   if kept.rstrip("/").casefold() == SHAPE_MAKEFILE.casefold())
    first = next((name for name in GNU_MAKE_READS
                  if name != SHAPE_MAKEFILE and _root_keeps(surviving, name)),
                 None)
    whose = "the shape's" if aside or folded or first else "the root"
    said = (f"{whose} Makefile wires `CONTRACTS_DIR` to the `contracts/` of "
            "the spec leg, where the plan's `legs.spec_path` mounts it, and "
            "exports it, so the code leg's tooling takes the path from the "
            "environment instead of assuming it sits beside it")
    copy = f"`{COLLISION_DIR}/{SHAPE_MAKEFILE}`"
    if aside:
        said += (
            "; but the source keeps a Makefile of its own at the root, so "
            f"that block waits in {copy} until the two are merged, and the "
            "run adds none of it to the root's Makefile")
    elif folded:
        said += (
            f"; it is written as the root's `{SHAPE_MAKEFILE}`, or as {copy}"
            f"{_CASE_ASIDE}, where the source's {_spelled(twins[0])} is that "
            "path, until the two are merged")
    elif first:
        said += f"; it is written as the root's `{SHAPE_MAKEFILE}`"
    if first:
        listed = _and_listed([f"`{name}`" for name in GNU_MAKE_READS])
        said += (
            f"{'; and' if aside or folded else ', but'} GNU make at the root "
            f"reads the source's {_spelled(first)}, the first of {listed} it "
            f"finds, so `make` there exports `CONTRACTS_DIR` only once "
            f"{_spelled(first)} does, or includes a Makefile that does")
    return said


def follow_ups_for(source: "Source", entries: list["Entry"], names: dict,
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
    one (#522's review, F1). So does the read-across line that
    `cross_leg_references` writes, for both mounts, and this function takes
    no mount path: no value of either key can reach a line it writes (#600).
    The path from the code leg to the spec leg, and to its `contracts/`, is
    printed beside the CURRENT mounts instead, where `check` and the split
    message name them (`contracts_from_code_leg`).

    WHERE THE ROOT KEEPS A `Makefile` OF THE SOURCE'S OWN, the shape's goes
    beside it as `shape/Makefile` with the block in it, and the root's is
    the source's, untouched: `make contracts-dir` there answers `No rule to
    make target` until the two are merged. The line then says the block
    waits in `shape/Makefile`, as #634 words it for the pinned
    `AGENTS-shape.md`, of the plan's entries as `_predict_collisions` reads
    them (`_root_keeps`), the reading that moves the copy (#906). And it
    names the source's file GNU make reads before the shape's, and where a
    disk that ignores case writes the shape's (`_makefile_follow_up`, #977).
    """
    out = cross_leg_references(source, entries)
    if any(e.leg == "spec" and (e.path == "contracts/"
                                or e.path.startswith("contracts/"))
           for e in entries):
        out.append(_makefile_follow_up(
            {e.path for e in entries if e.leg == "root"}))
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
        "# `cloned: true` says `plan` cloned `repository` into `local_path`, so",
        "# `check` and `execute` clone it again where that clone is gone or no",
        "# longer whole. A path given to `plan` is never cloned again.",
        "source:",
    ]
    emit(lines, "repository", source.repository, 2)
    emit(lines, "local_path", str(source.path), 2)
    emit(lines, "cloned", source.cloned, 2)
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
#: is named by where it came from as well (#529), and so is an organisation
#: read from the source's `origin` (L1-39): a url can end in `~x`, which
#: `checked_value` takes and the validator refuses, and that refusal said
#: `--org is '~x'`. The words are `_planned_org`'s for the same value; a
#: source `plan` cloned has the `--source` it was cloned from as its
#: `origin`.
FLAG_DEFAULTS = {"id": "--project lowercased",
                 TRACKING_KEY: "the source's default branch",
                 ELECTED_BY_KEY: "`git config user.name`",
                 "org": "the organisation of the source's `origin`"}
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
    `execute --local-remote-dir` asks them, of the source as a remote, with
    `git ls-remote` (`_branches_a_clone_gets`); one that cannot be listed is
    no branch `execute` pushes to there."""
    if _tracking_branch_problem(source, TRACKING_KEY, tracking) is not None:
        return False
    try:
        return tracking in _branches_a_clone_gets(str(source.path),
                                                  source.path)
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
    # (`_template_table`). None at all where the plan's `pins:` has a
    # finding of its own (`_read_pins`, #273): `execute` refuses such a plan
    # before any leg exists, and one wrong pin is one finding. A product
    # given twice is one such finding (`plan-pin-collides`), so each is
    # asked about once.
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
    raw = git_out(["for-each-ref", "--format=%(refname)", BRANCH_REFS,
                   ORIGIN_BRANCHES], cwd=source.path, binary=True)
    refs = [_git_path(line) for line in raw.splitlines()]
    fetched = sorted(ref[len(ORIGIN_BRANCHES):] for ref in refs
                     if ref.startswith(ORIGIN_BRANCHES)
                     and ref != f"{ORIGIN_BRANCHES}HEAD")
    if fetched:
        return "the source's remote `origin`", fetched
    return "the source", sorted(ref[len(BRANCH_REFS):] for ref in refs
                                if ref.startswith(BRANCH_REFS))


def _branches_named(branches: list[str]) -> str:
    """`branches` as a finding names them: the first `BRANCHES_NAMED`, and
    how many more there are; `none` where there are none."""
    named = _listed(branches[:BRANCHES_NAMED]) or "none"
    if len(branches) > BRANCHES_NAMED:
        named += f" and {len(branches) - BRANCHES_NAMED} more"
    return named


def _tracking_branch_problem(source: Source, what: str,
                             tracking: str) -> str | None:
    """Why `tracking`, named as `what`, cannot be this adoption's tracking
    branch, as a sentence; None when it is a branch of the source as
    `_branches_of` reads them. ONE TEST, asked by `plan` as a NOTE and by
    `check` and `execute` as `plan-tracking-branch-missing`."""
    whose, branches = _branches_of(source)
    if tracking in branches:
        return None
    return (f"{what} is {_spelled(tracking)}, which is no branch of {whose} "
            f"(its branches: {_branches_named(branches)}; the source's "
            f"default branch is {_spelled(source.branch)}). `execute` pushes "
            "both legs to it, writes it into the root's `project.yaml` as the "
            "branch the project tracks, and opens the split's pull request "
            "against it once both legs and the split are pushed, where "
            "GitHub refuses a base that is not a branch (`Base ref must be a "
            "branch`)")


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


#: The name the naming policy takes for an assembly root, in the words
#: `naming-unclassified` says it in (`_check_names`). A derived id's remedy
#: says the same (#658): "change --project" alone sent the person to
#: `North-Wind`, which `naming-unclassified` then refused.
PROJECT_NAME_RULE = ("one CamelCase token with no hyphen, underscore, dot or "
                     "space")
#: What a refusal says first where `--project` is the source's own name,
#: adopted in place, before `_rename_first`'s way out: the rule the new name
#: is held to. The derived id's remedy says it (L2-54), and so does
#: `_check_names`' refusal of that name (L2-89 on #457).
OWN_NAME_RULE = ("--project is the source's own name, which must be "
                 f"{PROJECT_NAME_RULE}. ")
#: What a passed `--id` the project's validators would not take is told
#: (#902): `PROJECT_ID_RE` in words. "Pass an explicit lowercase --id" was
#: said to `--id foo_bar`, which is both, and whose fault is the underscore
#: (L2-82 on #459). The scaffold's `scaffold-bad-id` and `family.py init`'s
#: `family-bad-id` say the same sentence (#911).
PASSED_ID_REMEDIATION = ("Remediation: pass an --id of lowercase letters, "
                         "digits and hyphens, starting with a letter or "
                         "digit.")
#: And what `check` and `execute` say of a plan's `id:` the pattern refuses
#: (`plan-bad-id`, #902), in the same words.
PLAN_ID_REMEDIATION = (
    "Remediation: set `id:` in the plan to lowercase letters, digits and "
    "hyphens, starting with a letter or digit, or re-run `plan` with an --id "
    "of that form. The GitHub topic is derived from it.")
#: What `plan-bad-id` says of an id derived from `legs.assembly` (#902, L2-88
#: on #457), as `plan` words the id it derives from `--project` (L2-54): the
#: name it comes from, and the rule the naming policy holds that name to.
DERIVED_PLAN_ID_REMEDIATION = (
    f"Remediation: change `legs.assembly` in the plan to {PROJECT_NAME_RULE}, "
    "or re-run `plan` with a --project of that form. The id is "
    "legs.assembly lowercased, and an `id:` would leave `legs.assembly`, the "
    "assembly root's name, as it is. The GitHub topic is derived from the id.")
#: What `check` and `execute` say of a plan value the plan's reader read as a
#: number or a boolean where `execute` takes text (#902, L1-K3 on #457):
#: `_not_text` says what was read, and this how to write what was meant.
NOT_TEXT_REMEDIATION = (
    "Remediation: write each value named between double quotes in the plan, "
    "as typed (`\"007\"`, `\"true\"`), so that the plan's reader takes it as "
    "text, and run `check` again; or re-run `plan`, which writes every value "
    "so that it is read back as typed.")


def _a_number_or_boolean(value) -> bool:
    """Whether the plan's reader read `value` as a number or a boolean, which
    `execute` would turn into text with `str`: `007` into `7`, `true` into
    `True` and `1.50` into `1.5` (#902, L1-K3 on #457)."""
    return isinstance(value, (bool, int, float))


def _not_text(key: str, value) -> str:
    """A sentence about the plan's `key:`, which the plan's reader read as
    `value`, a number or a boolean, where `execute` takes text: what was
    read, and the text `execute` would take in its place (#902). The kind
    is the one `_the_loader_made` names, as #181's misread rule names it."""
    return (f"`{key}:` was read out of the plan as {_the_loader_made(value)}, "
            f"not as text, so `execute` would take it as the text "
            f"{_worded(str(value))}")


def _refuse_bad_id(project_id: str, project: str, given: set,
                   source: Source | None, naming: NamingPolicy,
                   pins: set[str]) -> None:
    """`plan`'s refusal of an id the project's validators would not take
    (`PROJECT_ID_RE`), in the words of where it came from. `given` is
    `flags_given`. A `--id` the person passed, `''` among them (L2-53), is
    named as the flag they typed, with the value as typed, and is told what
    an id may hold (`PASSED_ID_REMEDIATION`, #902). One `plan` derived from
    `--project` is named by `_flag_named` from `FLAG_DEFAULTS`, as the
    tracking branch and the elector it fills in are (#529): `--id
    'north_wind' must match` named a flag nobody had passed (#601). The
    finding's code is the same for both.

    A REFUSED NAME SPEAKS BEFORE A PASSED ID (#902, L2-90 on #457). `--project
    North_Wind --id north_wind` was refused for its id, and typing the
    remedy's `--id north-wind` then met `naming-unclassified`, which no
    `--id` mends. So a passed id is refused only once the names `--project`
    makes are ones the naming policy holds: `_check_names` is asked of them
    first, with `pins`, the products `--pin` declares, which are all it
    reads, so it answers here as it answers after the pins' digests are
    read. It is handed `source` only where `--project` is the source's own
    name, as below, since the names are not yet held to the source
    (`_refuse_another_repository`). The scaffold and `family.py init` ask
    their names first too (#911).

    A DERIVED ID IS MENDED IN `--project`, NOT WITH `--id` (L2-54). It is
    refused only for a `--project` holding a character no id takes, and the
    naming policy reads `--project` itself, as all three repositories'
    names: "pass an explicit lowercase --id" led to `naming-unclassified`.
    So the remedy is to change `--project`, to what the naming policy takes
    (`PROJECT_NAME_RULE`, the words of `naming-unclassified`); and where the
    source names a repository and `--project` is its name, adopted in place,
    that name is not the person's to retype, and the remedy is
    `_rename_first`'s, after the same rule. A source `plan` cloned names its
    repository as an `origin` does (`Source.repository`)."""
    if PROJECT_ID_RE.match(project_id):
        return
    flag, pattern = _flag_named("id", given), PROJECT_ID_RE.pattern
    repository = None if source is None else source.repository
    in_place = repository is not None and _is_the_source(
        repository, repository.partition("/")[0], project)
    if "id" in given:
        _check_names(naming, _names(project), pins,
                     source if in_place else None)
        raise Refusal("adopt-bad-id",
                      f"{flag} {project_id!r} must match {pattern}",
                      PASSED_ID_REMEDIATION)
    derived = FLAG_DEFAULTS["id"]
    if in_place:
        remedy = _rename_first(repository,
                               f"the id is {derived}, and {OWN_NAME_RULE}")
    else:
        remedy = (f"Remediation: change --project to {PROJECT_NAME_RULE}. "
                  f"The id is {derived}, and an explicit --id would not "
                  "change --project, which also names the assembly root and "
                  "both legs.")
    raise Refusal("adopt-bad-id",
                  f"{flag} is {project_id!r}, which must match {pattern}",
                  remedy)


def _names_held(naming: NamingPolicy, project: str, pins: set[str]) -> bool:
    """Whether the naming policy holds the three names `--project` makes, as
    `_check_names` asks it of `pins`, the products `--pin` declares (#902).
    `_checked_flag_inputs` refuses a passed `--id` that is no id only where
    it does; beside a name it refuses, the naming refusal speaks first."""
    try:
        _check_names(naming, _names(project), pins)
    except Refusal:
        return False
    return True


#: `adopt-bad-project-name` (#1014): an assembly root no Windows disk can make
#: a folder of. One code for the three subcommands, as `adopt-name-too-long`
#: is: `plan` asks it of `--project`, and `check` and `execute` of the plan's
#: `legs.assembly`, the name `execute` clones the root into a folder of.
BAD_PROJECT_NAME = "adopt-bad-project-name"
#: What the refusal's sentence says the name names, after "which names".
PROJECT_NAMES = "the assembly root and the folder `execute` clones it into"
#: And what it is told to do, in the words the scaffold gives
#: `scaffold-bad-project-name` and `family.py init` `family-bad-holder-name`
#: (#989), of what `--project` names here. A plan's name is mended by `plan`
#: again, which writes `project:`, `id:` and the three `legs:` from one
#: `--project`. Where the name is the source's own, adopted in place, it is
#: `_rename_first`'s way out, in its words: `plan` asks before it has read
#: the source, so it cannot yet say which of the two it is.
PROJECT_NAME_FIX = (
    "Run `plan` again with another --project. It names the assembly root, "
    "and so the folder `execute` clones the root into and the folder every "
    "clone of it is made in; and a root is cloned on Windows too, where no "
    "file or folder can be called a device name (`CON`, `PRN`, `AUX`, "
    "`NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, in any case, with or without an "
    "extension), and a name ending in a dot or a space is made under another "
    "name. Where --project is the source's own name, it cannot be changed "
    "here: an in-place adoption keeps the source's own name, and whether to "
    "rename the source is a human's decision, made first on GitHub (`gh "
    "repo rename`); then run `plan` again against the renamed repository, "
    "with its new name as --project.")


def _refuse_a_root_no_disk_holds(name: str, flag: str, made: str) -> None:
    """`adopt-bad-project-name`: `name`, the assembly root's, as `flag`
    names it, is one a Windows disk can make a folder of, or this refuses
    it, saying `made` (what was not made) before `PROJECT_NAME_FIX` (#1014).

    The question is `shape_materialize.refuse_an_unholdable_name`, the one
    the scaffold asks of its `--project` and `family.py init` of `--family`
    (#989): a Windows device name, with or without an extension, in any case
    (`NUL`, `Con`, `com1`, `Lpt9`), a name ending in a dot or a space, or one
    of Git's own names. `plan --project NUL` wrote a plan, and `check` said
    `plan ok` over it, for a root those two refuse. A device name is the
    WHOLE name: `Nullable`, and the legs `NUL-spec` and `NUL-code`, are
    folders Windows makes, so only the root's name is asked. It starts no
    process."""
    refuse_an_unholdable_name(BAD_PROJECT_NAME, flag, name,
                              names=PROJECT_NAMES,
                              remediation=f"Remediation: {made} "
                                          f"{PROJECT_NAME_FIX}")


#: What `plan` says after `checked_value`'s remedy when the value refused is
#: the source's own branch, which nobody passed (#797, L1-71's first case on
#: #457). The alphabet alone said nothing of the way past it, which works.
DEFAULT_BRANCH_WAY_PAST = (
    "The source's branch can keep its name: the source is read at it as it "
    "is, and only the tracking branch is held to that pattern, since "
    "`execute` pushes both legs to it and opens the split's pull request "
    "against it. So make a branch whose name matches at the same commit, in "
    "the source with that branch checked out (`git branch main`, and `git "
    "push origin main` where the source has a remote `origin`), and pass "
    "it: `--tracking-branch main`.")


def _checked_default_branch(what: str, branch: str) -> str:
    """`checked_value(what, branch)` of the source's default branch, which
    `plan` takes as the tracking branch when none is passed, its refusal
    saying the way past it too (`DEFAULT_BRANCH_WAY_PAST`)."""
    try:
        return checked_value(what, branch)
    except Refusal as refused:
        raise Refusal(refused.code, refused.detail,
                      f"{refused.remediation} {DEFAULT_BRANCH_WAY_PAST}"
                      ) from None


def _checked_plan_inputs(args, source: Source,
                         naming: NamingPolicy) -> tuple[dict, list]:
    """Every value the plan will RECORD, defaulted and checked before one of
    them is written. Returns `(names, pins)`, `pins` being
    `declared_pin_values`'s `{product: PIN_* values}`, each digest read.

    Split out of `cmd_plan` for #138, and the order inside it is the order the
    refusals came in: a run that got as far as naming the three legs before it
    refused an unparseable `--elected-on` would send a reader looking in the
    wrong place for the line that was wrong. The refusals of a passed flag's
    own value are asked before this, before the source is read
    (`_checked_flag_inputs`, #903); what is here needs the source, or the
    value a flag's default stands for, or is asked of the values as the plan
    will record them (`naming-unclassified`, an empty `--elected-by`).
    """
    # Which of the flags `plan` fills in by itself were passed: a value it
    # filled in is named by where it came from, should it be refused below.
    # PASSED IS ON THE COMMAND LINE, `''` INCLUDED (L2-53), as #479 reads
    # `--tracking-branch`: `--id ''` and `--elected-by ''` were read as not
    # passed, so `--id "$ID"` with `ID` unset planned the derived id, and an
    # empty elector became `git config user.name` though `--help` says "not
    # blank". Each is a value typed, held to its flag's own rule below and
    # refused there by name. So is `--org ''` since #902 (L2-86 on #457):
    # this set counted it passed while `_planned_org` read it as no `--org`,
    # so one refusal named `--org is '~x'`, a value nobody typed, and
    # another said `--org` was not given.
    flags_given = {key for key in FLAG_DEFAULTS
                   if getattr(args, key) is not None}
    products = set(declared_pin_products(args))
    # THE SOURCE'S OWN BRANCH, WHERE NONE IS NAMED (#479): the branch `plan`
    # reads the source at is the one its pull request can be opened against.
    # A default this tool filled in is named by where it came from, as
    # `--elected-by` is below, and not as a flag the person never passed.
    # One that was passed was held to its rules before the source was read
    # (`_checked_flag_inputs`). Git's own question (#420) is asked of the
    # default too: a branch name inside that alphabet that git will not
    # create is refused here, in git's words.
    if args.tracking_branch is None:
        tracking = _flag_named(TRACKING_KEY, set())
        args.tracking_branch = _checked_default_branch(tracking,
                                                       source.branch)
        refuse_bad_branch("adopt-bad-tracking-branch", tracking,
                          args.tracking_branch)
    # Whether `--id` was passed is read BEFORE it is filled in: a refusal of
    # the id names where it came from (#601), and says what to change. An
    # `org/repo` source was asked it before it was cloned, and passes here.
    # A passed one that is no id reaches here only beside a name the naming
    # policy refuses, which is refused first (#902), as `_check_names` asks
    # it below, with the source.
    args.id = args.id if "id" in flags_given else args.project.lower()
    _refuse_bad_id(args.id, args.project, flags_given, source, naming,
                   products)
    # The organisation, given or read from the source's `origin`, and named
    # by which of the two it is should it be refused (#292, #427). Given is
    # on the command line, `''` included (#902), as `flags_given` reads it.
    org_given = args.org is not None
    args.org = _planned_org(args.org, source)
    # IN PLACE, THE SOURCE'S OWN NAME (#499), as soon as both halves are
    # known and before any pin's digest is read: `execute` acts on the
    # repository `--org` and `--project` name, so they must be the source.
    # An `org/repo` source was asked before it was cloned
    # (`_refuse_a_clone_of_another_repository`) and passes here again.
    _refuse_another_repository(args, source, naming, products, org_given)
    # A DATE OR A REFERENCE PASSED EMPTY IS A VALUE (#902, L2-87 on #457):
    # read by its truth, `--elected-on ''` recorded today's date and
    # `--reference ''` the default reference, exit 0, where `--tracking-branch
    # ''` is refused. Each is read by `is not None`, as `--id` and
    # `--elected-by` are (L2-53): an empty date was refused with the flags
    # (`_checked_flag_inputs`), and an empty reference is the project's own
    # validator's to refuse (`_refuse_unholdable_values`).
    args.elected_on = (args.elected_on if args.elected_on is not None
                       else _dt.date.today().isoformat())
    args.reference = (args.reference if args.reference is not None
                      else default_reference(args.elected_on))
    # A value `plan` filled in by itself is named by where it came from, as
    # #181 names one, and not as a flag the person never passed. A passed
    # `--elected-by` was asked with the other flags' values already.
    if ELECTED_BY_KEY not in flags_given:
        args.elected_by = _elector()
        _refuse_unwritable_flag_values(
            [(_flag_named(ELECTED_BY_KEY, flags_given), args.elected_by,
              ROOT_MANIFEST_AND_README)])
    names = _names(args.project)
    pins = _as_planned(declared_pin_values(args), args.pin_source)
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


def _refuse_unwritable_flag_values(fields) -> None:
    """`adopt-unwritable-value` for each `(what, value, where)` of `fields`
    that `execute` could not write into a file, in the words `check` would
    use (#255); nothing, where every one can be held. `plan` asks it twice
    (#903): of the values it was passed, before anything exists
    (`_checked_flag_inputs`), and of the elector it reads from `git config
    user.name` where `--elected-by` was not (`_checked_plan_inputs`)."""
    unwritable = unwritable_values(fields)
    if unwritable:
        raise Refusal("adopt-unwritable-value",
                      " ".join(f"{problem}." for problem in unwritable),
                      "Remediation: no plan was written. Pass each value "
                      "named again, retyped; when `--elected-by` is not "
                      "given, `plan` reads `git config user.name`, so pass "
                      "the flag or correct that. " + WRITTEN_AS_TEXT)


def _checked_flag_inputs(args, naming: NamingPolicy) -> None:
    """The refusals of a passed flag's own value, which `plan` makes from
    its flags ALONE, in the order `_checked_plan_inputs` asked them, before
    anything exists (#903): no work directory is made, no `git` reads the
    source and no `gh repo clone` runs. `--pin-source` and `--out` were
    asked first already (#450, #451, #799), and an `org/repo` source's own
    name, and the id derived from `--project`, follow once `--source` is
    read (`_refuse_a_clone_of_another_repository`). Each refusal keeps its
    code and its words; only WHEN it is asked changed. On main they came
    after `_work_root`, `Source.open` and, for an `org/repo` source, the
    clone: with a stub `gh` that exits 97, a `--spec-path spec/` was
    `source-unclonable` and never `adopt-bad-leg-path`.

    The values it checks stay on `args`, as `_checked_plan_inputs` keeps
    the rest, and what it asks of a flag that has a default waits for the
    value: a `--tracking-branch` nobody passed is the source's own branch,
    an `--id` nobody passed is `--project` lowercased, an `--org` nobody
    passed is the source's, and an `--elected-by` nobody passed is `git
    config user.name`. Those are `_checked_plan_inputs`', which reads the
    source.

    NOT EVERY REFUSAL A FLAG DECIDES IS HERE. Still after the source, for
    an `org/repo` source as for a local one: `naming-unclassified` and
    `naming-role-mismatch`, which `_check_names` asks of the names
    `--project` makes, with a remedy about the source; an empty
    `--elected-by`, which is a value `unwritable_values` holds and the
    manifest validator refuses (`adopt-manifest-invalid`, in
    `_refuse_unholdable_values`), and an empty `--reference` with it
    (#902); and a missing `--path-policy` (`yaml-unreadable`). A passed
    `--id` that is no id is here only where `naming` holds the names
    `--project` makes (`_names_held`, #902): beside a name it refuses, the
    naming refusal speaks first, and its remedy needs the source.
    """
    args.project = checked_value("--project", args.project)
    # A `--tracking-branch` that was passed: PASSED IS ON THE COMMAND LINE,
    # `''` INCLUDED, as #479 reads it. Git's own question follows
    # `checked_value` (#420): a name inside its alphabet that git will not
    # create (`a..b`, `~`, `x.lock`, `a/`) is refused here, in git's words,
    # and is not written for `check` to find it no branch of the source and
    # the plan to be written again. That question is asked of a throwaway
    # repository in the system temp folder, which it removes, and never of
    # the source.
    if args.tracking_branch is not None:
        tracking = _flag_named(TRACKING_KEY, {TRACKING_KEY})
        args.tracking_branch = checked_value(tracking, args.tracking_branch)
        refuse_bad_branch("adopt-bad-tracking-branch", tracking,
                          args.tracking_branch)
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
    # A `--project` NO WINDOWS DISK CAN MAKE A FOLDER OF (#1014), in the
    # order #972 set for the scaffold and `init`: the naming refusal first,
    # then this one, then a passed `--id`'s sentence. The naming policy is
    # asked after the source is read, its remedy needing the source, so this
    # is asked only of names it holds (`_names_held`): one it refuses too
    # (`NUL.git`, `Nul.`) is left to the refusals asked after the source, as
    # on main. Before the work directory, the source, `gh` and the plan
    # file, as the scaffold asks it before anything exists.
    held = _names_held(naming, args.project, set(products))
    if held:
        _refuse_a_root_no_disk_holds(args.project, "--project",
                                     PLAN_NOT_WRITTEN)
    # An `--id` that was passed is held to its rule here, named as the flag
    # (#601): that branch of `_refuse_bad_id` reads no source, so it is
    # given none. One derived from `--project` is refused where the source's
    # own name is known, for its remedy names that: right after `--source`
    # is read, for an `org/repo` one, and after git has read the `origin`
    # of a local one. AND ONLY WHERE THE NAMING POLICY HOLDS THE NAMES
    # `--project` MAKES (#902): a refused name speaks before a passed id,
    # and its remedy names the source where `--project` is the source's own
    # name, so a passed id beside such a name is refused where the source
    # is known, as the derived one is (`_refuse_bad_id`).
    if args.id is not None and held:
        _refuse_bad_id(args.id, args.project, {"id"}, None, naming,
                       set(products))
    # An `--org` that was passed, as `_planned_org` holds it, `''` included
    # (#902): an empty one is a value passed, refused by name. One that was
    # not is the organisation of the source's name, read there.
    if args.org is not None:
        checked_value(_flag_named("org", {"org"}), args.org)
    # Read before the plan is written, whether or not it is what chooses the
    # reference: a date the tools cannot parse would reach `execute` as a
    # manifest field instead of as a question. One nobody passed is today's,
    # which `_checked_plan_inputs` fills in; `''` was passed (#902).
    if args.elected_on is not None:
        election_date(args.elected_on)
    # Before the plan is written, in the words `check` would use (#255): a
    # value `execute` writes into a file must be text one can hold. Of the
    # values that were passed alone: an elector `plan` reads from `git
    # config user.name` is asked in `_checked_plan_inputs`, after the
    # source, and a reference it chooses is text it holds. An `--elected-by
    # ''` and a `--reference ''` are values typed (#902) and text one can
    # hold, so each passes here and is refused by the manifest validator,
    # after the source (`adopt-manifest-invalid`).
    passed = [(_flag_named(key, {key}), value, ROOT_MANIFEST_AND_README)
              for key, value in ((ELECTED_BY_KEY, args.elected_by),
                                 (REFERENCE_KEY, args.reference))
              if value is not None]
    _refuse_unwritable_flag_values(passed)


def _org_read_from(source: Source) -> str:
    """Where `plan` read the organisation it records when `--org` is not
    given (#427): the `org/repo` it cloned as `--source`, or the source's
    `origin` (`Source.repository`)."""
    return "`--source`" if source.cloned else "the source's `origin`"


def _planned_org(org: str | None, source: Source) -> str:
    """The organisation the plan records: `--org`, or, where it is not
    given, the one the source names (`_org_read_from`); held to
    `checked_value` either way, which hands back the text.

    NO ORG IS `adopt-no-org`, asked before `checked_value` (#292). The `-`
    that once stood in for a missing one reached `checked_value` first,
    which refused `--org is '-'`, a value nobody passed; this refusal was
    never reached. A source with no `origin`, one whose URL is not UTF-8 or
    ends in no `org/repo`, and one whose `origin` is a path, which names no
    repository (`url_repository`, #521), all name no org, and the refusal
    says each: it is asked of a source that HAS an origin as often as of one
    that has none.

    AN ORGANISATION `plan` READ IS NAMED BY WHERE IT CAME FROM (#427). A url
    can end in any text -- `caf%C3%A9`, `-evil`, a space -- and
    `checked_value` refused it as `--org is 'café'`, a flag nobody passed,
    with a remedy about a leading `-` and a character class. It is `--org
    (not given, so the organisation of the source's `origin`)`, as
    `--elected-by` is named when `git config user.name` filled it in, and
    the remedy says first to pass `--org`. The refusal and its exit code
    stay: `plan` never puts such a value on a command line.

    AN `--org ''` IS A VALUE PASSED (#902, L2-86 on #457). Read by its truth,
    it was taken for no `--org`, so the organisation of the source's
    `origin` was planned, and named as `--org is '~x'` by one refusal and as
    `--org` not given by another. It is held to `checked_value` as passed,
    which refuses it by name, as it refuses `--tracking-branch ''`.
    """
    if org is not None:
        return checked_value("--org", org)
    read = (source.repository or "/").split("/")[0]
    if not read:
        raise Refusal(
            "adopt-no-org", "the source's `origin` names no organisation "
            "this tool can read: it has none, its URL is not UTF-8 or ends "
            "in no `org/repo`, or it is a path, which names no repository on "
            "GitHub",
            "Remediation: pass --org <org>.")
    where = _org_read_from(source)
    try:
        return checked_value(
            f"--org (not given, so the organisation of {where})", read)
    except Refusal as exc:
        said = (exc.remediation.partition("Remediation: ")[2]
                or exc.remediation)
        raise Refusal(
            exc.code, exc.detail,
            "Remediation: pass --org <org>; without it, `plan` reads the "
            f"organisation from {where}. {said[:1].upper()}{said[1:]}"
        ) from exc


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


def _refuse_an_unrecordable_pin_source(source: Path) -> None:
    """`--pin-source` is a path `plan` can record, or this refuses it as
    `adopt-unwritable-value`, before anything is made, before any digest is
    read and before a plan is written: `cmd_plan` asks it straight after
    `refuse_an_unread_pin_source`, for it needs the flags alone, so no work
    directory, git process or `gh repo clone` has come first.

    `plan` records the path in each pin's `digest_source:` in the plan, so
    that `check` can recompute the digest in that clone (#449), and `check`
    holds it to `one_printable_line` (`_a_digest_source`). A path holding a
    line break, an ESC or a byte that is not UTF-8 was planned, exit 0, and
    printed raw in `plan`'s report -- the line break split it -- and `check`
    then found `plan-pin-malformed` and said to re-run the `plan` that wrote
    it. So `plan` asks `check`'s question of the value it would record, and
    says why in #270's words (`unwritable_reason`) where they name it; the
    one thing `check` refuses that they do not is an invisible formatting
    character, a zero-width joiner among them. The `local-clone (` and `)`
    that `_as_planned` puts around the path are printable, so the path alone
    decides.

    THE PIN FILE NEVER HOLDS THE PATH (#540): `execute` writes `local-clone`
    there, so this is about the plan alone, and the scaffold, which records
    no path, scaffolds from such a clone (#450).
    """
    text = str(source)
    if one_printable_line(text):
        return
    reason = (unwritable_reason(text)
              or "it holds an invisible formatting character")
    raise Refusal(
        "adopt-unwritable-value",
        f"--pin-source is {text!r}, which `plan` records in each pin's "
        "`digest_source:` in the plan, for `check` to recompute the digest "
        f"in that clone, and {reason}.",
        "Remediation: no plan was written. Point --pin-source at a clone "
        "whose path is one line of printable UTF-8 text, or drop "
        "--pin-source and let `gh api` read the forge. `check` refuses a "
        "`digest_source:` that is not one printable line as "
        "`plan-pin-malformed`.")


def _as_planned(pins: dict, pin_source: Path | None) -> dict:
    """`declared_pin_values`'s pins as `plan` records them: a digest read
    from a `--pin-source` clone records where, `local-clone (<the path as
    typed>)`, so that `check` and `execute` recompute it in that clone
    (#449). `declared_pin_values` says `local-clone` alone, as the pin file
    does (#540): the plan is a file on this machine, which nothing commits,
    and the pin file is the one written from it (`_recorded_pins`)."""
    if pin_source is None:
        return pins
    where = f"{DIGEST_FROM_CLONE} ({pin_source})"
    return {product: {**values, "PIN_DIGEST_SOURCE": where}
            for product, values in pins.items()}


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
    is, by the function `execute` asks after the plan's three repository
    names, which both commands ask earlier (`plan.names()`), and before the
    plan's leg paths and branch names (`_checked_org_and_id`, #901), so a bad
    date beside a bad organisation or id does not make `check` and `execute`
    name different problems first.
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
    # The organisation and the id are asked BEFORE the date's guard below,
    # and as `execute` asks them, after the three repository names above
    # and before the leg paths and the branch names (#901): `unsafe-value`
    # for an `org:` this tool will not put on a command line, and
    # `plan-bad-id` for an `id:` that is not a project id
    # (`_template_table` reads it again). After the guard, neither was asked
    # of a plan whose date is a finding: `check` listed the date where
    # `execute` refused the organisation, and refused the id where `execute`
    # refused the date.
    org = _checked_org_and_id(plan)
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

    A MANIFEST THE READER MAKES NO MAPPING OF is one finding about no value
    (`KIND_NOT_A_MAPPING`, #1059): its remedy is the one for a defect of the
    copy of the standard, which `PROJECT_MANIFEST.remediations` gives the
    kind, and it has no sentence about the plan's values, none of which is
    at fault.
    """
    naming = NamingPolicy.load(NAMING_POLICY)
    values = _manifest_values(plan, naming)
    if values is None:
        return [], []
    problems = manifest_value_problems(values, naming, _named_as_read(plan),
                                       misreads=False,
                                       ignore=_validator_ignores(plan))
    if not problems:
        return [], []
    # The remedy is the kind's own: where the project's own YAML reader
    # refuses the manifest, the words are the reader's, and so is the remedy
    # (#708); where it reads the template's manifest as something other than
    # a mapping, no value is at fault and only the template is, so the remedy
    # is the defect-of-the-standard one and the sentence about the plan's
    # values is left out (#1059).
    kind = problems[0][0]
    values_tail = (
        "" if kind == KIND_NOT_A_MAPPING
        else " `execute` writes the plan's values into the project's "
        "`project.yaml` as they stand, so correct each one named here in "
        "the plan, or re-run `plan` with a value the validator accepts.")
    return ([f"FINDING plan-manifest-invalid: {sentence}"
             for _, sentence in problems],
            [f"{PROJECT_MANIFEST.remediations[kind]}{values_tail}"])


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
    return manifest_judged(values, naming, ignore=_validator_ignores(plan))


#: The validator's finding about `tracking_branch:` (#455), which `check`
#: leaves to `unsafe-value` wherever that names the branch (#708).
TRACKING_BRANCH_CODES = ("manifest-tracking-branch",)
#: The validator's finding about a `neutral_product_pins:` entry (#714),
#: which `check` leaves to `_read_pins` wherever that names an entry (#901).
PIN_ENTRY_CODES = ("manifest-neutral-product-pins",)


def _validator_ignores(plan: Plan) -> tuple:
    """The codes of the validator's findings `check` leaves out, because a
    rule of its own names the same value: a leg path's always
    (`LEG_PATH_CODES`), the tracking branch's where `checked_value`
    refuses that branch, which `_branch_name_findings` reports as
    `unsafe-value` (#708), and a pin's where `_read_pins` finds the plan's
    `pins:` (#901).

    ONE BAD `tracking_branch` IS ONE FINDING. Since #644 (#455) the
    validator finds a NUL or a lone surrogate in it, and `check` asks the
    validator, so `tracking_branch: "a\\x00b"` was `unsafe-value`, and
    then `plan-manifest-invalid` again in the validator's words, which
    name no plan key. No such value is in `checked_value`'s alphabet, so
    `unsafe-value`, `execute`'s own refusal of it, names every one, and
    the validator's sentence is left out where it does. `checked_value`
    alone is asked, the value `execute` reads (`_branch_name_refusal`'s),
    because the validator's question starts no process (git's verdict on
    a name is `_branch_name_findings`' own).

    ONE BAD PIN IS ONE FINDING TOO (#901). A pin edited to `product:
    "a\\t"` was `plan-pin-malformed`, `plan-unwritable-value` and then
    `plan-manifest-invalid` in the validator's words, three findings about
    one value. The validator refuses a `neutral_product_pins:` entry that
    is blank or holds a character that is not printable, and `_read_pins`
    passes no such product, for it holds each to `PIN_ARG_RE`'s alphabet:
    every entry the validator refuses is one `_read_pins` names, with the
    `plan` that records the pin whole, the remedy, and `execute` refuses a
    plan holding it before any leg exists. So wherever `_read_pins` finds
    the plan's `pins:`, the validator's sentence about an entry is left
    out, as #181 leaves such a plan's pins (`_plan_fields`) and #255 asks
    only the pins `execute` writes (`_plan_values`).
    """
    ignored = LEG_PATH_CODES + (PIN_ENTRY_CODES if _read_pins(plan)[1]
                                else ())
    try:
        checked_value(TRACKING_KEY, plan.get(TRACKING_KEY, "main"))
    except Refusal:
        return ignored + TRACKING_BRANCH_CODES
    return ignored


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
                       follow_ups: list, seeded: list,
                       pins: dict | None = None) -> None:
    """What `plan` says to the terminal once the file is on disk.

    Split out of `cmd_plan` for #138. THE UNRESOLVED PATHS ARE LAST on
    purpose: they are the one part of this report somebody has to act on, and
    a question printed above a summary table is a question that gets scrolled
    past. `plan written to` is NOT in it: `cmd_plan` prints that line the
    moment the file is written, before this report reads anything more of the
    source, so a read that fails here (`symlink_targets`' `git cat-file
    --batch`) still leaves the line that says the plan exists (#799).
    """
    print(f"source     {_source_named(source)} @ {source.commit[:12]} "
          f"({source.branch}), {len(tree)} files, "
          f"{source.commit_count()} commits")
    print(f"project    {args.project} ({args.id}) in {args.org}, mode in-place")
    # Each pin as the scaffold's plan prints it: what is pinned, at which
    # commit and digest, the file `execute` writes, and how the digest was
    # read (#273), as that file will say it: `local-clone`, and not the
    # clone's path, which the plan records beside it for `check` (#540).
    for product, values in (pins or {}).items():
        print(f"pin        {values['PIN_REPOSITORY']} @ "
              f"{values['PIN_COMMIT'][:12]} tree "
              f"{values['PIN_TREE_SHA256'][:12]}… -> "
              f"{neutral_pin_path(product)} "
              f"({_digest_source_written(values['PIN_DIGEST_SOURCE'])})")
    _print_triad_advisory(source.path, source.commit)
    _print_entries(entries)
    _print_summary(entries)
    print(f"\nfollow-ups ({len(follow_ups)}):")
    for item in follow_ups:
        print(f"  - {_shown(item)}")
    for line in seeding_warnings(seeded, set(args.allow_empty_leg or [])):
        print(line)
    for line in _kept_collision_notes(args, entries, tree):
        print(line)
    for line in _empty_symlink_notes(tree, symlink_targets(source, tree)):
        print(line)
    for line in _tracking_branch_notes(args, source):
        print(line)
    for line in _path_origin_notes(args, source):
        print(line)
    unresolved = [e for e in entries if e.leg is None]
    # A default is still a question (#528): it is printed with the question,
    # before the paths `execute` refuses over, which stay last. The question
    # is a path policy's, which `--path-policy` may name and which nothing
    # asks to be printable, so it is `_shown`, as `check`'s `plan-unresolved`
    # prints it (#900).
    proposed = [e for e in entries if e.leg is not None and e.review_required]
    if proposed or unresolved:
        print()
    if proposed:
        print(f"{len(proposed)} path(s) carry their rule's default answer, "
              "which `execute` takes as written unless it is changed:")
        for entry in proposed:
            print(f"  {_shown(entry.path)} (leg: {entry.leg})\n"
                  f"      {_shown(str(entry.question))}")
    if unresolved:
        print(f"{len(unresolved)} path(s) need a human or an AI to answer a "
              "question before `execute` will run:")
        for entry in unresolved:
            print(f"  {_shown(entry.path)}\n"
                  f"      {_shown(str(entry.question))}")


def _source_named(source: Source) -> str:
    """The source as `plan`'s `source` line names it. A clone `plan` made
    is its repository. A source read in place is its directory, with the
    repository its `origin` names beside it (#796): on main the line named
    only that repository, so it read the same whatever directory of it was
    read, a directory inside it included."""
    if source.cloned:
        return str(source.repository)
    where = _shown(str(source.path))
    if source.repository:
        where += f" (origin: {_shown(source.repository)})"
    return where


#: The code `plan` refuses an `--out` it cannot write under (#799), whether
#: it asks before any work or the write itself fails; and what both say to
#: do, after `PLAN_NOT_WRITTEN`.
OUT_UNWRITABLE = "adopt-out-unwritable"
OUT_FIX = ("Pass an --out that names a file in a folder this user can write "
           "in, making the folder first if it is not there.")
#: A write that fails for want of room (no space, a quota, an I/O error, a
#: file too large) may have cut the file it opened short: that is all it
#: adds to the way out, with its own remedy.
OUT_NO_ROOM = frozenset(
    getattr(errno, name) for name in ("ENOSPC", "EDQUOT", "EIO", "EFBIG")
    if hasattr(errno, name))
OUT_NO_ROOM_FIX = ("Free space, or pass an --out on another file system. If "
                   "the write began, what now lies at that path is cut short "
                   "and is not a plan.")


def _out_refusal(args, why: str, fix: str = OUT_FIX) -> Refusal:
    """`adopt-out-unwritable` for `why` the plan cannot be written at the
    `--out` as it was typed; `fix` is the way out."""
    return Refusal(OUT_UNWRITABLE,
                   f"--out {_spelled(str(args.out))} cannot be written: {why}",
                   f"Remediation: {PLAN_NOT_WRITTEN} {fix}")


def _out_folder(out: Path) -> str:
    """The folder `out` goes in, as it was typed and made absolute: with
    `absolute` and not `os.path.abspath`, which collapses `nope/..` as text,
    so a folder that exists is never called missing for a path the kernel
    would not have walked through."""
    return _spelled(str(out.parent.absolute()))


def _the_work_dir(args) -> Path | None:
    """The `--work-dir` as `_work_root` reads it, with `os.path.realpath`,
    or None where none was given."""
    if not getattr(args, "work_dir", None):
        return None
    return Path(os.path.realpath(args.work_dir))


def _out_is_the_work_dir(args, out: Path) -> bool:
    """Whether `out` is the `--work-dir` itself, which the run makes a
    folder where it is missing."""
    work = _the_work_dir(args)
    return work is not None and Path(os.path.realpath(out)) == work


def _first_missing_part(folder: Path) -> Path:
    """The first part of `folder`, walked as it was typed, that is not
    there, or `folder` itself where all of it is: a `..` steps back by
    name, as the kernel does through a folder that is there, and so `W/..`
    is missing while `W` is."""
    absolute = folder.absolute()
    walked = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        walked = walked.parent if part == ".." else walked / part
        if not os.path.lexists(walked):
            return walked
    return walked


def _out_is_made_by_this_run(args, out: Path) -> bool:
    """Whether the folder `out` goes in, found missing, is one this run
    makes and no other: the `--work-dir`, what is above it that `_work_root`
    makes with it (parents included), or `source-readonly` and the one
    folder `Source.clone` makes in it for an `org/repo` source. Read as
    `_work_root` reads the directory, with `os.path.realpath`, and asked of
    the folder and of the first part of it that is missing, so that a `..`
    which leads back to a folder above the `--work-dir` through one that
    nothing makes (`nope/..`) is not taken for one the run makes. A local
    source's `source-readonly/<name>` is not told apart from a clone's:
    nothing makes it, and the write refuses what it cannot make."""
    work = _the_work_dir(args)
    if work is None:
        return False
    clones = work / SOURCE_READONLY

    def made(path: Path) -> bool:
        path = Path(os.path.realpath(path))
        return (path == work or path in work.parents or path == clones
                or path.parent == clones)

    return made(out.parent) and made(_first_missing_part(out.parent))


def _why_out_cannot_be_written(args, out: Path) -> str | None:
    """Why the plan cannot be written at `out`, or None. THE QUESTION HAS NO
    SIDE EFFECT: nothing is made, opened or removed, because a probe that
    made the file would leave one where a later step refuses, and one that
    opened a file that is there would block on a pipe. It is asked of the
    file system with `os.path` and `os.access` alone, which answer False
    rather than raise.

    A FOLDER IS REFUSED FIRST, the `--work-dir` itself included, and so is
    anything there that is not a regular file (a pipe, a device, a socket):
    the plan is a file `write_lf` makes and fills. `os.access` is the
    system's answer for the real user, a read-only mount included, and not
    what a full disk, a quota or a Windows ACL say, so `_write_the_plan`
    refuses, under the same code, whatever it cannot see. A symlink to
    nothing is left to the write, which follows it as it always did. A
    folder that is not there is left to the write only where this run makes
    it (`_out_is_made_by_this_run`): any other is refused here, before a
    clone."""
    if os.path.isdir(out) or _out_is_the_work_dir(args, out):
        return "it is a folder, and the plan is one file"
    if os.path.exists(out):
        return _why_the_file_there_is_no_plan(out)
    return _why_the_folder_holds_no_plan(args, out)


def _why_the_file_there_is_no_plan(out: Path) -> str | None:
    """Why what is at `out` cannot be rewritten as the plan, or None."""
    if not os.path.isfile(out):
        return ("what is already there is not a regular file, and the plan "
                "is one")
    if not os.access(out, os.W_OK):
        return ("the file already there cannot be written: this user has "
                "no write permission on it")
    return None


def _why_the_folder_holds_no_plan(args, out: Path) -> str | None:
    """Why a new file cannot be made in the folder `out` goes in, or None:
    it is missing (unless the `--work-dir` makes it), it is a file or lies
    under one, it cannot be reached, or this user may not write in it."""
    folder, where = out.parent, _out_folder(out)
    try:
        found = os.stat(folder)
    except FileNotFoundError:
        if _out_is_made_by_this_run(args, out):
            return None
        return f"the folder it goes in, {where}, does not exist"
    except NotADirectoryError:
        return f"the folder it goes in, {where}, is a file or lies under one"
    except OSError as exc:
        return (f"the folder it goes in, {where}, cannot be reached "
                f"({exc.strerror or exc})")
    if not stat.S_ISDIR(found.st_mode):
        return f"the folder it goes in, {where}, is a file or lies under one"
    if not os.access(folder, os.W_OK | os.X_OK):
        return f"this user cannot write in the folder it goes in, {where}"
    return None


def _refuse_an_unwritable_out(args) -> None:
    """Refuse an `--out` the plan cannot be written at, as
    `adopt-out-unwritable`, before anything exists (#799's L1-89)."""
    why = _why_out_cannot_be_written(args, Path(args.out))
    if why:
        raise _out_refusal(args, why)


def _write_the_plan(args, out: Path, text: str) -> None:
    """Write the plan at `out`, or refuse the write as
    `adopt-out-unwritable` where it fails after all: the folder went since
    `_refuse_an_unwritable_out` asked, a disk filled, or the name is too
    long for the file system (#799's L1-89). Only a failure for want of
    room says the file may be cut short."""
    try:
        write_lf(out, text)
    except OSError as exc:
        raise _out_refusal(
            args, f"writing it failed ({exc.strerror or exc})",
            OUT_NO_ROOM_FIX if exc.errno in OUT_NO_ROOM else OUT_FIX
        ) from None


def cmd_plan(args) -> int:
    # A `--pin-source` that names no path, `''`, which as a `Path` is the
    # directory this runs in, one no `--pin` will read, and one `plan` cannot
    # record, are refused FIRST, in this order (#451, #450): it names the
    # clone a pin's digest is read from, and with no `--pin` it changed
    # nothing and was never even asked about. They need the flags alone, so
    # they are asked before anything exists and before any process starts.
    # Asked in `_checked_plan_inputs`, the second came after `_work_root` had
    # made the work directory, which stayed behind, and after `Source.open`
    # had run git in the source or `gh repo clone` for an `org/repo` one
    # (rv540 F2), and so did the third (rv540c's item 1).
    args.pin_source = pin_source_path(args.pin_source,
                                      nothing_made=PLAN_NOT_WRITTEN)
    refuse_an_unread_pin_source(args.pin_source, args.pin,
                                nothing_made=PLAN_NOT_WRITTEN)
    if args.pin and args.pin_source is not None:
        _refuse_an_unrecordable_pin_source(args.pin_source)
    # `--out` is asked here too (#799's L1-89): it needs the flag and the
    # file system alone, and a plan that could not be written ended in a
    # traceback at the write, after the work directory was made, an
    # `org/repo` source cloned and the whole plan built.
    _refuse_an_unwritable_out(args)
    # Then the refusals of a passed flag's own value (#903): a leg path, a
    # `--pin`, `--elected-on`, a `--reference` and the rest of
    # `_checked_flag_inputs`. They were asked after the work directory was
    # made, git had read the source and an `org/repo` one was cloned, and
    # with a clone that failed they were never reached: no work directory
    # is made, git reads nothing of the source and no `gh` runs before
    # them. A passed `--tracking-branch` runs `git check-ref-format` in a
    # throwaway repository first, and never touches the source.
    # The naming policy is read first, a file of this checkout: a passed
    # `--id` is refused with the flags only where the names `--project`
    # makes are ones it holds (#902).
    naming = NamingPolicy.load(NAMING_POLICY)
    _checked_flag_inputs(args, naming)
    # What `--source` names, next, before the work directory is made
    # (#796): every refusal of it that needs none -- an empty value, a path
    # that is no repository's top level, a name `gh` cannot clone -- is
    # asked here, and only `git rev-parse` has run in a local source. On
    # main a file ended `plan` in a traceback after the `--work-dir` it was
    # given had been made, and that directory stayed.
    named = _source_spec(args.source)
    # An `org/repo` source names its repository before it is cloned, so
    # `--org` and `--project` are held to it here (#903). A local source
    # names it by its `origin`, which `_checked_plan_inputs` reads.
    repository = named[1]
    if repository is not None:
        _refuse_a_clone_of_another_repository(args, repository, naming)
    work_root = _work_root(args)
    # An `org/repo` source is cloned into the work directory, so one this
    # user cannot write in is refused before the clone, as `check` refuses
    # it (#650), in the words of what `plan` does there (#903). A local
    # source is read in place, and writes nothing there: the directory is
    # still made, because `--out` may lie in it, and refused where it
    # cannot be made, but it is not asked whether it can be written in.
    # The clone goes on `args.clones`, and `_leave_the_clones` removes it
    # unless this run ends having written the plan that records it (#652).
    # Read at `--tracking-branch` where its remote's default branch is no
    # branch of its own, a `git clone -b` (#797).
    unwritable = (None if repository is None else
                  _unwritable_work_dir(args, work_root,
                                       _plan_clones(repository)))
    source = Source.of(named, work_root, unwritable,
                       getattr(args, "clones", None),
                       instead=args.tracking_branch)
    policy = PathPolicy.load(args.path_policy or PATH_POLICY)

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
    follow_ups = follow_ups_for(source, implied, names, materialized)
    seeded = seeded_legs(assigned_paths(implied))
    entries = with_defaults(ask_about_refused_paths(
        ask_about_submodules(policy, ruled, tree), tree))
    out = Path(args.out)
    _write_the_plan(args, out, render_plan(args, source, entries, names, pins,
                                           follow_ups, seeded))
    # The plan that records the clone exists from here, whatever happens
    # next: `_leave_the_clones` keeps it, though the report below be cut
    # short by a closed pipe or Ctrl-C (#652's review, F2).
    args.plan_written = True
    # And it is SAID from here, before the report reads more of the source:
    # the report's last reads (`symlink_targets`) can still refuse, exit 2,
    # and the plan is on disk (#799's L1-79).
    print(f"\nplan written to {out}")

    _print_plan_report(args, source, tree, entries, follow_ups, seeded, pins)
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
    """`plan`'s table, one row to an entry.

    THE PATH IS PADDED AS IT IS PRINTED (#900): `_shown`, then as stdout
    writes it (`_printed`). Padded before stdout escaped it, `caf\\u00e9.md`
    was padded as the 7 characters it holds and printed as the 10 of
    `caf\\xe9.md` under `LC_ALL=C PYTHONUTF8=0`, so every column after it
    stood 3 characters right of its heading. The rule id is a path
    policy's, which `--path-policy` may name and nothing asks to be
    printable, so it is `_shown` as a question is.
    """
    print(f"\n{'path':<34} {'leg':<10} {'conf':<7} {'files':>6} {'rule'}")
    for entry in entries:
        print(f"{_printed(_shown(entry.path)):<34} "
              f"{(entry.leg or 'REVIEW'):<10} "
              f"{entry.confidence:<7} {entry.files:>6} "
              f"{_shown(str(entry.rule))}")


def _printed(text: str) -> str:
    """`text` as stdout writes it: each character its encoding cannot hold
    escaped, as `escape_what_stdout_cannot_encode` has it write one, so
    `caf\\u00e9.md` is the 10 characters of `caf\\xe9.md` on an ASCII
    stdout and the 7 of `caf\\u00e9.md` on a UTF-8 one (#900). It is asked
    of a text `_shown` returned, which holds no surrogate; where stdout
    names no encoding, or cannot encode `text` with its own handler, it is
    `text` as it is."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    errors = getattr(sys.stdout, "errors", None) or "strict"
    try:
        return text.encode(encoding, errors).decode(encoding)
    except (LookupError, UnicodeError):
        return text


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
              if _root_keeps(surviving, path)}
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

    @property
    def read_at(self) -> str | None:
        """The branch `plan` read the source at, `source.default_branch`, or
        None where the plan records none: where the source's remote's
        default branch is no branch of its own, `check` and `execute` read
        it there again (`_default_branch`'s `instead`, #797)."""
        branch = self.source.get("default_branch")
        return None if branch is None else str(branch)

    def open_source(self, override: str | None, work_root: Path,
                    unwritable: str | None = None,
                    made: list | None = None, done: str = "") -> Source:
        """The source `check` and `execute` read: `override`, read as `plan
        --source` reads it, or the one the plan records
        (`_recorded_source`). `unwritable` is why `work_root` cannot be
        written, `made` the list of clones the command removes when it ends,
        and `done` what `execute` says first in a way out, as `Source.clone`
        takes them.

        A RECORDED NAME IS ALWAYS CLONED FROM GITHUB, never read as a
        directory here (#652): on main `check`, run where `./acme/Atlas`
        existed, said the plan's repository is cloned again and read that
        directory instead.

        AN EMPTY `override` IS ONE GIVEN (#796), and `Source.open` refuses
        it: on main `check --source ''` and `execute --source ''` dropped it
        and read the plan's own source. So is an empty `local_path:`, which
        no `plan` writes, refused as `plan-source-gone`: on main it was read
        as no `local_path` at all, and the plan's `source.repository` was
        cloned from GitHub, a path the person gave or a gitlab clone's
        `origin` included, which `_recorded_source` never clones again."""
        if override is not None:
            source = Source.open(override, work_root, unwritable, made, done,
                                 self.read_at)
            self._keep_the_clone_at_the_record(made)
            return source
        local_path = self.source.get("local_path")
        if local_path == "":
            raise Refusal(
                PLAN_SOURCE_GONE,
                "the plan's `source.local_path` is empty: it names no path, "
                "and an empty path would be read as the directory this runs "
                "in", PLAN_SOURCE_GONE_REMEDY)
        if local_path:
            return self._recorded_source(str(local_path), work_root,
                                         unwritable, made, done)
        repository = self._recorded_repository()
        if repository is None:
            raise Refusal("plan-no-source",
                          f"{self.path}: `source:` names neither a local path "
                          "nor a repository")
        return Source.clone(repository, work_root, unwritable, made,
                            done=done, instead=self.read_at)

    def _keep_the_clone_at_the_record(self, made: list | None) -> None:
        """Take off `made` the clone this run made from `--source` where it
        is at the plan's own `source.local_path` (#803, #457's L1-97): it is
        the plan's source again, as the clone `_recorded_source` makes there
        is. On main `check` removed it, and the next run cloned it once
        more."""
        record = self.source.get("local_path")
        if not (made and record):
            return
        try:
            at = os.path.realpath(os.path.expanduser(str(record)))
        except (OSError, ValueError):
            return
        made[:] = [claim for claim in made
                   if not _same_spelling(claim.made_at, at)]

    def _recorded_repository(self) -> str | None:
        """The plan's `source.repository` as `_github_name` reads it, or None
        where it records none. One that names no `owner/repo` is refused, by
        its key: no `--source` was passed (#652)."""
        repository = self.source.get("repository")
        if not repository:
            return None
        name = _github_name(str(repository))
        if name is None:
            raise Refusal(
                SOURCE_UNRESOLVABLE,
                f"the plan's `source.repository`, {_shown(str(repository))}, "
                f"names no `owner/repo` on {GITHUB_HOST}", SOURCE_REMEDIATION)
        return name

    def _recorded_source(self, local_path: str, work_root: Path,
                         unwritable: str | None, made: list | None,
                         done: str = "") -> Source:
        """The source the plan's `source.local_path` records, read in place
        where it can be; or, where it is a clone `plan` made
        (`source.cloned: true`) that is gone or no longer whole, its
        `source.repository` cloned again, said in one NOTE (#526, #652).

        `plan --source <org/repo>` without `--work-dir` clones into the
        system temp folder and records that clone, and the system may clean
        it before `check` or `execute` runs: remove it, or, as macOS's
        cleaner does, empty it and keep its directories. On main a clone
        that was gone and recorded no repository was handed to `gh repo
        clone` as an `org/repo`, refused `source-unclonable` with a remedy
        about `gh auth status` (and on Windows `source-unresolvable`, naming
        a `--source` nobody passed); one emptied was refused `git-failed`;
        and one emptied inside another repository was read AS that
        repository. A clone made again at another commit is no plan's
        source: `check` finds `plan-stale` and `execute` refuses it.

        ONLY A CLONE `plan` MADE IS MADE AGAIN. A path the person gave, and
        a plan written before `cloned:` was recorded, is never cloned again:
        on main a moved clone of `gitlab.com/acme/Atlas` was cloned again
        from github.com as `acme/Atlas`. It is `plan-source-gone`, naming
        `--source` as the way past it.

        Where the work directory cannot be written (`unwritable`), nothing
        can be cloned into it: refused before the NOTE says it is (#650).
        Where the clone would land on the plan's own clone, no longer whole
        (the same `--work-dir`), it is refused, and nothing there is
        removed; where that path is free, the clone made there is the one
        the plan records, and is not on `made`.

        A PATH THE PERSON GAVE IS HELD TO BEING A REPOSITORY'S TOP LEVEL, as
        `--source` is (`_top_level`, #796), and refused by its key: a file
        ended `check` and `execute` in a traceback, and a directory inside a
        repository was read as the source. A `~user` this machine has not is
        a path that is not there (`os.path.expanduser`): `Path.expanduser`
        raised `RuntimeError` for it.

        A PATH THIS USER CANNOT REACH IS NEITHER GONE NOR CLONED AGAIN (#430).
        Whether it is there is asked as `_is_a` asks it, and a `stat` the
        operating system refused for another reason than that nothing is
        there (a directory above it this user cannot search) is
        `source-unreadable`, naming it. On Python 3.9 to 3.13 `Path.exists()`
        raised it, a `PermissionError` traceback; on 3.14 it answered False,
        so the path was `plan-source-gone`, "names nothing that exists", or,
        a clone `plan` made, "no longer exists" and was cloned again from
        GitHub beside the one still there."""
        path = Path(os.path.expanduser(local_path))
        try:
            there = _is_there(path)
        except OSError as exc:
            raise _source_unreadable(
                f"the plan's `source.local_path`, {_spelled(local_path)}", exc,
                ("whether `plan`'s clone is still there, to be read, or gone, "
                 "to be cloned again," if self.source.get("cloned") is True
                 else "whether the source is still there"),
                "pass the source again with --source, which is held to the "
                "plan's `commit:`") from exc
        if self.source.get("cloned") is not True:
            if there:
                return Source.in_place(_top_level(
                    path, f"the plan's `source.local_path`, "
                          f"{_spelled(local_path)},"), work_root, self.read_at)
            raise self._gone(local_path, "names nothing that exists",
                             "the plan does not record it as a clone `plan` "
                             "made (`source.cloned` is not `true`), so "
                             "nothing clones it again")
        broken = _not_a_whole_clone(path, self.source_commit) if there \
            else None
        if there and broken is None:
            return Source.in_place(Path(os.path.realpath(path)), work_root,
                                   self.read_at)
        state = (f"is a clone `plan` made that is no longer whole ({broken})"
                 if there else "no longer exists")
        repository = self._recorded_repository()
        if repository is None:
            raise self._gone(local_path, state, "the plan records no "
                             "`source.repository` to clone again")
        at_the_record = os.path.realpath(path) == os.path.realpath(
            work_root / SOURCE_READONLY / repository.split("/")[1])
        return Source.clone(
            repository, work_root, unwritable,
            None if at_the_record else made,
            note=(f"NOTE the plan's `source.local_path`, "
                  f"{_spelled(local_path)}, {state}, so its "
                  f"`source.repository`, {repository}, is cloned again from "
                  "GitHub, as `plan` cloned it."),
            taken=(f"the plan's `source.local_path`, {_spelled(local_path)}, "
                   f"{state}" if at_the_record and there else ""),
            done=done, instead=self.read_at)

    def _gone(self, local_path: str, state: str, why: str) -> Refusal:
        """`plan-source-gone`: the plan's `source.local_path` is in `state`,
        and `why` nothing clones it again (#652). The way out is `--source`.

        NO RECORDED NAME IS OFFERED. A `source.repository` the plan read from
        a clone's `origin` names its last two segments on whatever host that
        is, and the plan does not record the host: offering `--source
        testorg/Thing` "to clone it from GitHub" for a moved clone of
        gitlab.com/testorg/Thing named another repository (#652's review,
        N4). An `org/repo` is named only as what `plan` cloned from GitHub."""
        return Refusal(
            PLAN_SOURCE_GONE,
            f"the plan's `source.local_path`, {_spelled(local_path)}, "
            f"{state}, and {why}", PLAN_SOURCE_GONE_REMEDY)

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

        EACH REFUSAL NAMES WHAT THE PLAN HOLDS (#902). With no `id:`, the id
        is `legs.assembly` lowercased, and it is named so (`DERIVED_ID`), with
        `legs.assembly` as the remedy: the refusal said "`id:` is
        'north_wind'" of a plan with no `id:`, and sent the person to `--id`,
        though only a character no id takes makes a derived id bad, and the
        naming policy refuses that in `legs.assembly` whatever `id:` says
        (L2-88 on #457). An `id:` the plan's reader read as a number or a
        boolean (`id: 007`) was `str` of what was read, `7`, which the
        pattern takes: it is refused by what was read (L1-K3). And an `id:`
        the pattern refuses is told what an id may hold, as `plan` tells a
        passed `--id` (`PASSED_ID_REMEDIATION`).
        """
        set_id, pattern = self.get("id"), PROJECT_ID_RE.pattern
        if set_id is None:
            project_id = self.names()["assembly"].lower()
            if not PROJECT_ID_RE.match(project_id):
                raise Refusal(
                    "plan-bad-id",
                    f"{self.path}: {DERIVED_ID} is {project_id!r}, which "
                    f"must match {pattern}", DERIVED_PLAN_ID_REMEDIATION)
            return project_id
        if _a_number_or_boolean(set_id):
            raise Refusal("plan-bad-id",
                          f"{self.path}: {_not_text('id', set_id)}",
                          NOT_TEXT_REMEDIATION)
        project_id = str(set_id)
        if not PROJECT_ID_RE.match(project_id):
            raise Refusal(
                "plan-bad-id",
                f"{self.path}: `id:` is {project_id!r} and must match "
                f"{pattern}", PLAN_ID_REMEDIATION)
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


def _covering_names(path: str) -> list[str]:
    """Every name `_covering` can find covering `path`: each directory above
    it, with its `/`, then `path` itself (#655).

    For a caller holding many entries, who looks each of these up rather
    than holding every entry against every path."""
    return [path[:index + 1] for index, char in enumerate(path)
            if char == "/"] + [path]


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


def _leg_findings(plan: Plan, tree: list | None,
                  named_links: frozenset | set = frozenset()) -> list[str]:
    """`leg:` is answered with one of the four words, each leg's mount path
    is canonical (#169), and neither overlaps a path the assembly root holds
    (#172); and the root keeps nothing where the shape writes (#262, #263).
    `named_links` are the symlinks of the source that `plan-empty-symlink`
    and `plan-bad-symlink-target` name one by one (`_named_symlinks`, #908):
    one kept AT `project.yaml` is theirs, and `plan-root-blocks-manifest`
    leaves it.

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
        findings += _root_shape_findings(plan, tree, named_links)
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
# One whose target `plan-empty-symlink` or `plan-bad-symlink-target` names is
# those findings' alone, which then say where it sits (#908): `drop` cannot
# help a link no clone can make.
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
            "holds as a file naming its target; either way it would fail "
            if relation == "is" and mode == SYMLINK_MODE else
            f"{beside} and fail ")
        return (
            f"the plan keeps {_kind_of(mode)} {named} in the assembly "
            f"root{under}{spot}, where the shape writes its manifest. No "
            "copy stands in for the manifest: `shape-doctor.py`, the root's "
            f"validators and `make bootstrap` read {_first_and_more(rels)} "
            "at the root itself, and there they would find the source's "
            f"{found}. {written}its verification "
            "(`adopt-manifest-not-shape`), after both leg repositories were "
            f"created and pushed: {fix}.")
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


def _root_shape_findings(plan: Plan, tree: list,
                         named_links: frozenset | set = frozenset()
                         ) -> list[str]:
    """`check`'s findings for a path the plan keeps in the root where the
    shape writes (#262, #263): one per kept path in the way, naming the
    first shape path it blocks and counting the rest. Asked of a disk that
    keeps case and then of one that ignores it; a finding the first disk
    already made is not made again, and one only the second makes says so,
    and so does a copy only the second writes.

    THE COPY OF THE SHAPE'S PIN IS NOT ASKED where the root holds the pin
    itself (#651, L1-07 of #457). That is #524's `plan-root-holds-pin`
    (`_kept_pin_findings`), and the copy under `shape/` is only its
    consequence: with the kept path gone, the shape writes its pin at its
    own path and nothing at the copy's. A path kept at the copy as well was
    a second finding, `plan-root-blocks-shape-copy`, for one cause.

    A SYMLINK AT THE MANIFEST THAT `named_links` HOLDS IS LEFT OUT (#908,
    L1-80 of #457): `plan-empty-symlink` or `plan-bad-symlink-target` names
    it, says where it sits and ends with the remedy that helps, which is not
    this finding's `drop`: no answer in the plan ends either. One link, one
    finding."""
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
            if (code, rel, group) in seen or (
                    code == ROOT_BLOCKS_COPY and rel == SHAPE_PIN
                    and _holds_a_pin(disk, rel)) or (
                    code == ROOT_BLOCKS_MANIFEST and group[0] == "at"
                    and rows[0][0] in named_links):
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
# verification has nothing new to account for. Whether anything ANSWERS
# there is #418's question, asked below of the leg's resolution.
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
    "registration then stays behind in the leg, inert. `check` and "
    "`execute` resolve it from the leg remotes `execute` would create: the "
    "GitHub repositories the plan's `org:` names, or, under "
    "`--local-remote-dir`, the bare repositories there, which `check` asks "
    "only when given the same `--local-remote-dir`. `execute` resolves it "
    "again before it creates any leg.")


class _FromTheLeg(str):
    """A FINDING about a RELATIVE url as git resolves it from a leg's
    remote: #190's, and #418's of one that answers nothing there. Under
    `--local-remote-dir` `execute` resolves it from the bare repositories it
    would create, which `check` resolves it from only when given the same
    `--local-remote-dir` (#417), so its refusal says which `check` prints
    it (`_as_resolved_here`). A `str`, as `InTheHistory` is, so that every
    reader takes it as the line it is."""


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
        disk can add an answer and never take one away. Each is asked as
        the bytes it spells (`_path_argument`, #653).
        """
        if self.url is None or other.url is None:
            return False
        if remote_key(self.url) == remote_key(other.url):
            return True
        paths = [remote_local_path(url) for url in (self.url, other.url)]
        return None not in paths \
            and os.path.realpath(_path_argument(paths[0])) \
            == os.path.realpath(_path_argument(paths[1]))

    def __str__(self) -> str:
        # `redacted`: a source's remote may carry a token, and so does every
        # url resolved against it.
        return (f"to {_spelled(redacted(self.url))}" if self.url is not None
                else f"not at all ({self.said})")


def _kept_urls(entries: list, tree: list, registered: Registrations | str
               ) -> tuple[str | None, list[tuple[str, str, str]]]:
    """`(leg, [(path, entry, url), ...])`: each submodule the plan keeps in
    the leg its `.gitmodules` goes to, registered with a url, in the tree's
    order, and that leg. A submodule kept anywhere else, or not registered,
    is already a finding of `submodule_plan_problems`; a dropped one is
    inert; and a `.gitmodules` git cannot read has no url to read."""
    gitlinks = [path for path, mode, _, _ in tree if mode == GITLINK_MODE]
    if not gitlinks or isinstance(registered, str):
        return None, []
    answered = _answered_legs(entries, [GITMODULES, *gitlinks])
    leg = answered.get(GITMODULES, (None, None))[0]
    return leg, [(path, entry, registered.url(path)) for path, kept, entry
                 in _kept_in_a_leg(answered, gitlinks)
                 if kept == leg and path in registered]


def _kept_relative_urls(entries: list, tree: list,
                        registered: Registrations | str
                        ) -> tuple[str | None, list[tuple[str, str, str]]]:
    """`_kept_urls`, of the urls that are relative alone."""
    leg, kept = _kept_urls(entries, tree, registered)
    return leg, [(path, entry, url) for path, entry, url in kept
                 if RELATIVE_URL_RE.match(url)]


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
    every other base.

    The source's directory, the base or the working tree, is spelled as git
    spells the url beside it (`_git_spelling`), so `_resolved` and
    `same_as` hand both the bytes they name in any locale (#653)."""
    name = _config_value(source.path, f"branch.{source.branch}.remote") \
        or "origin"
    url = _config_value(source.path, f"remote.{name}.url")
    if url is None:
        return (_git_spelling(source.path.as_posix()),
                f"its own directory, as it has no remote {_spelled(name)}",
                None)
    if remote_is_a_path(url) and remote_local_path(url) is None:
        return (url, f"its remote {_spelled(name)}, relative to its working "
                "tree", Path(_git_spelling(str(source.path))))
    return url, f"its remote {_spelled(name)}", None


def _config_value(repository: Path, key: str) -> str | None:
    """`key` in `repository`'s git config, as git reads it -- the last
    value, when there are several; None when unset. The key as the bytes
    it spells (`_path_argument`): a remote's name in it is one git printed,
    and as text `remote.\\u00dcrsprung.url` raised `UnicodeEncodeError`
    under `LC_ALL=C PYTHONUTF8=0` (#653)."""
    got = subprocess.run(["git", GIT_CONFIG, "-z", "--get",
                          _path_argument(key)],
                         cwd=repository, capture_output=True, check=False)
    return None if got.returncode else _git_path(got.stdout.rstrip(b"\x00"))


def _resolved(base: str, urls: list[str],
              working_tree: Path | None = None) -> list[_Resolution]:
    """Each of `urls` as `git submodule init` resolves it in a repository
    whose `origin` is `base`, in a scratch repository made for the purpose
    and removed after it; and, given a `working_tree`, git's relative answer
    joined to it, which is what the clone opens (`_default_remote`). A url
    git cannot resolve is what git said: that is where the clone fails.

    `base` and each url reach git as the bytes they spell (`_run_exact`):
    as text, `../\\u00dcnterlagen` raised `UnicodeEncodeError` under
    `LC_ALL=C PYTHONUTF8=0`, and `check` and `execute` died (#653)."""
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-url-"))
    try:
        run(["git", "init", "-q", str(scratch)])
        _run_exact(["git", GIT_CONFIG, "remote.origin.url", base], scratch)
        for index, url in enumerate(urls):
            for key, value in (("path", f"u{index}"), ("url", url)):
                _run_exact(["git", GIT_CONFIG, "-f", GITMODULES,
                            f"submodule.u{index}.{key}", value], scratch)
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
                           ) -> tuple[list[str], list[str],
                                      dict[str, tuple[str, str]]]:
    """`(findings, notes, from_the_leg)` for the relative urls of the
    submodules the plan keeps in a leg: a `plan-submodule-relative-url`
    FINDING for each that git resolves to another repository from its leg
    than from the source, or cannot resolve from one of them; when there is
    none of those, the one NOTE `check` prints about what it could not know;
    and `{path: (remote, url)}` for each url that names one repository from
    both: the leg's remote, and the url git resolves from it, which #418
    asks (`_unanswered_url_findings`).

    THE LEG'S REMOTE IS THE ONE `execute` WOULD CREATE: under
    `local_remote_dir`, the bare repository there; otherwise the GitHub
    repository the plan's `org:` and leg name give. `check` takes the same
    `--local-remote-dir` (#417): given the one `execute` is given, it
    decides on the same remotes, and without one on GitHub's; `execute`
    decides again on the remotes it is about to create, before it creates
    any. They are read only when there is a relative url to resolve, and
    the NOTE says, where `check` resolved them all alike from GitHub's,
    that it was GitHub's it asked: a plan it passes there can still be
    refused by `execute --local-remote-dir`, as `check` given the same
    directory finds."""
    leg, kept = _kept_relative_urls(plan.entries, tree, registered)
    if not kept:
        return [], [], {}
    remote = _git_spelling(_remote_urls(checked_value("org", plan.get("org")),
                                        plan.names(), local_remote_dir,
                                        source)[leg])
    base, which, working_tree = _default_remote(source)
    urls = [url for _, _, url in kept]
    found, alike, from_the_leg = [], [], {}
    for (path, entry, url), here, there in zip(
            kept, _resolved(base, urls, working_tree),
            _resolved(remote, urls)):
        if here.same_as(there):
            alike.append(f"{_spelled(url)} of {_spelled(path)}, {there}")
            from_the_leg[path] = (remote, there.url)
            continue
        found.append(_FromTheLeg(
            f"FINDING {RELATIVE_URL}: the submodule {_as_entry(path, entry)} "
            f"has leg: {leg}, and its url in the source's {GITMODULES} is the "
            f"relative {_spelled(url)}, which git resolves against the remote "
            "of the repository holding that file: from the source, at "
            f"{_spelled(redacted(base))} ({which}), {here}, and from the "
            f"{leg} leg, at {_spelled(remote)}, {there}; the assembly's "
            "recursive clone resolves it from the leg"))
    if found or local_remote_dir is not None:
        return found, [], from_the_leg
    return [], [
        f"NOTE `check` resolved the relative url of each submodule the plan "
        f"keeps in the {leg} leg from that leg's GitHub remote, "
        f"{_spelled(remote)}, and each names the same repository from there "
        f"as from the source: {'; '.join(alike)}. `execute "
        "--local-remote-dir` resolves it again from the bare repository it "
        "would create instead, and refuses there, before it creates any leg, "
        "a url that names another repository; `check`, given the same "
        "`--local-remote-dir`, resolves it there too."], from_the_leg


# ---------------------------------------------------------------------------
# Whether the url of a kept submodule answers at all (#418)
# ---------------------------------------------------------------------------
#
# `adoption verified` accounts for blobs, and the `NEXT:` it prints is `git
# clone --recurse-submodules`, which clones each submodule a leg keeps from
# its url, as the leg resolves it. Nothing asked whether anything answers
# there. A dependency since moved or deleted, or a relative url that names
# the same empty place from the leg as from the source -- which #190 above
# takes as settled -- passed `plan`, `check` and `execute`, and that clone
# then failed, as the source's own recursive clone already did: after both
# leg repositories were made and the split was pushed.
#
# ASKED ON THIS MACHINE ALONE. Each url the plan keeps in a leg, as the leg
# resolves it and as git here expands it (`url.<base>.insteadOf`, read by
# `git ls-remote --get-url`, which contacts nothing), that names a
# repository on this machine's disk -- an absolute path, or a `file://` url
# with no host (`_on_this_disk`) -- is asked with `git ls-remote`, which
# needs no clone, under `GIT_ALLOW_PROTOCOL=file`, so that git can reach
# nothing else whatever it is configured to do. One that answers nothing is
# a FINDING of `check` and a refusal of `execute` before any leg exists.
# Under `--local-remote-dir` that is every relative url too, resolved from
# the bare repositories `execute` would create, and the answer is certain
# there. A url on a network is never asked: whether it answers can depend
# on whose credentials ask, and neither command makes a network call to
# find out, so `check` names each in a NOTE instead. A source whose kept
# submodules all name a network starts no git process here.
#
# ONE FINDING PER CAUSE. A relative url that names another repository from
# its leg, or that git cannot resolve from one side, is
# `plan-submodule-relative-url` alone and is not asked: the fix that finding
# names -- the absolute url committed in the source, or the submodule
# dropped -- comes first, and `check` asks the url it leaves when it runs
# again.

URL_ANSWERS_NOTHING = "plan-submodule-url-answers-nothing"
#: What a plan that keeps a submodule whose url answers nothing is told: by
#: `check`, once after its findings, and by `execute`'s refusal.
URL_ANSWERS_NOTHING_REMEDIATION = (
    "Remediation for a submodule url that answers nothing: the assembly's "
    "`git clone --recurse-submodules` clones each submodule a leg keeps from "
    "its url, as the leg resolves it, and fails where no repository "
    "answers, as the source's own recursive clone does. Commit a url that "
    "names the submodule's repository in the source's `.gitmodules` and "
    "re-run `plan`, or put that repository where the url names it, or "
    "`drop` the submodule: its registration then stays behind in the leg, "
    "inert. `check` and `execute` ask, with `git ls-remote`, only a url "
    "that names a repository on this machine's disk; a relative one is "
    "resolved from the leg's remote, which is on GitHub, or, under "
    "`--local-remote-dir`, the bare repository `execute` would create "
    "there.")
#: What `_answers` holds `git ls-remote` to: the disk, and no transport
#: that could reach a network.
ON_THIS_DISK_ONLY = {"GIT_ALLOW_PROTOCOL": "file"}
#: A Windows drive at the start of a path `remote_local_path` names, which
#: folds `\` to `/`: `C:` or `C:/...`.
DRIVE_RE = re.compile(r"[A-Za-z]:(?:/|\Z)")


def _on_this_disk(url: str) -> bool:
    """Whether git on THIS machine opens `url` as a repository on its own
    disk: an absolute path, or a `file://` url with no host
    (`remote_local_path`). A drive only on Windows, where git reads `C:/` as
    a drive; everywhere else it reads `C:` as the scp host `C`, which only a
    network can answer. A path relative to wherever the clone is made, such
    as `dependency`, is not one: nobody knows yet where that is. Nor, on any
    platform, is a path that starts with two separators, which
    `remote_local_path` spells `//server/share` for `\\\\server\\share`,
    `//server/share` and `file:////server/share` alike: Windows opens it as
    a share on another machine, over the network, with the credentials of
    whoever asks, and on POSIX `\\\\server` is a name relative to the
    clone."""
    path = remote_local_path(url)
    return path is not None and not path.startswith("//") and (
        os.name == "nt" or DRIVE_RE.match(path) is None)


def _answers(urls: list[str]) -> list[tuple[str, str | None]]:
    """`(expanded, said)` for each of `urls`: the url as git here expands it
    (`git ls-remote --get-url`, which contacts nothing) and, where that is
    on this machine's disk, None when `git ls-remote` reaches a repository
    there and the first line git said when it does not. An expansion that
    leaves the disk is not asked, and its `said` is None.

    Asked in a scratch repository made for the purpose, as `_resolved` asks
    its questions, so that no repository's own config around this process
    rewrites a url as the assembly's clone would not; and under
    ON_THIS_DISK_ONLY, so that nothing a config could do sends git to a
    network. Each url as the bytes it spells (`_path_argument`, #653)."""
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-ask-"))
    env = {**os.environ, **ON_THIS_DISK_ONLY}
    try:
        run(["git", "init", "-q", str(scratch)])
        out = []
        for url in urls:
            got = subprocess.run(["git", "ls-remote", "--get-url", "--",
                                  _path_argument(url)],
                                 cwd=scratch, env=env, capture_output=True,
                                 check=False)
            expanded = ("" if got.returncode else
                        _git_path(got.stdout.rstrip(b"\r\n"))) or url
            if not _on_this_disk(expanded):
                out.append((expanded, None))
                continue
            listed = subprocess.run(["git", "ls-remote", "--",
                                     _path_argument(url)],
                                    cwd=scratch, env=env, capture_output=True,
                                    check=False)
            out.append((expanded, None if not listed.returncode
                        else _first_words(listed)))
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _first_words(failed: subprocess.CompletedProcess) -> str:
    """The first line git wrote to stderr, on one line, each character a
    terminal would act on spelled as `_spelled` spells it; the exit code
    when git wrote nothing."""
    lines = [line for line in failed.stderr.decode(
        "utf-8", "replace").splitlines() if line.strip()]
    if not lines:
        return f"`git ls-remote` exited {failed.returncode}"
    return "".join(char if char.isprintable() else _spelled_character(char)
                   for char in _one_line(lines[0]))


def _unanswered_url_findings(plan: Plan, tree: list,
                             registered: Registrations | str,
                             from_the_leg: dict[str, tuple[str, str]]
                             ) -> tuple[list[str], list[str]]:
    """`(findings, notes)` for the url of each submodule the plan keeps in
    the leg its `.gitmodules` goes to (`_kept_urls`), as that leg resolves
    it: a `plan-submodule-url-answers-nothing` FINDING for each on this
    machine's disk where `git ls-remote` reaches no repository, in the
    tree's order, and the one NOTE `check` prints about those it did not
    ask. `from_the_leg` is `_relative_url_findings`' own: an absolute url
    is its own resolution, and a relative one not in it is that function's
    finding and is not asked. The NOTE is the same whichever remotes a
    relative url was resolved from: a url on a network is not asked under
    `--local-remote-dir` either, and `check` given one names it (#417)."""
    leg, kept = _kept_urls(plan.entries, tree, registered)
    candidates = []
    for path, entry, url in kept:
        if not RELATIVE_URL_RE.match(url):
            candidates.append((path, entry, url, None, url))
        elif path in from_the_leg:
            candidates.append((path, entry, url, *from_the_leg[path]))
    on_disk = [each for each in candidates if _on_this_disk(each[4])]
    answers = dict(zip([each[0] for each in on_disk],
                       _answers([each[4] for each in on_disk]))) \
        if on_disk else {}
    found, unasked = [], []
    for path, entry, url, remote, there in candidates:
        expanded, said = answers.get(path, (there, None))
        if not _on_this_disk(expanded):
            unasked.append(_unasked(path, url, remote, there, expanded))
        elif said is not None:
            found.append(_answers_nothing(path, entry, leg, url, remote,
                                          there, said))
    if not unasked:
        return found, []
    return found, [
        "NOTE `check` did not ask whether the url of each submodule the "
        f"plan keeps in the {leg} leg answers, as that leg resolves it: "
        f"{'; '.join(unasked)}. It asks, with `git ls-remote`, only a url "
        "that names a repository on this machine's disk, and finds one that "
        f"answers nothing as `{URL_ANSWERS_NOTHING}`; whether a url on a "
        "network answers can depend on whose credentials ask, and neither "
        "`check` nor `execute` makes a network call to find out. The "
        "assembly's `git clone --recurse-submodules` asks, after the legs "
        "are made, and fails on one that answers nothing, as the source's "
        "own does."]


def _unasked(path: str, url: str, remote: str | None, there: str,
             expanded: str) -> str:
    """One url the NOTE names: the url, the submodule, where the leg
    resolves it when it is relative, and where git here sends it when a
    config rewrites it off the disk. Each url `redacted`: an absolute one
    may carry a token, as a source's remote may (#190)."""
    named = f"{_spelled(redacted(url))} of {_spelled(path)}"
    if remote is not None:
        named += f", to {_spelled(redacted(there))}"
    if expanded != there:
        named += (", which git here rewrites to "
                  f"{_spelled(redacted(expanded))}")
    return named


def _answers_nothing(path: str, entry: str, leg: str, url: str,
                     remote: str | None, there: str, said: str) -> str:
    """The FINDING for one url that answers nothing: `remote` is the leg's
    remote it was resolved from when it is relative, and None when it is
    absolute; `said` is what git said. A relative one is `_FromTheLeg`."""
    if remote is None:
        named = f"is {_spelled(redacted(url))}"
    else:
        named = (f"is the relative {_spelled(url)}, which git resolves from "
                 f"the {leg} leg, at {_spelled(redacted(remote))}, to "
                 f"{_spelled(redacted(there))}, the repository it names "
                 "from the source")
    finding = (
        f"FINDING {URL_ANSWERS_NOTHING}: the submodule "
        f"{_as_entry(path, entry)} has leg: {leg}, and its url in the "
        f"source's {GITMODULES} {named}, where `git ls-remote` reaches no "
        f"repository ({said}): the assembly's recursive clone fails on it "
        f"in the {leg} leg, as the source's own recursive clone does")
    return finding if remote is None else _FromTheLeg(finding)


def _submodule_findings(plan: Plan, source: Source, tree: list,
                        local_remote_dir: Path | None = None
                        ) -> tuple[tuple[list[str], list[str]],
                                   tuple[list[str], list[str]], list[str]]:
    """`(findings, remediation)` for `submodule_plan_problems`, one FINDING
    each and SUBMODULE_REMEDIATION when there is one; the same for the urls
    of the submodules a leg keeps, each `_relative_url_findings` one and
    then each `_unanswered_url_findings` one (#418), with
    RELATIVE_URL_REMEDIATION and URL_ANSWERS_NOTHING_REMEDIATION for those
    there are; and the NOTEs `check` prints. A remediation is printed ONCE
    after every finding. The two come back apart because `_entry_findings`
    lists the urls last, after the values #255 finds. `check` is where the
    person is told to fix the plan, so it says how, in the words `execute`'s
    refusal would use one step later."""
    registered = source.registered_submodules(tree)
    found = [f"FINDING {code}: {detail}" for code, detail
             in submodule_plan_problems(plan.entries, tree, registered)]
    moved, notes, from_the_leg = _relative_url_findings(
        plan, source, tree, registered, local_remote_dir)
    unanswered, unasked = _unanswered_url_findings(
        plan, tree, registered, from_the_leg)
    return ((found, [SUBMODULE_REMEDIATION] if found else []),
            (moved + unanswered,
             ([RELATIVE_URL_REMEDIATION] if moved else [])
             + ([URL_ANSWERS_NOTHING_REMEDIATION] if unanswered else [])),
            notes + unasked)


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
        prints as an escape, never as itself, the split commit's message
        included, which lists it as `_shown` does (#900);
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
                    "included, and adopting one is not yet measured on "
                    "macOS or Windows")
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
        chosen = ("" if plan.get("reference") is not None else
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
# A symlink in the source whose target is empty (#303), or begins with a NUL
# byte (#388)
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
# A TARGET THAT BEGINS WITH A NUL BYTE IS EMPTY TOO (#388). git hands a
# symlink's target to `symlink(2)` as a C string, which ends at its first
# NUL, so `\0spec.md`, 8 bytes and not the empty blob, is the empty target
# to Linux, and every run above went the same way: on main `check` said
# `plan ok`, and with symlinks on `execute` failed in its first clone after
# both leg repositories were created; with `core.symlinks` false it said
# `adoption verified` over a spec leg whose own clone exits 128. It is the
# same fact of the source, failing the same way, with the same remediation,
# so it is the same finding, worded for its blob. A second code would give
# one fault two names for every reader of this one to learn: `execute`'s
# refusal, and the walk of #183, which says nothing of a link this finding
# names. A NUL further on (`spec\0.md`) is another failure, a link git
# makes to `spec`, and is not this one's to report: it is
# `plan-bad-symlink-target`'s (#908), below.
#
# Size first, then the target. `Source.tree()` lists each entry with
# `ls-tree -l`, and the size of a symlink's blob is the length of its
# target, so an empty target is a `120000` row of size 0, in a SHA-1 or a
# SHA-256 repository alike, and is not read. The target of every other link
# is read in ONE `git cat-file --batch` over the blob ids the tree lists
# (`symlink_targets`), so a source with no symlink of size 1 or more starts
# no process for it. Only the commit being adopted is read: a symlink in the
# history alone is never checked out by a clone, and `git filter-repo`
# rewrites the history without a checkout.

#: `check`'s finding for a symlink of the source's whose target is empty, or
#: begins with a NUL byte, which ends it (#388).
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


def symlink_targets(source: Source, tree: list) -> dict[str, bytes]:
    """The target of each symlink of `tree` (`Source.tree()`'s rows) whose
    blob is not empty, as the bytes the blob holds, by blob id (#388).

    ONE `git cat-file --batch` over the ids, each id once however many
    links share it, and none at all when no link has a size: a link of size
    0 has the empty target, which is known without reading it. Each object
    comes back as `<id> <type> <size>`, a line feed, that many bytes and a
    line feed, so it is cut by its size, and a target that holds a line feed
    is read whole. An id git does not have comes back as `<id> missing` and
    nothing else, and is left out: such a link is judged by its size alone.

    EACH BLOB IS READ ONCE PER SOURCE (#908). What is read is kept on
    `source.link_targets`, so a second call, `_PlannedRoot`'s every walk
    among them, asks git for no blob it has already read, and for none at
    all when the first read took them all.
    """
    sized = list(dict.fromkeys(oid for _, mode, oid, size in tree
                               if mode == SYMLINK_MODE and size))
    known = source.link_targets
    oids = [oid for oid in sized if oid not in known]
    if oids:
        args = [GIT_CAT_FILE, "--batch"]
        read = subprocess.run(
            ["git", *args], cwd=source.path,
            input="".join(f"{oid}\n" for oid in oids).encode(),
            capture_output=True, check=False)
        if read.returncode:
            raise Refusal(
                "git-failed",
                f"`git {' '.join(args)}` in {source.path} exited "
                f"{read.returncode}: "
                f"{read.stderr.decode('utf-8', 'replace').strip()}")
        out, at = read.stdout, 0
        for oid in oids:
            known[oid] = None
            end = out.find(b"\n", at)
            if end < 0:
                continue
            header, at = out[at:end].split(), end + 1
            if len(header) == 3:
                size = int(header[2])
                known[oid] = out[at:at + size]
                at += size + 1
    return {oid: known[oid] for oid in sized if known[oid] is not None}


def empty_symlinks(tree: list, targets: dict[str, bytes]) -> list[str]:
    """The paths of `tree` (`Source.tree()`'s rows) that are symlinks whose
    target is empty to Linux: mode 120000, and a blob of size 0 (#303), or
    one whose target in `targets` (`symlink_targets`, by blob id) begins
    with a NUL byte, which ends it there (#388)."""
    return [path for path, mode, oid, size in tree
            if mode == SYMLINK_MODE
            and (not size or targets.get(oid, b"").startswith(b"\0"))]


def _empty_symlink_sentence(path: str, nul: bool) -> str:
    """What `check` says of the symlink at `path` whose target is empty,
    or, with `nul`, begins with a NUL byte (#388), and `plan` notes."""
    if nul:
        target = ("begins with a NUL byte at the source commit; a symlink's "
                  "target ends at its first NUL, so this one is empty too,")
        held = "a plain file"
    else:
        target, held = "is empty at the source commit,", "an empty file"
    return (f"{_spelled(path)} is a symlink whose target {target} and Linux "
            "cannot make a symlink to nothing. "
            "There, where git makes symlinks by default, each clone "
            "`execute` makes of the source stops at it after both leg "
            "repositories were created, whatever the plan answers for it; "
            "and where `core.symlinks` is false the clone holds it as "
            f"{held}, and the leg or root the plan keeps it in then "
            "cannot be cloned on Linux, where the root's own `validate` "
            "workflow runs")


def _empty_symlink_sentences(tree: list,
                             targets: dict[str, bytes]) -> list[str]:
    """`_empty_symlink_sentence` of each path `empty_symlinks` names, in its
    order: one that has a size is there for its NUL."""
    sized = {path for path, _, _, size in tree if size}
    return [_empty_symlink_sentence(path, nul=path in sized)
            for path in empty_symlinks(tree, targets)]


def _empty_symlink_findings(tree: list, targets: dict[str, bytes],
                            at_the_manifest: frozenset | set = frozenset()
                            ) -> tuple[list[str], list[str]]:
    """A FINDING for each symlink of the source whose target is empty
    (#303) or begins with a NUL byte (#388), as `check` prints it, the first
    EMPTY_SYMLINKS_NAMED one by one; and what to print ONCE after every
    finding, as `_unsafe_path_findings` does. Read from the tree and the
    targets (`symlink_targets`) alone: no answer of the plan's changes it.
    `at_the_manifest` holds the paths of the links the plan keeps in the
    root AT `project.yaml`, whose finding says so (`_at_the_manifest`,
    #908)."""
    said = _empty_symlink_sentences(tree, targets)
    shown = list(zip(empty_symlinks(tree, targets), said))
    found = [f"FINDING {EMPTY_SYMLINK}: {sentence}."
             f"{_at_the_manifest(path) if path in at_the_manifest else ''}"
             for path, sentence in shown[:EMPTY_SYMLINKS_NAMED]]
    if len(said) > EMPTY_SYMLINKS_NAMED:
        found.append(f"FINDING {EMPTY_SYMLINK}: … and "
                     f"{len(said) - EMPTY_SYMLINKS_NAMED} more symlinks "
                     "whose target is empty or begins with a NUL byte")
    return found, [EMPTY_SYMLINK_REMEDIATION] if found else []


def _empty_symlink_notes(tree: list, targets: dict[str, bytes]) -> list[str]:
    """What `plan` says of each symlink of the source whose target is empty
    or begins with a NUL byte: a NOTE in `check`'s words, and a line saying
    what follows. `plan` still writes the plan, but no answer in it will
    pass `check`. Then the same for each whose target holds a NUL byte
    after its first, or is longer than Linux takes (#908)."""
    notes: list[str] = []
    for sentence in _empty_symlink_sentences(tree, targets):
        notes += [f"\nNOTE {sentence}.",
                  f"     `check` reports this as `{EMPTY_SYMLINK}` and "
                  "`execute` refuses it, whatever the plan answers: give it "
                  "a target in the source, or remove it there, commit, and "
                  "re-run `plan`."]
    return notes + _bad_symlink_target_notes(tree, targets)


# ---------------------------------------------------------------------------
# A symlink in the source whose target holds a NUL after its first byte, or is
# longer than Linux takes (#908)
# ---------------------------------------------------------------------------
#
# #388 left "a NUL further on (`spec\0.md`)" to "another failure, a link git
# makes to `spec`", and no check asked it; nor did any ask a target's length.
# Both passed `check` and failed after both leg repositories existed. Measured
# on the v1.1.1 release commit with git 2.43 on Linux (ext4):
#
#   * A target is handed to `symlink(2)` as a C string, which ends at its
#     first NUL: a blob holding `ci\0xx` is the link `ci`, and `spec\0.md` is
#     `spec`. Linux makes the link, a different one, so no clone fails there.
#     A link `execute` meets in a leg's path stops at the split's `git rm`,
#     which refuses the link the checkout made, as one that changed, after
#     both legs were pushed; one kept in the root is `adopt-lost` in the
#     verification, the split holding the 4 bytes `spec` where the source
#     holds 8. Whatever the plan answers: `drop`, `spec` and `code` stop at
#     the `git rm`, `root` at the verification.
#   * Where `core.symlinks` is false, `execute` said `adoption verified`, the
#     clone holding the blob's bytes as a plain file; and a clone of that leg
#     on Linux, symlinks on, then held `docs/link -> spec` with `git status`
#     reading ` M docs/link`, or, for a target too long, exited 128.
#   * On ext4, a target of 4095 bytes is made, and one of 4096 or 5000 is
#     not: `symlink(2)` fails with ENAMETOOLONG, `File name too long`, and
#     the clone exits 128, `unable to checkout working tree`, after both
#     legs exist. That is `PATH_MAX`, 4096 counting the NUL that ends the
#     string, and `NAME_MAX` is not asked: a target that is one name of 300
#     bytes is made (a path is asked it only when something is opened
#     through it).
#   * Some hosts take less, which is NOT measured here and is read from
#     their sources: macOS (`symlink(2)` copies the target in with
#     `MAXPATHLEN`, 1024, counting the NUL) and XFS (`XFS_SYMLINK_MAXLEN`,
#     1024) make a target of at most 1023 bytes.
#
# SO THE LIMIT IS 4095 (`SYMLINK_TARGET_MAX`), GIT'S AND LINUX'S. `check`
# reads the source's tree and never the disk it runs on, as #303 does, so one
# plan gets one answer on every machine. A finding must never be false
# anywhere, and a target over 4095 bytes is made on no host: it fails on
# every Linux filesystem, and on the hosts that take less still.
#
# IT IS NOT THE SMALLEST BOUND A HOST HAS, SO A TARGET UNDER IT CAN STILL
# FAIL. A target of 4095 bytes is made on ext4-like filesystems; on macOS and
# XFS the most is 1023 (above). A target of 1024 to 4095 bytes therefore
# passes `check` and fails `execute`'s first clone there, after both leg
# repositories exist: #908's own failure, in a window this rule leaves open
# for those hosts. That is read from their sources, not measured here, and
# it is a follow-up of #908. Windows makes no symlink by default
# (`core.symlinks` false writes the target as a file's contents, which no
# length bounds); where it is on, NTFS is thought to take far longer targets
# (not measured here), and either way the rule asks Windows nothing.
#
# A NEW CODE, NOT A WIDENED `plan-empty-symlink`. #388 made a NUL-led target
# the same finding because it is the same fault: Linux reads it as empty,
# and fails in the same clone for the same reason, with the same remedy. A
# late NUL is a different one (Linux makes a link, and another command
# stops), and a long target is no empty one at all, so a finding named
# `plan-empty-symlink` would tell whoever relays it that a link of 5000
# bytes is empty. The two codes never name one link: a target is empty or
# NUL-led for `plan-empty-symlink`, and anything else here. Their remedy is
# alike, and the finding says what git makes in place of the link.
#
# ONE FINDING FOR A LINK AT `project.yaml` (L1-80 of #457). A link the plan
# keeps in the root AT the manifest was named twice, `plan-empty-symlink` for
# its target and `plan-root-blocks-manifest` for its place, and the second's
# remedy ("send it to a leg, `drop` it") cannot help an empty link: no
# answer in the plan does. This finding is the plan-independent one, so it
# stays, says where the link sits, and ends with the remedy that does help;
# `_root_shape_findings` leaves out the other for that link.

#: The most `symlink(2)` takes as a target on Linux, in bytes: `PATH_MAX` is
#: 4096, counting the NUL that ends the string. On ext4-like filesystems 4095
#: is made and 4096 is not; macOS and XFS make at most 1023 (see above).
SYMLINK_TARGET_MAX = 4095
#: `check`'s finding for a symlink of the source's whose target holds a NUL
#: byte after its first, which git cuts at, or is longer than
#: SYMLINK_TARGET_MAX (#908).
BAD_SYMLINK_TARGET = "plan-bad-symlink-target"
#: How many of them `check` names one by one; past it, a count.
BAD_SYMLINK_TARGETS_NAMED = 20
#: How many bytes of a target a sentence spells; it counts the rest.
TARGET_SPELLED = 100
#: What a plan whose source holds one is told to do. Said by `check`, once
#: after its findings, and by `execute`'s refusal, after its own remediation.
BAD_SYMLINK_TARGET_REMEDIATION = (
    "Remediation: a symlink's target is a fact of the source, and no answer "
    "in the plan changes it, `drop` included: `execute` clones the whole "
    "source before it takes out anything the plan sends elsewhere, and a "
    "clone makes the link git makes of the target, or none, not the "
    "blob's. Give each such symlink a target of its own in the source, with "
    "no NUL byte in it and no more than "
    f"{SYMLINK_TARGET_MAX} bytes, or remove it there, commit, and re-run "
    "`plan`: a plan is written against one commit of the source, and "
    "`check` calls it `plan-stale` once the source has moved.")


def _at_the_manifest(path: str) -> str:
    """What a finding adds of the link at `path` that the plan keeps AT
    `project.yaml`: where it sits, and the remedy that helps. A link at the
    manifest's case twin (`Project.yaml`) sits there only once case is
    ignored, as `plan-root-blocks-manifest` says of it, so the aside stays."""
    manifest = _spelled(SHAPE_MANIFEST)
    where = (f"where the shape writes its manifest, {manifest}"
             if path == SHAPE_MANIFEST else
             f"at {manifest}{_CASE_ASIDE}, where the shape writes its "
             "manifest")
    return (f" The plan keeps it in the assembly root, {where}, and no copy "
            f"stands in for that (`{ROOT_BLOCKS_MANIFEST}`, not said again "
            "here): a target of its own would not end that, so remove the "
            "link or rename it in the source, commit, and re-run `plan`.")


def _unmade_target(raw: bytes) -> bool:
    """Whether git does not make the symlink a blob of `raw` describes as
    that target: `raw` holds a NUL, which ends the string `symlink(2)` is
    handed, or is longer than Linux takes (#908). An empty one, or one that
    begins with a NUL, is `plan-empty-symlink`'s (#303, #388), and is so
    here too: both are unmade."""
    return not raw or b"\0" in raw or len(raw) > SYMLINK_TARGET_MAX


def bad_symlink_targets(tree: list, targets: dict[str, bytes]
                        ) -> list[tuple[str, bytes]]:
    """`(path, target)` of each symlink of `tree` (`Source.tree()`'s rows)
    whose target in `targets` (`symlink_targets`, by blob id) git does not
    make as it stands and `empty_symlinks` does not name: it holds a NUL
    byte after its first, or is longer than SYMLINK_TARGET_MAX. A link whose
    target was not read is judged by `empty_symlinks` alone, by its size."""
    found = []
    for path, mode, oid, size in tree:
        raw = targets.get(oid, b"") if mode == SYMLINK_MODE and size else b""
        if raw and not raw.startswith(b"\0") and _unmade_target(raw):
            found.append((path, raw))
    return found


def _target_spelled(raw: bytes) -> str:
    """The target `raw` as a sentence spells it: `_spelled`, and only the
    first TARGET_SPELLED bytes of a long one, with a count of the rest."""
    head = _spelled(_git_path(raw[:TARGET_SPELLED]))
    more = len(raw) - TARGET_SPELLED
    return head if more <= 0 else f"{head} and {more} more bytes"


def _bytes(count: int) -> str:
    """`count` bytes, in the singular for one."""
    return f"{count} byte{'' if count == 1 else 's'}"


def _bad_symlink_target_sentence(path: str, raw: bytes) -> str:
    """What `check` says of the symlink at `path` whose target is `raw`,
    and `plan` notes: what is wrong with the blob, what git makes of it, and
    what then fails (#908)."""
    cut = raw.split(b"\0", 1)[0]
    nul = len(cut) < len(raw)
    made = len(cut) <= SYMLINK_TARGET_MAX
    after = ("its first byte" if len(cut) == 1
             else f"its first {len(cut)} bytes")
    limit = (f"Linux takes at most {SYMLINK_TARGET_MAX} bytes in a "
             "symlink's target (`PATH_MAX` is 4096, counting the NUL that "
             "ends it), so git makes no symlink there: `symlink(2)` fails "
             "with `File name too long`")
    if not nul:
        head = f"is {_bytes(len(raw))} at the source commit, and {limit}"
    elif made:
        head = (f"holds a NUL byte after {after} at the source commit; a "
                "symlink's target ends at its first NUL, so git makes "
                f"{_spelled(path)} a link to {_target_spelled(cut)}, not to "
                f"the {_bytes(len(raw))} the blob holds")
    else:
        head = (f"holds a NUL byte after {after} at the source commit, and "
                f"those alone are too many: {limit}")
    if nul and made:
        then = ("On Linux, where git makes symlinks by default, each clone "
                "`execute` makes of the source holds that other link, and "
                "`execute` stops at it after both leg repositories were "
                "created, whatever the plan answers for it; and where "
                "`core.symlinks` is false the clone holds the "
                f"{_bytes(len(raw))} as a plain file, and a clone of the "
                "leg or root the plan keeps it in, on Linux, then holds "
                "the other link")
    else:
        then = ("There, where git makes symlinks by default, each clone "
                "`execute` makes of the source stops at it after both leg "
                "repositories were created, whatever the plan answers for "
                "it; and where `core.symlinks` is false the clone holds it "
                "as a plain file, and the leg or root the plan keeps it in "
                "then cannot be cloned on Linux, where the root's own "
                "`validate` workflow runs")
    return f"{_spelled(path)} is a symlink whose target {head}. {then}"


def _bad_symlink_target_sentences(tree: list, targets: dict[str, bytes]
                                  ) -> list[tuple[str, str]]:
    """`(path, sentence)` of each path `bad_symlink_targets` names, in its
    order."""
    return [(path, _bad_symlink_target_sentence(path, raw))
            for path, raw in bad_symlink_targets(tree, targets)]


def _bad_symlink_target_findings(
        tree: list, targets: dict[str, bytes],
        at_the_manifest: frozenset | set = frozenset()
        ) -> tuple[list[str], list[str]]:
    """A FINDING for each symlink of the source whose target holds a NUL
    byte after its first, or is longer than Linux takes (#908), as `check`
    prints it, the first BAD_SYMLINK_TARGETS_NAMED one by one; and what to
    print ONCE after every finding, as `_empty_symlink_findings` does. Read
    from the tree and the targets alone: no answer of the plan's changes it.
    `at_the_manifest` holds the paths of the links the plan keeps in the
    root AT `project.yaml`, whose finding says so (`_at_the_manifest`)."""
    said = _bad_symlink_target_sentences(tree, targets)
    found = [f"FINDING {BAD_SYMLINK_TARGET}: {sentence}."
             f"{_at_the_manifest(path) if path in at_the_manifest else ''}"
             for path, sentence in said[:BAD_SYMLINK_TARGETS_NAMED]]
    if len(said) > BAD_SYMLINK_TARGETS_NAMED:
        found.append(
            f"FINDING {BAD_SYMLINK_TARGET}: … and "
            f"{len(said) - BAD_SYMLINK_TARGETS_NAMED} more symlinks whose "
            "target holds a NUL byte after its first or is longer than "
            "Linux takes")
    return found, [BAD_SYMLINK_TARGET_REMEDIATION] if found else []


def _bad_symlink_target_notes(tree: list, targets: dict[str, bytes]
                              ) -> list[str]:
    """What `plan` says of each symlink of the source whose target holds a
    NUL byte after its first, or is longer than Linux takes: a NOTE in
    `check`'s words, and a line saying what follows, as
    `_empty_symlink_notes` does."""
    notes: list[str] = []
    for _, sentence in _bad_symlink_target_sentences(tree, targets):
        notes += [f"\nNOTE {sentence}.",
                  f"     `check` reports this as `{BAD_SYMLINK_TARGET}` and "
                  "`execute` refuses it, whatever the plan answers: give it "
                  "a target of its own in the source, or remove it there, "
                  "commit, and re-run `plan`."]
    return notes


def _links_at_the_manifest(plan: Plan, tree: list) -> set[str]:
    """Each symlink the plan keeps in the root AT `project.yaml`, which
    #305's `plan-root-blocks-manifest` names (`_shape_blocks`), on a disk
    that keeps case and on one that ignores it. Asked, as `_leg_findings`
    asks it, of a plan whose `legs` it can read."""
    if not isinstance(plan.legs, dict):
        return set()
    kept = _kept_in_root(plan.entries, tree)
    return {rows[0][0] for fold in (False, True)
            for code, _, _, group, rows in _shape_blocks(_KeptTree(kept, fold))
            if code == ROOT_BLOCKS_MANIFEST and group[0] == "at"
            and rows[0][1] == SYMLINK_MODE}


def _named_symlinks(tree: list, targets: dict[str, bytes]) -> set[str]:
    """The paths `plan-empty-symlink` and `plan-bad-symlink-target` name ONE
    BY ONE, the first EMPTY_SYMLINKS_NAMED and BAD_SYMLINK_TARGETS_NAMED of
    each: `_root_shape_findings` leaves out `plan-root-blocks-manifest` for
    one of them at `project.yaml`, which its own finding says all of. A link
    past those is only counted, and is named by nothing else if this leaves
    it out too, so the manifest finding stays its own.

    THE OTHER FINDINGS ABOUT A PATH THE SHAPE WRITES DO NOT LEAVE A NAMED
    LINK OUT. A bad link at `shape/README.md` is also
    `plan-root-blocks-shape-copy`, and one at `contracts/shape-pin.yaml`
    also `plan-root-holds-pin`, each with a remedy (`drop` it, send it to a
    leg) that cannot help a link no clone makes. That is L1-80's defect at
    those two paths, outside #908's wording, and a follow-up of it."""
    return {*empty_symlinks(tree, targets)[:EMPTY_SYMLINKS_NAMED],
            *(path for path, _ in bad_symlink_targets(
                tree, targets)[:BAD_SYMLINK_TARGETS_NAMED])}


def _source_path_findings(plan: Plan, tree: list, targets: dict[str, bytes]
                          ) -> tuple[list[str], list[str]]:
    """The findings `_entry_findings` lists first, about the source's own
    paths, and what to print once after every finding for them: each entry
    path `execute` will not extract (#196), then each symlink of the source
    whose target is empty (#303) or begins with a NUL byte (#388), its
    target read from `targets` (`symlink_targets`), and each whose target
    holds a NUL byte after its first, or is longer than Linux takes (#908).
    A link the plan keeps in the root AT `project.yaml` says so in its
    finding, which is then the only one that names it."""
    unsafe, unsafe_remediation = _unsafe_path_findings(plan)
    # Asked only where a named link sits at the manifest's own name, which
    # is rare: it reads the plan's answers, which no other finding here does.
    named = _named_symlinks(tree, targets)
    manifest = (_links_at_the_manifest(plan, tree)
                if any(path.casefold() == SHAPE_MANIFEST for path in named)
                else set())
    empty, empty_remediation = _empty_symlink_findings(tree, targets,
                                                       manifest)
    bad, bad_remediation = _bad_symlink_target_findings(tree, targets,
                                                        manifest)
    return (unsafe + empty + bad,
            unsafe_remediation + empty_remediation + bad_remediation)


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


# ---------------------------------------------------------------------------
# The two branch names a plan gives `execute` (#420, #520)
# ---------------------------------------------------------------------------
#
# `execute` hands two plan values to git as branch names: `adopt_branch:`,
# the split branch, which each extraction's clone checks out and the split
# is pushed to, and `tracking_branch:`, the branch both legs are pushed to.
# `_checked_plan_values` holds each to `checked_value`'s alphabet, which
# keeps an option off a command line and is wider than the names git
# creates. Measured on main at bfed143: an `adopt_branch:` edited to `a..b`,
# `~`, `x.lock` or `a/` checked `plan ok`, and `execute --local-remote-dir`
# made both legs and died at the extraction's `git checkout -B`, the
# corrected plan then meeting `leg-remote-exists`; a name outside the
# alphabet that git accepts (`a=b`) checked `plan ok`, and `execute` refused
# it as `unsafe-value` (L2-1 on #457). A `tracking_branch:` git refuses was
# found since #479, as `plan-tracking-branch-missing`, a sentence about the
# source's branches that named no rule.
#
# So `check` asks both, as `execute` reads them: the constant `ADOPT_BRANCH`
# and `main` where the key is absent, and `str` of whatever the file holds.
# Each is held to the alphabet first, and a name outside it is `execute`'s
# own refusal, `unsafe-value`, in its own words; a name inside it is asked of
# git with #283's `refuse_bad_branch`, under the key's own code. ONE FINDING
# PER VALUE: a name outside the alphabet is not asked of git, and no other
# question is asked about a name found here (`_check_split_branch`, and
# `plan-tracking-branch-missing` in `_entry_findings`). `execute` refuses
# `unsafe-value` in `_checked_plan_values`, as it always did, and git's
# verdict among `check`'s other findings in `_refuse_what_check_finds`, both
# before any leg exists. `plan` refuses its own `--tracking-branch` the same
# way, as `adopt-bad-tracking-branch`, before it writes a plan.

#: Each branch name `execute` hands git, in the order `_checked_plan_values`
#: asks them: `(key, what execute reads where the key is absent, the code
#: check finds a name git will not create under)`.
SPLIT_BRANCH_KEY = ("adopt_branch", ADOPT_BRANCH, "plan-bad-adopt-branch")
BRANCH_KEYS = (SPLIT_BRANCH_KEY,
               (TRACKING_KEY, "main", "plan-bad-tracking-branch"))
#: What `check` says once after a finding git made about either name: the
#: remedy `refuse_bad_branch` gives a name git judged is worded for a flag.
BRANCH_NAME_REMEDIATION = (
    "Remediation: set each branch name a finding names to one git creates, "
    "such as `main` or `release/1.2`, in the plan, and run `check` again: "
    "`git check-ref-format --branch <name>` prints such a name back as it "
    "is written, and `git help check-ref-format` lists every rule.")


def _branch_name_refusal(plan: Plan, key: str, default: str,
                         code: str) -> Refusal | None:
    """Why `execute` will not hand git the plan's `key` as a branch name, as
    the refusal `check` reports, or None: `checked_value`'s, `execute`'s own,
    for a name outside its alphabet, and otherwise git's verdict under
    `code`. The value is `execute`'s (`_checked_plan_values`): `default`
    where the key is absent, and `str` of what the file holds.

    A NUMBER OR A BOOLEAN IS NO BRANCH NAME (#902, L1-K3 on #457). `str` of
    it is one: `tracking_branch: 007` was the branch `7`, `true` was `True`
    and `1.50` was `1.5`, and `adopt_branch:` the same, so a plan holding
    any of them checked ok and was adopted onto that branch without a word.
    It is refused under the key's own code, saying what was read
    (`_not_text`), and is not asked of git."""
    value = plan.get(key, default)
    if _a_number_or_boolean(value):
        return Refusal(code, _not_text(key, value), NOT_TEXT_REMEDIATION)
    try:
        checked_value(key, value)
        refuse_bad_branch(code, key, value)
    except Refusal as exc:
        return exc
    return None


def _branch_name_findings(plan: Plan) -> tuple[list[str], list[str], set]:
    """`_branch_name_refusal` of each of `BRANCH_KEYS`, as `check` prints
    them, in `execute`'s order; what it prints once after them; and the
    keys they name, which nothing else asks about."""
    found, remedies, named = [], [], set()
    for key, default, code in BRANCH_KEYS:
        refusal = _branch_name_refusal(plan, key, default, code)
        if refusal is None:
            continue
        found.append(f"FINDING {refusal.code}: {refusal.detail}")
        named.add(key)
        remedy = (BRANCH_NAME_REMEDIATION
                  if refusal.remediation == BRANCH_REMEDIATION
                  else refusal.remediation)
        if remedy not in remedies:
            remedies.append(remedy)
    return found, remedies, named


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
    be written through (#178, #183), then each `.gitattributes` the plan
    keeps below the root that outranks the root's line-ending rule for a
    pinned copy (#530), then the source's own root `.gitattributes`, which
    the split writes into, where this machine's `git add` would not store
    what it writes there (#530's D5(a)), then each other file the plan keeps
    or moves, and each pinned copy, that this machine's git would store as
    other bytes than the split expects, or refuses (#654), then each value
    `execute` writes into
    a file that no file can hold (#255), then what the project's own
    `validate-manifest.py` would refuse of the values `execute` writes into
    its manifest (#261), then the split branch's name and the tracking
    branch's, in that order, the order `execute` asks them, each held to
    `checked_value`'s alphabet and otherwise asked of git (#420, #520), then
    a tracking branch that is no branch of the source (#479), then each
    relative url of a kept submodule that names another repository from its
    leg (#190), then each url of a kept submodule that names a repository on
    this machine's disk where none answers (#418), and last each plan value
    `execute` reads late and
    `_plan_field_findings` asks about (#293, #294).

    ONE LIST, read by `check` and by `execute`'s `_refuse_what_check_finds`.
    #168 and #166 each added findings to `check` and a refusal to `execute`
    while both were open, and composed them separately so as not to edit the
    same lines; three compositions then disagreed, and a plan `check`
    rejected as uncovered AND split was refused by `execute` for the split
    alone, to be refused again for the rest once that was fixed. Composed
    once, the two commands cannot differ about a plan -- but in the two
    places something outside the plan decides it. `local_remote_dir` is
    the run's, and a relative submodule url is resolved from the leg
    remotes it names, and from GitHub's without one (#190): `check` takes
    the same `--local-remote-dir` as `execute` (#417), so the two differ
    there only where they are given different ones. And two things about a
    symlink AT a shape path are asked of the disk by each command when it
    runs (#183): whether anything is at the
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

    THEN THE SOURCE'S EMPTY SYMLINKS (#303), a target that begins with a
    NUL byte among them (#388), which no answer in the plan
    fixes: the fix is a commit in the source, and the fresh `plan` after it
    takes back every answer given before, so they are listed before the
    findings about those answers (`_source_path_findings`). Their
    remediation is said once after the findings, with the others. The
    same goes for each symlink whose target holds a NUL byte after its
    first, or is longer than Linux takes (#908), as
    `plan-bad-symlink-target`: git makes another link or none, which no
    answer changes either.

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
    where the plan's `pins:` has no finding of #273's (`_plan_fields`). A
    `pins:` entry #273 names is that finding alone (#901): #255 asks only
    the pins `execute` writes (`_plan_values`), and the validator's word on
    such an entry is left out (`_validator_ignores`).
    And a tracking branch whose NAME is wrong is that finding alone (#520):
    one outside the alphabet or one git will not create is no branch of any
    source, and is not also said to be missing from this one.
    """
    tree = source.tree()
    targets = symlink_targets(source, tree)
    unsafe, unsafe_remediation = _source_path_findings(plan, tree, targets)
    findings = (unsafe
                + _coverage_findings([str(e.get("path"))
                                      for e in plan.entries],
                                     [path for path, _, _, _ in tree])
                + _leg_findings(plan, tree, _named_symlinks(tree, targets)))
    # Beside the pins' other findings, which `_leg_findings` lists last: a
    # digest the clone `plan` read it from recomputes otherwise (#449).
    digest_findings, pin_notes = _pin_digest_findings(plan)
    findings += digest_findings
    (split, split_remediation), (moved, moved_remediation), notes = \
        _submodule_findings(plan, source, tree, local_remote_dir)
    unwritable_findings, unwritable_remediation = _value_findings(plan)
    value_findings, value_remediation = _manifest_findings(plan)
    field_findings, field_remediation = _plan_field_findings(plan)
    names, names_remediation, misnamed = _branch_name_findings(plan)
    tracking_findings, tracking_remediation = (
        ([], []) if TRACKING_KEY in misnamed
        else _tracking_branch_findings(plan, source))
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
    # One answer to whether git checks a symlink out as one, for the two
    # questions whose walks may need it on any source (#654).
    probe = _SymlinkProbe(source.work_root)
    return (findings + misread + split
            + _root_symlink_findings(plan, source, tree, probe)
            + _nested_attributes_findings(plan, source, tree)
            + _reencoded_attributes_findings(plan, source, tree)
            + _reencoded_files_findings(plan, source, tree, probe)
            + unwritable_findings + value_findings + names
            + tracking_findings + moved + field_findings,
            unsafe_remediation
            + ([MANIFEST_MISREAD_REMEDIATION] if misread else [])
            + split_remediation + unwritable_remediation + value_remediation
            + names_remediation + tracking_remediation + moved_remediation
            + field_remediation,
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
# ONCE CASE IS IGNORED TOO (#520's A4; ruled 2026-10-12: on every system).
# Git keeps a branch as a file named after it, and a macOS or Windows disk
# keeps `Adopt` and `adopt` as one path, so a source branch `Adopt`, or one
# that is the split branch in another case, passed `check` there and
# `execute` made both legs before git refused it (#457). `_in_the_way`
# compares as a leg's mount path is compared (`path_overlap`), and a finding
# about a name in the way only once case is ignored says so. It is refused
# on Linux too, where git would hold the pair: one plan is then not good on
# one machine and refused after both legs exist on another.
#
# A BRANCH THE SOURCE HIDES (#520). A local repository's branches were read
# with `git ls-remote`, which asks `git upload-pack`, and that leaves out a
# branch hidden by `uploadpack.hideRefs` or `transfer.hideRefs`: `check` said
# `plan ok`, and `execute --local-remote-dir` made both legs before the push
# of the split met the branch on git's ref lock, measured on main at bfed143
# with git 2.43. A push into a repository meets its own refs, so those are
# what `_branches_at` reads of a local one, with `git for-each-ref`. A clone
# of it obeys the setting, as `ls-remote` does, so the extraction never
# meets such a branch: a source branch the clone gets is about either run,
# and one the source hides is about the push into it alone
# (`_places_in_the_source`).
#
# ONE CODE FOR ONE SITUATION. `check`'s finding for the split branch itself
# is `adopt-branch-exists`: the code `execute` refuses that branch under, and
# the one `_left_by_the_split` tells a run that pushed its split the re-run
# will meet. It is asked by that refusal's own rule (`_in_the_history_of`),
# so a branch the push fast-forwards is no finding, and the two commands
# cannot disagree about it, as #168 has them agree about every other finding.
# A branch in the way is `plan-split-branch-taken` in both.
#
# WHERE `check` ASKS. It does not know whether `execute` will be given
# `--local-remote-dir`, and its own (#417) is not read here, so it asks the
# two places it can see without the network, and each finding says which
# run it is about: the source's own branches, and, where
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
    "it, and a macOS or Windows disk holds none whose name is another's, or "
    "such a name, in another case, so the plan's split branch cannot be made "
    "beside a branch named above, where it is named. Delete that branch "
    "there, once neither it nor a pull request from it is wanted, or set "
    "`adopt_branch:` in the plan to a name git can create there, then run "
    "`check` and `execute` again.")
#: Why a branch is in git's way of the split branch only once case is
#: ignored, said after `CASE_ASIDE` in a finding (#520's A4).
SPLIT_BRANCH_CASE_CLASH = (
    ": git keeps each branch as a file named after it, and such a disk keeps "
    "two paths that differ only by case as one. `check` and `execute` refuse "
    "such a pair on every system")
#: The listing `git for-each-ref` prints of a repository's own branches, in
#: the shape `git ls-remote` prints them: `<commit> TAB <ref>`.
REF_LISTING = "--format=%(objectname)%09%(refname)"
BRANCH_REFS = "refs/heads/"


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


def _listed_by(args: list[str], cwd: Path) -> dict[str, str]:
    """`_listed_branches` of the branches `args` prints in `cwd`. A listing
    that fails raises as `run` fails a command, `CommandFailed`."""
    listed = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    if listed.returncode:
        raise CommandFailed(args, cwd, listed.returncode,
                            listed.stderr.decode("utf-8", "replace"))
    return _listed_branches(listed.stdout, BRANCH_REFS)


def _branches_at(url: str, cwd: Path) -> dict[str, str]:
    """Every branch of the repository at `url`, as a push to it meets them.
    A LOCAL path's are its own refs, `git for-each-ref` (#520): `git
    ls-remote` leaves out a branch the repository hides with `hideRefs`, and
    a push into it meets that branch all the same. Any other url is listed
    with `git ls-remote --heads`, as the push will meet it
    (`_branches_a_clone_gets`). One that cannot be listed fails as `run`
    fails a command, `CommandFailed`, and in `execute` before any leg
    exists: `_refuse_a_split_branch_left_behind` has just asked the same
    repository, and a failure there is the same."""
    if remote_is_a_path(url):
        return _listed_by(["git", "for-each-ref", REF_LISTING, BRANCH_REFS],
                          Path(url))
    return _branches_a_clone_gets(url, cwd)


def _branches_a_clone_gets(url: str, cwd: Path) -> dict[str, str]:
    """The branches the repository at `url` gives a fetch or a clone: `git
    ls-remote --heads`, which leaves out one it hides with `hideRefs`. Of a
    local source, these are the branches `_extract_leg`'s `git clone` gets,
    and so the ones its `git filter-repo` meets."""
    return _listed_by(["git", *FILE_PROTOCOL, "ls-remote", "--heads", "--",
                       url], cwd)


def _in_the_way(branches: dict[str, str], branch: str) -> list[tuple]:
    """`(name, commit, aside)` of each of `branches` that stops
    `refs/heads/<branch>` being created as a new branch: `branch` itself,
    first, then each whose name is a directory of it or lies under it, which
    git cannot hold beside it. COMPARED WITHOUT CASE TOO (#520's A4), as a
    leg's mount path is (`path_overlap`): `aside` is `CASE_ASIDE` for a name
    in the way only once case is ignored, and empty for one that is in the
    way on every disk."""
    found = []
    for name, commit in branches.items():
        overlap = _overlap(branch, name)
        if overlap:
            found.append((name, commit, overlap[1]))
    return sorted(found, key=lambda each: (each[0] != branch, each[0]))


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


def _taken(where: str, run: str, branch: str, name: str, commit: str,
           aside: str = "") -> str:
    """One `plan-split-branch-taken` finding about the push: `where` holds
    the branch `name`, at `commit`, which git cannot hold beside the split
    branch `branch` (once case is ignored, where `aside` says so), and `run`
    pushes the split there."""
    split, held = _spelled(branch), _spelled(name)
    # git's own words, each name spelled as `_spelled` spells it, so a
    # backtick a branch name may hold cannot end the quotation. A disk that
    # ignores case is not measured here, so it is not quoted.
    why = (aside + SPLIT_BRANCH_CASE_CLASH if aside else
           f": `'refs/heads/{held[1:-1]}' exists; cannot create "
           f"'refs/heads/{split[1:-1]}'`")
    return (f"{where} holds the branch {held}, at {commit[:12]}. {run} "
            f"pushes its split commit to {split} there, after both leg "
            "repositories were created and pushed, and git cannot create "
            f"{split} beside {held}{why}. Delete {held} there, or set "
            "`adopt_branch:` in the plan to a branch git can create there.")


def _in_the_extraction(where: str, branch: str, name: str, commit: str,
                       aside: str = "") -> str:
    """One `plan-split-branch-taken` finding: the source, `where`, holds the
    branch `name` at `commit`, which git cannot hold beside the split branch
    `branch` (once case is ignored, where `aside` says so), and
    `_extract_leg`'s `git filter-repo` makes each branch of the source a
    branch of a clone where `branch` is checked out. Either run extracts, so
    the finding is about both."""
    split, held = _spelled(branch), _spelled(name)
    why = (aside + SPLIT_BRANCH_CASE_CLASH if aside else
           ": git holds no branch whose name is a directory of another's, or "
           "lies under it")
    return (f"{where} holds the branch {held}, at {commit[:12]}. "
            f"{EITHER_RUN} extracts a leg from a clone of the source with "
            f"the plan's split branch {split} checked out in it, after both "
            "leg repositories were created, and `git filter-repo` cannot "
            f"create {held} beside {split} there{why}. Delete {held} there, "
            "or set `adopt_branch:` in the plan to a branch git can create "
            "there.")


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
        for name, commit, aside in _in_the_way(branches, branch):
            if name != branch and extracted:
                found.append(f"FINDING {SPLIT_BRANCH_TAKEN}: "
                             + _in_the_extraction(where, branch, name,
                                                  commit, aside))
            elif name != branch and pushed_by:
                found.append(f"FINDING {SPLIT_BRANCH_TAKEN}: "
                             + _taken(where, pushed_by, branch, name, commit,
                                      aside))
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
        git_out(["for-each-ref", REF_LISTING, refs], cwd=path, binary=True),
        refs)


def _places_in_the_source(where: str, path: Path, extracting: bool) -> list:
    """The source at `path`, named `where`, as the place a run with
    `--local-remote-dir` pushes the split to, `(where, pushed_by, extracted,
    branches)`, as `_split_branch_findings` asks it: its own branches, as
    the push meets them (`_branches_at`). While `extracting`, those a clone
    of it gets (`_branches_a_clone_gets`) are met by either run's extraction
    too, and one it hides from a clone with `hideRefs` (#520) is met by the
    push alone, a second place, so a finding about it is about that run."""
    branches = _branches_at(str(path), path)
    if not extracting:
        return [(where, LOCAL_RUN, False, branches)]
    cloned = _branches_a_clone_gets(str(path), path)
    return [(where, LOCAL_RUN, True,
             {name: tip for name, tip in branches.items() if name in cloned}),
            (where, LOCAL_RUN, False,
             {name: tip for name, tip in branches.items()
              if name not in cloned})]


def _places_check_asks(plan: Plan, source: Source, extracting: bool) -> list:
    """The places `check` asks for the split branch, `(where, pushed_by,
    extracted, branches)`: the source, which a run with `--local-remote-dir`
    pushes to and either run extracts from while `extracting`
    (`_places_in_the_source`), and, where the source's `origin` is the
    assembly repository, that repository's branches as the source last
    fetched them, which a run without it pushes to. `check` reads no
    network for either."""
    places = _places_in_the_source(f"the source {_shown(str(source.path))}",
                                   source.path, extracting)
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
    `_submodule_findings` returns it. A split branch whose name `execute`
    will not hand git is not asked about (#520): `_entry_findings` names it,
    as `unsafe-value` or `plan-bad-adopt-branch`, and `execute` refuses it
    before any leg exists."""
    if _branch_name_refusal(plan, *SPLIT_BRANCH_KEY) is not None:
        return [], []
    key, default, _ = SPLIT_BRANCH_KEY
    branch = checked_value(key, plan.get(key, default))
    extracting = _extracts_a_leg(assigned_paths(plan.entries))
    found = _split_branch_findings(
        branch, _places_check_asks(plan, source, extracting), source)
    return found, [SPLIT_BRANCH_REMEDIATION] if found else []


def _a_leg_may_be_on_disk(urls: dict) -> bool:
    """Whether, under `--local-remote-dir`, a leg's bare repository is at
    its url, or may be: its `stat` refused for another reason than that
    nothing is there (a `--local-remote-dir` this user cannot search), asked
    as `_is_a` asks it (#430).

    Either way the split branch's two refusals, which defer to a leg still
    on disk, defer: `_refuse_what_stands_in_the_legs_way` names both, before
    either leg is made, a leg already there as `leg-remote-exists` and a
    directory this user cannot search or write in as
    `adopt-folder-cannot-be-made`. `Path.exists()` raised the refused `stat`
    out of `execute` on Python 3.9 to 3.13, a `PermissionError` traceback
    before either question was asked, and on 3.14 answered False, and the
    split branch was asked about first."""
    for role in EXTRACTED_LEGS:
        try:
            if _is_there(Path(urls[role])):
                return True
        except OSError:
            return True
    return False


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
    also what the extraction clones: the places `check` asks there
    (`_places_in_the_source`), its own branches as the push meets them and
    those a clone of it gets, and each finding is `check`'s, word for word.
    Without it, the branches a clone of the source gets are asked for the
    extraction, reading no network, and each finding is `check`'s, word for
    word: a branch the source hides from a clone (#520) is met by no part
    of this run. Then the assembly repository on GitHub, as the push will
    meet it, which `check` reads as the source's `origin` last fetched it,
    if at all.
    """
    if local and _a_leg_may_be_on_disk(urls):
        return
    the_source = f"the source {_shown(str(source.path))}"
    if local:
        places = _places_in_the_source(the_source, source.path, extracting)
    else:
        places = [(the_source, None, True,
                   _branches_a_clone_gets(str(source.path), source.path))
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
    # A bare repository on disk has no visibility, so under
    # `--local-remote-dir` none is printed: `execute` creates the legs with
    # `git init --bare`, and never calls `gh repo create` (#906).
    visibility = ("" if local else
                  f" ({_shown(str(plan.get('visibility', 'private')))})")
    print(f"  create {names['spec']} and {names['code']}{visibility}")
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
    # Beside the mounts, the path the read-across follow-up leaves to them,
    # from the mounts as the plan stands (#600's review, F1).
    across = contracts_from_code_leg(mounts[0], mounts[1],
                                     _leg_paths(plan)["spec"],
                                     _plan_follow_ups(plan))
    print(f"  ONE split commit on branch "
          f"{_shown(str(plan.get('adopt_branch', ADOPT_BRANCH)))} "
          f"of {names['assembly']}: `git rm -r` those paths, mount the "
          f"legs{mounted}{across}")
    print(f"  {len(stays)} path(s) stay in the assembly root; "
          f"{len(drops)} dropped")
    # Each pin `execute` writes, as the plan records it (#273) and as the
    # pin file will say it: `local-clone`, and not the clone's path the
    # plan records beside it (`_recorded_pins`, #540). A pin it
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
    writes the shape's copy beside it under `shape/`; the symlink it met that
    git does not make as the blob holds it, if any, whose target is empty
    (#303, #388), holds a NUL byte, or is longer than Linux takes (#908),
    and which a finding of the source names and the walk does not; and,
    once a symlink has been met, what stops it, or None."""

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
        self._tree = tree
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
        self._blobs: dict[str, bytes] | None = None
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
            self._targets[real] = _git_path(self._read(oid))
        return real, self._targets[real]

    def _read(self, oid: str) -> bytes:
        """The target the symlink blob `oid` holds, from the one batch read
        of every link's target (`symlink_targets`, #908): a link's own `git
        cat-file` per walk, per disk and per question was 15 processes for
        five links, and is now none beyond the batch, which `Source` keeps
        for the whole command. A link of size 0 is the empty blob, read
        from no one. A blob the batch did not return is read alone, as it
        was, and git says why it cannot."""
        if self._blobs is None:
            empty = {row_oid: b"" for _, mode, row_oid, size in self._tree
                     if mode == SYMLINK_MODE and not size}
            self._blobs = {**empty, **symlink_targets(self.source,
                                                      self._tree)}
        if oid in self._blobs:
            return self._blobs[oid]
        return git_out([GIT_CAT_FILE, "blob", oid], cwd=self.source.path,
                       binary=True)

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
        if _unmade_target(target.encode("utf-8", "surrogateescape")):
            # A target that begins with NUL ends there, and is as empty to
            # Linux as an empty one: `plan-empty-symlink` names both (#388).
            # One that holds a NUL further on, or is longer than Linux takes,
            # is not the link the blob says: `plan-bad-symlink-target` names
            # it (#908). The walk goes no further along any of them, and
            # names none: one link, one finding.
            walk.empty = at
            walk.problem = (f"the symlink {_spelled(at)} has an empty target, "
                            "which leads nowhere")
            if target and not target.startswith("\0"):
                walk.problem = (f"the symlink {_spelled(at)} has a target "
                                "git does not make as it stands")
            return []
        last = not queue
        if _absolute_here(target):
            leads = (f"the symlink {_spelled(at)} leads to "
                     f"{_spelled(target)}, {ON_THIS_MACHINE}")
            if last:
                self._outside(walk, target, leads, ", and nothing is there")
            else:
                walk.problem = leads
            return []
        parts = target.split("/")
        return ([(part, at, last, ()) for part in parts[:-1]]
                + [(parts[-1], at, last, ((at, target), *ends))] + queue)

    @staticmethod
    def _outside(walk: _Walk, place: str, lead: str, nothing: str) -> None:
        """`walk` leaves the assembly for `place` on this machine's disk:
        taken where something is there, else `lead` and `nothing`, which
        says nothing is there, are what stops it. Windows may spell a place
        with backslashes; it is named with slashes, as every other path is.

        A `stat` THE OPERATING SYSTEM REFUSED for another reason than that
        nothing is there (a directory above `place` this user cannot
        search) stops it too, `<place>: cannot be read (<reason>)` after
        `lead` (#430): `os.path.exists` answered False to it on every
        Python, and the finding said "nothing is there" of a place that
        holds something. `place` is asked as the text it is, as
        `os.path.exists` asked it: a `Path` drops a trailing `/`, which a
        `stat` takes only from a directory."""
        walk.outside, walk.landed = True, Path(place).as_posix()
        walk.taken = False
        try:
            os.stat(place)
        except OSError as exc:
            walk.problem = lead + (nothing if _absent(exc) else (
                f", and {_spelled(walk.landed)}: cannot be read "
                f"({_os_reason(exc)}), so whether anything is there cannot "
                "be told"
                + (" until this user can search every directory above it "
                   "(`chmod u+rx`)" if isinstance(exc, PermissionError)
                   else "")))
        except ValueError:
            # a name the operating system cannot take at all (a NUL in it)
            walk.problem = lead + nothing
        else:
            walk.taken = True

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
        self._outside(walk, place,
                      f"{climbs}, to {_spelled(Path(place).as_posix())}",
                      ", where nothing is")
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
        what = "a directory" if is_dir else A_FILE
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


def _root_symlink_findings(plan: Plan, source: Source, tree: list,
                           probe: _SymlinkProbe | None = None) -> list[str]:
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

    A walk that stops at a symlink with an empty target, or one that begins
    with a NUL byte (#388), is #303's to say: `plan-empty-symlink` names
    every such symlink in the source, first in `_entry_findings`' list, with
    the fix in the source, so it is not said again here, wherever in the
    walk's chain that symlink is. So is one that holds a NUL byte further
    on, or is longer than Linux takes, which `plan-bad-symlink-target` names
    and says what git makes of it (#908): the walk used to read `ci\x00xx`
    as where `.github` leads, and called that not in the source tree, where
    Linux makes `.github` a link to `ci`.

    Where `git` checks a symlink out as a plain file, the link a reported
    walk meets first ABOVE its path is that file in the clone, and the
    finding says so, as `adopt-symlinks-off` does, in place of where the
    link leads (`_a_file_above`, L1-J3 of #183's re-verify, #531). It is
    still the one finding for that link, in the same place in the list, and
    a link the walk follows into something the root keeps is still no
    finding of this check's: `execute` refuses it after this list, as
    `adopt-symlinks-off`.

    `probe` is `_entry_findings`' one probe, which `plan-file-reencoded`'s
    walks share, so git is asked that once (#654).
    """
    findings: list[str] = []
    if not any(mode == SYMLINK_MODE for _, mode, _, _ in tree):
        return findings
    seen = _links_at_a_copy(plan, tree) | _links_at_a_pin(plan, tree)
    if probe is None:
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
    target never comes here: that symlink is #303's `plan-empty-symlink`,
    and a target git does not make as it stands is #908's
    `plan-bad-symlink-target`.

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


# ---------------------------------------------------------------------------
# A `.gitattributes` the plan keeps BELOW the root, over a pinned copy (#530)
# ---------------------------------------------------------------------------
#
# #471 gives every pinned copy at the root ONE line-ending rule: a `/<copy>
# text eol=lf` line in the block the split appends to the source's own root
# `.gitattributes` (`shape_materialize.with_eol_block`), or, where the source
# keeps none, the shape's own `* text=auto eol=lf`. Git reads attributes for a
# path from the `.gitattributes` of its own directory and of each directory
# above it, and a deeper file outranks a shallower one, so a source's
# `.github/.gitattributes` or `scripts/.gitattributes` that the plan keeps in
# the root outranks that rule for each copy under it. Measured on main at
# 2247dbff with git 2.43: `*.yml eol=crlf` in a kept `.github/.gitattributes`
# -- or `* text=auto eol=crlf`, or a macro the root defines to say it --
# checked `.github/workflows/validate.yml` out with CRLF in every clone,
# Linux's included, and `* !eol` did so in every clone that writes CRLF
# (`core.autocrlf=true`, Git for Windows' default, or `core.eol=crlf`). Each
# time `execute` said `adoption verified` and exited 0, and the root's first
# `make bootstrap` reported shape-copy-drift: `validate-pins.py` digests the
# bytes on disk (#51).
#
# A FINDING, NOT A WRITE. Brett Heap ruled at 2026-10-12T22:48Z that the
# root's `.gitattributes` is the ONE file of the source's that the split
# writes into, because no file beside it can reach the copies at the root. A
# nested file is not that case: the person can end it, in the source, with
# the lines the finding names, or keep it out of the root, and neither needs
# this tool to write a second file of theirs, to make a second exception to
# "by blob sha" in the verification, or to give `update-shape.py --add` a
# second block to extend. So `check` finds it, and `execute` refuses it with
# every other finding of `check`'s, before any leg exists (#168).
#
# GIT IS ASKED, NEVER IMITATED (`_AttributesProbe`): patterns, macros,
# precedence and what `crlf`, `text` and `eol` make of each other are git's.
# A throwaway repository holds, where the split's tree will hold them, only
# the root's `.gitattributes` as the split writes it, the shape's
# `shape/.gitattributes` where that goes beside the source's, and the kept
# nested files, and `git check-attr` is asked about each pinned copy where
# the split puts it: `_PlannedRoot`'s walks, which follow the root's symlinks
# as the materializer does. No system or global attributes file is read, nor
# a tree `GIT_ATTR_SOURCE` or `attr.tree` names, nor system or global config,
# since a clone on another machine has none of them (`_probe_env`). What a
# checkout then writes over the copy's LF blob is `checked_out_as`: the blob
# itself where the copy is not text or says `eol=lf`, CRLF everywhere where
# it says `eol=crlf`, and CRLF wherever git is set to write it where it is
# text and says no `eol`; git reads `text` first, and `crlf` only where
# `text` is unspecified, both measured with real checkouts. So
# `-text` and `binary` are no finding: a checkout writes a file that is not
# text as its blob, and the blob is LF (measured too).
#
# ONE FINDING PER CAUSE. A copy is outranked when the root's own files keep
# it LF and the kept nested files, added, do not. Each kept file that,
# added to the root's own files alone, makes a checkout write such a copy
# with CRLF is named once (and only where no file alone does, each that
# changes what git says of the copy), with every outranked copy it reaches
# and the line its own directory spells for each; a copy still outranked
# once those lines are in is named again by the next `check`, under the
# file that then decides it. A deeper kept file that restores LF leaves
# nothing to find, and one that alone keeps the copy LF is not named. A root
# `.gitattributes` that is a symlink to a path, which gives no rule (git
# follows no such link, and a checkout reads only the link's own text, the
# path it leads to, which names no attribute unless it holds a space, a tab
# or a carriage return, #906), is #471's follow-up, not this finding: its
# copies are asked against the block that follow-up asks a regular file to
# hold, so a kept nested file is still found, and the finding names that
# block's rule.
# Asked as a disk that keeps case does and again as one that ignores it, as
# #262's findings are: there `core.ignorecase` folds git's patterns, and a
# kept `.GitHub/.gitattributes` is read for `.github/`. A finding only the
# second makes says so.

#: `check`'s finding, and the code of `execute`'s refusal, for a kept
#: `.gitattributes` below the root that outranks the root's line-ending rule
#: for a pinned copy, or the one #471's follow-up asks a root that is a
#: symlink to hold (#530).
NESTED_ATTRIBUTES = "plan-nested-attributes"

#: The copies the shape pins, in the pin's order: what `_materialize` lists
#: in `Materialized.shape_files`, each at its own path or under `shape/`.
PINNED_COPIES = (*COPIED_VERBATIM, *(rel for _, rel in COPIED_FROM_SHAPE))

#: Where the materializer copies the shape's files from for the split,
#: `materialize_assembly_root(SHAPE_ROOT, ...)`: the bytes each pinned copy
#: lands with, and the shape's own `.gitattributes`. Not `ASSEMBLY_TEMPLATE`,
#: which #181's gate reads and a test may point elsewhere (#654).
SPLIT_TEMPLATE = SHAPE_ROOT / "templates" / "assembly-root"

#: The attributes a checkout reads a file's line endings from. Git's
#: `convert.c` reads `text` first, and `crlf`, its old spelling, only where
#: `text` is unspecified.
LINE_ENDING_ATTRIBUTES = ("crlf", "text", "eol")

#: What `crlf` or `text` asks of a checkout, as git's `git_path_check_crlf`
#: reads either one: not text, text checked out as it was checked in, and
#: the rest. Any other value is no answer, and the next is read.
_NOT_TEXT, _AS_CHECKED_IN = "binary", "input"
_TEXT_ACTIONS = {"set": "text", "unset": _NOT_TEXT,
                 _AS_CHECKED_IN: _AS_CHECKED_IN, "auto": "auto"}

#: What a checkout writes over a pinned copy's LF blob (`checked_out_as`).
KEPT = "kept"
CRLF_EVERYWHERE = "everywhere"
CRLF_BY_CONFIG = "by config"

#: What a question to `git check-attr` must not inherit: a repository, an
#: index or a work tree named for another one; a tree to read attributes
#: from instead of the work tree (`GIT_ATTR_SOURCE`); and a parent git's
#: `-c` settings, whose quoted form is not read here and none of which the
#: question needs (`GIT_CONFIG_PARAMETERS`).
_NOT_INHERITED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                  "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_ATTR_SOURCE",
                  "GIT_CONFIG_PARAMETERS")
#: The setting that reads attributes from a tree instead of the work tree.
ATTR_TREE = "attr.tree"


def _inherited_env() -> dict:
    """This process's environment, as a question to a throwaway repository
    inherits it: with nothing of `_NOT_INHERITED`, and no `attr.tree` in
    git's command scope (`GIT_CONFIG_COUNT`), whose other entries are kept
    in their order. Git 2.43 reads `attr.tree` from any config, and one
    naming the empty tree made `check-attr` read no rule at all, which
    silenced the finding; `GIT_ATTR_SOURCE=HEAD` made git fail in the empty
    repository."""
    count = os.environ.get("GIT_CONFIG_COUNT", "")
    scoped = [(os.environ.get(f"GIT_CONFIG_KEY_{n}", ""),
               os.environ.get(f"GIT_CONFIG_VALUE_{n}", ""))
              for n in range(int(count) if count.isdigit() else 0)]
    env = {name: value for name, value in os.environ.items()
           if name.upper() not in _NOT_INHERITED
           and not re.fullmatch(r"GIT_CONFIG_(COUNT|KEY_\d+|VALUE_\d+)",
                                name.upper())}
    kept = [(key, value) for key, value in scoped
            if key.lower() != ATTR_TREE]
    for n, (key, value) in enumerate(kept):
        env[f"GIT_CONFIG_KEY_{n}"], env[f"GIT_CONFIG_VALUE_{n}"] = key, value
    if kept:
        env["GIT_CONFIG_COUNT"] = str(len(kept))
    return env


def _probe_env(nothing: Path) -> dict:
    """The environment `git check-attr` is asked in: `_inherited_env()`,
    with no system config and the empty file `nothing` as the global
    config. Each could steer the answer here and holds nothing on another
    machine, as `attr.tree` from either did."""
    env = _inherited_env()
    env.update(GIT_ATTR_NOSYSTEM="1", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=str(nothing))
    return env


def checked_out_as(values: dict) -> str:
    """What a checkout writes over an LF blob whose `crlf`, `text` and `eol`
    are `values`, as `git check-attr` prints them: `KEPT`, the blob itself
    on every platform; `CRLF_EVERYWHERE`; or `CRLF_BY_CONFIG`, CRLF wherever
    `core.autocrlf` or `core.eol` asks for it, as Git for Windows' default
    does.

    Git's `convert.c`, `convert_attrs`, read for a checkout: `text`, else
    `crlf`, says whether the file is text, and one that is not is written as
    its blob. Then `eol=lf` keeps LF and `eol=crlf` writes CRLF; with
    neither, only `input` keeps LF without asking the configuration."""
    crlf, text, eol = (values.get(name, "") for name in LINE_ENDING_ATTRIBUTES)
    action = _TEXT_ACTIONS.get(text) or _TEXT_ACTIONS.get(crlf)
    if action == _NOT_TEXT or eol == "lf":
        return KEPT
    if eol == "crlf":
        return CRLF_EVERYWHERE
    return KEPT if action == _AS_CHECKED_IN else CRLF_BY_CONFIG


class _AttributesProbe:
    """A throwaway repository to ask `git check-attr` in: each question's
    `.gitattributes` files are written into a work tree of their own, which
    holds nothing else. Made where `_ask_git_branch` makes its own, in the
    system's temporary directory, and removed on leaving the `with`."""

    def __init__(self) -> None:
        self._scratch = Path(tempfile.mkdtemp(
            prefix="openreposhape-attributes-"))
        self._asked = 0
        #: An empty file, read in place of the person's own global config
        #: and `core.attributesFile`.
        self._nothing = self._scratch / "nothing"
        self._env = _probe_env(self._nothing)
        self._git_dir = self._scratch / "repository" / ".git"

    def __enter__(self) -> "_AttributesProbe":
        try:
            empty = self._scratch / "no-template"
            empty.mkdir()
            self._nothing.write_bytes(b"")
            git_out(["init", "-q", f"--template={empty}",
                     str(self._git_dir.parent)], cwd=self._scratch,
                    env=self._env)
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        shutil.rmtree(self._scratch, ignore_errors=True)

    def ask(self, layout: dict, paths: list[str],
            fold: bool) -> dict[str, dict[str, str]]:
        """`{path: {attribute: value}}` for each of `paths`, with the
        `.gitattributes` files `layout` holds (`{path: bytes}`) where git
        reads them, and git ignoring case where `fold` says so."""
        self._asked += 1
        tree = self._scratch / f"tree-{self._asked}"
        tree.mkdir()
        for rel, data in layout.items():
            target = tree.joinpath(*rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        raw = git_out([f"--git-dir={self._git_dir}", f"--work-tree={tree}",
                       "-c", f"core.ignorecase={str(fold).lower()}",
                       "-c", f"core.attributesFile={self._nothing}",
                       "check-attr", "-z", *LINE_ENDING_ATTRIBUTES, "--",
                       *paths], cwd=tree, binary=True, env=self._env)
        fields = raw.split(b"\0")
        said: dict[str, dict[str, str]] = {}
        for at in range(0, len(fields) - 2, 3):
            path, name, value = (field.decode("utf-8", "surrogateescape")
                                 for field in fields[at:at + 3])
            said.setdefault(path, {})[name] = value
        return said


def _kept_nested_attributes(plan: Plan, tree: list) -> list[tuple]:
    """`(path, mode, blob, entry)` for each `.gitattributes` below the root
    that the plan keeps in the root, in the tree's order, one so named only
    once case is ignored among them, for the disk that ignores it.

    A SYMLINK IS ONE. Git follows none to read attributes, but a checkout
    reads each `.gitattributes` from the index first, and there a symlink's
    blob is its target, which git then reads as the file's rules: measured
    with git 2.43, a kept `.github/.gitattributes` linking to `*.yml
    eol=crlf` checked `.github/workflows/validate.yml` out with CRLF. A
    target with no space, tab or carriage return, a path, is a pattern and
    names no attribute, and changes nothing; one with any of them is a
    pattern and the attributes after it, as any line of the file is read, so
    every link is asked like a file (#906: measured with `config/attributes`,
    which left the copy LF, and `*.yml eol=crlf`, `*.yml` TAB `eol=crlf` and
    `*.yml` CR `eol=crlf`, which wrote it CRLF)."""
    blobs = {path: oid for path, _, oid, _ in tree}
    return [(path, mode, blobs[path], entry)
            for path, mode, entry in _kept_in_root(plan.entries, tree)
            if "/" in path and mode in (*FILE_MODES, SYMLINK_MODE)
            and path.rsplit("/", 1)[1].casefold() == ATTRIBUTES]


def _pinned_landings(walks: list) -> list[tuple[str, str]]:
    """`(the name the pin gives it, where the split puts it)` for each copy
    the shape pins, in the pin's order, as `place` writes it: at its own
    path, or under `shape/` where that is taken, followed through the
    root's symlinks. A copy a walk cannot write, or one it writes outside
    the assembly, is another finding's, and is left out."""
    by_path = {walk.path: walk for walk in walks}
    landings = []
    for rel in PINNED_COPIES:
        name, walk = rel, by_path.get(rel)
        if walk is not None and walk.problem is None and walk.taken:
            name = f"{COLLISION_DIR}/{rel}"
            walk = by_path.get(name)
        if walk is None or walk.problem is not None or walk.outside \
                or walk.taken:
            continue
        landings.append((name, walk.landed))
    return landings


def _root_attributes(source: Source, walks: list, disk: _KeptTree,
                     tree: list, names: list[str]) -> dict:
    """The `.gitattributes` the split puts at the root, and under `shape/`,
    as `{path: bytes}`. Where the root keeps none, the shape's own. Where it
    keeps one, the shape's goes beside it and the split appends the block
    for the copies `names` outside `shape/` (#471), each named where `walks`
    land it, the path git tracks, and by its own name where that differs
    (#807); a kept one that is not a regular file gets no block, so it is
    asked as the block alone, the lines #471's follow-up asks a regular file
    in its place to hold."""
    shapes = (SPLIT_TEMPLATE / ATTRIBUTES).read_text(
        encoding="utf-8").encode("utf-8")
    walk = next((walk for walk in walks if walk.path == ATTRIBUTES), None)
    if walk is None or not walk.taken:
        return {ATTRIBUTES: shapes}
    row = disk.at(ATTRIBUTES)
    blobs = {path: oid for path, _, oid, _ in tree}
    own = (_blob_bytes(source.path, blobs[row[0]])
           if row and row[1] in FILE_MODES else b"")
    return {ATTRIBUTES: with_eol_block(own, eol_block_paths(
                names, COLLISION_DIR, dict(_pinned_landings(walks)))),
            f"{COLLISION_DIR}/{ATTRIBUTES}": shapes}


def _placed_attributes(nested: list[tuple], landed: list[str],
                       fold: bool) -> dict:
    """`{where git reads it: row}` for each row of `nested` in a directory
    above where a pinned copy lands, spelled as that place spells it; on a
    disk that ignores case, the first of two twins."""
    def key(path: str) -> str:
        return path.casefold() if fold else path

    above: dict[str, str] = {}
    for path in landed:
        parts = path.split("/")
        for end in range(1, len(parts)):
            here = "/".join(parts[:end])
            above.setdefault(key(here), here)
    placed: dict[str, tuple] = {}
    for row in nested:
        directory, _, name = row[0].rpartition("/")
        spelled = above.get(key(directory))
        if spelled is not None and key(name) == ATTRIBUTES:
            placed.setdefault(f"{spelled}/{ATTRIBUTES}", row)
    return placed


def _copy_line(rel: str) -> str:
    """The line a kept file's own directory spells for the copy at `rel`
    below it, between backticks; for a name no line can spell literally,
    which a symlink the root keeps can lead a copy to, what to write."""
    if EOL_PATH_RE.fullmatch(rel):
        return f"`{eol_line(rel)}`"
    return f"a `text eol=lf` line that names {_spelled(rel)}"


def _nested_attributes_finding(row: tuple, at: str, copies: list[str],
                               written: list[str], aside: str,
                               linked: bool = False) -> str:
    """`check`'s line for the kept file `row`, which git reads at `at`, and
    the outranked `copies` it reaches, each written as `written` says.
    `linked` says the root's own `.gitattributes` is a symlink, which gives
    no rule: the rule outranked is then the one #471's follow-up asks a
    regular file in its place to hold (#654's L1-11)."""
    path, mode, _, entry = row
    rule = (f"the line-ending rule #471's follow-up asks a regular root "
            f"`{ATTRIBUTES}` to hold (the root's is a symlink, which gives "
            "none)" if linked else "the root's line-ending rule")
    directory = at[:-len(ATTRIBUTES) - 1]
    many = len(copies) > 1
    under = "" if entry == path else f" under the entry {_spelled(entry)}"
    where = (("on such a disk, whatever git is set to" if aside else
              "on every platform, Linux and macOS included")
             if CRLF_EVERYWHERE in written else
             "wherever git writes them, as Git for Windows does by default "
             "(`core.autocrlf=true`)")
    lines = ", ".join(_copy_line(copy[len(directory) + 1:])
                      for copy in copies)
    end = (f"replace the symlink {_spelled(path)} in the source with a "
           "regular file that ends" if mode == SYMLINK_MODE else
           f"end {_spelled(path)} in the source")
    return (
        f"FINDING {NESTED_ATTRIBUTES}: the plan keeps {_spelled(path)} in "
        f"the assembly root{under}, and git reads it after the root's own "
        f"`{ATTRIBUTES}` for each path under {_spelled(directory + '/')}, so "
        f"its rules outrank {rule} for the pinned "
        f"{'copies' if many else 'copy'} "
        f"{_first_and_more(copies, _spelled)}{aside}: a clone would check "
        f"{'them' if many else 'it'} out with CRLF line endings {where}, and "
        "the root's first `make bootstrap` would report shape-copy-drift on "
        f"{'each' if many else 'it'}, after `execute` had said `adoption "
        f"verified`. Send {_spelled(entry)} to a leg or `drop` it, or {end} "
        f"with {'these lines, one per copy:' if many else 'the line'} "
        f"{lines}, commit, and re-run `plan`.")


def _outranking(asked: _AttributesProbe, fold: bool, landed: list[str],
                root: dict, placed: dict,
                linked: bool = False) -> list[tuple[str, str]]:
    """`(path, finding)` for each kept nested file that outranks the root's
    rule for a copy landed at one of `landed`, asked of git on the disk
    `fold` says. `root` is `_root_attributes`', and `placed` is
    `{where git reads it: (row, its bytes)}`.

    A file is named for a copy when, added to the root's files alone, it
    makes a checkout write that copy with CRLF. Where no file alone does,
    and two or more do it only together, each that changes what git says
    of the copy is named."""
    held = {at: data for at, (_, data) in placed.items()}
    before = asked.ask(root, landed, fold)
    after = asked.ask({**root, **held}, landed, fold)
    outranked = [path for path in landed
                 if checked_out_as(before[path]) == KEPT
                 and checked_out_as(after[path]) != KEPT]
    alone = {}
    for at, data in held.items():
        under = [path for path in outranked
                 if path.startswith(at[:-len(ATTRIBUTES)])]
        alone[at] = asked.ask({**root, at: data}, under, fold) if under else {}
    breaks = {(at, path) for at, said in alone.items() for path in said
              if checked_out_as(said[path]) != KEPT}
    broken = {path for _, path in breaks}
    found = []
    for at, (row, _) in placed.items():
        copies = [path for path in alone[at] if (at, path) in breaks
                  or (path not in broken
                      and alone[at][path] != before[path])]
        if copies:
            found.append((row[0], _nested_attributes_finding(
                row, at, copies, [checked_out_as(after[path])
                                  for path in copies],
                _CASE_ASIDE if fold else "", linked)))
    return found


def _nested_attributes_findings(plan: Plan, source: Source,
                                tree: list) -> list[str]:
    """A FINDING for each `.gitattributes` the plan keeps below the root
    whose rules outrank the root's line-ending rule for a pinned copy (#530),
    in the tree's order. A source that keeps none above a copy asks git
    nothing, and adopts as it did."""
    nested = _kept_nested_attributes(plan, tree)
    if not nested:
        return []
    kept = _kept_in_root(plan.entries, tree)
    probe = _SymlinkProbe(source.work_root)
    questions = []
    for fold in (False, True):
        walks = _PlannedRoot(plan, source, tree, probe=probe,
                             fold=fold).walks()
        landings = _pinned_landings(walks)
        landed = [where for _, where in landings]
        placed = _placed_attributes(nested, landed, fold)
        if not placed:
            continue
        disk = _KeptTree(kept, fold)
        root = _root_attributes(source, walks, disk, tree,
                                [name for name, _ in landings])
        # The shape's own `shape/.gitattributes` is written where the source
        # keeps one only if nothing is there: `plan-root-blocks-shape-copy`
        # names what is (#262), and it is not named again here.
        placed = {at: (row, _blob_bytes(source.path, row[2]))
                  for at, row in placed.items() if at not in root}
        top = disk.at(ATTRIBUTES)
        linked = (top is not None and top[1] == SYMLINK_MODE
                  and f"{COLLISION_DIR}/{ATTRIBUTES}" in root)
        if placed:
            questions.append((fold, landed, root, placed, linked))
    if not questions:
        return []
    found: dict[str, str] = {}
    with _AttributesProbe() as asked:
        for fold, landed, root, placed, linked in questions:
            for path, finding in _outranking(asked, fold, landed, root,
                                             placed, linked):
                found.setdefault(path, finding)
    return [found[row[0]] for row in nested if row[0] in found]


# ---------------------------------------------------------------------------
# The root's own `.gitattributes`, as `git add` stores it (#530, D5(a))
# ---------------------------------------------------------------------------
#
# THE ONE FILE OF THE SOURCE'S THE SPLIT WRITES INTO (#471) is staged again
# by the split's `git add -A`, and git stores it through its rules for it. A
# blob the source committed with CRLF under `* text eol=lf`, `* text
# eol=crlf` or `* eol=lf` was stored as LF, so the root held neither the
# source's blob nor its bytes followed by the block, and the verification
# ended `adopt-lost` after both legs existed (measured at 2423eaa2: lane 2's
# D5(a) line on #530; `* ident` over a `$Id: deadbeef $` did the same).
# `text=auto` leaves alone a file whose indexed blob already holds CRLF, so
# a CRLF blob under it adopted, as an LF blob did under every rule.
#
# GIT IS ASKED, AS THE SPLIT ASKS IT (`_stored_as_written`). A throwaway
# repository's index holds the source's blob at `.gitattributes`, as the
# assembly's checkout does, so the check-in rules that read the index answer
# as they do there; its work tree holds what the verification expects at the
# root (`_land_the_eol_block`), the source's bytes followed by the block
# (`_root_attributes`); and `git add` there stores those bytes or not. The
# materializer appends the block to the checkout's bytes, and git's check-in
# undoes what its checkout did to line endings, an `ident` or an encoding,
# so the blob's own bytes get the same answer. UNLIKE THE NESTED QUESTION,
# THIS MACHINE'S SETTINGS ARE READ: the split's `git add` runs here, with
# this machine's config and attributes (`core.autocrlf`, `core.safecrlf`, a
# `filter` driver, `core.attributesFile`), so only `_inherited_env` is taken
# from them: no other repository, and no tree to read attributes from
# (`GIT_ATTR_SOURCE`, `attr.tree`), of which the throwaway repository has
# none. What `git add` refuses there -- `core.safecrlf=true` over such a
# CRLF, or a `working-tree-encoding` the bytes are not in -- would stop the
# split committing after both legs exist, and is found too, in git's words.
#
# A FINDING, as the nested one is: the fix is the source's, a commit of the
# file as git stores it, and `execute` refuses it before any leg exists. A
# root that keeps no `.gitattributes` of the source's, or keeps a symlink
# there, which the split writes nothing into, asks git nothing. Another kept
# file whose blob `git add` would re-encode fails the same way when git reads
# it again; asking about each one needs a checkout of the whole source, and
# is not done here.

#: `check`'s finding, and the code of `execute`'s refusal, for the source's
#: root `.gitattributes` that `git add` would not store as the split writes
#: it (#530, D5(a)).
REENCODED_ATTRIBUTES = "plan-attributes-reencoded"


def _stored_as_written(blob: bytes, mode: str,
                       written: bytes) -> tuple[str | None, bool]:
    """`(None, …)` when this machine's `git add` stores `written` at the
    root's `.gitattributes`, over an index that holds `blob` there with
    `mode`, as exactly those bytes; else what it did: git's last line where
    it refused, or "" where it stored other bytes. And whether a
    `working-tree-encoding` rule reaches the file itself, which leaves the
    split's checkout of it a file git reads no rule from (#654's L1-12).
    Asked in a throwaway repository in the system's temporary directory,
    removed afterwards."""
    scratch = Path(tempfile.mkdtemp(prefix="openreposhape-attributes-"))
    env = _inherited_env()
    # No fsmonitor daemon is started for a repository that is about to go.
    git = ["-c", "core.fsmonitor=false"]
    repository = scratch / "repository"

    def raw_oid(data: bytes, name: str, *write: str) -> str:
        """The oid of `data` as they are, no rule applied; `-w` stores it."""
        (scratch / name).write_bytes(data)
        return git_out([*git, "hash-object", *write, "--no-filters", "--",
                        str(scratch / name)], cwd=repository, env=env)

    try:
        empty = scratch / "no-template"
        empty.mkdir()
        git_out(["init", "-q", f"--template={empty}", str(repository)],
                cwd=scratch, env=env)
        git_out([*git, "update-index", "--add", "--cacheinfo",
                 f"{mode},{raw_oid(blob, 'held', '-w')},{ATTRIBUTES}"],
                cwd=repository, env=env)
        (repository / ATTRIBUTES).write_bytes(written)
        encoded = git_out([*git, "check-attr", "-z", "working-tree-encoding",
                           "--", ATTRIBUTES], cwd=repository, env=env,
                          binary=True).split(b"\0")[2].decode(
                              "utf-8", "replace") not in NO_RULE
        added = subprocess.run(["git", *git, "add", "--", ATTRIBUTES],
                               cwd=str(repository), env=env,
                               capture_output=True, check=False)
        if added.returncode:
            said = added.stderr.decode(errors="replace").strip()
            return (said.splitlines()[-1] if said else
                    f"exit {added.returncode}"), encoded
        staged = git_out([*git, "ls-files", "-s", "--", ATTRIBUTES],
                         cwd=repository, env=env).split()[1]
        return (None if staged == raw_oid(written, "wanted") else ""), encoded
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _reencoded_attributes_finding(said: str, encoded: bool = False) -> str:
    """`check`'s line for the root's `.gitattributes`, which this machine's
    `git add` stores as other bytes (`said` empty) or refuses (`said`, in
    git's words). Where a `working-tree-encoding` rule reaches the file
    itself (`encoded`), the split stops sooner, at mounting the legs, and
    renormalizing stages the encoded bytes: measured with git 2.43 on
    a5245427 (#654's L1-12)."""
    if encoded:
        return (
            f"FINDING {REENCODED_ATTRIBUTES}: the plan keeps the source's "
            f"`{ATTRIBUTES}` in the assembly root, where the split appends "
            "#471's block to it, and a `working-tree-encoding` rule reaches "
            "that file itself: the split's checkout writes it in that "
            "encoding, git then reads no rule from it, and the files its "
            "rules reach are stored again as other bytes, so the mount's `git "
            "rm` refuses those sent to a leg, at mounting the legs, after "
            f"both legs exist. `git add --renormalize -- {ATTRIBUTES}` is no "
            "way out: it stores the encoded bytes, which git reads no rule "
            "from. Keep the rule off the file with the line "
            f"`{ATTRIBUTES} -working-tree-encoding` after it, or narrow the "
            "rule, commit, and re-run `plan`.")
    if said:
        what = (f"refuses what the split writes there (git said "
                f"{_spelled(said)}), so the split's own `git add` would fail, "
                "after both legs exist.")
    else:
        what = ("would store other bytes there than the source's followed by "
                "the block, as git does where its rules for the file make it "
                "text and the blob holds CRLF line endings, or where an "
                "`ident`, `working-tree-encoding` or `filter` rule reaches "
                f"it. The verification would then report the source's "
                f"`{ATTRIBUTES}` as `adopt-lost`, in no leg and not in the "
                "root tree, after both legs exist.")
    return (f"FINDING {REENCODED_ATTRIBUTES}: the plan keeps the source's "
            f"`{ATTRIBUTES}` in the assembly root, where the split appends "
            f"#471's block to it, and this machine's `git add` {what} Commit "
            "the file in the source as git stores it (`git add --renormalize "
            f"-- {ATTRIBUTES}`, then commit), or change the rule git applies "
            "to it, and re-run `plan`.")


def _reencoded_attributes_findings(plan: Plan, source: Source,
                                   tree: list) -> list[str]:
    """A FINDING where the plan keeps the source's own `.gitattributes` in
    the root, which the split appends the block to, and this machine's `git
    add` would not store what the split writes there as those bytes (#530,
    D5(a)). A root that keeps none, or keeps a symlink there, asks git
    nothing."""
    disk = _KeptTree(_kept_in_root(plan.entries, tree), False)
    row = disk.at(ATTRIBUTES)
    if row is None or row[1] not in FILE_MODES:
        return []
    walks = _PlannedRoot(plan, source, tree,
                         probe=_SymlinkProbe(source.work_root)).walks()
    written = _root_attributes(source, walks, disk, tree,
                               [name for name, _ in _pinned_landings(walks)])
    if f"{COLLISION_DIR}/{ATTRIBUTES}" not in written:
        return []
    blobs = {path: oid for path, _, oid, _ in tree}
    said, encoded = _stored_as_written(_blob_bytes(source.path, blobs[row[0]]),
                                       row[1], written[ATTRIBUTES])
    return ([] if said is None
            else [_reencoded_attributes_finding(said, encoded)])


# ---------------------------------------------------------------------------
# Every other file the split's git would store as other bytes (#654)
# ---------------------------------------------------------------------------
#
# NOT ONLY THE ROOT'S OWN `.gitattributes` (#654, lane 1's D5). The split
# clones the source and checks its commit out with this machine's config and
# the source's rules; the mount's `git rm` takes what the plan sends to a leg
# or drops, and the split's `git add -A` stages what the root keeps and what
# the shape writes. Git reads a file again, through its rules, wherever it
# cannot trust the stat data its index holds: every file it checked out in
# the second it wrote that index. A file whose blob those rules do not give
# back -- CRLF under `text`, an expanded `$Id$` under `ident`, bytes a
# `working-tree-encoding` cannot take, a filter's own output -- then failed
# after both legs existed. Measured on main a5245427 with git 2.43: a kept
# one ended `adopt-lost`; one sent to a leg was refused by `git rm` ("local
# modifications") at mounting the legs; git's refusal (`core.safecrlf=true`,
# an encoding) stopped the split committing; and a pinned copy under a
# source's `working-tree-encoding` or `filter` rule (#530's rider) was
# refused the same way, or committed as other bytes than its pin records
# under `adoption verified`. Git reads every file of a small source again,
# and of a large one a share that changes from run to run (852 to 6,803 of
# 20,000 in three identical runs), so `check` asks about every file: it
# finds the source that can fail, not the run that does.
#
# GIT IS ASKED, AS THE SPLIT ASKS IT (`_SplitRehearsal`). A throwaway
# repository borrows the source's objects (alternates: nothing is copied, and
# no byte of the source changes, though where the question stores a blob the
# source holds, git's object freshening sets the modification time of the
# source's pack or loose object file that holds it to now) and runs with this
# machine's config, as `_stored_as_written` does, with git-lfs's smudge
# skipped. First, which rules reach which path: `git
# check-attr --cached` of `BYTE_ATTRIBUTES`, over indexes `read-tree` makes of
# the commit, once as the source holds its rules and once as the split's root
# will (what goes to a leg or is dropped gone, the root's `.gitattributes` as
# the split writes it, the shape's own beside it). Only the files a rule
# reaches are asked further, so a source with no rule costs a `read-tree` and
# a `check-attr`; `text=auto` is asked too, since git is asked, never
# trusted. Then, through indexes that hold no stat data, so that git reads
# every entry again as it reads a file the clock leaves in doubt: those files
# and every `.gitattributes` are checked out with the source's rules, as the
# split's clone writes them; the mount's side is asked as `git rm` asks it, a
# content compare (`update-index --refresh`) in which a conversion git cannot
# make is no change (a file sent to a leg that its encoding refuses adopted);
# the split's side as `git add` stores it, a plain `git add -u` (never
# `--renormalize`, which skips git's protection of a blob that already holds
# CRLF, and so re-stored files `core.autocrlf=true` leaves alone), once the
# moved `.gitattributes` are gone and the root's is written as the split
# writes it; and then each pinned copy, its own bytes where `_pinned_landings`
# lands it. What git refuses on the way is a finding in git's own words.
#
# ONE FINDING PER GROUP, each naming `NAMED_PATHS` paths in the tree's order
# and counting the rest: what the root keeps, what goes to a leg or is
# dropped, the pinned copies, and then each of git's refusals. The root's own
# `.gitattributes` is #530's D5(a) question above, and is not asked again; a
# symlink and a gitlink get no rule applied. The files the split renders
# from values it knows only once the legs are pushed (the manifest, the pin
# files, the README) and the mounts' `.gitmodules` are not asked.

#: `check`'s finding, and the code of `execute`'s refusal, for a file the
#: plan keeps or moves, or a pinned copy, that this machine's git would store
#: as other bytes than the split expects, or refuses (#654).
REENCODED_FILES = "plan-file-reencoded"

#: The attributes that can make git store a checked-out file as other bytes
#: than its blob: its line endings, an `ident`, an encoding and a filter.
BYTE_ATTRIBUTES = ("text", "eol", "crlf", "working-tree-encoding", "ident",
                   "filter")

#: What `git check-attr` prints for an attribute nothing sets.
NO_RULE = ("unspecified", "unset")

#: What a line of the source's own can unset to keep its rule off a pinned
#: copy, whose line endings #471's block already keeps.
COPY_RULES = ("working-tree-encoding", "ident", "filter")

#: How many paths one finding names before it counts the rest.
NAMED_PATHS = 10

#: The rehearsal's index files: the commit as the source holds it, and as
#: the split's root will; what the split's checkout writes; what the mount's
#: `git rm` takes; and what the split's `git add` stores again.
AS_HELD, AS_SPLIT = "index-as-held", "index-as-split"
CHECKED_OUT, TAKEN, STORED = "index-checked-out", "index-taken", "index-stored"

#: How a finding says which files git reads again.
READ_AGAIN = ("each one git reads again (every file of a small source; of a "
              "large one, those checked out in the second git wrote its "
              "index)")

#: Where `execute` stops for each of git's refusals, measured with the
#: refusal's own fixtures and the check that refuses them patched out (#906).
#: A clone of the source meets the rule that refuses a checkout the first
#: time `execute` makes one: extracting a leg (`REFUSED extracting the spec
#: leg`, where both legs are extracted, before either is pushed). The split's
#: `git add -A` stops it at `REFUSED committing the split`, a step the push
#: of the split branch follows, unless a step before it meets the same rule:
#: the extraction, on a filter that fails; the seeding of a leg, which runs
#: a `git add -A` of its own (`REFUSED seeding the code leg`); or the mount,
#: where a rule over every file reaches the `.gitmodules` it writes
#: (`REFUSED mounting the legs`, `failed to encode '.gitmodules'`).
STOPS_AT_A_CLONE = "at its first clone of the source"
STOPS_AT_THE_SPLIT = (
    "no later than committing the split, and sooner where a step before it "
    "meets the same rule: extracting or seeding a leg, or mounting the legs, "
    "where the rule reaches the `.gitmodules` it writes")

#: What git refused, where `execute` would stop, and the way out, for each
#: step a refusal can stop.
CHECKOUT_REFUSED = (
    "to check the source's commit out as the split's clone does",
    STOPS_AT_A_CLONE,
    "Change the rule or the setting git names, and re-run `plan`.")
STORE_REFUSED = (
    "to store again what the plan keeps in the assembly root, as the split's "
    "`git add -A` does",
    STOPS_AT_THE_SPLIT,
    "Commit the file git names in the source as git stores it, or change the "
    "rule or the setting that refuses it, and re-run `plan`.")
COPY_REFUSED = (
    "to store the pinned shape copies the split writes",
    STOPS_AT_THE_SPLIT,
    "Keep the rule off the copy git names with a line after it in the "
    "source's root `.gitattributes`, or narrow the rule, commit, and re-run "
    "`plan`.")


def _nul(path: str) -> bytes:
    """`path` as git's `-z` input holds it: the bytes the tree holds."""
    return path.encode("utf-8", "surrogateescape") + b"\0"


class _SplitRehearsal:
    """A throwaway repository that borrows a source's objects, to ask this
    machine's git what the split's checkout, `git rm` and `git add` make of
    them. Made in the system's temporary directory, as `_stored_as_written`
    makes its own, and removed on leaving the `with`."""

    def __init__(self, source: Source) -> None:
        self._source = source
        self._scratch = Path(tempfile.mkdtemp(
            prefix="openreposhape-reencoded-"))
        self.work = self._scratch / "repository"
        # git-lfs's smudge is skipped: each LFS file is checked out as its
        # pointer, which git-lfs's clean stores as it is, so no LFS object is
        # read, linked or fetched, and a blob under `filter=lfs` that is not
        # a pointer is still stored otherwise and found.
        self._env = {**_inherited_env(), "GIT_LFS_SKIP_SMUDGE": "1"}

    def __enter__(self) -> "_SplitRehearsal":
        try:
            objects = git_out(["rev-parse", "--path-format=absolute",
                               "--git-path", "objects"],
                              cwd=self._source.path, binary=True,
                              env=self._env).strip()
            empty = self._scratch / "no-template"
            empty.mkdir()
            git_out(["init", "-q", f"--template={empty}", str(self.work)],
                    cwd=self._scratch, env=self._env)
            info = self.work / ".git" / "objects" / "info"
            info.mkdir(parents=True, exist_ok=True)
            (info / "alternates").write_bytes(objects + b"\n")
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        shutil.rmtree(self._scratch, ignore_errors=True)

    def git(self, args: list[str], index: str,
            data: bytes = b"") -> subprocess.CompletedProcess:
        """`git <args>` here, over the index file `index`, `data` its stdin.
        No fsmonitor daemon is started for a repository about to go."""
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args], cwd=str(self.work),
            input=data, capture_output=True, check=False,
            env={**self._env,
                 "GIT_INDEX_FILE": str(self.work / ".git" / index)})

    def asked(self, args: list[str], index: str, data: bytes = b"") -> bytes:
        """`git`'s stdout, or the `git-failed` refusal `git_out` raises."""
        proc = self.git(args, index, data)
        if proc.returncode:
            raise Refusal("git-failed", "`git {}` in {} exited {}: {}".format(
                " ".join(args), self.work, proc.returncode,
                proc.stderr.decode("utf-8", "replace").strip()))
        return proc.stdout

    def refused(self, args: list[str], index: str,
                data: bytes = b"") -> str | None:
        """None where git does what `args` ask; else git's last line."""
        proc = self.git(args, index, data)
        if not proc.returncode:
            return None
        said = proc.stderr.decode("utf-8", "replace").strip()
        return said.splitlines()[-1] if said else f"exit {proc.returncode}"

    def listed(self, args: list[str], index: str) -> list[str]:
        """The paths a `-z` listing of git's names."""
        return [_git_path(path)
                for path in self.asked(args, index).split(b"\0") if path]

    def staged(self, index: str) -> dict[str, str]:
        """`{path: oid}` for each entry `index` holds, read from the index
        alone: comparing it with a commit instead (`diff-index`) makes git
        read the `.gitmodules` the checkout wrote for each gitlink the
        commit holds, and die on one it cannot parse."""
        staged = {}
        for entry in self.asked(["ls-files", "-s", "-z"], index).split(b"\0"):
            head, _, path = entry.partition(b"\t")
            if path:
                staged[_git_path(path)] = head.split()[1].decode("ascii")
        return staged

    def hold(self, index: str, rows) -> None:
        """An index with no stat data, holding `rows`: `(path, mode, oid)`.
        Git trusts none of it, and reads each file again."""
        self.asked(["update-index", "-z", "--index-info"], index,
                   b"".join(f"{mode} {oid}\t".encode("ascii") + _nul(path)
                            for path, mode, oid in rows))

    def reached(self, index: str,
                paths: list[str]) -> dict[str, dict[str, str]]:
        """`{path: {attribute: value}}` for each of `paths` one of
        `BYTE_ATTRIBUTES` reaches, with the rules `index` holds."""
        if not paths:
            return {}
        fields = self.asked(["check-attr", "--cached", "-z", "--stdin",
                             *BYTE_ATTRIBUTES], index,
                            b"".join(map(_nul, paths))).split(b"\0")
        said: dict[str, dict[str, str]] = {}
        for at in range(0, len(fields) - 2, 3):
            value = fields[at + 2].decode("utf-8", "surrogateescape")
            if value not in NO_RULE:
                said.setdefault(_git_path(fields[at]), {})[
                    fields[at + 1].decode("ascii")] = value
        return said

    def checkout(self, index: str) -> str | None:
        """What `index` holds, written with the source's rules as the split's
        clone writes it: None, or git's refusal."""
        return self.refused(["checkout-index", "-a", "-f", "-q"], index)

    def place(self, rel: str, data: bytes) -> None:
        """`data` at `rel` in the work tree, as the split writes a file: in
        place of a symlink the checkout wrote there, never through it, as
        one the source keeps may lead out of this repository."""
        target = self.work.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_bytes(data)


def _rules_reaching(asked: _SplitRehearsal, source: Source, tree: list,
                    kept: set[str], written: dict,
                    copies: list[str]) -> tuple[set[str], dict]:
    """The source files a rule reaches, as the source holds its rules or as
    the split's root will, and `{copy: {attribute: value}}` for each pinned
    copy where it lands, under the split's root."""
    asked.asked(["read-tree", source.commit], AS_HELD)
    files = [path for path, mode, _, _ in tree if mode in FILE_MODES]
    reached = set(asked.reached(AS_HELD, files))
    asked.asked(["read-tree", source.commit], AS_SPLIT)
    asked.asked(["update-index", "-z", "--force-remove", "--stdin"], AS_SPLIT,
                b"".join(_nul(path) for path, _, _, _ in tree
                         if path not in kept))
    for rel, data in written.items():
        if rel in kept:
            continue    # the root's own is there, and the shape's is not
        oid = asked.asked(["hash-object", "-w", "--no-filters", "--stdin"],
                          AS_SPLIT, data).decode("ascii").strip()
        asked.asked(["update-index", "--add", "--replace", "--cacheinfo",
                     f"{FILE_MODES[0]},{oid},{rel}"], AS_SPLIT)
    at_the_root = asked.reached(
        AS_SPLIT, [path for path in files if path in kept] + copies)
    return reached | (kept & set(at_the_root)), at_the_root


def _as_the_split_writes(asked: _SplitRehearsal, rules: list, kept: set[str],
                         own: str | None, written: dict,
                         landings: list[tuple[str, str]]) -> None:
    """The root's rules as the split's `git add` reads them: the moved
    `.gitattributes` gone; the root's own followed by #471's block, or the
    shape's own where the root keeps none; and the shape's beside it, where
    the root keeps nothing there (`plan-root-blocks-shape-copy` names what
    it keeps, #262). The block names each pinned copy of `landings`
    (`_pinned_landings`') where it lands, the path git tracks, and by its own
    name where that differs (#807)."""
    for path, _, _ in rules:
        if path not in kept:
            asked.work.joinpath(*path.split("/")).unlink(missing_ok=True)
    beside = f"{COLLISION_DIR}/{ATTRIBUTES}"
    if beside not in written:
        asked.place(ATTRIBUTES, written[ATTRIBUTES])
        return
    if own is not None:
        asked.place(ATTRIBUTES, with_eol_block(
            (asked.work / ATTRIBUTES).read_bytes(),
            eol_block_paths([name for name, _ in landings], COLLISION_DIR,
                            dict(landings))))
    if beside not in kept:
        asked.place(beside, written[beside])


def _copy_bytes(name: str, makefile: str | None) -> bytes | None:
    """The bytes the split writes for the pinned copy the pin names `name`,
    as `_materialize` writes them; None for the Makefile where the plan's
    leg paths are another finding's, and its block cannot be written."""
    rel = name.removeprefix(f"{COLLISION_DIR}/")
    for shape_path, copied in COPIED_FROM_SHAPE:
        if copied == rel:
            return (SHAPE_ROOT / shape_path).read_text(
                encoding="utf-8").encode("utf-8")
    text = (SPLIT_TEMPLATE / rel).read_text(encoding="utf-8")
    if rel == SHAPE_MAKEFILE:
        if makefile is None:
            return None
        text += makefile
    return text.encode("utf-8")


def _copies_stored(asked: _SplitRehearsal, landings: list,
                   makefile: str | None) -> tuple[str | None, list[str]]:
    """`(git's refusal, [each pinned copy git stores as other bytes])`, its
    own bytes written where it lands and added as the split adds it."""
    placed = []
    for name, landed in landings:
        data = _copy_bytes(name, makefile)
        if data is None:
            continue
        try:
            asked.place(landed, data)
        except OSError:
            continue    # what is in its way is another finding's (#262)
        placed.append((landed, data))
    if not placed:
        return None, []
    said = asked.refused(["--literal-pathspecs", "add", "-f",
                          "--pathspec-from-file=-", "--pathspec-file-nul"],
                         STORED, b"".join(_nul(path) for path, _ in placed))
    if said is not None:
        return said, []
    staged = asked.staged(STORED)
    return None, [landed for landed, data in placed
                  if staged.get(landed) != asked.asked(
                      ["hash-object", "--no-filters", "--stdin"], STORED,
                      data).decode("ascii").strip()]


def _named_and_counted(paths: list[str]) -> str:
    """Up to `NAMED_PATHS` of `paths`, each `_spelled`, and how many more."""
    named = [_spelled(path) for path in paths[:NAMED_PATHS]]
    if len(paths) > NAMED_PATHS:
        named.append(f"{len(paths) - NAMED_PATHS} more")
    return _and_listed(named)


def _stored_otherwise(paths: list[str]) -> tuple[str, str, str]:
    """`(how many, what this machine's git would do to them, the way out)`
    for files the plan keeps or moves."""
    one = len(paths) == 1
    them, blob, each = (("it", "its blob", "it") if one else
                        ("them", "their blobs", "each"))
    return (
        "1 file" if one else f"{len(paths)} files",
        f"this machine's `git add` would store {them} as other bytes than "
        f"{blob} once the split's checkout has written {them}: "
        f"{_named_and_counted(paths)}",
        f"Commit {each} in the source as git stores it (`git add "
        "--renormalize -- <path>`, then commit), or change the rule that "
        f"reaches {them}, and re-run `plan`.")


def _kept_finding(paths: list[str]) -> str:
    count, stored, way_out = _stored_otherwise(paths)
    each = "it" if len(paths) == 1 else "each"
    return (f"FINDING {REENCODED_FILES}: the plan keeps {count} in the "
            f"assembly root, and {stored}. The split's `git add -A` stores "
            f"again {READ_AGAIN}, and the verification then reports {each} "
            "as `adopt-lost`, in no leg and not in the root tree, after both "
            f"legs exist. {way_out}")


def _moved_finding(paths: list[str]) -> str:
    count, stored, way_out = _stored_otherwise(paths)
    them = "it" if len(paths) == 1 else "them"
    return (f"FINDING {REENCODED_FILES}: the plan sends {count} to a leg or "
            f"drops {them}, and {stored}. The mount's `git rm` refuses "
            f"{READ_AGAIN}, as holding local modifications, so the split "
            f"stops at mounting the legs, after both legs exist. {way_out}")


def _copy_unset_line(landed: str, rules: dict) -> str:
    """The line that keeps the source's rules off the copy at `landed`."""
    unset = [name for name in COPY_RULES if name in rules]
    if not unset:
        return f"a line that keeps the rule off {_spelled(landed)}"
    if EOL_PATH_RE.fullmatch(landed):
        return f"`/{landed} {' '.join(f'-{name}' for name in unset)}`"
    return (f"a line that names {_spelled(landed)} and unsets "
            f"{_and_listed([f'`{name}`' for name in unset])}")


def _copies_finding(copies: list[str], at_the_root: dict) -> str:
    one = len(copies) == 1
    them = "it" if one else "them"
    lines = [_copy_unset_line(landed, at_the_root.get(landed, {}))
             for landed in copies[:NAMED_PATHS]]
    if len(copies) > NAMED_PATHS:
        lines.append(f"one for each of the {len(copies) - NAMED_PATHS} more")
    return (f"FINDING {REENCODED_FILES}: the source's rules make this "
            f"machine's `git add` store {len(copies)} pinned shape "
            f"{'copy' if one else 'copies'} as other bytes than the split "
            f"writes: {_named_and_counted(copies)}. The split would commit "
            f"{them} as {'a copy' if one else 'copies'} the shape's pin does "
            "not describe, and `execute` would say `adoption verified` over "
            f"{them}. Keep the rules off {them} with "
            f"{'the line' if one else 'these lines'} after them in the "
            f"source's root `{ATTRIBUTES}`: {_and_listed(lines)}, or narrow "
            "the rules, commit, and re-run `plan`.")


def _refused_finding(step: tuple[str, str, str], said: str) -> str:
    """`check`'s line for a step of the split that git refuses: what it
    refuses, in git's words, and where `execute` stops over it (`step`'s
    `STOPS_AT_*`), which is never past the step git refuses and is not always
    that step (#906: it said "there", and stopped on the mount's
    `.gitmodules`, before the split's `git add`, for `* working-tree-encoding`
    with `.gitattributes` exempted)."""
    what, stops, way_out = step
    return (f"FINDING {REENCODED_FILES}: this machine's git refuses {what} "
            f"(git said {_spelled(said)}), so `execute` would stop after the "
            f"leg repositories exist, {stops}. {way_out}")


def _reencoded_files_findings(plan: Plan, source: Source, tree: list,
                              probe: _SymlinkProbe | None = None
                              ) -> list[str]:
    """A FINDING for each group of files the plan keeps or moves, and of
    pinned copies, that this machine's git would store as other bytes than
    the split expects, then one for each of git's refusals (#654). The
    source's own root `.gitattributes`, kept as a file, is #530's D5(a)
    question, and is not asked again; one kept as a symlink, which the split
    never writes through, is `plan-root-symlink`'s or #471's follow-up's.
    `probe` is `_entry_findings`' one probe, shared with
    `_root_symlink_findings`."""
    kept_rows = _kept_in_root(plan.entries, tree)
    kept = {path for path, _, _ in kept_rows}
    disk = _KeptTree(kept_rows, False)
    top = disk.at(ATTRIBUTES)
    own = top[0] if top is not None and top[1] in FILE_MODES else None
    at_the_top = top[0] if top is not None else None
    order = {path: at for at, (path, _, _, _) in enumerate(tree)}
    files = [(path, mode, oid) for path, mode, oid, _ in tree
             if mode in FILE_MODES and path != own]
    rules = [(path, mode, oid) for path, mode, oid, _ in tree
             if mode in (*FILE_MODES, SYMLINK_MODE)
             and path.rsplit("/", 1)[-1].casefold() == ATTRIBUTES]
    if probe is None:
        probe = _SymlinkProbe(source.work_root)
    walks = _PlannedRoot(plan, source, tree, probe=probe).walks()
    landings = _pinned_landings(walks)
    names = [name for name, _ in landings]
    written = _root_attributes(source, walks, disk, tree, names)
    spec, code = _plan_leg_paths(plan)
    makefile = (None if leg_path_problems(spec, code)
                else adopt_makefile_block(spec[1], code[1]))
    with _SplitRehearsal(source) as asked:
        reached, at_the_root = _rules_reaching(
            asked, source, tree, kept, written,
            [landed for _, landed in landings])
        wanted = [row for row in files if row[0] in reached]
        asked.hold(CHECKED_OUT, {*wanted, *rules})
        said = asked.checkout(CHECKED_OUT)
        if said is not None:
            return [_refused_finding(CHECKOUT_REFUSED, said)]
        # The mount's side: `git rm`'s own compare, which writes nothing.
        moved = {row[0] for row in wanted if row[0] not in kept}
        asked.hold(TAKEN, {*[row for row in wanted if row[0] in moved],
                           *rules})
        asked.git(["update-index", "-q", "--refresh"], TAKEN)
        taken = [path for path in asked.listed(
            ["diff-files", "--name-only", "-z"], TAKEN) if path in moved]
        # The split's side: its `git add`, over the root it writes.
        try:
            _as_the_split_writes(asked, rules, kept, own, written, landings)
        except OSError:
            return [_moved_finding(taken)] if taken else []
        held = {*[row for row in wanted if row[0] in kept],
                *[row for row in rules
                  if row[0] in kept and row[0] != at_the_top]}
        asked.hold(STORED, held)
        stored_said = asked.refused(["add", "-u"], STORED)
        blobs = {path: oid for path, _, oid in held}
        stored = [] if stored_said is not None else [
            path for path, oid in asked.staged(STORED).items()
            if blobs.get(path, oid) != oid]
        copies_said, copies = _copies_stored(asked, landings, makefile)
    return _grouped_findings(
        sorted(stored, key=order.get), sorted(taken, key=order.get),
        copies, at_the_root,
        ((STORE_REFUSED, stored_said), (COPY_REFUSED, copies_said)))


def _grouped_findings(stored: list[str], taken: list[str], copies: list[str],
                      at_the_root: dict, refusals) -> list[str]:
    """`_reencoded_files_findings`' lines, in `check`'s order: what the
    root keeps, what goes to a leg or is dropped, the pinned copies, then
    each of git's refusals `(step, what git said, or None)`."""
    found = []
    if stored:
        found.append(_kept_finding(stored))
    if taken:
        found.append(_moved_finding(taken))
    if copies:
        found.append(_copies_finding(copies, at_the_root))
    for step, said in refusals:
        if said is not None:
            found.append(_refused_finding(step, said))
    return found


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
    # `execute` refuses it, where it ended in a PermissionError traceback,
    # and before the NOTE that says a recorded clone is made again (#650).
    # So is a source that cannot be opened at all, which `execute`, asking
    # first, never reaches: `source-unresolvable` here was a second answer.
    unwritable = _unwritable_work_dir(args, work_root)
    try:
        source = plan.open_source(args.source, work_root, unwritable,
                                  getattr(args, "clones", None))
    except (OSError, Refusal):
        if not unwritable:
            raise
        raise _work_dir_refusal(unwritable) from None
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
    # The directory `execute --local-remote-dir` will be given: each relative
    # submodule url is resolved from the bare repositories that run would
    # create there, as it resolves them, and from GitHub's without one, and
    # the topics line below is that run's (#417). Read as `work_dir` is, so
    # a Namespace made without it has none.
    local_remote_dir = getattr(args, "local_remote_dir", None)
    entry_findings, remediation, notes = _entry_findings(plan, source,
                                                         local_remote_dir)
    findings.extend(entry_findings)
    remediation = taken_remediation + remediation

    names = plan.names()
    pins = set(plan.pins)
    # The plan names the source, or `execute` acts on another repository
    # (#499): said before the names' own findings, as `execute` refuses it.
    another = _not_the_source(plan, source, names)
    if another:
        findings.append(f"FINDING {PLAN_NOT_THE_SOURCE}: {another}")
        remediation.append(_own_name_remediation(
            _held_repository(plan, source), naming, pins, ""))
    # THE SOURCE IS HANDED TO `_check_names` WHERE `execute` HANDS IT (#716):
    # when the plan does not name another repository, so that a refusal of
    # the assembly root's own name says to rename it first, as `execute`
    # says it on the same plan. Where the plan does name another,
    # `execute` stops at `plan-not-the-source` and never asks the names, and
    # a refusal of the plan's name is then about a name that is not the
    # source's: `_own_name_remediation` has said what to do.
    in_place = source.repository if not another else None
    try:
        _check_names(naming, names, pins, None if another else source)
        for role, name in names.items():
            found = naming.classify(name, role, pins)
            print(f"  {role:<9} {name:<28} {found.family}"
                  + (f"/{found.role}" if found.role else ""))
    except Refusal as exc:
        findings.append(f"FINDING {exc.code}: {exc.detail}")
        # Only the rename-first remedy is printed, once after the findings:
        # it is the one `check` was missing. `--project takes ...` is not,
        # and `check` never printed it (#716). It says the rule its new name
        # follows first, as `_check_names` says it (#902).
        if in_place is not None and exc.remediation == _name_remedy(
                exc.code, in_place):
            remediation.append(exc.remediation)
    else:
        # WHAT THE DISK OR GITHUB WILL NOT HOLD (#863): the names, the
        # organisation and the topic, `execute`'s one list, which it refuses
        # the first of before either leg exists, each a finding here under
        # its code. Only `execute` asked them, so `check` said `plan ok` over
        # a plan `execute` then refused.
        held, held_fixes, held_codes = _held_findings(
            plan, names, local_remote_dir, naming)
        findings.extend(held)
        remediation.extend(held_fixes)
        # LAST, as `execute` asks it last, right before it makes either leg
        # (#798), and only of names `execute` would get that far with: what
        # stands in the way of the two leg repositories, of the disk under
        # `--local-remote-dir` and otherwise of GitHub, with `gh repo view
        # --json nameWithOwner`. NOT ASKED AFTER A FINDING ABOVE WHOSE FIX
        # RENAMES THE LEGS (`RENAMES_THE_LEGS`): a name too long is mended
        # with a shorter --project, and an `org:` too long or misspelled
        # with another `org:`, so `<org>/<Project>-spec` and `-code` change,
        # and the question asked now would be asked of two repositories the
        # mended plan does not name. A topic finding is mended with another
        # `id:`, which names no repository: the legs keep their names, the
        # question is still the right one, and asked beside it, one round
        # shows both (#871's review, S1), as it is asked beside the
        # manifest's and the split branch's findings, which `execute`
        # refuses first too.
        # A question gh cannot answer is a NOTE here, not a finding.
        legs, fixes, unasked = (
            ([], [], []) if RENAMES_THE_LEGS.intersection(held_codes)
            else _leg_remote_findings(plan, names, local_remote_dir))
        findings.extend(legs)
        remediation.extend(fixes)
        notes = [*notes, *unasked]

    _print_what_will_happen(plan, source, names,
                            naming.topic_for(plan.project_id),
                            local_remote_dir is not None)

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
    it there: `Source.clone` clones an `org/repo` into
    `<work_root>/source-readonly/<repo>`, and a re-run given the same
    --work-dir is refused there, as `adopt-work-dir-occupied` (#188's
    re-verification, R3; #652). A local path is read in place and is no
    part of the work directory.

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

    `execute` refuses a re-run while they exist, before it makes either
    (#798): `leg-remote-exists`, under `--local-remote-dir` and against
    GitHub alike. Every failure after it
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
              f"that meets {them} is refused as `leg-remote-exists` before "
              "it makes either leg, under --local-remote-dir and against "
              "GitHub alike.")
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
#: What `execute` says it left as it was when it refuses a `--work-dir`.
NO_LEG_YET = "no leg repository was created and nothing was pushed. "


def _work_dir_refusal(detail: str, done: str = "") -> Refusal:
    """`adopt-work-dir-unwritable` for `detail`, why the `--work-dir`
    cannot be used: `_work_root`'s or `_unwritable_work_dir`'s. The one
    refusal of a work directory, in all three commands (#650); `done` is
    what the refusing command left as it was, said first."""
    return Refusal(WORK_DIR_UNWRITABLE, detail,
                   f"Remediation: {done}{WORK_DIR_FIX}")


def _unwritable_work_dir(args, work_root: Path,
                         needed: str | None = None) -> str | None:
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
    user owns and can write in, and nothing is asked.

    `needed` is what the asking command does in the directory, and the
    reason ends with it (#903): `execute`'s, which is what `check` and
    `execute` give, where none is passed; `plan`'s own need of it is the
    clone (`_plan_clones`)."""
    if not getattr(args, "work_dir", None):
        return None
    try:
        os.rmdir(tempfile.mkdtemp(prefix="write-probe-", dir=work_root))
    except OSError as exc:
        needed = needed or (
            f"`execute` builds {_and_listed(list(BUILT_IN.values()))} "
            "there, only after it has made both leg repositories")
        return (f"--work-dir {_spelled(str(work_root))} cannot be written: "
                "making a directory in it, and removing it again, failed "
                f"({exc.strerror or exc}), and {needed}")
    return None


def _plan_clones(repository: str) -> str:
    """What `plan` does in a `--work-dir` (#903), as `_unwritable_work_dir`
    ends its reason with it: it clones an `org/repo` `--source` into
    `source-readonly/<repo>`, which is why the directory must be one this
    user can write in. A local source is read in place, so `plan` does not
    ask whether the directory can be written in; it still makes it, and
    refuses one another user can rename in (#803), for `--out` may be
    written there too."""
    return (f"`plan` clones {repository} into "
            f"`{SOURCE_READONLY}/{repository.split('/')[1]}` there")


def _refuse_an_unwritable_work_dir(args, work_root: Path) -> None:
    """Refuse `_unwritable_work_dir`'s `--work-dir`, before any leg
    repository exists (#524)."""
    unwritable = _unwritable_work_dir(args, work_root)
    if unwritable:
        raise _work_dir_refusal(unwritable, NO_LEG_YET)


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


def _tip_at(url: str, branch: str) -> str | None:
    """The commit the repository at `url` has `branch` at, as `git ls-remote`
    reads it now, or None where it has no such branch."""
    ref = f"refs/heads/{branch}"
    listed = run(["git", "ls-remote", url, ref])
    tips = [line.split("\t")[0] for line in listed.splitlines()
            if line.split("\t")[-1] == ref]
    return tips[0] if tips else None


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
    asked of the very remote the split is pushed to, with `git ls-remote`
    (`_tip_at`), so the answer is the push's own; under `--local-remote-dir`
    that remote is the source, whose own refs are read (`_branches_at`), so
    that one it hides from `git ls-remote` with `hideRefs`, which `check`
    finds, is refused too (#520): the push into it meets that branch.

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
    if local and _a_leg_may_be_on_disk(urls):
        return
    # Under `--local-remote-dir` the push goes into the source, and meets its
    # own refs, a branch it hides from `git ls-remote` too (#520).
    tip = (_branches_at(urls["assembly"], source.path).get(branch) if local
           else _tip_at(urls["assembly"], branch))
    if tip is None or _in_the_history_of(source, tip):
        return
    raise Refusal(
        "adopt-branch-exists",
        f"{_spelled(urls['assembly'])} already has {_spelled(branch)}, the "
        "branch this adoption pushes its split commit to, at "
        f"{tip[:12]}: neither the source commit {source.commit[:12]} nor "
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


# ---------------------------------------------------------------------------
# Both leg repositories, asked about before either is made (#798)
# ---------------------------------------------------------------------------
#
# `_create_leg_remotes` made the spec leg's repository and asked about the
# code leg's only as it made that one: `leg-remote-exists` under
# `--local-remote-dir`, and `gh repo create` finding the name taken against
# GitHub. So a code leg that already existed was refused once the spec leg
# had been made, which #188 N4's notice named and nothing prevented; on
# GitHub that left a stray private `<P>-spec`, whose removal needs the
# `delete_repo` scope. And a `--local-remote-dir` that could not hold them
# ended in a traceback (a file at the path, `FileExistsError`; a folder above
# it this user cannot write in, `PermissionError`) or in `git init`'s raw
# failure (a folder this user cannot write in), each after `check` had said
# `plan ok`.
#
# BOTH ARE ASKED ABOUT FIRST, and everything that stands in their way is
# refused at once (`_refuse_what_stands_in_the_legs_way`):
#
# - under `--local-remote-dir`, whether each bare repository's path is taken
#   (`os.path.lexists`, so a dangling link is taken too), the spec leg's and
#   then the code leg's, and then whether the directory can be made and
#   written in, asked as the scaffold and `family.py` ask theirs
#   (`folder_in_the_way`, #609), which makes nothing;
# - against GitHub, `gh repo view <name> --json nameWithOwner` of the spec
#   leg's name and then the code leg's. A NAME IS TAKEN ONLY WHEN GITHUB
#   ANSWERS WITH IT: gh's GraphQL follows a rename or a transfer, so the
#   answer counts only when its `nameWithOwner` is the name asked, compared
#   without case as GitHub compares names; an answer naming another
#   repository is a redirect, which `gh repo create` takes over, and the
#   name is free. A name that exists is `leg-remote-exists` before any `gh
#   repo create`. Gh's not-found answer means absent, as #609 has it for the
#   scaffold; a view that fails otherwise, or answers with no
#   `nameWithOwner` to read, is `adopt-remote-unreadable`, naming the
#   command and what it said.
#
# WHERE: right before `_create_leg_remotes`, after the yes, where
# `leg-remote-exists` was always refused. Every refusal before it keeps its
# order, and its precedence over this one: `adopt-branch-exists` and
# `plan-split-branch-taken` already defer to a leg still on disk. And GitHub
# is asked as close to `gh repo create` as it can be.
#
# `check` ASKS THE SAME, under the same flags and in the same order (#417's
# one verdict): given `--local-remote-dir`, of the disk, and without it, of
# GitHub; its findings come last, as `execute` asks them last. One
# difference: where gh cannot answer -- no login, a bad token, a rate limit,
# no network -- `check` says what it could not ask in a NOTE and still
# passes, so that it stays usable offline, where `execute` refuses.
#
# WHAT CAN STILL FAIL AFTER THE FIRST MAKE keeps #188 N4's notice
# (`_create_leg_remotes`): GitHub answers a repository the token cannot see
# as not found, and `gh repo create` then finds the name taken; a rate limit
# or an outage between the two creates; and under `--local-remote-dir` a
# path made since the question, or a disk that fills, at the code leg's
# `git init`.

#: `check`'s finding, and `execute`'s refusal, of a leg repository that
#: already exists (#174, #798).
LEG_REMOTE_EXISTS = "leg-remote-exists"
#: ... of a `--local-remote-dir` that cannot hold them, under the name the
#: scaffold and `family.py` give theirs (#609).
LEG_FOLDER_REFUSED = "adopt-folder-cannot-be-made"
#: What each says to do: `check` after `Remediation:`, and `execute` after
#: `NO_LEG_YET`.
ON_DISK_FIX = (
    "Choose an empty --local-remote-dir, and a --work-dir the run that made "
    "it did not clone into (a fresh one, or none): `git clone` refuses a "
    "directory it already cloned into. There is no --force: re-running over "
    "a live leg is not an adoption.")
ON_GITHUB_FIX = (
    "A leg repository is created new, never over one that exists, and there "
    "is no --force: re-running over a live leg is not an adoption. If an "
    "earlier `execute` made it and its adoption is not one to keep, delete "
    "it (`gh repo delete <repository>`, which needs the `delete_repo` "
    "scope); another repository of that name is renamed on GitHub first. "
    "Then run `check` and `execute` again.")
UNREAD_FIX = (
    "Only gh's own answer that a repository does not exist (exit 1, "
    f"`{GH_NOT_FOUND_WORDS}`), or one naming another repository that the "
    "name redirects to, lets `execute` create one; any other answer says "
    "nothing about whether it is there. Check `gh auth status` (`gh "
    "auth login` where it names a token that is missing, bad or expired), "
    "or let a rate limit or an outage pass, then run `execute` again.")
FOLDER_FIX = (
    "Move what stands in the way aside, or pass a --local-remote-dir where "
    "a folder can be made. There is no --force.")
UNWRITABLE_FOLDER_FIX = (
    "Give this user write and search permission on that folder, or pass "
    "another --local-remote-dir.")


def _leg_remote_answers(repositories: dict, names: dict,
                        local_remote_dir: Path | None) -> list[tuple]:
    """`(code, detail, fix, note)` for each thing that stands in the way of
    making the two leg repositories, in the order they are asked (#798):
    nothing when both can be made. It makes nothing.

    Under `local_remote_dir` the disk is asked (`_in_the_way_on_disk`), and
    otherwise GitHub, of `repositories` (`_in_the_way_on_github`). `note` is
    what `check` prints instead of a finding, for a question gh could not
    answer, and "" for every finding."""
    if local_remote_dir is not None:
        return _in_the_way_on_disk(names, local_remote_dir)
    asked = [_in_the_way_on_github(role, repositories[role])
             for role in EXTRACTED_LEGS]
    return [answer for answer in asked if answer]


def _the_remote_dir(local_remote_dir: Path) -> Path:
    """`--local-remote-dir` as each leg's url is made of it (`_remote_urls`)
    and asked about: resolved, and made absolute as given where it cannot be
    resolved. `Path.resolve` raised `RuntimeError` out of `execute` for a
    link loop, a traceback before anything was asked (#798);
    `folder_in_the_way` names it now, in `check` and `execute` alike."""
    try:
        return local_remote_dir.resolve()
    except (OSError, RuntimeError):
        return local_remote_dir.absolute()


def _in_the_way_on_disk(names: dict, local_remote_dir: Path) -> list[tuple]:
    """The disk's answers under `--local-remote-dir`: each leg's bare
    repository path that something already takes, the spec leg's and then
    the code leg's, and then the directory, where it cannot be made and
    written in. Every path `_spelled`, as the notice spells it (#212)."""
    remote_dir = _the_remote_dir(local_remote_dir)
    found = []
    for role in EXTRACTED_LEGS:
        bare = remote_dir / f"{names[role]}.git"
        if os.path.lexists(bare):
            found.append((LEG_REMOTE_EXISTS,
                          f"{_spelled(str(bare))}, the {role} leg's bare "
                          "repository, already exists", ON_DISK_FIX, ""))
    in_the_way = folder_in_the_way(remote_dir)
    if in_the_way:
        here, why = in_the_way
        found.append((
            LEG_FOLDER_REFUSED,
            f"--local-remote-dir {_spelled(str(remote_dir))} cannot hold the "
            f"two leg repositories: {_spelled(str(here))} {why}",
            UNWRITABLE_FOLDER_FIX if why == CANNOT_WRITE_IN else FOLDER_FIX,
            ""))
    return found


def _first_said(output: str) -> str:
    """`: <the first line gh said>`, each character a terminal would act on
    spelled as `_spelled` spells it; "" when it said nothing."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    return ": " + "".join(char if char.isprintable()
                          else _spelled_character(char) for char in lines[0])


def _name_with_owner(answer: str) -> str | None:
    """The `nameWithOwner` a `gh repo view --json nameWithOwner` answer
    names, or None for anything else: not JSON, not an object, no such
    field, or one that is not a name."""
    try:
        value = json.loads(answer)
    except ValueError:
        return None
    value = value.get("nameWithOwner") if isinstance(value, dict) else None
    return value if isinstance(value, str) and value else None


def _in_the_way_on_github(role: str, repository: str) -> tuple | None:
    """GitHub's answer for one leg's `repository`, by `gh repo view --json
    nameWithOwner`: `leg-remote-exists` when GitHub answers with that very
    name, compared without case as GitHub compares names; None when gh
    says it does not exist (#609), or answers with another repository's
    name, which is a redirect left by a rename or a transfer, a name `gh
    repo create` takes over; and `adopt-remote-unreadable` when gh failed
    otherwise, could not be run or answered with no `nameWithOwner` to
    read, which says nothing either way."""
    command = ["gh", "repo", "view", repository, "--json", "nameWithOwner"]
    shown = " ".join(command)
    try:
        answer = run(command)
    except CommandFailed as exc:
        if exc.code == 1 and GH_NOT_FOUND_WORDS in exc.output:
            return None
        how = f"`{shown}` exited {exc.code}{_first_said(exc.output)}"
    except OSError as exc:
        how = f"`gh` could not be run: {exc}"
    else:
        found = _name_with_owner(answer)
        if found is None:
            how = (f"`{shown}` exited 0, and what it printed holds no "
                   f"`nameWithOwner`{_first_said(answer)}" if answer.strip()
                   else f"`{shown}` exited 0 and printed nothing")
        elif found.lower() == repository.lower():
            return (LEG_REMOTE_EXISTS,
                    f"{repository}, the {role} leg's repository, already "
                    f"exists on GitHub: `{shown}` finds it", ON_GITHUB_FIX,
                    "")
        else:
            # GitHub followed a rename or a transfer away from this name:
            # the name itself is free, and `gh repo create` takes it over.
            return None
    named = f"{repository}, the {role} leg's repository,"
    return (REMOTE_UNREADABLE,
            f"whether {named} already exists on GitHub cannot be told: {how}",
            UNREAD_FIX,
            f"NOTE `check` could not ask GitHub whether {named} already "
            f"exists: {how}. It is no finding here, so that `check` stays "
            "usable offline; `execute` asks again before it makes either "
            f"leg, and refuses as `{REMOTE_UNREADABLE}` while gh cannot "
            "answer.")


def _refuse_what_stands_in_the_legs_way(repositories: dict, names: dict,
                                        local_remote_dir: Path | None
                                        ) -> None:
    """Refuse every answer `_leg_remote_answers` gives at once, BEFORE
    either leg repository is made (#798): the code is the first one's own,
    the detail lists each as `check` prints it, and the remediation says
    what each asks for, once."""
    answers = _leg_remote_answers(repositories, names, local_remote_dir)
    if not answers:
        return
    raise Refusal(
        answers[0][0],
        "\n".join([f"{len(answers)} finding(s) about the two leg "
                   "repositories, asked before either is made:",
                   *(f"  FINDING {code}: {detail}"
                     for code, detail, _fix, _note in answers)]),
        f"Remediation: {NO_LEG_YET}" + " ".join(
            dict.fromkeys(fix for _code, _detail, fix, _note in answers)))


def _leg_remote_findings(plan: Plan, names: dict,
                         local_remote_dir: Path | None
                         ) -> tuple[list[str], list[str], list[str]]:
    """`check`'s `(findings, remediation, notes)` about the two leg
    repositories: `execute`'s answers (#798), each finding as its refusal
    lists it, and a NOTE for each question gh could not answer. GitHub is
    asked only of an `org:` `execute` would put on a `gh` command line;
    another is `execute`'s to refuse first, as `unsafe-value`."""
    repositories = {}
    if local_remote_dir is None:
        try:
            org = checked_value("org", _plan_org(plan))
        except Refusal:
            return [], [], []
        repositories = {role: f"{org}/{names[role]}"
                        for role in EXTRACTED_LEGS}
    findings, fixes, notes = [], [], []
    for code, detail, fix, note in _leg_remote_answers(
            repositories, names, local_remote_dir):
        if note:
            notes.append(note)
        else:
            findings.append(f"FINDING {code}: {detail}")
            fixes.append(f"Remediation: {fix}")
    return findings, list(dict.fromkeys(fixes)), notes


#: The codes of `_what_cannot_be_held` whose fix changes the names the two
#: leg repositories are asked under, `<org>/<Project>-spec` and
#: `<org>/<Project>-code` (#871's review, S1): `adopt-name-too-long` is
#: mended with a shorter --project, `adopt-bad-project-name` with another
#: (#1014), `adopt-org-too-long` and `adopt-bad-org` with another `org:`.
#: `check` asks #861's leg question only where none of them is found.
#: `adopt-topic-too-long` is not one: it is mended with another `id:`, and an
#: id names no repository.
RENAMES_THE_LEGS = frozenset({"adopt-name-too-long", BAD_PROJECT_NAME,
                              "adopt-org-too-long", "adopt-bad-org"})


def _held_findings(plan: Plan, names: dict, local_remote_dir: Path | None,
                   naming: NamingPolicy
                   ) -> tuple[list[str], list[str], list[str]]:
    """`check`'s `(findings, remediation, codes)` for what the disk or
    GitHub will not hold of the three names, the organisation and the topic:
    every refusal of `_what_cannot_be_held`, the list `execute` refuses the
    first of (#863), each as a FINDING under its code, and the codes, which
    say whether the leg question is still asked (`RENAMES_THE_LEGS`). Asked
    only of an `org:` `execute` would get that far with: another is
    `unsafe-value`, refused first in `_checked_plan_values` (#901)."""
    try:
        org = checked_value("org", _plan_org(plan))
    except Refusal:
        return [], [], []
    refused = list(_what_cannot_be_held(plan, names, org,
                                        local_remote_dir is not None, naming))
    return ([f"FINDING {exc.code}: {exc.detail}" for exc in refused],
            list(dict.fromkeys(exc.remediation for exc in refused)),
            [exc.code for exc in refused])


def _make_the_remote_dir(remote_dir: Path) -> None:
    """`--local-remote-dir`'s `mkdir`, after the question said it can be
    made (`folder_in_the_way`): what fails here anyway -- a file put there
    since, a permission `os.access` did not foresee -- is refused by name,
    before any leg exists, and is no `OSError` traceback (#798)."""
    try:
        remote_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Refusal(
            LEG_FOLDER_REFUSED,
            f"--local-remote-dir {_spelled(str(remote_dir))} cannot be made: "
            f"{exc.strerror or exc}",
            f"Remediation: {NO_LEG_YET}"
            + (UNWRITABLE_FOLDER_FIX if isinstance(exc, PermissionError)
               else FOLDER_FIX)) from exc


def _create_leg_remotes(plan: Plan, names: dict, repositories: dict,
                        urls: dict, tracking: str, local: bool,
                        work_root: Path, *,
                        source: Source | None = None) -> None:
    """(a) The two NEW repositories. The assembly root is never created here.

    Both were asked about first (`_refuse_what_stands_in_the_legs_way`,
    #798), so a name or a path already taken, and a `--local-remote-dir`
    that cannot hold them, are refused before this runs. The spec leg's
    repository is created first, so a failure creating the code leg's
    that the question could not foresee -- a name GitHub hides from this
    token, a path made since -- leaves one repository behind, and the re-run
    meets it. That failure therefore gets the notice too, naming the one
    that exists (#188 N4), and is re-raised `reported`: `main` exits 2 on
    any of `LATE_FAILURES` without printing it twice, and anything else
    (Ctrl-C) keeps its traceback. A failure on the first leg leaves nothing,
    and `main` reports it as before. `source` is handed on for the notice:
    nothing is built in the work directory yet, but an `org/repo` source is
    already cloned there.
    """
    print("\ncreating the leg repositories")
    if local:
        _make_the_remote_dir(Path(urls["spec"]).parent)
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
        # The secrets that credential is kept in are the ROOT's, where the
        # workflow runs, so the Free-plan hint goes by the root (#602).
        _free_plan_hint_by_the_root(plan, repositories["assembly"])


def _free_plan_hint_by_the_root(plan: Plan, root: str) -> None:
    """The Free-plan secrets hint, BY THE ADOPTED ROOT (#602).

    The `validate` workflow that reads SHAPE_LEGS_APP_ID and
    SHAPE_LEGS_APP_PRIVATE_KEY runs in the assembly root, and on the Free
    plan an organisation secret is delivered only to a public repository. An
    adopted root keeps the visibility it had, which is not the plan's
    `visibility:` (the two new legs'), so the hint went by the wrong
    repository: a public source adopted with private legs was told its
    organisation secrets "resolve to EMPTY", and a private one was told the
    legs were why. It is printed now only when GitHub says the root is
    private or internal, naming the root, as `scaffold-project.py`'s
    `_private_leg_note` has gated it since #542. Asked only once a leg is
    private or internal: a public leg needs no credential, so no secret
    decides whether the `validate` check reads it.

    A ROOT WHOSE VISIBILITY CANNOT BE READ IS NOT GUESSED. Read as private,
    a public root would be given a false hint; read as public, a private one
    would lose a true one with nothing said. `ROOT_VISIBILITY_UNREAD` says
    so instead, with the condition and the command that settles it, and
    asks nothing of the organisation's plan: the NOTE names both
    conditions, so it holds whatever the plan is. It is a NOTE and not a
    refusal, because both legs exist by now and the run goes on to push
    them.

    NOR IS A PLAN THAT CANNOT BE READ (#660). `free_plan_secret_hint`
    answered None alike for a paid plan and for one it could not read, so a
    private root on an organisation whose plan the token could not see was
    told nothing. `free_plan_secrets_note`, which the scaffold and
    `family.py` ask too, and where `ROOT_VISIBILITY_UNREAD` now lives, says
    `FREE_PLAN_UNREAD` there. Since #969 (#913), an INTERNAL root whose plan
    is unread is told `FREE_PLAN_UNREAD_INTERNAL` instead, which says the
    plan is not what the hint hangs on, and since #994 an internal root on a
    plan read as `free` is told it is internal, which the hint treats as
    private, where it was called private; every other case is in the words
    adopt printed before.
    """
    note = free_plan_secrets_note(plan.get("org", ""), root,
                                  _root_visibility(root))
    if note:
        print(note)


def _root_visibility(repository: str) -> str | None:
    """`repository`'s visibility on GitHub, one of `VISIBILITY_CHOICES`, or
    None when it cannot be read: `gh repo view` failed (a repository the
    token cannot see, a rate limit, the network) or could not be started,
    or answered anything but one of GitHub's three visibilities. Never asked
    under `--local-remote-dir`, whose root is the source on disk. The answer
    is read by `visibility_in`, the reading the scaffold's and `family.py`'s
    `repository_visibility` gives theirs (#660); `gh` is run here, by this
    module's `run`, so a `gh` that cannot be started is unread too."""
    try:
        answer = run(["gh", "repo", "view", repository, "--json",
                      "visibility"])
    except (CommandFailed, OSError):
        return None
    return visibility_in(answer)


def _create_leg_remote(plan: Plan, names: dict, repositories: dict,
                       urls: dict, tracking: str, local: bool,
                       role: str) -> None:
    """One leg's repository: `gh repo create`, or a bare one on disk.

    The description's em dash reaches gh as UTF-8 under any locale
    (`_run_exact`): as text it raised `UnicodeEncodeError` under `LC_ALL=C
    PYTHONUTF8=0`, before any leg existed, for every source (#653)."""
    if not local:
        _run_exact(["gh", "repo", "create", repositories[role],
                    f"--{plan.get('visibility', 'private')}", "--description",
                    f"{names['assembly']} — {role} leg, extracted from "
                    f"{repositories['assembly']} with history"])
        print(f"  gh    {repositories[role]}")
        return
    bare = Path(urls[role])
    # Asked before either leg was made (#798); one there now was made since.
    if bare.exists():
        raise Refusal(
            LEG_REMOTE_EXISTS, f"{bare} already exists",
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
    "`leg-remote-exists`, on the disk or on GitHub) "
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
            kind = INDEX_ENTRY_KINDS.get(int(head.split()[0], 8), A_FILE)
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


#: `git rm` of one path the split moves to a leg or drops, up to the path.
#: `--literal-pathspecs` (#196): after `--` a path is no option, but it is
#: still a pathspec, where `*` and `?` are wildcards and a leading `:` is
#: magic -- `git rm -- ':!keep.md'` removes every other path in the tree.
GIT_RM = ("git", "--literal-pathspecs", "rm", "-r", "-q", "--")


def _git_rm(assembly: Path, path: str) -> None:
    """`git rm` of `path`, an entry's path as the plan holds it, in the
    assembly: what `run` does, with `path` handed to git as the bytes the
    tree holds (`_path_argument`, #527).

    `run` takes only text (`check_program`), so this asks `check_program` of
    the command as the person reads it, and a git that refuses raises
    `CommandFailed` with that command, as `run` raises it: what `execute`
    reports after both legs exist is unchanged.
    """
    command = [*GIT_RM, path]
    check_program(command)
    proc = subprocess.run([*GIT_RM, _path_argument(path)], cwd=str(assembly),
                          capture_output=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(command, assembly, proc.returncode,
                            (proc.stderr + proc.stdout).decode("utf-8",
                                                               "replace"))


def _mount_the_legs(assembly: Path, work_root: Path, names: dict, urls: dict,
                    paths_for: dict, spec_path: str, code_path: str) -> None:
    """(c, first half) `git rm` what moved, then mount the two legs.

    The submodule is added from the LEG'S WORKING TREE and its recorded URL is
    then rewritten to the canonical remote, exactly as the scaffold does: the
    adoption never depends on a push having propagated.

    Each path is the source tree's, so `_git_rm` hands it to git as the bytes
    the tree holds (#527). The mount paths are `checked_value`s, ASCII.
    """
    removed = sorted((p.rstrip("/") for p in (paths_for["spec"]
                                              + paths_for["code"]
                                              + paths_for["drop"])),
                     key=lambda p: (p != GITMODULES, p))
    for path in removed:
        _git_rm(assembly, path)
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


def _checked_org_and_id(plan: Plan) -> str:
    """The plan's `org:` as `checked_value` hands it back, once its `id:`
    is asked too. Both commands ask the two BEFORE THE PLAN'S LEG PATHS AND
    BRANCH NAMES, and after its three repository names, which they ask
    earlier (`plan.names()`, then `_check_names`): `check` in
    `_manifest_values` and `execute` in `_checked_plan_values`.
    `checked_value` refuses an `org:` this tool will not put on a `git` or
    `gh` command line as `unsafe-value`, and `Plan.project_id` an `id:`
    that is no project id as `plan-bad-id`.

    ONE ORDER, THE MORE BASIC PROBLEM FIRST (#901). `execute` asked the two
    leg paths and the two branch names first, the organisation after them
    (`_repository_urls`) and the id last, in `_refuse_what_check_finds`,
    where the manifest is built (`_manifest_values`), so a plan edited to
    `id: "North Wind"` and `legs.spec_path: "../spec"` was `plan-bad-id` to
    `check` and `plan-bad-leg-path` to `execute`, and one edited to `org:
    "-evil"` with the same path was `unsafe-value` to one and
    `plan-bad-leg-path` to the other. The organisation and the id come
    before the leg paths and the branches because they say which project
    the plan is about: every repository the plan names is `<org>/<name>`,
    on GitHub and in the manifest, and the topic `execute` sets and the
    manifest's `id:` are made from the id, where a leg path or a branch is
    a value inside that project. And `check` holds the manifest built from
    both to the project's own validator before it lists a finding, so it
    refuses either outright, exit 2, where a leg path or a branch name is
    one finding of the many it lists: asked before the leg paths and the
    branches by both commands, this is the one order they can share.
    """
    org = checked_value("org", _plan_org(plan))
    _ = plan.project_id
    return org


def _checked_plan_values(plan: Plan) -> tuple[str, str, str, str]:
    """The plan's options, in the order `check` asks them (#901): its
    `org:` and `id:` (`_checked_org_and_id`), after the three repository
    names both commands ask earlier (`plan.names()`), then the four values
    that reach a `git` command line as arguments, which it returns:
    `(spec_path, code_path, branch, tracking)`.

    Split out of `cmd_execute` for #138, in the order the refusals came in
    there, the leg paths first; #901 asks the organisation and the id
    before them, as `check` does, so the two name one problem first.
    A branch name `checked_value` refuses is `check`'s finding too, in the
    same words (`_branch_name_refusal`, #520), and so is a branch the plan's
    reader read as a number or a boolean, which is asked first
    (`_checked_branch_value`, #902), so that `tracking_branch: -007` is
    `plan-bad-tracking-branch` in `check` and in `execute`, and not
    `unsafe-value` of the `-7` nobody typed; one inside its alphabet that
    git will not create is refused with `check`'s other findings, by
    `_refuse_what_check_finds`, and before any leg exists as well.
    """
    _checked_org_and_id(plan)
    spec_leg, code_leg = _plan_leg_paths(plan)
    # Before ANY leg exists: `check` finds a bad path and `execute` refuses it
    # on its own account, not because `check` happened to be run first (#169).
    _refuse_bad_leg_paths("plan-bad-leg-path", spec_leg, code_leg)
    spec_path = checked_value(*spec_leg)
    code_path = checked_value(*code_leg)
    # Each branch asks the number-or-boolean question before `checked_value`,
    # as `check` does (`_branch_name_refusal`, #902), in `BRANCH_KEYS`' order:
    # a `tracking_branch: -007` is `plan-bad-tracking-branch` in both, not
    # `unsafe-value` of the `-7` nobody typed.
    branch, tracking = [_checked_branch_value(plan, *key)
                        for key in BRANCH_KEYS]
    return spec_path, code_path, branch, tracking


def _checked_branch_value(plan: Plan, key: str, default: str,
                          code: str) -> str:
    """The plan's branch `key:` as `execute` hands it to git, or the refusal
    `check` finds it under (`_branch_name_refusal`, #520): a number or a
    boolean is refused under `code`, saying what was read, and any other
    value is `checked_value`'s. `default` is what `execute` reads where the
    key is absent."""
    value = plan.get(key, default)
    if _a_number_or_boolean(value):
        raise Refusal(code, _not_text(key, value), NOT_TEXT_REMEDIATION)
    return checked_value(key, value)


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


def _repository_urls(args, plan: Plan, names: dict, source: Source,
                     naming: NamingPolicy | None = None
                     ) -> tuple[bool, dict, dict]:
    """Where the three repositories are: `(local, repositories, urls)`.

    Split out of `cmd_execute` for #138. The assembly root's URL is the SOURCE
    itself under `--local-remote-dir`, because an in-place adoption pushes its
    split branch back to the repository it read. What the disk or GitHub will
    not hold of them is refused here, the first of `_what_cannot_be_held`,
    the list `check` finds each of (#863). `naming` gives the topic, and is
    loaded when not given.
    """
    org = checked_value("org", _plan_org(plan))
    repositories = {role: f"{org}/{name}" for role, name in names.items()}
    local = args.local_remote_dir is not None
    refused = next(_what_cannot_be_held(plan, names, org, local, naming), None)
    if refused is not None:
        raise refused
    return (local, repositories,
            _remote_urls(org, names, args.local_remote_dir, source))


def _what_cannot_be_held(plan: Plan, names: dict, org: str, local: bool,
                         naming: NamingPolicy | None = None):
    """Each `Refusal` of what the disk or GitHub will not hold of the three
    names, the organisation and the topic, in the order `execute` asks them,
    one at a time: the assembly root's name, of which a Windows disk must be
    able to make a folder (`adopt-bad-project-name`, #1014), the names'
    lengths, and without `--local-remote-dir` the `org:`, its length and
    then its characters, and the topic.

    ONE LIST, TWO READERS (#863). `execute` refuses the first one
    (`_repository_urls`), before either leg exists; `check` finds every one,
    under the same code (`_held_findings`). Only `execute` asked them, so a
    plan `check` called `plan ok` was refused by `execute` for a name the
    disk or GitHub will not take, an organisation or a topic: one list, as
    `_refuse_what_check_finds` makes `check` and `execute` read one list of
    the manifest's values, means the two cannot disagree again. It is a
    generator, so `execute` asks nothing after the first refusal."""
    asked = [lambda: _refuse_a_root_no_disk_holds(
                 names["assembly"], f"{plan.path}: `legs.assembly`",
                 "no repository was created."),
             lambda: _refuse_names_nothing_keeps(names, org, local)]
    if not local:
        named = f"{plan.path}: `org:`"
        asked += [
            lambda: refuse_an_owner_github_cannot_have(
                "adopt-org-too-long", org, named, ORG_REMEDIATION),
            lambda: refuse_an_owner_github_cannot_spell(
                "adopt-bad-org", org, named, ORG_SPELLING_REMEDIATION),
            lambda: _refuse_the_plans_topic(plan, naming)]
    for ask in asked:
        try:
            ask()
        except Refusal as exc:
            yield exc


def _refuse_names_nothing_keeps(names: dict, org: str, local: bool) -> None:
    """`adopt-name-too-long`: a name the disk or GitHub will not hold
    (#261, #838), asked by `_what_cannot_be_held` for `execute` and `check`
    alike (#863)."""
    # Each name is a directory's too: the work directory's for all three, and
    # under `--local-remote-dir` a bare `<name>.git` for the two new legs. A
    # name of 247 to 250 characters passed every check and died in
    # `Path.exists` with `File name too long`, a traceback, before any leg
    # existed (#261). Without it the two legs are GitHub repositories, which
    # GitHub keeps to 100 characters, under an organisation it keeps to 39:
    # either passed to the first `gh repo create` (#838).
    legs = [names["spec"], names["code"]]
    try:
        refuse_unstorable_names(
            "adopt-name-too-long", list(names.values()),
            legs if local else [], [] if local else legs)
    except Refusal as exc:
        if local or not _a_leg_named_after_a_long_root(names):
            raise
        # THE SOURCE'S OWN NAME IS NOT `--project`'S TO SHORTEN (#859's
        # review, SHOULD 1). Without `--local-remote-dir` the assembly root
        # is the source's own repository on GitHub, which GitHub lets be
        # named with up to 100 characters, and a leg named after one of 96
        # to 100 is over that limit. "Use a shorter --project" planned
        # another repository, which `git ls-remote` could not read. A root
        # of 101 or more is no name GitHub gives a repository, so it is no
        # repository's to rename, and keeps "Use a shorter --project"
        # (#859's re-review, NIT 3).
        raise Refusal(exc.code, exc.detail, _rename_first(
            f"{org}/{names['assembly']}", SOURCE_NAME_TOO_LONG)) from None


#: How `adopt-org-too-long` and `adopt-topic-too-long` are told to go on
#: (#838): the plan's own key, or `plan` again with the flag that writes it.
#: Neither is a leg: `execute` refuses both before it makes one.
ORG_REMEDIATION = (
    "Remediation: no repository was created. Fix `org:` in the plan, or "
    "re-run `plan` with --org, as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`: GitHub gives no user or "
    f"organisation a name of more than {GITHUB_OWNER_MAX} characters.")
#: How `adopt-bad-org` is told to go on (#863): `ORG_REMEDIATION`'s way out,
#: without the number, which is not what it broke.
ORG_SPELLING_REMEDIATION = (
    "Remediation: no repository was created. Fix `org:` in the plan, or "
    "re-run `plan` with --org, as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`.")
TOPIC_REMEDIATION = (
    "Remediation: no repository was created. Fix `id:` in the plan, or "
    f"re-run `plan` with an explicit --id, of at most {GITHUB_ID_MAX} "
    "characters: the id need not be the project's name lowercased, and the "
    "name, which the assembly root already has, stays as it is.")
#: What `adopt-name-too-long` says before `_rename_first`'s way out, where a
#: leg GitHub will not create is named after the source (#859's review,
#: SHOULD 1), as `adopt-bad-id` says why the source's own name will not do.
#: `GITHUB_LIMITS` says the project name's bound, 95, so this does not.
SOURCE_NAME_TOO_LONG = (
    "nothing was created. The legs are named `<Project>-spec` and "
    "`<Project>-code`, and --project is the source's own name: "
    f"{GITHUB_LIMITS}. ")


def _a_leg_named_after_a_long_root(names: dict) -> bool:
    """Whether a leg over GitHub's `GITHUB_NAME_MAX` is named after an
    assembly root GitHub can have, one of at most `GITHUB_NAME_MAX`
    characters. A leg is named `<legs.assembly>-spec` or `-code`, as `plan`
    names both: its length is then the root's, the source's own name (#859's
    review, SHOULD 1). A leg the plan was edited to name otherwise is the
    plan's own to shorten, and keeps the remediation it had; so does any leg
    where the root is over `GITHUB_NAME_MAX`, which no repository on GitHub
    is named, so renaming the source there shortens nothing (#859's
    re-review, NIT 3)."""
    return len(names["assembly"]) <= GITHUB_NAME_MAX and any(
        len(names[role]) > GITHUB_NAME_MAX
        and names[role] == f"{names['assembly']}-{role}"
        for role in ("spec", "code"))


def _refuse_the_plans_topic(plan: Plan,
                            naming: NamingPolicy | None = None) -> None:
    """`_refuse_a_topic_github_cannot_set` of the topic the plan's id gives,
    for `_what_cannot_be_held` (#863). An id that is no project id is
    `plan-bad-id`, which `Plan.project_id` refuses where it always was, and
    no topic is asked of it here."""
    try:
        project_id = plan.project_id
    except Refusal:
        return
    naming = naming or NamingPolicy.load(NAMING_POLICY)
    _refuse_a_topic_github_cannot_set(plan, naming.topic_for(project_id))


def _refuse_a_topic_github_cannot_set(plan: Plan, topic: str) -> None:
    """`adopt-topic-too-long`: an id whose `xf-project-<id>` topic GitHub
    will not set (#838), refused before `_confirm` and before either leg
    exists, with the names and the organisation (`_what_cannot_be_held`,
    #863), and found by `check` alike. `_set_the_topic` sets it on all
    three only once both legs and the split are pushed, so an id over 39
    characters, which a project name of 40 or more gives by default, ended
    the run there, exit 2, with the adoption pushed and the topic unset.
    Asked in GitHub mode alone: under
    `--local-remote-dir` no topic is set. The id is named by where it came
    from, `id:` or `DERIVED_ID`, as `_id_field` names it."""
    named = "`id:`" if plan.get("id") is not None else DERIVED_ID
    refuse_a_topic_github_cannot_set(
        "adopt-topic-too-long", topic, plan.project_id,
        f"{plan.path}: {named}", TOPIC_REMEDIATION)


def _remote_urls(org: str, names: dict, local_remote_dir: Path | None,
                 source: Source) -> dict:
    """The url of each of the three repositories, by role: what `execute`
    pushes to, and what a relative submodule url kept in a leg is resolved
    from (#190), which `check` asks with the `local_remote_dir` it is given,
    or none (#417)."""
    if local_remote_dir is None:
        return {role: f"https://github.com/{org}/{name}.git"
                for role, name in names.items()}
    # NOT created yet: nothing exists on disk until the human has said yes,
    # so a refused run leaves the directory it would have used absent rather
    # than empty. One that cannot be resolved (a link loop) is kept as given,
    # for the question about it to refuse by name (#798).
    remote_dir = _the_remote_dir(local_remote_dir)
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
    in `_checked_plan_values` and `_repository_urls`, before this runs, and
    a branch name inside its alphabet that git will not create is one of
    `check`'s findings, refused here (`plan-bad-adopt-branch`,
    `plan-bad-tracking-branch`, #520). An
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
    `local_remote_dir` that is a bare repository `check` resolves it from
    only when given the same `--local-remote-dir` (#417), and the refusal
    says so. A url `check` finds from GitHub's remotes may name the same
    repository from these, and one it passes there may not; and one these
    resolve to a repository on this disk is asked whether it answers
    (#418), which a url on GitHub never is.
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
    """What the refusal's first line adds when a finding in it is one
    `check` prints only when given this run's `--local-remote-dir` (#417):
    a relative url resolved from `local_remote_dir`'s remotes -- #190's
    finding, or #418's of one that answers nothing there (`_FromTheLeg`).
    Nothing otherwise."""
    if local_remote_dir is None or not any(
            isinstance(finding, _FromTheLeg) for finding in findings):
        return ""
    return (" given the same --local-remote-dir, with each relative submodule "
            "url resolved from the leg remotes this run would create there")


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
        # The body is the split's message, which names the paths it moved,
        # as UTF-8 under any locale (`_run_exact`, #653).
        url = _run_exact(_pull_request_command(repositories, names, tracking,
                                               branch, message))
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

#: The key `execute` appends after `submodules:` (#525): the plan's answer
#: for each path the policy itself asked about, or put in another leg than
#: the plan's (#655). Read by the doctor by this name through the module it
#: loads, and spelt once more by the project's own `validate-manifest.py`,
#: as `SUBMODULE_RECORD` is.
ANSWER_RECORD = "answered_paths"

#: The comment above that block, for the same reader.
ANSWER_RECORD_PREAMBLE = (
    "",
    "# THE PATHS THE ADOPTION'S POLICY ASKED ABOUT OR PUT IN ANOTHER LEG,",
    "# and the leg each was ANSWERED into (#525, #655). Written once, by",
    "# `adopt-project.py execute`, from the adoption plan: one row per entry",
    "# kept in a leg that covers a path `contracts/path-classification.yaml`",
    "# could not call, or called for the other leg or the root, its path",
    "# inside that leg (a directory's with its `/`: without it, a row names",
    "# a file), the `resolution:` the plan gave it, and the source commit the",
    "# plan was answered at. `shape-doctor.py` takes each row as the answer",
    "# for that path in that leg: not asked again, and not misplaced. A",
    "# directory's row answers for every file under it, one added after the",
    "# adoption too: the doctor does not hold a file to `source_commit:`.",
    "# Like every field here, it confers nothing.",
    f"{ANSWER_RECORD}:",
)


def _record_block(preamble: tuple, rows: list, entries: list,
                  commit: str) -> str:
    """`preamble` and one row per `(path, leg, entry)` of `rows`: the shape
    both records take (#189, #525), or "" when there is no row.

    The entry's `resolution:` travels with each row it covers, and every
    path and reason is double-quoted, for the reasons `submodule_record`
    gives.
    """
    if not rows:
        return ""
    resolutions = {str(e.get("path")): _resolution_text(e.get("resolution"))
                   for e in entries}
    lines = list(preamble)
    for path, leg, entry in rows:
        lines.append(f"  - path: {double_quoted(path)}")
        lines.append(f"    leg: {leg}")
        if resolutions.get(entry):
            lines.append(
                f"    resolution: {double_quoted(resolutions[entry])}")
        lines.append(f'    source_commit: "{commit}"')
    return "\n".join(lines) + "\n"


def answered_path_record(policy: PathPolicy, entries: list, tree: list,
                         commit: str) -> str:
    """The `answered_paths:` block `execute` appends to `project.yaml` after
    `submodules:`, or "" when the plan kept no path in a leg the policy did
    not put it in (#525, #655).

    WHY THE ANSWER IS WRITTEN DOWN. A path the policy cannot call --
    `examples/` under `ambiguous-examples`, a directory whose extensions do
    not agree -- is a question `plan` asks and a human answers in the plan,
    which is committed nowhere. `shape-doctor.py` runs the same policy over
    each leg after the split and, with no record, asks the same question
    again on every run, of a path somebody already answered.

    AND AN ANSWER AGAINST A RULE, FOR THE SAME REASON (#655). A path a rule
    calls -- `docs/` under `spec-governance` -- may be answered into the
    other leg in the plan, with a `resolution:` saying why: `check` passes
    it and `execute` carries it out, because the plan is the person's word.
    With no record the doctor held the leg to the rule, and its first run
    after `adoption verified` called that path MISPLACED.

    THE POLICY'S OWN VERDICTS, READ AGAIN HERE. The policy's `walk` is run
    again over the source's paths at the plan's commit, gitlinks left out
    as the doctor leaves them out, and a row is written for each entry the
    plan answers `spec` or `code` (read as `_answered_legs` reads it) that
    covers a path the walk does not put in that leg: one it leaves `leg:
    null`, or one it calls for the other leg or the root. An entry
    answered as its rule says needs no record: the doctor's walk agrees
    with it. Not from the plan's own `review_required:`, which is a file a
    person edits: an entry they split by hand to answer one question two
    ways is still recorded, each half in its own leg, and one split to
    answer half of it against a rule is recorded for that half alone. An
    entry answered `root` or `drop` is in no leg, and the doctor never
    reads it. `.gitmodules` is left out: its question is which leg owns
    the submodules it registers, and `submodules:` answers that per
    submodule, which is the reading the doctor holds a leg's `.gitmodules`
    to. And a question `plan` asks for a reason of its own -- a gitlink
    under the entry, a name `execute` will not extract -- is not the
    policy's, and is recorded only where the policy's walk disagrees with
    the answer under it.

    AGAINST A RULE MEANS AGAINST WHAT `plan` SHOWED AS WELL (#655). `plan`
    walks the tree WITH its gitlinks, and a gitlink is one more verdict in
    its directory's extension majority, so it can keep `plan` from folding
    a directory the walk above folds: `plan` then proposes each file by its
    own extension. An entry left as `plan` wrote it was answered against
    nothing, so an answer against a rule is recorded only where it also
    differs from the leg `plan` showed: that walk, with its entries asked
    again by `ask_about_submodules` and `ask_about_refused_paths` as `plan`
    asks them. A question of the walk above is recorded as before.

    AND AGAINST WHAT EACH LEG'S OWN WALK SAYS (#801). The doctor walks a
    leg, not the source, and `walk` folds a directory by the files under it
    in THAT leg. A directory the source's walk folds, split by hand, leaves
    part of it in each leg, and a part may fold another way or not at all:
    `engine/` is 3 of 4 `.py`, exactly the 75% `extension_majority:`, so it
    folds to code; with `engine/c.py` answered `spec`, the code leg's
    `engine/` is 2 of 3, which does not fold, and there `engine/x.md` is
    spec by its own extension. Answers against their extensions can fold a
    directory in a leg as the source's walk did not, over an entry beside
    them left as `plan` wrote it. So `walk` is run again over each leg's
    own files -- the paths `_answered_legs` keeps in it, gitlinks left out,
    as the doctor runs it over the leg -- and an entry covering a path that
    walk does not put in that leg is recorded too, whether the walk asks of
    the path or puts it elsewhere. A row is added only where the doctor's
    walk of that leg disputes the path. A plan left as `plan` wrote it,
    over a source with no gitlink, gets none: each entry is whole in the
    leg `plan` gave it, and no directory above one can fold to another leg
    there, since at most a quarter of an entry's files read as one. Before
    it walks, the doctor also sets aside the files every repository carries
    (`everywhere_patterns`: names at the top of a leg, and `.github/`),
    which change how no other directory folds, and a name no report can
    carry, which can: this walk keeps both, as the one above does.

    A SOURCE WITH NO SUCH ENTRY GETS "" and so the `project.yaml` it always
    got, byte for byte.
    """
    gitlinks = {path for path, mode, _, _ in tree if mode == GITLINK_MODE}
    files = [(path, size) for path, mode, _, size in tree
             if path not in gitlinks]
    called = {entry.path: entry.leg for entry in walk(policy, files)}
    shown = {entry.path: entry.leg for entry in ask_about_refused_paths(
        ask_about_submodules(policy, walk(
            policy, [(path, size) for path, _, _, size in tree]), tree),
        tree)}
    answered = _answered_legs(entries, [path for path, _ in files])
    in_its_leg = _walked_in_each_leg(policy, files, answered)
    kept = sorted({entry: leg for path, (leg, entry) in answered.items()
                   if leg in EXTRACTED_LEGS and entry != GITMODULES
                   and (leg != in_its_leg.get(path)
                        or (leg != _walked_leg(called, path)
                            and (_walked_leg(called, path) is None
                                 or leg != _walked_leg(shown, path))))
                   }.items())
    return _record_block(ANSWER_RECORD_PREAMBLE,
                         [(entry, leg, entry) for entry, leg in kept],
                         entries, commit)


def _walked_in_each_leg(policy: PathPolicy, files: list,
                        answered: dict) -> dict:
    """`{path: leg}` for each of `files` that `answered` keeps in a leg:
    the leg `walk` gives it over THAT leg's files alone, as the doctor
    walks the leg after the split; None for a question (#801)."""
    out: dict = {}
    for role in EXTRACTED_LEGS:
        held = [(path, size) for path, size in files
                if path in answered and answered[path][0] == role]
        called = {entry.path: entry.leg for entry in walk(policy, held)}
        out.update((path, _walked_leg(called, path)) for path, _ in held)
    return out


def _walked_leg(called: dict, path: str) -> str | None:
    """The leg `walk` gave `path`, from `called` (`{entry path: leg}`): its
    own entry's, or the folded directory's above it; None for a question.
    The walk's entries cover each path it was given exactly once (#655)."""
    return next((called[name] for name in _covering_names(path)
                 if name in called), None)


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
    return _record_block(SUBMODULE_RECORD_PREAMBLE, kept, entries, commit)


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
                      code_path: str, branch: str, leg_commits: dict,
                      answers: str = "") -> tuple[str, str, list] | None:
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
        # And the plan's answers to the policy's own questions, and against
        # its rules, after it (#525, #655): `answered_path_record`, read
        # before any leg existed.
        if answers:
            append[SHAPE_MANIFEST] = append.get(SHAPE_MANIFEST, "") + answers
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
            print(f"  appended to {ATTRIBUTES}: "
                  f"{_appended_lines(materialized)}, so every checkout keeps "
                  "their bytes (#471); none of its own lines was changed")

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
    work_root = _work_root(args, NO_LEG_YET)
    # Before the source is opened, so before any leg exists (#524).
    _refuse_an_unwritable_work_dir(args, work_root)
    source = plan.open_source(args.source, work_root, done=NO_LEG_YET)
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
    local, repositories, urls = _repository_urls(args, plan, names, source,
                                                 naming)
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
    # The topic GitHub will not set was refused in `_repository_urls`, with
    # the names and the organisation, as `check` finds them (#863).
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

    # The plan's answers to the policy's own questions (#525), and against
    # its rules (#655), worked out here, before anything exists: the policy
    # is this standard's file, the one the doctor will ask, and one that
    # does not load refuses now and not after both legs are pushed. "" for
    # a plan that answered none.
    answers = answered_path_record(PathPolicy.load(PATH_POLICY),
                                   plan.entries, source.tree(), source.commit)

    # ---- (a) the two legs' remotes ----------------------------------------
    # Both asked about first, and everything in their way refused at once,
    # before either is made (#798): where `leg-remote-exists` always came,
    # so every refusal above keeps its order.
    _refuse_what_stands_in_the_legs_way(repositories, names,
                                        args.local_remote_dir)
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
                              code_path, branch, leg_commits, answers)
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
# source's path, and `check` does not ask about it: its own
# `--local-remote-dir` (#417) is not read for it.
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
    and is never iterated here. The pins are the products of the pins
    `execute` writes (`_declared_pins`): a `pins:` entry `_read_pins` names
    is that finding alone (#901), and `execute` writes none of a plan
    holding one."""
    fields = [(key, str(plan.get(key)), where)
              for key, where in WRITTEN_PLAN_VALUES.items()
              if plan.get(key) is not None]
    fields += [("a `pins:` item", pin, ROOT_MANIFEST)
               for pin in _declared_pins(plan)]
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

    EACH ENTRY IS SPELLED AS `y` SPELLS THE PLAN'S `product:`, by
    `shape_materialize.neutral_pin_entry`, the one function
    `scaffold-project.py` calls too (#924). Of the names `--pin` takes, it
    writes bare only one that begins with a letter, `_` or `.` (`y`'s
    `_PLAIN_RE`, the same rule) and that the reader reads back as the same
    text, after `key: ` and as a `- ` item alike (#181), so `openGlass` is
    the line it always was, `007` is `"007"`, and `true` and `null` are
    `"true"` and `"null"`. The reader is asked once more of the entry as
    this list holds it, as `family.py` asks it of a member's id (#259),
    rather than a list of its words, and an entry it would not read back as
    the same text is double-quoted all the same. Such a name reaches here
    from `plan` as well as from a plan edited by hand: `plan` records it
    quoted, and `check` passes it. The list is a block placeholder, so
    `render` writes it as it stands, and nothing else quotes it.
    """
    if not pins:
        return "[]"
    return "\n" + "\n".join(f"  - {_neutral_pin_entry(product)}"
                            for product in sorted(pins))


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
        # act; the calendar of the machine running the split does not. An
        # EMPTY `reference:` is a value, not one omitted (#902): read by its
        # truth, `reference: ""` was written as the default without a word,
        # and `plan --reference ''` planned it. The project's own validator
        # refuses it ("drop the key or name the document"), and `check`,
        # `execute` and `plan` ask the validator of this table.
        "REFERENCE": str(plan.get(REFERENCE_KEY)
                         if plan.get(REFERENCE_KEY) is not None
                         else default_reference(elected_on)),
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
    """The split commit's message, which is also the pull request's body.

    EACH PATH IS NAMED AS `plan`'S REPORT NAMES IT (`_shown`, #900): as it
    is, unless it is not printable, begins and ends with a backtick or
    ends in a space, and then `_spelled`. Written as it is, a name read as
    another path: `git commit` strips the whitespace that ends a line, so
    `cr\\r` was `cr`, and `env_commit` writes a character UTF-8 cannot
    carry as `?`, so `caf\\udce9.md`, the byte 0xE9 that is not UTF-8, was
    `caf?.md`. A follow-up, which a person may edit in the plan, is
    `_shown` too, as `execute` prints it before it begins.
    """
    def none_line(role: str) -> list[str]:
        if role not in seeded:
            return ["  (none)"]
        return [f"  (none — this leg was SEEDED from {SHAPE_REPOSITORY}'s "
                f"{SEED_TEMPLATE[role]}/, because no path of this repository "
                f"was assigned to it. It is mounted and pinned like the other "
                f"leg and carries no history from here, there being none.)"]

    # Beside the mounts `execute` made, the path the read-across follow-up
    # leaves to them (#600's review, F1; #906).
    across = contracts_from_code_leg(spec_path, code_path, paths_for["spec"],
                                     follow_ups)
    lines = [
        f"Adopt the three-repository shape: {names['spec']} and "
        f"{names['code']}",
        "",
        f"{names['assembly']} keeps its name, its identity and its full "
        "history and becomes the assembly root of the project. The two legs "
        "are NEW repositories extracted with `git filter-repo`, so every "
        "moved file keeps the commits that made it. Nothing was deleted: what "
        "leaves this tree arrives in a leg at the same path, mounted back "
        f"here at {spec_path}/ and {code_path}/"
        f"{across}.",
        "",
        f"MOVED TO THE SPEC LEG ({names['spec']} @ {leg_commits['spec'][:12]}):",
    ]
    lines += _listed_lines(paths_for["spec"]) or none_line("spec")
    lines += ["",
              f"MOVED TO THE CODE LEG ({names['code']} @ "
              f"{leg_commits['code'][:12]}):"]
    lines += _listed_lines(paths_for["code"]) or none_line("code")
    if paths_for["drop"]:
        lines += ["", "DROPPED (in no leg and no longer here):"]
        lines += _listed_lines(paths_for["drop"])
    lines += ["", "STAYS IN THE ASSEMBLY ROOT:"]
    lines += _listed_lines(paths_for["root"])
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
        lines += [f"  - {_shown(item)}" for item in follow_ups]
    return "\n".join(lines) + "\n"


def _listed_lines(paths) -> list[str]:
    """`paths`, sorted, one to a line of the split commit's message, each as
    `plan`'s report names it (`_shown`, #900)."""
    return [f"  {_shown(path)}" for path in sorted(paths)]


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
    findings += _split_manifest_findings(split_tree, before,
                                         paths_for["drop"])
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


def _appended_lines(materialized: Materialized) -> str:
    """What `execute` says it appended to the source's `.gitattributes`: a
    line for each pinned copy outside `shape/`, and the second line each
    copy written through a symlink has under its pinned path (#807)."""
    copies = len(eol_block_paths(materialized.shape_files, COLLISION_DIR))
    said = f"a `text eol=lf` line for each of {copies} pinned copies"
    second = len(materialized.eol_block) - copies
    if second:
        said += (f", and {second} more under the pinned path of each copy "
                 "written through a symlink, which governs it once the link "
                 "is replaced")
    return said


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
    it. Each copy the block names is named where the split's symlinks lead
    its pinned path (`_SplitTree.tracked_at`), the path git tracks, and then
    by that pinned path where it differs, as the materializer named it
    (#807).
    """
    source_oid = before.get(ATTRIBUTES)
    landed = after.get(ATTRIBUTES, [])
    root = [where for where in landed if where.startswith("root:")]
    if source_oid is None or len(root) != 1 \
            or root[0] == f"root:{source_oid}":
        return 0
    blobs = {path: oid for path, mode, oid, _ in tree if mode in FILE_MODES}
    split = _SplitTree(assembly, split_commit)
    pin = _pin_through_links(split)
    pinned = _pinned_shape_paths(assembly, pin) if pin else None
    if pinned is None or blobs.get(ATTRIBUTES) != root[0].split(":", 1)[1]:
        return 0
    paths = eol_block_paths(pinned, COLLISION_DIR,
                            {path: split.tracked_at(path) for path in pinned})
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
#: The exit of `adopt-manifest-not-shape` (#389).
MANIFEST_DEFECT = (
    "`execute` refuses before any leg exists a plan that keeps a path of the "
    f"source's at `{SHAPE_MANIFEST}` in the root (`{ROOT_BLOCKS_MANIFEST}`) "
    f"or mounts a leg there (`{LEG_COLLIDES}`), {SPLIT_IS_WRONG}")


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


def _split_manifest_findings(tree: list, before: dict,
                             drops: list[str]) -> list[str]:
    """`adopt-manifest-not-shape` when the root's `project.yaml` is not the
    shape's manifest (#389): the source's own entry is still there, or the
    manifest went beside the root's as `shape/project.yaml`, or both.

    THE ONE SHAPE FILE NO COPY STANDS IN FOR (#305). `shape-doctor.py`, the
    root's validators and `make bootstrap` read the manifest at the root
    itself. A plan that kept the source's `project.yaml` there had the
    manifest written beside it, and every source blob was still in exactly
    one place, so this check said `adoption verified` over an assembly the
    doctor calls NOT A SHAPE ROOT. `check` finds that plan and `execute`
    refuses it before any leg exists (`plan-root-blocks-manifest`), and that
    refusal was all there was: this check does not lean on it, as it leans
    on none of `check`'s (#165).

    BY BLOB, AS THE REST OF THE ACCOUNTING IS, and never by the pin, which
    does not list a rendered file. The source's own entry is matched by path
    and blob, whatever its mode: a kept symlink that led nowhere had the
    manifest written through it, and the root keeps the link. The copy is
    the shape's only when the source did not have that blob at that path: a
    source's own `shape/project.yaml`, kept where the root's `project.yaml`
    is the manifest, is a file like any other.

    A `project.yaml` THE PLAN DROPS IS NOT THE SOURCE'S OWN AT THE ROOT,
    whatever its bytes. `drops` is `paths_for["drop"]`, the list
    `_mount_the_legs` has `git rm`ed before the shape writes anything, so
    what is at `project.yaml` then is what the shape wrote: this asks what
    the split did, not what `check` refused. Matched by blob alone, a source
    file that held exactly the manifest this run renders, answered `drop`
    (a plan `check` passes, and main verified), was called the source's own,
    and the run failed after both legs were pushed (#389's review, R1). Only
    that half is waived: the manifest beside it is a finding still.
    """
    entries = {path: (mode, oid) for path, mode, oid, _ in tree}
    copy = f"{COLLISION_DIR}/{SHAPE_MANIFEST}"
    mode, oid = entries.get(SHAPE_MANIFEST, ("", ""))
    dropped = SHAPE_MANIFEST in {path.rstrip("/") for path in drops}
    kept = bool(oid) and oid == before.get(SHAPE_MANIFEST) and not dropped
    beside = copy in entries and entries[copy][1] != before.get(copy)
    if not (kept or beside):
        return []
    if kept:
        said = (f"{_spelled(SHAPE_MANIFEST)} in the root tree is the "
                f"source's own {_kind_of(mode).split()[-1]} ({oid[:12]}), "
                "not the shape's manifest"
                + (f", which is beside it as {_spelled(copy)}" if beside
                   else ""))
    else:
        said = (f"the shape's manifest is at {_spelled(copy)} in the root "
                "tree, where it is written only when the root already holds "
                f"{_spelled(SHAPE_MANIFEST)}")
    return [f"FINDING adopt-manifest-not-shape: {said}. `shape-doctor.py`, "
            "the root's validators and `make bootstrap` read the manifest at "
            f"{_spelled(SHAPE_MANIFEST)} itself, and no copy stands in for "
            f"it; {MANIFEST_DEFECT}"]


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

    def tracked_at(self, path: str) -> str | None:
        """Where the split tracks what `path` leads to, each symlink on the
        way followed (#807); None where the way leads out of the tree, above
        it, round a loop, or through what is no directory in it."""
        try:
            return self._resolve(path)
        except _NotInTheSplitError:
            return None

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
    that renaming it on GitHub comes first (`_rename_first`), never that
    `--project` takes one CamelCase token. A leg's name is the plan's own to
    edit, and keeps the remediation it had.

    THE RULE IS SAID IN PLACE TOO, of the new name (#902, L2-89 on #457).
    The way out was `_rename_first`'s alone, which says to rename the source
    and give its new name as `--project`, and said no rule for that name,
    where the same refusal of a name that is not the source's says
    "--project takes one CamelCase token with no hyphen, underscore, dot or
    space". Both say the rule now, from one table (`_name_remedy`).
    """
    for role, name in names.items():
        found = policy.classify(name, role, pins)
        in_place = (source.repository if role == "assembly"
                    and source is not None else None)
        if found is None:
            raise Refusal(
                UNCLASSIFIED,
                f"{name!r} matches no family in the naming policy",
                _name_remedy(UNCLASSIFIED, in_place))
        if not accepts_role(found, role):
            raise Refusal(
                ROLE_MISMATCH,
                f"{name!r} classifies as {found.family}"
                + (f"/{found.role}" if found.role else "")
                + f", not as the {role!r} form of a project leg "
                f"({found.reason})",
                _name_remedy(ROLE_MISMATCH, in_place))


#: `_check_names`' two refusals.
UNCLASSIFIED = "naming-unclassified"
ROLE_MISMATCH = "naming-role-mismatch"
#: What each of them says the assembly root's name may be, by its code: the
#: rule `naming-unclassified` gives (`PROJECT_NAME_RULE`), and the forms an
#: assembly root may take beyond it, which `naming-role-mismatch` gives.
NAME_RULES = {
    UNCLASSIFIED: f"{PROJECT_NAME_RULE}.",
    ROLE_MISMATCH: (
        "one CamelCase token. Two forms beyond the bare one MAY be the "
        "assembly root: a declared descendant (declare the pin with `--pin "
        "open<Product>@<40 hex commit>` and it classifies as one, "
        "2026-09-02), and an `open<Product>` neutral product, which may "
        "elect the shape and be its own root (2026-09-05). Neither may be the "
        "spec or code leg, and an `<X>-Install` may be no leg at all."),
}


def _name_remedy(code: str, repository: str | None) -> str:
    """What `_check_names`' refusal `code` says to do: `--project` takes the
    rule (`NAME_RULES`), or, where `repository` is the source adopted in
    place, whose own name `--project` is, that rule as the one its new name
    must follow, then `_rename_first`'s way out (#902). `check` asks it
    again to know the remedy it prints (#716)."""
    rule = NAME_RULES[code]
    if repository is None:
        return f"Remediation: --project takes {rule}"
    return _rename_first(repository, "--project is the source's own name, "
                         f"which must be {rule} ")


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
# because `org:` is read as `execute` reads it (`_plan_org`), as `str()` of
# what the file holds. One that `checked_value` refuses (a list, a mapping,
# an empty value, a space, a leading `-`, a character outside ASCII) is, in
# `execute`, `plan-not-the-source` where the plan is held to a repository
# (`_held_repository`, and the `org:` is not that repository's own) and
# `unsafe-value` where it is held to none. `check` asks `checked_value` of
# `org:` first (`_manifest_values`, and `_submodule_findings` where a kept
# submodule url is relative) and ends in `unsafe-value`, exit 2, before it
# compares anything; only where the plan's own names are refused, and no
# kept url is relative, does it reach the comparison with one (#716,
# L4-48). A source that names no repository (no `origin`, or one that ends
# in no `org/repo`) is asked nothing by `plan`, as before; `check` and
# `execute` hold the plan's names to what the plan recorded for it,
# `source: repository:`, where it recorded one (#716).
#
# AN `origin` THAT IS A PATH NAMES NO REPOSITORY (#521), in any separator
# (`url_repository`). It was read as its last two directories, so a clone of
# `/srv/clones/Atlas.git` was `clones/Atlas` and the right `--org` was refused,
# while the same path written with backslashes named nothing and was not
# compared. A path is a directory on this machine and says nothing of the
# repository on GitHub that `execute` acts on, so nothing is compared with it,
# and `plan` says so in a NOTE naming that repository (`_path_origin_notes`).
#
# AND A NAME THE POLICY REFUSES IS RENAMED FIRST, NOT RETYPED. Where the
# source's own name is one the naming policy refuses (`billing-service`), it
# cannot be adopted in place under that name, and no `--project` changes
# that: whether to rename the repository is a human's decision, made first on
# GitHub, and `plan` runs again after it. So these refusals say that, and
# `_check_names` says it in place of its hint to retype `--project`.

#: `plan`'s refusal of an `--org` and a `--project` that name another
#: repository than the source's (#499).
NOT_THE_SOURCE = "adopt-not-the-source"
#: `check`'s finding, and `execute`'s refusal, of a plan that does.
PLAN_NOT_THE_SOURCE = "plan-not-the-source"


def _is_the_source(repository: str, org: str, name: str) -> bool:
    """Whether `<org>/<name>` is `repository` as GitHub resolves a name:
    without case (#499)."""
    return f"{org}/{name}".casefold() == repository.casefold()


def _rename_first(repository: str, said: str = "") -> str:
    """The remediation where the source's own name is one the naming policy
    refuses, or one too long for GitHub to create a leg named after it
    (#838): it cannot be adopted in place under that name, and renaming it
    is a human's decision that comes first (#499). `said` is what the
    refusal says before that, a sentence or none. THE ONE TEXT of it.

    ON GITHUB, ALWAYS. The source names a repository only by a url or an
    `org/repo` (`url_repository`), so the repository renamed is one on
    GitHub. A path `origin` once named its last two directories, and this
    then said to rename the repository at that path (#513's review, NIT-3);
    it names none since #521, and nothing here is said of one."""
    return (f"Remediation: {said}{_shown(repository)} cannot be adopted in "
            "place under that name: an in-place adoption keeps the source's "
            "own name, and `--project` cannot rename it. Whether to rename "
            "it is a human's decision, made first on GitHub (`gh repo "
            "rename`); then run `plan` again against the renamed repository "
            "(`--source <org>/<new name>`, or a clone whose `origin` names "
            "it), with its new name as `--project`.")


def _origin_path(source: Source) -> str | None:
    """The source's `origin` where it is a filesystem PATH
    (`origin_is_a_path`), which names no repository (`url_repository`,
    #521); None for a source `plan` cloned from an `org/repo`, and for an
    `origin` that is a url, or none. Read as `source.repository` was read
    (`_origin_url`)."""
    if source.cloned:
        return None
    url = _origin_url(source.path)
    return url if url is not None and origin_is_a_path(url) else None


def _path_origin_notes(args, source: Source) -> list[str]:
    """What `plan` says where the source's `origin` is a path (#521): that
    `--org` and `--project` were not compared with it, and the repository
    `execute` acts on without `--local-remote-dir`, which only the person can
    say is the source. A NOTE, not a refusal: the plan names the repository
    the person gave it, as for a source with no `origin`."""
    path = _origin_path(source)
    if path is None:
        return []
    return [f"\nNOTE the source's `origin` is the path {_spelled(path)}, "
            "which names no repository on GitHub, so `--org` and `--project` "
            "were not compared with it.",
            "     `execute` without `--local-remote-dir` pushes the split to "
            f"{args.org}/{args.project}, opens its pull request there and "
            "sets its topic on it, so that must be the source's own "
            "repository on GitHub."]


def _own_name_remediation(repository: str, naming: NamingPolicy,
                          pins: set[str], done: str) -> str:
    """What `adopt-not-the-source` and `plan-not-the-source` say to do:
    `plan` again under the source's own name, or, where the naming policy
    refuses that name, `_rename_first`. `repository` is the one the source
    is held to (`_held_repository`), as text: where the live source names
    none, the plan's record of it, and `str(None)` is no name (#716). `done`
    is what the refusing command left as it was, said first.

    Where the naming policy refuses the source's own name, the rule the new
    name must follow is said before the way out (#902, L2-89 on #457), the
    rule `_check_names` gives for that refusal (`NAME_RULES`): the way out
    renames the source, and said nothing of the name to give it."""
    org, _, name = repository.partition("/")
    try:
        _check_names(naming, _names(name), pins)
    except Refusal as exc:
        rule = NAME_RULES.get(exc.code)
        return _rename_first(repository, f"{done}The source's own name is no "
                             f"remedy either: {exc.detail}. "
                             + (f"The name must be {rule} " if rule else ""))
    return (f"Remediation: {done}Run `plan` again with `--project "
            f"{_shown(name)} --org {_shown(org)}`, the source's own name, "
            "which `plan` writes into the plan's `org:`, `project:` and "
            "`legs:`. Any other name is another repository; if "
            f"{_shown(repository)} is not the one to adopt, plan from a clone "
            "of the one that is, or with `--source <org>/<repo>`.")


def _refuse_another_repository(args, source: Source, naming: NamingPolicy,
                               pins: set[str], org_given: bool = True) -> None:
    """`plan` refuses an `--org` and a `--project` that name another
    repository than the one the source names, as `adopt-not-the-source`,
    before anything is written (#499). `args.org` is settled: given, or,
    where `org_given` is false, read from the source, and then named by
    where it came from, not as a flag nobody passed (#427)."""
    repository = source.repository
    if repository is None or _is_the_source(repository, args.org,
                                            args.project):
        return
    named = (f"--org {args.org} and --project {args.project} name"
             if org_given else
             f"--project {args.project}, with the organisation of "
             f"{_org_read_from(source)} (`--org` not given), names")
    raise Refusal(
        NOT_THE_SOURCE,
        f"{named} {args.org}/{args.project}, and the source is "
        f"{_shown(repository)}: "
        "an in-place adoption keeps the source's own name, and `execute` "
        "pushes the split to the repository they name, opens its pull "
        "request there and sets its topic on it",
        _own_name_remediation(repository, naming, pins,
                              "no plan was written. "))


def _refuse_a_clone_of_another_repository(args, repository: str,
                                          naming: NamingPolicy) -> None:
    """What an `org/repo` `--source` is refused for BEFORE the clone (#903):
    the id derived from `--project` (`adopt-bad-id`), and then
    `adopt-not-the-source`, in the order `_checked_plan_inputs` asks them.
    The source's name is the one `--source` gives, and `--org` and
    `--project` are flags, so nothing here needs the clone. They were asked
    after `gh repo clone`, so with a clone that failed `--source acme/Thing
    --project Other` was `source-unclonable`, with a remedy about `gh auth
    status`, and never the refusal that says it is not the repository.

    Both are asked of a `Source` that holds the name alone and says it is
    a clone, as the source `plan` is about to make is (`_org_read_from`
    then names `--source`). `adopt-not-the-source` is
    `_refuse_another_repository`'s own question and words; `args.org` is
    read from it as `_checked_plan_inputs` reads it, and `args` is left as
    it was, so that both are asked again of the clone, where they pass,
    with `--org` still not given. A source read in place is asked after
    git has read its `origin`, which is where its name is."""
    named = Source(Path(SOURCE_READONLY), repository, "", "", cloned=True)
    # An `--id` that was passed was asked with the flags. The one derived
    # from `--project` is asked first, as `_checked_plan_inputs` asks it.
    # One that was passed and is no id reaches here only beside a name the
    # naming policy refuses (`_checked_flag_inputs`), which `_refuse_bad_id`
    # refuses first, in the words it has once the source is known (#902).
    products = set(declared_pin_products(args))
    passed = args.id is not None
    _refuse_bad_id(args.id if passed else args.project.lower(), args.project,
                   {"id"} if passed else set(), named, naming, products)
    asked = argparse.Namespace(org=_planned_org(args.org, named),
                               project=args.project)
    _refuse_another_repository(asked, named, naming, products,
                               args.org is not None)


def _last_two_directories(path: str) -> str | None:
    """`<directory>/<name>` for a filesystem path, in either separator and
    after a `:`, with one `.git` dropped from the name and the case kept;
    None where the path has fewer than two (#716).

    A SUPERSET OF WHAT v1.0.0 AND v1.0.1 READ. Their `_remote_repository`
    took `[:/]([^/:]+/[^/]+?)(?:\\.git)?$` of a path `origin` (until #521),
    which is its last two segments, split at `/` or `:`, one `.git` dropped
    from the second: `/srv/a:b/Atlas.git` was `b/Atlas`, and
    `/srv/clones/Atlas.git.git` was `clones/Atlas.git`. It read none for a
    trailing `/`, a backslash path, or a relative one that starts with no
    separator; this reads each as its last two directories too, which only
    holds a plan to nothing more often, and that is what main does."""
    segments = [part for part in re.split(r"[\\/:]", path) if part]
    if segments and segments[-1].endswith(".git") \
            and len(segments[-1]) > len(".git"):
        segments[-1] = segments[-1][:-len(".git")]
    return "/".join(segments[-2:]) if len(segments) >= 2 else None


def _held_repository(plan: Plan, source: Source) -> str | None:
    """The repository an in-place adoption by `plan` is held to, or None
    where there is none (#716): the one the live source names
    (`source.repository`), and where it names none, the one the plan
    recorded for it, `source: repository:`.

    A SOURCE WITH NO `origin` ONCE HELD A PLAN TO NOTHING. `plan` records
    `repository: null` for it and compares nothing, which is right; but a
    plan for acme/Atlas whose names were edited to `Atlsa`, with `origin`
    then removed from the source, or given a copy of it that has none by
    `--source`, checked `plan ok`, and `execute` went on to ask GitHub about
    `acme/Atlsa`. The record is read as `_github_name` reads a name, and
    never raises: one that is no text, or names no `owner/repo`, holds the
    plan to nothing, as a null does, and `Plan.open_source` is the reader
    that refuses one it must clone (`_recorded_repository`).

    A RECORD THAT IS THE PATH'S OWN LAST TWO DIRECTORIES HOLDS NOTHING. v1.0.0
    and v1.0.1 read a path `origin` as those directories (#521), so `plan
    --org acme --project Atlas` on a clone of `/srv/clones/Atlas.git` was
    refused with "`--org clones`" and, where the plan was written all the
    same, recorded `repository: clones/Atlas`. A person who put `org: acme`
    back by hand holds a correct plan, and holding it to that record
    refused it, with a remedy that is the advice #521 took out. Where the
    source's `origin` is a path (`_origin_path`), a record that is its last
    two directories, as `_last_two_directories` reads them without case, in
    either separator, is the old reader's and not the source's name: the
    plan is held to nothing. Any other record is held, so a `git clone` of
    the source, whose `origin` is a path, still holds a plan edited to
    `Atlsa` to `acme/Atlas`."""
    if source.repository is not None:
        return source.repository
    recorded = plan.source.get("repository")
    held = _github_name(recorded) if isinstance(recorded, str) else None
    path = _origin_path(source) if held is not None else None
    if path is not None:
        # Read as `held` was, so the two spellings are one name: v1.0.1
        # records `clones/Atlas.git` for `/srv/clones/Atlas.git.git`.
        old = _last_two_directories(path)
        old = None if old is None else _github_name(old)
        if old is not None and old.casefold() == held.casefold():
            return None
    return held


def _why_the_source_names_none(source: Source) -> str:
    """Why the live source names no repository, as `_not_the_source` says it
    beside the plan's record (#716): it has no `origin`, or its `origin`
    names none (a path, a url that ends in no `org/repo`, or one that is not
    UTF-8: `_remote_repository`)."""
    try:
        git_out(["remote", "get-url", "origin"], cwd=source.path, binary=True)
    except Refusal:
        return "it has no `origin`"
    return "its `origin` names no repository"


def _not_the_source(plan: Plan, source: Source,
                    names: dict[str, str]) -> str | None:
    """`plan-not-the-source`'s detail, or None: the plan's `org:` with its
    `legs.assembly:` (`names`, read by `Plan.names`) or with its `project:`
    names another repository than the one the source is held to
    (`_held_repository`): the one it names (#499), or, where it names none,
    the one the plan records for it (#716).

    `org:` is read as `execute` reads it (`_plan_org`), as whatever text
    `str()` makes of what the file holds. While it was compared only when
    it was text, a number, a boolean, a null or a deleted `org:` line
    checked `plan ok`, and `execute` acted on `2026/Atlas`, `True/Atlas` or
    `None/Atlas` (#513's review, SHOULD-1). Where it is not text, the detail
    says what the file holds beside how `execute` spells it. `project:` is
    read only as text: a misread one is not this question's to answer, and
    `execute` acts on `legs.assembly:`.

    AN `org:` THAT `checked_value` REFUSES IS CAUGHT, BUT NOT ALWAYS AS
    THIS (#716, L4-48): a list, a mapping, an empty value, one with a space,
    a leading `-` or a character outside ASCII. `execute` asks this first,
    so it refuses such an `org:` as `plan-not-the-source` where the plan is
    held to a repository (`_held_repository`, and the `org:` is not that
    repository's own), and as `unsafe-value`, from `_checked_plan_values`
    (#901), where it is held to none. `check` asks
    `checked_value` of `org:` first (`_manifest_values`, and
    `_submodule_findings` where a kept submodule url is relative) and ends
    in `unsafe-value`, exit 2, before it compares anything; only where the
    plan's own names are refused, and no kept url is relative, does it
    reach this with one."""
    repository = _held_repository(plan, source)
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
    # Where the live source names none, the plan's own record is what it is
    # held to, and the detail says so: the source did not say it (#716).
    is_the = (f"the source is {_shown(repository)}"
              if source.repository is not None else
              f"the plan records the source as {_shown(repository)} "
              f"({_why_the_source_names_none(source)})")
    return (f"the plan's {said} with its {keys} names {named}, "
            f"and {is_the}: an in-place adoption "
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
                _held_repository(plan, source), naming, pins,
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


def _work_root(args, done: str = "") -> Path:
    """The command's work directory: `--work-dir`, made where it is missing,
    or a new one in the system temp folder, which `args` keeps as
    `made_work_root`, so that `main` can remove it once the command has
    ended (`_leave_the_work_root`, #526).

    A `--work-dir` THAT CANNOT BE MADE IS REFUSED, by `plan`, `check` and
    `execute` alike, before anything is read (#650): a file is there or
    above it, a symlink there leads round a loop, or this user cannot write
    where it would be made. The bare `mkdir` ended each command in a
    FileExistsError, NotADirectoryError or PermissionError traceback, exit
    1, and on a loop Python 3.12's `Path.resolve` raised RuntimeError
    first; `os.path.realpath` is the same reading without that raise. The
    code and the way out are #524's, for one this user cannot write in;
    `done` is what the refusing command left as it was, said first.

    A `--work-dir` ANOTHER USER CAN RENAME IN IS REFUSED NEXT, before
    anything is made in it (#803): one another user owns, or one every user
    can write in without the sticky bit (`_shared_with_another_user`), as
    `adopt-work-dir-shared`. There another user could replace the clone
    `plan` reads, or turn the clone's removal onto a directory of theirs
    (#457's L1-99), or the legs `execute` builds. So is one under a
    directory another user can rename in (`_shared_above`): asked of the
    directories that exist BEFORE any is made, so that a refused run makes
    nothing, and again after. Asked with `os.lstat` of the real path, which
    is the one path the run uses from then on; never on Windows. Each
    directory made here is 0755 whatever the umask (`_made_0755`). The
    default work directory is not asked: `tempfile.mkdtemp` makes it 0700."""
    if not getattr(args, "work_dir", None):
        root = Path(tempfile.mkdtemp(prefix="openreposhape-adopt-"))
        args.made_work_root = root
        return root
    root = Path(os.path.realpath(args.work_dir))
    _refuse_a_shared_chain(root, done)
    try:
        _made_0755(root)
        status = os.lstat(root)
    except OSError as exc:
        raise _work_dir_refusal(
            f"--work-dir {_spelled(str(root))} cannot be made: making it a "
            f"directory failed ({exc.strerror or exc})", done) from None
    _refuse_a_shared_chain(root, done)
    shared = _shared_with_another_user(status)
    if shared:
        raise _shared_work_dir(
            f"--work-dir {_spelled(str(root))} {shared}, so another user "
            "could rename or replace what this run makes in it", done,
            WORK_DIR_OWN)
    return root


def _holds_a_file(root: Path) -> bool:
    """Whether anything but directories is in `root`, at any depth: a file,
    a symlink, anything else that is not a directory. A directory that
    cannot be listed counts, as it does for `_holds_something`."""
    def unlistable(exc: OSError) -> None:
        raise exc

    try:
        for top, directories, files in os.walk(root, onerror=unlistable):
            if files or any(os.path.islink(os.path.join(top, name))
                            for name in directories):
                return True
    except OSError:
        return True
    return False


def _removed_if_it_holds_no_file(root: Path) -> bool:
    """Remove `root` where it holds no file (`_holds_a_file`), and say
    whether it is gone.

    Nothing at all is what `plan` and `check` of a local source leave, and
    what `execute` leaves when it is refused before it builds anything; an
    empty `source-readonly/` is what a refused `gh repo clone` leaves.
    Anything else keeps all of it. Only `os.rmdir` removes, deepest first,
    and it removes an empty directory and nothing else, so nothing written
    there meanwhile is lost."""
    if not os.path.lexists(root):
        return True
    if _holds_a_file(root):
        return False
    try:
        for top, _, _ in os.walk(root, topdown=False):
            os.rmdir(top)
    except OSError:
        return False
    return True


def _writable_then_removed(remove, target, error) -> None:
    """`shutil.rmtree`'s handler where a clone is removed by path. What git
    wrote READ-ONLY, a clone's packs and loose objects, Windows refuses to
    unlink: a file or directory whose unlink or rmdir fails gets its write
    bit ADDED, and is removed again. Every other failure is raised as it
    was, and no mode is ever lowered (#652's review, F4): the handler once
    set the mode to exactly `S_IWRITE`, taking read and search away, and
    called whatever function failed, `os.open` included, which ended in a
    TypeError traceback. A symlink is never changed, since `chmod` would
    follow it."""
    if remove not in (os.unlink, os.remove, os.rmdir) \
            or os.path.islink(target):
        raise error if isinstance(error, BaseException) else error[1]
    os.chmod(target, stat.S_IMODE(os.lstat(target).st_mode) | stat.S_IWRITE)
    remove(target)


#: The keyword `_writable_then_removed` is given as: `onexc` from Python
#: 3.12, whose `onerror` warns.
REMOVAL_HANDLER = "onexc" if sys.version_info >= (3, 12) else "onerror"


def _opened_directory(path: str) -> int | None:
    """A descriptor of the directory at `path`, opened without following a
    symlink there; None where nothing is there. A symlink or anything else
    that is no directory is `_NotTheClone`."""
    try:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise _NotTheClone(NOT_THE_CLONE) from None
        raise


def _status_at(where: str, dir_fd: int | None) -> os.stat_result | None:
    """`os.lstat` of `where`, in the directory `dir_fd` where one is given;
    None where nothing is there. A path through something that is no
    directory is `_NotTheClone`."""
    try:
        return os.lstat(where, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        raise _NotTheClone(NOT_THE_CLONE) from None


def _held_to(status: os.stat_result, identity: tuple) -> None:
    """`_NotTheClone` where `status`, an `lstat`, is not the directory
    `identity` names: a symlink never is."""
    if not stat.S_ISDIR(status.st_mode) or _identity(status) != identity:
        raise _NotTheClone(NOT_THE_CLONE)


def _removed_if_still(parent: str, identity: tuple) -> None:
    """`os.rmdir` of `source-readonly/`, made by this run, where it is still
    that directory and empty; and silently not, as on main (#652)."""
    above, name = os.path.split(parent)
    with contextlib.suppress(OSError, _NotTheClone):
        held = _opened_directory(above) if FD_REMOVAL else None
        where = name if held is not None else parent
        try:
            status = _status_at(where, held)
            if status is not None:
                _held_to(status, identity)
                os.rmdir(where, dir_fd=held)
        finally:
            if held is not None:
                os.close(held)


def _remove_through_a_descriptor(claim: _Claim) -> None:
    """`_remove_a_tree` where `FD_REMOVAL` holds: `source-readonly/` opened
    once, never through a symlink, and held to its identity; the clone's
    directory asked and removed relative to that descriptor alone."""
    parent, name = os.path.split(claim.made_at)
    held = _opened_directory(parent)
    if held is None:
        return
    try:
        _held_to(os.fstat(held), claim.parent_identity)
        status = _status_at(name, held)
        if status is not None:
            _held_to(status, claim.identity)
            shutil.rmtree(name, dir_fd=held)
    finally:
        os.close(held)
    if claim.made_parent:
        _removed_if_still(parent, claim.parent_identity)


def _remove_by_path(claim: _Claim) -> None:
    """`_remove_a_tree` where no removal by descriptor is had: Python 3.9
    and 3.10, and Windows. The same checks, each with `os.lstat`, then
    `shutil.rmtree` of the path, with `_writable_then_removed`."""
    parent = os.path.dirname(claim.made_at)
    status = _status_at(parent, None)
    if status is not None:
        _held_to(status, claim.parent_identity)
        status = _status_at(claim.made_at, None)
    if status is not None:
        _held_to(status, claim.identity)
        shutil.rmtree(claim.made_at,
                      **{REMOVAL_HANDLER: _writable_then_removed})
    if claim.made_parent:
        _removed_if_still(parent, claim.parent_identity)


def _remove_a_tree(claim: _Claim) -> None:
    """Remove the directory `claim` names, and `source-readonly/` where
    this run made that too, each only where it is still the directory this
    run made (#803). Nothing at the path any more is nothing to remove;
    anything else there is `_NotTheClone`, and nothing is removed through
    it.

    ON MAIN THE REAL PATH WAS ASKED, AND THEN THE PATH REMOVED: a
    `source-readonly` swapped for a symlink between the two removed the
    directory of that name wherever the link led (#457's L1-99 (b)). Now
    the identity of each directory, `st_dev` and `st_ino` read right after
    this run's `mkdir`, is asked of what is there, never through a symlink.
    Where `FD_REMOVAL` holds, the removal is relative to the descriptor of
    the `source-readonly/` so asked, so no rename of `source-readonly/` or
    above it after the check redirects it. Elsewhere it is by path, after
    the same checks. Either way, only someone who can rename in the work
    directory, in its `source-readonly/` or in a directory above them could
    swap one, and `_work_root` and `_source_readonly_refusal` refuse all
    three before anything is made there: but for group write, which is not
    asked, and on Windows, where nothing is."""
    if FD_REMOVAL:
        _remove_through_a_descriptor(claim)
    else:
        _remove_by_path(claim)


def _why_kept(claim: _Claim) -> str | None:
    """Remove the clone `claim` names (`_remove_a_tree`), and say why it is
    not removed, in the words its NOTE ends with; None where it is."""
    now = os.path.realpath(claim.path)
    if not _same_spelling(now, claim.made_at):
        return (f"is not removed: that path now leads to {_spelled(now)}, so "
                "nothing is removed through it")
    try:
        _remove_a_tree(claim)
    except _NotTheClone as kept:
        return f"is not removed: {kept}"
    except OSError as exc:
        return (f"is kept: removing it failed ({exc.strerror or exc}). Delete "
                "it once nothing in it is needed")
    return None


def _leave_the_clones(args) -> None:
    """Remove each clone of a source this command made that no plan records
    (#652), however the command ended: `args.clones`, the `_Claim` of each
    directory `Source.clone` made for `plan` and `check`.

    ON MAIN EACH STAYED, and nothing said so: the clone `check --source
    <org/repo>` made, the one `check` made again where the plan's was gone,
    and the one a `plan` refused after its clone made. Without `--work-dir`
    each kept a directory in the system temp folder; with one, the next run
    given it was refused at the clone (`source-unclonable`, with a remedy
    about `gh auth status`), so `check --work-dir W` and then `execute
    --work-dir W`, as `check`'s help says to run them, failed.

    WHAT IS NEVER REMOVED. A clone that a written plan records: once `plan`
    has written it (`args.plan_written`), whatever ends the run after, its
    report cut short by a closed pipe or Ctrl-C included (#652's review,
    F2). `check` does not list a clone it made at the plan's own
    `local_path` (`Plan._recorded_source`,
    `Plan._keep_the_clone_at_the_record`).
    `execute` lists none: under `--local-remote-dir` its clone IS the
    assembly the split is pushed into, and the deletion command
    `adopt-branch-exists` prints runs in it; the work directory it made is
    named on its last line (`_leave_the_work_root`). A directory is listed
    only where this run's own `mkdir` made it (#803), so nothing a person,
    an earlier run or another run put there is. And it is removed only
    where its path still leads to it, compared as the platform compares
    names (#803), and where it is still the directory this run made
    (`_remove_a_tree`), so nothing outside the work directory's own
    `source-readonly/` is: not through a symlink or a junction there
    before the run, and not through one put there during it.

    A CLONE NOT REMOVED IS NAMED, in a NOTE on stderr: one that cannot be
    removed, which is kept, and since #803 one whose path no longer leads
    to it, where on main the skip said nothing (#457's L1-99 (a)). Nothing
    here raises: an exception the command raised reaches the caller as it
    was, and the exit is the command's (F4)."""
    if getattr(args, "plan_written", False):
        return
    for claim in getattr(args, "clones", None) or ():
        why = _why_kept(claim)
        if why:
            _flush_stdout()
            with contextlib.suppress(OSError, UnicodeError):
                print(f"NOTE the clone this run made, "
                      f"{_spelled(claim.made_at)}, {why}.", file=sys.stderr)


def _leave_the_work_root(args, succeeded: bool) -> None:
    """What happens to the work directory `_work_root` made for a command,
    however it ended: a success, a refusal, a failed command or an
    exception (#526). It is removed where it holds no file; where it holds
    one, it stays, and `execute` says where on its last line, on stdout
    after a success (`succeeded`) and on stderr after anything else.

    WITHOUT `--work-dir`, EVERY RUN LEFT ONE. `plan` and `check` of a local
    source read it in place and build nothing, so theirs was empty, as was
    the one of an `execute` refused before it built anything: 2,992 of the
    first 3,000 such directories in one container's `/tmp` were empty, and
    one run of `tests/test_adopt_pins.py` left 117. A directory that holds
    something is what a person may still need: the clone a
    `plan --source <org/repo>` records as `source.local_path`, which `check`
    and `execute` read; and the legs and the split `execute` built, which
    the verification table and the notice of a failure name. Those stay.

    A `--work-dir` the person gave is theirs, and nothing in it is removed
    here; `_leave_the_clones`, before this, removes from it only the clone
    `plan` or `check` made there that no plan records (#652). Nothing here
    raises: an exception the command raised reaches the caller as it
    was."""
    root = getattr(args, "made_work_root", None)
    if root is None or _removed_if_it_holds_no_file(root) \
            or getattr(args, "command", None) != "execute":
        return
    _flush_stdout()
    with contextlib.suppress(OSError, UnicodeError):
        print(f"NOTE the work directory this run made, {_spelled(str(root))}"
              ", is kept, because it holds what the run made there: delete "
              "it once nothing in it is needed.",
              file=sys.stdout if succeeded else sys.stderr)


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


def _work_dir_help(does: str, refused: str, but: str = "") -> str:
    """`--help` for `--work-dir` (#650): what the command does there
    (`does`), then where the default lands and what becomes of it, and of
    one given, which is the same in all three commands (`_work_root`,
    `_leave_the_work_root`) but for the clone `_leave_the_clones` removes
    (`but`, #652), then the codes the command refuses one under
    (`refused`), by the words the command prints."""
    return (f"{does} Default: a new directory in the system temp folder, "
            "removed when the run ends if it holds no file. A --work-dir "
            "you give is made where it is missing, and nothing in it is "
            f"removed{but}. {refused} {WORK_DIR_SHARED_HELP}")


#: What `_work_root` refuses in all three commands, said in each one's
#: `--work-dir` help (#803).
WORK_DIR_SHARED_HELP = (
    "Except on Windows, `adopt-work-dir-shared` refuses, before anything is "
    "made, one that a user other than this one or root owns or every user "
    "can write in without the sticky bit, one under such a directory, and "
    "one whose `source-readonly` is one.")


#: What a work directory that holds the clone's directory is refused as, in
#: `plan`'s and `check`'s `--work-dir` help (#652).
CLONE_TARGET_HELD = ("Where a source is cloned, one whose `source-readonly` "
                     "is a file or a symlink, or holds `<repo>` already, even "
                     "empty, is refused as `adopt-work-dir-occupied`.")
#: `--source`'s help on `check` and `execute`: how the source is read with
#: it and without it (#652), and a recorded path refused (#796, #430).
SOURCE_OVERRIDE_HELP = (
    "override the source the plan names, read as `plan --source` reads it. "
    "Without it, the plan's `source.local_path` is read; where that is a "
    "clone `plan` made (`source.cloned: true`) and is gone or no longer "
    "whole, its `source.repository` is cloned again, and any other "
    "`local_path` that is gone is refused as `plan-source-gone`; one that "
    "is a file, or a directory inside a repository, as "
    "`source-not-top-level`; and one this user cannot reach, a clone "
    "`plan` made included, as `source-unreadable`, never cloned again.")


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
                      help="a local path, read in place, or `org/repo` to "
                           "clone from GitHub, which a github.com url names "
                           "too. `source-ambiguous` refuses a name that is "
                           "also a path here, as `acme/Atlas` is beside a "
                           "directory `acme/Atlas`: pass `./acme/Atlas` for "
                           "the directory, or the url for the repository. "
                           "The path is a repository's top-level directory "
                           "(`git rev-parse --show-toplevel` prints it): "
                           "`source-not-top-level` refuses a file, or a "
                           "directory inside a repository. "
                           "`source-unresolvable` refuses an empty value, "
                           "and one that is neither a path that exists nor "
                           "an `org/repo`; `source-unreadable`, a path this "
                           "user cannot reach (under a directory it may not "
                           "search), which is never read as one that is not "
                           "there, nor cloned as an `org/repo`.")
    plan.add_argument("--project", required=True,
                      help="the assembly-root name; for an in-place adoption "
                           "it is the source repository's own name. "
                           f"`execute` refuses one over {GITHUB_PROJECT_MAX} "
                           "characters without --local-remote-dir: GitHub "
                           "keeps a leg's name, `<Project>-spec`, to "
                           f"{GITHUB_NAME_MAX}.")
    plan.add_argument("--org", default=None,
                      help="the organisation the source repository is in, "
                           "which the plan records as `org:` (default: the "
                           "organisation of an `org/repo` --source, or the "
                           "one a local source's `origin` url names). A "
                           "source whose `origin` is a path, or that has "
                           "none, names no organisation: `plan` refuses "
                           "it as `adopt-no-org` unless --org is given. "
                           f"`execute` refuses one over {GITHUB_OWNER_MAX} "
                           "characters without --local-remote-dir, GitHub's "
                           "limit on an organisation's name.")
    plan.add_argument("--id", default=None,
                      help="lowercase project id (default: --project "
                           f"lowercased). `execute` refuses one over "
                           f"{GITHUB_ID_MAX} characters without "
                           "--local-remote-dir: GitHub keeps a topic to "
                           f"{GITHUB_TOPIC_MAX}, and the topic is "
                           "`xf-project-<id>`.")
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
                           "(`plan-tracking-branch-missing`), and `plan` "
                           "refuses one git will not create as a branch "
                           "(`adopt-bad-tracking-branch`) and writes no "
                           "plan.")
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
    # TEXT, not `type=Path`: `Path("")` is `.`, so an empty value could not
    # be told from a typed `.` once parsed (`pin_source_path`).
    plan.add_argument("--pin-source", default=None,
                      help="a local clone to compute --pin digests from, "
                           "instead of reading the forge with `gh api` (the "
                           "TEST path; no network). The plan records the "
                           "path, so that `check` recomputes each digest "
                           "there; a path that is not one printable line is "
                           "refused as `adopt-unwritable-value`. The pin "
                           "file says only `local-clone`, never the path. "
                           "Given with no --pin to read it, the flag is "
                           "refused as `pin-source-unused`; an empty value "
                           "is refused as `pin-source-no-path`, and `.` "
                           "means this directory. `pin-source-not-a-clone` "
                           "refuses any other path than a clone's top level, "
                           "or a bare clone's, where a --pin's digest is "
                           "read.")
    plan.add_argument("--allow-empty-leg", action="append", default=[],
                      choices=EXTRACTED_LEGS,
                      help="record in the plan that this leg having NO path "
                           "is intended, so it may be SEEDED from the shape's "
                           "template instead of extracted. The InkRouter "
                           "services are specifications with no code yet "
                           "(2026-09-04): `--allow-empty-leg code`. "
                           "Repeatable.")
    plan.add_argument("--path-policy", type=Path, default=None)
    plan.add_argument("--out", default="adoption-plan.yaml",
                      help="where the plan is written: a file, in a folder "
                           "that is there and that this user can write in "
                           "(default: `adoption-plan.yaml` in the current "
                           "directory). Any other is refused as "
                           "`adopt-out-unwritable`, and no plan is written: "
                           "a folder, a pipe or a device, or a file in a "
                           "folder that is missing or that nobody can write "
                           "in. That is asked before the source is read or "
                           "cloned and before a work directory is made, and "
                           "a write that fails all the same is refused as "
                           "the same code. The --work-dir, and for an "
                           "org/repo source its `source-readonly/<repo>`, "
                           "may be missing: the run makes them.")
    plan.add_argument(
        "--work-dir", type=Path, default=None,
        help=_work_dir_help(
            "the directory an `org/repo` --source is cloned into, as "
            "`source-readonly/<repo>`, which the plan records as "
            "`source.local_path` for `check` and `execute` to read; a "
            "local --source is read in place.",
            "One that cannot be made, or that this user cannot write in "
            "when a source is cloned into it, is refused as "
            f"`adopt-work-dir-unwritable`. {CLONE_TARGET_HELD}",
            " but the clone, when `plan` writes no plan that records it"))
    plan.set_defaults(func=cmd_plan)

    check = subparsers.add_parser("check", help="validate a plan")
    check.add_argument("--plan", required=True)
    check.add_argument("--source", default=None, help=SOURCE_OVERRIDE_HELP)
    check.add_argument("--local-remote-dir", type=Path, default=None,
                       help="the directory `execute --local-remote-dir` will "
                            "be given (the TEST path): each relative "
                            "submodule url the plan keeps in a leg is "
                            "resolved from the bare repository `execute` "
                            "would create there, as that run resolves it, "
                            "and not from GitHub's, and `check` asks, as "
                            "`execute` asks before it makes either leg, "
                            "whether each leg's bare repository is already "
                            "there and whether this directory can be made "
                            "and written in. Nothing is created there. "
                            "Without it, `check` asks GitHub with `gh repo "
                            "view --json nameWithOwner` whether either "
                            "leg's name exists (a name GitHub only "
                            "redirects to a repository renamed or moved "
                            "away does not), and a `gh` that cannot answer "
                            "is a NOTE.")
    check.add_argument(
        "--work-dir", type=Path, default=None,
        help=_work_dir_help(
            "where `check` works: an `org/repo` --source, or the plan's "
            "`source.repository` where the clone `plan` made is gone or no "
            "longer whole, is cloned there. Give the one `execute` will be "
            "given.",
            "One this user cannot write in is a finding, "
            "`adopt-work-dir-unwritable`, and is refused under that code "
            "where a source would be cloned into it or cannot be opened, "
            f"as one that cannot be made is. {CLONE_TARGET_HELD}",
            " but a clone `check` made there, unless the plan records it"))
    check.set_defaults(func=cmd_check)

    execute = subparsers.add_parser("execute", help="carry the plan out")
    execute.add_argument("--plan", required=True)
    execute.add_argument("--source", default=None, help=SOURCE_OVERRIDE_HELP)
    execute.add_argument("--local-remote-dir", type=Path, default=None,
                         help="create the legs as bare repositories here "
                              "instead of calling `gh` (the TEST path). Both "
                              "are asked about before either is made: one "
                              "already there, or a directory that cannot be "
                              "made and written in, is refused, as `gh repo "
                              "view` finding either leg's name is without "
                              "it.")
    execute.add_argument("--allow-empty-leg", action="append", default=[],
                         choices=EXTRACTED_LEGS,
                         help="proceed even though NO path is assigned to this "
                              "leg, seeding it from the shape's template. "
                              "Unioned with the plan's own `allow_empty_legs:`; "
                              "without one of the two, execute refuses.")
    execute.add_argument("--yes", action="store_true",
                         help="the human has read the plan and the follow-ups")
    execute.add_argument(
        "--work-dir", type=Path, default=None,
        help=_work_dir_help(
            "where `execute` builds the two legs and the split, and clones "
            "an `org/repo` source; the verification table and the notice "
            "of a failure name what is there.",
            "A default one that holds what the run made is kept, and the "
            "run's last line names it. One that already "
            "holds what a run builds is refused as "
            "`adopt-work-dir-occupied`, and one that cannot be made, or "
            "that this user cannot write in, as "
            "`adopt-work-dir-unwritable`, before any leg repository "
            "exists."))
    execute.set_defaults(func=cmd_execute)

    args = parser.parse_args(argv)
    # The clones `Source.clone` makes for `plan` and `check`, which
    # `_leave_the_clones` removes where no plan records them (#652).
    args.clones = []
    # Stdout may still hold what ran before a refusal or a failed command
    # that reaches these handlers -- the plan's lines, the topic line -- so it
    # is flushed first, and a merged log keeps the order (#188). One a step
    # has already reported, with the notice of what it left
    # (`_create_leg_remotes` on its second leg), is not printed again: it
    # only sets the exit. However the command ends, the clones no plan
    # records go (#652), and then the work directory it made, where it holds
    # no file, last (#526).
    ended = None
    try:
        ended = args.func(args)
        return ended
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
    finally:
        _leave_the_clones(args)
        _leave_the_work_root(args, ended == 0)


if __name__ == "__main__":
    sys.exit(main())
