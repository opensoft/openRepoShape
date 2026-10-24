# SPDX-License-Identifier: Apache-2.0
"""Four `update-shape.py` messages that said what was not true (#535).

Each was an ordinary path whose only harm was a misleading or unpasteable
message, found in the v1.0.0 review of `apply` and `check`:

  N1  A branchless `apply` that moved the pin back to what HEAD commits still
      printed a commit line, and pasted, git said "nothing to commit".
  N3  The `update-conflict` remedy said `git show <target>:<source path>` and
      nothing, in the refusal or in `check`, said what either was.
  N4  The commit `apply --branch` writes said "the copies are not
      hand-edited", and so did `--pr`'s body, of every file, including those
      `--accept-local` re-pinned from the project's own bytes.
  N7  The `gh pr create` that `apply --branch` prints without `--pr` had no
      `--title`, `--body` or `--fill`; `gh` prompts for them.

THE TEXTS ARE READ, NEVER RUN. `gh` is never reached: `--pr` runs in this
process with `update_shape.run` stubbed at the one seam it goes through, as
`test_update_shape_pr_base.py` does, and a printed `gh pr create` is a line of
text, read back by `shlex.split`. What `gh` does without a terminal was not
run, and nothing here says what it does.
"""

from __future__ import annotations

import importlib.util
import io
import re
import shlex
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ORG, REPO, WINDOWS_SKIP, git, run_script
from test_commit_trailers import message_of
from test_update_shape import (CHANGED, CHANGED_SOURCE, LOCAL, PROJECT,
                               UPSTREAM_FIX_LINE, commit_upstream_changes,
                               next_line_of, pin_rows,
                               scaffold_upstream_and_project)
from test_update_shape_header_comments import (  # noqa: F401
    HOLDER, holder_project,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256  # noqa: E402
from shape_materialize import SHAPE_REPOSITORY  # noqa: E402

UPDATE = REPO / "update-shape.py"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"
LOCAL_SOURCE = f"templates/assembly-root/{LOCAL}"

#: The sentence the commit message ends on, and the body's: "not
#: hand-edited" of the copies re-copied from the upstream, and of nothing
#: else.
MESSAGE_ENDS = ("the copies re-copied from the upstream are not hand-edited "
                "and the digests are recomputed, not adjusted.")
BODY_SAYS = ("No copy re-copied from the upstream was hand-edited and every "
             "digest was recomputed.")


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so `--pr` runs here with `gh` stubbed
    and `next_line` and `conflict_remediation` are called directly."""
    spec = importlib.util.spec_from_file_location("update_shape_messages",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A and an upstream that has moved twice. B changes the one
    file `CHANGED_SOURCE`. C, on B, changes it and `LOCAL_SOURCE` too, so a
    project that edited both has TWO files changed on both sides at C, and one
    that edited `LOCAL` alone has a file only IT changed at B."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-messages")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    commit_c = commit_upstream_changes(
        upstream, "Fix both validators",
        {CHANGED_SOURCE: "\n# A second fix.\n", LOCAL_SOURCE: "\n# A fix.\n"})
    assert len({commit_a, commit_b, commit_c}) == 3
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b, "c": commit_c}


@pytest.fixture
def root(project, tmp_path) -> Path:
    """A private, mutable copy of the project as it was scaffolded at A."""
    target = tmp_path / PROJECT
    shutil.copytree(project["clone"], target, symlinks=True)
    return target


def edit(root: Path, path: str, *, commit: bool = False) -> None:
    """A local edit to a pinned copy, in bytes, and, where `--branch` is to
    take the run, committed: `apply --branch` refuses a root whose pinned
    copy is not what HEAD commits."""
    target = root / path
    target.write_bytes(target.read_bytes() + b"\n# a local edit\n")
    if commit:
        git("add", "--", path, cwd=root)
        git("commit", "-q", "-m", f"Edit {path}", cwd=root)


def run_apply(root: Path, project: dict, at: str, *extra: str):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(project["upstream"]), "--at",
                      project[at], *extra)


def run_check(root: Path, project: dict, at: str):
    return run_script(UPDATE, "check", "--root", str(root), "--upstream",
                      str(project["upstream"]), "--at", project[at])


# --- N3: the source path nobody names ------------------------------------------


def test_check_names_the_upstream_file_of_a_row_changed_on_both_sides(
        project, root):
    """`check`'s `both` row says which file in the standard it compares with,
    which is not the path in the root."""
    edit(root, CHANGED)

    result = run_check(root, project, "b")

    assert result.returncode == 1, result.stdout + result.stderr
    assert ("(edited here AND upstream since the pin (upstream's file: "
            f"{CHANGED_SOURCE}). Merge it by hand") in result.stdout, \
        result.stdout


def test_apply_refuses_a_both_row_with_the_command_that_reads_its_upstream_bytes(
        project, root):
    """The remedy's placeholders are filled: the full target commit and the
    path in the standard, which `git show` reads in a shape clone. The row's
    own line in the refusal names the same file."""
    edit(root, CHANGED)

    result = run_apply(root, project, "b")

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED update-conflict: "), result.stderr
    assert (f"    {CHANGED}: edited here AND upstream since the pin "
            f"(upstream's file: {CHANGED_SOURCE})") in result.stderr
    assert ("(the upstream bytes are `git show "
            f"{project['b']}:{CHANGED_SOURCE}` in a shape clone)"
            ) in result.stderr
    assert "<target>" not in result.stderr
    assert "<source path>" not in result.stderr
    assert "--accept-local on that path" in result.stderr


def test_apply_names_each_both_rows_command_by_the_path_in_the_root(
        project, root):
    """Two rows changed on both sides are two commands, each for its own
    file, so the person reading one never runs the other's."""
    edit(root, CHANGED)
    edit(root, LOCAL)

    result = run_apply(root, project, "c")

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"`git show {project['c']}:{LOCAL_SOURCE}` for {LOCAL}"
            in result.stderr), result.stderr
    assert (f"`git show {project['c']}:{CHANGED_SOURCE}` for {CHANGED}"
            in result.stderr), result.stderr
    assert "(the upstream bytes, in a shape clone: " in result.stderr


