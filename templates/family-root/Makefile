# The six targets a family holder ships. Copied verbatim from
# openRepoShape and digest-pinned in `contracts/shape-pin.yaml`.
#
# `siblings` is the WORKSTATION half and the only target that writes outside
# this repository: it clones each member BESIDE the holder, in the family
# folder, and it never touches a clone that is already there beyond a fetch.
#
# `bootstrap` and the member half of `validate` are done by
# `scripts/bootstrap.py` rather than by a shell loop here: it must resolve a
# credential for PRIVATE members before `git submodule update --init
# --recursive`, and it must report a member that is not initialised instead
# of failing the loop. A Makefile cannot do either honestly.
#
# `park` and `resume` are the ESTATE half of the same story (#77, RULING
# 2026-09-09 ruling 5), and they go through `siblings.py --make` because they
# must run in the members' WORKING CLONES BESIDE THIS HOLDER — not in
# `members/<Project>`, which is pinned, DETACHED, and where nobody's
# in-flight work is. A holder that parked the pinned copies would report
# "nothing to park" for every member while the person's features sat
# untouched next door. Each member's own `make park` is the one
# implementation of the verb, and the mechanics under it are the Speckit git
# extension's, not this repository's. A member with no working clone is
# reported and SKIPPED (`make siblings` is what places one); one whose verb
# refuses is reported too; either way the holder carries on to the next
# member and exits non-zero at the end. A skip is not a pass, and a refusal
# is never hidden. The dispatch clones nothing and fetches nothing.
PYTHON ?= python3
.DEFAULT_GOAL := help

.PHONY: help bootstrap siblings validate pins park resume

help:
	@echo 'make bootstrap   fetch every member and its legs, then run each'
	@echo '                 member'\''s own make bootstrap'
	@echo 'make siblings    clone every member BESIDE the holder, on its'
	@echo '                 tracking branch; fetch the ones already there'
	@echo 'make validate    the family validator, then each member'\''s make validate'
	@echo 'make pins        the family lockstep check alone (gitlink == pin)'
	@echo 'make park        each WORKING CLONE beside the holder runs its'
	@echo '                 own make park; no clone, no fetch, one report'
	@echo 'make resume      the same, with make resume. A member with no'
	@echo '                 clone is SKIPPED (make siblings places one),'
	@echo '                 and ARGS reaches every member that does run'

bootstrap:
	$(PYTHON) scripts/bootstrap.py

siblings:
	$(PYTHON) scripts/siblings.py

validate:
	$(PYTHON) scripts/validate-family.py
	$(PYTHON) scripts/bootstrap.py --no-fetch --members-make validate

pins:
	$(PYTHON) scripts/validate-family.py --pins

park:
	$(PYTHON) scripts/siblings.py --make park --make-arg 'ARGS=$(ARGS)'

resume:
	$(PYTHON) scripts/siblings.py --make resume --make-arg 'ARGS=$(ARGS)'
