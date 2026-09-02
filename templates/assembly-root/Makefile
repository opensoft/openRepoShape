# The three targets a scaffolded project ships. Copied verbatim from
# openRepoShape and digest-pinned in `contracts/shape-pin.yaml`.
PYTHON ?= python3
.DEFAULT_GOAL := help

.PHONY: help bootstrap validate pins

help:
	@echo 'make bootstrap   legs onto tracking branches at their pins, then'
	@echo '                 the validators, then the review-authority readout'
	@echo 'make validate    naming + manifest + lockstep pins (what CI runs)'
	@echo 'make pins        the lockstep pin validator alone'

bootstrap:
	$(PYTHON) scripts/bootstrap.py

validate:
	$(PYTHON) scripts/validate-repository-naming.py --project project.yaml
	$(PYTHON) scripts/validate-manifest.py
	$(PYTHON) scripts/validate-pins.py

pins:
	$(PYTHON) scripts/validate-pins.py
