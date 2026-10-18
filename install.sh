#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# install.sh — openRepoShape in one line, pinned to a release (#564):
#
#   curl -fsSL https://github.com/opensoft/openRepoShape/releases/latest/download/install.sh | bash
#
# A named release instead of the newest: `… | bash -s -- v1.0.1`. From a
# checkout or a download, the same: `bash install.sh [<version>]`. Running the
# same line again upgrades to the newest release. This file is attached to
# every GitHub release, which is what makes that URL always the newest one.
#
# FOUR STEPS, IN THIS ORDER, EACH SAYING IN A LINE WHAT IT DID:
#
#   1. THE RELEASE: the one named, or the newest, read from the redirect
#      github.com answers `releases/latest` with. That needs no `gh`, no token
#      and no login, because the repository is public; `gh api` is asked only
#      when the redirect names no release and `gh` is installed.
#   2. THAT RELEASE'S `openRepoShape`, fetched into a temporary directory,
#      checked to be the command, and installed by its own `--install` with
#      `$OPENREPOSHAPE_REF` set to the release tag and
#      `$OPENREPOSHAPE_RECORD_REF=1`, which asks it to record that tag beside
#      the command it places; the command then stays on it.
#   3. GIT-FILTER-REPO, which `adopt-project.py` needs and nothing else does:
#      said when it is there; installed with `pipx` when pipx is there and it
#      is not, or with `uv` when uv is there and pipx is not (#595);
#      otherwise the one command that installs it, printed.
#   4. THE INSTALLED COMMAND'S `--preflight`, LAST, and its verdict, then the
#      two readinesses: `adoption:` and `done:` (#595).
#
# install.sh ITSELF NEVER RUNS sudo, AND INSTALLS NOTHING BUT THESE TWO: the
# command and, through the pipx or uv already there, git-filter-repo. It
# never installs pipx, uv or a system package. The preflight it ends with
# offers what is missing, each behind a typed `yes` at the person's own
# terminal, exactly as `openRepoShape --preflight` always has, and some of
# those offers are `sudo` commands: that is the preflight's, asked first.
#
# EXIT STATUS:
#   0  installed, pinned to the release tag, and the preflight passed;
#   1  installed, but the preflight did not pass, or the installed command
#      does not stay on the release tag (one older than v1.0.1 cannot record
#      it): the lines above say which;
#   2  refused before anything was installed: a version that is not a ref, no
#      release found, a fetch that failed, a file that is not the command, a
#      command already there as a symbolic link (pipx's, #563), a
#      `$OPENREPOSHAPE_BIN_DIR` spelled for Windows where no `cygpath` can
#      spell it the way bash does (#667), or a directory holding a control
#      character or a `:`, which no line about `$PATH` can name (#760), or
#      a character a terminal draws as something other than itself (#837).
# git-filter-repo never changes it: only adopting needs it, and
# `adopt-project.py` refuses with its own install command where it is missing.
# What it changes is the summary (#595): `adoption:` says whether it is there
# and, where it is not, the command to run next, and `done:` says the machine
# is ready only when it is, and "ready to scaffold, not yet to adopt" when not.
#
# EVERYTHING RUNS FROM `main`, CALLED ON THE LAST LINE, INSIDE BRACES. Under
# `curl … | bash` bash reads this script from the pipe as it goes, so a
# download cut off part-way would run whatever had arrived. Inside a function
# nothing runs until the last line has arrived; the braces make that line one
# command that bash parses whole, so a download cut inside it runs nothing
# either; and by then the pipe holds nothing a child could read in its place.
#
# BASH 3.2, which is /bin/bash on every Mac: no `${x,,}`, no `declare -A`,
# no `mapfile`; an empty array never meets `set -u`.

set -euo pipefail

REPO="${OPENREPOSHAPE_REPO:-opensoft/openRepoShape}"

#: The version CI installs (`.github/workflows/tests.yml`), so what this
#: installs is what the adoption suites ran against.
FILTER_REPO_PIN="git-filter-repo==2.47.0"

#: Where uv says how to install uv itself, named for a machine with neither
#: pipx nor uv and no package manager `filter_repo_command` knows (#595).
UV_INSTALL_PAGE="https://docs.astral.sh/uv/getting-started/installation/"

WORKDIR=""

#: What `latest_from_redirect` and `latest_from_gh` found, and when they did
#: not, why. Globals rather than output, because a function run inside
#: `$(…)` is a subshell and could say only one of the two.
FOUND=""
FAULT=""

