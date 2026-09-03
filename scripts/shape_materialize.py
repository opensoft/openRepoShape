#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize an assembly root out of `templates/assembly-root/`.

ONE MATERIALIZER, TWO CALLERS. `scaffold-project.py` builds an assembly root
in an empty directory; `adopt-project.py` builds one INSIDE a repository that
already exists and keeps its history. Those differ in exactly two ways — what
to do when a template file collides with a file the source repository already
has, and whether a Makefile needs the adopted project's `CONTRACTS_DIR` line —
so they differ by two arguments rather than by a second copy of the code.

The alternative was a second copy, and a second copy is how `shape-pin.yaml`
starts digesting a different set of files than the scaffold writes.

STANDARD LIBRARY ONLY, like everything else shipped here.

WHAT A COLLISION IS, AND WHY IT IS NOT AN OVERWRITE. Adopting in place means
the source repository's own `README.md`, `Makefile` and `.gitignore` are
already at the root and are part of its history. The shape's copies of those
names are NOT more important than the project's, and silently overwriting one
would put a byte in the split commit that no `git rm` accounts for — which is
precisely what `adopt-project.py --verify` would then report as a mismatch.
So a colliding template file is written BESIDE the original under
`collision_dir` (`shape/`) and the collision is reported for the plan's
`follow_ups:`. The human merges it; the tool never guesses.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import NamingPolicy, Refusal, file_sha256  # noqa: E402

SHAPE_REPOSITORY = "opensoft/openRepoShape"
DEFAULT_REFERENCE = (
    "openxFactory ideation/staging/project-repo-schema/project-repo-schema.md"
)

#: One name, used in three places below: the source path, the target path and
#: the chmod list. Spelling it three times is how the chmod list starts naming
#: a file the copy list no longer writes.
VALIDATE_NAMING = "scripts/validate-repository-naming.py"

