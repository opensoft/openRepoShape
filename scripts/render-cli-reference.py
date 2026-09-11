#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render `docs/cli.md`: every shipped tool's own `--help`, for an agent.

Brett Heap, 2026-09-10, in session: *"do we have documentation designed for an
AI to understand what our CLI can do and how to use it?"* — no. `AGENTS.md` is
PROCEDURE-first (which act, in what order, and what must never be done on the
assistant's own initiative) and `README.md` is the standard itself. Neither is
a flag-by-flag reference, and the flags only existed inside seventeen separate
`--help` texts. His ruling was *"add the docs/cli.md"* (#97).

GENERATED, never hand-written, for the reason this repository refuses a
hand-edited pin: a second copy of the flags starts drifting the day after it is
written, and the drift lands in front of whoever was not looking. The only
prose in the output that a person wrote is in THIS FILE — the orientation
paragraph and the one-line purpose beside each tool in `TOOLS` — so an edit to
the document itself is either reverted by the next run or caught by
`tests/test_cli_reference.py`.

DETERMINISM IS THE WHOLE DESIGN CONSTRAINT, because the guard compares bytes:

*   The child environment pins `COLUMNS` (argparse wraps to the terminal
    width), forces UTF-8 in and out, and turns off colour. No `LC_*` variable
    is set: a locale a runner does not have makes bash write a `setlocale`
    warning to the stderr this script captures, which would be noise in the
    document on one platform only.
*   Every line is stripped of trailing whitespace, CRLF is folded to LF, and
    trailing blank lines are dropped, so the file is the same on the windows
    runner as on the other two.
*   The `usage:` block is RE-WRAPPED here from its own collapsed tokens rather
    than left as argparse wrapped it. Python 3.14's argparse keeps `--to
    COMMIT` together where 3.12's breaks between them — the only difference
    between the two across all twenty-two help texts, and `.github/workflows/
    tests.yml` pins `python-version: '3.x'`, so a naive byte comparison would
    go red the day a runner image moves. Only the line BREAKS differ, never
    the tokens, so collapsing and re-wrapping is lossless. The continuation
    indent is read from argparse's own second line rather than recomputed from
    the program name, which is what keeps a subcommand's two-word `prog`
    (`family.py bump`) aligned the way argparse aligns it.
*   A path under the generating machine's home directory is replaced with a
    placeholder, and the run REFUSES rather than writing a file that still
    carries a host-absolute path — the estate's Rule 1, asserted here as well
    as in `tests/test_repo_hygiene.py`, because this is the one file in the
    repository whose bytes come from running programs on somebody's machine.

THE PROJECT-SIDE COPIES CANNOT PRINT THEIR HELP AS THEY STAND from a checkout
of this standard. Each of the six does `sys.path.insert(0, <its own
directory>)` and then `from repo_shape import …`, and `repo_shape.py` is beside
them only in a materialized project. This script puts `scripts/` on
`PYTHONPATH`, which that inserted directory still shadows, so the files
themselves need no change and nothing under `templates/` moves.

    python3 scripts/render-cli-reference.py            # rewrite docs/cli.md
    python3 scripts/render-cli-reference.py --check    # diff, write nothing
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
GENERATOR = "scripts/render-cli-reference.py"
GUARD = "tests/test_cli_reference.py"
OUTPUT = "docs/cli.md"

#: What argparse wraps to, and what this script re-wraps the usage block to:
#: `shutil.get_terminal_size().columns - 2`, with the columns pinned below.
#: Matching argparse's own budget keeps the re-wrap a no-op wherever the two
#: agree, so the only lines this script moves are the ones it has to.
COLUMNS = 80
WIDTH = COLUMNS - 2


class Tool(NamedTuple):
    """One entry point, and the one line saying what it is FOR.

    `purpose` is the only prose a person writes about a tool here. It answers
    "which of these do I want", which no `--help` text answers, because each
    one is written as though the reader already chose it.
    """

    path: str                    #: repository-relative, POSIX. THE HEADING,
                                 #: because it is unique and it is what a
                                 #: reader greps for; two of the six copies
                                 #: are both called `bootstrap.py`.
    runner: str                  #: "python" or "bash"
    command: str                 #: what a person types, as the reference shows it
    purpose: str
    installed_as: str = ""       #: where the copy lands in a project, if it is one
    installed_in: str = ""       #: what kind of root that is
    note: str = ""               #: one more sentence, where the help alone misleads


#: RUN FROM A CHECKOUT OF THE STANDARD. Order is the order somebody meets
#: them: the two front doors, the flow behind them, then the acts on a
#: repository that already exists, then the two under `scripts/`.
CHECKOUT_TOOLS = [
    Tool("setup.sh", "bash", "./setup.sh",
         "The front door for a NEW project: preflight, the naming check, the "
         "plan, one typed `yes`, then three repositories. A SHIM over "
         "`setup-project.py`, so the help below is that tool's own."),
    Tool("openRepoShape", "bash", "openRepoShape",
         "The same front door as an installed command, plus `--install` "
         "(itself, into `~/.local/bin`), `--preflight` (this MACHINE) and "
         "`--doctor` (one REPOSITORY)."),
    Tool("setup-project.py", "python", "python3 setup-project.py",
         "THE FLOW itself, and the only way in on a machine with no bash."),
    Tool("scaffold-project.py", "python", "python3 scaffold-project.py",
         "Creates the three repositories and writes the pins. What the front "
         "door calls once the human has said yes."),
    Tool("adopt-project.py", "python", "python3 adopt-project.py",
         "Converts an EXISTING repository into the shape, in place, keeping "
         "its name and its history."),
    Tool("update-shape.py", "python", "python3 update-shape.py",
         "Re-copies a project's shape files from this standard and re-pins "
         "them. It never merges."),
    Tool("shape-doctor.py", "python", "python3 shape-doctor.py",
         "Answers ONE question about ONE repository: is it compliant with "
         "this shape, and what is missing. Writes nothing."),
    Tool("bootstrap", "python", "python3 bootstrap",
         "Runs this standard's canonical bootstrap against a project that was "
         "never scaffolded, so a repository that elected nothing still has "
         "the command.",
         note="A shim: it runs `templates/assembly-root/scripts/bootstrap.py` "
              "with `--root` set to the directory you are standing in, which "
              "is why the help below prints under THAT file's name and "
              "carries its flags."),
    Tool("scripts/bump-leg.py", "python", "python3 scripts/bump-leg.py",
         "Advances ONE leg's pin — the gitlink, `contracts/<role>-pin.yaml` "
         "and every workflow `@<sha>` — in one lockstep commit."),
    Tool("scripts/family.py", "python", "python3 scripts/family.py",
         "Creates a FAMILY holder and maintains its member pins."),
    Tool("scripts/validate-repository-naming.py", "python",
         "python3 scripts/validate-repository-naming.py",
         "Classifies repository names against "
         "`contracts/repository-naming.yaml`, and explains which form won."),
]

#: SHIPPED INTO EVERY PROJECT. These are the master copies of files
#: `scaffold-project.py` writes into a scaffolded project or a family holder
#: and records by sha256 in that root's own `contracts/shape-pin.yaml`. They
#: are run FROM THERE, as `scripts/<name>.py`, never from this checkout — the
#: help is rendered from the master copy because that is where a change to
#: them is made.
PROJECT_TOOLS = [
    Tool("templates/assembly-root/scripts/bootstrap.py", "python",
         "python3 scripts/bootstrap.py",
         "The one command after `git clone --recurse-submodules`: places each "
         "leg on its tracking branch AT the pinned commit. What `make "
         "bootstrap` runs.",
         "scripts/bootstrap.py", "an assembly root"),
    Tool("templates/assembly-root/scripts/validate-manifest.py", "python",
         "python3 scripts/validate-manifest.py",
         "The project's own `project.yaml` validator: the manifest against "
         "the naming and path policies it was cut from.",
         "scripts/validate-manifest.py", "an assembly root"),
    Tool("templates/assembly-root/scripts/validate-pins.py", "python",
         "python3 scripts/validate-pins.py",
         "The project's own LOCKSTEP validator: the gitlink, the pin and the "
         "workflow references must agree, and every digest must recompute.",
         "scripts/validate-pins.py", "an assembly root"),
    Tool("templates/family-root/scripts/bootstrap.py", "python",
         "python3 scripts/bootstrap.py",
         "The holder's own bootstrap: mounts every member at its pin and runs "
         "each member's.",
         "scripts/bootstrap.py", "a family holder"),
    Tool("templates/family-root/scripts/siblings.py", "python",
         "python3 scripts/siblings.py",
         "Places the WORKSTATION layout: every member cloned BESIDE the "
         "holder, on its tracking branch. It moves nothing and overwrites "
         "nothing.",
         "scripts/siblings.py", "a family holder"),
    Tool("templates/family-root/scripts/validate-family.py", "python",
         "python3 scripts/validate-family.py",
         "The holder's own `family.yaml` validator: the members, their pins "
         "and its shape copies.",
         "scripts/validate-family.py", "a family holder"),
]

