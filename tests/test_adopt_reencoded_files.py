# SPDX-License-Identifier: Apache-2.0
"""Every other file the split's git would store as other bytes (#654).

#530's D5(a) line made `check` ask this machine's `git add` about the
source's own root `.gitattributes`, the one file the split writes into. Any
other file the plan keeps or moves, and the shape's pinned copies, still
passed `check` and failed after both leg remotes existed. Measured on main
a5245427 with git 2.43, in real adoptions:

* a kept CRLF `notes.txt` under `* text eol=lf`, a kept CRLF
  `docs/.gitattributes`, a kept `$Id: deadbeef $` under `ident`, a kept file
  under a filter this machine defines, and a kept `*.txt` whose
  `working-tree-encoding` rule went to a leg with the root's `.gitattributes`
  each ended `adopt-lost`;
* the same CRLF or `ident` file sent to a leg, a CRLF file under
  `core.safecrlf=true` sent to a leg and a `src/*.py` under that filter were
  refused by the mount's `git rm` ("local modifications") at mounting the
  legs;
* a kept file that is not UTF-8 under `working-tree-encoding`, a kept CRLF
  file under `core.safecrlf=true` and the pinned scripts under `*.py
  working-tree-encoding=UTF-16LE-BOM` (#530's rider) stopped the split
  committing, in git's words; `filter.<name>.required` with no command
  stopped the leg's extraction;
* and `/scripts/*.py filter=<upper>` said `adoption verified` over uppercased
  pinned scripts, whose `validate-pins.py` then died with a `SyntaxError`.

Git reads a file again, and stores it through its rules, where it cannot
trust the stat data: every file of a small source, and of a large one those
checked out in the second git wrote its index. `check` now asks about every
file as `plan-file-reencoded`, and `execute` refuses it before any leg.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

from conftest import (ADOPT, findings, git, make_source_repo, planned,
                      refused_before_any_leg, run_script)
from test_adopt_nested_attributes import (EMPTY_TREE, GITHUB_ATTRIBUTES,
                                          REENCODED, ROOT, ROOT_ATTRIBUTES,
                                          SOURCE, adopted_by_execute, checked,
                                          command_scope, committed_raw,
                                          needs_filter_repo)

#: The finding, and the code of `execute`'s refusal.
REENCODED_FILES = "plan-file-reencoded"
NOTES = "notes.txt"
SPEC = "spec"
CODE = "code"
DROP = "drop"
CRLF = b"one\r\ntwo\r\n"
TEXT_EOL_LF = b"* text eol=lf\n"
TXT_ENCODING = b"*.txt working-tree-encoding=UTF-16LE\n"
PY_UTF16_BOM = b"*.py working-tree-encoding=UTF-16LE-BOM\n"
NOT_UTF8 = b"caf\xe9\n"
EXPANDED_ID = b"$Id: deadbeef $\n"
#: A filter this machine defines: its clean step uppercases.
UPPER = "w654upper"
UPPER_CLEAN = ((f"filter.{UPPER}.clean", "tr a-z A-Z"),)
#: A filter git must run, with no command to run on the way in.
REQUIRED = "w654req"
REQUIRED_ONLY = ((f"filter.{REQUIRED}.required", "true"),)
SAFECRLF = (("core.safecrlf", "true"),)
#: Where each group of findings starts.
KEPT_GROUP = "the plan keeps "
MOVED_GROUP = "the plan sends "
COPIES_GROUP = "the source's rules make this machine's `git add` store "
REFUSED_GROUP = "this machine's git refuses "
NAMED_NOTES = ": `notes.txt`."
#: The five shape scripts the pin names, in its order, as they land.
SCRIPTS = ("scripts/validate-pins.py", "scripts/validate-manifest.py",
           "scripts/bootstrap.py", "scripts/repo_shape.py",
           "scripts/validate-repository-naming.py")


def raw_plan(base: Path, files: dict, answers: dict) -> Path:
    """The plan for `SOURCE` and `files`, each committed byte for byte
    (`committed_raw`), with `answers` given."""
    source = make_source_repo(base / "Thing", tree=dict(SOURCE), edits=())
    for name, data in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        committed_raw(source, name, data)
    return planned(source, base, answers)


def configure(monkeypatch: pytest.MonkeyPatch, pairs) -> None:
    """Each `(key, value)` of `pairs` in git's command scope, after what
    the environment holds, for this process and every git it starts."""
    held = int(os.environ.get("GIT_CONFIG_COUNT") or 0)
    for n, (key, value) in enumerate(pairs, held):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{n}", key)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{n}", value)
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(held + len(pairs)))


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_reencoded_files",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encoded_attributes() -> dict:
    return {ROOT_ATTRIBUTES: TXT_ENCODING}


#: `(files, answers, config, [(where the finding starts, what it says)])`
#: for each source the split's git stores otherwise, in `check`'s order.
FOUND = [
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: ROOT},
                 (), [(KEPT_GROUP, NAMED_NOTES)], id="kept-crlf-under-text"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: SPEC},
                 (), [(MOVED_GROUP, NAMED_NOTES)], id="sent-crlf-under-text"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: DROP},
                 (), [(MOVED_GROUP, NAMED_NOTES)],
                 id="dropped-crlf-under-text"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF,
                  "docs/.gitattributes": b"*.md text\r\n",
                  "docs/a.md": b"# a\n"}, {"docs/": ROOT}, (),
                 [(KEPT_GROUP, ": `docs/.gitattributes`.")],
                 id="kept-nested-attributes-crlf"),
    pytest.param({ROOT_ATTRIBUTES: b"*.txt ident\n", NOTES: EXPANDED_ID},
                 {NOTES: ROOT}, (), [(KEPT_GROUP, NAMED_NOTES)],
                 id="kept-expanded-ident"),
    pytest.param({ROOT_ATTRIBUTES: b"*.txt ident\n", NOTES: EXPANDED_ID},
                 {NOTES: CODE}, (), [(MOVED_GROUP, NAMED_NOTES)],
                 id="sent-expanded-ident"),
    pytest.param({**encoded_attributes(), NOTES: b"abcd\n"},
                 {NOTES: ROOT, ROOT_ATTRIBUTES: SPEC}, (),
                 [(KEPT_GROUP, NAMED_NOTES)],
                 id="kept-file-whose-encoding-rule-goes-to-a-leg"),
    pytest.param({ROOT_ATTRIBUTES: f"*.txt filter={UPPER}\n".encode(),
                  NOTES: b"abc\n"}, {NOTES: ROOT}, UPPER_CLEAN,
                 [(KEPT_GROUP, NAMED_NOTES)], id="kept-under-a-filter"),
    pytest.param({ROOT_ATTRIBUTES: f"*.py filter={UPPER}\n".encode()}, {},
                 UPPER_CLEAN,
                 [(MOVED_GROUP, ": `src/app/main.py`."),
                  (COPIES_GROUP, "5 pinned shape copies")],
                 id="sent-and-copies-under-a-filter"),
    pytest.param({ROOT_ATTRIBUTES: f"/scripts/*.py filter={UPPER}\n".encode()},
                 {}, UPPER_CLEAN, [(COPIES_GROUP, "5 pinned shape copies")],
                 id="copies-alone-under-a-filter"),
    pytest.param({ROOT_ATTRIBUTES: PY_UTF16_BOM}, {}, (),
                 [(REFUSED_GROUP, "from UTF-16LE-BOM to UTF-8`)")],
                 id="copies-refused-by-an-encoding"),
    pytest.param({ROOT_ATTRIBUTES: b"* working-tree-encoding=UTF-16LE\n"
                                   b".gitattributes -working-tree-encoding\n"},
                 {}, (), [(REFUSED_GROUP, "from UTF-16LE to UTF-8`)")],
                 id="copies-refused-where-the-rules-are-exempt"),
    pytest.param({**encoded_attributes(), NOTES: NOT_UTF8}, {NOTES: ROOT},
                 (), [(REFUSED_GROUP, "(git said `fatal: failed to encode "
                                      "'notes.txt' from UTF-16LE to UTF-8`)")],
                 id="kept-bytes-the-encoding-refuses"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: ROOT},
                 SAFECRLF, [(REFUSED_GROUP, "(git said `fatal: CRLF would be "
                                            "replaced by LF in notes.txt`)")],
                 id="kept-crlf-under-safecrlf"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: SPEC},
                 SAFECRLF, [(MOVED_GROUP, NAMED_NOTES)],
                 id="sent-crlf-under-safecrlf"),
    pytest.param({ROOT_ATTRIBUTES: f"*.txt filter={REQUIRED}\n".encode(),
                  NOTES: b"abc\n"}, {NOTES: ROOT}, REQUIRED_ONLY,
                 [(REFUSED_GROUP, f"clean filter '{REQUIRED}' failed`)")],
                 id="required-filter-with-no-command"),
    pytest.param({ROOT_ATTRIBUTES: f"*.txt filter={REQUIRED}\n".encode(),
                  NOTES: b"abc\n"}, {NOTES: ROOT},
                 (*REQUIRED_ONLY, (f"filter.{REQUIRED}.smudge", "false")),
                 [(REFUSED_GROUP, f"smudge filter {REQUIRED} failed`)")],
                 id="required-smudge-that-fails"),
]


@pytest.mark.parametrize(("files", "answers", "config", "said"), FOUND)
def test_check_finds_what_the_split_would_store_otherwise(
        monkeypatch, tmp_path, files, answers, config, said):
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    found = findings(plan)
    assert [code for code, _ in found] == [REENCODED_FILES] * len(said), found
    for (_, detail), (start, part) in zip(found, said):
        assert detail.startswith(start), detail
        assert part in detail, detail


@pytest.mark.parametrize(("files", "answers", "config"), [
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: ROOT},
                 (), id="kept"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF}, {NOTES: SPEC},
                 (), id="sent"),
    pytest.param({ROOT_ATTRIBUTES: f"/scripts/*.py filter={UPPER}\n".encode()},
                 {}, UPPER_CLEAN, id="copies"),
    pytest.param({**encoded_attributes(), NOTES: NOT_UTF8}, {NOTES: ROOT}, (),
                 id="refused")])
def test_execute_refuses_it_before_any_leg_exists(adopter, monkeypatch,
                                                 tmp_path, files, answers,
                                                 config):
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == REENCODED_FILES


#: Sources the split's git stores as their blobs, each measured to adopt on
#: main a5245427: a CRLF blob `text=auto` leaves alone, an LF blob under
#: `text`, a CRLF blob with no rule under `core.autocrlf=true` (which
#: `git add --renormalize` would have re-stored), a filter with no driver
#: here, a file sent to a leg under an encoding, valid or not (the mount's
#: `git rm` reads a conversion git cannot make as no change), pinned
#: scripts under `*.py text eol=crlf` with `core.safecrlf=true`, which the
#: block the split appends keeps LF, and a kept `.github/workflows/` whose
#: filter rule's `.github/.gitattributes` goes to a leg: the mount's `git
#: rm` takes the rule away before the split's `git add` reads the files.
STORED_AS_THEIR_BLOBS = [
    pytest.param({ROOT_ATTRIBUTES: b"* text=auto\n", NOTES: CRLF},
                 {NOTES: ROOT}, (), id="crlf-under-text-auto"),
    pytest.param({ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: b"one\ntwo\n"},
                 {NOTES: ROOT}, (), id="lf-under-text"),
    pytest.param({NOTES: CRLF}, {NOTES: ROOT}, (("core.autocrlf", "true"),),
                 id="crlf-with-no-rule-under-autocrlf"),
    pytest.param({ROOT_ATTRIBUTES: b"*.txt filter=nodriver\n",
                  NOTES: b"abc\n"}, {NOTES: ROOT}, (),
                 id="a-filter-with-no-driver-here"),
    pytest.param({**encoded_attributes(), NOTES: "café\n".encode()},
                 {NOTES: SPEC}, (), id="sent-under-an-encoding"),
    pytest.param({**encoded_attributes(), NOTES: NOT_UTF8}, {NOTES: SPEC},
                 (), id="sent-bytes-the-encoding-refuses"),
    pytest.param({ROOT_ATTRIBUTES: b"*.py text eol=crlf\n"}, {}, SAFECRLF,
                 id="copies-the-block-keeps-lf-under-safecrlf"),
    pytest.param({GITHUB_ATTRIBUTES: f"*.yml filter={UPPER}\n".encode()},
                 {GITHUB_ATTRIBUTES: CODE, ".github/workflows/": ROOT},
                 UPPER_CLEAN, id="kept-where-the-rule-goes-to-a-leg"),
]


@pytest.mark.parametrize(("files", "answers", "config"),
                         STORED_AS_THEIR_BLOBS)
def test_what_the_split_stores_as_its_blob_is_no_finding(
        monkeypatch, tmp_path, files, answers, config):
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    assert findings(plan) == []


@needs_filter_repo
@pytest.mark.parametrize(("files", "answers", "config"),
                         STORED_AS_THEIR_BLOBS)
def test_what_the_split_stores_as_its_blob_adopts(monkeypatch, tmp_path,
                                                  files, answers, config):
    plan = raw_plan(tmp_path, files, answers)
    configure(monkeypatch, config)
    adopted_by_execute(plan, tmp_path)


def test_the_kept_and_the_sent_findings_say_what_follows_and_the_way_out(
        tmp_path):
    files = {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF, "more.txt": CRLF}
    found = findings(raw_plan(tmp_path, files,
                              {NOTES: ROOT, "more.txt": SPEC}))
    stored = ("this machine's `git add` would store it as other bytes than "
              "its blob once the split's checkout has written it")
    again = ("each one git reads again (every file of a small source; of a "
             "large one, those checked out in the second git wrote its index)")
    way_out = ("Commit it in the source as git stores it (`git add "
               "--renormalize -- <path>`, then commit), or change the rule "
               "that reaches it, and re-run `plan`.")
    assert found == [
        (REENCODED_FILES,
         f"the plan keeps 1 file in the assembly root, and {stored}: "
         f"`notes.txt`. The split's `git add -A` stores again {again}, and "
         "the verification then reports it as `adopt-lost`, in no leg and "
         f"not in the root tree, after both legs exist. {way_out}"),
        (REENCODED_FILES,
         f"the plan sends 1 file to a leg or drops it, and {stored}: "
         f"`more.txt`. The mount's `git rm` refuses {again}, as holding "
         "local modifications, so the split stops at mounting the legs, "
         f"after both legs exist. {way_out}")]


def test_the_copies_finding_gives_each_copy_the_line_that_keeps_the_rule_off(
        monkeypatch, tmp_path):
    rules = f"/scripts/*.py filter={UPPER}\n".encode()
    plan = raw_plan(tmp_path, {ROOT_ATTRIBUTES: rules}, {})
    configure(monkeypatch, UPPER_CLEAN)
    found = findings(plan)
    lines = ", ".join(f"`/{path} -filter`" for path in SCRIPTS[:-1])
    assert found == [(
        REENCODED_FILES,
        "the source's rules make this machine's `git add` store 5 pinned "
        "shape copies as other bytes than the split writes: "
        + ", ".join(f"`{path}`" for path in SCRIPTS[:-1])
        + f" and `{SCRIPTS[-1]}`. The split would commit them as copies the "
        "shape's pin does not describe, and `execute` would say `adoption "
        "verified` over them. Keep the rules off them with these lines after "
        f"them in the source's root `.gitattributes`: {lines} and "
        f"`/{SCRIPTS[-1]} -filter`, or narrow the rules, commit, and re-run "
        "`plan`.")]


def test_a_refusal_says_where_execute_stops_and_the_way_out(monkeypatch,
                                                           tmp_path):
    plan = raw_plan(tmp_path, {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF},
                    {NOTES: ROOT})
    configure(monkeypatch, SAFECRLF)
    found = findings(plan)
    assert found == [(
        REENCODED_FILES,
        "this machine's git refuses to store again what the plan keeps in "
        "the assembly root, as the split's `git add -A` does (git said "
        "`fatal: CRLF would be replaced by LF in notes.txt`), so `execute` "
        "would stop there, after the leg repositories exist. Commit the file "
        "git names in the source as git stores it, or change the rule or the "
        "setting that refuses it, and re-run `plan`.")]


def test_the_finding_names_ten_paths_and_counts_the_rest(tmp_path):
    names = [f"notes/n{n:02d}.txt" for n in range(1, 13)]
    files = {ROOT_ATTRIBUTES: TEXT_EOL_LF, **dict.fromkeys(names, CRLF)}
    found = findings(raw_plan(tmp_path, files, {"notes/": ROOT}))
    assert [code for code, _ in found] == [REENCODED_FILES], found
    named = ", ".join(f"`{name}`" for name in names[:10])
    assert found[0][1].startswith(
        f"the plan keeps 12 files in the assembly root, and this machine's "
        "`git add` would store them as other bytes than their blobs once the "
        f"split's checkout has written them: {named} and 2 more. "), found


def test_the_roots_own_attributes_is_the_d5a_question_alone(tmp_path):
    """The source's root `.gitattributes`, which the split writes into, is
    asked by `plan-attributes-reencoded` (#530's D5(a)), and named once."""
    crlf_rules = {ROOT_ATTRIBUTES: b"* text eol=lf\r\n"}
    found = findings(raw_plan(tmp_path, crlf_rules, {}))
    assert [code for code, _ in found] == [REENCODED], found


def opened(adopter, plan: Path, base: Path):
    loaded = adopter.Plan.load(plan)
    (base / "work").mkdir()
    return loaded, loaded.open_source(None, base / "work")


def test_a_source_no_rule_reaches_checks_out_only_its_rules(adopter,
                                                            monkeypatch,
                                                            tmp_path):
    """A source whose rules reach none of its files costs a `read-tree` and
    a `check-attr`: only its `.gitattributes` are checked out, to ask the
    pinned copies under them."""
    plan, source = opened(adopter, raw_plan(
        tmp_path, {ROOT_ATTRIBUTES: b"*.png binary\n"}, {}), tmp_path)
    held = []
    real = adopter._SplitRehearsal.hold

    def hold(self, index, rows):
        held.append((index, sorted(path for path, _, _ in rows)))
        return real(self, index, rows)

    monkeypatch.setattr(adopter._SplitRehearsal, "hold", hold)
    assert adopter._reencoded_files_findings(plan, source,
                                             source.tree()) == []
    assert held[0] == (adopter.CHECKED_OUT, [ROOT_ATTRIBUTES]), held


def test_every_file_is_read_again_whatever_the_clock(adopter, monkeypatch,
                                                     tmp_path):
    """Git trusts an entry's stat data, and reads the file again only where
    the clock leaves it in doubt: 852 to 6,803 of 20,000 CRLF files in
    three identical runs of the split's own clone and `git add -A`. The
    files a rule reaches are checked out through an index with no stat
    data, so git reads every one again, whatever the clock says."""
    plan, source = opened(adopter, raw_plan(
        tmp_path, {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF},
        {NOTES: ROOT}), tmp_path)
    stats = []
    real = adopter._SplitRehearsal.checkout

    def checkout(self, index):
        said = real(self, index)
        stats.append(self.git(["ls-files", "--debug"], index).stdout)
        return said

    monkeypatch.setattr(adopter._SplitRehearsal, "checkout", checkout)
    adopter._reencoded_files_findings(plan, source, source.tree())
    listed = stats[0].decode()
    assert listed.count("mtime:") > 1, listed
    assert listed.count("mtime: 0:0") == listed.count("mtime:"), listed


def env_steering(tmp_path: Path, steer: dict) -> subprocess.CompletedProcess:
    plan = raw_plan(tmp_path, {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF},
                    {NOTES: ROOT})
    return checked(plan, steer)


@pytest.mark.parametrize("steer", [
    pytest.param({"GIT_ATTR_SOURCE": "HEAD"}, id="git-attr-source-head"),
    pytest.param({"GIT_ATTR_SOURCE": EMPTY_TREE},
                 id="git-attr-source-the-empty-tree"),
    pytest.param(command_scope("attr.tree", EMPTY_TREE),
                 id="attr-tree-in-the-command-scope")])
def test_no_tree_this_machine_names_steers_the_question(tmp_path, steer):
    """The throwaway repository has no commit for `HEAD` to name, and the
    empty tree would make git read no rule: neither is inherited."""
    result = env_steering(tmp_path, steer)
    assert "REFUSED" not in result.stderr, result.stderr
    assert f"FINDING {REENCODED_FILES}: {KEPT_GROUP}" in result.stderr, \
        result.stderr


@pytest.mark.parametrize(("old", "new"), [
    pytest.param("  spec_path: spec\n", "  spec_path: ../spec\n",
                 id="a-bad-leg-path"),
    pytest.param("pins: []\n", "pins: nope\n", id="pins-that-are-no-list")])
def test_a_malformed_plan_gets_findings_not_a_traceback(tmp_path, old, new):
    plan = raw_plan(tmp_path, {ROOT_ATTRIBUTES: TEXT_EOL_LF, NOTES: CRLF},
                    {NOTES: ROOT})
    text = plan.read_text(encoding="utf-8")
    assert old in text
    plan.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    result = checked(plan, {})
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stderr


def test_a_link_the_checkout_writes_is_never_written_through(monkeypatch,
                                                             tmp_path):
    """The source keeps a root `.gitattributes` that is a symlink out of it,
    `../../../victim.txt`, which leads to the same file from the source and
    from the throwaway repository in `TMPDIR`. `plan-root-symlink` names it
    alone: the question writes the shape's `.gitattributes` in the link's
    place, never through it (at 0224f96a `check` overwrote that file), and
    does not ask about the link it replaced."""
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"left alone\n")
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    monkeypatch.setenv("TMPDIR", str(temporary))
    source = make_source_repo(tmp_path / "a" / "b" / "Thing",
                              tree=dict(SOURCE), edits=())
    try:
        (source / ROOT_ATTRIBUTES).symlink_to("../../../victim.txt")
    except OSError as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    git("add", ROOT_ATTRIBUTES, cwd=source)
    git("commit", "-qm", "Link the root's rules out of the source",
        cwd=source)
    result = run_script(ADOPT, "check", "--plan",
                        str(planned(source, tmp_path, {ROOT_ATTRIBUTES: ROOT})),
                        "--work-dir", str(tmp_path / "work"))
    assert [line.split(":")[0] for line in result.stderr.splitlines()
            if line.startswith("FINDING ")] == ["FINDING plan-root-symlink"], \
        result.stderr
    assert victim.read_bytes() == b"left alone\n"


