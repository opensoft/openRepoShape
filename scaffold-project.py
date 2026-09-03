#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create a project's three repositories in the shape this standard describes.

    ./scaffold-project.py --org <org> --project <Project> [--dry-run]

WHAT IT DOES
  1. Validates the three names — `<Project>`, `<Project>-spec`,
     `<Project>-code` — against `contracts/repository-naming.yaml` BEFORE it
     creates anything, so a naming mistake costs a message rather than three
     repositories and a rename.
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

IDEMPOTENCY. It refuses to write into a remote or a working directory that
already exists. There is no --force: re-running over a live project is not a
scaffold, and the failure mode of getting it wrong is silent data loss.

EXIT CODES: 0 done · 1 nothing (dry run prints and exits 0) · 2 refusal.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHAPE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SHAPE_ROOT / "scripts"))
from repo_shape import (  # noqa: E402
    PROJECT_ID_RE, TREE_DIGEST_DEFINITION, NamingPolicy, Refusal, accepts_role,
    file_sha256, git_out, tree_digest,
)

SHAPE_REPOSITORY = "opensoft/openRepoShape"
DEFAULT_REFERENCE = (
    "openxFactory ideation/staging/project-repo-schema/project-repo-schema.md"
)

#: Copied out of openRepoShape's OWN tree, so the project carries the standard
#: it was cut from rather than a link to it.
COPIED_FROM_SHAPE = (
    ("scripts/repo_shape.py", "scripts/repo_shape.py"),
    ("scripts/validate-repository-naming.py", "scripts/validate-repository-naming.py"),
    ("contracts/repository-naming.yaml", "contracts/repository-naming.yaml"),
)
#: Copied VERBATIM out of the assembly-root template (no substitution).
COPIED_VERBATIM = (
    "scripts/validate-pins.py",
    "scripts/validate-manifest.py",
    "scripts/bootstrap.py",
    "Makefile",
    ".gitignore",
    ".github/workflows/validate.yml",
)
#: Rendered from the template with `{{PLACEHOLDER}}` substitution. These are
#: NOT digest-pinned in the shape pin: they are this project's own content.
TEMPLATED = (
    "README.md",
    "project.yaml",
    "contracts/spec-pin.yaml",
    "contracts/code-pin.yaml",
    # shape-pin.yaml is rendered LAST, because its `files:` block digests the
    # copies above after they have been written.
)
EXECUTABLE = ("scripts/validate-pins.py", "scripts/validate-manifest.py",
              "scripts/bootstrap.py", "scripts/validate-repository-naming.py")

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def naming_block(policy: NamingPolicy, name: str, role: str,
                 pins: set[str], indent: str = "    ") -> str:
    """The `naming:` block `project.yaml` records for one leg.

    It records the classification AND what was not chosen. A name in
    `<Domainx><Product>` form is a CLAIM of descent that needs a REFERENT
    (2026-09-02): with no declared pin on `open<Product>` the declared role
    wins, and the descendant form survives in `also_matches` so the next reader
    sees the overlap that was resolved rather than wondering whether anyone
    noticed it. Nothing here confers anything; it is a record.
    """
    found = policy.classify(name, role, pins)
    lines = [
        f"{indent}naming:",
        f"{indent}  form: {found.family}",
        f"{indent}  role: {found.role or '~'}",
        f"{indent}  also_matches: [{', '.join(found.also_matches)}]",
    ]
    referents = policy.descendant_referents(name)
    if referents:
        declared_pins = {str(pin).casefold() for pin in pins}
        declared = any(r.casefold() in declared_pins for r in referents)
        # The CANONICAL spelling is what is recorded, whichever one is pinned.
        lines.append(f"{indent}  descendant_referent: {referents[0]}")
        lines.append(f"{indent}  referent_declared: "
                     + ("true" if declared else "false"))
    return "\n".join(lines)


