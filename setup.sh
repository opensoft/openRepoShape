#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# setup.sh — fork, clone, run one command.
#
#   gh repo fork opensoft/openRepoShape --org <your-org> --clone
#   cd openRepoShape
#   ./setup.sh --project Atlas
#
# It checks your machine, works out which organisation you are in, checks the
# three repository names against the naming policy, shows you the plan, asks
# once, creates the three repositories, clones the assembly root beside this
# fork and bootstraps it. Nothing is created before you have said yes.
#
# WHY A SHELL SCRIPT AND NOT MORE PYTHON. This is the FIRST thing a person runs
# in a fork, before they know anything about the repository, and it must work
# with what is already on the machine. It shells out to the same
# `scripts/validate-repository-naming.py`, `scaffold-project.py` and
# `make bootstrap` that the README documents — it adds no behaviour of its own
# and skips no step, so a person who prefers to run those three by hand gets
# exactly the same result. The README's "What setup.sh does" section is the
# same commands, in the same order.

set -euo pipefail

INVOCATION_DIR="$PWD"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM_ORG="opensoft"

PROJECT=""
ORG=""
PROJECT_ID=""
DISPLAY_NAME=""
VISIBILITY="private"
ELECTED_BY=""
INTO=""
LOCAL_REMOTE_DIR=""
ASSUME_YES=0
ALLOW_UPSTREAM_ORG=0
PASSTHROUGH=()

TICK="✓"
CROSS="✗"

usage() {
	cat <<'USAGE'
usage: ./setup.sh --project <Project> [options] [-- <extra scaffold flags>]

  --project <Project>     the assembly-root name: ONE CamelCase token, no
                          hyphen, underscore, dot or space. Prompted for when
                          omitted and a terminal is attached.
  --id <id>               lowercase project id      (default: project lowercased)
  --name "<Display>"      display name              (default: the project name)
  --visibility private|public|internal              (default: private)
  --elected-by "<Name>"   who is electing the shape (default: your gh login)
  --into <dir>            PARENT directory for the clone (default: ..), so the
                          clone lands at <dir>/<Project>
  --org <org>             override the detected organisation
  --allow-upstream-org    permit scaffolding into `opensoft`. You almost
                          certainly cloned the upstream instead of your fork.
  --yes                   skip the confirmation prompt
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Anything after `--` is passed straight through to scaffold-project.py.
USAGE
}

say() { printf '%s\n' "$*"; }
ok() { printf '  %s %s\n' "$TICK" "$*"; }
bad() { printf '  %s %s\n' "$CROSS" "$*" >&2; }
die() { printf '\nREFUSED: %s\n' "$1" >&2; exit "${2:-2}"; }

