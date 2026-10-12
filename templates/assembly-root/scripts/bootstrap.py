#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after `git clone --recurse-submodules`.

    git clone --recurse-submodules <assembly-root-url>
    cd <Project>
    make bootstrap          # or: python3 scripts/bootstrap.py (python on Windows)

WHAT IT DOES, in order:

  (a) MOVES EACH LEG OFF DETACHED HEAD WITHOUT MOVING THE PIN. A fresh
      recursive clone leaves every submodule detached at the pinned commit —
      the thing that makes people hate submodules, and the first thing an
      engineer meets on day one. Bootstrap creates the tracking branch AT the
      pinned commit, so the WORKING state is branch-shaped while the RECORDED
      state stays an exact pin. It never advances the pin. A tracking branch
      that already exists is FAST-FORWARDED to the pin when its tip is an
      ancestor of it, because that move loses nothing: it is the state
      `bump-leg.py` leaves, the leg detached at the new pin over a branch at
      the old one. A branch holding a commit the pin does not contain is never
      moved; bootstrap prints both and leaves them alone. Advancing a pin
      remains an explicit commit in this repository — see `README.md`, "The
      lockstep invariant". This is why `.gitmodules` carries no `branch=`:
      that would buy the same ergonomics by weakening the pin, and then "what
      commit is this project" would have two answers.

  (b) RUNS THE NEUTRAL VALIDATORS — naming, manifest, lockstep pins. These are
      the only ones a fork with no review lane and no wallet register has, and
      they are enough: a project with no overlays is fully conformant. It then
      prints ONE line if this machine can tell OFFLINE that the upstream shape
      has moved past the pinned commit — see `shape_upstream_notice`, which
      adds no network call and is silent when it cannot answer.

  (c) READS A WALLET REVIEW-AUTHORITY REGISTER IF ONE EXISTS, and prints the
      grants whose objects name this project. If none is found it prints
      exactly `authority is not wallet-carried in this org` and CONTINUES. The
      readout degrades; it never fails. An organisation that has not adopted
      wallet-carried authority is not misconfigured, and a bootstrap that
      failed there would have made the layout load-bearing again.

  (d) EXITS 0 unless a validator failed.

SCHEMA-NEUTRAL BY CONTRACT. A one-repository project runs the same command:
step (a) is a no-op where there are no submodules, and steps (c) and (d) are
unchanged. A bootstrap that existed only for electing projects would make the
election worth something operationally, which is exactly what the ratified
doctrine forbids.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    Refusal, escape_unencodable_stdout, find_repo_root, git_out, load_yaml,
    recorded_gitlink, spelled,
)

DEGRADE_LINE = "authority is not wallet-carried in this org"

#: The two OFFLINE ways this command can learn where the upstream shape is.
#: Both are opt-in and neither is consulted unless it is already there:
#: `SHAPE_UPSTREAM_PATH` points at a clone of openRepoShape on this machine,
#: and `.shape-upstream-tip` is a 40-hex commit a nightly job or a human wrote
#: into the root. NO NETWORK CALL IS ADDED HERE, deliberately — `make
#: bootstrap` runs in organisations that cannot reach the upstream at all, and
#: a bootstrap that paused to ask GitHub a question would have made the shape
#: a dependency again, which is the whole thing the copies exist to avoid.
SHAPE_UPSTREAM_ENV = "SHAPE_UPSTREAM_PATH"
SHAPE_UPSTREAM_CACHE = ".shape-upstream-tip"
COMMIT_40 = re.compile(r"^[0-9a-fA-F]{40}$")
REGISTER_RELPATH = Path("governance") / "review-authority" / "register.yaml"
VALIDATORS = (
    ("naming", ["scripts/validate-repository-naming.py", "--project",
                "project.yaml", "--quiet"]),
    ("manifest", ["scripts/validate-manifest.py"]),
    ("pins", ["scripts/validate-pins.py"]),
)