#: What step 3 found, for the summary `main` ends with (#595): 1 when
#: `adopt-project.py` will find git-filter-repo, and what the `adoption:`
#: line says, which names the command to run next where it will not.
ADOPTION_READY=0
ADOPTION=""

say() { printf '%s\n' "$*"; }
die() { printf '\nREFUSED: %s\n' "$1" >&2; exit "${2:-2}"; }

usage() {
	cat <<'USAGE'
install.sh: install openRepoShape, pinned to a release.

  curl -fsSL https://github.com/opensoft/openRepoShape/releases/latest/download/install.sh | bash
  curl -fsSL https://github.com/opensoft/openRepoShape/releases/latest/download/install.sh | bash -s -- v1.0.1
  bash install.sh [<version>]

With no <version> it installs the newest release. It fetches that release's
`openRepoShape`, installs it into ~/.local/bin pinned to the release tag,
installs git-filter-repo with pipx, or with uv where there is no pipx, when
git-filter-repo is not there (or prints the command that installs it), and
ends with `openRepoShape --preflight` and two lines: `adoption:`, whether
git-filter-repo is there, and `done:`. install.sh itself never runs sudo and
never installs pipx or uv; the preflight it ends with offers what is missing,
each behind a typed `yes` at your terminal. Run the same line again to
upgrade.

Exit 0: installed, pinned, and the preflight passed. 1: installed, but the
preflight did not pass, or the command does not stay on the release tag. 2:
refused, and nothing was installed. git-filter-repo, which only adopting
needs, never changes it.

  $OPENREPOSHAPE_REPO       owner/name to install from (default opensoft/openRepoShape)
  $OPENREPOSHAPE_BIN_DIR    where the command goes      (default ~/.local/bin)
USAGE
}

# THE REPOSITORY, AS AN OWNER/NAME, because every URL below is built from it.
# The launcher also takes a URL or a path in this variable, for the clone
# setup.sh makes; there is no release at either, so this refuses them by
# name. A control character is refused before anything is echoed, and
# before it a character a terminal draws as something other than itself
# (#837), named by its code point: first, because `[![:print:]]` is the
# locale's, matching every byte past ASCII under `C` and none of those
# characters under a UTF-8 locale, where the refusal below would echo them.
checked_repo() {
	local misdrawn
	misdrawn="$(LC_ALL=C; misdrawn_characters "$REPO")"
	[ -z "$misdrawn" ] ||
		die "\$OPENREPOSHAPE_REPO holds a character a terminal draws as something other than itself ($misdrawn): one that is invisible, is drawn as another character, ends a line or reorders the text around it. It must be an owner/name on github.com, such as opensoft/openRepoShape."
	case "$REPO" in
	*[![:print:]]*) die "\$OPENREPOSHAPE_REPO carries a control character; it must be an owner/name on github.com, such as opensoft/openRepoShape." ;;
	esac
	case "$REPO" in
	[A-Za-z0-9]*/[A-Za-z0-9._-]*) ;;
	*) die "\$OPENREPOSHAPE_REPO is '$REPO', which is not an owner/name on github.com, such as opensoft/openRepoShape: this installer builds github.com URLs from it." ;;
	esac
	case "$REPO" in
	*/*/* | *[!A-Za-z0-9._/-]* | */. | */..) die "\$OPENREPOSHAPE_REPO is '$REPO', which is not an owner/name on github.com, such as opensoft/openRepoShape: this installer builds github.com URLs from it." ;;
	esac
}

# THE LAUNCHER'S `checked_ref`, TRANSCRIBED: the version reaches a URL here
# and `git checkout` once the command runs, so it is held to the same three
# checks in the same order (length, then a control character, then the
# shape, which is the only one that echoes it), plus the empty value, and,
# between the length and the control character, a character a terminal
# draws as something other than itself, as the launcher's `ref_fault` has
# it (#837). Not shared, because this file arrives alone down a pipe.
checked_version() {
	local ref="$1" what="$2" misdrawn
	[ -n "$ref" ] || die "$what is empty. Name a release, such as v1.0.1, or none for the newest."
	if [ "${#ref}" -gt 255 ]; then
		die "$what is ${#ref} characters long; a release tag, branch or commit is at most 255 characters."
	fi
	misdrawn="$(LC_ALL=C; misdrawn_characters "$ref")"
	[ -z "$misdrawn" ] ||
		die "$what holds a character a terminal draws as something other than itself ($misdrawn): one that is invisible, is drawn as another character, ends a line or reorders the text around it. No release tag, branch or commit holds one."
	case "$ref" in
	*[![:print:]]*) die "$what carries a control character, which is not a release tag, branch or commit." ;;
	esac
	case "$ref" in
	[!A-Za-z0-9]* | *..* | *.lock | *[!A-Za-z0-9._/-]*) die "$what is '$ref', which is not a release tag, branch or commit: a ref starts with a letter or digit, uses only letters, digits, '.', '_', '/', '-', has no '..' and does not end in '.lock'." ;;
	esac
}

