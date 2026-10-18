# SPDX-License-Identifier: Apache-2.0
"""The standard a packaged command runs: a clone of openRepoShape (#563).

A WHEEL HAS NO CHECKOUT, AND THE TOOLS NEED ONE. `scaffold-project.py` pins
the commit it runs from (`git rev-parse HEAD` in its own checkout),
`update-shape.py` and the doctor's currency row read the standard's history,
and every tool finds its templates beside itself. So the package carries no
tool: every command but `--preflight` runs the tools from a FULL clone of
this repository at the commit the package was built from, the commit its
stamp (`_release`) names.

ONE CLONE PER COMMIT, IN A PER-USER CACHE, KEPT. The first run that needs the
standard clones it into `<cache>/<commit>` and every later run at that commit
uses it as it is. It is kept because the doctor's NEXT lines name files in it
(#500), and it is a full clone because the doctor's currency row compares
commits (`--depth 1` holds one).

CHECKED BEFORE EVERY RUN, WHEN NOTHING OVERRIDES THE STAMP. The clone must be
at the stamped commit, carry no change, and digest to the stamped value. The
digest is computed by the clone's OWN `scripts/repo_shape.py`
(`tree_digest`, `sorted-ls-tree-r-v1`), never by a copy in this package, so
it is the digest the scaffold then pins.

THE REF IS THE STAMPED 40-HEX COMMIT, NEVER THE TAG, because a tag can be
moved. `$OPENREPOSHAPE_REF`, set for one run, names another branch, tag or
commit, as it does for the bash launcher, and then no digest is checked:
the stamp's digest is the stamped commit's. `$OPENREPOSHAPE_REPO` names a
fork or a mirror to clone from. A build with no stamp follows main.

BESIDE A CHECKOUT, THAT CHECKOUT ANSWERS. Run from the `src/` of a checkout
of this standard (an editable install, or the test suite), the package uses
the checkout it sits in, as it stands, and clones nothing: the launcher's
`--doctor` rule for a copy of itself that sits in a checkout.

STANDARD LIBRARY ONLY, like every tool here: `tests/test_repo_hygiene.py`
holds this file to it.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
from pathlib import Path

from . import _release

#: Where the standard comes from when `$OPENREPOSHAPE_REPO` is unset or empty.
DEFAULT_REPO = "opensoft/openRepoShape"

#: What the stamped digest means: `scripts/repo_shape.py`'s
#: `TREE_DIGEST_DEFINITION`, the definition every pin this standard writes
#: records. A clone whose own module says otherwise is not compared.
DIGEST_DEFINITION = "sorted-ls-tree-r-v1"

#: The one dependency, and the only program whose presence moves PATH.
FILTER_REPO = "git-filter-repo"

#: A stamped commit and digest are lowercase hex of exactly these lengths.
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
ANY_CASE_COMMIT_RE = re.compile(r"[0-9a-fA-F]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")

#: A REF IS ASKED FIVE THINGS, IN THE LAUNCHER'S ORDER (its `ref_fault` and
#: `ref_character_fault`): whether it is empty, its length, a character a
#: terminal draws as another (`MISDRAWN_CHARACTERS`), a control character
#: (`CONTROL_RE`), and only then its shape (`REF_RE`, then git's rule part
#: by part). A repository is asked the middle two, in the same order
#: (`clone_url`, the launcher's `checked_repo`). See `ref_fault`.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")

#: THE CHARACTERS A TERMINAL DRAWS AS SOMETHING OTHER THAN THEMSELVES (#837,
#: #939), by code point, a range as its first and last: the launcher's
#: `MISDRAWN_CHARACTERS`, entry for entry, where the reason for each entry
#: and for each character left out is written down. A COPY, because the
#: package ships alone and reads no file of the launcher's at run time:
#: `tests/test_openreposhape_package.py` holds it equal to the launcher's
#: list. `clone_url` refuses a repository holding one, and `ref_fault` a
#: ref, naming each by its code point and nothing else of the value.
MISDRAWN_CHARACTERS = ("00AD", "061C", "200B", "200E-200F", "2028-202E",
                       "2060-206F", "FEFF", "FFF9-FFFB", "1D173-1D17A",
                       "E0001")

#: A Windows path with a drive letter, which is a path to clone and never an
#: owner/name on github.com.
DRIVE_RE = re.compile(r"[A-Za-z]:[\\/]")

#: The entry point the preflight and a scaffold run, and the two names a
#: ref can come by besides the stamp.
SETUP_ENTRY = "setup-project.py"
REF_VARIABLE = "$OPENREPOSHAPE_REF"
REF_FLAG = "--shape-ref"

#: What makes a directory a checkout of this standard for the BESIDE rule:
#: the three tools a run reaches for and the naming policy `setup-project.py`
#: itself asks for (`is_shape_checkout`).
CHECKOUT_MARKERS = (SETUP_ENTRY, "scaffold-project.py",
                    "shape-doctor.py", "contracts/repository-naming.yaml")

#: The way out of every refusal about a cached clone. The cache is this
#: command's, and a clone it made again is the same clone.
CLONE_AFRESH = "Delete it and run this again: the next run clones it afresh."

#: Run by the CLONE'S OWN interpreter path with `-I`: its `scripts/` first on
#: `sys.path`, and its `repo_shape` answers, never a copy carried here.
DIGEST_PROGRAM = """\
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import repo_shape
print(repo_shape.TREE_DIGEST_DEFINITION)
print(repo_shape.tree_digest(Path(sys.argv[2]), sys.argv[3]))
"""


class Refusal(Exception):
    """A refusal and its exit code, printed as `REFUSED: <message>` by the
    command that raised it, as the launcher's `die` prints one."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def note(text: str) -> None:
    """A line about what this command is doing, on stderr, so that a
    `--json` report on stdout stays one object."""
    print(text, file=sys.stderr, flush=True)