abspath() {
	case "$1" in
	/*) printf '%s' "$1" ;;
	*) printf '%s/%s' "$INVOCATION_DIR" "$1" ;;
	esac
}

# --------------------------------------------------------------------------
# arguments
# --------------------------------------------------------------------------
while [ $# -gt 0 ]; do
	case "$1" in
	--project) PROJECT="${2:?--project needs a value}"; shift 2 ;;
	--org) ORG="${2:?--org needs a value}"; shift 2 ;;
	--id) PROJECT_ID="${2:?--id needs a value}"; shift 2 ;;
	--name) DISPLAY_NAME="${2:?--name needs a value}"; shift 2 ;;
	--visibility) VISIBILITY="${2:?--visibility needs a value}"; shift 2 ;;
	--elected-by) ELECTED_BY="${2:?--elected-by needs a value}"; shift 2 ;;
	--into) INTO="$(abspath "${2:?--into needs a value}")"; shift 2 ;;
	--local-remote-dir) LOCAL_REMOTE_DIR="$(abspath "${2:?--local-remote-dir needs a value}")"; shift 2 ;;
	--yes | -y) ASSUME_YES=1; shift ;;
	--allow-upstream-org) ALLOW_UPSTREAM_ORG=1; shift ;;
	-h | --help) usage; exit 0 ;;
	--) shift; PASSTHROUGH=("$@"); break ;;
	*) usage >&2; die "unknown argument: $1" ;;
	esac
done

case "$VISIBILITY" in
private | public | internal) ;;
*) die "--visibility is $VISIBILITY; it must be 'private', 'public' or 'internal'" ;;
esac

LOCAL_MODE=0
if [ -n "$LOCAL_REMOTE_DIR" ]; then LOCAL_MODE=1; fi

cd "$SCRIPT_DIR"
if [ ! -f scaffold-project.py ] || [ ! -f contracts/repository-naming.yaml ]; then
	die "$SCRIPT_DIR is not an openRepoShape checkout (no scaffold-project.py). Run setup.sh from inside your fork."
fi

# --------------------------------------------------------------------------
# 1. preflight
# --------------------------------------------------------------------------
say "openRepoShape setup"
say ""
say "(1) preflight"
FAILED=0

if command -v git >/dev/null 2>&1; then
	ok "git $(git --version | awk '{print $3}')"
else
	bad "git is not installed. Install it: https://git-scm.com/downloads"
	FAILED=1
fi

if command -v python3 >/dev/null 2>&1; then
	if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
		ok "python3 $(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
	else
		bad "python3 is $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo unknown), and 3.9 or newer is required. Install a newer python3 and re-run."
		FAILED=1
	fi
else
	bad "python3 is not installed. Install Python 3.9 or newer: https://www.python.org/downloads/"
	FAILED=1
fi

if command -v make >/dev/null 2>&1; then
	ok "make $(make --version 2>/dev/null | head -1 | awk '{print $NF}')"
else
	ok "make is absent — bootstrap will run as \`python3 scripts/bootstrap.py\` instead"
fi

if [ "$LOCAL_MODE" -eq 1 ]; then
	ok "gh not required (--local-remote-dir: bare repositories on disk, no network)"
elif command -v gh >/dev/null 2>&1; then
	ok "gh $(gh --version | head -1 | awk '{print $3}')"
	if gh auth status >/dev/null 2>&1; then
		ok "gh is authenticated$(gh api user --jq '" as " + .login' 2>/dev/null || true)"
	else
		bad "gh is not authenticated. Run: gh auth login"
		FAILED=1
	fi
else
	bad "gh is not installed. Install it: https://cli.github.com — or re-run with --local-remote-dir <dir> to try this offline against bare repositories on disk."
	FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
	die "one or more prerequisites are missing (see above)."
fi

# --------------------------------------------------------------------------
# 2. which organisation
# --------------------------------------------------------------------------
say ""
say "(2) organisation"
detect_org_from_url() {
	local url="$1" rest
	case "$url" in
	*://*) rest="${url#*://}"; rest="${rest#*@}"; rest="${rest#*/}" ;;
	*:*) rest="${url#*@}"; rest="${rest#*:}" ;;
	*) rest="$url" ;;
	esac
	printf '%s' "${rest%%/*}"
}

# `gh repo view` with no argument resolves the CURRENT repository by its own
# rules, and on a fork clone (two remotes: `origin` is the fork, `upstream` is
# opensoft/openRepoShape) it can prefer `upstream` over `origin` — reporting
# `opensoft` for a perfectly correct fork and tripping the upstream-org guard
# below on a clone that was never wrong. `origin` is the remote that means
# "this clone", in every mode, so it is read directly and parsed by hand;
# `gh repo view` is consulted only as a fallback, and only ON THE ORIGIN URL
# itself (never bare), so it cannot go pick `upstream` either.
#
# Read against $INVOCATION_DIR, not the current directory — by the time we
# are here that is $SCRIPT_DIR (the `cd` a few lines up), which is wherever
# this FILE lives rather than the clone the person is standing in. The two
# are the same for the README's own `cd openRepoShape && ./setup.sh` usage;
# they differ only when setup.sh is invoked by a path from elsewhere, and
# then the clone you are IN is the one whose organisation you mean.
ORIGIN_URL="$(git -C "$INVOCATION_DIR" remote get-url origin 2>/dev/null || true)"
ORIGIN_ORG=""
if [ -n "$ORIGIN_URL" ]; then
	ORIGIN_ORG="$(detect_org_from_url "$ORIGIN_URL")"
fi

if [ -n "$ORG" ]; then
	ok "organisation $ORG (from --org)"
elif [ -n "$ORIGIN_ORG" ]; then
	ORG="$ORIGIN_ORG"
	ok "organisation $ORG (from the \`origin\` remote: $ORIGIN_URL)"
elif [ -n "$ORIGIN_URL" ] && [ "$LOCAL_MODE" -ne 1 ] \
	&& ORG="$(gh repo view "$ORIGIN_URL" --json owner --jq .owner.login 2>/dev/null)" \
	&& [ -n "$ORG" ]; then
	ok "organisation $ORG (from \`gh repo view\` on the origin URL: $ORIGIN_URL; could not parse it by hand)"