# THE NEWEST RELEASE, FROM THE REDIRECT. `releases/latest` answers 302 with
# `location: …/releases/tag/<tag>`; a repository with no release yet answers
# with `…/releases`, which names no tag and is no answer. The header name is
# matched in any case (HTTP/2 sends it in lower case, HTTP/1.1 need not),
# without `${x,,}`, which bash 3.2 does not have, and a relative location is
# read the same way as a whole URL.
#
# EVERY curl HERE IS HTTPS ONLY, REDIRECTS INCLUDED, AT TLS 1.2 OR NEWER
# (SonarCloud shell:S6506), with the flags written out on the curl line
# itself, never gathered into an array, so a reader and the analyser both
# see them there. `tests/test_install_sh.py` holds every curl line to it.
latest_from_redirect() {
	local url="$1" headers line value status=0
	FOUND=""
	command -v curl >/dev/null 2>&1 || {
		FAULT="curl is not installed"
		return 1
	}
	headers="$(curl -fsSI --proto '=https' --proto-redir '=https' --tlsv1.2 "$url" 2>/dev/null)" || status=$?
	if [ "$status" -ne 0 ]; then
		FAULT="curl failed, exit $status"
		return 1
	fi
	while IFS= read -r line; do
		line="${line%$'\r'}"
		case "$line" in
		[Ll][Oo][Cc][Aa][Tt][Ii][Oo][Nn]:*)
			value="${line#*:}"
			while :; do
				case "$value" in
				' '* | $'\t'*) value="${value#?}" ;;
				*) break ;;
				esac
			done
			case "$value" in
			*/releases/tag/?*)
				FOUND="${value##*/releases/tag/}"
				return 0
				;;
			esac
			# The location is named only when it is text a terminal draws as
			# it is: no control character, and no character it draws as
			# something other than itself (#837).
			FAULT="it redirects to a location that names no release"
			if [ -z "$(LC_ALL=C; misdrawn_characters "$value")" ]; then
				case "$value" in
				*[![:print:]]*) ;;
				*) FAULT="it redirects to $value, which names no release" ;;
				esac
			fi
			return 1
			;;
		esac
	done <<<"$headers"
	FAULT="it answered with no location"
	return 1
}

# THE FALLBACK, AND ONLY WHERE `gh` IS INSTALLED: `gh api` needs a login even
# for a public repository, which is why it is not the first way.
latest_from_gh() {
	local status=0
	FOUND=""
	command -v gh >/dev/null 2>&1 || {
		FAULT="gh is not installed"
		return 1
	}
	FOUND="$(gh api "repos/$REPO/releases/latest" --jq .tag_name 2>/dev/null)" || status=$?
	if [ "$status" -ne 0 ] || [ -z "$FOUND" ]; then
		FAULT="gh failed, exit $status"
		return 1
	fi
}

# THE COMMAND, AND NOT A PAGE THAT SAYS 200. A captive portal, a proxy's
# error page or a renamed file is refused here, before anything runs it:
# the launcher's first line, and the `INSTALLABLES=(` line that
# `tests/test_repo_hygiene.py` holds it to carrying.
looks_like_the_launcher() {
	local line first=1
	while IFS= read -r line || [ -n "$line" ]; do
		if [ "$first" -eq 1 ]; then
			[ "$line" = "#!/usr/bin/env bash" ] || return 1
			first=0
		fi
		case "$line" in "INSTALLABLES=("*) return 0 ;; esac
	done <"$1"
	return 1
}