def test_a_kept_file_named_shape_is_that_finding_alone(tmp_path):
    """The root keeps its own `.gitattributes` and a FILE named `shape`,
    where the shape's own `shape/.gitattributes` would go beside it:
    `plan-root-blocks-shape-copy` names that (#262), and the question still
    lays the split's root out, the kept file giving way in its index."""
    source = make_source_repo(tmp_path / "Thing",
                              tree={**SOURCE, "shape": "a file\n"}, edits=())
    committed_raw(source, ROOT_ATTRIBUTES, TEXT_EOL_LF)
    found = findings(planned(source, tmp_path, {"shape": ROOT}))
    assert [code for code, _ in found] == ["plan-root-blocks-shape-copy"], \
        found


def test_the_root_is_asked_as_the_split_writes_it(monkeypatch, tmp_path):
    """No rule of the source's own, and `core.autocrlf=true` with
    `core.safecrlf=true`: the clone writes the kept `.gitignore` CRLF, the
    split writes the shape's `* text=auto eol=lf` at the root, and its `git
    add -A` refuses the file it would store as LF (replayed by hand with git
    2.43). Asked under no root rule instead, the pinned copies would be the
    ones refused. `execute` meets the mounts' own `.gitmodules` first, which
    no question asks (measured: `LF would be replaced by CRLF in
    .gitmodules`); the finding stands before any leg either way."""
    plan = planned(make_source_repo(tmp_path / "Thing", tree=dict(SOURCE),
                                    edits=()), tmp_path, {})
    configure(monkeypatch, (("core.autocrlf", "true"), *SAFECRLF))
    found = findings(plan)
    assert [code for code, _ in found] == [REENCODED_FILES], found
    assert found[0][1].startswith(
        f"{REFUSED_GROUP}to store again what the plan keeps in the assembly "
        "root, as the split's `git add -A` does (git said `fatal: CRLF would "
        "be replaced by LF in .gitignore`)"), found