def _run(root: Path, args: list[str]) -> int:
    # Flush first: this process's own stdout is block-buffered when it is a
    # pipe, and a child writing straight to the fd would otherwise appear
    # BEFORE the heading that introduces it.
    sys.stdout.flush()
    proc = subprocess.run([sys.executable, *args], cwd=str(root), check=False)
    sys.stdout.flush()
    return proc.returncode


def _try_git(args: list[str], cwd: Path) -> str | None:
    try:
        return git_out(args, cwd=cwd)
    except Refusal:
        return None


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "?"


def _git_says(args: list[str], cwd: Path) -> list[str] | None:
    """`None` when `git <args>` succeeds in `cwd`, else the lines git wrote
    to say why not (never an empty list).

    `_try_git` answers only whether a command worked, which is all a read
    needs. A MOVE git refuses has a reason the person has to act on (an
    untracked file in the way, a branch another worktree has checked out),
    so bootstrap prints git's own words rather than a guess. The bytes are
    decoded here, with `replace`, so no locale's codec decides whether the
    reason can be read.
    """
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          check=False)
    if proc.returncode == 0:
        return None
    said = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    return [line.rstrip() for line in said] or [
        f"`git {args[0]}` exited {proc.returncode}"]


def _is_ancestor(sub: Path, local: str, pin: str | None) -> bool:
    """Whether the branch tip `local` is an ancestor of the pin, so that
    moving the branch to the pin loses nothing. A pin this leg has not
    fetched is not known to be one, and is answered no."""
    return pin is not None and _try_git(
        ["merge-base", "--is-ancestor", local, pin], sub) is not None


def fast_forward_to_pin(sub: Path, label: str, branch: str, local: str,
                        pin: str, remote: str | None) -> None:
    """Step (a) for a leg whose tracking branch is BEHIND the pin (#475).

    The branch tip `local` is an ancestor of `pin`, so moving the branch to
    the pin loses nothing. It is the state `bump-leg.py` leaves: the leg
    DETACHED at the new pin over the branch an earlier bootstrap placed at
    the old one. It used to stay detached, and the next commit made in the
    leg was on no branch. The branch is moved, and the leg put on it, from
    exactly two checkouts:

    - HEAD on the branch itself: `merge --ff-only`, which moves the working
      tree too, and moves nothing when a local change or an untracked file
      is in the way.
    - HEAD detached AT THE PIN: `branch -f`, then a `checkout` of the
      branch, which is by then the commit already checked out. Not
      `checkout -B`: git 2.43 resets a branch another worktree has checked
      out with it, leaving that worktree's files behind its own HEAD, where
      `branch -f` refuses.

    ANY OTHER CHECKOUT IS LEFT WHERE IT IS. A commit made on the detached
    leg after the bump is on no branch, and checking the branch out would
    leave it only in the reflog; a leg on another branch is somebody's work.
    Either is said, with what to do, and nothing moves.

    `label` is the leg as `checkout_tracking_branch` prints it, already
    spelled; the branch names and git's own lines are spelled here (#391).
    """
    named = spelled(branch)
    head = _try_git(["rev-parse", "--verify", "--quiet", "HEAD"], sub)
    current = _try_git(["symbolic-ref", "--quiet", "HEAD"], sub)
    if current == f"refs/heads/{branch}":
        why = _git_says(["merge", "--ff-only", "-q", pin], sub)
    elif current is None and head == pin:
        # The checkout runs only once `branch -f` has succeeded (None).
        why = (_git_says(["branch", "-f", branch, pin], sub)
               or _git_says(["checkout", "-q", branch], sub))
    else:
        place = "detached"
        if current is not None:
            place = "on " + spelled(current.split("refs/heads/", 1)[-1])
        print(f"  {label}: branch {named} tip {_short(local)} is behind the "
              f"PIN {_short(pin)}, and the checkout is at {_short(head)} "
              f"({place}), which is neither")
        print("          not moving the checkout off it. Keep any commit made "
              "there on a branch, check out the pin or the branch in the "
              "leg, and run bootstrap again.")
        return
    if why is not None:
        print(f"  {label}: branch {named} tip {_short(local)} is behind the "
              f"PIN {_short(pin)}, and git refused to move it:")
        for line in why:
            print(f"          {spelled(line.strip())}")
        print("          nothing else is tried; the recorded pin is "
              "authoritative. Deal with what git said and run bootstrap "
              "again.")
        return
    note = ""
    if remote is not None and remote != pin:
        note = (f"; origin/{named} is {_short(remote)}, which the pin "
                "deliberately does NOT follow")
    print(f"  {label}: branch {named} fast-forwarded {_short(local)} -> "
          f"{_short(pin)}, the pin{note}")