def descendant_note(policy: NamingPolicy, name: str, role: str,
                    pins: set[str]) -> str | None:
    """The one line the plan prints when a name also matches the claim form."""
    found = policy.classify(name, role, pins)
    if "domain-descendant" not in found.also_matches:
        return None
    referent = policy.descendant_referent(name)
    return (f"NOTE {name} also matches the descendant form; it is not a "
            f"descendant because no pin on {referent} is declared — declare "
            f"`contracts/{referent.lower()}-pin.yaml` later if it becomes one")


def run(args: list[str], cwd: Path | None = None, capture: bool = True) -> str:
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(args, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


class CommandFailed(Exception):
    def __init__(self, args, cwd, code, output):
        super().__init__(" ".join(args))
        self.args_list = args
        self.cwd = cwd
        self.code = code
        self.output = output.strip()

    def loudly(self, what: str) -> str:
        where = f"    (in {self.cwd})\n" if self.cwd else ""
        return (
            f"REFUSED {what}. THE EXACT COMMAND WAS:\n"
            f"    {' '.join(self.args_list)}\n{where}"
            f"    exit {self.code}\n"
            f"--- output ---\n{self.output}\n--- end output ---"
        )


RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. Two legitimate exits:

  (1) have an operator holding the bypass right seed the default branch once,
      then re-run this scaffold; or
  (2) push a seed BRANCH and open a pull request:
          git -C {work} push -u origin main:seed/scaffold
          gh pr create --repo {repo} --base main --head seed/scaffold \\
              --title 'Seed the {role} leg' --body 'Scaffolded shape.'

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run.
"""


def render(text: str, values: dict[str, str], source: str) -> str:
    out = text
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    left = PLACEHOLDER_RE.findall(out)
    if left:
        raise Refusal("template-unsubstituted",
                      f"{source}: no value for {sorted(set(left))}",
                      "Remediation: this is a defect in scaffold-project.py's "
                      "substitution table, not in your invocation.")
    return out


def copy_tree(src: Path, dst: Path, values: dict[str, str]) -> None:
    """Copy a template tree, substituting placeholders in every text file."""
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render(path.read_text(encoding="utf-8"), values, str(path)),
            encoding="utf-8",
        )


def git_init_commit(work: Path, message: str, branch: str) -> str:
    run(["git", "init", "-q", "-b", branch, str(work)])
    run(["git", "add", "-A", "--", "."], cwd=work)
    env_commit(work, message)
    return run(["git", "rev-parse", "HEAD"], cwd=work)


def env_commit(work: Path, message: str) -> None:
    """Commit with an identity that always resolves.

    A scaffold that fails on a machine with no `user.email` configured fails
    for a reason that has nothing to do with the project being scaffolded, so
    a fallback identity is supplied rather than assumed.
    """
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape scaffold"),
                          ("GIT_COMMITTER_NAME", "openRepoShape scaffold"),
                          ("GIT_AUTHOR_EMAIL", "scaffold@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL", "scaffold@openreposhape.invalid")):
        env.setdefault(key, fallback)
        if not env.get(key):
            env[key] = fallback
    proc = subprocess.run(["git", "commit", "-q", "-m", message], cwd=str(work),
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(["git", "commit", "-m", message], work,
                            proc.returncode, proc.stderr + proc.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", required=True)
    parser.add_argument("--project", required=True,
                        help="the assembly-root name, e.g. Atlas")
    parser.add_argument("--id", default=None, help="lowercase project id")
    parser.add_argument("--name", default=None, help="display name")
    parser.add_argument("--visibility", choices=("private", "public"),
                        default="private")
    parser.add_argument("--elected-by", default=None)
    parser.add_argument("--elected-on", default=None, help="YYYY-MM-DD")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--tracking-branch", default="main")
    parser.add_argument("--spec-path", default="spec")
    parser.add_argument("--code-path", default="code")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--local-remote-dir", type=Path, default=None,
                        help="create bare repositories here instead of calling "
                             "`gh repo create` (the TEST path; no network)")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="where the working trees are built "
                             "(default: a temporary directory)")
    args = parser.parse_args(argv)

    try:
        return _scaffold(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except CommandFailed as exc:
        print(exc.loudly("a git or gh command failed"), file=sys.stderr)
        return 2


def _scaffold(args) -> int:  # noqa: C901 - a linear procedure, read top to bottom
    project = args.project
    project_id = args.id or project.lower()
    display = args.name or project
    elected_on = args.elected_on or _dt.date.today().isoformat()
    local = args.local_remote_dir is not None

    elected_by = args.elected_by
    if not elected_by:
        try:
            elected_by = git_out(["config", "user.name"], cwd=SHAPE_ROOT)
        except Refusal:
            elected_by = ""
    if not elected_by:
        raise Refusal(
            "scaffold-no-elector",
            "no --elected-by and no `git config user.name`. Electing this "
            "shape is a human's act and the manifest records whose.",
            "Remediation: re-run with --elected-by 'Your Name'.",
        )

    names = {"assembly": project, "spec": f"{project}-spec",
             "code": f"{project}-code"}
    policy = NamingPolicy.load(SHAPE_ROOT / "contracts" / "repository-naming.yaml")
    if not PROJECT_ID_RE.match(project_id):
        raise Refusal("scaffold-bad-id",
                      f"--id {project_id!r} must match {PROJECT_ID_RE.pattern}",
                      "Remediation: pass an explicit lowercase --id.")
    # A FRESH project declares no neutral-product pins, so a descendant-form
    # name here is a claim with no referent and the DECLARED ROLE wins. What is
    # still refused is a real mismatch: a `-spec` name offered as the assembly
    # root, or a `open<Product>` / `<X>-Install` form used as any leg — those
    # forms are unambiguous by construction and declaring a role cannot make
    # them into a leg.
    declared_pins: set[str] = set()
    for role, name in names.items():
        found = policy.classify(name, role, declared_pins)
        if found is None:
            raise Refusal(
                "naming-unclassified",
                f"{name!r} matches no family in the naming policy. "
                "`<Project>` is one CamelCase token with no hyphen, "
                "underscore, dot or space.",
                "Remediation: re-run with a --project value of that form.",
            )
        if not accepts_role(found, role):
            raise Refusal(
                "naming-role-mismatch",
                f"{name!r} classifies as {found[0]}"
                + (f"/{found[1]}" if found[1] else "")
                + f", not as the {role!r} form of a project leg"
                + f" ({found.reason})",
                "Remediation: re-run with a --project value that is one "
                "CamelCase token.",
            )
    topic = policy.topic_for(project_id)

    # ---- the shape revision this project is cut from ----------------------
    shape_commit = git_out(["rev-parse", "HEAD"], cwd=SHAPE_ROOT).lower()
    shape_tree = tree_digest(SHAPE_ROOT, shape_commit)
    dirty = git_out(["status", "--porcelain"], cwd=SHAPE_ROOT)
    if dirty:
        print(
            "WARNING the openRepoShape checkout is DIRTY. `commit:` and "
            f"`tree_sha256` in the shape pin will record {shape_commit[:12]}, "
            "which does NOT describe the bytes being copied. The per-file "
            "sha256 rows are computed from the actual copies, so drift stays "
            "detectable — but commit before scaffolding a real project.",
            file=sys.stderr,
        )

    if local:
        remote_dir = args.local_remote_dir.resolve()
        urls = {role: str(remote_dir / f"{name}.git")
                for role, name in names.items()}
    else:
        urls = {role: f"https://github.com/{args.org}/{name}.git"
                for role, name in names.items()}
    repositories = {role: f"{args.org}/{name}" for role, name in names.items()}

    values = {
        "PROJECT": project,
        "PROJECT_ID": project_id,
        "PROJECT_NAME": display,
        "ORG": args.org,
        "TOPIC": topic,
        "REFERENCE": args.reference,
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
        "CLONE_URL": urls["assembly"],
        "ASSEMBLY_CLONE_URL": urls["assembly"],
        "ASSEMBLY_NAMING": naming_block(policy, names["assembly"], "assembly",
                                        declared_pins),
        "SPEC_NAMING": naming_block(policy, names["spec"], "spec", declared_pins),
        "CODE_NAMING": naming_block(policy, names["code"], "code", declared_pins),
    }

    # ---- the plan ----------------------------------------------------------
    print(f"project      {display} ({project_id})   topic {topic}")
    print(f"shape        {SHAPE_REPOSITORY} @ {shape_commit[:12]} "
          f"(tree {shape_tree[:12]}…)")
    print(f"elected by   {elected_by} on {elected_on}")
    print(f"reference    {args.reference}")
    for role in ("assembly", "spec", "code"):
        print(f"  {role:<9} {repositories[role]:<28} -> {urls[role]}")
    for role in ("assembly", "spec", "code"):
        note = descendant_note(policy, names[role], role, declared_pins)
        if note:
            print(note)
    print(f"legs mounted at {args.spec_path}/ and {args.code_path}/ inside "
          f"{names['assembly']}")
    print("remotes      " + ("bare repositories on disk (no network)" if local
                             else f"gh repo create --{args.visibility}"))
    print("push         " + ("SKIPPED (--no-push)" if args.no_push else "yes"))
    print("topics       " + ("skipped for local remotes" if local
                             else f"gh repo edit --add-topic {topic}"))
    if args.dry_run:
        print("\n--dry-run: nothing was created.")
        return 0

    # ---- refuse to write over anything that already exists ----------------
    work_root = (args.work_dir.resolve() if args.work_dir
                 else Path(tempfile.mkdtemp(prefix="openreposhape-")))
    work_root.mkdir(parents=True, exist_ok=True)
    for role, name in names.items():
        target = work_root / name
        if target.exists() and any(target.iterdir()):
            raise Refusal(
                "scaffold-target-exists",
                f"{target} already exists and is not empty",
                "Remediation: choose an empty --work-dir. There is no --force: "
                "re-running over a live tree is not a scaffold.",
            )
    if local:
        remote_dir.mkdir(parents=True, exist_ok=True)
        for role, name in names.items():
            bare = Path(urls[role])
            if bare.exists():
                raise Refusal(
                    "scaffold-remote-exists", f"{bare} already exists",
                    "Remediation: choose an empty --local-remote-dir. There is "
                    "no --force: re-running over a live project is not a "
                    "scaffold.")
    else:
        for role, repo in repositories.items():
            probe = subprocess.run(["gh", "repo", "view", repo, "--json", "name"],
                                   capture_output=True, text=True, check=False)
            if probe.returncode == 0:
                raise Refusal(
                    "scaffold-remote-exists",
                    f"{repo} already exists on GitHub",
                    "Remediation: delete it, or scaffold under a different "
                    "--project. There is no --force.",
                )

    # ---- create the remotes ------------------------------------------------
    print("\ncreating remotes")
    for role in ("spec", "code", "assembly"):
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

    # ---- the two legs ------------------------------------------------------
    leg_commits: dict[str, str] = {}
    leg_digests: dict[str, str] = {}
    for role, template in (("spec", "spec-root"), ("code", "code-root")):
        work = work_root / names[role]
        copy_tree(SHAPE_ROOT / "templates" / template, work, values)
        commit = git_init_commit(
            work, f"Seed the {role} leg of {display}\n\n"
                  f"Scaffolded from {SHAPE_REPOSITORY} @ {shape_commit}.",
            args.tracking_branch)
        leg_commits[role] = commit.lower()
        leg_digests[role] = tree_digest(work, commit)
        run(["git", "remote", "add", "origin", urls[role]], cwd=work)
        if not args.no_push:
            try:
                run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
                    cwd=work)
            except CommandFailed as exc:
                print(exc.loudly(f"pushing the {role} leg"), file=sys.stderr)
                print(RULESET_HINT.format(work=work, repo=repositories[role],
                                          role=role), file=sys.stderr)
                return 2
        print(f"  {role:<9} {commit[:12]} tree {leg_digests[role][:12]}… "
              f"-> {urls[role]}")

    values.update({
        "SPEC_COMMIT": leg_commits["spec"],
        "CODE_COMMIT": leg_commits["code"],
        "SPEC_TREE_SHA256": leg_digests["spec"],
        "CODE_TREE_SHA256": leg_digests["code"],
    })

    # ---- the assembly root -------------------------------------------------
    assembly = work_root / names["assembly"]
    template_root = SHAPE_ROOT / "templates" / "assembly-root"
    assembly.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATED:
        target = assembly / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render((template_root / name).read_text(encoding="utf-8"), values,
                   name),
            encoding="utf-8")
    for name in COPIED_VERBATIM:
        target = assembly / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(template_root / name, target)
    for src, dst in COPIED_FROM_SHAPE:
        target = assembly / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SHAPE_ROOT / src, target)
    for name in EXECUTABLE:
        (assembly / name).chmod(0o755)

    # The shape pin's `files:` block digests the copies just written. Rendered
    # last, for that reason.
    rows = []
    for path in [dst for _, dst in COPIED_FROM_SHAPE] + list(COPIED_VERBATIM):
        rows.append(f"  - path: {path}\n    sha256: \"{file_sha256(assembly / path)}\"")
    values["SHAPE_FILES"] = "\n".join(rows)
    (assembly / "contracts" / "shape-pin.yaml").write_text(
        render((template_root / "contracts" / "shape-pin.yaml")
               .read_text(encoding="utf-8"), values, "contracts/shape-pin.yaml"),
        encoding="utf-8")

    run(["git", "init", "-q", "-b", args.tracking_branch, str(assembly)])
    # `git submodule add` from the LEG WORKING TREE, then the recorded URL is
    # rewritten to the canonical remote: this way the scaffold never depends on
    # a push having propagated, and `--no-push` produces the same tree.
    for role, path in (("spec", args.spec_path), ("code", args.code_path)):
        run(["git", "-c", "protocol.file.allow=always", "submodule", "add",
             "-q", str(work_root / names[role]), path], cwd=assembly)
        run(["git", "config", "-f", ".gitmodules", f"submodule.{path}.url",
             urls[role]], cwd=assembly)
        run(["git", "remote", "set-url", "origin", urls[role]],
            cwd=assembly / path)
    run(["git", "submodule", "sync", "-q"], cwd=assembly)
    run(["git", "add", "-A", "--", "."], cwd=assembly)
    env_commit(assembly,
               f"Scaffold {display}: manifest, two legs, three pins\n\n"
               f"Shape {SHAPE_REPOSITORY} @ {shape_commit}.\n"
               f"spec {leg_commits['spec']}\ncode {leg_commits['code']}")
    run(["git", "remote", "add", "origin", urls["assembly"]], cwd=assembly)
    if not args.no_push:
        try:
            run(["git", "push", "-q", "-u", "origin", args.tracking_branch],
                cwd=assembly)
        except CommandFailed as exc:
            print(exc.loudly("pushing the assembly root"), file=sys.stderr)
            print(RULESET_HINT.format(work=assembly,
                                      repo=repositories["assembly"],
                                      role="assembly"), file=sys.stderr)
            return 2
    print(f"  assembly  {run(['git', 'rev-parse', 'HEAD'], cwd=assembly)[:12]} "
          f"-> {urls['assembly']}")

    # ---- topics ------------------------------------------------------------
    if not local:
        for role in ("assembly", "spec", "code"):
            run(["gh", "repo", "edit", repositories[role], "--add-topic", topic])
        print(f"  topic     {topic} set on all three")

    print(f"""
NEXT STEPS

    git clone --recurse-submodules {urls['assembly']}
    cd {names['assembly']}
    make bootstrap

`make bootstrap` puts each leg on `{args.tracking_branch}` AT its pinned commit,
runs the naming, manifest and lockstep-pin validators, and prints the review
authority a wallet register names for this project — or says that authority is
not wallet-carried here, and continues.

Working trees are at {work_root}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
