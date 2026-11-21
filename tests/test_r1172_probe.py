# r1172 review probe: not part of the PR. Records what each tool says.
from __future__ import annotations

import json
import os
import shutil
from contextlib import ExitStack
from pathlib import Path

import pytest

from conftest import run_script
from test_root_git_unreadable import gitfile_into, linked_into, moved_out
from test_shape_doctor import (  # noqa: F401
    FAMILY_MEMBER, FAMILY_NAME, holder, scaffolded_here, standard, doctor,
)
from test_validate_pins_unreadable_workflows_dir import mode_of

OUT = Path(os.environ["R1172_OUT"])

RUNS = [
    ("assembly-bootstrap", "project", "bootstrap.py", []),
    ("validate-family", "family", "validate-family.py", []),
    ("validate-family--no-members", "family", "validate-family.py",
     ["--no-members"]),
    ("family-bootstrap", "family", "bootstrap.py", []),
    ("family-bootstrap--no-fetch--skip-members", "family", "bootstrap.py",
     ["--no-fetch", "--skip-members"]),
    ("siblings--dry-run", "family", "siblings.py", ["--dry-run"]),
    ("siblings", "family", "siblings.py", []),
]


def fresh(kind, tmp, state, holder, scaffolded_here):
    if kind == "project":
        root = tmp / state / "proj" / "Atlas"
        root.parent.mkdir(parents=True)
        shutil.copytree(scaffolded_here["clone"], root, symlinks=True)
    else:
        root = tmp / state / "fam" / FAMILY_NAME / FAMILY_NAME
        root.parent.mkdir(parents=True)
        shutil.copytree(holder["root"], root, symlinks=True)
    return root


def arrange(stack, root, state):
    if state == "readable":
        return
    if state == "link":
        linked_into(root)
        stack.enter_context(mode_of(root.parent, "locked", 0))
    elif state == "dir000":
        stack.enter_context(mode_of(root, ".git", 0))
    elif state == "dir444":
        stack.enter_context(mode_of(root, ".git", 0o444))
    elif state == "gitfile-locked":
        gitfile_into(root)
        stack.enter_context(mode_of(root.parent, "locked", 0))
    elif state == "gitfile000":
        moved_out(root)
        stack.enter_context(mode_of(root, ".git", 0))
    elif state == "gitdir-head000":
        stack.enter_context(mode_of(root, ".git/HEAD", 0))
    elif state == "link-loop-parent-locked":
        # .git a link to itself, and the folder above holds a .git into a
        # locked folder: find_repo_root walks past the loop.
        shutil.move(str(root / ".git"), str(root.parent / "kept"))
        (root / ".git").symlink_to(".git")
    else:
        raise AssertionError(state)


STATES = ["readable", "link", "dir000", "dir444", "gitfile-locked",
          "gitfile000", "gitdir-head000"]


def short(text, n=6):
    lines = text.splitlines()
    return lines[:n] + ([f"... ({len(lines)} lines)"] if len(lines) > n
                        else [])


@pytest.mark.parametrize("state", STATES)
def test_probe_tools(holder, scaffolded_here, tmp_path, state):
    records = []
    for label, kind, script, args in RUNS:
        root = fresh(kind, tmp_path, f"{state}-{label}", holder,
                     scaffolded_here)
        with ExitStack() as stack:
            arrange(stack, root, state)
            result = run_script(root / "scripts" / script, *args, cwd=root)
        records.append({"state": state, "tool": label,
                        "rc": result.returncode,
                        "stdout": short(result.stdout),
                        "stderr": short(result.stderr, 12),
                        "traceback": "Traceback" in result.stderr})
    with OUT.open("a", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec) + "\n")


@pytest.mark.parametrize("state", ["readable", "link", "dir000", "dir444",
                                   "gitfile-locked", "gitfile000"])
def test_probe_doctor(standard, holder, scaffolded_here, tmp_path, state):
    root = fresh("family", tmp_path, state, holder, scaffolded_here)
    with ExitStack() as stack:
        arrange(stack, root, state)
        result = doctor(standard, root, "--json")
    rec = {"state": state, "tool": "doctor", "rc": result.returncode,
           "traceback": "Traceback" in result.stderr}
    try:
        payload = json.loads(result.stdout)
        rec["verdict"] = payload["verdict"]
        rec["rows"] = {row["id"]: [row["status"], row["reason"],
                                   row.get("next"), row.get("why")]
                       for row in payload["rows"]
                       if row["id"] in ("members", "family", "placement",
                                        "shape-currency", "manifest-kinds",
                                        "agent-files")}
    except Exception as exc:  # noqa: BLE001
        rec["error"] = repr(exc)
        rec["stdout"] = short(result.stdout)
        rec["stderr"] = short(result.stderr)
    with OUT.open("a", encoding="utf-8") as out:
        out.write(json.dumps(rec) + "\n")


FILE_OK = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow",
           "GIT_CONFIG_VALUE_0": "always"}


@pytest.mark.parametrize("state", ["readable", "dir000", "link"])
def test_probe_plain_with_file_transport(holder, scaffolded_here, tmp_path,
                                         state):
    records = []
    for label, script, args in (("family-bootstrap", "bootstrap.py", []),
                                ("siblings", "siblings.py", [])):
        root = fresh("family", tmp_path, f"{state}-{label}", holder,
                     scaffolded_here)
        with ExitStack() as stack:
            arrange(stack, root, state)
            result = run_script(root / "scripts" / script, *args, cwd=root,
                                env=FILE_OK)
        placed = sorted(p.name for p in root.parent.iterdir()
                        if p.name != root.name)
        records.append({"state": state, "tool": "file-ok-" + label,
                        "rc": result.returncode,
                        "stdout": result.stdout.splitlines()[-3:],
                        "stderr": short(result.stderr, 6),
                        "traceback": "Traceback" in result.stderr,
                        "beside": placed})
    with OUT.open("a", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec) + "\n")
