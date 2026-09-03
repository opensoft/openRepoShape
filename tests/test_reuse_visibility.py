# SPDX-License-Identifier: Apache-2.0
"""`--reuse-empty-repo` INHERITS the reused root's own GitHub visibility.

Every other test in this suite runs against `--local-remote-dir` (bare
repositories on disk have no visibility at all, which is the point of
`test_scaffold_e2e.py::test_internal_visibility_is_accepted`). Answering
whether the two NEW legs inherit an INTERNAL assembly root needs a real
`gh repo view --json visibility` read, so this file is the one place in the
suite that runs the scaffold in its NON-local mode — against a FAKE `gh` on
`PATH`, never the real one, and with `--no-push` so no `git push` ever reaches
`https://github.com/...` either. Nothing here touches a network.
"""

from __future__ import annotations

import os
import stat
import sys
import textwrap

from conftest import ORG, REPO, SCAFFOLD, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

PROJECT = "Kirkwood"
ASSEMBLY_REPO = f"{ORG}/{PROJECT}"

#: A minimal `gh` that answers exactly the calls a reused-empty-root scaffold
#: makes: `repo view --json name|visibility` and `api .../commits` for the
#: KNOWN assembly repository (everything else — the two legs, which must not
#: exist yet — answers "not found"), and `repo create` / `repo edit` as a
#: silent success, logging every invocation for the test to inspect.
FAKE_GH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json
    import os
    import sys

    argv = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as f:
        f.write(" ".join(argv) + "\\n")

    KNOWN = os.environ["FAKE_GH_ASSEMBLY_REPO"]
    VISIBILITY = os.environ["FAKE_GH_VISIBILITY"]


    def fail(msg):
        print(msg, file=sys.stderr)
        sys.exit(1)


    if argv[:2] == ["repo", "view"]:
        repo = argv[2] if len(argv) > 2 else None
        if repo != KNOWN:
            fail(f"GraphQL: Could not resolve to a Repository with the name "
                 f"'{repo}'. (NOT_FOUND)")
        idx = argv.index("--json")
        fields = argv[idx + 1].split(",")
        out = {}
        if "name" in fields:
            out["name"] = repo.rsplit("/", 1)[-1]
        if "visibility" in fields:
            out["visibility"] = VISIBILITY
        print(json.dumps(out))
        sys.exit(0)
    elif argv[:1] == ["api"]:
        path = argv[1] if len(argv) > 1 else ""
        if path.startswith(f"repos/{KNOWN}/commits"):
            print("[]")
            sys.exit(0)
        fail("HTTP 404: Not Found")
    elif argv[:2] == ["repo", "create"]:
        sys.exit(0)
    elif argv[:2] == ["repo", "edit"]:
        sys.exit(0)
    else:
        fail(f"fake gh: unhandled invocation: {argv!r}")
    """)


def _fake_gh_env(tmp_path, visibility: str) -> dict:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    gh_path.write_text(FAKE_GH, encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log_path = tmp_path / "fake-gh.log"
    log_path.write_text("", encoding="utf-8")
    return {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "FAKE_GH_LOG": str(log_path),
        "FAKE_GH_ASSEMBLY_REPO": ASSEMBLY_REPO,
        "FAKE_GH_VISIBILITY": visibility,
    }, log_path


def test_an_internal_reused_root_is_inherited_by_the_legs(tmp_path):
    env, log_path = _fake_gh_env(tmp_path, "INTERNAL")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--no-push", "--work-dir", str(tmp_path / "work"),
                        env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "already internal on GitHub" in result.stdout
    assert "the two new legs inherit that visibility" in result.stdout

    log = log_path.read_text()
    assert f"repo create {ORG}/{PROJECT}-spec --internal" in log
    assert f"repo create {ORG}/{PROJECT}-code --internal" in log
    assert f"repo create {ASSEMBLY_REPO} " not in log, (
        "the reused assembly root must never be (re-)created")

    manifest = load_yaml(tmp_path / "work" / PROJECT / "project.yaml")
    assert manifest["visibility"] == "internal"


def test_an_explicit_visibility_disagreeing_with_the_reused_root_warns(tmp_path):
    env, log_path = _fake_gh_env(tmp_path, "INTERNAL")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--visibility", "public", "--no-push",
                        "--work-dir", str(tmp_path / "work"), env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "WARNING --visibility public disagrees with the reused" in result.stderr
    assert "internal" in result.stderr

    log = log_path.read_text()
    assert f"repo create {ORG}/{PROJECT}-spec --public" in log, (
        "the human's explicit --visibility wins over the inherited one")

    manifest = load_yaml(tmp_path / "work" / PROJECT / "project.yaml")
    assert manifest["visibility"] == "public"