elif [ "$LOCAL_MODE" -eq 1 ]; then
	ORG="localorg"
	ok "organisation $ORG (placeholder; no \`origin\` remote to read, and --local-remote-dir creates nothing on GitHub)"
else
	die "cannot work out which organisation to scaffold into: this clone has no \`origin\` remote and no --org was given. Re-run with --org <your-org>."
fi

# The normal fork shape: `origin` is the fork, `upstream` is opensoft's. Name
# it so a person who did not expect an `upstream` remote at all is not left
# guessing why the detected organisation is not opensoft's.
UPSTREAM_REMOTE_URL="$(git -C "$INVOCATION_DIR" remote get-url upstream 2>/dev/null || true)"
if [ -n "$UPSTREAM_REMOTE_URL" ]; then
	UPSTREAM_REMOTE_ORG="$(detect_org_from_url "$UPSTREAM_REMOTE_URL")"
	if [ -n "$UPSTREAM_REMOTE_ORG" ] && [ -n "$ORIGIN_ORG" ] && [ "$UPSTREAM_REMOTE_ORG" != "$ORIGIN_ORG" ]; then
		say "  upstream is $UPSTREAM_REMOTE_ORG; scaffolding into $ORG"
	fi
fi

# The guard that matters. `gh repo fork ... --clone` leaves you in YOUR fork;
# `git clone opensoft/openRepoShape` leaves you in the upstream. Both look
# identical from inside the directory, and only one of them should be creating
# repositories.
#
# It applies in EVERY mode, --local-remote-dir included. What is skipped for a
# local run is the `gh` call, not the origin-remote read: `--org` is what a
# scaffolded `project.yaml` records as the owner of all three legs, so a
# manifest reading `opensoft/Sample` written from an upstream clone is exactly
# as wrong as three repositories in the wrong place. A local run with no
# `origin` remote and no --org gets the `localorg` placeholder, so the guard
# never fires by surprise.
if [ "$ORG" = "$UPSTREAM_ORG" ] && [ "$ALLOW_UPSTREAM_ORG" -ne 1 ]; then
	die "the detected organisation is '$UPSTREAM_ORG', which is the UPSTREAM. You have almost certainly cloned opensoft/openRepoShape instead of a fork of it, and scaffolding here would create three repositories in the wrong organisation.

  To fork:      gh repo fork $UPSTREAM_ORG/openRepoShape --org <your-org> --clone
  Wrong guess?  re-run with --org <your-org>
  You meant it? re-run with --allow-upstream-org"
fi

# --------------------------------------------------------------------------
# 3. the project
# --------------------------------------------------------------------------
say ""
say "(3) project"
if [ -z "$PROJECT" ]; then
	if [ -t 0 ]; then
		printf '  project name (ONE CamelCase token, e.g. Atlas): '
		read -r PROJECT || true
	fi
fi
if [ -z "$PROJECT" ]; then
	usage >&2
	die "no --project given, and no terminal to ask on."
fi

if [ -z "$ELECTED_BY" ] && [ "$LOCAL_MODE" -ne 1 ]; then
	ELECTED_BY="$(gh api user --jq .login 2>/dev/null || true)"
fi
if [ -z "$ELECTED_BY" ]; then
	# Per-invocation identity first (GIT_AUTHOR_NAME), then the repo/global
	# config, then the gh login — never a global config WRITE.
	ELECTED_BY="${GIT_AUTHOR_NAME:-$(git config user.name 2>/dev/null || true)}"
fi
if [ -z "$ELECTED_BY" ]; then
	die "cannot work out who is electing this shape. Re-run with --elected-by 'Your Name' — the manifest records whose act it was."
fi

ok "project      $PROJECT"
ok "legs         $PROJECT-spec, $PROJECT-code"
ok "visibility   $VISIBILITY"
ok "elected by   $ELECTED_BY"

# --------------------------------------------------------------------------
# 4. the names, before anything exists
# --------------------------------------------------------------------------
say ""
say "(4) naming policy"
if ! python3 scripts/validate-repository-naming.py --explain \
	"$PROJECT" "$PROJECT-spec" "$PROJECT-code"; then
	die "the names do not satisfy the naming policy (see above). A naming mistake caught here costs a message; caught later it costs three repositories and a rename." 1
