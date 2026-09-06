#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# setup.sh — the front door, and a SHIM over `setup-project.py`.
#
#   curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup.sh \
#       | bash -s -- --org <your-org> --project Atlas
#
# THIS FILE IS NOT THE FLOW; `setup-project.py` is. The preflight, the
# organisation, the naming policy, the plan, the one yes, the scaffold, the
# clone and the bootstrap all live there — one implementation, one flag list,
# one set of refusal wordings, one `--help`. This script parses nothing, and
# owns exactly four things, each of them something Python cannot do for
# itself before it is running: an INTERPRETER (3.9 or newer, under whichever
# name this machine has one); GIT itself, because the checkout probe below
# asks git a question before Python is ever started; a CHECKOUT when the
# person has none, because `curl … | bash` leaves no file on disk at all and
# this script is then the whole of what they have; and the INVOCATION
# DIRECTORY, which that checkout would otherwise lose — handed over as
# `--into`, so the new project lands where the person was standing and not
# beside a temporary checkout in /tmp (#39).
#
# What follows is a bash transcription of `setup-project.py`'s section 0
# (`self_bootstrap`), and nothing else. Every flag named below is about the
# checkout THIS FILE makes, never about the run.

set -euo pipefail

INVOCATION_DIR="$PWD"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)"
SHAPE_REPO="${OPENREPOSHAPE_REPO:-https://github.com/opensoft/openRepoShape.git}"
ENTRY="setup-project.py"

say() { printf '%s\n' "$*"; }
die() { printf '\nREFUSED: %s\n' "$1" >&2; exit "${2:-2}"; }

# APPLE'S COMMAND LINE TOOLS, NAMED IN BOTH REFUSALS BELOW AND ONLY ON A MAC.
# Since macOS 12.3 both /usr/bin/python3 and /usr/bin/git are Command Line
# Tools STUBS: `command -v python3` succeeds and the version probe below
# fails, so a bare Mac is refused by the INTERPRETER check and never reaches
# the git one — and the single answer to both is Apple's own command, which
# supplies git, make and a python3 at once. TEXT ONLY, NEVER RUN AND NEVER
# PROMPTED FOR: it opens a dialog this script could not answer anyway, and one
# sentence buys the same outcome. The install OFFERS live in
# `setup-project.py` (#59), which is the flow; an offer table transcribed into
# bash here would be the duplication #50 removed, growing back. `2>/dev/null`
# because a machine can be missing `uname` too — the git-missing test runs
# this script with almost nothing on $PATH — and a `case` whose word came from
# a failed substitution simply matches nothing.
MAC_TOOLS=""
case "$(uname -s 2>/dev/null)" in
Darwin) MAC_TOOLS=$'\n  On a Mac, install Apple\'s Command Line Tools with `xcode-select --install` (a dialog opens; run this again when it has finished), which supplies git, make and a python3.' ;;
esac

# THE INTERPRETER FIRST, BEFORE ANY CLONE. A machine with no Python cannot run
# the flow whatever we fetch for it, and one sentence is a better answer than a
# temporary checkout made and thrown away. `python3` is the name every POSIX
# install answers to; `python` is for the machines that have only that one.
find_python() {
	for candidate in python3 python; do
		if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
			'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
			>/dev/null 2>&1; then
			printf '%s' "$candidate"
			return 0
		fi
	done
	return 1
}
PY="$(find_python)" || die "no Python 3.9 or newer on this machine (tried python3, python). Install Python 3.9 or newer and re-run: https://www.python.org/downloads/$MAC_TOOLS"

# GIT ITSELF, BEFORE THE CHECKOUT PROBE. `is_shape_checkout` below redirects
# git's own stderr to /dev/null, so a MISSING git reads identically to "not a
# checkout" — and section 0 would then die on a bare `git: command not found`,
# exit 127, where `setup-project.py` prints its own named refusal. The Python
# is not running yet, so the shim owns this fourth thing; the wording is
# `setup-project.py`'s own `GIT_MISSING`, said once here for the same reason
# it is said once there.
command -v git >/dev/null 2>&1 || die "git is not installed. Install it: https://git-scm.com/downloads$MAC_TOOLS"