def test_a_missing_copy_keeps_its_own_remedy_and_the_others_are_named(
        project, root):
    """`copy-missing` has an exit of its own and no upstream bytes to name; a
    `both` row beside it still gets its command, after `For the others,`."""
    edit(root, CHANGED)
    (root / "Makefile").unlink()

    result = run_apply(root, project, "b")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Makefile is pinned and gone from the root" in result.stderr
    assert ("For the others, merge each one by hand (the upstream bytes are "
            f"`git show {project['b']}:{CHANGED_SOURCE}` in a shape clone)"
            ) in result.stderr, result.stderr


def test_a_row_with_no_upstream_bytes_is_named_no_command(update_shape):
    """`unmapped` has no upstream file and `upstream-removed` is gone at the
    target, so `git show` would fail for either: the sentence is what it
    always was, with no parenthesis, never a command that cannot run."""
    unmapped = update_shape.Row("scripts/x.py", "0" * 64)
    unmapped.state = update_shape.UNMAPPED
    removed = update_shape.Row("scripts/y.py", "0" * 64)
    removed.state = update_shape.UPSTREAM_REMOVED
    removed.source = "templates/assembly-root/scripts/y.py"
    removed.target = "f" * 40

    said = update_shape.conflict_remediation([unmapped, removed])

    assert said == ("Remediation: merge each one by hand, commit it, then "
                    "re-run this with --accept-local on that path so the row "
                    "is recomputed from what you merged.")
    assert "git show" not in said


# --- N4: "not hand-edited" is not true of everything ---------------------------


def test_a_run_that_accepted_nothing_says_not_hand_edited_of_the_re_copied_only(
        project, root):
    result = run_apply(root, project, "b", "--branch", "shape/update-n4a")

    assert result.returncode == 0, result.stdout + result.stderr
    message = message_of(root)
    assert message.endswith(f"Written by update-shape.py; {MESSAGE_ENDS}\n")
    assert "was not re-copied" not in message
    assert "were not re-copied" not in message
    assert "--accept-local" not in message


def test_the_commit_names_a_path_accept_local_kept_from_the_projects_own_bytes(
        project, root):
    """`LOCAL` is edited here and unchanged upstream at B, so `--accept-local`
    re-pins it from the project's bytes: the history must not call it
    not hand-edited."""
    edit(root, LOCAL, commit=True)

    result = run_apply(root, project, "b", "--accept-local", LOCAL,
                       "--branch", "shape/update-n4b")

    assert result.returncode == 0, result.stdout + result.stderr
    message = message_of(root)
    assert (f"{LOCAL} was not re-copied: `--accept-local` kept it as the "
            "project holds it, so the pin's row for it records a digest of "
            "the project's own bytes, not of the upstream's file.\n\n"
            f"Written by update-shape.py; {MESSAGE_ENDS}") in message, message
    assert message.endswith(MESSAGE_ENDS + "\n")