fi

# --------------------------------------------------------------------------
# 5. the plan, and one explicit yes
# --------------------------------------------------------------------------
SCAFFOLD_ARGS=(--org "$ORG" --project "$PROJECT" --visibility "$VISIBILITY"
	--elected-by "$ELECTED_BY")
if [ -n "$PROJECT_ID" ]; then SCAFFOLD_ARGS+=(--id "$PROJECT_ID"); fi
if [ -n "$DISPLAY_NAME" ]; then SCAFFOLD_ARGS+=(--name "$DISPLAY_NAME"); fi
if [ "$LOCAL_MODE" -eq 1 ]; then SCAFFOLD_ARGS+=(--local-remote-dir "$LOCAL_REMOTE_DIR"); fi
SCAFFOLD_ARGS+=(${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"})

say ""
say "(5) the plan"
python3 scaffold-project.py "${SCAFFOLD_ARGS[@]}" --dry-run

if [ "$ASSUME_YES" -ne 1 ]; then
	if [ ! -t 0 ]; then
		die "this will create THREE repositories and there is no terminal to confirm on. Re-run with --yes if you mean it."
	fi
	say ""
	say "This will create THREE repositories in '$ORG'."
	printf 'Type yes to continue: '
	CONFIRM=""
	read -r CONFIRM || true
	if [ "$CONFIRM" != "yes" ]; then
		die "not confirmed; nothing was created." 1
	fi
fi

# --------------------------------------------------------------------------
# 6. create
# --------------------------------------------------------------------------
say ""
say "(6) scaffold"
python3 scaffold-project.py "${SCAFFOLD_ARGS[@]}"

# --------------------------------------------------------------------------
# 7. clone and bootstrap
# --------------------------------------------------------------------------
PARENT="${INTO:-$(cd .. && pwd)}"
mkdir -p "$PARENT"
CLONE="$PARENT/$PROJECT"

if [ "$LOCAL_MODE" -eq 1 ]; then
	ASSEMBLY_URL="$LOCAL_REMOTE_DIR/$PROJECT.git"
	SPEC_URL="$LOCAL_REMOTE_DIR/$PROJECT-spec.git"
	CODE_URL="$LOCAL_REMOTE_DIR/$PROJECT-code.git"
	# A local bare repository is a `file://` origin, which git refuses to
	# recurse into by default since the 2022 advisories. This concession is
	# specific to the test path; a real clone from GitHub needs none of it.
	CLONE_CMD=(git -c protocol.file.allow=always clone -q --recurse-submodules "$ASSEMBLY_URL" "$CLONE")
else
	ASSEMBLY_URL="https://github.com/$ORG/$PROJECT.git"
	SPEC_URL="https://github.com/$ORG/$PROJECT-spec.git"
	CODE_URL="https://github.com/$ORG/$PROJECT-code.git"
	CLONE_CMD=(git clone -q --recurse-submodules "$ASSEMBLY_URL" "$CLONE")
fi

# The three repositories now EXIST. Everything from here is recoverable by
# hand, so a failure names the command that finishes the job rather than
# leaving the person wondering what was created.
if [ -e "$CLONE" ]; then
	die "$CLONE already exists, so there is nowhere to clone into. The three repositories WERE created. Finish by hand:
    git clone --recurse-submodules $ASSEMBLY_URL
    cd $PROJECT && make bootstrap"
fi

say ""
say "(7) clone and bootstrap"
say "  ${CLONE_CMD[*]}"
"${CLONE_CMD[@]}"

if command -v make >/dev/null 2>&1; then
	(cd "$CLONE" && make bootstrap)
else
	(cd "$CLONE" && python3 scripts/bootstrap.py)
fi

# --------------------------------------------------------------------------
# 8. hand over
# --------------------------------------------------------------------------
cat <<DONE

DONE. $PROJECT is scaffolded and bootstrapped.

  clone       $CLONE
  assembly    $ASSEMBLY_URL
  spec        $SPEC_URL
  code        $CODE_URL

Next:

    cd $CLONE
    make validate          # naming, manifest, lockstep pins — what CI runs
    \$EDITOR project.yaml   # the manifest is the SOURCE of this group

Advancing a leg is ONE commit in the assembly root that moves the gitlink,
contracts/<role>-pin.yaml and any workflow @<sha> naming that leg together.
Electing this shape confers nothing: a one-repository project is reviewed
identically.
DONE
