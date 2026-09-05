#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# setup.sh — clone the standard into a temp dir, scaffold, clean up.
#
#   curl -fsSL https://raw.githubusercontent.com/opensoft/openRepoShape/main/setup.sh \
#       | bash -s -- --org <your-org> --project Atlas
#
# Run from wherever: if this is not already a checkout of openRepoShape it
# self-bootstraps — clones `opensoft/openRepoShape` (or `$OPENREPOSHAPE_REPO`,
# for a fork or mirror) into a temporary directory with `mktemp -d`, re-runs
# itself from there with the same arguments, and removes the temporary
# checkout on exit (`--keep-shape-checkout` keeps it and prints the path).
# `--org` is then REQUIRED: there is no fork origin left to read it from. Run
# it from inside an existing checkout instead (the developer path) and it
# behaves exactly as before, still detecting the organisation from `origin`.
#
# Either way it checks your machine, works out which organisation you are
# scaffolding into, checks the three repository names against the naming
# policy, shows you the plan, asks once, creates the three repositories,
# clones the assembly root and bootstraps it. Nothing is created before you
# have said yes.
#
# WHY A SHELL SCRIPT AND NOT MORE PYTHON. This is the FIRST thing a person
# runs, before they know anything about the repository, and it must work with
# what is already on the machine. It shells out to the same
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
SHAPE_REF=""
KEEP_SHAPE_CHECKOUT=0
PASSTHROUGH=()

# Captured before argument parsing consumes "$@" below, so a self-bootstrap
# re-exec (section 0) can hand the temporary checkout's setup.sh the exact
# same invocation.
ORIGINAL_ARGS=("$@")

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
  --org <org>             override the detected organisation. REQUIRED when
                          run outside a checkout of openRepoShape
                          (self-bootstrap mode): there is no origin to read it
                          from.
  --allow-upstream-org    permit `--org opensoft` itself: opensoft is the
                          upstream owner of openRepoShape, and almost never
                          what you meant to scaffold into.
  --shape-ref <ref>       self-bootstrap mode only: clone this commit or tag
                          of the standard instead of its default branch.
  --keep-shape-checkout   self-bootstrap mode only: do not delete the
                          temporary checkout on exit; print its path instead.
  --yes                   skip the confirmation prompt
  --local-remote-dir <d>  TEST PATH: create three BARE repositories in <d> and
                          use them as origins. No network, no `gh`, and no real
                          repository is created.
  -h, --help              this text

Set $OPENREPOSHAPE_REPO to clone a fork or mirror in self-bootstrap mode
instead of opensoft/openRepoShape.

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
	--shape-ref) SHAPE_REF="${2:?--shape-ref needs a value}"; shift 2 ;;
	--keep-shape-checkout) KEEP_SHAPE_CHECKOUT=1; shift ;;
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

# --------------------------------------------------------------------------
# 0. self-bootstrap: run from wherever a checkout of openRepoShape is not
# --------------------------------------------------------------------------
# `curl | bash -s --` has no file on disk at all: $SCRIPT_DIR then resolves to
# $PWD (see the BASH_SOURCE fallback above), which is an openRepoShape
# checkout only by coincidence. Detect the real thing by asking git, not by
# trusting the directory a person happened to be standing in.
SHAPE_REPO="${OPENREPOSHAPE_REPO:-https://github.com/opensoft/openRepoShape.git}"

is_shape_checkout() {
	local dir="$1" toplevel
	toplevel="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || return 1
	[ -n "$toplevel" ] && [ -f "$toplevel/scaffold-project.py" ] \
		&& [ -f "$toplevel/contracts/repository-naming.yaml" ]
}

if ! is_shape_checkout "$SCRIPT_DIR"; then
	[ -n "$ORG" ] || die "running outside a checkout of openRepoShape (self-bootstrap mode): there is no fork origin to read the organisation from. Re-run with --org <your-org>."

	say "openRepoShape setup"
	say ""
	say "(0) self-bootstrap"
	SHAPE_CHECKOUT="$(mktemp -d)"
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
	CLONE_SHAPE_CMD+=("$SHAPE_REPO" "$SHAPE_CHECKOUT")
	say "  ${CLONE_SHAPE_CMD[*]}"
	"${CLONE_SHAPE_CMD[@]}"
	if [ -n "$SHAPE_REF" ]; then
		say "  git -C $SHAPE_CHECKOUT checkout --quiet $SHAPE_REF"
		git -C "$SHAPE_CHECKOUT" checkout --quiet "$SHAPE_REF"
	fi
	say "  checkout: $SHAPE_CHECKOUT"
	say ""

	# WHERE THE NEW PROJECT LANDS (#39). The re-exec runs from the TEMPORARY
	# checkout, so the child's own default parent — `..` of the directory
	# setup.sh lives in — is /tmp, and the project was cloned there and left
	# behind when the checkout beside it was deleted. It belongs where the
	# person was standing, so the invocation directory is passed as --into.
	# FIRST, before their own arguments: an explicit --into of theirs is
	# parsed after this one and wins, which is what keeps --into the override
	# it is documented as. Passing it rather than teaching the child a new
	# variable also means the clone lands correctly even when --shape-ref
	# pins a version of the standard that predates this fix.
	set +e
	bash "$SHAPE_CHECKOUT/setup.sh" --into "$INVOCATION_DIR" "${ORIGINAL_ARGS[@]}"
	STATUS=$?
	set -e
	exit "$STATUS"