# THE ONE COMMAND THAT INSTALLS IT HERE, for a machine with neither pipx nor
# uv, PRINTED AND NEVER RUN, in POSIX shell, and nothing but the command, so
# it pastes and runs as printed in any shell (#595, the review on #598: an
# interactive zsh hands a `# comment` to the command as arguments). Never
# `pip install --user`: Debian 12, Ubuntu 23.04 and Arch, among others, mark
# the system Python externally managed (PEP 668) and refuse it.
#
#   * brew's, where `brew` is;
#   * pipx from apt or dnf, which takes `sudo` and is the person's to type,
#     then git-filter-repo through it at the version CI runs, then `pipx
#     ensurepath`, which exits 0 whether or not it had a directory to add;
#   * Arch's own package where `pacman` is, which lands on PATH in one step.
#     pacman cannot pin a version: Arch's `extra` holds 2.47.0, CI's, as of
#     2026-10-15;
#   * and with no package manager this knows, uv's, once uv itself is
#     installed, which the caller says first: the one command here that
#     needs a tool that is not on this machine.
filter_repo_command() {
	if command -v brew >/dev/null 2>&1; then
		printf '%s' "brew install git-filter-repo"
	elif command -v apt-get >/dev/null 2>&1; then
		printf '%s' "sudo apt-get install -y pipx && pipx install $FILTER_REPO_PIN && pipx ensurepath"
	elif command -v dnf >/dev/null 2>&1; then
		printf '%s' "sudo dnf install -y pipx && pipx install $FILTER_REPO_PIN && pipx ensurepath"
	elif command -v pacman >/dev/null 2>&1; then
		printf '%s' "sudo pacman -S --needed git-filter-repo"
	else
		printf '%s' "uv tool install $FILTER_REPO_PIN"
	fi
}

adoption_ready() {
	ADOPTION_READY=1
	ADOPTION="git-filter-repo is installed, which adopt-project.py needs beyond what the preflight checks."
}

# `$1` says why it is not ready, and `$2` what to do first, in the caller's
# own words: a command comes after `run: `, at the end of the line, or between
# backticks, so it pastes as printed.
adoption_not_ready() {
	ADOPTION_READY=0
	ADOPTION="NOT READY: adopt-project.py needs git-filter-repo, and $1. Before adopting a repository, $2"
}

# ONE INSTALL, WITH THE pipx OR uv ALREADY HERE, into an environment of its
# own and at the version CI runs. Installed is not yet found: either tool puts
# the command in a directory of its own (`~/.local/bin` by default) that this
# shell may not have on PATH, and `adopt-project.py` looks on PATH, so the
# install is checked by looking where it will. `$1` names the tool, `$2` is
# what puts its directory on PATH, and the rest is the install.
filter_repo_install() {
	local tool="$1" ensure="$2" status=0
	shift 2
	say "git-filter-repo: not installed; installing it with $tool, because adopt-project.py needs it: $*"
	"$@" || status=$?
	if [ "$status" -ne 0 ]; then
		say "git-filter-repo: $tool could not install it (exit $status). Before adopting a repository, install it: $*"
		adoption_not_ready "$tool could not install it (exit $status)" "run: $*"
	elif command -v git-filter-repo >/dev/null 2>&1; then
		say "git-filter-repo: installed with $tool"
		adoption_ready
	else
		say "git-filter-repo: installed with $tool, into a directory that is not on PATH yet: run \`$ensure\` and open a new shell"
		adoption_not_ready "$tool installed it into a directory that is not on PATH yet" "run \`$ensure\`, then open a new shell"
	fi
}

filter_repo_step() {
	local found how="run:"
	if found="$(command -v git-filter-repo 2>/dev/null)" && [ -n "$found" ]; then
		say "git-filter-repo: already installed ($found)"
		adoption_ready
		return 0
	fi
	if command -v git >/dev/null 2>&1 &&
		git filter-repo --version >/dev/null 2>&1; then
		say "git-filter-repo: already installed (git filter-repo --version answers)"
		adoption_ready
		return 0
	fi
	if command -v pipx >/dev/null 2>&1; then
		filter_repo_install pipx "pipx ensurepath" pipx install "$FILTER_REPO_PIN"
		return 0
	fi
	if command -v uv >/dev/null 2>&1; then
		filter_repo_install uv "uv tool update-shell" uv tool install "$FILTER_REPO_PIN"
		return 0
	fi
	found="$(filter_repo_command)"
	case "$found" in
	"uv "*) how="install uv ($UV_INSTALL_PAGE), then run:" ;;
	esac
	say "git-filter-repo: not installed, and there is neither pipx nor uv to install it with. Only adopt-project.py needs it; before adopting a repository, $how"
	say "    $found"
	adoption_not_ready "it is not installed" "$how $found"
}

# THE CHARACTERS A TERMINAL DRAWS AS SOMETHING OTHER THAN THEMSELVES, AND
# WHICH OF THEM "$1" HOLDS (#837): the launcher's `MISDRAWN_CHARACTERS` and
# `misdrawn_characters`, copied as they are, for the reason the control
# check in `main` is copied: this file arrives alone down a pipe. The
# launcher says why these characters and no others, and which forms of
# UTF-8 the function builds (two, three and four bytes), and
# `tests/test_openreposhape_command.py` holds the two copies to one text.
# `main` asks it of the directory, of an option, `checked_repo` of the
# repository, `checked_version` of a version and `latest_from_redirect`
# of the location it reads, each before any line prints the value.
MISDRAWN_CHARACTERS=(00AD 061C 200B 200E-200F 2028-202E 2060-206F FEFF FFF9-FFFB 1D173-1D17A E0001)

