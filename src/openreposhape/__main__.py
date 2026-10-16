# SPDX-License-Identifier: Apache-2.0
"""`python -m openreposhape` is `openRepoShape` (#563): the same command,
for an interpreter whose scripts directory is not on PATH."""

import sys

from .cli import openreposhape

sys.exit(openreposhape())