# `curl | bash -s --` has no file on disk either: $SCRIPT_DIR then falls back
# to $PWD, which is an openRepoShape checkout only by coincidence. Ask git,
# rather than trust the directory a person happened to be standing in. Sets
# $SHAPE_ROOT to git's own answer when the probe passes — see the exec below.
is_shape_checkout() {
	local dir="$1" toplevel
	toplevel="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || return 1
	[ -n "$toplevel" ] && [ -f "$toplevel/scaffold-project.py" ] \
		&& [ -f "$toplevel/contracts/repository-naming.yaml" ] || return 1
	SHAPE_ROOT="$toplevel"
}

# THE DEVELOPER PATH, AND NO `cd`. `setup-project.py` reads the `origin` remote
# of `os.getcwd()` to work out which organisation you are scaffolding into, so
# the directory the person ran this from is a value and not a detail; a `cd`
# here would hand it $SCRIPT_DIR — wherever this FILE lives — instead, and
# three tests in `tests/test_setup_sh.py` say so. `exec`, because this process
# has nothing left to clean up.
#
# EXEC FROM $SHAPE_ROOT, NOT $SCRIPT_DIR. `${BASH_SOURCE[0]:-$0}` falls back to
# $PWD under `bash -s` (a piped-stdin invocation has no source file), so a
# person standing in a SUBDIRECTORY of a checkout passes the probe above —
# `is_shape_checkout` asks git, and git answers from anywhere inside the work
# tree — while $SCRIPT_DIR would still name that subdirectory, and
# `$SCRIPT_DIR/$ENTRY` would then name a file that is not there. The probe
# already asked git for the toplevel; $SHAPE_ROOT is that answer, kept
# rather than rediscovered.
if is_shape_checkout "$SCRIPT_DIR"; then
	# A value leaked from an outer shell would make setup-project.py refuse a
	# real fork checkout with the self-bootstrap sentence.
	unset OPENREPOSHAPE_SELF_BOOTSTRAP
	exec "$PY" "$SHAPE_ROOT/$ENTRY" ${1+"$@"}
fi

# --------------------------------------------------------------------------
# 0. self-bootstrap: there is no checkout, so make one
# --------------------------------------------------------------------------
# $OPENREPOSHAPE_REPO reaches `git clone`, which reads its own arguments: a
# value starting with `-` is an option to git rather than a repository. A
# CONTROL CHARACTER is refused too — a newline in this value could put a
# forged line on stdout or stderr before this script has said a word of its
# own, which is why the refusal below does not echo the value back. The `--`
# below guards the argv too; this is what names the fault instead of leaving
# a confusing git error.
case "$SHAPE_REPO" in
-*|*[![:print:]]*) die "OPENREPOSHAPE_REPO is not a value this tool will put on a \`git clone\` command line: it starts with '-' or carries a control character. Set it to a URL or a path." ;;
esac

# THE ONLY READ OF THE COMMAND LINE, AND IT CONSUMES NOTHING. Both flags are
# about the checkout made here, and every argument is passed on to Python
# unchanged whatever this scan concludes — which is what keeps one parser.
# TWO KNOWN FALSE POSITIVES, both harmless: a VALUE spelled
# `--keep-shape-checkout` sets that flag, and a VALUE spelled `--shape-ref`
# makes the WORD AFTER IT become $SHAPE_REF. Both runs are refused anyway by
# Python's `checked_value`, which rejects that leading `-` before anything is
# created — this scan only decides whether a temporary directory is removed
# and whether a ref gets checked out, never what the run itself does.
KEEP_SHAPE_CHECKOUT=0
SHAPE_REF=""
prev=""
for arg in ${1+"$@"}; do
	case "$arg" in --) break ;; esac
	case "$prev" in --shape-ref) SHAPE_REF="$arg" ;; esac
	case "$arg" in --keep-shape-checkout) KEEP_SHAPE_CHECKOUT=1 ;; esac
	prev="$arg"
