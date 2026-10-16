# SPDX-License-Identifier: Apache-2.0
"""openreposhape: openRepoShape's commands, installed with pipx (#563).

A SECOND WAY IN, NEVER A REQUIREMENT. Cloning this repository and running its
tools with `python3` and `git` keeps working exactly as it does without this
package, and every tool stays standard-library only. The package adds five
commands, `openRepoShape`, `scaffold-project`, `adopt-project`,
`update-shape` and `shape-doctor`, and one dependency, `git-filter-repo`,
which only `adopt-project.py` needs.

IT IS THIN. It carries no tool, template or contract: `cli` runs them from a
full clone of this repository at the commit the package was built from
(`standard`), and `_release` is the stamp that names that commit. The one
file of the standard it does carry is `setup-project.py`, byte for byte, so
that `openRepoShape --preflight` runs on a machine with no git yet.
"""