def checkout_tracking_branch(root: Path, leg: dict, branch: str) -> None:
    """Step (a) for one leg. Prints; never raises; never moves the pin."""
    path = str(leg.get("path") or "")
    sub = root / path
    # What is PRINTED of the leg is spelled (#391): `role`, `path` and `branch`
    # are the manifest's text, read before any validator has had its say.
    where = f"[{spelled(leg.get('role'))}] {spelled(path)}"
    named = spelled(branch)
    if not (sub / ".git").exists():
        print(f"  {where}: NOT INITIALIZED. Run "
              f"`git submodule update --init {spelled(path)}` — the "
              f"validators below will refuse until you do.")
        return
    pin = recorded_gitlink(root, path)
    local = _try_git(["rev-parse", "--verify", "--quiet",
                      f"refs/heads/{branch}"], sub)
    remote = _try_git(["rev-parse", "--verify", "--quiet",
                       f"refs/remotes/origin/{branch}"], sub)

    if local is None:
        if pin is None:
            print(f"  {where}: no gitlink recorded; leaving as is")
            return
        if _try_git(["checkout", "-q", "-b", branch, pin], sub) is None:
            print(f"  {where}: could not create branch {branch!r} at "
                  f"the pin {_short(pin)}; leaving detached")
            return
        if remote is not None:
            _try_git(["branch", "-q", f"--set-upstream-to=origin/{branch}",
                      branch], sub)
        state = "at the pin"
        if remote is not None and remote != pin:
            state = (f"at the pin; origin/{named} is {_short(remote)}, which "
                     f"the pin deliberately does NOT follow")
        print(f"  {where}: branch {named} created at "
              f"{_short(pin)} — {state}")
        return

    if local == pin:
        _try_git(["checkout", "-q", branch], sub)
        print(f"  {where}: on {named} at {_short(pin)} "
              f"(branch tip == pin)")
        return

    if _is_ancestor(sub, local, pin):
        fast_forward_to_pin(sub, where, branch, local, pin, remote)
        return

    print(f"  {where}: PIN {_short(pin)} != branch {named} tip "
          f"{_short(local)}")
    print("          not moving an existing branch. The checkout stays at "
          "the pin; the recorded pin is authoritative and advancing it is an "
          "explicit commit in this repository.")