def test_the_commit_names_every_accepted_path_in_one_order(project, root):
    """Two rows changed on both sides, both accepted: named together, sorted,
    in the plural."""
    edit(root, CHANGED, commit=True)
    edit(root, LOCAL, commit=True)

    result = run_apply(root, project, "c", "--accept-local", CHANGED,
                       "--accept-local", LOCAL, "--branch",
                       "shape/update-n4c")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (f"{LOCAL}, {CHANGED} were not re-copied: `--accept-local` kept "
            "each as the project holds it, so the pin's row for each records "
            "a digest of the project's own bytes, not of the upstream's "
            "file.") in message_of(root)


def test_a_path_accept_local_names_but_the_run_re_copied_is_not_called_kept(
        project, root):
    """`--accept-local` on a copy nobody edited changes nothing: it is
    re-copied from the upstream, so it is among the copies the message says
    are not hand-edited, and it is not named as kept."""
    result = run_apply(root, project, "b", "--accept-local", CHANGED,
                       "--branch", "shape/update-n4d")

    assert result.returncode == 0, result.stdout + result.stderr
    message = message_of(root)
    assert "1 copied file(s) re-copied from the upstream" in message
    assert "not re-copied" not in message


def stub_gh(update_shape, monkeypatch, answer) -> list:
    """`update_shape.run` with `gh` answered by `answer(command, calls)`, which
    is never run, and `git` still run for real: a commit under test has to be
    a real one. Returns the list of every `gh` command the tool tried."""
    real = update_shape.run
    calls: list = []

    def run(command, *args, **kwargs):
        if command[0] == "gh":
            calls.append(list(command))
            return answer(command, calls, update_shape)
        return real(command, *args, **kwargs)

    monkeypatch.setattr(update_shape, "run", run)
    for name, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                        ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                        ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                        ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid"),
                        ("LANES_LANE", "")):
        monkeypatch.setenv(name, value)
    return calls


@pytest.fixture
def gh_calls(update_shape, monkeypatch) -> list:
    """Every `gh` command the tool tries to run, none of them run: `gh` is
    answered with a pull request URL."""
    return stub_gh(update_shape, monkeypatch,
                   lambda command, calls, module:
                   "https://example.invalid/pull/1")


def apply_in_process(update_shape, root: Path, project: dict, at: str,
                     branch: str, *extra: str) -> int:
    """`apply --branch <branch> --pr` run in this process, whose `gh` is a
    stub; the exit code."""
    return update_shape.main(["apply", "--root", str(root), "--yes",
                              "--upstream", str(project["upstream"]), "--at",
                              project[at], "--branch", branch, "--pr", *extra])


def opened_by_pr(update_shape, gh_calls: list, root: Path, project: dict,
                 at: str, branch: str, *extra: str) -> tuple[str, str]:
    """`(title, body)` of the one `gh pr create` `--pr` runs."""
    assert apply_in_process(update_shape, root, project, at, branch,
                            *extra) == 0
    assert len(gh_calls) == 1, gh_calls
    command = gh_calls[0]
    assert command[:3] == ["gh", "pr", "create"], command
    return (command[command.index("--title") + 1],
            command[command.index("--body") + 1])


def test_the_pull_request_body_claims_not_hand_edited_of_the_re_copied_only(
        update_shape, gh_calls, project, root):
    title, body = opened_by_pr(update_shape, gh_calls, root, project, "b",
                               "shape/update-n4e")

    assert title == ("Re-sync the shape copies to "
                     f"{SHAPE_REPOSITORY} @ {project['b'][:12]}")
    assert BODY_SAYS in body
    assert body.startswith("Written by openRepoShape's `update-shape.py`: "
                           "`contracts/shape-pin.yaml` and `project.yaml` "
                           "re-pinned onto "), body
    assert "No copy was hand-edited" not in body
    assert "not re-copied" not in body


def test_the_pull_request_body_names_what_accept_local_kept(
        update_shape, gh_calls, project, root):
    edit(root, LOCAL, commit=True)

    _, body = opened_by_pr(update_shape, gh_calls, root, project, "b",
                           "shape/update-n4f", "--accept-local", LOCAL)

    assert BODY_SAYS in body
    assert body.endswith(
        f" {LOCAL} was not re-copied: `--accept-local` kept it as the "
        "project holds it, so the pin's row for it records a digest of the "
        "project's own bytes, not of the upstream's file."), body