misdrawn_characters() {
	local value="$1" entry code last bytes name found=""
	for entry in "${MISDRAWN_CHARACTERS[@]}"; do
		code=$((0x${entry%-*}))
		last=$((0x${entry#*-}))
		while [ "$code" -le "$last" ]; do
			if [ "$code" -lt 2048 ]; then
				printf -v bytes '\\0%o\\0%o' $((0xC0 | (code >> 6))) \
					$((0x80 | (code & 63)))
			elif [ "$code" -lt 65536 ]; then
				printf -v bytes '\\0%o\\0%o\\0%o' $((0xE0 | (code >> 12))) \
					$((0x80 | ((code >> 6) & 63))) $((0x80 | (code & 63)))
			else
				printf -v bytes '\\0%o\\0%o\\0%o\\0%o' \
					$((0xF0 | (code >> 18))) $((0x80 | ((code >> 12) & 63))) \
					$((0x80 | ((code >> 6) & 63))) $((0x80 | (code & 63)))
			fi
			printf -v bytes '%b' "$bytes"
			case "$value" in
			*"$bytes"*)
				printf -v name 'U+%04X' "$code"
				found="${found:+$found, }$name"
				;;
			*) ;;
			esac
			code=$((code + 1))
		done
	done
	printf '%s' "$found"
}

# THE VALUE AS THE PERSON'S LOCALE READS IT, IN UTF-8, WHERE THAT LOCALE
# READS TWO OR MORE OF ITS BYTES AS ONE CHARACTER (#858): the launcher's
# `locale_reading`, copied as it is, for the reason the control check in
# `main` is copied. The launcher says when it reads the value again and
# when the bytes decide, and `tests/test_openreposhape_command.py` holds the
# two copies to one text. `main` asks it of a directory the bytes refuse.
locale_reading() {
	local charmap reading
	charmap="$(locale charmap 2>/dev/null)" || return 1
	case "$charmap" in
	"" | [Uu][Tt][Ff]-8 | [Uu][Tt][Ff]8 | ANSI_X3.4-1968 | *ASCII*) return 1 ;;
	*) ;;
	esac
	reading="$(printf '%s' "$1" | iconv -f "$charmap" -t UTF-8 2>/dev/null)" ||
		return 1
	[ "$(printf '%s' "$reading" | iconv -f UTF-8 -t "$charmap" 2>/dev/null)" = "$1" ] ||
		return 1
	(
		LC_ALL=C
		letters=${reading//[$'\200'-$'\277']/}
		[ "${#letters}" -lt "${#1}" ] || exit 1
		printf '%s' "$reading"
	)
}