# --- the stamp ---------------------------------------------------------------

class Stamp:
    """`_release`, read and checked: the version, the tag, the commit and the
    digest this package was built from, or a version and three empty strings
    for a build with no stamp."""

    def __init__(self, version: str, tag: str, commit: str,
                 digest: str) -> None:
        self.version = version
        self.tag = tag
        self.commit = commit
        self.digest = digest

    @property
    def stamped(self) -> bool:
        return bool(self.commit)


def read_stamp(module=_release) -> Stamp:
    """The stamp, ALL FOUR VALUES OR NONE OF THEM.

    A stamp that names part of a release is a broken build: a commit with no
    digest would run unchecked, and a digest with no commit names nothing.
    It is refused, never read as the half it holds.
    """
    values = [getattr(module, name, "") for name in
              ("VERSION", "TAG", "COMMIT", "DIGEST")]
    if not all(isinstance(value, str) for value in values):
        values = ["", "?", "?", "?"]
    version, tag, commit, digest = values
    if not (tag or commit or digest):
        return Stamp(version or "0.0.0", "", "", "")
    if not (version and version != "0.0.0" and tag
            and COMMIT_RE.fullmatch(commit) and DIGEST_RE.fullmatch(digest)):
        raise Refusal(
            "this package's stamp (openreposhape/_release.py) names part of "
            "a release and not all of it: a release carries its version, its "
            "tag, a 40-hex commit and a 64-hex digest, together. This build "
            "is broken. Install a release: pipx install --force openreposhape")
    return Stamp(version, tag, commit, digest)


# --- where the standard comes from ---------------------------------------------

def repository() -> str:
    """`$OPENREPOSHAPE_REPO`, or opensoft/openRepoShape where it is unset or
    empty: the shell's `${VAR:-default}`, as setup.sh and the launcher read
    it."""
    return os.environ.get("OPENREPOSHAPE_REPO") or DEFAULT_REPO