def shape_upstream_notice(root: Path) -> None:
    """ONE LINE, and only when this machine can already answer offline.

    The pin says which openRepoShape the copied files came from; it cannot say
    whether that revision is still the current one. Where the answer happens to
    be on this machine — a clone at `SHAPE_UPSTREAM_PATH`, or a tip somebody
    cached at `.shape-upstream-tip` — saying so costs nothing and closes the
    gap that had two projects updated by hand. Where it is not, this is silent:
    an absent answer is not a finding, and it never fails the bootstrap.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        return
    try:
        pin = load_yaml(pin_path)
    except Refusal:
        return
    pinned = str((pin or {}).get("commit") or "").lower()
    if not COMMIT_40.match(pinned):
        return
    tip = None
    upstream = os.environ.get(SHAPE_UPSTREAM_ENV)
    if upstream and Path(upstream).is_dir():
        tip = _try_git(["rev-parse", "HEAD"], Path(upstream))
    if tip is None:
        cache = root / SHAPE_UPSTREAM_CACHE
        if cache.is_file():
            tip = cache.read_text(encoding="utf-8").strip()
    if not tip or not COMMIT_40.match(tip):
        return
    if tip.lower() == pinned:
        return
    print(f"  shape: the upstream is at {tip[:12]} and this project is pinned "
          f"at {pinned[:12]}. Run openRepoShape's "
          f"`update-shape.py check --root .` to see what moved; nothing here "
          f"is wrong until you have.")


def _register_paths(root: Path, legs: list[dict]) -> list[Path]:
    candidates = [root / REGISTER_RELPATH]
    for leg in legs:
        path = str(leg.get("path") or "")
        if path and path != ".":
            candidates.append(root / path / REGISTER_RELPATH)
    return [c for c in candidates if c.is_file()]


def _row_objects(row: dict) -> list[str]:
    """Every object identifier a register row scopes authority to.

    Tolerant on purpose: the register's shape is a declared successor rather
    than a ratified schema, and the sibling topic proposes adding path-prefix
    objects below repository granularity. This reads what is there and claims
    nothing about what is not.
    """
    objects: list[str] = []
    for key in ("target_repo", "target_repository", "object"):
        value = row.get(key)
        if isinstance(value, str):
            objects.append(value)
    for container in (row, row.get("scope") if isinstance(row.get("scope"), dict) else {}):
        values = (container or {}).get("objects")
        if isinstance(values, list):
            objects.extend(str(v) for v in values if isinstance(v, (str, int)))
    return objects


def _matches(obj: str, repositories: set[str], prefixes: list[str]) -> bool:
    repo, _, path = obj.partition(":")
    if repo in repositories:
        return True
    if path:
        return any(path.startswith(prefix) for prefix in prefixes)
    return False


def _load_register_rows(register_path: Path) -> list[dict] | None:
    """One register file's rows, tolerant of which key holds them.

    Split from `read_authority` for #132. Returns `None` when the file
    itself could not be read — already printed in that case — so the
    caller's loop moves on to the next register file exactly as the
    original loop's `continue` did.
    """
    try:
        data = load_yaml(register_path)
    except Refusal as exc:
        print("    unreadable, so nothing is claimed from it: "
              f"{spelled(exc.detail)}")
        return None
    rows = []
    if isinstance(data, dict):
        for key in ("rows", "grants", "entries"):
            value = data.get(key)
            if isinstance(value, list):
                rows.extend(r for r in value if isinstance(r, dict))
    return rows


def _row_report_line(row: dict, repositories: set[str],
                     prefixes: list[str]) -> str | None:
    """One register row, formatted for `read_authority`'s report — or
    `None` when it names none of this project's repositories or paths.

    Split from `read_authority` for #132.
    """
    objects = [o for o in _row_objects(row)
              if _matches(o, repositories, prefixes)]
    if not objects:
        return None
    # A register row is a file's text (#391): each value is spelled.
    holder = spelled(row.get("holder_ref") or row.get("holder") or "?")
    act = spelled(row.get("act") or row.get("acts") or "?")
    state = spelled(row.get("state") or "?")
    expires = spelled(row.get("expires_at") or "-")
    return (f"    {holder} · {act} · {', '.join(map(spelled, objects))} · "
           f"{state} · expires {expires}")


def _report_one_register(register_path: Path, root: Path,
                         repositories: set[str], prefixes: list[str]) -> None:
    """One register file, start to finish: read it, print each row that
    names this project, and the "no rows"/"no row names…" line when there
    is nothing to show.

    Split from `read_authority` for #132 so its loop over every register
    file found is a single call per file.
    """
    # POSIX, on every platform: this line names a file in the repository,
    # and git and the reader both spell it that way.
    print("  register: "
          f"{spelled(register_path.relative_to(root).as_posix())}")
    rows = _load_register_rows(register_path)
    if rows is None:
        return
    if not rows:
        print("    no rows")
        return
    hits = 0
    for row in rows:
        line = _row_report_line(row, repositories, prefixes)
        if line is None:
            continue
        hits += 1
        print(line)
    if not hits:
        print("    no row names this project's repositories or paths")


def read_authority(root: Path, legs: list[dict]) -> None:
    """Step (c). Prints the degrade line and returns when no register exists."""
    found = _register_paths(root, legs)
    if not found:
        print(DEGRADE_LINE)
        print("  (no `governance/review-authority/register.yaml` in the "
              "assembly root or in any leg. Wallet-carried authority is an "
              "OVERLAY; the shape confers nothing without it, and nothing "
              "with it.)")
        return
    repositories = {str(leg.get("repository")) for leg in legs
                    if leg.get("repository")}
    prefixes = [str(leg.get("path")) for leg in legs
                if leg.get("path") and leg.get("path") != "."]
    for register_path in found:
        _report_one_register(register_path, root, repositories, prefixes)
    print("  Grants are read here for REPORTING only. This command confers "
          "nothing and enforces nothing; a required check in the repository "
          "that owns the object is what confers.")


def _load_root_and_manifest(args) -> tuple[Path, dict | None]:
    """`--root`'s repository, and its `project.yaml` if it has one.

    Split from `main` for #132 so its `try` wraps one call — a `Refusal`
    from either step is `main`'s early exit 2, exactly as the original
    function's two separate `try`/`except Refusal` blocks around these same
    two steps both were.
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    manifest_path = root / "project.yaml"
    manifest: dict | None = None
    if manifest_path.is_file():
        loaded = load_yaml(manifest_path)
        manifest = loaded if isinstance(loaded, dict) else None
    return root, manifest


