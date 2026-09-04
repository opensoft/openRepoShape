# The three targets a family holder ships. Copied verbatim from
# openRepoShape and digest-pinned in `contracts/shape-pin.yaml`.
#
# `bootstrap` and the member half of `validate` are done by
# `scripts/bootstrap.py` rather than by a shell loop here: it must resolve a
# credential for PRIVATE members before `git submodule update --init
# --recursive`, and it must report a member that is not initialised instead
# of failing the loop. A Makefile cannot do either honestly.
PYTHON ?= python3
.DEFAULT_GOAL := help

.PHONY: help bootstrap validate pins

help:
	@echo 'make bootstrap   fetch every member and its legs, then run each'
	@echo '                 member'\''s own make bootstrap'
	@echo 'make validate    the family validator, then each member'\''s make validate'
	@echo 'make pins        the family lockstep check alone (gitlink == pin)'

bootstrap:
	$(PYTHON) scripts/bootstrap.py

validate:
	$(PYTHON) scripts/validate-family.py
	$(PYTHON) scripts/bootstrap.py --no-fetch --members-make validate

pins:
	$(PYTHON) scripts/validate-family.py --pins