def misdrawn_characters(value: str) -> str:
    """Which characters of `MISDRAWN_CHARACTERS` `value` holds, each once,
    as `U+XXXX`, comma-separated, in code point order; or "" when it holds
    none. The launcher's `misdrawn_characters`, which looks for each one's
    UTF-8 bytes; this looks for the character, as `CONTROL_RE` does."""
    named = []
    for entry in MISDRAWN_CHARACTERS:
        first, _, last = entry.partition("-")
        for code in range(int(first, 16), int(last or first, 16) + 1):
            if chr(code) in value:
                named.append(f"U+{code:04X}")
    return ", ".join(named)


def clone_url(repo: str) -> str:
    """What `git clone` is handed for `repo`: an owner/name becomes its
    github.com URL, and a URL, an scp-style address or a path on disk goes
    through untouched (the launcher's `shape_clone_url`, and a Windows
    drive path besides).

    REFUSED, NOT ECHOED, in the launcher's order and words (`checked_repo`):
    first when the value as typed holds a character a terminal draws as
    another, which the refusal names by its code point (#837, #939); then
    when the URL starts with `-` or carries a control character. Both come
    before any line names the repository and before any `git` call:
    `--version` (`cli.print_version`) and `prepare` ask this as soon as
    they have read `$OPENREPOSHAPE_REPO`. The `--` before it on every git
    command line is defence in depth, not a substitute.
    """
    misdrawn = misdrawn_characters(repo)
    if misdrawn:
        raise Refusal(
            "OPENREPOSHAPE_REPO holds a character a terminal draws as "
            f"something other than itself ({misdrawn}): one that is "
            "invisible, is drawn as another character, ends a line or "
            "reorders the text around it. This tool will not put it on a "
            "`git clone` command line. Set it to a URL or a path.")
    after_at = repo.split("@", 1)[1] if "@" in repo else ""
    if ("://" in repo or ":" in after_at or repo.startswith(("/", "."))
            or os.path.isabs(repo) or DRIVE_RE.match(repo)):
        url = repo
    else:
        url = f"https://github.com/{repo}.git"
    if url.startswith("-") or CONTROL_RE.search(url):
        raise Refusal(
            "OPENREPOSHAPE_REPO is not a value this tool will put on a `git "
            "clone` command line: it starts with '-' or carries a control "
            "character. Set it to a URL or a path.")
    return url


def ref_fault(ref: str, what: str) -> str:
    """What is wrong with `ref`, or "" when nothing is: the launcher's
    `ref_fault` with its `ref_character_fault`, in their order and their
    words, for the ref `what` names (`$OPENREPOSHAPE_REF` or `--shape-ref`).

    EMPTY, then LENGTH, so an over-long value is refused without being
    echoed. Then a CHARACTER A TERMINAL DRAWS AS ANOTHER (#837, #939), named
    by its code point, and a CONTROL CHARACTER, because either would make a
    line that printed the ref show another one, or forge a line of its own;
    the first is asked first, where the launcher asks it, so a ref holding
    both gets the launcher's words. Only then the SHAPE, which is safe to
    echo back because the value has passed all four: git's rule part by
    part (#874, #941), no `..`, no empty part between slashes, no part that
    starts with `.` or ends in `.lock`, and no `.` at the end, which is what
    `git check-ref-format --branch` asks of each part and not of the whole
    name alone. So a ref git refuses is refused here, before any clone.

    `tests/test_openreposhape_package.py` holds it to the launcher: each
    name of `REF_PARTS` to git's answer and to the launcher's sentence, and
    `MISDRAWN_CHARACTERS` to the launcher's list."""
    if not ref:
        return (f"{what} is empty, which is not a branch, tag or commit this "
                "tool will pass to `git checkout`.")
    if len(ref) > 255:
        return (f"{what} is {len(ref)} characters long; a branch, tag or "
                "commit this tool will pass to `git checkout` is at most 255 "
                "characters.")
    misdrawn = misdrawn_characters(ref)
    if misdrawn:
        return (f"{what} holds a character a terminal draws as something "
                f"other than itself ({misdrawn}): one that is invisible, is "
                "drawn as another character, ends a line or reorders the "
                "text around it. No branch, tag or commit this tool will "
                "pass to `git checkout` holds one.")
    if CONTROL_RE.search(ref):
        return (f"{what} carries a control character, which is not a "
                "branch, tag or commit this tool will pass to `git "
                "checkout`.")
    parts = ref.split("/")
    if (not REF_RE.fullmatch(ref) or ".." in ref or "" in parts
            or any(part.startswith(".") or part.endswith(".lock")
                   for part in parts)
            or ref.endswith(".")):
        return (f"{what} is '{ref}', which is not a branch, tag or commit "
                "this tool will pass to `git checkout`: a ref starts with an "
                "ASCII letter or digit, uses only ASCII letters, digits, '.', "
                "'_', '/', '-', has no '..' (git reads it as a revision "
                "range), no empty part between slashes ('//', or a '/' at the "
                "end), no part that starts with '.' or ends in '.lock' (the "
                "name git gives the lock file it writes beside a ref), and "
                "does not end in '.'.")
    return ""