# --- N7: a bare `gh pr create` --------------------------------------------------


def create_argv(line: str) -> list[str]:
    """The `gh pr create` in a NEXT line, as the shell would split it: the
    part after the `&&` of the push, or the whole line after `--push`."""
    words = shlex.split(line.removeprefix("NEXT  "))
    return words[words.index("gh"):]


@pytest.mark.parametrize("accepted", [False, True],
                         ids=["plain", "accept-local"])
def test_the_branch_next_line_is_a_gh_pr_create_with_the_words_pr_uses(
        update_shape, gh_calls, project, tmp_path, accepted):
    """THE LINE ROUND-TRIPS through `shlex.split` and carries a `--title` and
    a `--body`, and they are exactly what `--pr` opens the pull request with
    for the same run, the apostrophe and the backticks in the body included.
    Never `--fill`, which reads the commits of wherever the line is pasted."""
    plain, opened = (tmp_path / "plain" / PROJECT, tmp_path / "opened" / PROJECT)
    for root in (plain, opened):
        shutil.copytree(project["clone"], root, symlinks=True)
        if accepted:
            edit(root, LOCAL, commit=True)
    extra = ("--accept-local", LOCAL) if accepted else ()

    result = run_apply(plain, project, "b", "--branch", "shape/update-n7",
                       *extra)
    assert result.returncode == 0, result.stdout + result.stderr
    argv = create_argv(next_line_of(result.stdout))
    title, body = opened_by_pr(update_shape, gh_calls, opened, project, "b",
                               "shape/update-n7", *extra)

    assert argv == ["gh", "pr", "create", "--repo", f"{ORG}/{PROJECT}",
                    "--base", "main", "--head", "shape/update-n7", "--title",
                    title, "--body", body]
    assert "--fill" not in argv
    assert "openRepoShape's `update-shape.py`" in body, "quoted whole"
    assert (LOCAL in body) is accepted


def test_the_line_after_a_push_carries_the_words_too(update_shape, tmp_path,
                                                     capsys):
    """`--push` has pushed, so the line is the `gh pr create` alone. It is
    given the words by the run that made the commit; a caller that came
    another way is given the standard's own repository to name."""
    (tmp_path / MANIFEST).write_text(
        "tracking_branch: main\nlegs:\n  - role: assembly\n"
        "    repository: acme/Atlas\n", encoding="utf-8")
    target = "ab" * 20
    kept = update_shape.pull_request_words("acme/Shape", target, MANIFEST,
                                           [LOCAL])
    fallback = update_shape.pull_request_words(SHAPE_REPOSITORY, target,
                                               MANIFEST)
    for stash, words in ((kept, kept), (None, fallback)):
        args = SimpleNamespace(branch="shape/x", push=True, pr=False)
        if stash:
            args.pull_request_words = stash

        update_shape.next_line(tmp_path, args, [], target, [])

        line = capsys.readouterr().out.strip()
        assert line.count("\n") == 0
        assert create_argv(line) == [
            "gh", "pr", "create", "--repo", "acme/Atlas", "--base", "main",
            "--head", "shape/x", "--title", words[0], "--body", words[1]]


def test_the_bare_form_a_failed_push_prints_carries_the_words_too(
        update_shape, tmp_path):
    """`pull_request_line` builds the `gh pr create` that `landing_failed`
    prints when `--push` fails, and it is the plain `--branch` line's twin: a
    bare one there would stop in a shell with no terminal for the same
    reason. Without `--pr` it leaves `--repo` off where the manifest names
    none, and carries the title and the body all the same."""
    (tmp_path / MANIFEST).write_text("tracking_branch: trunk\n",
                                     encoding="utf-8")
    args = SimpleNamespace(branch="shape/x", push=True, pr=False)
    upstream = SimpleNamespace(repository="o/r")
    title, body = update_shape.pull_request_words("o/r", "cd" * 20, MANIFEST,
                                                  [LOCAL])

    create = update_shape.pull_request_line(
        tmp_path, args, "cd" * 20, upstream, update_shape.PROJECT_KIND,
        [LOCAL])

    assert create == ["gh", "pr", "create", "--base", "trunk", "--head",
                      "shape/x", "--title", title, "--body", body]
    assert title == f"Re-sync the shape copies to o/r @ {'cd' * 6}"
    assert LOCAL in body