GROUPS = [
    ("Run from a checkout of the standard", CHECKOUT_TOOLS,
     "Every command below is typed at the root of a clone of this "
     "repository. `openRepoShape` is also the one file `--install` places on "
     "`PATH`, and is the only entry point that needs no checkout at all."),
    ("Shipped into every project (copied, digest-pinned)", PROJECT_TOOLS,
     "These six are COPIES. `scaffold-project.py` writes them into a "
     "scaffolded project or a family holder and records each one by sha256 "
     "in that root's own `contracts/shape-pin.yaml`, which is what lets a "
     "project run its gate with no network and no mount. They are run from "
     "INSIDE such a root, under its own `scripts/`, never from a checkout of "
     "this standard — the help below is rendered from the master copy here, "
     "because a change to one of them is made here and reaches a project "
     "through `update-shape.py`."),
]

#: The line the guard asserts, and the reason it is one line: a sentence
#: broken across two is a sentence a reader can lose half of.
HEADER = (
    "**GENERATED** by `{generator}`; do not edit. The test that keeps it "
    "honest is `{guard}`.".format(generator=GENERATOR, guard=GUARD))

ORIENTATION = """\
This is the flag-level reference. `AGENTS.md` is the procedure — which act to
perform, in what order, and what must never be done on your own initiative —
and it outranks this file wherever the two meet: a flag documented here is not
permission to pass it. `README.md` is the standard itself. Read this one when
you know which act you are performing and need the exact spelling.

Two rules the help texts below do not repeat, because they are about all of
them at once. Nothing here is run with `--yes` on an assistant's own
initiative, and a refusal is never worked around: each one names the command
to run instead, and running THAT is the whole of the fix.
"""

