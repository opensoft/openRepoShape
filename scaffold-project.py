#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a project's three repositories in the shape this standard describes.

    ./scaffold-project.py --org <org> --project <Project> [--dry-run]

WHAT IT DOES
  1. Validates the three names — `<Project>`, `<Project>-spec`,
     `<Project>-code` — against `contracts/repository-naming.yaml` BEFORE it
     creates anything, so a naming mistake costs a message rather than three
     repositories and a rename. A leg path that is, holds or lies inside a
     path the shape writes into the assembly root (`contracts`,
     `project.yaml`, a `--pin`'s `contracts/<product>-pin.yaml`) is refused
     just as early, for the same reason (#197), and so is a `--pin` whose
     file the shape writes itself or another `--pin` writes (#241), and a
     `--referent-chain` link between the first and the last that is not a
     neutral product's name (#251). So is an `--elected-by`, `--reference`
     or `--name` that no file can hold as one line of text -- a byte that is
     not UTF-8, a line break, a control character, a bidi embedding,
     override or isolate -- given as the flag or read from the elector's
     fallback (#282).
  2. Creates the three remotes: `gh repo create` normally, or three BARE
     repositories in a directory with `--local-remote-dir`, which is the test
     path and touches no network.
  3. Materializes and pushes the spec and code trees.
  4. Materializes the assembly root, mounts the two legs as submodules, and
     writes the three pins — `commit` plus a `sorted-ls-tree-r-v1` tree digest
     for each leg, and a per-file sha256 pin over every file COPIED out of
     openRepoShape.
  5. Sets the `xf-project-<id>` topic on all three (skipped for local remotes).

WHY THE SHAPE FILES ARE COPIED AND NOT SUBMODULED. A scaffolded project must
work in an organisation that forked openRepoShape once and may never speak to
the upstream again; a project that needed the upstream mounted to run its own
gate would have made the shape a dependency rather than a shape. The copies are
digest-pinned in `contracts/shape-pin.yaml`, so "which openRepoShape is this a
copy of, and has anyone edited it since" both have answers.

WHAT THE NEW PROJECT MUST BE ABLE TO HOLD (#258, #261). The manifest is
rendered from the values the run is about to use, read with the project's own
YAML reader and put through the validator the template ships, BEFORE anything
is created and under `--dry-run` alike. A value the reader would turn into
something else where a template line writes it bare is refused as
`scaffold-manifest-misread`. The template writes `id` and `tracking_branch`
between double quotes (#259), so `--id null` or `--tracking-branch 007` is
held as typed, and that refusal guards the template rather than the flags. A
value the validator refuses (a blank `--elected-by`, `--reference` or
`--name`, an `--org` it cannot hold) is refused as
`scaffold-manifest-invalid`, in the validator's own words; an `--elected-on`
is read in the validator's form only, on every Python. A flag passed empty is
a value, refused by name by its own rule, never read as one not given (#911).
A name that cannot be a
directory's is refused as `scaffold-name-too-long`, and so is one GitHub will
not give a repository; an `--org` longer than GitHub keeps one is
`scaffold-org-too-long`, and an id whose topic GitHub will not set is
`scaffold-topic-too-long` (#838). An `--org` holding a character GitHub gives
no organisation (`.`), ending in a hyphen or holding two in a row is
`scaffold-bad-org` (#863). GitHub's limits are asked only without
`--local-remote-dir`, by the runs that make repositories on GitHub.

IDEMPOTENCY. It refuses to write into a remote or a working directory that
already exists. There is no --force: re-running over a live project is not a
scaffold, and the failure mode of getting it wrong is silent data loss. The
one exception is `--reuse-empty-repo`, which reuses each of the three remotes
while it has ZERO commits, and a leg whose one commit is the seed this
scaffold pushes (#462): a reserved name, or what a run whose later push an
organisation's ruleset refused left behind. It never deletes, rewrites or
force-pushes a remote. `--dry-run` asks the same question of the three
remotes and refuses `scaffold-remote-exists` as the real run does (#537), so
`setup-project.py` refuses at the plan, before it asks for the yes. Both
runs ask it after the folders, and before either makes one (#609): a file
where `--work-dir`, `--local-remote-dir` or a working tree must go, or a
folder this user cannot write in, is `scaffold-folder-cannot-be-made` or
`scaffold-target-exists`, never a traceback. Only gh's own not-found answer
says a repository does not exist; any other `gh repo view` failure (a bad
login, a rate limit, no network) is refused as `remote-unreadable`.

EXIT CODES: 0 done · 1 nothing (dry run prints and exits 0) · 2 refusal.
"""

from __future__ import annotations

import os
import argparse
import datetime as _dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, NEUTRAL_PRODUCT_OWNER, PROJECT_ID_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, accepts_role, checked_value,
    git_out, link_pins_from_trees, repo_basename, shell_line, shown_path,
    tree_digest,
)
from shape_materialize import (  # noqa: E402
    RULESET_HINT, SHAPE_REPOSITORY, CommandFailed,
    copy_tree, default_reference, descendant_note, election_date, env_commit,
    escape_what_stdout_cannot_encode, folder_flag_path, git_init_commit,
    materialize_assembly_root, naming_block, refuse_bad_branch, run,
    stage_written,
)
# The leg-path rule `adopt-project.py` asks of its own paths (#179).
from shape_materialize import refuse_bad_leg_paths  # noqa: E402
# The root's visibility and the Free-plan secrets note, asked as `family.py`
# asks them of its holder (#660).
from shape_materialize import (  # noqa: E402
    free_plan_secrets_note, repository_visibility_answer,
)
# What the plan says "not found" means against GitHub (#913, L2-61).
from shape_materialize import NOT_FOUND_WITH_THIS_TOKEN  # noqa: E402
# What the new project's own reader and `validate-manifest.py` would make of
# the values written into its manifest, and whether a repository's name can
# be a directory's: asked before anything is created (#258, #261).
from shape_materialize import (  # noqa: E402
    refuse_manifest_values, refuse_unstorable_names,
)
# And what GitHub keeps a repository's name, a topic and an organisation's
# name to, asked before anything is created where GitHub is (#838).
from shape_materialize import (  # noqa: E402
    GITHUB_ID_MAX, GITHUB_NAME_MAX, GITHUB_OWNER_MAX, GITHUB_PROJECT_MAX,
    GITHUB_TOPIC_MAX, refuse_a_topic_github_cannot_set,
    refuse_an_owner_github_cannot_have,
)
# And the characters GitHub gives an organisation's name (#863).
from shape_materialize import refuse_an_owner_github_cannot_spell  # noqa: E402
from shape_advisory import scaffold_lines  # noqa: E402
# Whether `--elected-by`, `--reference` and `--name` are text a file can
# hold: the question `adopt-project.py` asks of the same values (#282).
from shape_materialize import unwritable_reason  # noqa: E402
# The words a chain link that is not reachable is offered: what THIS tool
# reads (#610), which setup's step (4) hands the naming gate too (#661).
from shape_materialize import (  # noqa: E402
    scaffold_link_remedies as _link_remedies,
)
# The shape half of the leg-path collision rule, which `adopt-project.py`
# asks of its own mount paths (#172), imported as one unit (#197), with the
# one spelling of the file a `--pin` adds to what the shape writes.
from shape_materialize import (  # noqa: E402
    assembly_root_paths, neutral_pin_path, shape_path_collisions,
)
# The one spelling of a `neutral_product_pins:` entry (#516), which
# `adopt-project.py execute` calls too, so the same `--pin` writes the same
# line whichever tool made the root (#924).
from shape_materialize import (  # noqa: E402
    neutral_pin_entry as _neutral_pin_entry,
)
# What both runs ask before the first write, as `family.py init` asks it
# (#609): each folder this run makes, each working tree it writes, and gh's
# not-found answer as the one failure of `gh repo view` that means absent.
from shape_materialize import (  # noqa: E402
    make_folder, refuse_unless_not_found, refuse_unmakeable_folder,
    shown_source, target_in_the_way, target_remediation,
)
# How the READMEs' `git clone` line spells the clone URL, one word (#693),
# in the quoting `shell_line` gives the NEXT STEPS clone (#486).
from repo_shape import shell_quoted  # noqa: E402

#: How a refusal names each value the manifest records (#258, #261). The leg
#: paths are not here: `refuse_bad_leg_paths` asks for them (#179, #225).
MANIFEST_FLAGS = {
    "PROJECT_ID": "--id", "PROJECT_NAME": "--name",
    "ELECTED_BY": "--elected-by", "ELECTED_ON": "--elected-on",
    "REFERENCE": "--reference", "VISIBILITY": "--visibility",
    "TRACKING_BRANCH": "--tracking-branch", "ORG": "--org",
}

#: The pin argument: `openGlass@<40 hex>`, optionally organisation-qualified.
#: It, its digest and its collisions are `shape_materialize`'s since #273,
#: because `adopt-project.py plan --pin` takes the same argument and writes
#: the same file; imported under the names this file has always called them
#: by, so what it refuses, and in which words, is unchanged.
from shape_materialize import (  # noqa: E402
    declared_pin_products, declared_pin_values, pin_source_path,
    refuse_an_unread_pin_source,
    refuse_colliding_pins as _refuse_colliding_pins,
)

#: The naming-policy form every link between a chain's first and last must
#: classify as (#251). Each such link is an entry of the link before its
#: `neutral_product_pins:`, the key a link is verified by
#: (`referent.chain.link_declared_by`), so it is a neutral product's name.
CHAIN_LINK_FORM = "neutral-product"


def _gh_not_found(question: str, exc: FileNotFoundError) -> Refusal:
    """NO `gh` ON PATH IS `gh-not-found` (#537), as `pin_digest_from_gh` names
    it, and not a `FileNotFoundError` traceback. Each `gh` read this file makes
    before it creates anything refuses with this one, in these words, where
    `question` is what could not be asked."""
    return Refusal(
        "gh-not-found",
        f"the `gh` CLI is not on PATH, so {question} cannot be asked: {exc}",
        "Remediation: put `gh` on PATH, logged in (`gh auth login`), and "
        "run this again: the real run creates the three repositories "
        "with `gh repo create`. `openRepoShape --preflight` names each "
        "missing prerequisite and offers to install it, on a typed "
        "yes.")


def remote_is_empty(repository: str) -> bool | None:
    """Does `<org>/<repo>` exist on GitHub with ZERO commits?

    True: it exists and is empty. False: it exists and has commits. None: it
    does not exist. GitHub answers a commit listing for an empty repository
    with 409 and the words "Git Repository is empty", which is the only
    reliable signal — `size: 0` is also what a repository of small files says.

    NO `gh` ON PATH IS `gh-not-found` (#537), and not a `FileNotFoundError`
    traceback: `--dry-run` asks this question too now, and before that a dry
    run needed no `gh` at all.

    ONLY GH'S NOT-FOUND ANSWER IS "IT DOES NOT EXIST" (#609). Any failure of
    `gh repo view` used to be, so a bad login, a rate limit or an outage
    planned under `--dry-run` and sent the real run on to `gh repo create`;
    `refuse_unless_not_found` refuses every other failure by name.
    """
    try:
        probe = subprocess.run(
            ["gh", "repo", "view", repository, "--json", "name"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
    except FileNotFoundError as exc:
        raise _gh_not_found(
            f"whether {repository} already exists on GitHub", exc) from exc
    if probe.returncode != 0:
        refuse_unless_not_found(repository, probe)
        return None
    commits = subprocess.run(
        ["gh", "api", f"repos/{repository}/commits?per_page=1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    if commits.returncode != 0:
        blob = (commits.stderr + commits.stdout).lower()
        if "empty" in blob:
            return True
        raise Refusal(
            "remote-unreadable",
            f"{repository} exists but its commit listing could not be read: "
            f"{commits.stderr.strip()}",
            "Remediation: check `gh auth status`, then re-run.",
        )
    try:
        return not json.loads(commits.stdout)
    except json.JSONDecodeError:
        return False


def remote_visibility(repository: str) -> str | None:
    """`<org>/<repo>`'s GitHub visibility (`private`, `public`, `internal`),
    lowercased; `REPOSITORY_NOT_FOUND` where gh's answer is that this token
    finds no such repository; or None if it cannot be read — `gh repo view`
    failed otherwise, or answered a word that is not one of the three. It is
    `repository_visibility_answer`, the reader `family.py` asks of its
    holder (#660), which tells not-found apart (#913): `_leg_visibility`
    says before its plan that a root it could not read is unread, and a root
    not there yet is the ordinary run. Never called for a
    `--local-remote-dir` repository: a bare repository on disk has no
    visibility at all.

    NO `gh` ON PATH IS `gh-not-found` (#537), as `remote_is_empty`'s is, and
    not a `FileNotFoundError` traceback: `--reuse-empty-repo` reads the root's
    visibility (`_leg_visibility`) BEFORE it asks `remote_is_empty` whether the
    three repositories exist, in a dry run and a real one alike, so the refusal
    has to come from here too or the run never reaches the one that has it.
    """
    try:
        return repository_visibility_answer(repository)
    except FileNotFoundError as exc:
        raise _gh_not_found(
            f"what visibility {repository} has on GitHub", exc) from exc


def local_remote_is_empty(bare: Path) -> bool | None:
    """The same question for a bare repository on disk (the test path)."""
    if not bare.exists():
        return None
    out = subprocess.run(["git", "-C", str(bare), "rev-list", "--count", "--all"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    if out.returncode != 0:
        raise Refusal("remote-unreadable",
                      f"{bare} exists but is not a git repository")
    return out.stdout.strip() in ("", "0")


def main(argv: list[str] | None = None) -> int:
    # FIRST, so that every `print` after it -- `--help` included -- escapes
    # a name stdout cannot encode rather than raising on it (#214).
    escape_what_stdout_cannot_encode()
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # GITHUB'S LIMITS, said where each value is typed (#838), and asked
    # only without `--local-remote-dir`, as the plan asks them.
    parser.add_argument("--org", required=True,
                        help="the organisation the three repositories are "
                             f"created in; at most {GITHUB_OWNER_MAX} "
                             "characters without --local-remote-dir, "
                             "GitHub's limit on an organisation's name")
    parser.add_argument("--project", required=True,
                        help="the assembly-root name, e.g. Atlas; at most "
                             f"{GITHUB_PROJECT_MAX} characters without "
                             "--local-remote-dir, as GitHub keeps a "
                             f"repository's name to {GITHUB_NAME_MAX} and "
                             "`-spec` adds 5")
    parser.add_argument("--id", default=None,
                        help="lowercase project id (default: --project "
                             f"lowercased); at most {GITHUB_ID_MAX} "
                             "characters without --local-remote-dir, as "
                             "GitHub keeps the topic `xf-project-<id>` to "
                             f"{GITHUB_TOPIC_MAX}")
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument("--visibility", choices=VISIBILITY_CHOICES,
                        default=None,
                        help="default: private for a fresh scaffold; with "
                             "--reuse-empty-repo and an existing assembly "
                             "root, the legs it creates INHERIT that root's "
                             "own visibility instead (a mismatch with an "
                             "explicit --visibility is a warning, not a "
                             "refusal, and so is a reused leg's)")
    parser.add_argument("--pin-owner", default=NEUTRAL_PRODUCT_OWNER,
                        help="the organisation an UNQUALIFIED --pin name "
                             f"resolves under (default: {NEUTRAL_PRODUCT_OWNER}, "
                             "where every neutral open<Product> lives — never "
                             "this scaffold's own --org). Name the owner in "
                             "--pin itself (owner/openProduct@<sha>) to "
                             "override it for one pin without changing this "
                             "default for the others.")
    parser.add_argument("--elected-by", default=None,
                        help="the human electing the shape (default: "
                             "GIT_AUTHOR_NAME, then `git config user.name`); "
                             "not blank")
    parser.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    parser.add_argument("--reference", default=None,
                        help="the document the election followed. Default: "
                             "openxFactory's ratified "
                             "docs/project-repo-schema.md for an election on "
                             "or after 2026-09-02, and the staged fragment it "
                             "was ratified from for one dated earlier — so "
                             "--elected-on chooses it, and a back-dated "
                             "project does not claim it followed a document "
                             "that did not exist yet.")
    parser.add_argument("--tracking-branch", default="main",
                        help="the branch every repository is created on "
                             "(default: main)")
    parser.add_argument("--spec-path", default="spec",
                        help="where the spec leg is mounted, as a path in "
                             "the assembly root (default: spec). A path that "
                             "is, holds or lies inside a FILE the shape "
                             "writes into the root is refused before anything "
                             "is created: `project.yaml` is one, and "
                             "`contracts` holds several.")
    parser.add_argument("--code-path", default="code",
                        help="where the code leg is mounted, as a path in "
                             "the assembly root (default: code). A path that "
                             "is, holds or lies inside a FILE the shape "
                             "writes into the root is refused before anything "
                             "is created: `project.yaml` is one, and "
                             "`contracts` holds several.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and ask, as the real run does, "
                             "whether each folder it makes can be made "
                             "(--work-dir, the trees in it, "
                             "--local-remote-dir) and whether each of the "
                             "three repositories already exists (`gh repo "
                             "view` and its commit listing, or the bare "
                             "repositories with --local-remote-dir), "
                             "refusing what it refuses; make no folder, "
                             "create no remote and push nothing")
    # TEXT, not `type=Path`, as `--pin-source` and `--work-dir` are: `Path("")`
    # is `.`, so an empty value could not be told from a typed `.` once
    # parsed (`folder_flag_path`).
    parser.add_argument("--local-remote-dir", default=None,
                        help="create bare repositories here instead of calling "
                             "`gh repo create` (the TEST path; no network)")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--reuse-empty-repo", action="store_true",
                        help="if <org>/<Project>, <Project>-spec or "
                             "<Project>-code already exists and has ZERO "
                             "commits, use it instead of refusing, and a leg "
                             "whose one commit is the seed this scaffold "
                             "pushes too: an operator holding the bypass "
                             "right finishes a run a ruleset refused by "
                             "re-running it with this. A root with commits, "
                             "and a leg with any other, is still refused: "
                             "that is a live repository, not a slot.")
    parser.add_argument("--pin", action="append", default=[],
                        metavar="openProduct@COMMIT",
                        help="declare a neutral-product pin, e.g. "
                             "--pin openGlass@<40 hex>. It writes "
                             "contracts/<openproduct>-pin.yaml and lists the "
                             "product in the manifest, which is what makes a "
                             "`<Domainx><Product>` name a DESCENDANT rather "
                             "than a name shaped like one. Repeatable, "
                             "once per product (the same name in another "
                             "case, or under another owner, is the same "
                             "product).")
    parser.add_argument("--referent-chain", default="",
                        metavar="openLayer,openProduct",
                        help="the CHAIN of neutral-product pins this project "
                             "reaches its referent through, e.g. "
                             "--referent-chain openXdox,openDox. Its first "
                             "entry must be one of the --pin products (the "
                             "pin this project actually holds), its last "
                             "must be the `open<Product>` the name claims, "
                             "and every link between them must be a neutral "
                             "product's name (`open<Product>`, e.g. "
                             "openXdox); the manifest RECORDS it, which is "
                             "what makes a descendant that pins a LAYER a "
                             "descendant (2026-09-05).")
    # TEXT, not `type=Path`: `Path("")` is `.`, so an empty value could not
    # be told from a typed `.` once parsed (`pin_source_path`).
    parser.add_argument("--pin-source", default=None,
                        help="a local clone to compute --pin digests from, "
                             "instead of reading the forge with `gh api` (the "
                             "TEST path; no network). The pin file says "
                             "only that the digest was read from "
                             "`local-clone`, never the path. Given with no "
                             "--pin and no --referent-chain to read it, it "
                             "is refused as `pin-source-unused`; an empty "
                             "value is refused as `pin-source-no-path`, and "
                             "`.` means this directory. A --pin's digest is "
                             "read only at a clone's top level, or a bare "
                             "clone's: any other path is refused as "
                             "`pin-source-not-a-clone`.")
    parser.add_argument("--work-dir", default=None,
                        help="where the working trees are built "
                             "(default: a temporary directory)")
    parser.add_argument("--no-next-steps", action="store_true",
                        help="leave out the closing NEXT STEPS (the clone, "
                             "the cd and `make bootstrap`): setup-project.py "
                             "passes it, because it runs those steps itself "
                             "next. `Working trees are at` still prints.")
    args = parser.parse_args(argv)

    try:
        return _scaffold(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2


#: The two legs and the template each is seeded from: what `_seed_legs`
#: builds, and what `seed_tree` builds again to know a leg's seed (#462).
LEG_TEMPLATES = {"spec": "spec-root", "code": "code-root"}


def seed_tree(role: str, values: dict, tracking: str, scratch: Path) -> str:
    """The tree of the one commit `_seed_legs` makes for the `role` leg
    (#462), built as `_seed_legs` builds it and in `scratch`, so nothing is
    written into the work directory before every remote has been asked.

    `copy_tree` from the same template with the same values, `git init` on
    the tracking branch and `stage_written`: the index `_seed_legs` commits.
    Git names a tree by its content, so a run given the same values builds
    the same tree whoever commits it and on whatever day. The values a leg's
    template takes are the project's names, its id, display name and topic,
    the two leg paths and the root's clone URL; no date and no commit.
    """
    work = scratch / "seed"
    written = copy_tree(SHAPE_ROOT / "templates" / LEG_TEMPLATES[role], work,
                        values)
    run(["git", "init", "-q", "-b", tracking, str(work)])
    stage_written(work, written)
    return run(["git", "write-tree"], cwd=work).lower()


#: THE ONE PROMPT RULE (#542, #915): what every git command this scaffold
#: sends to a remote runs with, over the caller's environment. That is
#: `only_commit`'s two (`PROBE_ENV`), `_take_held_seed`'s fetch and each
#: push, of a leg and of the root (`PUSH_ENV`). git's own terminal prompt is
#: off. `gh` can
#: see a repository that git cannot read -- `gh` is logged in and git has no
#: credential for the host -- and git then asks the terminal for a username,
#: so a re-run typed in one stopped there, waiting, before a word about the
#: leg (#542). A `--reuse-empty-repo` re-run whose legs are empty asks
#: `only_commit` nothing, and its first push waited at the same prompt
#: (#915). With the prompt off, the credential git would ask a person for is
#: a failure in git's own words: `_held_seed` reads it as a leg git cannot
#: read, and a push, a first run's as a re-run's, is refused with how to give
#: git a login (`_refused_push`).
#:
#: ssh, a credential helper and an askpass program are not turned off: they
#: are how people give git a credential, and each of them still asks under
#: this rule (#915's probes). Whether the rule must never wait for input,
#: ssh run with `BatchMode=yes` for one, is #915's open ruling question; it
#: is decided here, once, for every command above.
REMOTE_ENV = {"GIT_TERMINAL_PROMPT": "0"}

#: What `only_commit`'s two commands run with: the prompt rule, and git's
#: words untranslated (#915). `_unread_because` reads git's `fatal:` line,
#: and the line ssh printed before git's generic one, and in a locale whose
#: catalogue translates git there is neither, so the reason fell back to
#: git's last line, which is advice about its own command. Under `LC_ALL=C`
#: gettext translates nothing and ignores `LANGUAGE`, and nothing
#: `only_commit` reads of git's output depends on the locale.
PROBE_ENV = {**REMOTE_ENV, "LC_ALL": "C"}

#: What each push, a leg's and the root's, runs with: the prompt rule, and
#: git's words untranslated, as `only_commit`'s two (#993). `_refused_push`
#: reads a refused push's output to name its fix, and git translates the
#: line it prints where the host refused the login it sent
#: (`LOGIN_REFUSED`), so in a locale whose catalogue translates git that
#: login was named by the ruleset hint alone. The cost is git's own lines of
#: a refused push in English, inside a refusal this tool prints in English;
#: a push that goes through shows nothing of git's.
PUSH_ENV = {**REMOTE_ENV, "LC_ALL": "C"}


def only_commit(url: str, scratch: Path) -> tuple[str, str] | None:
    """`(commit, tree)` when the repository at `url` holds exactly ONE commit
    and every ref it has names it, else None (#462).

    `git ls-remote` lists every ref, `HEAD`, a `seed/*` branch and a pull
    request's included, and one object name across all of them is the first
    half. That object is then fetched ALONE (`--depth=1`) into a bare
    repository in `scratch`, never the history behind it, and a commit with
    no parent is the second half. So a repository somebody works in is told
    apart by its listing or by one commit, and is never cloned whole to be
    refused. The same question on disk and on GitHub: both are a git URL.
    Both commands that reach `url` run under `PROBE_ENV`, and a `url` git
    cannot read raises `CommandFailed` for `_held_seed` to answer (#542).
    """
    tips = {line.split()[0].lower()
            for line in run(["git", "ls-remote", url],
                            env=PROBE_ENV).splitlines()
            if line.strip()}
    if len(tips) != 1:
        return None
    commit = tips.pop()
    probe = scratch / "probe.git"
    run(["git", "init", "-q", "--bare", "--template=", str(probe)])
    run(["git", "fetch", "-q", "--depth=1", url, commit], cwd=probe,
        env=PROBE_ENV)
    if run(["git", "cat-file", "-t", commit], cwd=probe) != "commit":
        return None
    header = run(["git", "cat-file", "commit", commit],
                 cwd=probe).split("\n\n", 1)[0].splitlines()
    if any(line.startswith("parent ") for line in header):
        return None
    tree = next(line.split()[1] for line in header if line.startswith("tree "))
    return commit, tree.lower()


def _held_seed(role: str, url: str, values: dict, tracking: str,
               scratch: Path) -> tuple[str | None, str | None]:
    """`(commit, None)` when a leg that is not empty holds ONE commit and its
    tree is the one this run would seed the leg with (#462); `(None, None)`
    when it holds anything else; `(None, why)` when git cannot read it
    (#542).

    That is a leg a run of this scaffold pushed before a later push was
    refused, by an organisation's ruleset or anything else, or one an
    operator seeded by pushing that run's own clone: what Brett Heap ruled
    the re-run accepts on 2026-10-12, "Accept the scaffold's own seed". The
    commit's message, author and date are not asked: two runs never make
    the same commit, and they make the same tree.

    A LEG GIT CANNOT READ holds nothing this run knows of (#542). "Empty" is
    asked of `gh` (`remote_is_empty`), and `gh` sees a repository that git
    cannot read when `gh` is logged in and git has no credential for the
    host. `only_commit`'s `CommandFailed` reached `main` as the generic
    `a git or gh command failed`, which named neither the leg nor a way on.
    It is answered here instead, `why` being the command git refused and
    what git said, and `_reusable_remotes` refuses the leg as
    `scaffold-remote-exists`, as it refuses any leg with commits, saying that
    git could not read it. Only `only_commit` is answered so: `seed_tree`
    reads nothing remote, and a failure there is still `CommandFailed`.
    """
    try:
        held = only_commit(url, scratch)
    except CommandFailed as exc:
        return None, _unread_because(exc)
    if held is None:
        return None, None
    commit, tree = held
    seeded = tree == seed_tree(role, values, tracking, scratch)
    return (commit if seeded else None), None


#: The `fatal:` line git prints when the program it reaches a remote through
#: failed, ssh above all: it says only that the remote could not be read,
#: and the program's own last line, printed just before it, says why (#915).
GENERIC_FATAL = "fatal: Could not read from remote repository."


def _unread_because(failed: CommandFailed) -> str:
    """Why git could not read a leg, in one line (#542): the command, its
    exit and git's first `fatal:` line, or its last line when it printed no
    `fatal:`. The rest of git's output is advice about its own command
    ("Please make sure you have the correct access rights"), which the
    refusal's remedy replaces.

    WHERE THAT `fatal:` IS `GENERIC_FATAL`, THE LINE BEFORE IT IS THE REASON
    (#915). A git config that rewrites `https://github.com/` to ssh sends
    `only_commit` over ssh, and ssh's `Permission denied (publickey).`, the
    real reason, carries no `fatal:`, so it was dropped for git's generic
    line. A `fatal:` of git's own before the generic one (`'<path>' does not
    appear to be a git repository`) is kept, as it was; so is the generic
    line when nothing came before it. `PROBE_ENV` keeps git's words
    untranslated, so both lines are found in any locale."""
    said = [line.strip() for line in failed.output.splitlines()
            if line.strip()]
    first = next((index for index, line in enumerate(said)
                  if line.startswith("fatal:")), None)
    if first is None:
        why = said[-1] if said else ""
    elif said[first] == GENERIC_FATAL and first:
        why = said[first - 1]
    else:
        why = said[first]
    return (f"`{' '.join(failed.args_list)}` exited {failed.code}"
            + (f": {why}" if why else ""))


def _reusable_remotes(names: dict, urls: dict, repositories: dict,
                      local: bool, reuse_flag: bool, values: dict,
                      tracking: str) -> dict[str, str | None]:
    """Which remotes already exist, and whether that is allowed: each one
    `--reuse-empty-repo` reuses, mapped to the commit it holds, or to None
    when it is empty.

    THE ASSEMBLY ROOT may already exist only with `--reuse-empty-repo`, and
    only with ZERO commits. An organisation that creates the repository
    first and asks for the shape second is the ordinary case, not a mistake;
    an EMPTY repository is a name that has been reserved, and reserving a
    name is not starting a project. A root with commits is refused: that is
    a live project, and `adopt-project.py` is the tool for one of those.

    EACH LEG is reused on the same terms, and also when its one commit is
    the seed this scaffold pushes (#462; Brett Heap, 2026-10-12, "Re-run
    reuses empty legs" and "Accept the scaffold's own seed"). A run whose
    push an organisation's ruleset refused left all three repositories
    behind, empty or, for a leg pushed before the refusal, holding its seed,
    and its re-run was refused as `scaffold-remote-exists` for them, with or
    without the flag, so no exit finished it. Re-run with the flag by an
    operator holding the bypass right, it reuses them and pushes the seed
    itself. Any other leg with commits is still refused, and nothing here
    deletes, rewrites or force-pushes a remote. "Empty" is asked as it
    always was, of `remote_is_empty` or `local_remote_is_empty`; the seed is
    asked only of a leg that is not empty, and a leg git cannot read is
    refused as one with commits, saying so (#542).

    A LOCAL REMOTE IS NAMED AS `shown_path` NAMES A PATH (#766), as
    `family.py init` names its holder's: it is a path under
    `--local-remote-dir`, where `scaffold-unwritable-value` refuses a
    control character first. A GitHub `<org>/<name>` is named as it is.
    """
    reused: dict[str, str | None] = {}
    with tempfile.TemporaryDirectory(prefix="openreposhape-seed-") as scratch:
        for role in names:
            target = Path(urls[role]) if local else repositories[role]
            empty = (local_remote_is_empty(target) if local
                     else remote_is_empty(target))
            if empty is None:
                continue
            seed, unread = ((None, None) if role == "assembly" or empty else
                            _held_seed(role, urls[role], values, tracking,
                                       Path(scratch) / role))
            if reuse_flag and (empty or seed):
                reused[role] = seed
                print(f"  reuse {target} " + (
                    "(zero commits)" if empty else
                    f"(one commit, {seed[:12]}: the seed this scaffold "
                    "pushes)"))
                continue
            raise Refusal(
                "scaffold-remote-exists",
                f"{shown_path(target) if local else target} already exists"
                + ("" if local else " on GitHub")
                + ("" if empty else " and has commits"),
                _exists_remedy(role, empty, reuse_flag, seed is not None,
                               unread))
    return reused


#: Where git reaches GitHub over ssh, the clause each remedy for git's access
#: names beside `gh auth setup-git` (#915): `_exists_remedy`'s for a leg git
#: could not read, and `_login_remedy`'s for a push git had no login for.
#: `ssh -T` is asked as git asks: of the user, host and port the rule names,
#: with whatever `GIT_SSH_COMMAND` or `core.sshCommand` adds (the variable
#: overrides the setting, so a person with either set is told of both).
#: `ssh -T git@github.com`, which this named first, asks the default host,
#: port and key, so it said nothing true of a rule naming a `Host` alias of
#: `~/.ssh/config`, or `ssh.github.com` on port 443, or of a key that
#: `core.sshCommand` gives by `-i` (RV971). GitHub takes ssh only as the user
#: `git`, so `ssh -T -p 443 ssh.github.com` without `git@` is refused
#: whatever the key, which is why the user is named too (RV971, round 2).
#: That check alone is `SSH_KEY_CHECK`, which `_login_remedy` also names for
#: a push ssh was refused (#993).
SSH_KEY_CHECK = ("`ssh -T` against the user, host and port your rule names, "
                 "with anything your `GIT_SSH_COMMAND` or `core.sshCommand` "
                 "adds, says whether GitHub takes yours")
SSH_KEY_CLAUSE = ("where a `url.<base>.insteadOf` rule in your git config "
                  "sends `https://github.com/` over ssh, git logs in with an "
                  "ssh key instead, and " + SSH_KEY_CHECK)


def _exists_remedy(role: str, empty: bool, reuse_flag: bool,
                   seeded: bool = False, unread: str | None = None) -> str:
    """The remedy line for a remote that is already there.

    Each situation answers to its own exit, and a refusal that named only
    one of them would send a human to the wrong one. `seeded` is a leg whose
    one commit is this scaffold's seed (#462), and `unread` says why git
    could not read a leg that exists with commits, so whether it holds that
    seed is not known (#542): its exit is git's access, then the same re-run.

    GIT'S ACCESS IS NAMED FOR BOTH WAYS GIT REACHES GITHUB (#915). `gh auth
    setup-git` gives git's https the login `gh` has, and does nothing for an
    operator whose git config rewrites `https://github.com/` to ssh: there
    git logs in with an ssh key, and the command named is still the https
    URL this run gave git. So the ssh key's clause (`SSH_KEY_CLAUSE`) stands
    beside the `setup-git` one, each saying where it applies.
    """
    if role != "assembly":
        if unread:
            return (f"Remediation: git could not read it ({unread}), so "
                    "whether its one commit is the seed this scaffold pushes "
                    "cannot be asked. Let git read it (on GitHub, `gh auth "
                    "setup-git` gives git the login `gh` has; "
                    + SSH_KEY_CLAUSE + "), then re-run: with "
                    "--reuse-empty-repo a leg whose one commit is that seed "
                    "is reused, and a leg holding anything else is still "
                    "refused. There is no --force.")
        if empty or seeded:
            return ("Remediation: "
                    + ("it has ZERO commits" if empty else
                       "its one commit is the seed this scaffold pushes, "
                       "left by a run that stopped after pushing it")
                    + f", so re-run with --reuse-empty-repo to use it as the "
                    f"{role} leg. A run an organisation's ruleset refused is "
                    "finished that way, by an operator holding the bypass "
                    "right.")
        return ("Remediation: it holds commits other than the one seed this "
                "scaffold would push to it, so it is not a slot this scaffold "
                "may fill. Delete it, or scaffold under a different "
                "--project. A leg a run of this scaffold seeded is reused "
                "only when this run would seed it with the same tree, which "
                "takes the same flags and the same openRepoShape. There is "
                "no --force.")
    if empty and not reuse_flag:
        return ("Remediation: it has ZERO commits, so it is a reserved name "
                "rather than a live project — re-run with --reuse-empty-repo "
                "to use it as the assembly root.")
    return ("Remediation: it HAS commits, so it is a live repository and this "
            "is not a scaffold. Use `adopt-project.py plan --source "
            "<org>/<repo> --project <Project>` to convert it in place, which "
            "keeps its name, its identity and its history. There is no "
            "--force.")


def _leg_collision_remediation(neutral_pins=()) -> str:
    """What a leg-path collision tells the person to do. The paths are
    `assembly_root_paths(neutral_pins)`, the materializer's own list for this
    run, never a copy of it: each `--pin` adds the file it writes."""
    return (
        "Remediation: nothing was created, and nothing here picks a path for "
        "you, so pass another one yourself. A leg path neither is, holds nor "
        "lies inside, whatever the case, a path the shape writes into the "
        "assembly root ("
        + ", ".join(f"`{path}`" for path in assembly_root_paths(neutral_pins))
        + "). The defaults `spec` and `code` pass."
    )


def _refuse_colliding_leg_paths(spec_path: str, code_path: str,
                                neutral_pins=()) -> None:
    """Neither leg is mounted over a path the shape writes into the assembly
    root, or this refuses (#197).

    `_build_assembly_root` writes the shape into the root FIRST and mounts
    the legs after it, so a leg path the shape had just written was met only
    by `git submodule add`. On main through 20e13f0, `--spec-path contracts`
    and `--code-path project.yaml` planned under `--dry-run`, then created
    all three repositories, pushed both legs, left the root empty and exited
    2 (`'contracts' already exists and is not a valid git repo`).
    `--code-path Makefile/code` died the same way, and `--spec-path
    Contracts` exited 0 with a gitlink beside the shape's `contracts/`,
    which a macOS or Windows disk keeps as one path. Against GitHub, each
    left three repositories for a run that made no project.

    THE QUESTION IS `adopt-project.py`'s (#172), asked through the one
    definition both tools import: `shape_path_collisions` over
    `assembly_root_paths(neutral_pins)`, so a file the shape gains is
    refused here without anybody editing this tool. It is asked with no
    collision directory, because the scaffold hands the materializer none
    and writes nothing under adopt's `shape/`.

    A `--pin` IS ONE MORE PATH. `_build_assembly_root` hands the materializer
    `neutral_pins=pins`, which writes `neutral_pin_path(product)` for each,
    so `neutral_pins` is those products (`declared_pin_products`) and they
    are asked about with the rest. Without them, `--pin openGlass@<sha>
    --spec-path contracts/openglass-pin.yaml` planned and then made three
    repositories, and `Contracts/OpenGlass-pin.yaml` exited 0 with a gitlink
    beside the pin, one path on a macOS or Windows disk. With no `--pin`,
    `contracts/openglass-pin.yaml` lies inside a directory the shape writes
    into, not a path it writes, and it mounts. `_refuse_colliding_pins` runs
    first (#241), so each pin's path is listed once and is none of the
    shape's own, and a count here counts distinct paths.
    """
    collisions = [sentence
                  for what, value in (("--spec-path", spec_path),
                                      ("--code-path", code_path))
                  for sentence in shape_path_collisions(
                      what, value, neutral_pins=neutral_pins)]
    if collisions:
        raise Refusal("scaffold-leg-path-collides", " ".join(collisions),
                      _leg_collision_remediation(neutral_pins))


def _refuse_unholdable_manifest(args, values: dict, policy) -> None:
    """The manifest this run would write is one the project can hold, or this
    refuses (#258, #261), before a work directory or a remote exists and
    under `--dry-run` alike.

    `values` is the whole substitution table, so the project's own YAML
    reader and `validate-manifest.py` are asked about the `project.yaml` the
    run is about to write: a value the reader would turn into something else
    where a template line writes it bare is `scaffold-manifest-misread` (the
    template quotes `id` and `tracking_branch`, #259, so `--id null` and
    `--tracking-branch 007` are held as typed), and one the validator refuses
    (a blank `--elected-by`, `--org test+org`) is `scaffold-manifest-invalid`.
    `shape_materialize.refuse_manifest_values` asks both, and says why each is
    refused.

    A value a flag did not supply is named by where it came from, so the
    sentence does not point at a flag nobody typed. A flag passed empty
    supplied its value, `''`, and is named as the flag (#911), as `_identity`
    reads it.
    """
    flags = dict(MANIFEST_FLAGS)
    for key, flag, given, source in (
            ("PROJECT_ID", "--id", args.id, ID_DERIVED_FROM),
            ("PROJECT_NAME", "--name", args.name, "--project"),
            ("ELECTED_BY", "--elected-by", args.elected_by,
             "GIT_AUTHOR_NAME or `git config user.name`")):
        if given is None:
            flags[key] = f"{flag} (not given, so {source})"
    refuse_manifest_values(
        "scaffold", values, policy, flags,
        "Nothing was created, and `--dry-run` refuses the same.")


def _elector(args) -> str:
    """(a) Whose act electing this shape was, or a refusal.

    Split out of `_scaffold` for #138. `--elected-by` first, then this
    machine's git identity; the manifest records a name either way, because
    electing this shape is a human's act and `elected_by` is the record of
    whose. `_elector_named` says which of the three answered, in this order.

    A `--elected-by ''` IS THE FLAG'S ANSWER (#911). It was read by its
    truth, so an empty one fell back to this machine's identity without a
    word, and with none `scaffold-no-elector` said "no --elected-by" of a
    flag that was passed. It is a value now, and the project's own
    validator refuses it by name (`_refuse_unholdable_manifest`), as it
    refuses `--elected-by ' '`; the fallback answers only where the flag is
    not given.
    """
    elected_by = args.elected_by
    if elected_by is None:
        try:
            # Per-invocation identity first, then the config — never a global
            # config write (see the CI workflow note, 2026-09-03). The config
            # is DECODED AS `sys.argv` AND `os.environ` ARE (#282): a byte
            # that is not UTF-8 is kept as `surrogateescape` keeps one, for
            # `unwritable_reason` to name. `git_out`'s own strict decode
            # raised `UnicodeDecodeError` on a `user.name` holding one, a
            # traceback where `--elected-by` holding it is a refusal.
            elected_by = ((os.environ.get("GIT_AUTHOR_NAME") or "").strip()
                          or git_out(["config", "user.name"], cwd=SHAPE_ROOT,
                                     binary=True).decode(
                                         "utf-8", "surrogateescape").strip())
        except Refusal:
            elected_by = ""
        if not elected_by:
            raise Refusal(
                "scaffold-no-elector",
                "no --elected-by, no GIT_AUTHOR_NAME and no `git config "
                "user.name`. Electing this shape is a human's act and the "
                "manifest records whose.",
                "Remediation: re-run with --elected-by 'Your Name'.",
            )
    return elected_by


def _identity(args, project: str) -> tuple[str, str, str, str, str]:
    """(b) Who this project is and who elected the shape for it, from the
    defaults its flags fall back to: `(project_id, display, elected_on,
    reference, elected_by)`.

    Split out of `_scaffold` for #138, and the ORDER inside it is load-bearing.
    `--elected-on` is PARSED HERE, before anything is created, whether or not
    it is the value that chooses the reference: an explicit --reference must
    not let a malformed --elected-on through into a manifest field no reader
    can use. The three free-text values are asked here too, beside the date
    and for the same reason, whether a file can hold them (#282): before a
    work directory or a remote exists, and under `--dry-run` alike.

    A FLAG PASSED EMPTY IS A VALUE, NOT A FLAG NOT GIVEN (#911). Each was
    read by its truth (`args.id or project.lower()`), so `--id ''`,
    `--name ''`, `--elected-on ''`, `--reference ''` and `--elected-by ''`
    planned their defaults and exited 0, and a script's `--id "$ID"` with
    `ID` unset scaffolded the derived id without a word. Each is read by `is
    not None` now, as `adopt-project.py plan` reads its own (#658), and an
    empty one meets its flag's own rule and is refused there by name:
    `--elected-on ''` by `election_date` just below, `--id ''` as
    `scaffold-bad-id` (`_refuse_bad_id`), and the three free-text values by
    the project's own validator (`_refuse_unholdable_manifest`). The id is
    held to `checked_value`'s alphabet after `_refuse_bad_id`, where an
    empty one is named for the id it is not, rather than as `unsafe-value`.
    """
    project_id = args.id if args.id is not None else project.lower()
    display = args.name if args.name is not None else project
    elected_on = (args.elected_on if args.elected_on is not None
                  else _dt.date.today().isoformat())
    election_date(elected_on)
    reference = (args.reference if args.reference is not None
                 else default_reference(elected_on))
    elected_by = _elector(args)
    _refuse_unwritable_values((
        (_elector_named(args), elected_by, ROOT_MANIFEST_AND_README),
        ("--reference", reference, ROOT_MANIFEST_AND_README),
        ("--name", display, NAME_WRITTEN_INTO)))
    return project_id, display, elected_on, reference, elected_by


#: Where `_identity` takes the id from when no `--id` is passed, as a
#: sentence names it: in the label `_refuse_unholdable_manifest` gives a
#: value no flag supplied, and in `scaffold-bad-id` (#659).
ID_DERIVED_FROM = "--project lowercased"

#: The rule a `--project` is held to, as `naming-unclassified` states it
#: (`_check_one_name`). `scaffold-bad-id`'s derived remedy names it in the
#: same words, so the person who follows it is not sent from one refusal to
#: the other (#659).
PROJECT_NAME_RULE = ("one CamelCase token with no hyphen, underscore, dot "
                     "or space")

#: How `scaffold-bad-id` is told to go on (#659), in the words
#: `adopt-project.py plan` gives `adopt-bad-id` (#658). A `--id` the person
#: passed is theirs to retype. An id `_identity` derived is `--project`
#: lowercased, and `--project` also names the three repositories, which the
#: naming policy reads itself: every form it holds takes only ASCII letters,
#: digits and hyphens, so "pass an explicit lowercase --id" led straight to
#: `naming-unclassified`, and so would "change --project" to `North-Wind`.
#: The derived remedy names the rule.
#:
#: A PASSED ONE IS TOLD WHAT AN ID MAY HOLD (#911): `PROJECT_ID_RE` in
#: words. "Pass an explicit lowercase --id" was said to `--id foo_bar`,
#: which is both, and whose fault is the underscore. `family-bad-id` says
#: the same sentence of its own `--id`.
PASSED_ID_REMEDIATION = ("Remediation: pass an --id of lowercase letters, "
                         "digits and hyphens, starting with a letter or "
                         "digit.")
DERIVED_ID_REMEDIATION = (
    f"Remediation: change --project to {PROJECT_NAME_RULE}. The id is "
    f"{ID_DERIVED_FROM}, and an explicit --id would not change --project, "
    "which also names the assembly root and both legs.")


def _refuse_bad_id(project_id: str, given: str | None, policy,
                   project: str) -> None:
    """`scaffold-bad-id`: an id the project's validators would not take
    (`PROJECT_ID_RE`), named by where it came from (#659), as
    `adopt-project.py plan` names `adopt-bad-id` (#658).

    `given` is `--id` as parsed. One the person passed, `''` among them
    (#911), is named as the flag they typed, value as typed, and is told
    what an id may hold (`PASSED_ID_REMEDIATION`). With none, `_identity`
    derived the id from `--project`, and `--id 'north_wind' must match`
    named a value nobody had typed: the flag is named as
    `_refuse_unholdable_manifest` names one, by where its value came from.

    A REFUSED NAME SPEAKS FIRST (#911). `--project North_Wind --id
    north_wind` was refused for its id, and the remedy's retype then met
    `naming-unclassified`, which no `--id` mends. So a passed id is refused
    only once `--project` is a name the naming policy holds as an assembly
    root; one it does not is refused here as `_check_one_name` refuses the
    assembly root's name, which `_check_declared_names` asks later, after
    `_declaration`. The question is the policy's answer for the name in the
    `assembly` role with nothing declared, and NOTHING DECLARED TURNS ITS NO
    INTO A YES (#972's review, M1): `classify` answers None only when
    `matches` finds no pattern; a form decided by its characters alone
    (`UNAMBIGUOUS_FORMS`) carries the same role whatever is pinned; and a
    pin makes a descendant form the assembly root only where the name also
    satisfies the `project-leg/assembly` form, which it answers with no pin
    too. So `Foo-Install` is refused here, and so are `Atlas-spec` and
    `Atlas-code`, a leg's form with a pin or without: `--project Atlas-spec
    --id foo_bar` was told to retype the id, and `--id foo-bar` then met
    `naming-role-mismatch`. A name a pin can make the root, `MedxGlass`,
    passes here, and every answer is asked with no process started. A
    derived id keeps its own refusal: its remedy is already the naming
    rule."""
    if PROJECT_ID_RE.match(project_id):
        return
    pattern = PROJECT_ID_RE.pattern
    if given is not None:
        found = policy.classify(project, "assembly")
        if found is None:
            raise _unclassified(project)
        if not accepts_role(found, "assembly"):
            raise _role_mismatch(project, found, "assembly")
        raise Refusal("scaffold-bad-id",
                      f"--id {project_id!r} must match {pattern}",
                      PASSED_ID_REMEDIATION)
    raise Refusal("scaffold-bad-id",
                  f"--id (not given, so {ID_DERIVED_FROM}) is "
                  f"{project_id!r}, which must match {pattern}",
                  DERIVED_ID_REMEDIATION)


#: How `scaffold-topic-too-long` and `scaffold-org-too-long` are told to go
#: on (#838). A `--id` the person passed is theirs to shorten. One
#: `_identity` derived is `--project` lowercased, and an explicit `--id` is
#: the way round it that keeps the three repositories' names as they are.
NOTHING_MADE = ("Remediation: nothing was created, and `--dry-run` refuses "
                "the same.")
PASSED_TOPIC_REMEDIATION = (
    f"{NOTHING_MADE} Pass a shorter --id, of at most {GITHUB_ID_MAX} "
    "characters.")
DERIVED_TOPIC_REMEDIATION = (
    f"{NOTHING_MADE} Pass an explicit --id of at most {GITHUB_ID_MAX} "
    f"characters: the id need not be {ID_DERIVED_FROM}, and --project, "
    "which names the three repositories, stays as it is.")
ORG_REMEDIATION = (
    f"{NOTHING_MADE} Pass --org as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`: GitHub gives no user or "
    f"organisation a name of more than {GITHUB_OWNER_MAX} characters.")
#: How `scaffold-bad-org` is told to go on (#863): `ORG_REMEDIATION`'s way
#: out, without the number, which is not what it broke.
ORG_SPELLING_REMEDIATION = (
    f"{NOTHING_MADE} Pass --org as GitHub spells the organisation, the "
    "`<org>` of `https://github.com/<org>`.")


def _refuse_what_github_cannot_hold(args, project_id: str, policy) -> None:
    """`scaffold-org-too-long` and `scaffold-topic-too-long`: an `--org`
    GitHub gives no organisation, and an id whose `xf-project-<id>` topic
    GitHub will not set (#838); and `scaffold-bad-org`, an `--org` whose
    characters GitHub gives no organisation (#863). Each is refused where
    GitHub is asked, before any repository or work directory exists and
    under `--dry-run` alike. No process has started yet where `--elected-by`
    or GIT_AUTHOR_NAME names the elector; otherwise `_identity` has asked
    `git config user.name` first, as it has before `scaffold-bad-id`.

    THE TOPIC IS SET LAST (`_set_topics`), after `_create_remotes`,
    `_seed_legs` and `_build_assembly_root`, so an id over 39 characters,
    which a `--project` of 40 or more gives by default, failed there with
    all three repositories created and seeded. Under `--local-remote-dir`
    neither is asked: a bare repository on disk has no topic and no owner.
    The id is named as `_refuse_bad_id` names it, by where it came from; a
    `--id ''` was refused there (#911), so a derived id is one not given."""
    if args.local_remote_dir is not None:
        return
    refuse_an_owner_github_cannot_have("scaffold-org-too-long", args.org,
                                       "--org", ORG_REMEDIATION)
    refuse_an_owner_github_cannot_spell("scaffold-bad-org", args.org,
                                        "--org", ORG_SPELLING_REMEDIATION)
    if args.id is not None:
        named, remediation = "--id", PASSED_TOPIC_REMEDIATION
    else:
        named = f"--id (not given, so {ID_DERIVED_FROM})"
        remediation = DERIVED_TOPIC_REMEDIATION
    refuse_a_topic_github_cannot_set(
        "scaffold-topic-too-long", policy.topic_for(project_id), project_id,
        named, remediation)


#: How a refusal names an elector `_elector` did not get from `--elected-by`
#: (#282), so the sentence says where the value came from and not a flag
#: nobody typed: the words #255's `plan` uses for its own fallback.
ELECTOR_FROM_ENV = "--elected-by (not given, so GIT_AUTHOR_NAME)"
ELECTOR_FROM_CONFIG = "--elected-by (not given, so `git config user.name`)"

#: Where the scaffold writes each free-text value, for the sentence that
#: refuses one (#282). `--name` also goes into each repository's description
#: on GitHub, where `gh repo create` is asked.
ROOT_MANIFEST_AND_README = "the assembly root's `project.yaml` and `README.md`"
NAME_WRITTEN_INTO = (
    "the assembly root's `project.yaml` and `README.md`, each repository's "
    "`AGENTS.md` and each first commit's message")

#: How a `pin-source-unused` refusal's remediation begins (#451), and a
#: `pin-source-no-path` one's.
UNREAD_PIN_SOURCE_MADE = ("nothing was created, and `--dry-run` refuses the "
                          "same.")

#: What every `scaffold-unwritable-value` is told to do (#282).
UNWRITABLE_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. Pass "
    "each value named again, retyped; when `--elected-by` is not given, the "
    "scaffold reads GIT_AUTHOR_NAME, then `git config user.name`, so pass the "
    "flag or correct that. The manifest escapes what it records, but the "
    "README, each `AGENTS.md` and each commit message take the value as it "
    "stands, so it must be one line of UTF-8 text: a byte that is not UTF-8, "
    "or a lone surrogate, cannot be written at all; a line break or a control "
    "character would break or garble the line it is written into; and a "
    "bidirectional embedding, override or isolate control would show the rest "
    "of that line in another order than it is written. A byte that is not "
    "UTF-8 reaches a command line from a terminal or a script whose encoding "
    "is not the locale's.")


def _elector_named(args) -> str:
    """Where `_elector`'s answer came from, as a refusal names it (#282):
    `--elected-by`, else `ELECTOR_FROM_ENV` when GIT_AUTHOR_NAME holds more
    than whitespace, else `ELECTOR_FROM_CONFIG` -- `_elector`'s own order.
    A `--elected-by ''` is the flag's answer (#911)."""
    if args.elected_by is not None:
        return "--elected-by"
    if (os.environ.get("GIT_AUTHOR_NAME") or "").strip():
        return ELECTOR_FROM_ENV
    return ELECTOR_FROM_CONFIG


def _refuse_unwritable_values(fields) -> None:
    """Each `(what, value, where)` is text a file can hold, or this refuses
    as `scaffold-unwritable-value`, naming every one that is not (#282).

    `unwritable_reason` is the question `adopt-project.py` asks of the same
    values (#255), so the two tools refuse the same values in the same
    words: a lone surrogate (a byte that is not UTF-8, as `sys.argv` keeps
    one), a line break, a control character, a bidi embedding, override or
    isolate control. `double_quoted` spells each of them in `project.yaml`
    (#284), so the manifest reads back what was typed, but `README.md`, each
    `AGENTS.md` and each commit message take the value raw: a surrogate
    raised `UnicodeEncodeError` in `write_lf` after both legs were pushed
    (`--name`: after all three repositories were created), and a line break
    split the line it was written into, in the README and each `AGENTS.md`,
    each commit's subject, and the `manifest ok:` line `validate-manifest.py`
    prints.

    The value is spelled as Python spells it, so the sentence is one line of
    text whatever the value holds.
    """
    problems = []
    for what, value, where in fields:
        reason = unwritable_reason(value)
        if reason:
            problems.append(f"{what} is {value!r}, which the scaffold writes "
                            f"into {where}, and {reason}.")
    if problems:
        raise Refusal("scaffold-unwritable-value", " ".join(problems),
                      UNWRITABLE_REMEDIATION)


#: What a `scaffold-unwritable-value` for the clone URL is told to do (#433).
#: It is not `UNWRITABLE_REMEDIATION`, which says to retype a value: the path
#: is a directory, so the way out is another directory, or GitHub.
#:
#: THE URL IS THE PATH `--local-remote-dir` RESOLVES TO (#693), so one typed
#: as text can lead through a symbolic link to a directory whose name is not,
#: or be relative to one; told only to pass a path that is "one line of UTF-8
#: text", which it was, a person renames the link and is refused again, so
#: the remedy says where the fault is. And as `UNWRITABLE_REMEDIATION` says
#: (#282), a lone surrogate, which a Windows name can hold, cannot be
#: written either: the READMEs quote the URL for a shell (#693) and write
#: every character of it as itself but an apostrophe.
CLONE_URL_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Pass a --local-remote-dir whose path is one line of UTF-8 text with no "
    "control character in it, a directory renamed or made anew, and run "
    "again; or scaffold against GitHub, without --local-remote-dir, where "
    "the clone URL is `https://github.com/<org>/<name>.git`. The clone URL "
    "is the path --local-remote-dir resolves to, so where the path given is "
    "text and the URL named above is not, the fault is in what it leads "
    "through: a symbolic link on it whose target is not text, or, for a "
    "relative path, the directory it was given from. Rename or replace the "
    "directory whose name is not text, or pass a path that does not lead "
    "through it; renaming a link changes nothing. The READMEs print the "
    "clone URL in a `git clone` line, in quotes where a shell needs them, "
    "every character but an apostrophe written as itself: a byte that is "
    "not UTF-8 in the path (a directory named in a legacy code page), or a "
    "lone surrogate, cannot be written at all, a line break or a control "
    "character would break or garble the line it is written into, and a "
    "bidirectional embedding, override or isolate control would show the "
    "rest of that line in another order than it is written.")


def _refuse_an_unwritable_clone_url(local: bool, url: str) -> None:
    """Refuse the assembly root's clone URL when no file can hold it, before
    any remote exists, as `adopt-project.py` refuses its own (#255).

    Only a local one can be refused: under `--local-remote-dir` the URL is the
    bare repository's own path, which `templates/assembly-root/README.md`
    prints (`git clone --recurse-submodules {{CLONE_URL}}`) and each leg's
    `README.md` prints as `{{ASSEMBLY_CLONE_URL}}`; against GitHub it is
    `https://github.com/<org>/<name>.git`, ASCII by construction. A directory
    whose name is not UTF-8 reaches `sys.argv` as a string with a lone
    surrogate, and `write_lf` encodes strictly, so it raised
    `UnicodeEncodeError` in `_seed_legs` after all three bare repositories
    existed and the work directory was half made, while `--dry-run` exited 0
    and said nothing (#433). One bidi override or a line break in the path
    was written into the README raw.

    ONLY THE ASSEMBLY ROOT'S URL IS ASKED. It is the one URL `_scaffold`
    renders into a file; the legs' are `<dir>/<name>.git` beside it, so what
    makes one unwritable makes all three so, and the refusal names the one a
    README holds. `_refuse_unwritable_values` is not reused because its
    remediation tells a person to retype a value, and a directory is renamed
    or replaced, not retyped; the code and the question are the same, so the
    refusal is the same `scaffold-unwritable-value` for the same reasons
    (`unwritable_reason`).
    """
    if not local:
        return
    reason = unwritable_reason(url)
    if reason:
        raise Refusal(
            "scaffold-unwritable-value",
            "under --local-remote-dir the assembly root's clone URL is the "
            f"bare repository's own path, {url!r}, which the scaffold writes "
            "into the `README.md` of the assembly root and of each leg, and "
            f"{reason}.",
            CLONE_URL_REMEDIATION)


def referent_chain_links(raw: str, pins=()) -> tuple:
    """`--referent-chain`'s links: split on commas, each stripped, an empty
    one dropped. ONE reading, for `_declaration` and for the check below, so
    the links that are judged are the links that are recorded.

    A FIRST LINK THAT IS A `--pin` IS SPELLED AS THAT PIN (#909). The first
    link is matched to the `--pin` products, `pins`, by `pin_product_key`,
    the pin file's own fold (#444), so `open<U+212A KELVIN SIGN>dox` is the
    pin `openKdox`: `lower()` folds the Kelvin sign to `k`. It was recorded
    as typed, and the plan printed that spelling, beside one pin file,
    `contracts/openkdox-pin.yaml`. It is recorded in the `--pin`'s spelling
    now, and so is a first link differing from it by case alone. An owner
    typed before the name is kept: the manifest records the name alone."""
    # The fold `resolve_referent` matches the first link to a pin by.
    from repo_shape import pin_product_key
    links = tuple(link.strip() for link in raw.split(",") if link.strip())
    if not links:
        return links
    head, slash, first = links[0].rpartition("/")
    pinned = next((pin for pin in pins
                   if pin_product_key(pin) == pin_product_key(first)), None)
    return links if pinned is None else (head + slash + pinned, *links[1:])


def _refuse_malformed_chain_links(policy, chain: tuple) -> None:
    """Every link between the chain's first and last is a neutral product's
    name, or this refuses (#251).

    `naming_block` writes the chain into `project.yaml` as a plain flow
    sequence, `[openXdox, openDox]`, and nothing else looked at a MIDDLE
    link: `_chain_shape_problem` asks the length, a repeat, the first link and
    the last, and a link whose tree is not on the disk is declared-unverified,
    a warning. On main through 150c41d, `--referent-chain openXdox,a #b,openDox`
    created all three repositories, pushed both legs and exited 0 with a
    manifest the project's own `validate-manifest.py` refused as
    `yaml-unparsable` (the `#` began a comment), and `it's`, `a]b`, `null` and
    `007` were each recorded as a different chain than the one typed.

    THE NAMING POLICY ALREADY SAYS WHAT A LINK IS. Each link past the first is
    read out of the link before its `neutral_product_pins:`, so it is the
    name of a neutral product, and `CHAIN_LINK_FORM` is that family. A name of
    that form is one plain YAML word, so the manifest stays plain and reads
    back as typed. The link is judged at its basename, as `resolve_referent`
    reads it and `naming_block` records it.

    The FIRST and LAST links are left to the checks that already anchor them:
    the first must be a `--pin` product and the last the referent the name
    claims, both compared by `pin_product_key`, the pin file's own fold
    (#444), because a pin names WHICH product, not how it was typed. Each
    must fold to a name this run already holds (`[A-Za-z0-9_.-]`, or
    `open<Product>`), so neither can carry a `#`, a quote, a bracket, a comma
    or a space.

    Asked before `_declaration`, so before `gh api` reads a pin's tree and
    before `--dry-run` returns: a dry run refuses exactly as the real run
    does, and nothing has been created.

    The chain and each bad link are quoted with `repr`, as `--pin` and `--id`
    are in their refusals: a link is the operator's own argument, and one
    that holds a newline, a carriage return or an escape byte prints as
    `\\n`, `\\r` or `\\x1b`, so it cannot end the refusal's line and start
    another that reads as a refusal of its own.
    """
    malformed = [link for link in chain[1:-1]
                 if CHAIN_LINK_FORM not in {family for family, _role
                                            in policy.matches(
                                                repo_basename(link))}]
    if not malformed:
        return
    form = (policy.family(CHAIN_LINK_FORM) or {}).get("pattern", "")
    raise Refusal(
        "chain-link-malformed",
        f"--referent-chain {','.join(chain)!r}: "
        + ", ".join(repr(link) for link in malformed)
        + (" is not" if len(malformed) == 1 else " are not")
        + " the name of a neutral product. Every link between the first and "
        "the last is a product the link before it pins, and the manifest "
        "records each one as a name.",
        "Remediation: nothing was created. Spell each link between the first "
        "and the last as the neutral product's repository name, "
        f"`open<Product>` (the naming policy's `{form}`, e.g. openXdox). "
        "`validate-repository-naming.py --explain <link>` says which form a "
        "name is.")


def _declaration(args) -> tuple[dict, set, tuple, dict]:
    """(c) What the project DECLARES about itself: `(pins, declared_pins,
    chain, link_pins)`.

    Split out of `_scaffold` for #138. THE RECORDED CHAIN (2026-09-05):
    `codexDox` pins `openXdox` and reaches `openDox` through it; the chain is a
    DECLARATION, so it is checked by `_check_declared_names` below and written
    into the manifest rather than re-derived by every reader. A link is
    verified against its own tree when `SHAPE_PIN_SOURCE_<PRODUCT>` points
    at one, or `--pin-source` for the FIRST link alone (#441: it is the
    pinned product's checkout, never a later link's tree), and is
    declared-unverified otherwise — a warning, never a refusal, because the
    check is offline.

    A tree `--pin-source` reached whose declaration could not be read (a
    `neutral_product_pins:` that is not a list of names) is declared-unverified
    too, and the warning says that tree could not be READ, with why, rather
    than that it "is not reachable here" (#338): the scaffold prints no other
    line about a source, so `with_reasons` is asked for here.

    A tree that is not reachable is offered the sources THIS TOOL reads
    (`_link_remedies`, #610), never the naming validator's.
    """
    pins = declared_pin_values(args)
    declared_pins: set[str] = set(pins)
    chain = referent_chain_links(args.referent_chain, declared_pins)
    link_pins = link_pins_from_trees(
        chain, None, {}, args.pin_source, with_reasons=True,
        remedies=_link_remedies(chain)) if chain else {}
    return pins, declared_pins, chain, link_pins


def _check_referent_chain(policy, assembly_name: str, declared_pins: set,
                          chain: tuple, link_pins: dict) -> None:
    """(d) A declared `--referent-chain` reaches the referent the name claims,
    or this refuses. Split out of `_scaffold` for #138.
    """
    if not chain:
        return
    resolution = policy.resolve_referent(assembly_name, declared_pins,
                                         chain, link_pins)
    if resolution.status == "broken":
        raise Refusal(
            "chain-not-declared",
            f"--referent-chain {','.join(chain)}: {resolution.reason}",
            "Remediation: the first entry is the product this project "
            "PINS (pass it as --pin <product>@<40 hex>) and the last is "
            "the `open<Product>` the name claims; every link between them "
            "is declared by that link's own project.yaml.")
    for warning in resolution.warnings:
        print(f"WARNING {warning}", file=sys.stderr)


def _unclassified(name: str) -> Refusal:
    """`naming-unclassified`: `name` matches no form in the naming policy.
    One refusal, raised by `_check_one_name` and, for a passed `--id` the
    project's validators would not take, first by `_refuse_bad_id` (#911)."""
    return Refusal(
        "naming-unclassified",
        f"{name!r} matches no family in the naming policy. "
        f"`<Project>` is {PROJECT_NAME_RULE}.",
        "Remediation: re-run with a --project value of that form.",
    )


def _role_mismatch(name: str, found, role: str) -> Refusal:
    """`naming-role-mismatch`: `name` classifies as `found`, a form its
    `role` does not accept. Raised by `_check_one_name` and, for a passed
    `--id` that is no id, first by `_refuse_bad_id` (#911)."""
    return Refusal(
        "naming-role-mismatch",
        f"{name!r} classifies as {found[0]}"
        + (f"/{found[1]}" if found[1] else "")
        + f", not as the {role!r} form of a project leg"
        + f" ({found.reason})",
        "Remediation: re-run with a --project value that is one "
        "CamelCase token.",
    )


def _check_one_name(policy, name: str, role: str, declared_pins: set,
                    chain: tuple, link_pins: dict) -> None:
    """(e) ONE of the three names classifies as a form its role accepts, or
    this refuses. Split out of `_scaffold` for #138.
    """
    found = policy.classify(name, role, declared_pins,
                            chain if role == "assembly" else (), link_pins)
    if found is None:
        raise _unclassified(name)
    if not accepts_role(found, role):
        raise _role_mismatch(name, found, role)


def _check_declared_names(policy, names: dict, declared_pins: set,
                          chain: tuple, link_pins: dict) -> None:
    """(d+e) The chain, then each of the three names. Split out of `_scaffold`
    for #138; the chain is judged first because a broken one makes every
    classification under it meaningless.
    """
    _check_referent_chain(policy, names["assembly"], declared_pins, chain,
                          link_pins)
    for role, name in names.items():
        _check_one_name(policy, name, role, declared_pins, chain, link_pins)


def _shape_revision() -> tuple[str, str]:
    """(f) The shape revision this project is cut from: `(commit, tree)`.

    Split out of `_scaffold` for #138. A DIRTY checkout still scaffolds — the
    per-file sha256 rows are computed from the actual copies, so drift stays
    detectable — but it says so, loudly, because `commit:` and `tree_sha256`
    would then describe bytes nobody copied.

    WHETHER THE CHECKOUT IS DIRTY IS ASKED OF GIT'S BYTES (#423). Only
    whether `status --porcelain` printed anything is used, never what, so it
    is not decoded at all. With `core.quotePath=false` git prints a file name
    as the bytes it holds, and a name that is not UTF-8 (a checkout from a
    filesystem that stores one) made `git_out`'s strict decode raise
    `UnicodeDecodeError`: a traceback, exit 1, before a remote existed, where
    this means to print the warning below and go on.
    """
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    dirty = bool(git_out(["status", "--porcelain"], cwd=SHAPE_ROOT,
                         binary=True))
    if dirty:
        print(
            "WARNING the openRepoShape checkout is DIRTY. `commit:` and "
            f"`tree_sha256` in the shape pin will record {shape_commit[:12]}, "
            "which does NOT describe the bytes being copied. The per-file "
            "sha256 rows are computed from the actual copies, so drift stays "
            "detectable — but commit before scaffolding a real project.",
            file=sys.stderr,
        )
    return shape_commit, shape_tree


def _repository_urls(args, names: dict) -> tuple[bool, dict, dict]:
    """(g) The three repositories as the forge — or the disk — names them:
    `(local, repositories, urls)`.

    Split out of `_scaffold` for #138. `local` is `--local-remote-dir`, the
    TEST path: three bare repositories in a directory, and no network.
    """
    local = args.local_remote_dir is not None
    if local:
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
    else:
        urls = {role: f"https://github.com/{args.org}/{name}.git"
                for role, name in names.items()}
    repositories = {role: f"{args.org}/{name}" for role, name in names.items()}
    return local, repositories, urls


#: What the scaffold says before its plan where `--reuse-empty-repo` could not
#: read the root's visibility (#913, L2-96): `ROOT_VISIBILITY_UNREAD`'s leg
#: twin, said while `--visibility` can still choose what a leg it creates
#: is. The first is said with no `--visibility`, the second with one.
ROOT_UNREAD_LEGS_DEFAULT = (
    "NOTE this run could not read {root}'s visibility from GitHub, so a leg "
    "this run creates is created private, the default, and does not inherit "
    "{root}'s; a leg it reuses keeps its own. Pass --visibility to choose "
    "one before any leg exists; `gh repo view {root} --json visibility` "
    "says which {root} is.")
ROOT_UNREAD_LEGS_CHOSEN = (
    "NOTE this run could not read {root}'s visibility from GitHub, so it "
    "cannot say whether --visibility {visibility} agrees with it. A leg this "
    "run creates is created {visibility}, as you asked; a leg it reuses "
    "keeps its own. `gh repo view {root} --json visibility` says which "
    "{root} is.")


def _leg_visibility(args, assembly_repository: str,
                    local: bool) -> tuple[str, str | None]:
    """(h) The visibility a leg this run CREATES is created at: explicit, or
    inherited from a reused empty root; and the root's own, as GitHub gave
    it, or None.

    Split out of `_scaffold` for #138. An organisation that created the
    assembly root first (--reuse-empty-repo) generally wants the legs this
    run creates to match what it already is, not the tool's own idea of a
    default. Reading it costs one `gh repo view`, is skipped entirely for
    --local-remote-dir (a bare repository on disk has no visibility at all)
    and for a fresh scaffold with nothing to reuse.

    NEITHER LINE COUNTS THE LEGS (#542). Both are printed before the plan,
    under `--dry-run` too, and which legs this run reuses is asked only
    later, by `_reusable_remotes`. A re-run that reuses one leg creates one
    and one that reuses both creates none, so "the two new legs" was wrong
    there; each line now says what happens to a leg this run creates, and
    that a reused leg keeps its own visibility, which `_reused_leg_visibility`
    reads and warns about leg by leg.

    A ROOT IT COULD NOT READ IS SAID TO BE UNREAD, HERE (#913, L2-96). The
    legs it creates were made private with no word, `--dry-run` included,
    and only a real run's `_private_leg_note` said anything about the read.
    `ROOT_UNREAD_LEGS_DEFAULT` or `ROOT_UNREAD_LEGS_CHOSEN` is printed before
    the plan, so a person can pass `--visibility` before any leg exists. A
    root gh does not find is the ordinary run, which creates it: nothing is
    said of it.

    THE ROOT IS READ ONCE (#913, L2-96). `_create_remotes` asked GitHub again
    for a reused root, and the two reads could disagree; the second element
    of the answer is this read, the root's visibility where GitHub gave one,
    and `_create_remotes` takes it. It is None where nothing was read (no
    `--reuse-empty-repo`, or `--local-remote-dir`), where gh does not find
    the root, and where the read failed.
    """
    if not args.reuse_empty_repo or local:
        return args.visibility or "private", None
    seen = remote_visibility(assembly_repository)
    if seen is None:
        unread = (ROOT_UNREAD_LEGS_DEFAULT if args.visibility is None
                  else ROOT_UNREAD_LEGS_CHOSEN)
        print(unread.format(root=assembly_repository,
                            visibility=args.visibility))
    root = seen if seen in VISIBILITY_CHOICES else None
    if args.visibility is None:
        if root:
            print(f"NOTE {assembly_repository} is already {root} "
                  "on GitHub; a leg this run creates inherits that "
                  "visibility, and a leg it reuses keeps its own (pass "
                  "--visibility to choose one explicitly).")
        return root or "private", root
    if root and root != args.visibility:
        print(f"WARNING --visibility {args.visibility} disagrees with the "
              f"reused {assembly_repository}, which is {root} "
              "on GitHub. A leg this run creates is created "
              f"{args.visibility} because that is what you asked for, not "
              "because it is what the assembly root already is; a leg it "
              "reuses keeps its own.",
              file=sys.stderr)
    return args.visibility, root


def _print_plan(args, values: dict, names: dict, repositories: dict,
                urls: dict, local: bool, policy, declared_pins: set,
                chain: tuple, link_pins: dict, pins: dict) -> None:
    """(i) The plan a human reads before they type yes.

    Split out of `_scaffold` for #138, in three parts — this one, the declared
    classification and the actions — because the plan is the ONE output of
    this tool that somebody is asked to act on, and a printer that no longer
    fits on a screen is a printer nobody proof-reads.
    """
    print(f"project      {values['PROJECT_NAME']} ({values['PROJECT_ID']})   "
          f"topic {values['TOPIC']}")
    # THE TRIAD, OFFERED FIRST (openxFactory `prefer-triad-project-shape`,
    # ratified by Brett Heap on 2026-10-06). This tool has no
    # single-repository mode -- every run creates an assembly root and two
    # legs -- so the offer is the tool itself, and the plan a person reads
    # before typing yes names it as the preferred shape with the posture
    # beside it. Printed once, in a dry run and a real one alike; it changes
    # nothing this run does and no exit code.
    first, second = scaffold_lines()
    print(f"triad        {first}")
    print(f"             {second}")
    print(f"shape        {SHAPE_REPOSITORY} @ {values['SHAPE_COMMIT'][:12]} "
          f"(tree {values['SHAPE_TREE_SHA256'][:12]}…)")
    print(f"elected by   {values['ELECTED_BY']} on {values['ELECTED_ON']}")
    print(f"reference    {values['REFERENCE']}"
          + ("" if args.reference is not None
             else "   (chosen by the election date)"))
    for role in ("assembly", "spec", "code"):
        print(f"  {role:<9} {repositories[role]:<28} -> {urls[role]}")
    for role in ("assembly", "spec", "code"):
        note = descendant_note(policy, names[role], role, declared_pins,
                               chain if role == "assembly" else ())
        if note:
            print(note)
    print(f"legs mounted at {args.spec_path}/ and {args.code_path}/ inside "
          f"{names['assembly']}")
    for product, pin_values in pins.items():
        print(f"pin          {pin_values['PIN_REPOSITORY']} @ "
              f"{pin_values['PIN_COMMIT'][:12]} tree "
              f"{pin_values['PIN_TREE_SHA256'][:12]}… -> "
              f"{neutral_pin_path(product)} ({pin_values['PIN_DIGEST_SOURCE']})")
    _print_declared_classification(policy, names, declared_pins, chain,
                                   link_pins, pins)
    _print_plan_actions(args, values["TOPIC"], local)


def _print_declared_classification(policy, names: dict, declared_pins: set,
                                   chain: tuple, link_pins: dict,
                                   pins: dict) -> None:
    """(i′) What the naming policy makes of the assembly root's own name.

    PRINT THE CLASSIFICATION whenever the root is not an ordinary project-leg
    — a neutral-product or descendant root, pinned or not — so the human
    reading the plan before typing yes sees `neutral-product / assembly` even
    with no `--pin` on the command line (2026-09-05). A pinned root always
    printed this line; what is new is that `openDox` needs no pin to earn one.
    Split out of `_print_plan` for #138.
    """
    found = policy.classify(names["assembly"], "assembly", declared_pins,
                            chain, link_pins)
    if pins or found.family != "project-leg":
        print(f"declared     {names['assembly']} classifies as {found.family}"
              + (f" / {found.role}" if found.role else "")
              + f" — {found.reason}")


def _print_plan_actions(args, topic: str, local: bool) -> None:
    """(i″) The lines that say what this run will DO — create the remotes,
    reuse an empty root, the branch, push, set the topic. Split out of
    `_print_plan` for #138.

    THE BRANCH AND, ON DISK, THE VISIBILITY ARE NAMED (#913, AT-scaffold N3).
    The plan a person approves, here and in setup's step (5), named neither
    the tracking branch the three repositories are created on nor, under
    `--local-remote-dir`, the visibility the manifest records: against
    GitHub `gh repo create --<visibility>` names it, and a bare repository
    on disk has none. And "NOT FOUND" IS WHAT THIS TOKEN CAN SEE (#913,
    L2-61): only gh's not-found answer reads as absent (#609), and GitHub
    gives it for a private repository the token cannot see, so the real run
    would create the legs and then fail at `gh repo create` for a root that
    exists. gh's answer cannot tell the two apart, so the row says which
    repositories it creates in those words (`NOT_FOUND_WITH_THIS_TOKEN`).
    """
    if local:
        print(f"visibility   {args.visibility}, which project.yaml records; "
              "a bare repository on disk has none")
        print("remotes      bare repositories on disk (no network)")
    else:
        print(f"remotes      gh repo create --{args.visibility}, for each of "
              "the three gh does not find")
        for line in NOT_FOUND_WITH_THIS_TOKEN:
            print(f"             {line}")
    if args.reuse_empty_repo:
        print("reuse        each of the three that EXISTS with zero commits "
              "is used, and a leg whose one commit is this scaffold's seed")
    print(f"branch       {args.tracking_branch}, the tracking branch each of "
          "the three is created on")
    print("push         " + ("SKIPPED (--no-push)" if args.no_push else "yes"))
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))


#: The code of every folder this run makes and cannot (#609).
FOLDER_REFUSAL = "scaffold-folder-cannot-be-made"


def _refuse_existing_trees(work_root: Path, names: dict) -> None:
    """(j) Refuse to write over a working tree that already has something in
    it. Split out of `_scaffold` for #138.

    A FILE THERE IS REFUSED TOO (#609): `iterdir()` raised
    `NotADirectoryError` on one, a traceback after `--dry-run` had exited 0.
    `target_in_the_way` asks both, and makes nothing. A folder this user
    cannot write in (L2-60) or cannot list (#930) is told the permission and
    `--work-dir` by `target_remediation`, not this sentence about a live
    tree, which the run cannot see there.
    """
    for role, name in names.items():
        target = work_root / name
        why = target_in_the_way(target)
        if why:
            raise Refusal(
                "scaffold-target-exists",
                f"{shown_source(target)} already exists and {why}",
                target_remediation(
                    why,
                    "Remediation: choose an empty --work-dir. There is no "
                    "--force: re-running over a live tree is not a scaffold.",
                    "--work-dir"),
            )


def _refuse_unmakeable_folders(args, work_root: Path | None, names: dict,
                               local: bool) -> None:
    """(j′) Every folder this run makes, and each working tree it writes,
    asked before anything is made, by the dry run and the real run alike
    (#609): `--work-dir`, then the three trees in it, then
    `--local-remote-dir`, the order the real run makes them in.

    THE DRY RUN ASKED NONE OF IT. With a file where `--work-dir` or
    `--local-remote-dir` goes, or where a tree goes, `--dry-run` exited 0
    and the real run died in `mkdir` or `iterdir()` with a traceback. A
    folder that cannot be made, because a file stands at it or above it or
    this user cannot write where it goes, is `scaffold-folder-cannot-be-made`
    now, and the real run's own `mkdir` is `make_folder`, which refuses the
    same in the system's words. With no `--work-dir` the run makes a fresh
    temporary directory, which nothing stands in.
    """
    if work_root is not None:
        refuse_unmakeable_folder(FOLDER_REFUSAL, "--work-dir", work_root)
        _refuse_existing_trees(work_root, names)
    if local:
        refuse_unmakeable_folder(FOLDER_REFUSAL, "--local-remote-dir",
                                 args.local_remote_dir.resolve())


def _create_remotes(args, values: dict, repositories: dict, urls: dict,
                    local: bool, reused: dict,
                    root_seen: str | None) -> dict[str, str | None]:
    """(k) The three remotes, spec and code first so a failure costs the
    cheapest thing. Split out of `_scaffold` for #138.

    It takes no `names`: every line here addresses a repository by the
    `<org>/<name>` the forge knows it as, or by its clone URL, and the bare
    name is not one of the things it needs. A reused one (`reused`, from
    `_reusable_remotes`) is not created, and keeps the visibility it has.

    Returns each repository's visibility as it now stands, by role, for
    `_private_leg_note` (#542): the run's for one created here, and for a
    reused one what GitHub says of it, or None where GitHub does not say. A
    reused leg's is what `_reused_leg_visibility` read, with its WARNING.
    The reused ROOT's is `root_seen`, the one read `_leg_visibility` made
    before the plan and said what it found (#913, L2-96): it was read a
    second time here, and the two reads could disagree. It is None where
    GitHub did not say (#660): the run's `--visibility` is not the root's,
    so a public root whose read failed was given the Free-plan hint as
    private, and `_private_leg_note` says now that it could not be read.
    """
    display = values["PROJECT_NAME"]
    project_id = values["PROJECT_ID"]
    standing: dict[str, str | None] = {}
    print("\ncreating remotes")
    for role in ("spec", "code", "assembly"):
        standing[role] = args.visibility
        if role in reused:
            print(f"  reused {repositories[role]} (already there, "
                  + ("zero commits)" if reused[role] is None else
                     f"holding this scaffold's seed {reused[role][:12]})"))
            if not local and role == "assembly":
                standing[role] = root_seen
            elif not local:
                standing[role] = _reused_leg_visibility(args,
                                                        repositories[role])
            continue
        if local:
            run(["git", "init", "-q", "--bare", "-b", args.tracking_branch,
                 urls[role]])
            print(f"  bare  {urls[role]}")
        else:
            description = {
                "assembly": f"{display} — assembly root (project {project_id})",
                "spec": f"{display} — spec leg (project {project_id})",
                "code": f"{display} — code leg (project {project_id})",
            }[role]
            run(["gh", "repo", "create", repositories[role],
                 f"--{args.visibility}", "--description", description])
            print(f"  gh    {repositories[role]} ({args.visibility})")
    return standing


def _reused_leg_visibility(args, repository: str) -> str | None:
    """(k″) A reused leg keeps the visibility the run that created it gave it
    (#462), and a re-run whose visibility disagrees is told so, as
    `_leg_visibility` tells it about a reused root. Nothing here changes a
    repository's visibility. Never asked of a `--local-remote-dir` leg,
    which has none.

    Returns the visibility GitHub reports for the leg, which is the one
    `_private_leg_note` goes by (#542), or None when GitHub does not say
    (#913, L2-92): a read that failed, or gh not finding a leg it found a
    moment before. It returned the run's then, so the leg NOTE and the
    Free-plan hint went by a value GitHub did not give, hiding a true hint
    or printing a false NOTE, and nothing said the read failed; the root's
    rule since #660, for each leg.
    """
    seen = remote_visibility(repository)
    if seen not in VISIBILITY_CHOICES:
        return None
    if seen != args.visibility:
        print(f"WARNING {repository} is reused and is {seen} on GitHub, "
              f"where this run's visibility is {args.visibility}. It keeps "
              "the visibility it has: this run changes no repository's "
              "visibility.", file=sys.stderr)
    return seen


def _private_leg_note(args, repositories: dict, local: bool,
                      standing: dict) -> None:
    """(k′) A private or internal leg is unreadable to the `validate`
    workflow's default GITHUB_TOKEN — the defect on the first real adoption
    (MedxSoft/MedxEHR #7). Printed once, after both legs exist, rather than
    per-leg. Split out of `_scaffold` for #138.

    EACH LEG AS IT STANDS (#542). `standing` is each repository's visibility
    from `_create_remotes`: the run's for one it created, GitHub's for one it
    reused. The note went by the run's visibility alone, so a re-run that
    reused a public leg under a private run called that leg private beside
    the WARNING that it is reused and is public, and a public run that
    reused private legs said nothing about them. It names each leg that is
    private or internal, at its own visibility, and is not printed when
    both are public. Two legs at one visibility read as they always did.

    THE FREE-PLAN HINT GOES BY THE ROOT (#542). The `validate` workflow runs
    in the assembly root, and it is there that an organisation secret is not
    delivered to a private repository on the Free plan. So the hint is
    printed only when the root, as it stands, is private or internal: a
    public root, new or reused, receives the organisation's secrets, and a
    hint that they "resolve to EMPTY" is false of it however private a leg
    is. The per-leg NOTE above stays, since a public root still needs a
    credential to read a private leg. AND IT NAMES THE ROOT (#602): it said
    the closed legs were private, so a public run over a reused private root
    was told the secrets resolve to EMPTY because a leg is private, when the
    reason is that the root is. `adopt-project.py` goes by its root the same
    way.

    WHAT GITHUB DOES NOT SAY IS SAID (#660), by `free_plan_secrets_note`,
    which adopt and `family.py` ask too: a reused root whose visibility could
    not be read (`standing` None) is `ROOT_VISIBILITY_UNREAD`, where it took
    the run's `--visibility`, and a closed root whose organisation's plan
    could not be read is `FREE_PLAN_UNREAD`, where it was silent as for a
    paid plan.

    AND A REUSED LEG IT COULD NOT READ (#913, L2-92), `standing` None, is
    named by `_unread_legs_note`, where it was taken at the run's
    visibility: a public leg under a private run was called private, and a
    private one under a public run got no NOTE. The legs it could read are
    named as before, and the Free-plan note follows either NOTE, since an
    unread leg may be closed.
    """
    if local:
        return
    closed = [role for role in ("spec", "code")
              if standing[role] in ("private", "internal")]
    unread = [role for role in ("spec", "code") if standing[role] is None]
    if closed:
        both = len(closed) == 2
        who = " and ".join(repositories[role] for role in closed)
        are = "are" if both else "is"
        stated = (f"{repositories['spec']} is {standing['spec']} and "
                  f"{repositories['code']} is {standing['code']}"
                  if both and standing["spec"] != standing["code"]
                  else f"{who} {are} {standing[closed[0]]}")
        them, which = ("them", "the legs") if both else ("it", "that leg")
        print(f"NOTE {stated}: give {repositories['assembly']} a way to "
              f"read {them} — a GitHub App (SHAPE_LEGS_APP_ID + "
              "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
              f"PAT (contents:read on {which}, fallback) — or the `validate` "
              f"check cannot check {them} out.")
    if unread:
        print(_unread_legs_note(repositories, unread))
    if closed or unread:
        note = free_plan_secrets_note(args.org, repositories["assembly"],
                                      standing["assembly"])
        if note:
            print(note)


def _unread_legs_note(repositories: dict, unread: list) -> str:
    """(k‴) The NOTE for each reused leg whose visibility GitHub did not give
    (#913, L2-92), as `ROOT_VISIBILITY_UNREAD` names a root: the question
    that went unanswered, what the answer would mean, and the command that
    answers it. `unread` is the roles, `spec` before `code`."""
    root = repositories["assembly"]
    legs = [repositories[role] for role in unread]
    if len(legs) == 1:
        whose, them = f"{legs[0]}'s visibility", "it"
        who, which = "if it is", "that leg"
        asks = f"`gh repo view {legs[0]} --json visibility` says which it is."
    else:
        whose, them = f"the visibility of {legs[0]} and {legs[1]}", "them"
        who, which = "for each that is", "the legs"
        asks = (f"`gh repo view {legs[0]} --json visibility` and `gh repo "
                f"view {legs[1]} --json visibility` say which each is.")
    return (f"NOTE this run could not read {whose} from GitHub, so it cannot "
            f"say whether {root} needs a way to read {them}: {who} private "
            f"or internal, give {root} a GitHub App (SHAPE_LEGS_APP_ID + "
            "SHAPE_LEGS_APP_PRIVATE_KEY, preferred) or a SHAPE_LEGS_TOKEN "
            f"PAT (contents:read on {which}, fallback), or the `validate` "
            f"check cannot check {them} out. {asks}")


def _take_held_seed(work: Path, url: str, seed: str, tracking: str) -> str:
    """(l′) A leg whose remote already holds this scaffold's seed (#462): the
    work clone, its files just written, is put AT that commit rather than
    given a new one.

    A new commit would carry the same tree under another name, and pushing
    it over the seed would be the rewrite a reuse never makes. So the commit
    `_reusable_remotes` found is fetched, by name and alone, and the
    tracking branch and the index are set to it; its tree is the one
    `seed_tree` built from these values, which is what was just written. The
    pin, the gitlink and the push that follows are then about the commit the
    remote already has, and that push changes nothing where the tracking
    branch already holds it. The fetch reaches the remote, so it runs under
    `REMOTE_ENV`, the prompt rule every such command runs under (#915).
    """
    run(["git", "init", "-q", "-b", tracking, str(work)])
    run(["git", "remote", "add", "origin", url], cwd=work)
    run(["git", "fetch", "-q", "origin", seed], cwd=work, env=REMOTE_ENV)
    run(["git", "reset", "-q", seed], cwd=work)
    return seed


#: What git says when a push needed a login it could not get (#915). Every
#: push runs under `REMOTE_ENV`, so where git would have asked the terminal
#: for a username or a password it dies `could not read Username for
#: '<url>': terminal prompts disabled`, or `Password` where the URL names
#: the user; a credential helper with nothing stored for the host is asked
#: first and answers nothing. These are git's own words, untranslated in
#: any locale: gettext translates only the `fatal: ` before them (git 2.43,
#: asked under a catalogue that translates each of these words). So they are
#: found in any locale; each push runs under `LC_ALL=C` all the same
#: (`PUSH_ENV`), for the words of `LOGIN_REFUSED`, which git translates.
NO_LOGIN = ("terminal prompts disabled", "could not read Username",
            "could not read Password")

#: What git says when it sent a login and the host refused it (#993): `fatal:
#: Authentication failed for '<url>'`, where a token a credential helper
#: holds for the host is wrong, expired or revoked. Its own case, and not one
#: of `NO_LOGIN`: git had a login, so "could not get one" is untrue of it.
#: git translates these words (git 2.43, asked under a catalogue that
#: translates them), which is why each push runs under `PUSH_ENV`. git also
#: asks its helpers to forget the refused login (a `store` file's line for
#: it is gone after it, measured), so a re-run before it is replaced is
#: refused as `NO_LOGIN`, with the same exit.
LOGIN_REFUSED = ("Authentication failed for ",)

#: What ssh says when the host took no key of the person's (#993):
#: `<user>@<host>: Permission denied (publickey).`, the line before git's
#: generic one (`GENERIC_FATAL`), where a `url.<base>.insteadOf` or
#: `url.<base>.pushInsteadOf` rule sends a push over ssh. OpenSSH's own
#: words, which it does not translate; a host offering more ways to log in
#: than a key lists them after `publickey`, so the list is read up to it.
KEY_REFUSED = ("Permission denied (publickey",)


def _login_remedy(output: str, repo: str, reused: bool) -> str:
    """How to give git the login a refused push lacked, then the re-run
    (#915, #993), or "" where `output`, git's for that push, shows no login
    trouble. Printed before `RULESET_HINT`, whose one exit is the same
    re-run. A login git could not get (`NO_LOGIN`), one it sent and the host
    refused (`LOGIN_REFUSED`) and a key ssh was refused (`KEY_REFUSED`) each
    fail a first scaffold's push and leave the three repositories empty, and
    the re-run is refused the same way until git has a login the host takes,
    so the hint alone named an exit that could not finish (RV971, #993).

    On GitHub git logs in over https with the login `gh auth setup-git`
    gives it or a token a credential helper holds, and over ssh with a key
    (`SSH_KEY_CLAUSE`). `gh auth setup-git` writes an empty helper before its
    own for `https://github.com`, which empties the list git has read so
    far, so a stale helper named before it is no longer asked, and one named
    after it is asked only when `gh`'s answers nothing
    (`setup-project.py`'s `_credential_helper_configured` reads it so). So
    it replaces a refused login too. Over ssh it changes nothing, so a key
    ssh was refused is told the ssh check alone (`SSH_KEY_CHECK`). A run
    that was itself the re-run (`reused`) is re-run as it was."""
    if any(words in output for words in NO_LOGIN):
        fix = (f"git could not get a login for {repo}: every push this "
               "scaffold makes runs with git's terminal prompt off, so where "
               "git would have asked you for one the push is refused, and a "
               "credential helper with nothing stored for the host answers "
               "nothing. Give git a login first (on GitHub, `gh auth "
               "setup-git` gives git the login `gh` has, or store a token for "
               "the host in your credential helper; " + SSH_KEY_CLAUSE + ")")
    elif any(words in output for words in LOGIN_REFUSED):
        fix = (f"the host refused the login git sent for {repo}: git had "
               "one, from your credential helper for one, and it is wrong, "
               "expired or revoked, so a re-run is refused too until git has "
               "one the host takes. Replace it first (on GitHub, `gh auth "
               "setup-git` makes git use the login `gh` has instead, or "
               "store a new token for the host in your credential helper; "
               + SSH_KEY_CLAUSE + ")")
    elif any(words in output for words in KEY_REFUSED):
        fix = (f"GitHub took no ssh key of yours for the push to {repo}: a "
               "`url.<base>.insteadOf` or `url.<base>.pushInsteadOf` rule in "
               "your git config sends it over ssh, where git logs in with an "
               "ssh key and not with the login `gh` has, so `gh auth "
               "setup-git` changes nothing for it. Give GitHub a key it takes "
               "first (" + SSH_KEY_CHECK + ")")
    else:
        return ""
    again = ("the same command with a new --work-dir or none" if reused else
             "the same command with --reuse-empty-repo added (after `--` "
             "through setup.sh) and a new --work-dir or none")
    return (f"\nRemediation: {fix}, then re-run {again}: it reuses the "
            "repositories this run left empty, and a leg whose one commit is "
            "the seed this scaffold pushes.")


def _refused_push(failed: CommandFailed, what: str, repo: str,
                  tracking: str, reused: bool) -> None:
    """What a refused push prints, a leg's and the root's (#462, #915,
    #993): the command and git's output, then, where it shows git could not
    get a login, the host refused the one git sent, or ssh was refused the
    key, how to give git one and the re-run (`_login_remedy`), then
    `RULESET_HINT` for `repo` and `tracking`. Any other refusal, a ruleset's
    above all, and an HTTP 403 too, prints what it always printed."""
    print(failed.loudly(what), file=sys.stderr)
    remedy = _login_remedy(failed.output, repo, reused)
    if remedy:
        print(remedy, file=sys.stderr)
    print(RULESET_HINT.format(repo=repo, tracking=tracking), file=sys.stderr)


def _seed_legs(args, values: dict, names: dict, repositories: dict,
               urls: dict, work_root: Path, reused: dict) -> dict | None:
    """(l) The two legs: template, one commit, push.

    Returns the four template values the assembly root's own templates name —
    or None when a push was REFUSED, having already said so on stderr
    (`_refused_push`). Split out of `_scaffold` for #138. A leg
    `reused` maps to its seed is put at that commit (`_take_held_seed`).
    """
    display = values["PROJECT_NAME"]
    shape_commit = values["SHAPE_COMMIT"]
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role, template in LEG_TEMPLATES.items():
        work = work_root / names[role]
        written = copy_tree(SHAPE_ROOT / "templates" / template, work, values)
        if reused.get(role):
            commit = _take_held_seed(work, urls[role], reused[role],
                                     args.tracking_branch)
        else:
            commit = git_init_commit(
                work, f"Seed the {role} leg of {display}\n\n"
                      f"Scaffolded from {SHAPE_REPOSITORY} @ {shape_commit}.",
                args.tracking_branch, written)
            run(["git", "remote", "add", "origin", urls[role]], cwd=work)
        leg_commits[role] = commit.lower()
        leg_digests[role] = tree_digest(work, commit)
        if not args.no_push:
            try:
                # THE BRANCH BY ITS FULL REFNAME (#421). A bare `<branch>`
                # is a REFSPEC, and a leading `+` in a refspec means FORCE:
                # `--tracking-branch +x`, a name `git check-ref-format
                # --branch` accepts and `git init -b` creates, was read as
                # the forced push of a local branch `x` and died `src refspec
                # x does not match any`, after all three remotes existed.
                # `HEAD:refs/heads/<branch>` names both sides in full, so
                # every name git accepts is pushed as the branch it is, and
                # `-u` still records `origin/<branch>` as its upstream.
                # `adopt-project.py` pushes `HEAD:refs/heads/<branch>` too.
                # Under `PUSH_ENV`, the prompt rule (#915), a first run's
                # and a re-run's: a reuse re-run whose legs are empty asks
                # `only_commit` nothing, and this push waited at git's
                # `Username for '...':` prompt. A login git cannot get, or
                # one the host refused, is named by `_refused_push`, which
                # reads git's words untranslated (#993).
                run(["git", "push", "-q", "-u", "origin",
                     f"HEAD:refs/heads/{args.tracking_branch}"], cwd=work,
                    env=PUSH_ENV)
            except CommandFailed as exc:
                _refused_push(exc, f"pushing the {role} leg",
                              repositories[role], args.tracking_branch,
                              args.reuse_empty_repo)
                return None
        print(f"  {role:<9} {commit[:12]} tree {leg_digests[role][:12]}… "
              f"-> {urls[role]}")
    return {
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    }


def _build_assembly_root(args, values: dict, names: dict, repositories: dict,
                         urls: dict, pins: dict, work_root: Path) -> bool:
    """(m) The assembly root: manifest, the two legs mounted, three pins.

    Returns False when the push was REFUSED, having already said so on stderr
    (`_refused_push`). Split out of `_scaffold` for #138.
    """
    display = values["PROJECT_NAME"]
    shape_commit = values["SHAPE_COMMIT"]
    assembly = work_root / names["assembly"]
    assembly.mkdir(parents=True, exist_ok=True)
    # ONE materializer, shared with `adopt-project.py`. The scaffold builds
    # into a directory it made itself, so a collision here is a defect and
    # `collision_dir=None` says so by raising.
    materialized = materialize_assembly_root(SHAPE_ROOT, assembly, values,
                                             neutral_pins=pins)

    # NO TEMPLATE (#229). `git init` copies the operator's template
    # (`init.templateDir`, or `GIT_TEMPLATE_DIR`) into `.git`, and one that
    # holds a `modules/<leg path>` store, as a copy of a working Triad root's
    # `.git` does, plants `.git/modules/<leg path>`. `git submodule add
    # --force` below REACTIVATES a store that is already there ("Reactivating
    # local git directory") where it would refuse without `--force`, so the
    # mount took the STRANGER's store: exit 0, a pushed root whose gitlink is
    # that store's commit and not the leg's tip, and a recursive clone that
    # fails. The empty `--template=` is git's documented way to use none. The
    # root is a build directory this tool fills and pushes, so no template
    # content belongs in it, and whoever clones the pushed root still gets
    # their template from `git clone`.
    run(["git", "init", "-q", "--template=", "-b", args.tracking_branch,
         str(assembly)])
    # `git submodule add` from the LEG WORKING TREE, then the recorded URL is
    # rewritten to the canonical remote: this way the scaffold never depends on
    # a push having propagated, and `--no-push` produces the same tree.
    for role, path in (("spec", args.spec_path), ("code", args.code_path)):
        # `--force`, git's documented way past an ignore rule (git's flag, not
        # one of this tool's: it still has none), for the reason
        # `stage_written` forces what the materializer wrote (#175). The root
        # is a fresh `git init` the materializer has just filled, so two sets
        # of rules reach the MOUNT PATH: the shape's own `.gitignore`, copied
        # into the root (`__pycache__/`, `*.py[cod]`, `.venv/`, `.DS_Store`),
        # and the operator's own excludes. A path either matches (`__pycache__`
        # as `--code-path`, or the DEFAULT `spec` under a global
        # `core.excludesFile` that names it) was refused HERE, after
        # `_create_remotes` and `_seed_legs` had made all three repositories
        # and pushed both legs: three repositories and no project, a corrected
        # re-run met `scaffold-remote-exists`, and `--dry-run`, which asks no
        # ignore rule anything, had planned it (#229; #174 and #200 for the
        # same cure in `adopt-project.py`). A gitlink once added is TRACKED,
        # so no rule touches it again.
        # Besides the ignore rule, `--force` changes three things in git 2.43,
        # and none can arise here, so there is no guard like adopt's
        # `_refuse_an_unmountable_path`:
        #   - a `.git/modules/<path>` already there is REACTIVATED instead of
        #     refused. `_refuse_existing_trees` refuses a
        #     `<work-dir>/<assembly>` that is not empty, so no `.git` was
        #     there when the run began, and the root is `git init`ed with no
        #     template (above), so `.git/modules` holds nothing before the
        #     first mount and only that mount's store at the second.
        #   - a GITLINK the index already holds at the path is accepted
        #     instead of refused, and a repository already checked out there
        #     is REUSED instead of the leg cloned. (A regular file or a
        #     tracked directory there is refused either way.)
        #     When the second mount runs, the index holds `.gitmodules` and
        #     the first gitlink and nothing else (the materialized files are
        #     staged after both, `stage_written`). No leg path can be
        #     `.gitmodules`, which `refuse_bad_leg_paths` refuses (#201), and
        #     the two paths are different and not nested, whatever the case
        #     (#169, #179), so the second add meets neither.
        #   - git's early dry run of the path is skipped. That dry run is what
        #     refuses a path beyond a symlink or inside a submodule before
        #     anything is cloned. With `--force` git still refuses both, but
        #     later: a path beyond a symlink only at the last step, after the
        #     leg has been cloned into the link's target. The materializer
        #     writes only regular files, and a mount inside the other is the
        #     nesting that was just refused.
        # A leg AT a path the shape wrote (`contracts`, `project.yaml`) is a
        # collision of another kind: refused up front by the collision check
        # where there is one, and by git at the mount where there is not.
        # `--force` changes neither.
        run(["git", "-c", "protocol.file.allow=always", "submodule", "add",
             "--force", "-q", str(work_root / names[role]), path],
            cwd=assembly)
        run(["git", "config", "-f", ".gitmodules", f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)
    # Every file the materializer wrote is FORCED past the operator's own
    # excludes (#175); see `stage_written`.
    stage_written(assembly, materialized.written)
    env_commit(assembly,
               f"Scaffold {display}: manifest, two legs, three pins\n\n"
               f"Shape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               f"spec {values['SPEC_COMMIT']}\ncode {values['CODE_COMMIT']}")
    run(["git", "remote", "add", "origin", urls["assembly"]], cwd=assembly)
    if not args.no_push:
        try:
            # By full refname, as the legs are pushed (`_seed_legs`, #421): a
            # bare `+x` is a forced refspec, not the branch named `+x`. And
            # under `PUSH_ENV`, as they are (#915, #993).
            run(["git", "push", "-q", "-u", "origin",
                 f"HEAD:refs/heads/{args.tracking_branch}"], cwd=assembly,
                env=PUSH_ENV)
        except CommandFailed as exc:
            _refused_push(exc, "pushing the assembly root",
                          repositories["assembly"], args.tracking_branch,
                          args.reuse_empty_repo)
            return False
    print(f"  assembly  {run(['git', 'rev-parse', 'HEAD'], cwd=assembly)[:12]} "
          f"-> {urls['assembly']}")
    return True


def _set_topics(repositories: dict, topic: str, local: bool) -> None:
    """(n) The `xf-project-<id>` topic, on all three. Skipped entirely for
    `--local-remote-dir`: a bare repository on disk has no topics. Split out
    of `_scaffold` for #138.
    """
    if local:
        return
    for role in ("assembly", "spec", "code"):
        run(["gh", "repo", "edit", repositories[role], "--add-topic", topic])
    print(f"  topic     {topic} set on all three")


def _neutral_product_pins(products) -> str:
    """`NEUTRAL_PRODUCT_PINS`, the manifest's list of the products `--pin`
    declares: `[]`, or one `  - <product>` line for each, in the order the
    pins were given, each spelled so that the project's own reader reads it
    back as the text given (#516).

    WRITTEN BARE, `  - 007` WAS THE NUMBER 7. `--pin 007@<commit>` scaffolded
    and exited 0, and the root's own reader took the manifest's bare `007`
    for 7, and `2026` and `1.5` for numbers, so its `validate-pins.py`
    refused the entry as `neutral-pin-entry-malformed` and the project's
    first CI run was red. `adopt-project.py execute` wrote the same line
    (#514). The list is a block placeholder, so `render` writes it as it
    stands, and nothing else quotes it.

    EACH ENTRY IS `shape_materialize.neutral_pin_entry`'s, the one function
    `adopt-project.py execute` calls too (#924). The scaffold spelled its
    own, bare wherever the reader read it back, so `0x1F`, `1_000`, `1e3`,
    `3dGlass` and `-x` were bare here and double-quoted in an adopted root.
    """
    if not products:
        return "[]"
    return "\n" + "\n".join(f"  - {_neutral_pin_entry(product)}"
                            for product in products)


def _scaffold(args) -> int:
    """The whole act, as the phases above, in the order they must happen.

    NOTHING IS CREATED until every name has been judged and the plan has been
    printed, which is what makes `--dry-run` an honest rehearsal: the refusals
    a real run would raise are raised by a dry run too.
    """
    # VALIDATED BEFORE ANYTHING IS BUILT FROM THEM. These five reach a `git`
    # or `gh` command line, and `checked_value` refuses a leading `-` because
    # git reads its own arguments. The naming policy checks what a project
    # name MEANS a few lines below; this checks what it may CONTAIN.
    project = checked_value("--project", args.project)
    args.tracking_branch = checked_value("--tracking-branch",
                                         args.tracking_branch)
    # The leg paths are asked the ONE question `adopt-project.py` asks of its
    # own -- canonical, mountable, two different places, then the alphabet
    # `checked_value` allows -- BEFORE `checked_value` is asked alone, because
    # it lets `spec/` through: Git records that mount at `spec` while the
    # `.gitmodules` write in `_build_assembly_root` names a second section,
    # `spec/`, so the project's recursive clone fails once this work
    # directory is gone (#179). Asked first, the answer for `legs\spec` is the
    # spelling to retype, where the alphabet check alone would only say no.
    # Refused before a work directory or a remote exists, and by `--dry-run`.
    spec_leg = ("--spec-path", args.spec_path)
    code_leg = ("--code-path", args.code_path)
    refuse_bad_leg_paths("scaffold-bad-leg-path", spec_leg, code_leg)
    args.spec_path = checked_value(*spec_leg)
    args.code_path = checked_value(*code_leg)
    args.org = checked_value("--org", args.org)
    args.pin_owner = checked_value("--pin-owner", args.pin_owner)
    # A FOLDER FLAG THAT NAMES NO PATH, `''` (#972's review, S2), which as a
    # `Path` is the directory this runs in, as `--pin-source ''` is just
    # below: read as `.` it built the trees there, or made the bare
    # repositories there, without a word. Asked before anything reads them.
    args.work_dir = folder_flag_path(
        args.work_dir, "--work-dir", "work-dir-no-path",
        names="the folder the working trees are built in",
        absent="they are built in a temporary directory")
    args.local_remote_dir = folder_flag_path(
        args.local_remote_dir, "--local-remote-dir",
        "local-remote-dir-no-path",
        names="the folder the bare repositories are made in",
        absent="they are created on GitHub")
    # A `--pin-source` THAT NAMES NO PATH, `''`, which as a `Path` is the
    # directory this runs in, and then one NOTHING WILL READ (#451): no
    # `--pin` reads a digest there and no `--referent-chain` link a
    # declaration. Asked of the flags as typed, with no process started, so
    # a dry run refuses them too.
    args.pin_source = pin_source_path(args.pin_source,
                                      nothing_made=UNREAD_PIN_SOURCE_MADE)
    refuse_an_unread_pin_source(args.pin_source, args.pin,
                                referent_chain_links(args.referent_chain),
                                nothing_made=UNREAD_PIN_SOURCE_MADE)
    # EACH `--pin`'S FILE AGAINST THE SHAPE'S OWN AND AGAINST EACH OTHER, from
    # the arguments as typed (#241), and first: the leg-path question below
    # asks about every pin's file, and would miscount one written over the
    # shape's or listed twice. Here for the reasons the leg paths are, so a
    # dry run refuses it too and no process has been started.
    _refuse_colliding_pins(args.pin, args.pin_owner)
    # THE LEG PATHS AGAINST THE SHAPE'S OWN, before anything else runs
    # (#197): `_identity` may read git's config, `_declaration` asks `gh api`
    # for a `--pin` with no `--pin-source`, `_leg_visibility` asks `gh repo
    # view` about a reused root, and `--dry-run` returns only after all of
    # them. Refused here, a dry run refuses exactly as the real run would,
    # and no process has been started. Each `--pin`'s file is among the
    # shape's paths, its product read off the argument by `parse_pin` alone.
    _refuse_colliding_leg_paths(args.spec_path, args.code_path,
                                declared_pin_products(args))
    project_id, display, elected_on, reference, elected_by = _identity(
        args, project)

    names = {"assembly": project, "spec": f"{project}-spec",
             "code": f"{project}-code"}
    # Each name is a directory's too, in the work directory and, under
    # `--local-remote-dir`, as a bare `<name>.git` (#261): a `--project` of
    # 247 to 250 characters died in `Path.exists` with a traceback, and one
    # of 251 or more in the work directory, where adopt's `check` refused it.
    # And without it, each is a GitHub repository's, which GitHub keeps to
    # 100 characters: a `--project` of 96 to 250 planned and met GitHub's
    # refusal at the first `gh repo create` (#838).
    on_disk = args.local_remote_dir is not None
    refuse_unstorable_names(
        "scaffold-name-too-long", list(names.values()),
        list(names.values()) if on_disk else [],
        [] if on_disk else list(names.values()))
    # THE CLONE URL IS A PATH A FILE WILL HOLD (#433): under
    # `--local-remote-dir` it is the bare repository's own path, which the
    # READMEs print, so it is asked here, as the free-text values are asked
    # in `_identity` (#282), before `_declaration` runs `gh api` and before
    # a work directory or a remote exists, and `--dry-run` refuses alike.
    local, repositories, urls = _repository_urls(args, names)
    _refuse_an_unwritable_clone_url(local, urls["assembly"])
    policy = NamingPolicy.load(SHAPE_ROOT / "contracts" / "repository-naming.yaml")
    _refuse_bad_id(project_id, args.id, policy, project)
    # AND THE ALPHABET A COMMAND LINE'S VALUE IS HELD TO, after the id's own
    # rule (#911), so `--id ''` is named for the id it is not; this still
    # refuses what `PROJECT_ID_RE.match` lets through, a trailing line break.
    project_id = checked_value("--id", project_id)
    _refuse_what_github_cannot_hold(args, project_id, policy)
    # WHAT THE PROJECT DECLARES ABOUT ITSELF, before any name is judged.
    # With no `--pin`, a descendant-form name is a claim with no referent and
    # the DECLARED ROLE wins. With `--pin openGlass@<sha>`, `MedxGlass` IS a
    # descendant — and, since 2026-09-02, may still be the assembly root that
    # carries the two legs. Since 2026-09-05 an `open<Product>` MAY be that
    # root too: a neutral product may ELECT the shape (Brett Heap, "elect the
    # shape for both, follow the pin chain, no family yet"), and because
    # electing confers nothing, `openDox` mounting `openDox-spec` and
    # `openDox-code` is a fact about layout rather than a claim about
    # neutrality. The form still wins the classification — the manifest records
    # `form: neutral-product, role: assembly` with the leg form in
    # `also_matches` — so nothing here reads a neutral product as a leg.
    #
    # What is still refused is a real mismatch: a `-spec` name offered as the
    # assembly root; an `<X>-Install`, which carries a hyphen and therefore
    # satisfies no leg form at all, offered as ANY leg; and either of the two
    # CamelCase forms offered as the `spec` or `code` leg, because those names
    # carry the lowercase suffix and are ordinary project legs.
    #
    # A chain's middle links are NAMES, judged before `_declaration` asks
    # `gh api` or git for any pin's tree (#251).
    _refuse_malformed_chain_links(policy,
                                  referent_chain_links(args.referent_chain))
    pins, declared_pins, chain, link_pins = _declaration(args)
    _check_declared_names(policy, names, declared_pins, chain, link_pins)
    topic = policy.topic_for(project_id)
    # THE BRANCH, ASKED OF GIT (#283). `checked_value`'s alphabet is wider
    # than the names git accepts as a branch (`~`, `a..b`, `x.lock`, `a/`),
    # and nothing asked git, so `--dry-run` printed a plan and, against
    # GitHub, `gh repo create` had made all three repositories before the
    # first `git init -b` died. Asked here a dry run refuses it as the real
    # run would, before a work directory or a remote exists.
    #
    # HERE, AFTER `_declaration`, AND NOT BESIDE THE ALPHABET CHECK AT THE
    # TOP: the refusals that come before `_identity` and `_declaration` start
    # no process, and three test files hold that, each with a control that
    # the first process is `git config user.name` or `_declaration`'s
    # (`test_scaffold_pin_collisions`, `..._leg_path_collisions`,
    # `..._referent_chain_links`). This one has to ask `git`. It still comes
    # before `_shape_revision`, the work directory and every remote, so
    # nothing exists when it refuses.
    refuse_bad_branch("scaffold-bad-tracking-branch", "--tracking-branch",
                      args.tracking_branch)

    shape_commit, shape_tree = _shape_revision()
    args.visibility, root_seen = _leg_visibility(
        args, repositories["assembly"], local)

    values = {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": display,
        "ORG": args.org,
        "TOPIC": topic,
        "VISIBILITY": args.visibility,
        "REFERENCE": reference,
        "ELECTED_BY": elected_by,
        "ELECTED_ON": elected_on,
        "TRACKING_BRANCH": args.tracking_branch,
        "SPEC_PATH": args.spec_path,
        "CODE_PATH": args.code_path,
        "ASSEMBLY_REPOSITORY": repositories["assembly"],
        "SPEC_REPOSITORY": repositories["spec"],
        "CODE_REPOSITORY": repositories["code"],
        "SHAPE_REPOSITORY": SHAPE_REPOSITORY,
        "SHAPE_COMMIT": shape_commit,
        "SHAPE_TREE_SHA256": shape_tree,
        "DIGEST_DEFINITION": TREE_DIGEST_DEFINITION,
        # ONE WORD OF A COMMAND A PERSON PASTES (#693): every README prints
        # it in `git clone --recurse-submodules <url>`, and under
        # `--local-remote-dir` it is a path, which was rendered raw, so one
        # under `a b/` split the line when pasted. POSIX quoting whatever the
        # host, as `_next_steps_clone` prints it (#532): a README is a
        # committed file read on every OS. A GitHub URL is left bare.
        "CLONE_URL": shell_quoted(urls["assembly"], "posix"),
        "ASSEMBLY_CLONE_URL": shell_quoted(urls["assembly"], "posix"),
        "NEUTRAL_PRODUCT_PINS": _neutral_product_pins(pins),
        "ASSEMBLY_NAMING": naming_block(policy, names["assembly"], "assembly",
                                        declared_pins, chain=chain),
        "SPEC_NAMING": naming_block(policy, names["spec"], "spec", declared_pins),
        "CODE_NAMING": naming_block(policy, names["code"], "code", declared_pins),
    }

    # THE PROJECT MUST BE ABLE TO HOLD WHAT IS ABOUT TO BE WRITTEN (#258,
    # #261): the manifest is rendered from this very table and put through
    # the project's own reader and `validate-manifest.py`, so what its first
    # bootstrap would refuse is refused here, before the plan is printed.
    _refuse_unholdable_manifest(args, values, policy)

    _print_plan(args, values, names, repositories, urls, local, policy,
                declared_pins, chain, link_pins, pins)

    # ---- refuse to write over anything that already exists ----------------
    # ONE QUESTION, ASKED BY BOTH RUNS BEFORE ANYTHING IS MADE (#537, #609):
    # every folder this run makes and each tree it writes, then every
    # remote. It READS: the folders, then `gh repo view` and a commit
    # listing, or the bare repositories on disk with `--local-remote-dir`,
    # and for a leg that is not empty the one commit it holds, fetched into a
    # temporary directory it deletes. So `--dry-run` refuses what the real
    # run refuses, which `setup-project.py` asks before the yes, and the
    # real run makes no folder for a run it then refuses.
    work_root = args.work_dir.resolve() if args.work_dir else None
    _refuse_unmakeable_folders(args, work_root, names, local)
    # A REPOSITORY MAY ALREADY EXIST only with `--reuse-empty-repo`, and only
    # with ZERO commits, or, for a leg, with this scaffold's own seed as its
    # one commit (#462). An organisation that creates the repository first and
    # asks for the shape second is the ordinary case, not a mistake; an EMPTY
    # repository is a name that has been reserved, and reserving a name is not
    # starting a project. So is a run a ruleset refused part-way, re-run by an
    # operator holding the bypass right. A root with commits is refused
    # exactly as before: that is a live project, and `adopt-project.py` is the
    # tool for one of those. See `_reusable_remotes`.
    reused = _reusable_remotes(names, urls, repositories, local,
                               args.reuse_empty_repo, values,
                               args.tracking_branch)
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    if work_root is None:
        work_root = Path(tempfile.mkdtemp(prefix="openreposhape-"))
    else:
        make_folder(FOLDER_REFUSAL, "--work-dir", work_root)
    if local:
        make_folder(FOLDER_REFUSAL, "--local-remote-dir",
                    args.local_remote_dir.resolve())

    standing = _create_remotes(args, values, repositories, urls, local, reused,
                               root_seen)
    _private_leg_note(args, repositories, local, standing)

    leg_values = _seed_legs(args, values, names, repositories, urls, work_root,
                            reused)
    if leg_values is None:
        return 2
    values.update(leg_values)

    if not _build_assembly_root(args, values, names, repositories, urls, pins,
                                work_root):
        return 2
    _set_topics(repositories, topic, local)

    if not args.no_next_steps:
        print(f"""
NEXT STEPS

    {_next_steps_clone(urls['assembly'], local)}
    cd {names['assembly']}
    make bootstrap

`make bootstrap` puts each leg on `{args.tracking_branch}` AT its pinned commit,
runs the naming, manifest and lockstep-pin validators, and prints the review
authority a wallet register names for this project — or says that authority is
not wallet-carried here, and continues.""")
    print(f"\nWorking trees are at {work_root}\n")
    return 0


def _next_steps_clone(url: str, local: bool) -> str:
    """The NEXT STEPS clone, as a person pastes it into a POSIX shell.

    UNDER `--local-remote-dir` IT CARRIES `-c protocol.file.allow=always`
    (#538), as setup-project.py's own clone does: the legs are cloned from
    the plain paths `.gitmodules` records, the file transport, which git
    refuses a submodule by default since the 2022 advisories, so the line as
    printed failed `transport 'file' not allowed`. The URL is a path there,
    one word whatever folder it is in (`shell_line`, POSIX as #532 rules
    for a printed command); a GitHub URL needs no quotes.
    """
    words = ["git", "-c", "protocol.file.allow=always"] if local else ["git"]
    return shell_line([*words, "clone", "--recurse-submodules", url], "posix")


if __name__ == "__main__":
    sys.exit(main())