class ClosedPipe(io.StringIO):
    """A stdout whose reader has gone away, as under `... | true`: it takes
    what is printed, and its flush raises, as the one
    `tests/test_adopt_late_failure.py` gives `adopt-project.py`."""

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_a_refused_push_is_reported_on_stderr_whatever_stdout_is(
        update_shape, repository, tmp_path, monkeypatch):
    """A PUSH ORIGIN REFUSES, after the commit, and nobody reads stdout any
    more (#1218). `landing_failed` flushed stdout bare before it said
    anything, so the flush's `BrokenPipeError` went over its whole report:
    stderr said neither which step failed nor that the commit stands. Both
    reach stderr, and the run ends as a landing that is not complete. The
    NEXT line is stdout's, handed to stdout whatever it does with it."""
    git("checkout", "-q", "-b", "shape/x", cwd=repository)
    git("remote", "add", "origin", str(tmp_path / "no-such-remote.git"),
        cwd=repository)
    head = git("rev-parse", "HEAD", cwd=repository).stdout.strip()
    stdout, stderr = ClosedPipe(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    args = SimpleNamespace(branch="shape/x", push=True, pr=False)

    with pytest.raises(update_shape.LandingIncomplete):
        update_shape.push_branch(repository, args, ["gh", "pr", "create"])

    said = stderr.getvalue()
    assert said.startswith(
        "REFUSED pushing shape/x. THE EXACT COMMAND WAS:\n"
        "    git push -q -u -- origin refs/heads/shape/x:refs/heads/shape/x"
        "\n"), said
    assert (f"shape/x carries the re-pin at {head[:12]}, and origin does not "
            "have it yet: that commit stands and nothing was rolled back."
            ) in said, said
    assert stdout.getvalue().startswith("\nNEXT  git -C "), stdout.getvalue()


# --- the words are true in every state (review of PR #558) -------------------


def test_a_pull_request_that_re_copied_nothing_does_not_say_it_did(
        update_shape, gh_calls, project, root):
    """`CHANGED` is the one file upstream changed at B, and this project
    edited it: its row is `both`, accepted, so NOTHING is re-copied. The body
    opened with "the copied shape files were re-copied from the upstream" in
    every state; it claims no copy was re-copied, and names the one kept."""
    edit(root, CHANGED, commit=True)

    _, body = opened_by_pr(update_shape, gh_calls, root, project, "b",
                           "shape/update-n3b", "--accept-local", CHANGED)

    assert body.startswith("Written by openRepoShape's `update-shape.py`: "
                           "`contracts/shape-pin.yaml` and `project.yaml` "
                           "re-pinned onto "), body
    assert "shape files were re-copied" not in body
    assert f" {CHANGED} was not re-copied: " in body


def test_a_holders_pull_request_words_name_family_yaml_and_not_project_yaml(
        update_shape, gh_calls, holder_project, tmp_path):
    """A holder has a `family.yaml` and no `project.yaml`, and the body said
    `project.yaml` was re-pinned: in what `--pr` opens the pull request
    with, in the plain `--branch` NEXT line and in the line a failed
    `--push` prints. The words are read whole here, never stripped."""
    printed = tmp_path / "printed" / HOLDER
    opened = tmp_path / "opened" / HOLDER
    for holder in (printed, opened):
        shutil.copytree(holder_project["clone"], holder, symlinks=True)

    result = run_script(UPDATE, "apply", "--root", str(printed), "--yes",
                        "--upstream", str(holder_project["upstream"]), "--at",
                        holder_project["b"], "--branch", "shape/update-fam")
    assert result.returncode == 0, result.stdout + result.stderr
    argv = create_argv(next_line_of(result.stdout))
    printed_body = argv[argv.index("--body") + 1]
    _, opened_body = opened_by_pr(update_shape, gh_calls, opened,
                                  holder_project, "b", "shape/update-fam")

    assert printed_body == opened_body
    for body in (printed_body, opened_body):
        assert ("`contracts/shape-pin.yaml` and `family.yaml` re-pinned onto "
                f"{holder_project['b']}") in body, body
        assert "project.yaml" not in body, body
    args = SimpleNamespace(branch="shape/x", push=True, pr=False)
    failed_push = update_shape.pull_request_line(
        opened, args, holder_project["b"],
        SimpleNamespace(repository=SHAPE_REPOSITORY), update_shape.FAMILY_KIND)
    assert "`family.yaml` re-pinned" in failed_push[failed_push.index(
        "--body") + 1]
    assert "project.yaml" not in " ".join(failed_push)


def failing_once(command, calls, module):
    """`gh`, as a stub: no pull request exists, and the first one it is asked
    to open fails, as it does when `gh` is not logged in."""
    if command[:3] == ["gh", "pr", "list"]:
        return "[]"
    if sum(1 for each in calls if each[:3] == ["gh", "pr", "create"]) == 1:
        raise module.CommandFailed(command, None, 1, "stubbed: gh failed")
    return "https://example.invalid/pull/1"


def creations(calls: list) -> list[list[str]]:
    return [call for call in calls if call[:3] == ["gh", "pr", "create"]]


def adopt_the_makefile(root: Path) -> None:
    """As an in-place adoption leaves it: the project's own `Makefile` carries
    a block the standard's does not, and the pin's row records THOSE bytes.
    Committed, so `--branch` takes the run."""
    makefile = root / "Makefile"
    makefile.write_bytes(makefile.read_bytes() + b"\n# the adoption's block\n")
    pin = root / PIN
    old = pin_rows(root)["Makefile"]
    text, count = re.subn(old, file_sha256(makefile),
                          pin.read_bytes().decode("utf-8"), flags=re.I)
    assert count == 1, "fixture: one row holds that digest"
    pin.write_bytes(text.encode("utf-8"))
    git("add", "--", "Makefile", PIN, cwd=root)
    git("commit", "-q", "-m", "Adopt in place", cwd=root)
    # ... and landed: the tracking branch the clone has seen holds it too.
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=root)