def checked_ref(ref: str, what: str = REF_VARIABLE) -> str:
    """`ref`, or a refusal saying what is wrong with it."""
    fault = ref_fault(ref, what)
    if fault:
        raise Refusal(fault)
    return ref


class Target:
    """The commit a run asks for: `ref` as a person would read it, the
    40-hex `commit` where that is already known, the `digest` to check the
    clone against (the stamp's, and only with no override), and `source`,
    which of the four ways it was named."""

    def __init__(self, ref: str, commit: str, digest: str,
                 source: str) -> None:
        self.ref = ref
        self.commit = commit
        self.digest = digest
        self.source = source

    @property
    def overridden(self) -> bool:
        return self.source in (REF_FLAG, REF_VARIABLE)


def target(stamp: Stamp, typed_ref: str = "") -> Target:
    """WHICH COMMIT, first match wins: a `--shape-ref` typed on a scaffold
    run (the launcher hands setup.sh its own ref FIRST, so a typed one is the
    last and wins), `$OPENREPOSHAPE_REF` set for this run, the stamped
    commit, and with none of those main. Each named ref is checked here,
    before anything reaches git."""
    for ref, source in ((typed_ref, REF_FLAG),
                        (os.environ.get("OPENREPOSHAPE_REF", ""),
                         REF_VARIABLE)):
        if ref:
            checked_ref(ref, source)
            commit = ref.lower() if ANY_CASE_COMMIT_RE.fullmatch(ref) else ""
            return Target(ref, commit, "", source)
    if stamp.stamped:
        return Target(stamp.commit, stamp.commit, stamp.digest, "stamp")
    return Target("main", "", "", "main")


# --- the cache -----------------------------------------------------------------

def cache_root() -> Path:
    """Where the clones live, one directory per commit: the platform's own
    per-user cache. `%LOCALAPPDATA%` on Windows, `~/Library/Caches` on macOS,
    and `$XDG_CACHE_HOME` (else `~/.cache`) everywhere else; a relative
    `$XDG_CACHE_HOME` is ignored, as the XDG specification says."""
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(
                Path.home() / "AppData" / "Local")
            return Path(base) / "openreposhape" / "checkouts"
        if sys.platform == "darwin":
            return (Path.home() / "Library" / "Caches" / "openreposhape"
                    / "checkouts")
        base = os.environ.get("XDG_CACHE_HOME", "")
        if not os.path.isabs(base):
            base = str(Path.home() / ".cache")
        return Path(base) / "openreposhape" / "checkouts"
    except RuntimeError as exc:
        raise Refusal(f"could not find your home directory, where this "
                      f"command keeps its clone of the standard: {exc}. Set "
                      f"HOME.") from exc