done
# Mirrors `setup-project.py`'s REF_RE: a ref starts with a letter or digit,
# holds only letters, digits, '.', '_', '/', '-', is never a `..` range,
# never ends in `.lock` (git's own lock-file name for one), and is at most
# 255 characters long. Only reached when $SHAPE_REF is non-empty — every
# alternative below requires at least one character to match. The LENGTH
# bound is checked separately, below, rather than folded into this `case`:
# its refusal names the length rather than the value, because the value
# itself is 255+ characters of noise on stderr, not a fault a person could
# read at a glance the way the shapes above are.
case "$SHAPE_REF" in
[!A-Za-z0-9]*|*..*|*.lock|*[!A-Za-z0-9._/-]*) die "--shape-ref is '$SHAPE_REF', which is not a branch, tag or commit this tool will pass to \`git checkout\`: a ref starts with a letter or digit, uses only letters, digits, '.', '_', '/', '-', has no '..' and does not end in '.lock'." ;;
esac
if [ "${#SHAPE_REF}" -gt 255 ]; then
	die "--shape-ref is ${#SHAPE_REF} characters long; a branch, tag or commit this tool will pass to \`git checkout\` is at most 255 characters."
fi

say "openRepoShape setup"
say ""
say "(0) self-bootstrap"
# An explicit template, because BSD `mktemp` (macOS) requires one.
SHAPE_CHECKOUT="$(mktemp -d "${TMPDIR:-/tmp}/openreposhape-shape-XXXXXX")"
self_bootstrap_cleanup() {
	if [ "$KEEP_SHAPE_CHECKOUT" -eq 1 ]; then
		say ""
		say "kept the shape checkout: $SHAPE_CHECKOUT"
	else
		rm -rf -- "$SHAPE_CHECKOUT"
	fi
}
trap self_bootstrap_cleanup EXIT

CLONE_SHAPE_CMD=(git clone --quiet)
# `--depth 1` only means something over a real transport; git warns and
# ignores it for a bare local path (what the tests use via
# $OPENREPOSHAPE_REPO), so skip it there rather than clone shallow noise.
case "$SHAPE_REPO" in
*://*) [ -n "$SHAPE_REF" ] || CLONE_SHAPE_CMD+=(--depth 1) ;;
esac
CLONE_SHAPE_CMD+=(-- "$SHAPE_REPO" "$SHAPE_CHECKOUT")
say "  ${CLONE_SHAPE_CMD[*]}"
"${CLONE_SHAPE_CMD[@]}"
if [ -n "$SHAPE_REF" ]; then
	say "  git -C $SHAPE_CHECKOUT checkout --quiet $SHAPE_REF"
	git -C "$SHAPE_CHECKOUT" checkout --quiet "$SHAPE_REF"
fi
say "  checkout: $SHAPE_CHECKOUT"
say ""

# HAND OVER — RUN, never `exec`: the trap above belongs to THIS process, and
# exec would replace the process that owes the temporary checkout its removal.
# $OPENREPOSHAPE_SELF_BOOTSTRAP is the handshake, command-scoped rather than
# exported: it tells the child that the checkout it is standing in is one this
# script just made, so `--org` is REQUIRED there rather than read off an
# `origin` that is opensoft's own. `--into` goes FIRST, before the person's own
# arguments — an explicit `--into` of theirs is parsed after it and wins, which
# is what keeps `--into` the override it is documented as (#39).
set +e
OPENREPOSHAPE_SELF_BOOTSTRAP=1 "$PY" "$SHAPE_CHECKOUT/$ENTRY" \
	--into "$INVOCATION_DIR" ${1+"$@"}
STATUS=$?
set -e
exit "$STATUS"