KEPT = (f"{LOCAL} was not re-copied: `--accept-local` kept it as the project "
        "holds it, so the pin's row for it records a digest of the project's "
        "own bytes, not of the upstream's file.")


@pytest.mark.parametrize("adopted", [False, True],
                         ids=["plain", "adopted-makefile"])
def test_the_rerun_that_opens_the_missing_pull_request_names_what_was_kept(
        update_shape, monkeypatch, project, root, adopted):
    """THE RE-RUN (`_finish_landing`). The first run commits, and its `gh pr
    create` fails; `apply --pr` run again has nothing to write and opens the
    pull request, with no rows to say what `--accept-local` kept. Its body
    names the same path, read back out of the pin. An in-place adoption's
    `Makefile` row records bytes the standard's file does not hold and was
    never accepted: it is not named, and the body says what is true."""
    calls = stub_gh(update_shape, monkeypatch, failing_once)
    if adopted:
        adopt_the_makefile(root)
    edit(root, LOCAL, commit=True)

    first = apply_in_process(update_shape, root, project, "b",
                             "shape/update-rerun", "--accept-local", LOCAL)
    again = apply_in_process(update_shape, root, project, "b",
                             "shape/update-rerun")

    assert first == 2 and again == 0
    opened_first, opened_again = [call[call.index("--body") + 1]
                                  for call in creations(calls)]
    assert opened_first.endswith(KEPT), opened_first
    assert opened_again == opened_first, (
        "the re-run opens the very command the first run tried")
    assert "Makefile" not in opened_again


def test_the_rerun_of_a_run_that_accepted_nothing_names_nothing(
        update_shape, monkeypatch, project, root):
    calls = stub_gh(update_shape, monkeypatch, failing_once)
    adopt_the_makefile(root)

    first = apply_in_process(update_shape, root, project, "b",
                             "shape/update-rerun-none")
    again = apply_in_process(update_shape, root, project, "b",
                             "shape/update-rerun-none")

    assert first == 2 and again == 0
    body = creations(calls)[1]
    assert "not re-copied" not in body[body.index("--body") + 1]


# --- N1: a commit line with nothing to commit -----------------------------------


@pytest.fixture
def repository(tmp_path) -> Path:
    """A root that is a git repository holding the pin and the manifest, as
    HEAD commits them."""
    where = tmp_path / "root"
    (where / "contracts").mkdir(parents=True)
    (where / PIN).write_bytes(b"commit: aaaa\n")
    (where / MANIFEST).write_bytes(b"name: Atlas\n")
    git("init", "-q", "-b", "main", cwd=where)
    git("add", "--", PIN, MANIFEST, cwd=where)
    git("commit", "-q", "-m", "Scaffold", cwd=where)
    return where