def remove_tree(path: Path) -> None:
    """`shutil.rmtree` that also removes a clone on Windows, where git's
    object files are read-only and an unlink of one is refused until the bit
    is cleared. `onerror`, not `onexc`, which is 3.12 and newer."""
    def clear_readonly(func, target_path, _exc):
        os.chmod(target_path, stat.S_IWRITE)
        func(target_path)

    shutil.rmtree(str(path), onerror=clear_readonly)


# --- the environment every child gets ------------------------------------------

def filter_repo_in(directory: str) -> bool:
    """Whether `directory` holds a `git-filter-repo` a command line would
    start: the bare name, or on Windows any name `PATHEXT` adds an extension
    to, which is how pip writes it (`git-filter-repo.exe`)."""
    names = [FILTER_REPO]
    if os.name == "nt":
        extensions = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        names += [FILTER_REPO + ext for ext in extensions.split(os.pathsep)
                  if ext]
    for name in names:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return True
    return False


def child_environment(environ=None) -> dict:
    """This process's environment for a child, with the package's own
    scripts directory FIRST ON PATH WHENEVER A `git-filter-repo` IS THERE.

    pipx exposes the package's own commands and not its dependencies', so the
    `git-filter-repo` the package depends on sits in the package
    environment's scripts directory, which is on nobody's PATH. adopt finds
    it with `shutil.which` and runs `git filter-repo`, which git finds on
    PATH; the doctor's machine row looks for it the same way. Putting that
    directory first for the children this command starts is the whole of the
    fix, and no tool changes for it: where the directory holds none, PATH is
    left exactly as it was, and adopt still refuses with
    `filter-repo-missing` where the tool is absent.
    """
    env = dict(os.environ if environ is None else environ)
    scripts = sysconfig.get_path("scripts")
    if scripts and filter_repo_in(scripts):
        current = env.get("PATH", "")
        env["PATH"] = scripts + (os.pathsep + current if current else "")
    return env


def git(args: list, env: dict) -> subprocess.CompletedProcess:
    """`git <args>`, its output captured and decoded as UTF-8."""
    return subprocess.run(["git", *args], env=env, capture_output=True,
                          encoding="utf-8", errors="replace", check=False)


def last_line(text: str) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return lines[-1].strip() if lines else "(nothing on stderr)"


# --- the checkout a run uses ---------------------------------------------------

class Standard:
    """The standard a run uses: its `root`, the `commit` it is at, which
    `repo` it came from and which `target` named it; or, `beside`, the
    checkout this package sits in, used as it stands."""

    def __init__(self, root: Path, commit: str = "", repo: str = "",
                 wanted: Target | None = None, beside: bool = False) -> None:
        self.root = root
        self.commit = commit
        self.repo = repo
        self.target = wanted
        self.beside = beside

    def describe(self) -> str:
        """Which standard this is, in a refusal or a progress line."""
        if self.beside:
            return f"the checkout this package sits in, {self.root}"
        named = self.target.ref if self.target else self.commit
        if named == self.commit:
            return f"{self.repo} at {self.commit}"
        return f"{self.repo} at {named} ({self.commit})"


def beside_checkout() -> Path | None:
    """The checkout of the standard this package sits in, or None.

    `src/openreposhape/` in a checkout: the package's parent is `src`, and
    the directory above that holds the files a run needs. An installed
    package sits in a `site-packages`, which holds none of them.
    """
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    if here.parent.name == "src" and all(
            (root / marker).is_file() for marker in CHECKOUT_MARKERS):
        return root
    return None


