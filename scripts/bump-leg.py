#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Advance ONE leg of an assembly root, in ONE LOCKSTEP COMMIT.

    ./scripts/bump-leg.py --root <assembly root> --leg spec|code
                          --to <40 hex> [--local-remote-dir <dir>] [--dry-run]

Run from a checkout of THIS standard and pointed at a project, exactly as
`scripts/family.py` and `update-shape.py` are run.

THREE FACTS, ONE COMMIT. A leg is pinned three times over, and the project's
own `scripts/validate-pins.py` refuses when the three disagree:

    1. the GITLINK the assembly root records at the leg's path,
    2. `commit:` and `digests.tree_sha256` in `contracts/<role>-pin.yaml`,
    3. every `.github/workflows/*.yml` reference of the form
       `<owner>/<leg>/...@<40 hex>` naming THAT leg's repository.

`family.py bump` already did exactly this for a family's MEMBER pins. Nothing
did it for a root's LEG pins, so every project moved its own by hand — which
is the failure the invariant was written down about: in the xFactory
aggregation seven consecutive pin-syncs from 2026-08-25 moved the gitlink
alone and left `validate` red on every pull request until 2026-08-26,
unnoticed for a day because the check runs on pull requests only.

WHAT IT REFUSES, and why each is a refusal rather than a warning:

  * `--to` that is not exactly 40 hex. A tag can be moved and a short oid can
    become ambiguous; a pin is a whole commit or it is nothing.
  * a commit the leg's REMOTE does not have. A pin nobody else can fetch is a
    root nobody else can bootstrap.
  * a dirty root. The commit is made with explicit pathspecs, so unrelated
    edits would not be swept in — but a lockstep commit that cannot be read as
    exactly one change is the thing the rule exists to keep readable.
  * the root standing on its own tracking branch. The next step this prints
    would then be a push to the default branch, and these organisations are
    pull-request only.
  * a validator that goes red after the rewrite. Every byte is rolled back
    first — the pin file, the workflow files, the leg's checkout and the index
    — so a refusal leaves the tree exactly as it was found.

EXIT CODES: 0 the commit was made, or a `--dry-run` printed a move it would
make · 1 NOTHING TO DO — every fact already names that commit, under
`--dry-run` as well, so a re-run of a bump that already landed writes no empty
commit · 2 a refusal.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    COMMIT_RE, Refusal, checked_value, git_out, load_yaml, recorded_gitlink,
    repo_basename, tree_digest,
)
from shape_materialize import (  # noqa: E402
    CommandFailed, check_program, run, write_lf,
)

MANIFEST = "project.yaml"

#: The root's OWN validators, run after the rewrite and before the commit.
#: Copies, not this checkout's: a project runs its own gate offline, and the
#: only opinion that matters here is the one its pull request will report.
VALIDATORS = ("scripts/validate-pins.py", "scripts/validate-manifest.py")

#: A local-path remote is a `file://` fetch, which git has refused for
#: submodule work since the 2022 advisories. Passed only on the
#: `--local-remote-dir` path, which is the TEST path; a real leg is an https
#: remote and needs none of it.
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: `owner/repo[/path]@<40 hex>` as it appears in a `uses:` line. CHARACTER FOR
#: CHARACTER the expression `templates/assembly-root/scripts/validate-pins.py`
#: reads the same lines with: this tool writes what that one checks, and a
#: rewriter matching a wider or narrower set than the validator is a rewriter
#: that leaves a reference the gate will still call wrong.
#: `tests/test_bump_leg.py` asserts the two spellings are identical.
WORKFLOW_REF_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?"
    r"@(?P<sha>[0-9a-fA-F]{40})"
)


# ---------------------------------------------------------------------------
# project.yaml: reading the leg out of it
# ---------------------------------------------------------------------------