main() {
	local version="" asked launcher_url bin_dir spelled target shown status=0 pinned=1
	local misdrawn seen
	local machine="this machine is ready"

	# NOTHING A CHILD READS IS THIS SCRIPT. Piped, stdin is the pipe the
	# script came down; a terminal stays a terminal, which is where the
	# preflight asks before it offers anything.
	[ -t 0 ] || exec </dev/null

	while [ $# -gt 0 ]; do
		case "$1" in
		-h | --help) usage; exit 0 ;;
		--) shift; continue ;;
		-*)
			misdrawn="$(LC_ALL=C; misdrawn_characters "$1")"
			[ -z "$misdrawn" ] ||
				die "an option holds a character a terminal draws as something other than itself ($misdrawn): one that is invisible, is drawn as another character, ends a line or reorders the text around it. The one argument is a version, such as v1.0.1; with none, the newest release."
			case "$1" in
			*[![:print:]]*) die "an option carries a control character. The one argument is a version, such as v1.0.1; with none, the newest release." ;;
			esac
			die "unknown option '$1'. The one argument is a version, such as v1.0.1; with none, the newest release."
			;;
		*)
			[ -z "$version" ] || die "two versions given. Name one release, such as v1.0.1, or none for the newest."
			version="$1"; shift ;;
		esac
	done

	checked_repo
	command -v curl >/dev/null 2>&1 ||
		die "curl is not installed, and this installer fetches with it. Install curl, or install by hand with: gh api repos/$REPO/contents/openRepoShape -H 'Accept: application/vnd.github.raw' | bash -s -- --install"

	bin_dir="${OPENREPOSHAPE_BIN_DIR:-$HOME/.local/bin}"
	# A DIRECTORY HOLDING A CONTROL CHARACTER IS REFUSED FIRST (#760), before
	# any line below names it: a newline breaks a line in two, a carriage
	# return rewrites it on the terminal and an escape is the terminal's to
	# act on, and the `install:`, `preflight:` and `done:` lines would print
	# the directory as typed. The command refuses the same value, but only
	# from the release that added the check, and only after this file had
	# fetched it. The `case` is `install_commands`'s in `openRepoShape`,
	# copied for the reason the drive-letter one below is, and the refusal
	# says nothing of the value. `[[:cntrl:]]` and not `[![:print:]]`, which
	# `checked_repo` uses: a directory with a letter the locale does not
	# print (`café` under LC_ALL=C) is no fault of the directory's. The check
	# runs under `LC_ALL=C` and names U+0080 to U+009F's two bytes (`\302`,
	# then `\200` to `\237`), so a C1 control is refused in every locale,
	# whatever else the value holds, unless the locale reads those bytes as
	# text (#858, below); U+2028 and U+2029, which only a UTF-8 locale's
	# `[[:cntrl:]]` matched, are the next check's (#837).
	# Left to the locale, `[[:cntrl:]]` matches a C1 control only in a value
	# that is valid UTF-8: one byte that is not (a lone 0xE9) makes bash
	# match byte by byte, and then U+009B's two bytes are not controls, as
	# under `C` (measured with bash 5.2.21). The locale is `C` in a subshell,
	# so that the match is byte by byte whatever a libc says of a byte in a
	# UTF-8 locale, and the locale of every line below is as it was.
	# WHERE THE BYTES ARE REFUSED, THE PERSON'S LOCALE IS ASKED HOW IT READS
	# THEM (#858), as the command asks it: a multibyte charset that is not
	# UTF-8 may read them as text, and then the C1 bytes and
	# `misdrawn_characters` are looked for in `locale_reading`'s UTF-8
	# instead. Only a value the bytes refuse is read again, so no name
	# placed before is refused, and where nothing reads it again the bytes
	# decide, as before. `[[:cntrl:]]` is asked of the bytes as typed. The
	# trade: such a locale, left in a terminal that reads UTF-8, has C1
	# bytes it reads as letters installed into and printed in the lines
	# below, and that terminal acts on them.
	seen="$bin_dir"
	if (LC_ALL=C; case "$bin_dir" in *$'\302'[$'\200'-$'\237']*) exit 0 ;; *) exit 1 ;; esac) ||
		[ -n "$(LC_ALL=C; misdrawn_characters "$bin_dir")" ]; then
		seen="$(locale_reading "$bin_dir")" || seen="$bin_dir"
	fi
	if (LC_ALL=C
		case "$bin_dir" in *[[:cntrl:]]*) exit 0 ;; *) ;; esac
		case "$seen" in *$'\302'[$'\200'-$'\237']*) exit 0 ;; *) exit 1 ;; esac); then
		die "the directory to install into holds a control character, such as a newline, a carriage return, a tab or an escape, and no line about \$PATH can print such a name as it is: a terminal acts on it. Nothing was installed. Set \$OPENREPOSHAPE_BIN_DIR to a directory without one, then run this line again."
	fi
	# A CHARACTER A TERMINAL DRAWS AS SOMETHING OTHER THAN ITSELF IS REFUSED
	# NEXT (#837), as the command refuses it, and before any request: the
	# name would read as another directory's in every line below. The
	# refusal names each one by its code point, because nobody can see it,
	# and says nothing else of the value. It is asked of the locale's
	# reading where there is one (#858).
	misdrawn="$(LC_ALL=C; misdrawn_characters "$seen")"
	[ -z "$misdrawn" ] ||
		die "the directory to install into holds a character a terminal draws as something other than itself ($misdrawn): one that is invisible, is drawn as another character, ends a line or reorders the text around it, so no line about \$PATH can print the name as it reads. Nothing was installed. Set \$OPENREPOSHAPE_BIN_DIR to a directory without one, then run this line again."
	# A WINDOWS SPELLING IS SPELLED THE WAY BASH SPELLS IT, THE COMMAND'S OWN
	# RULE (#667, after #649), before it is named in a line or looked at: a
	# value typed `D:\tools\bin` was echoed as typed, in the `install:`,
	# `preflight:` and `done:` lines, while the command's own lines said
	# `/d/tools/bin`, and where no `cygpath` answers the command refuses it
	# (exit 2), which this file learnt only after the fetch. So the same
	# `cygpath -u` respells it here, and the same refusal comes first, before
	# anything is asked of the network. The `case` is `install_commands`'s in
	# `openRepoShape`, copied: this file arrives alone down a pipe, and
	# `tests/test_install_sh.py` feeds one value through both. The refusal
	# does not echo the value.
	case "$bin_dir" in
	[A-Za-z]:/* | [A-Za-z]:\\*)
		spelled=""
		if command -v cygpath >/dev/null 2>&1; then
			spelled="$(cygpath -u -- "$bin_dir" 2>/dev/null)" || spelled=""
		fi
		case "$spelled" in
		"" | [A-Za-z]:*)
			die "\$OPENREPOSHAPE_BIN_DIR is spelled for Windows, and no cygpath here spells it the way bash does, so the directory could not go on \$PATH: the drive's colon splits it. Nothing was installed. Set \$OPENREPOSHAPE_BIN_DIR to the directory as this shell spells it, then run this line again."
			;;
		esac
		bin_dir="$spelled"
		;;
	esac
	# A `:` SPLITS A `$PATH` WHATEVER THE QUOTING (#760), so no line about
	# `$PATH` can name such a directory; the command refuses it from the
	# release that added the check (#667), and this file learnt of it only
	# after the fetch. Checked after the Windows spelling, as the command
	# checks it: a drive spelling holds a `:` by definition, is respelled
	# without one, and was refused above where it could not be. The
	# control-character arm is above, so the directory is named here, as the
	# command names it, and no value that can forge a line gets this far.
	case "$bin_dir" in
	*:*)
		die "install.sh would place openRepoShape in '$bin_dir', which holds a ':', and a ':' is what splits a \$PATH into its directories, so no line about \$PATH can name it. Nothing was installed. Set \$OPENREPOSHAPE_BIN_DIR to a directory without one, then run this line again."
		;;
	esac

	# A LINK IS NOT A PLACE TO INSTALL TO (#563), and this installer says so
	# itself, before anything is asked of the network. pipx places the
	# openreposhape package's `openRepoShape` as a symbolic link in this same
	# directory, and the command's `--install` copies with `cp`, which writes
	# through a link into the package's own environment. The command refuses
	# such a target too, but only from the release that added the check: the
	# release named here may be older, so its refusal cannot be relied on.
	target="$bin_dir/openRepoShape"
	[[ ! -L "$target" ]] ||
		die "$target is a symbolic link, so nothing was installed: pipx places the openreposhape package's openRepoShape that way, and installing this one through the link would overwrite the package's command. Use one installer or the other:
    keep the package's command, and update it with: pipx upgrade openreposhape
    or remove the link (pipx uninstall openreposhape, or rm $target), then run this line again."

	# 1. THE RELEASE.
	if [ -n "$version" ]; then
		checked_version "$version" "the version"
		say "release: $version, as named"
	else
		asked="https://github.com/$REPO/releases/latest"
		if latest_from_redirect "$asked"; then
			version="$FOUND"
		else
			local redirect_fault="$FAULT"
			latest_from_gh || die "could not find the newest release of $REPO, so nothing was installed. Both ways failed:
    curl -fsSI $asked   ($redirect_fault)
    gh api repos/$REPO/releases/latest   ($FAULT)
    Name a release instead, as bash install.sh v1.0.1 or as:
    curl -fsSL https://github.com/$REPO/releases/latest/download/install.sh | bash -s -- v1.0.1"
			version="$FOUND"
			asked="gh api repos/$REPO/releases/latest"
		fi
		checked_version "$version" "the newest release's tag"
		say "release: $version, the newest release of $REPO ($asked)"
	fi

	# 2. THAT RELEASE'S COMMAND, FETCHED, CHECKED AND INSTALLED BY ITSELF.
	WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/openRepoShape-install.XXXXXXXX")" ||
		die "could not make a temporary directory under ${TMPDIR:-/tmp}. Set \$TMPDIR to a directory you can write to."
	trap 'rm -rf -- "$WORKDIR"' EXIT
	launcher_url="https://raw.githubusercontent.com/$REPO/$version/openRepoShape"
	curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 "$launcher_url" -o "$WORKDIR/openRepoShape" || status=$?
	# WHICH FAILURE IT WAS DECIDES WHAT TO SAY. curl's exit 22 is the server
	# answering with an error, which for a raw URL means no such file at that
	# ref; anything else is curl getting no answer at all (DNS, a proxy, TLS,
	# a timeout), where asking whether the release exists would send the
	# person looking in the wrong place.
	case "$status" in
	0) [ -s "$WORKDIR/openRepoShape" ] ||
		die "fetched $launcher_url, but it was empty, so nothing was installed." ;;
	22) die "could not fetch $launcher_url: the server answered with an error (curl exit 22), so nothing was installed. Is $version a release of $REPO? https://github.com/$REPO/releases" ;;
	*) die "could not fetch $launcher_url: curl got no answer (curl exit $status), so nothing was installed. Check this machine's network, DNS and proxy, then run the line again." ;;
	esac
	looks_like_the_launcher "$WORKDIR/openRepoShape" ||
		die "$launcher_url is not the openRepoShape command (its first line is not #!/usr/bin/env bash, or it has no INSTALLABLES line), so nothing was installed."
	say "fetch: $launcher_url"

	say "install: OPENREPOSHAPE_REF=$version OPENREPOSHAPE_RECORD_REF=1 openRepoShape --install"
	OPENREPOSHAPE_REF="$version" OPENREPOSHAPE_RECORD_REF=1 \
		"${BASH:-bash}" "$WORKDIR/openRepoShape" --install ||
		die "the $version openRepoShape's --install refused (exit $?); its own refusal above says why."

	# THE PIN, CHECKED BY ASKING THE INSTALLED COMMAND, with the variable
	# unset: a release older than v1.0.1 installs without recording a ref and
	# would follow main, which is the drift this installer exists to end.
	shown="$(unset OPENREPOSHAPE_REF; "${BASH:-bash}" "$target" --version 2>/dev/null)" || shown=""
	case "$shown" in
	*"@ $version)") ;;
	*)
		pinned=0
		say "install: $target does not stay on $version: it says '${shown:-nothing}' to --version. A release older than v1.0.1 cannot record the tag it was installed at: install v1.0.1 or newer, or export OPENREPOSHAPE_REF=$version in your shell profile to keep it there."
		;;
	esac
	if [ -n "${OPENREPOSHAPE_REF:-}" ] && [ "$OPENREPOSHAPE_REF" != "$version" ]; then
		say "install: \$OPENREPOSHAPE_REF is set in this shell, by your shell profile or by hand, and while it is, every run uses it instead of $version. Remove it from your shell profile to run $version."
	fi

	# 3. GIT-FILTER-REPO.
	filter_repo_step

	# 4. THE PREFLIGHT, LAST, THROUGH THE INSTALLED COMMAND AND ITS RECORD, so
	# its setup.sh is the release's. Where the command did not record the tag,
	# the tag is handed to this one run instead, so that a command which
	# follows main is still not checked with main's setup.sh.
	say "preflight: $target --preflight"
	status=0
	if [ "$pinned" -eq 1 ]; then
		(
			unset OPENREPOSHAPE_REF
			"${BASH:-bash}" "$target" --preflight
		) || status=$?
	else
		OPENREPOSHAPE_REF="$version" "${BASH:-bash}" "$target" --preflight || status=$?
	fi

	# THE TWO READINESSES, LAST (#595). The preflight checks what scaffolding
	# and the doctor need, and its verdict is the exit status below.
	# git-filter-repo is needed to adopt and for nothing else, so it never
	# changes the exit status: `adoption:` says where it stands, with the
	# command to run next where it is missing, and `done:` says "ready" only
	# when it is there as well.
	say "adoption: $ADOPTION"
	[ "$ADOPTION_READY" -eq 1 ] ||
		machine="this machine is ready to scaffold, not yet to adopt"

	# EXIT 1 IS THE PREFLIGHT'S "not ready", which names what is missing; any
	# other status is a run that did not get that far (setup.sh could not be
	# fetched, or there is no Python to run it), and its REFUSED line says so.
	case "$status" in
	0) ;;
	1)
		say "done: openRepoShape $version is installed at $target, but the preflight did not pass (exit 1); it names what is missing above."
		exit 1
		;;
	*)
		say "done: openRepoShape $version is installed at $target, but the preflight did not run to the end (exit $status); the REFUSED line above says why."
		exit 1
		;;
	esac
	if [ "$pinned" -eq 0 ]; then
		say "done: openRepoShape $version is installed at $target and $machine, but the command does not stay on $version (see above)."
		exit 1
	fi
	say "done: openRepoShape $version is installed at $target, pinned to the release tag, and $machine. Run the same line again to upgrade to the newest release."
	exit 0
}

# `${1+"$@"}`, setup.sh's own spelling: no arguments is the one-line run, and
# that has to survive `set -u` under every bash this has to run on. In
# BRACES, so the call is one compound command that bash reads to its closing
# brace before running any of it: a download cut anywhere inside this line
# is a syntax error, and runs nothing.
{ main ${1+"$@"}; }