def said_by_next_line(update_shape, root, paths, added=(), capsys=None) -> str:
    args = SimpleNamespace(branch=None, push=False, pr=False)
    update_shape.next_line(root, args, list(paths), "ab" * 20, list(added))
    return capsys.readouterr().out


def test_no_commit_line_when_every_written_path_is_what_head_commits(
        update_shape, repository, capsys):
    out = said_by_next_line(update_shape, repository, [PIN, MANIFEST],
                            capsys=capsys)

    assert out.startswith("NEXT  nothing to commit: the working tree now "
                          "holds what HEAD commits at "
                          f"{PIN}, {MANIFEST}"), out
    assert out.count("\n") == 1
    assert "commit -m" not in out and "checkout -b" not in out


def test_the_commit_line_stands_when_one_written_path_differs_from_head(
        update_shape, repository, capsys):
    (repository / PIN).write_bytes(b"commit: bbbb\n")

    out = said_by_next_line(update_shape, repository, [PIN, MANIFEST],
                            capsys=capsys)

    assert out.startswith("NEXT  git -C "), out
    assert " commit -m 'Re-sync the shape @ " in out


def test_a_run_that_added_a_file_still_gets_its_commit_line(
        update_shape, repository, capsys):
    """An `--add` file is not in HEAD, so what this run wrote is a change
    even when the pin and the manifest are HEAD's bytes."""
    (repository / "docs").mkdir()
    (repository / "docs" / "new.md").write_bytes(b"new\n")

    out = said_by_next_line(update_shape, repository,
                            [PIN, MANIFEST, "docs/new.md"], ["docs/new.md"],
                            capsys)

    assert "--literal-pathspecs add -f -- docs/new.md" in out, out
    assert " commit -m 'Re-sync the shape @ " in out


def test_a_root_with_no_commit_gets_the_line_it_always_got(
        update_shape, tmp_path, capsys):
    """No HEAD, nothing to compare with: even paths that are not on disk, for
    which HEAD and the disk agree where there is a HEAD, get the line."""
    where = tmp_path / "fresh"
    where.mkdir()
    git("init", "-q", "-b", "main", cwd=where)

    out = said_by_next_line(update_shape, where, [PIN, MANIFEST],
                            capsys=capsys)

    assert out.startswith("NEXT  git -C "), out
    assert "nothing to commit" not in out


@WINDOWS_SKIP
def test_a_written_path_whose_mode_differs_from_head_still_gets_its_commit_line(
        update_shape, repository, capsys):
    """`_not_what_head_commits` compares blobs, which a mode change leaves
    alone, and git commits the change: the file is HEAD's bytes and not
    HEAD's mode, so "nothing to commit" would be false (review of PR #558).
    POSIX only: Windows runs with `core.fileMode=false`."""
    assert git("config", "core.fileMode", cwd=repository).stdout.strip() \
        == "true", "fixture: modes are tracked"
    (repository / PIN).chmod(0o755)
    assert git("diff", "--name-only", "HEAD", cwd=repository).stdout.split() \
        == [PIN], "fixture: git sees the mode change"

    out = said_by_next_line(update_shape, repository, [PIN, MANIFEST],
                            capsys=capsys)

    assert out.startswith("NEXT  git -C "), out
    assert " commit -m 'Re-sync the shape @ " in out
    assert "nothing to commit" not in out


def test_an_apply_that_moves_the_pin_back_to_heads_prints_no_commit_line(
        project, root):
    """THE ISSUE'S RUN, end to end. `apply` at B leaves the update written and
    uncommitted, and prints its commit line. `apply` at A then moves the copy,
    the pin and the manifest back to the bytes HEAD commits: the tree is clean
    and the one NEXT line says there is nothing to commit, where it used to
    print a `checkout -b && commit` that git answers with "nothing to
    commit"."""
    first = run_apply(root, project, "b")
    assert first.returncode == 0, first.stdout + first.stderr
    assert " commit -m 'Re-sync the shape @ " in next_line_of(first.stdout)
    assert git("status", "--porcelain", cwd=root).stdout != ""

    back = run_apply(root, project, "a")

    assert back.returncode == 0, back.stdout + back.stderr
    assert git("status", "--porcelain", cwd=root).stdout == ""
    line = next_line_of(back.stdout)
    assert line.startswith("NEXT  nothing to commit: "), line
    assert "commit -m" not in back.stdout