def _checkout_all_tracking_branches(root: Path, sub_legs: list[dict],
                                    manifest: dict | None,
                                    branch_arg: str | None) -> None:
    """Step (a): place every submodule leg on its tracking branch.

    Split from `main` for #132.
    """
    if not sub_legs:
        print("  no submodule legs declared. A one-repository project runs "
              "the same command and this step is a no-op.")
        return
    branch = branch_arg or (manifest or {}).get("tracking_branch") or "main"
    for leg in sub_legs:
        checkout_tracking_branch(root, leg, str(leg.get("branch") or branch))


def _run_neutral_validators(root: Path, manifest: dict | None,
                            skip: bool) -> list[str]:
    """Step (b): run the neutral validators, then the upstream notice.

    Split from `main` for #132. Returns the labels of any validator that
    failed, exactly as `main`'s local `failed` list used to accumulate them.
    """
    if skip:
        print("  skipped (--skip-validators)")
        return []
    if manifest is None:
        print("  no project.yaml: this project has not elected the schema, "
              "so there is no manifest and no pins to check. It is not less "
              "governed for that.")
        return []
    failed = []
    for label, argv_ in VALIDATORS:
        if not (root / argv_[0]).is_file():
            print(f"  {label}: {argv_[0]} is absent; SKIPPED")
            continue
        print(f"  --- {label} ---")
        code = _run(root, argv_)
        if code != 0:
            failed.append(f"{label} (exit {code})")
    shape_upstream_notice(root)
    return failed


def main(argv: list[str] | None = None) -> int:
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--branch", default=None,
                        help="tracking branch to place the legs on "
                             "(default: project.yaml `tracking_branch`, else main)")
    parser.add_argument("--skip-validators", action="store_true")
    args = parser.parse_args(argv)

    try:
        root, manifest = _load_root_and_manifest(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    legs = [leg for leg in ((manifest or {}).get("legs") or [])
            if isinstance(leg, dict)]
    sub_legs = [leg for leg in legs if leg.get("role") != "assembly"]

    name = (manifest or {}).get("name") or root.name
    print(f"bootstrap: {spelled(name)} ({spelled(root)})")

    print("\n(a) legs on tracking branches, pins untouched")
    _checkout_all_tracking_branches(root, sub_legs, manifest, args.branch)

    print("\n(b) neutral validators")
    failed = _run_neutral_validators(root, manifest, args.skip_validators)

    print("\n(c) review authority")
    read_authority(root, legs)

    print()
    if failed:
        print("bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