class Project:
    """An assembly root on disk: its manifest, its legs, and where it is."""

    def __init__(self, root: Path, data: dict):
        self.root = root
        self.data = data
        self.path = root / MANIFEST

    @classmethod
    def open(cls, root_spec) -> "Project":
        root = Path(root_spec).expanduser().resolve()
        path = root / MANIFEST
        if not path.is_file():
            raise Refusal(
                "bump-leg-root-not-a-project",
                f"{path} does not exist, so this is not an assembly root of a "
                "project that has elected this shape",
                "Remediation: --root takes the ASSEMBLY ROOT — the repository "
                "an engineer clones — not a leg and not a family holder. A "
                "family's member pins are moved with `scripts/family.py "
                "bump`; a leg has no legs of its own to move.")
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("bump-leg-manifest-unreadable",
                          f"{path}: not a mapping")
        if data.get("kind") != "project-manifest":
            raise Refusal(
                "bump-leg-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'project-manifest'",
                "Remediation: a family holder declares `kind: "
                "family-manifest` and its members move with `scripts/"
                "family.py bump`.")
        return cls(root, data)

    @property
    def legs(self) -> list[dict]:
        return [row for row in (self.data.get("legs") or [])
                if isinstance(row, dict)]

    def leg(self, role: str) -> dict:
        # `assembly` IS declared, at path `.`, and is refused BEFORE the
        # lookup rather than after it: the manifest names it, so a not-found
        # branch would never be reached, and the root is not a submodule of
        # itself to advance.
        if role == "assembly":
            raise Refusal(
                "bump-leg-assembly-is-not-a-leg",
                "the assembly root is THIS repository, mounted at `.`, and it "
                "is not a submodule of itself",
                "Remediation: --leg takes `spec` or `code`. The assembly "
                "root advances by its own commits; if you meant to move the "
                "project's pin inside a FAMILY, that is `scripts/family.py "
                "bump --member <Project> --to <sha>`.")
        for row in self.legs:
            if str(row.get("role")) == role:
                return row
        declared = ", ".join(sorted(str(row.get("role")) for row in self.legs))
        raise Refusal(
            "bump-leg-unknown-leg",
            f"{self.path} declares no leg with role {role!r}; it declares "
            f"{declared}",
            "Remediation: --leg takes a role this project's own manifest "
            "names. A leg that is missing from the manifest is a manifest "
            "defect, not something to pin around.")

    @property
    def display_name(self) -> str:
        name = str(self.data.get("name") or "").strip()
        if name:
            return name
        for row in self.legs:
            if str(row.get("role")) == "assembly":
                return repo_basename(str(row.get("repository") or ""))
        return str(self.data.get("id") or "this project")

    @property
    def tracking(self) -> str:
        return str(self.data.get("tracking_branch") or "main")


# ---------------------------------------------------------------------------
# the three facts, rewritten
# ---------------------------------------------------------------------------


def rewrite_pin(text: str, commit: str, digest: str) -> str:
    """`commit:` and `digests.tree_sha256:`, and NOTHING else.

    A LINE REWRITE, NOT A YAML DUMP, for the reason `update-shape.py` rewrites
    the shape pin that way and `family.py` rewrites the members block that
    way: the header of `<role>-pin.yaml` is three paragraphs saying what is
    digested and why a tag is never the referent, and a round trip through a
    serialiser would delete every one of them — the argument being the reason
    the file is trusted.

    THOSE TWO FIELDS ARE THE WHOLE DERIVATION. `revision_kind` is the constant
    `commit`; `leg_role`, `source_repository` and `submodule_path` come from
    `project.yaml` rather than from the commit; `digest_algorithm` and
    `digest_definition` name the definition, not a value. The scaffold and
    `adopt-project.py` substitute exactly `{{<ROLE>_COMMIT}}` and
    `{{<ROLE>_TREE_SHA256}}` from the commit being pinned, so those are
    exactly the two lines that move when the commit moves.

    Each replacement must fire exactly once or this refuses: a pin file this
    tool did not recognise is not a pin file it may edit.
    """
    out: list[str] = []
    seen = {"commit": 0, "tree_sha256": 0}
    for line in text.splitlines():
        if line.startswith("commit:"):
            seen["commit"] += 1
            out.append(f'commit: "{commit}"')
            continue
        if line.startswith("  tree_sha256:"):
            seen["tree_sha256"] += 1
            out.append(f'  tree_sha256: "{digest}"')
            continue
        out.append(line)
    for key, count in seen.items():
        if count != 1:
            raise Refusal(
                "bump-leg-pin-unrecognised",
                f"the pin file has {count} `{key}` line(s) where exactly one "
                "was expected, so this tool will not rewrite it",
                "Remediation: the pin was hand-edited into a shape this tool "
                "does not recognise. Fix it by hand this once — `commit:` at "
                "column 0 and `  tree_sha256:` under `digests:` — or re-"
                "scaffold.")
    return "\n".join(out) + "\n"