def preflight_entry() -> Path:
    """The `setup-project.py` `--preflight` runs: the copy the wheel carries
    beside this file, byte for byte the release's own, or in a checkout the
    one at its root. Either way no git is needed to reach it."""
    packaged = Path(__file__).resolve().parent / SETUP_ENTRY
    if packaged.is_file():
        return packaged
    beside = beside_checkout()
    if beside is not None:
        return beside / SETUP_ENTRY
    raise Refusal("this package carries no setup-project.py, so there is no "
                  "preflight to run. The install is incomplete: pipx install "
                  "--force openreposhape")


def remote_commit(url: str, repo: str, ref: str, env: dict) -> str:
    """The commit `ref` names on the remote, read with `git ls-remote`, or
    "" when no ref has exactly that name (an abbreviated commit, say, which
    only a clone can resolve).

    A TAG FIRST, then a branch, then the name as given (`HEAD`, or a full
    `refs/...`): `git checkout <name>` in a fresh clone resolves it in that
    order, and the two must not disagree. An annotated tag is read through
    to its commit (`^{}`), named short or in full (`refs/tags/<tag>`), and
    that line is asked for BY NAME: `git ls-remote` given a name prints a
    tag's peeled line only when a pattern names it too, and the tag's own
    line names a tag object, not a commit. (A ref here is letters, digits,
    `.`, `_`, `/` and `-`, so neither pattern holds a wildcard.)
    """
    proc = git(["ls-remote", "--", url, ref, f"{ref}^{{}}"], env)
    if proc.returncode != 0:
        raise Refusal(
            f"could not ask {repo} which commit {ref} is (`git ls-remote` "
            f"exited {proc.returncode}: {last_line(proc.stderr)}). This "
            "command runs the standard from a clone of it: make the network "
            "work, or set $OPENREPOSHAPE_REPO to a mirror you can reach.")
    found = {}
    for line in proc.stdout.splitlines():
        sha, _, name = line.partition("\t")
        found[name.strip()] = sha.strip().lower()
    for name in (f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}",
                 f"refs/heads/{ref}", f"{ref}^{{}}", ref):
        if COMMIT_RE.fullmatch(found.get(name, "")):
            return found[name]
    return ""


def move_into_place(incoming: Path, final: Path) -> None:
    """`os.rename`, and on Windows a few more tries a moment apart. A
    scanner that opens a file git has just written holds it for a moment,
    and Windows refuses to rename a directory while it does; an existing
    `final` is never retried, because another run placed it first."""
    tries = 10 if os.name == "nt" else 1
    for attempt in range(tries):
        try:
            os.rename(str(incoming), str(final))
            return
        except PermissionError:
            if attempt == tries - 1 or final.exists():
                raise
            time.sleep(0.2)


#: Where a clone is made before it is moved into place, and how long one
#: may sit untouched before a later run takes it for the leftover of a run
#: that was killed mid-clone.
INCOMING_PREFIX = ".incoming-"
INCOMING_STALE_SECONDS = 3600


def sweep_incoming(cache: Path) -> None:
    """Remove what a KILLED run left: an `.incoming-*` directory nothing has
    touched for an hour. A run that fails, or is interrupted with Ctrl-C,
    removes its own (`clone_into`'s `finally`); one ended by SIGTERM,
    SIGHUP or SIGKILL cannot, and its half-made clone would otherwise sit in
    the cache for good. An hour, so a clone another run is making right now
    is left alone. A link is never followed, and a directory that cannot be
    removed is left for the next run: this is tidying, never a refusal."""
    cutoff = time.time() - INCOMING_STALE_SECONDS
    for leftover in cache.glob(INCOMING_PREFIX + "*"):
        try:
            if (not leftover.is_symlink() and leftover.is_dir()
                    and leftover.stat().st_mtime < cutoff):
                remove_tree(leftover)
        except OSError:
            continue