#: Said in the document rather than only in this file's docstring, because a
#: reader comparing a tool's real output against a fenced block here needs to
#: know which differences are this script's and which are a drift.
NORMALISATION = """\
Each block is the tool's own `--help`, captured verbatim from stdout and
stderr with four normalisations, so that regenerating on another machine
produces the same bytes: the terminal width is pinned at {columns} columns;
trailing whitespace and CRLF line endings are removed; the `usage:` block is
re-wrapped from its own tokens, because argparse breaks that one line in
different places on different Python versions; and a path under the generating
machine's home directory would be replaced with a placeholder — no tool prints
one today, and the generator refuses to write this file if one ever appears.
""".format(columns=COLUMNS)


class Refusal(Exception):
    """Something this script will not paper over."""


def child_env() -> dict:
    """The environment every `--help` is captured under.

    `PYTHONPATH` is what lets the six project-side copies import the
    `repo_shape` that is beside them only in a materialized project. The
    UTF-8 pair is for the windows runner, whose locale encoding is cp1252 and
    whose console would otherwise mangle the em dashes this repository is
    written in. Nothing sets `LC_ALL`: a locale a runner does not have makes
    bash warn on stderr, and stderr is captured.
    """
    env = dict(os.environ)
    env.pop("LINES", None)
    env.update({
        "COLUMNS": str(COLUMNS),
        "PYTHONPATH": str(REPO / "scripts"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "1",
        "TERM": "dumb",
    })
    return env


def capture_help(tool: Tool, *subcommand: str) -> str:
    """One tool's `--help`, normalised.

    `sys.executable` rather than `python3`, because there is no `python3` on
    a Windows install — the fact `setup-project.py` exists for. The reference
    still SHOWS `python3 …`, which is what a reader types on the platforms
    that have one.
    """
    target = REPO / tool.path
    if tool.runner == "bash":
        argv = ["bash", str(target), *subcommand, "--help"]
    else:
        argv = [sys.executable, str(target), *subcommand, "--help"]
    proc = subprocess.run(argv, cwd=str(REPO), env=child_env(),
                          stdin=subprocess.DEVNULL, capture_output=True,
                          check=False)
    name = " ".join([tool.path, *subcommand])
    if proc.returncode != 0:
        raise Refusal(
            f"`{name} --help` exited {proc.returncode}; a tool whose help "
            f"does not print is a defect in the tool, not in this "
            f"script:\n{proc.stderr.decode('utf-8', 'replace')}")
    text = proc.stdout.decode("utf-8") + proc.stderr.decode("utf-8")
    if not text.strip():
        raise Refusal(f"`{name} --help` printed nothing")
    return normalise(text)


def normalise(text: str) -> str:
    """Trailing whitespace, line endings, the usage block, and Rule 1."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")
    text = rewrap_usage(text)
    return placehold_host_paths(text)


def _atoms(tokens: list) -> list:
    """Usage tokens grouped the way argparse groups them.

    A bracketed group is one atom however many spaces are inside it
    (`[--pin openProduct@COMMIT]`), and an option keeps its metavar
    (`--to COMMIT`) — the second rule is what Python 3.14's argparse added and
    3.12's lacks, and applying it here means the answer no longer depends on
    which interpreter ran the tool.
    """
    atoms, depth, current = [], 0, []
    for token in tokens:
        current.append(token)
        depth += token.count("[") - token.count("]")
        depth += token.count("(") - token.count(")")
        if depth <= 0:
            atoms.append(" ".join(current))
            current, depth = [], 0
    if current:
        atoms.append(" ".join(current))

    merged: list = []
    for atom in atoms:
        previous = merged[-1] if merged else ""
        if (previous.startswith("-") and not previous.endswith("]")
                and not atom.startswith(("-", "[", "("))):
            merged[-1] = f"{previous} {atom}"
        else:
            merged.append(atom)
    return merged


def rewrap_usage(text: str) -> str:
    """Re-break the `usage:` block, leaving everything under it alone.

    A one-line usage block is returned untouched: argparse did not wrap it, so
    there is nothing a version could disagree about.
    """
    lines = text.split("\n")
    if not lines or not lines[0].startswith("usage: "):
        return text
    end = 1
    while end < len(lines) and lines[end].startswith(" ") and lines[end].strip():
        end += 1
    if end == 1:
        return text

    indent = len(lines[1]) - len(lines[1].lstrip(" "))
    if indent >= len(lines[0]):
        return text
    head = lines[0][:indent]
    tokens = " ".join([lines[0][indent:], *(l.strip() for l in lines[1:end])])
    wrapped, line = [], head
    for atom in _atoms(tokens.split()):
        candidate = f"{line}{atom}" if line.endswith(" ") else f"{line} {atom}"
        if len(candidate) > WIDTH and line.strip() and line != head:
            wrapped.append(line.rstrip())
            line = " " * indent + atom
        else:
            line = candidate
    wrapped.append(line.rstrip())
    return "\n".join(wrapped + lines[end:])


def _host_prefixes() -> list:
    """This machine's home directory and temporary root, longest first.

    Computed rather than written down: a literal one would itself be the
    host-absolute path `tests/test_repo_hygiene.py::test_no_committed_file_
    names_a_host_absolute_path` refuses, in the file whose job is to keep one
    out of the reference.
    """
    home = str(Path.home())
    prefixes = [(home, "<home>")]
    tmp = os.environ.get("TMPDIR") or "/tmp"
    if tmp.rstrip("/") and tmp.rstrip("/") != "/tmp":
        prefixes.append((tmp.rstrip("/"), "<tmp>"))
    return sorted(prefixes, key=lambda pair: -len(pair[0]))


#: Rule 1, as a pattern rather than as a hope. Deliberately the same shape as
#: `HOST_ABSOLUTE_PATH` in `tests/test_repo_hygiene.py`: the suite-wide guard
#: is the one that must hold, and a refusal HERE is what stops a bad run from
#: ever producing the file that would trip it.
HOST_ABSOLUTE = re.compile(
    r"/home/[a-z][a-z0-9_-]*/"
    r"|/Users/[A-Za-z][A-Za-z0-9_-]*/"
    r"|C:\\Users\\[^\s\\]+\\"
)


def placehold_host_paths(text: str) -> str:
    for prefix, placeholder in _host_prefixes():
        text = text.replace(prefix, placeholder)
    return text


def table(tools: list) -> list:
    rows = ["| tool | what it is for |", "| --- | --- |"]
    for tool in tools:
        rows.append(f"| [`{tool.path}`](#{anchor(tool)}) | {tool.purpose} |")
    return rows


def anchor(tool: Tool, *subcommand: str) -> str:
    """The GitHub anchor for a tool's heading, derived the way GitHub does.

    Lowercased, everything that is not a letter, a digit, a space, an
    underscore or a hyphen dropped, then spaces to hyphens. Keyed on the
    PATH, which is unique — `templates/assembly-root/scripts/bootstrap.py`
    and `templates/family-root/scripts/bootstrap.py` are two different files
    that a project installs under one name.
    """
    text = " ".join([tool.path, *subcommand]).lower()
    text = re.sub(r"[^a-z0-9 _-]", "", text)
    return text.strip().replace(" ", "-")


#: A SUBPARSER GROUP IN A USAGE LINE, and the `...` is load-bearing: argparse
#: prints a dispatcher's commands as `{plan,check,execute} ...` and an
#: option's choices as `--leg {spec,code}`, with no ellipsis. Matching the
#: braces alone made `bump-leg.py --leg {spec,code}` look like a tool with
#: `spec` and `code` subcommands — and it rendered, because argparse fires
#: `-h` as it consumes it and exits 0 before it ever rejects the stray
#: positional, so the two bogus sections were the parent's help twice.
SUBPARSERS_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9,_-]*)\}\s+\.\.\.")


def subcommands(help_text: str) -> list:
    """A dispatcher's subcommands, read out of its own help.

    Derived rather than listed, so a subcommand added to `family.py` tomorrow
    appears here without anybody remembering to come and write it down — and
    CROSS-CHECKED against the `positional arguments:` block underneath, so a
    usage line this pattern misreads is a refusal rather than a wrong section.
    """
    usage, _, body = help_text.partition("\n\n")
    match = SUBPARSERS_RE.search(usage)
    if not match:
        return []
    names = match.group(1).split(",")
    listed = set(re.findall(r"^ {4}([A-Za-z][A-Za-z0-9_-]*)(?:\s|$)", body,
                            re.M))
    missing = [name for name in names if name not in listed]
    if missing:
        raise Refusal(
            f"the usage line offers {names} but the help body lists no "
            f"entry for {missing}; this is not a subparser group")
    return names


def fence(body: str) -> list:
    return ["```", *body.split("\n"), "```"]


def render(skip_bash: bool = False) -> str:
    """The whole document."""
    tools = [(title, [t for t in group if not (skip_bash and t.runner == "bash")],
              blurb) for title, group, blurb in GROUPS]

    out = ["# The openRepoShape CLI, flag by flag", "", HEADER, "",
           ORIENTATION.rstrip(), "", NORMALISATION.rstrip(), ""]
    if skip_bash:
        out += [
            "> This rendering OMITS the bash entry points (`setup.sh`, "
            "`openRepoShape`), because it was generated where there is no "
            "bash to run them. The committed `" + OUTPUT + "` has them.", ""]

    out += ["## The tools, and what each one is for", ""]
    for title, group, _ in tools:
        out += [f"**{title}**", ""] + table(group) + [""]

    for title, group, blurb in tools:
        out += [f"## {title}", "", blurb, ""]
        for tool in group:
            out += [f"### `{tool.path}`", ""]
            if tool.installed_as:
                out += [f"Run as `{tool.command}` from inside "
                        f"{tool.installed_in}.", ""]
            if tool.note:
                out += [tool.note, ""]
            out += [f"`{tool.command} --help`:", ""]
            body = capture_help(tool)
            out += fence(body) + [""]
            for name in subcommands(body):
                out += [f"#### `{tool.path} {name}`", "",
                        f"`{tool.command} {name} --help`:", ""]
                out += fence(capture_help(tool, name)) + [""]

    text = "\n".join(out).rstrip("\n") + "\n"
    leaked = HOST_ABSOLUTE.findall(text)
    if leaked:
        raise Refusal(
            f"the rendered reference carries host-absolute path(s) {leaked}; "
            "writing it would break the estate's Rule 1 and "
            "tests/test_repo_hygiene.py::test_no_committed_file_names_a_host_"
            "absolute_path. Fix the tool that prints one.")
    return text


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render-cli-reference.py",
        description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPO / OUTPUT),
                        help=f"where to write it (default: {OUTPUT})")
    parser.add_argument("--skip-bash", action="store_true",
                        help="omit the bash entry points, for a machine that "
                             "has no bash to run them (the windows runner). "
                             "Detected automatically when `bash` is not on "
                             "PATH.")
    parser.add_argument("--check", action="store_true",
                        help="print a unified diff against the file that is "
                             "there and write nothing; exit 1 if they differ")
    args = parser.parse_args(argv)

    # `os.name` BEFORE `shutil.which`, and the order is the point:
    # `tests/conftest.py::WINDOWS_SKIP` says at length that the `bash` on a
    # stock Windows PATH is `C:\Windows\System32\bash.exe`, the WSL
    # launcher — `which` finds it, it exits 1 with "no installed
    # distributions", and the failure reads as a syntax error in `setup.sh`.
    # A detection that trusted `which` there would produce a rendering that
    # is short two sections and say nothing about why.
    skip_bash = args.skip_bash or os.name == "nt" or shutil.which("bash") is None
    if skip_bash and not args.skip_bash:
        print("no bash to run the bash entry points with: rendering without "
              "them", file=sys.stderr)
    if args.check and skip_bash:
        print("[!!] this machine cannot run the bash entry points, so a "
              "rendering made here is short `setup.sh` and `openRepoShape` "
              f"and cannot be compared with the committed {OUTPUT}. Run "
              "`--check` where there is a bash.", file=sys.stderr)
        return 3
    try:
        text = render(skip_bash=skip_bash)
    except Refusal as refusal:
        print(f"[!!] {refusal}", file=sys.stderr)
        return 2

    out = Path(args.out)
    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else ""
        if current == text:
            print(f"[ok] {OUTPUT} is what the generator produces")
            return 0
        sys.stdout.writelines(difflib.unified_diff(
            current.splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile=f"a/{OUTPUT}", tofile=f"b/{OUTPUT}"))
        print(f"[!!] {OUTPUT} is not what the generator produces; "
              f"regenerate it with `python3 {GENERATOR}`")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"[ok] wrote {out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