def plan_workflows(root: Path, repository: str,
                   commit: str) -> list[tuple[Path, str, int]]:
    """Every workflow file whose `@<sha>` refs to THIS leg have to move.

    Returns `(path, rewritten text, references moved)`, one row per file that
    actually changes. A reference to any OTHER repository is left exactly as
    it is — `actions/checkout@<40 hex>` and the sibling leg's own reusable
    workflow are pinned by somebody else's rule, and a bump that moved them
    would be a supply-chain edit wearing a bookkeeping commit's message.

    `.yaml` is read as well as `.yml` because `validate-pins.py` reads both,
    and a file this rewrote nothing in is a file the gate still calls red.
    """
    plans: list[tuple[Path, str, int]] = []
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return plans
    for path in sorted(workflows.iterdir()):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        moved = 0

        def swap(match: re.Match) -> str:
            nonlocal moved
            if match.group("repo") != repository:
                return match.group(0)
            if match.group("sha").lower() == commit:
                return match.group(0)
            moved += 1
            return (f"{match.group('repo')}{match.group('path') or ''}"
                    f"@{commit}")

        text = path.read_text(encoding="utf-8")
        rewritten = WORKFLOW_REF_RE.sub(swap, text)
        if moved:
            plans.append((path, rewritten, moved))
    return plans


# ---------------------------------------------------------------------------
# the leg's own repository
# ---------------------------------------------------------------------------


def leg_placement(submodule: Path) -> str | None:
    """`refs/heads/<branch>`, or None when the leg is detached.

    Remembered BEFORE the checkout so a rollback puts the leg back where it
    stood rather than merely back at the right commit: `bootstrap.py` leaves
    each leg ON its tracking branch at the pinned commit, and a rollback that
    left it detached would have changed something a refusal promised not to.
    """
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "HEAD"],
                          cwd=str(submodule), capture_output=True, text=True,
                          check=False)
    return proc.stdout.strip() or None


def restore_leg(submodule: Path, placement: str | None, commit: str) -> None:
    if placement and placement.startswith("refs/heads/"):
        branch = checked_value("the leg's branch",
                               placement[len("refs/heads/"):])
        run(["git", "checkout", "-q", branch], cwd=submodule)
        return
    run(["git", "checkout", "-q", "--detach", commit], cwd=submodule)


def object_present(submodule: Path, commit: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        cwd=str(submodule), capture_output=True, text=True, check=False)
    return proc.returncode == 0