def clone_into(cache: Path, url: str, repo: str, wanted: Target,
               commit: str, env: dict) -> Path:
    """A full clone of `url` at `commit` (or at `wanted.ref`, resolved by the
    clone where `commit` is not known), placed at `<cache>/<commit>`.

    CLONED BESIDE ITS PLACE AND MOVED IN WHOLE. A clone that failed half way,
    or a run interrupted, leaves nothing at `<cache>/<commit>` for the next
    run to mistake for a clone; and of two runs cloning at once, the one that
    moves second uses the first one's and discards its own. What a killed
    run left beside it is swept first (`sweep_incoming`).
    """
    try:
        cache.mkdir(parents=True, exist_ok=True)
        sweep_incoming(cache)
        incoming = Path(tempfile.mkdtemp(prefix=INCOMING_PREFIX,
                                         dir=str(cache)))
    except OSError as exc:
        raise Refusal(f"could not make a directory under {cache}, where "
                      f"this command keeps its clones of the standard: "
                      f"{exc}") from exc
    placed = False
    try:
        named = f"commit {commit}" if commit else wanted.ref
        note(f"openRepoShape: cloning {repo} into {cache}, once for {named}; "
             "every later run at that commit uses this clone.")
        cloned = git(["clone", "--quiet", "--no-checkout", "--", url,
                      str(incoming)], env)
        if cloned.returncode != 0:
            raise Refusal(
                f"could not clone {repo} ({url}): `git clone` exited "
                f"{cloned.returncode}: {last_line(cloned.stderr)}. This "
                "command runs the standard from a clone of it: make the "
                "clone work, or set $OPENREPOSHAPE_REPO to a mirror.")
        # `<ref> --`, never `-- <ref>`: before the `--` git reads it as a
        # commit, after it as a pathspec. A commit already known is checked
        # out detached; a name only the clone can resolve is checked out as
        # git resolves it.
        checkout = (["checkout", "--quiet", "--detach", commit] if commit
                    else ["checkout", "--quiet", wanted.ref, "--"])
        checked_out = git(["-C", str(incoming), *checkout], env)
        if checked_out.returncode != 0:
            raise Refusal(
                f"cloned {repo} but could not check out "
                f"'{commit or wanted.ref}': {last_line(checked_out.stderr)}. "
                "Set $OPENREPOSHAPE_REF to a ref that repository carries, or "
                "$OPENREPOSHAPE_REPO to one that carries this one.")
        if not commit:
            head = git(["-C", str(incoming), "rev-parse", "HEAD"], env)
            commit = head.stdout.strip().lower()
            if head.returncode != 0 or not COMMIT_RE.fullmatch(commit):
                raise Refusal(f"cloned {repo} at '{wanted.ref}', but git "
                              f"could not say which commit that is: "
                              f"{last_line(head.stderr)}")
        final = cache / commit
        try:
            move_into_place(incoming, final)
            placed = True
        except OSError as exc:
            if not final.is_dir():
                raise Refusal(f"could not move the new clone to {final}: "
                              f"{exc}") from exc
        return final
    finally:
        if not placed and incoming.exists():
            remove_tree(incoming)


def tree_digest(root: Path, commit: str, env: dict) -> tuple:
    """`(definition, digest)` of `commit`'s tree, as the clone's own
    `scripts/repo_shape.py` computes them. `-I`, so nothing in this process's
    environment or user site can stand in for that module, and `-B`, so the
    clone gains no bytecode."""
    module = root / "scripts" / "repo_shape.py"
    if not module.is_file():
        raise Refusal(
            f"{root} has no scripts/repo_shape.py, so its tree digest cannot "
            "be computed the way every pin this standard writes computes "
            f"it, and nothing was run from it. {CLONE_AFRESH}")
    proc = subprocess.run(
        [sys.executable, "-I", "-B", "-c", DIGEST_PROGRAM,
         str(root / "scripts"), str(root), commit],
        env=env, capture_output=True, encoding="utf-8", errors="replace",
        check=False)
    said = proc.stdout.split()
    if proc.returncode != 0 or len(said) != 2:
        raise Refusal(
            f"could not compute the tree digest of {root} with its own "
            f"scripts/repo_shape.py (exit {proc.returncode}): "
            f"{last_line(proc.stderr)}")
    return said[0], said[1]


