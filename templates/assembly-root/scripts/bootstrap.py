#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after `git clone --recurse-submodules`.

    git clone --recurse-submodules <assembly-root-url>
    cd <Project>
    make bootstrap          # or: python scripts/bootstrap.py

WHAT IT DOES, in order:

  (a) MOVES EACH LEG OFF DETACHED HEAD WITHOUT MOVING THE PIN. A fresh
      recursive clone leaves every submodule detached at the pinned commit —
      the thing that makes people hate submodules, and the first thing an
      engineer meets on day one. Bootstrap creates the tracking branch AT the
      pinned commit, so the WORKING state is branch-shaped while the RECORDED
      state stays an exact pin. It never advances the pin and it never moves a
      branch that already exists somewhere else; when the pin and a branch tip
      disagree it prints both and leaves them alone. Advancing a pin remains an
      explicit commit in this repository — see `README.md`, "The lockstep
      invariant". This is why `.gitmodules` carries no `branch=`: that would
      buy the same ergonomics by weakening the pin, and then "what commit is
      this project" would have two answers.

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
    Refusal, find_repo_root, git_out, load_yaml, recorded_gitlink,
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


def checkout_tracking_branch(root: Path, leg: dict, branch: str) -> None:
    """Step (a) for one leg. Prints; never raises; never moves the pin."""
    path = str(leg.get("path") or "")
    role = leg.get("role")
    sub = root / path
    if not (sub / ".git").exists():
        print(f"  [{role}] {path}: NOT INITIALIZED. Run "
              f"`git submodule update --init {path}` — the validators below "
              f"will refuse until you do.")
        return
    pin = recorded_gitlink(root, path)
    local = _try_git(["rev-parse", "--verify", "--quiet",
                      f"refs/heads/{branch}"], sub)
    remote = _try_git(["rev-parse", "--verify", "--quiet",
                       f"refs/remotes/origin/{branch}"], sub)

    if local is None:
        if pin is None:
            print(f"  [{role}] {path}: no gitlink recorded; leaving as is")
            return
        if _try_git(["checkout", "-q", "-b", branch, pin], sub) is None:
            print(f"  [{role}] {path}: could not create branch {branch!r} at "
                  f"the pin {_short(pin)}; leaving detached")
            return
        if remote is not None:
            _try_git(["branch", "-q", f"--set-upstream-to=origin/{branch}",
                      branch], sub)
        state = "at the pin"
        if remote is not None and remote != pin:
            state = (f"at the pin; origin/{branch} is {_short(remote)}, which "
                     f"the pin deliberately does NOT follow")
        print(f"  [{role}] {path}: branch {branch} created at "
              f"{_short(pin)} — {state}")
        return

    if local == pin:
        _try_git(["checkout", "-q", branch], sub)
        print(f"  [{role}] {path}: on {branch} at {_short(pin)} "
              f"(branch tip == pin)")
        return

    print(f"  [{role}] {path}: PIN {_short(pin)} != branch {branch} tip "
          f"{_short(local)}")
    print(f"          not moving an existing branch. The checkout stays at "
          f"the pin; the recorded pin is authoritative and advancing it is an "
          f"explicit commit in this repository.")


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


def read_authority(root: Path, manifest: dict | None, legs: list[dict]) -> None:
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
        print(f"  register: {register_path.relative_to(root)}")
        try:
            data = load_yaml(register_path)
        except Refusal as exc:
            print(f"    unreadable, so nothing is claimed from it: {exc.detail}")
            continue
        rows = []
        if isinstance(data, dict):
            for key in ("rows", "grants", "entries"):
                value = data.get(key)
                if isinstance(value, list):
                    rows.extend(r for r in value if isinstance(r, dict))
        if not rows:
            print("    no rows")
            continue
        hits = 0
        for row in rows:
            objects = [o for o in _row_objects(row)
                       if _matches(o, repositories, prefixes)]
            if not objects:
                continue
            hits += 1
            holder = row.get("holder_ref") or row.get("holder") or "?"
            act = row.get("act") or row.get("acts") or "?"
            state = row.get("state") or "?"
            expires = row.get("expires_at") or "-"
            print(f"    {holder} · {act} · {', '.join(objects)} · "
                  f"{state} · expires {expires}")
        if not hits:
            print("    no row names this project's repositories or paths")
    print("  Grants are read here for REPORTING only. This command confers "
          "nothing and enforces nothing; a required check in the repository "
          "that owns the object is what confers.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--branch", default=None,
                        help="tracking branch to place the legs on "
                             "(default: project.yaml `tracking_branch`, else main)")
    parser.add_argument("--skip-validators", action="store_true")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    manifest_path = root / "project.yaml"
    manifest: dict | None = None
    if manifest_path.is_file():
        try:
            loaded = load_yaml(manifest_path)
            manifest = loaded if isinstance(loaded, dict) else None
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2
    legs = [leg for leg in ((manifest or {}).get("legs") or [])
            if isinstance(leg, dict)]
    sub_legs = [leg for leg in legs if leg.get("role") != "assembly"]

    name = (manifest or {}).get("name") or root.name
    print(f"bootstrap: {name} ({root})")

    print("\n(a) legs on tracking branches, pins untouched")
    if not sub_legs:
        print("  no submodule legs declared. A one-repository project runs the "
              "same command and this step is a no-op.")
    else:
        branch = args.branch or (manifest or {}).get("tracking_branch") or "main"
        for leg in sub_legs:
            checkout_tracking_branch(root, leg, str(leg.get("branch") or branch))

    print("\n(b) neutral validators")
    failed: list[str] = []
    if args.skip_validators:
        print("  skipped (--skip-validators)")
    elif manifest is None:
        print("  no project.yaml: this project has not elected the schema, so "
              "there is no manifest and no pins to check. It is not less "
              "governed for that.")
    else:
        for label, argv_ in VALIDATORS:
            if not (root / argv_[0]).is_file():
                print(f"  {label}: {argv_[0]} is absent; SKIPPED")
                continue
            print(f"  --- {label} ---")
            code = _run(root, argv_)
            if code != 0:
                failed.append(f"{label} (exit {code})")
        shape_upstream_notice(root)

    print("\n(c) review authority")
    read_authority(root, manifest, legs)

    print()
    if failed:
        print("bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