fi

cd "$SCRIPT_DIR"

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
# rules, and on a checkout with two remotes (`origin` plus an `upstream`
# pointing at opensoft/openRepoShape — kept only by someone contributing back
# to the standard itself) it can prefer `upstream` over `origin`. `origin` is
# the remote that means "this clone", in every mode, so it is read directly
# and parsed by hand; `gh repo view` is consulted only as a fallback, and only
# ON THE ORIGIN URL itself (never bare), so it cannot go pick `upstream`
# either.
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

# `origin` pointing at opensoft itself means this checkout IS the upstream —
# there is no fork to inherit an organisation from, exactly like self-bootstrap
# mode above, so the fix is the same: pass --org. This is a narrower ask than
# the old "you almost certainly cloned the wrong thing" refusal, because
# running setup.sh from a plain `git clone opensoft/openRepoShape` with an
# explicit --org is now a legitimate developer path, not a mistake.
if [ -z "$ORG" ] && [ "$ORIGIN_ORG" = "$UPSTREAM_ORG" ]; then
	die "you are running from the upstream checkout ($ORIGIN_URL); pass --org <your-org>."
fi

if [ -n "$ORG" ]; then
	ok "organisation $ORG (from --org)"
elif [ -n "$ORIGIN_ORG" ]; then
	ORG="$ORIGIN_ORG"
	ok "organisation $ORG (from the \`origin\` remote: $ORIGIN_URL)"
elif [ -n "$ORIGIN_URL" ] && [ "$LOCAL_MODE" -ne 1 ] \
	&& ORG="$(gh repo view "$ORIGIN_URL" --json owner --jq .owner.login 2>/dev/null)" \
	&& [ -n "$ORG" ]; then
	if [ "$ORG" = "$UPSTREAM_ORG" ]; then
		die "you are running from the upstream checkout ($ORIGIN_URL); pass --org <your-org>."
	fi
	ok "organisation $ORG (from \`gh repo view\` on the origin URL: $ORIGIN_URL; could not parse it by hand)"
elif [ "$LOCAL_MODE" -eq 1 ]; then
	ORG="localorg"
	ok "organisation $ORG (placeholder; no \`origin\` remote to read, and --local-remote-dir creates nothing on GitHub)"
else
	die "cannot work out which organisation to scaffold into: this clone has no \`origin\` remote and no --org was given. Re-run with --org <your-org>."
fi

# A checkout kept for contributing to the standard itself may still carry an
# `upstream` remote pointing at opensoft. Name it so a person who did not
# expect one at all is not left guessing why the detected organisation is not
# opensoft's.
UPSTREAM_REMOTE_URL="$(git -C "$INVOCATION_DIR" remote get-url upstream 2>/dev/null || true)"
if [ -n "$UPSTREAM_REMOTE_URL" ]; then
	UPSTREAM_REMOTE_ORG="$(detect_org_from_url "$UPSTREAM_REMOTE_URL")"
	if [ -n "$UPSTREAM_REMOTE_ORG" ] && [ -n "$ORIGIN_ORG" ] && [ "$UPSTREAM_REMOTE_ORG" != "$ORIGIN_ORG" ]; then
		say "  upstream is $UPSTREAM_REMOTE_ORG; scaffolding into $ORG"
	fi
fi

# The guard that matters now that ORG is never silently set to opensoft by
# detection (see the die above): the only way to reach this point with
# ORG=opensoft is an explicit `--org opensoft`, which is almost never what
# anyone means — it would create three repositories in opensoft's own
# namespace. It applies in EVERY mode, --local-remote-dir included: `--org` is
# what a scaffolded `project.yaml` records as the owner of all three legs, so
# a manifest reading `opensoft/Sample` is wrong regardless of whether any
# network call happened. A local run with no `origin` remote and no --org
# gets the `localorg` placeholder, so the guard never fires by surprise.
if [ "$ORG" = "$UPSTREAM_ORG" ] && [ "$ALLOW_UPSTREAM_ORG" -ne 1 ]; then
	die "the organisation is '$UPSTREAM_ORG', which is the UPSTREAM owner of openRepoShape itself, and scaffolding here would create three repositories in opensoft's own namespace.

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
# `..` is the DEVELOPER PATH's answer: a checkout's parent is where the person
# cloned it, so the new project lands beside it. Self-bootstrap mode has no
# such neighbour to land beside and passes --into instead (see section 0).
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