def verify(standard: Standard, digest: str, env: dict) -> None:
    """REFUSE TO RUN FROM A CLONE THAT IS NOT THE COMMIT AS IT WAS MADE: at
    another commit, carrying a change (an untracked file included), or, where
    a digest is given, digesting to anything else. Nothing is repaired or
    removed here, because the doctor's NEXT lines may have sent somebody into
    this directory, and what they changed is theirs to look at first."""
    root, commit = standard.root, standard.commit
    head = git(["-C", str(root), "rev-parse", "--verify", "HEAD"], env)
    at = head.stdout.strip().lower()
    if head.returncode != 0 or at != commit:
        raise Refusal(
            f"{root} should be this command's clone of the standard at "
            f"{commit}, and it is at {at or 'no commit git can read'}, so "
            f"nothing was run from it. {CLONE_AFRESH}")
    status = git(["-C", str(root), "status", "--porcelain",
                  "--untracked-files=normal"], env)
    if status.returncode != 0:
        raise Refusal(f"could not ask git whether {root} has changes: "
                      f"{last_line(status.stderr)}. {CLONE_AFRESH}")
    changed = [line[3:] for line in status.stdout.splitlines() if line.strip()]
    if changed:
        shown = ", ".join(changed[:3])
        if len(changed) > 3:
            shown += f", and {len(changed) - 3} more"
        raise Refusal(
            f"{root}, this command's clone of the standard at {commit}, has "
            f"changes ({shown}), so nothing was run from it: a run uses the "
            f"commit exactly as it was made. {CLONE_AFRESH}")
    if not digest:
        return
    definition, computed = tree_digest(root, commit, env)
    if definition != DIGEST_DEFINITION:
        raise Refusal(
            f"{root}'s own scripts/repo_shape.py computes the "
            f"{definition} digest, and this package was stamped with a "
            f"{DIGEST_DEFINITION} one, so the two cannot be compared and "
            f"nothing was run from it. {CLONE_AFRESH}")
    if computed != digest:
        raise Refusal(
            f"{root} is at {commit}, and its tree digests to {computed} "
            f"({DIGEST_DEFINITION}), not to {digest}, the digest this "
            "package was stamped with, so nothing was run from it: that "
            f"clone is not the release this package names. {CLONE_AFRESH} "
            f"If the new clone says the same, {standard.repo} does not hold "
            "that release.")


def prepare(typed_ref: str = "") -> Standard:
    """The standard this run uses, cloned if it has to be and checked.

    In order: BESIDE a checkout, that checkout, untouched. Otherwise the ref
    is checked before anything reaches git; git must be there, because the
    standard is a clone; the commit is the stamp's, the 40-hex ref's, or what
    the remote says the ref is; a clone of it already in the cache is used,
    and one that is not is made; and the clone is verified, against the
    stamped digest where nothing overrode the stamp.
    """
    beside = beside_checkout()
    if beside is not None:
        return Standard(beside, beside=True)
    stamp = read_stamp()
    wanted = target(stamp, typed_ref)
    repo = repository()
    url = clone_url(repo)
    env = child_environment()
    if shutil.which("git", path=env.get("PATH")) is None:
        raise Refusal(
            "git is not installed, and this command runs the standard from "
            "a clone of it, so there is nothing to clone one with. Install "
            "it: https://git-scm.com/downloads")
    commit = wanted.commit or remote_commit(
        url, repo, "HEAD" if wanted.source == "main" else wanted.ref, env)
    cache = cache_root()
    if commit and (cache / commit).is_dir():
        root = cache / commit
    else:
        root = clone_into(cache, url, repo, wanted, commit, env)
        commit = root.name
    standard = Standard(root, commit, repo, wanted)
    verify(standard, wanted.digest, env)
    return standard