#: Copied out of openRepoShape's OWN tree, so the project carries the standard
#: it was cut from rather than a link to it.
COPIED_FROM_SHAPE = (
    ("scripts/repo_shape.py", "scripts/repo_shape.py"),
    (VALIDATE_NAMING, VALIDATE_NAMING),
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
#: Rendered only when the project DECLARES a neutral-product pin, and written
#: once per declared pin as `contracts/<product lowercased>-pin.yaml`.
NEUTRAL_PIN_TEMPLATE = "contracts/neutral-product-pin.yaml"
EXECUTABLE = ("scripts/validate-pins.py", "scripts/validate-manifest.py",
              "scripts/bootstrap.py", VALIDATE_NAMING)

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")

#: Appended to the assembly root's Makefile by `adopt-project.py` ONLY. A
#: scaffolded project's legs are empty, so nothing reads across them yet; an
#: ADOPTED project's code leg holds tooling that used to read `contracts/`
#: from beside it and now reads it from the other leg through the root.
ADOPT_MAKEFILE_BLOCK = """
# --- adopted project: reading ACROSS the legs -------------------------------
# The spec leg owns `contracts/`; the code leg holds the tooling that reads
# them. Mounted here, `spec/contracts` is one relative path from `code/`, so
# the root exports it once and the code leg takes it from the environment
# rather than each script guessing at `../`.
CONTRACTS_DIR ?= $(CURDIR)/spec/contracts
export CONTRACTS_DIR

.PHONY: contracts-dir
contracts-dir:
\t@echo $(CONTRACTS_DIR)
"""


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


#: The ONLY programs anything here will execute. Every call is a fixed verb
#: with values from the command line as ARGUMENTS — never a shell string, so
#: `shell=False` keeps the arguments out of a shell — and this list keeps the
#: PROGRAM out of the caller's hands as well. The tools take a repository
#: name, a path and a commit from whoever runs them, including from an AI
#: assistant reading a plan file; the pair of constraints is what stops a
#: crafted value from becoming a command.
ALLOWED_PROGRAMS = ("git", "gh")


def check_program(args: list[str]) -> None:
    """Refuse to execute anything but the two tools this standard drives."""
    program = Path(args[0]).name if args else ""
    if program not in ALLOWED_PROGRAMS:
        raise Refusal(
            "program-not-allowed",
            f"refusing to execute {program!r}: this module runs only "
            + " and ".join(ALLOWED_PROGRAMS),
            "Remediation: this is a defect in the tool that built the command "
            "line, not in your invocation.")
    for argument in args:
        if not isinstance(argument, str):
            raise Refusal(
                "argument-not-a-string",
                f"a command argument is {argument!r}, not a string",
                "Remediation: this is a defect in the tool that built the "
                "command line.")


def run(args: list[str], cwd: Path | None = None, capture: bool = True) -> str:
    check_program(args)
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True, check=False)
    if proc.returncode != 0:
        raise CommandFailed(args, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


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
    command = ["git", "commit", "-q", "-m", message]
    check_program(command)
    proc = subprocess.run(command, cwd=str(work),
                          capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(["git", "commit", "-m", message], work,
                            proc.returncode, proc.stderr + proc.stdout)


def git_init_commit(work: Path, message: str, branch: str) -> str:
    run(["git", "init", "-q", "-b", branch, str(work)])
    run(["git", "add", "-A", "--", "."], cwd=work)
    env_commit(work, message)
    return run(["git", "rev-parse", "HEAD"], cwd=work)


def render(text: str, values: dict[str, str], source: str) -> str:
    out = text
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    left = PLACEHOLDER_RE.findall(out)
    if left:
        raise Refusal("template-unsubstituted",
                      f"{source}: no value for {sorted(set(left))}",
                      "Remediation: this is a defect in the substitution table "
                      "of the tool you ran, not in your invocation.")
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


def naming_block(policy: NamingPolicy, name: str, role: str,
                 pins, indent: str = "    ") -> str:
    """The `naming:` block `project.yaml` records for one leg.

    It records the classification AND what was not chosen. A name in
    `<Domainx><Product>` form is a CLAIM of descent that needs a REFERENT
    (2026-09-02): with no declared pin on `open<Product>` the declared role
    wins, and the descendant form survives in `also_matches` so the next reader
    sees the overlap that was resolved rather than wondering whether anyone
    noticed it. WITH the pin the answer is `domain-descendant` in the declared
    `assembly` role, because a descendant may carry legs. Nothing here confers
    anything; it is a record.
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
                    pins) -> str | None:
    """The one line the plan prints when a name also matches the claim form."""
    found = policy.classify(name, role, pins)
    if "domain-descendant" not in found.also_matches:
        return None
    referent = policy.descendant_referent(name)
    return (f"NOTE {name} also matches the descendant form; it is not a "
            f"descendant because no pin on {referent} is declared — declare "
            f"`contracts/{referent.lower()}-pin.yaml` later if it becomes one")


class Materialized:
    """What `materialize_assembly_root` wrote, and where it had to write it.

    `shape_files` is the ordered list of paths the shape pin digests, at the
    paths they ACTUALLY landed on — a pin that names a path nothing is at is
    a refusal in `validate-pins.py`, and rightly.
    """

    def __init__(self) -> None:
        self.written: list[str] = []
        self.collisions: list[tuple[str, str]] = []
        self.shape_files: list[str] = []

    def follow_ups(self) -> list[str]:
        return [
            f"merge {actual} into {intended}: the shape's copy could not take "
            f"that name because the source repository already has one, and "
            f"nothing was overwritten"
            for intended, actual in self.collisions
        ]


def materialize_assembly_root(shape_root: Path, target: Path,
                              values: dict[str, str], *,
                              collision_dir: str | None = None,
                              append: dict[str, str] | None = None,
                              neutral_pins: dict[str, dict] | None = None,
                              ) -> Materialized:
    """Write the assembly-root skeleton into `target`.

    `collision_dir` — where a template file goes when the target path is
    already taken. `None` means "there can be no collision" and a collision
    raises, which is the scaffold's case: it built the directory itself.

    `append` maps a template-relative path to text appended after rendering
    (the adopt tool's `CONTRACTS_DIR` block).

    `neutral_pins` maps a neutral product name to the values for its pin file,
    each rendered from `contracts/neutral-product-pin.yaml`.
    """
    template_root = shape_root / "templates" / "assembly-root"
    result = Materialized()

    def place(rel: str, write) -> str:
        """Write `rel`, or, if it is taken, the same name under `collision_dir`."""
        path = target / rel
        if path.exists():
            if collision_dir is None:
                raise Refusal(
                    "materialize-collision",
                    f"{path} already exists and this materializer was given no "
                    "collision directory",
                    "Remediation: scaffold into an empty directory, or call "
                    "with collision_dir set (which is what adopt does).")
            actual = f"{collision_dir}/{rel}"
            result.collisions.append((rel, actual))
            path = target / actual
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path)
        rel_written = str(path.relative_to(target))
        result.written.append(rel_written)
        return rel_written

    for rel in TEMPLATED:
        text = render((template_root / rel).read_text(encoding="utf-8"),
                      values, rel)
        text += (append or {}).get(rel, "")
        place(rel, lambda p, t=text: p.write_text(t, encoding="utf-8"))
    for rel in COPIED_VERBATIM:
        text = (template_root / rel).read_text(encoding="utf-8")
        text += (append or {}).get(rel, "")
        result.shape_files.append(
            place(rel, lambda p, t=text: p.write_text(t, encoding="utf-8")))
    for src, rel in COPIED_FROM_SHAPE:
        text = (shape_root / src).read_text(encoding="utf-8")
        result.shape_files.append(
            place(rel, lambda p, t=text: p.write_text(t, encoding="utf-8")))
    for product, pin_values in (neutral_pins or {}).items():
        rel = f"contracts/{product.lower()}-pin.yaml"
        text = render((template_root / NEUTRAL_PIN_TEMPLATE)
                      .read_text(encoding="utf-8"), {**values, **pin_values}, rel)
        place(rel, lambda p, t=text: p.write_text(t, encoding="utf-8"))
    for rel in EXECUTABLE:
        actual = next((w for w in result.written if w.endswith(rel)), None)
        if actual:
            (target / actual).chmod(0o755)

    # The shape pin's `files:` block digests the copies just written, so it is
    # rendered LAST and over the paths they actually landed on.
    rows = "\n".join(f"  - path: {rel}\n    sha256: \"{file_sha256(target / rel)}\""
                     for rel in result.shape_files)
    text = render((template_root / "contracts" / "shape-pin.yaml")
                  .read_text(encoding="utf-8"),
                  {**values, "SHAPE_FILES": rows}, "contracts/shape-pin.yaml")
    place("contracts/shape-pin.yaml",
          lambda p, t=text: p.write_text(t, encoding="utf-8"))
    return result


def copy_out(src: Path, dst: Path) -> None:
    """A byte copy that makes the parent directory first."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