def on_a_remote_branch(submodule: Path, commit: str) -> bool:
    """Is `commit` reachable from one of this leg's `origin/*` branches?"""
    proc = subprocess.run(
        ["git", "for-each-ref", "--contains", commit, "--format=%(refname)",
         "refs/remotes/origin/"],
        cwd=str(submodule), capture_output=True, text=True, check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def fetch_leg(submodule: Path, repository: str, commit: str,
              local_remote_dir: Path | None) -> None:
    """Get `commit` into the leg's object store, and prove the REMOTE has it.

    A pin nobody else can fetch is a root nobody else can bootstrap, so
    "present in this checkout" is not the question — "on the leg's remote" is.
    Every branch is fetched into `refs/remotes/origin/*` and the commit must
    then be REACHABLE FROM ONE OF THEM.

    REACHABILITY, NOT A FETCH THAT EXITED 0. `git fetch <remote> <sha>`
    answers success without asking the remote anything at all when the object
    is already in the local store — which is exactly the case this has to
    catch, a commit somebody made inside the mount and never pushed. Measured,
    against a bare repository that demonstrably did not have the object:
    `git fetch <bare> <sha>` exited 0. So the fetch is only ever how the refs
    get here; `for-each-ref --contains` is what answers.

    The fetch itself is BEST EFFORT: a machine that cannot reach the remote
    may still be able to answer from the remote-tracking refs it already has,
    and a refusal below says so rather than blaming the network.
    """
    if local_remote_dir is None:
        remote, protocol = "origin", []
    else:
        remote = checked_value(
            "--local-remote-dir",
            str(local_remote_dir.expanduser().resolve()
                / f"{repo_basename(repository)}.git"))
        protocol = FILE_PROTOCOL
    fetched = True
    try:
        run(["git", *protocol, "fetch", "-q", remote,
             "+refs/heads/*:refs/remotes/origin/*"], cwd=submodule)
    except CommandFailed as exc:
        fetched = False
        print(f"  note: `git fetch {remote}` in {submodule.name} exited "
              f"{exc.code}; answering from the remote-tracking refs this "
              "checkout already has", file=sys.stderr)
    if on_a_remote_branch(submodule, commit):
        return
    stale = ("" if fetched else
             " The fetch above FAILED, so this was answered from stale "
             "remote-tracking refs; fix the network or the credential and "
             "re-run before believing it.")
    if object_present(submodule, commit):
        raise Refusal(
            "bump-leg-commit-local-only",
            f"{commit} is in the leg's own object store but is reachable "
            f"from no branch of {repository}",
            "Remediation: somebody committed inside the leg's mount and "
            "never pushed it. Push it to a branch of the leg and re-run — a "
            "pin the rest of the world cannot fetch is a root the rest of "
            "the world cannot bootstrap." + stale)
    raise Refusal(
        "bump-leg-commit-not-on-remote",
        f"{repository} has no branch containing {commit}",
        "Remediation: check the commit — it belongs to the LEG, not to the "
        f"assembly root — and that it has been pushed. `git ls-remote "
        f"{repository}` lists what the remote actually has." + stale)


# ---------------------------------------------------------------------------
# the commit
# ---------------------------------------------------------------------------


def run_validator(root: Path, script: str) -> tuple[int, str]:
    """The ROOT's own copy of a validator, its output captured for a refusal."""
    if not (root / script).is_file():
        return 0, f"  {script} is absent; SKIPPED\n"
    proc = subprocess.run([sys.executable, script], cwd=str(root),
                          capture_output=True, text=True, check=False)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def commit_once(root: Path, message: str, paths: list[str]) -> str:
    """ONE commit, with EXPLICIT PATHSPECS.

    `git commit -- <paths>` commits the working-tree state of exactly those
    paths and nothing the index happens to be carrying. That matters wherever
    more than one session shares a checkout: a bare `git commit` takes
    whatever anyone staged, which is how a one-line bookkeeping commit swept
    nine unrelated renames into itself in the xFactory aggregation on
    2026-07-29.

    The identity is ENV-BASED and falls back rather than being configured: a
    bump that failed on a machine with no `user.email` would fail for a reason
    that has nothing to do with the leg being advanced, and writing
    `git config --global` to fix that is this tool editing a machine it was
    only asked to read.
    """
    run(["git", "add", "--", *paths], cwd=root)
    args = ["git", "commit", "-q", "-F", "-", "--", *paths]
    check_program(args)
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape bump-leg"),
                          ("GIT_COMMITTER_NAME", "openRepoShape bump-leg"),
                          ("GIT_AUTHOR_EMAIL", "bump-leg@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL",
                           "bump-leg@openreposhape.invalid")):
        if not env.get(key):
            env[key] = fallback
    proc = subprocess.run(args, cwd=str(root), input=message,
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(args, root, proc.returncode,
                            proc.stderr + proc.stdout)
    return git_out(["rev-parse", "HEAD"], cwd=root).lower()


def current_branch(root: Path) -> str | None:
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                          cwd=str(root), capture_output=True, text=True,
                          check=False)
    return proc.stdout.strip() or None


# ---------------------------------------------------------------------------


