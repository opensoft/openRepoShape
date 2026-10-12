#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after cloning a FAMILY holder.

    git clone --recurse-submodules <family-url>
    cd <Family>
    make bootstrap          # or: python3 scripts/bootstrap.py (python on Windows)

WHAT IT DOES, in order:

  (a) FETCHES EVERY MEMBER, RECURSIVELY, WITH A CREDENTIAL IF ONE IS THERE.
      A member is an assembly root that itself mounts two legs, so `--init
      --recursive` has to reach three repositories deep — and in most
      organisations all of them are PRIVATE. This resolves the same
      credentials the `validate` workflow does, in the same order: a GitHub
      App installation token (`SHAPE_LEGS_APP_TOKEN`, minted by whatever
      called this) first, then a `SHAPE_LEGS_TOKEN` PAT, then nothing at all.
      Whichever it finds is used ONLY through a `git -c
      url.<...>.insteadOf=<...>` rewrite for the duration of the one command,
      covering both the HTTPS and SSH spellings a submodule URL may carry. It
      is never written into `.git/config`, never persisted, never printed.

      With no credential this is a plain `git submodule update --init
      --recursive`, exactly as it was for a family whose members are public.
      A fetch that fails is REPORTED and does not stop the run: the members
      that did arrive are still worth bootstrapping, and a family that
      refused to do anything because one member is unreachable would be worse
      than one that says which.

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — its legs onto their tracking
      branches at their pinned commits, its own validators, its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses.

  (c) EXITS 0 unless a member's own command failed. A member that is not
      checked out is REPORTED and skipped, not a failure: it is the state a
      missing credential leaves, and it is already reported in (a).

THE FAMILY CONFERS NOTHING and neither does this command. It fetches, it
delegates, and it says what it could not reach.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import Refusal, find_repo_root, load_yaml  # noqa: E402

MANIFEST = "family.yaml"
DEFAULT_MEMBERS_DIR = "members"

#: The two environment variables a leg/member credential may arrive in, in the
#: order the `validate` workflow resolves them. An App-minted installation
#: token is short-lived and per-owner; the PAT is the standing fallback.
CREDENTIAL_ENV = ("SHAPE_LEGS_APP_TOKEN", "SHAPE_LEGS_TOKEN")

#: Both spellings a submodule URL may carry, rewritten to an authenticated
#: HTTPS one for the duration of a single command.
REWRITE_TARGETS = ("https://github.com/", "git@github.com:")


#: The characters `spelled` writes as an escape, besides the bidirectional
#: controls below: the controls (Cc), the surrogates (Cs), and the line and
#: paragraph separators (Zl, Zp). Nothing else is escaped, `spelled` says why.
ESCAPED_CATEGORIES = frozenset(("Cc", "Cs", "Zl", "Zp"))
#: The bidirectional controls: U+061C, U+200E and U+200F, the embeddings and
#: overrides U+202A to U+202E, and the isolates U+2066 to U+2069.
ESCAPED_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def escape_unencodable_stdout() -> None:
    """A character stdout cannot encode is printed escaped, never raised on (#391).

    WHAT WAS WRONG. `main` printed the manifest's `name` with a plain `print`
    before any step ran, so `name: "a\\ud83db"` (a lone surrogate, which no
    UTF-8 stdout can write) or `name: "日本"` on a stdout that is not UTF-8
    (`PYTHONIOENCODING=ascii`, or the ANSI code page Windows gives a stdout that
    is not the console) ended `make bootstrap` in a `UnicodeEncodeError`
    traceback one step before `validate-manifest.py`, the validator that names
    the problem, was reached. This file's own wording raised on such a stdout
    too, wherever it carries a dash or a middle dot.

    A `strict` or `surrogateescape` stdout, the two handlers that raise, is
    reconfigured ONCE, at the start of `main`, to `backslashreplace`, the
    handler stderr already has: what the stdout holds is written as it was, and
    what it cannot hold as `\\u65e5`. Any other handler, one somebody chose, is
    left alone, and the ENCODING is never changed. `scripts/validate-pins.py`
    does the same for its report (#295). The tools run from a checkout of the
    standard use `shape_materialize.escape_what_stdout_cannot_encode` (#214),
    which no project carries, and this file imports nothing but `repo_shape`.
    This function and `spelled` are the same in the assembly root's
    `bootstrap.py` and the family root's.

    GUARDED, because failing to set a handler is no reason to refuse the run: a
    stream a caller replaced may have no `reconfigure`, a closed one raises
    `ValueError`, and `pythonw` has no stdout at all.
    """
    if getattr(sys.stdout, "errors", None) in ("strict", "surrogateescape"):
        try:
            sys.stdout.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass


def spelled(value: object) -> str:
    """`value` as ONE line of text, with what a terminal must not be handed
    written as escapes (#391).

    What `escape_unencodable_stdout` cannot do. A raw ESC or CR is encodable on
    every stdout, so it reaches the terminal as the control it is, and a
    manifest's `name` or a register row is a person's text. EXACTLY these
    characters are written as the escape Python spells it (`\\x1b`, `\\r`,
    `\\u2028`, `\\ud83d`, `\\u202e`), and no others:

    - the controls (Unicode category Cc: C0, DEL and C1), which move a cursor,
      clear a screen or end a line;
    - the surrogates (Cs), which no UTF-8 text holds, so a lone one is named
      whatever handler the stdout has;
    - the line and paragraph separators (Zl and Zp, U+2028 and U+2029), which
      end a line in some viewers, so the value would not stay on its line;
    - the bidirectional controls (U+061C, U+200E, U+200F, U+202A to U+202E and
      U+2066 to U+2069), which reorder the text around them so that a name
      reads as another name.

    EVERY OTHER CHARACTER PRINTS AS IT IS, as it did before this function
    existed: the zero-width non-joiner a Persian or Indic name needs, the
    zero-width joiner that makes an emoji sequence, the ideographic space of a
    Japanese full name, the no-break space, the soft hyphen, and any other
    format, space or unassigned character. `str.isprintable` is not the test:
    it refuses all of those, which `validate-manifest.py` accepts and a UTF-8
    terminal shows correctly, and what it counts as unassigned moves with the
    interpreter's Unicode database. A backslash prints as it is too, so a name
    holding the four characters `\\x1b` prints as one holding ESC does.

    Applied to every value this script prints that it read from the manifest, a
    register row or the disk, and to none of its own wording.
    """
    return "".join(
        char.encode("unicode_escape").decode("ascii")
        if (char in ESCAPED_BIDI_CONTROLS
            or unicodedata.category(char) in ESCAPED_CATEGORIES)
        else char
        for char in str(value))


def credential() -> tuple[str, str]:
    """`(source, token)`; `("none", "")` when the environment carries none."""
    for name in CREDENTIAL_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    return "none", ""


def fetch_members(root: Path) -> bool:
    """(a) `git submodule update --init --recursive`, authenticated or not."""
    source, token = credential()
    args = ["git"]
    if token:
        for target in REWRITE_TARGETS:
            args += ["-c", f"url.https://x-access-token:{token}@github.com/"
                           f".insteadOf={target}"]
    args += ["submodule", "update", "--init", "--recursive"]
    print(f"  credential source: {source}")
    sys.stdout.flush()
    proc = subprocess.run(args, cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if proc.returncode == 0:
        print("  every member and leg fetched")
        return True
    # The token can appear in git's own error text (it is in the URL it tried),
    # so the output is scrubbed before it is printed.
    message = (proc.stderr + proc.stdout).strip()
    if token:
        message = message.replace(token, "<redacted>")
    print(f"  FETCH INCOMPLETE (git exit {proc.returncode}) using credential "
          f"source '{source}':\n{message}", file=sys.stderr)
    print("  If the members are PRIVATE, set SHAPE_LEGS_TOKEN (a fine-grained "
          "PAT with contents:read on them) or export an App-minted "
          "SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive is bootstrapped "
          "below.", file=sys.stderr)
    return False


def members_of(root: Path) -> tuple[str, list[dict]]:
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise Refusal(
            "family-manifest-missing",
            f"{manifest_path} does not exist, so there is no declaration of "
            "which members to bootstrap",
            "Remediation: this command bootstraps a FAMILY holder. A project "
            "runs its own `scripts/bootstrap.py` instead.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{manifest_path}: not a mapping")
    name = str(manifest.get("name") or root.name)
    rows = [row for row in (manifest.get("members") or [])
            if isinstance(row, dict)]
    return name, rows


def member_path(root: Path, row: dict) -> Path:
    return root / str(row.get("path")
                      or f"{DEFAULT_MEMBERS_DIR}/{row.get('project')}")


def run_member_target(root: Path, row: dict, target: str) -> str | None:
    """(b) One member's own `make <target>`. Returns a failure line, or None."""
    # A member row is the family manifest's text (#391): what is PRINTED of it,
    # and of `--members-make`, is spelled. The path is built from the raw row.
    project = spelled(row.get("project") or "?")
    path = member_path(root, row)
    named = spelled(target)
    if not (path / ".git").exists():
        print(f"  [{project}] {spelled(path.name)}: NOT CHECKED OUT; skipped. "
              "See the fetch above.")
        return None
    if not (path / "Makefile").is_file():
        print(f"  [{project}] no Makefile; skipped. A member without one is "
              "not misconfigured — it simply has nothing for this command to "
              "call.")
        return None
    make = os.environ.get("MAKE") or shutil.which("make")
    if not make:
        print(f"  [{project}] `make` is not on PATH; skipped.")
        return None
    print(f"  --- {project}: make {named} ---")
    sys.stdout.flush()
    proc = subprocess.run([make, target], cwd=str(path), check=False)
    sys.stdout.flush()
    if proc.returncode != 0:
        return f"{project} (make {named} exited {proc.returncode})"
    return None


def main(argv: list[str] | None = None) -> int:
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip step (a); the members are already there "
                             "(what `make validate` passes)")
    parser.add_argument("--members-make", default="bootstrap", metavar="TARGET",
                        help="the make target to run in each member "
                             "(default: bootstrap)")
    parser.add_argument("--skip-members", action="store_true",
                        help="fetch only; run nothing in the members")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        name, rows = members_of(root)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"bootstrap: {spelled(name)} ({spelled(root)}) — "
          f"{len(rows)} member(s)")

    print("\n(a) members and their legs")
    if args.no_fetch:
        print("  skipped (--no-fetch)")
    else:
        fetch_members(root)

    print(f"\n(b) each member's own `make {spelled(args.members_make)}`")
    failed: list[str] = []
    if args.skip_members:
        print("  skipped (--skip-members)")
    elif not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
    else:
        for row in rows:
            failure = run_member_target(root, row, args.members_make)
            if failure:
                failed.append(failure)

    print()
    if failed:
        print("family bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("family bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
