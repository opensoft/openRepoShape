# The five targets a scaffolded project ships. Copied verbatim from
# openRepoShape and digest-pinned in `contracts/shape-pin.yaml`.
#
# `park` and `resume` are THIN, and that is the whole design (#77, RULING
# 2026-09-09 ruling 1): the mechanics — the WIP commit, the push, `git
# worktree add`, the `.specify/feature.json` rewrite, the soft reset — belong
# to the SPECKIT GIT EXTENSION, and there is exactly one implementation of
# them. This file names the two verbs, hands them `ARGS`, and REFUSES BY NAME
# when the overlay is not installed. It reimplements none of it, and a target
# here that started to would be a second implementation nobody tests.
#
# The scripts' own exit codes are 0 ok, 1 usage or environment, 2 a REFUSAL
# before anything was done, 3 PARTIAL — at least one feature refused and the
# rest parked. Nothing here rewrites them, but GNU make reports ANY non-zero
# recipe status as its own exit 2 and prints `Error <code>`: when the code
# itself matters, read it from that line or run the script directly.
PYTHON ?= python3
# The Speckit worktree overlay, installed by `setup-openspeckit`. A project
# that never asked for it does not have this directory, which is why both
# targets test for the script before running it.
SPECKIT_GIT := .specify/extensions/git/scripts/bash
PARK := $(SPECKIT_GIT)/park.sh
RESUME := $(SPECKIT_GIT)/resume.sh
# One message, two targets, so the two refusals cannot drift apart. It names
# the installer: a refusal that says only "not installed" leaves the person
# guessing at what to run, which is the one thing a refusal must not do.
OVERLAY_MISSING = needs the Speckit worktree overlay; install it with: \
                  setup-openspeckit
.DEFAULT_GOAL := help

.PHONY: help bootstrap validate pins park resume

help:
	@echo 'make bootstrap   legs onto tracking branches at their pins, then'
	@echo '                 the validators, then the review-authority readout'
	@echo 'make validate    naming + manifest + lockstep pins (what CI runs)'
	@echo 'make pins        the lockstep pin validator alone'
	@echo 'make park        commit, push and RECORD every open feature, so'
	@echo '                 another workstation can take the work up'
	@echo 'make resume      recreate the parked features here; it REFUSES a'
	@echo '                 feature whose branch moved. ARGS=--dry-run first'

bootstrap:
	$(PYTHON) scripts/bootstrap.py

validate:
	$(PYTHON) scripts/validate-repository-naming.py --project project.yaml
	$(PYTHON) scripts/validate-manifest.py
	$(PYTHON) scripts/validate-pins.py

pins:
	$(PYTHON) scripts/validate-pins.py

park:
	@test -x $(PARK) || { echo 'make park $(OVERLAY_MISSING)' >&2; exit 2; }
	@exec $(PARK) $(ARGS)

resume:
	@test -x $(RESUME) || { echo 'make resume $(OVERLAY_MISSING)' >&2; exit 2; }
	@exec $(RESUME) $(ARGS)