def cmd_bump(args) -> int:  # noqa: C901
    project = Project.open(args.root)
    root = project.root
    role = checked_value("--leg", args.leg)
    leg = project.leg(role)
    repository = checked_value("the leg's repository",
                               str(leg.get("repository") or ""))
    path = checked_value("the leg's path", str(leg.get("path") or ""))
    commit = checked_value("--to", args.to).lower()
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "bump-leg-target-not-a-commit",
            f"--to {args.to!r} is not a 40-hex commit",
            "Remediation: pass the full 40 characters. A tag can be moved and "
            "an abbreviated oid can become ambiguous; a pin is a whole commit "
            "or it is nothing.")

    # THE ROOT MUST BE CLEAN. Tracked changes only: an untracked scratch file
    # cannot reach a commit made with explicit pathspecs, and refusing one
    # would be this tool having an opinion about somebody's working
    # directory. Untracked content INSIDE the leg is ignored for the same
    # reason; the leg sitting at a different commit than the gitlink is NOT,
    # because that is a half-finished bump and this one would land on top of
    # it.
    dirt = git_out(["status", "--porcelain", "--untracked-files=no",
                    "--ignore-submodules=untracked"], cwd=root)
    if dirt:
        raise Refusal(
            "bump-leg-root-dirty",
            f"{root} has uncommitted changes:\n"
            + "\n".join(f"    {line}" for line in dirt.splitlines()),
            "Remediation: commit or stash them first. A lockstep commit that "
            "cannot be read as exactly one change is the thing the rule "
            "exists to keep readable.")

    branch = current_branch(root)
    if branch is None:
        raise Refusal(
            "bump-leg-root-detached",
            f"{root} is not on a branch, so there is no branch to push and "
            "open a pull request from",
            "Remediation: `git -C " + str(root) + " switch -c bump/"
            + f"{role}-{commit[:12]}` and re-run.")
    if branch == project.tracking:
        raise Refusal(
            "bump-leg-on-tracking-branch",
            f"{root} is on {branch!r}, which {MANIFEST} declares as this "
            "project's tracking branch",
            "Remediation: these organisations are pull-request only, so this "
            "will not make a commit whose only next step is a push to the "
            "default branch. Run:\n    git -C " + str(root)
            + f" switch -c bump/{role}-{commit[:12]}\nand re-run.")

    submodule = root / path
    if not (submodule / ".git").exists():
        raise Refusal(
            "bump-leg-uninitialized",
            f"{path} is not an initialized submodule checkout, so the new "
            "commit cannot be resolved or digested",
            "Remediation: `make bootstrap` in the root, which resolves a "
            "credential for a private leg first, or `git submodule update "
            "--init " + path + "`.")

    # THE COMMIT BEING REPLACED, read from the INDEX first (`recorded_gitlink`
    # does), because the index is what the next commit will record. Its
    # absence is refused rather than treated as "nothing to roll back to": a
    # declared leg the root records no `160000` entry for is the same defect
    # `validate-pins.py` names `pin-gitlink-absent`, and a bump is not the
    # tool that invents a first gitlink.
    was = recorded_gitlink(root, path)
    if was is None:
        raise Refusal(
            "bump-leg-gitlink-absent",
            f"no gitlink (mode 160000) is recorded at {path!r}, so there is "
            "no pin to advance",
            "Remediation: the leg is declared in project.yaml but this "
            "repository does not record it as a submodule. `git submodule "
            f"add` mounted it once; restore that commit, or re-scaffold. "
            "`validate-pins.py` refuses on the same fact.")
    print(f"project      {project.display_name} ({project.data.get('id')})")
    print(f"leg          {role:<8} {repository} at {path}/")
    fetch_leg(submodule, repository, commit, args.local_remote_dir)
    digest = tree_digest(submodule, commit)
    pin_rel = f"contracts/{role}-pin.yaml"
    pin_path = root / pin_rel
    if not pin_path.is_file():
        raise Refusal(
            "bump-leg-pin-missing",
            f"{pin_rel} does not exist, so half of the invariant has nothing "
            "to be written into",
            "Remediation: `validate-pins.py` refuses the same way. Restore "
            "the file from the project's history, or re-scaffold it.")
    pin_text = pin_path.read_text(encoding="utf-8")
    plans = plan_workflows(root, repository, commit)

    print(f"commit       {was[:12]} -> {commit[:12]}")
    print(f"tree         {digest[:12]}… ({digest})")
    print(f"pin          {pin_rel}")
    if plans:
        moved = sum(count for _, _, count in plans)
        print(f"workflows    {moved} reference(s) in {len(plans)} file(s):")
        for wf_path, _, count in plans:
            print(f"  {wf_path.relative_to(root)}  {count} reference(s)")
    else:
        print("workflows    no `@<sha>` reference names this leg")

    if was == commit and not plans and rewrite_pin(pin_text, commit,
                                                   digest) == pin_text:
        print(f"\nnothing to do: {repository} is already pinned at "
              f"{commit[:12]} and every fact agrees.")
        return 1

    if args.dry_run:
        print("\n--dry-run: nothing was changed. The leg's object store was "
              "fetched into, which is how the digest above was computed; the "
              "working tree, the pin, the workflows and the index are "
              "untouched.")
        return 0

    # ---- the rewrite, remembered byte for byte so a red validator undoes it
    written: dict[Path, bytes] = {}
    placement = leg_placement(submodule)
    staged: list[str] = [path, pin_rel] + [
        str(wf_path.relative_to(root)) for wf_path, _, _ in plans]
    moved_leg = False
    try:
        # A BUMP LEAVES THE LEG AT THE COMMIT, detached, and does not move any
        # branch. `bootstrap.py` is what places a leg ON its tracking branch —
        # at the pin — and a bump that also moved `main` in the leg would be
        # this tool pushing somebody's branch around from inside a submodule.
        run(["git", "checkout", "-q", "--detach", commit], cwd=submodule)
        moved_leg = True
        for target, data in [(pin_path, rewrite_pin(pin_text, commit, digest))
                             ] + [(wf_path, text) for wf_path, text, _ in plans]:
            written[target] = target.read_bytes()
            # LF, on every platform. `.github/workflows/validate.yml` is
            # a digest-pinned COPY of the shape's file: `shape-pin.yaml`
            # records a sha256 of the bytes the materializer wrote - and this
            # is the lockstep rewrite the README documents: gitlink, pin and
            # every `@<sha>` in one commit. A CRLF rewrite on Windows would
            # change every line of the file it just re-pinned and the project's
            # own `validate-pins.py` would go red on the commit that fixed it.
            write_lf(target, data)

        # STAGED BEFORE THE VALIDATORS RUN, because `recorded_gitlink` asks
        # the INDEX first: the gitlink the next commit will record is the one
        # the check is about, and an unstaged bump would be reported against
        # the commit it is replacing.
        run(["git", "add", "--", *staged], cwd=root)

        print("\nthe project's own validators")
        for script in VALIDATORS:
            code, output = run_validator(root, script)
            sys.stdout.write(output)
            if code != 0:
                raise Refusal(
                    "bump-leg-validators-red",
                    f"{script} exited {code} after the rewrite. Every byte "
                    "this command wrote has been rolled back — the pin, the "
                    "workflow files, the leg's checkout and the index — and "
                    "the tree is exactly as it was.\n--- its output ---\n"
                    + output.rstrip() + "\n--- end output ---",
                    "Remediation: read the finding above. A tool that left a "
                    "project red would have moved the cost from this command "
                    "to somebody else's pull request.")
    except (Refusal, CommandFailed):
        # THE ROLLBACK NEVER RAISES OVER THE REFUSAL. Whatever it cannot put
        # back is printed and the original exit is re-raised: a rollback
        # failure that replaced the validator's finding would leave a person
        # with a changed tree and no idea what the gate objected to.
        for target, original in written.items():
            target.write_bytes(original)
        try:
            if moved_leg:
                restore_leg(submodule, placement, was)
            run(["git", "reset", "-q", "HEAD", "--", *staged], cwd=root)
        except CommandFailed as undo:
            print(undo.loudly("rolling the bump back"), file=sys.stderr)
        raise

    body = (
        f"{was[:12]} -> {commit[:12]}, tree {digest}.\n\n"
        + (f"{sum(count for _, _, count in plans)} workflow `@<sha>` "
           f"reference(s) in {len(plans)} file(s) moved with it.\n\n"
           if plans else
           "No workflow reference names this leg, so the gitlink and the pin "
           "file are the whole of it.\n\n")
        + f"The gitlink at {path}, `commit:` and `digests.tree_sha256` in "
          f"{pin_rel}, and every workflow reference to {repository} move in "
          "ONE commit because `scripts/validate-pins.py` refuses when they "
          "disagree — a gitlink advanced alone is red on the next pull "
          "request, and on somebody else's change.\n\nWritten by "
          "openRepoShape's `scripts/bump-leg.py`; the digest is recomputed "
          "from the leg's own objects, not adjusted.\n")
    head = commit_once(
        root, f"Bump {role} leg to {commit[:12]} in {project.display_name}\n\n"
        + body, staged)
    print(f"\n  committed {head[:12]}: " + ", ".join(staged))
    print(f"  {path}/ is left DETACHED at {commit[:12]}; `make bootstrap` in "
          "the root re-places it on its tracking branch AT the new pin")
    print(f"\nNEXT  git -C {root} push -u origin {branch}")
    print(f"      then open a pull request against {project.tracking}; never "
          "push the bump to the default branch directly")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bump-leg.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, metavar="PATH",
                        help="the project's ASSEMBLY ROOT — the repository "
                             "carrying project.yaml")
    parser.add_argument("--leg", required=True, metavar="{spec,code}",
                        help="which leg to advance, by the `role:` its own "
                             "project.yaml declares")
    parser.add_argument("--to", required=True, metavar="COMMIT",
                        help="the 40-hex commit to move the gitlink, the pin "
                             "and every workflow reference to, together")
    parser.add_argument("--local-remote-dir", type=Path, default=None,
                        help="resolve the leg's remote to a bare repository "
                             "here instead of its origin (the TEST path; no "
                             "network)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would move and change nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_bump(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("advancing a leg"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
