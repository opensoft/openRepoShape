# SPDX-License-Identifier: Apache-2.0
"""The release this package was built from: its STAMP (#563).

A release build GENERATES this file from the tag it builds, and nothing else
in the wheel differs from the tag's own tree. The four values are the
version (`v1.1.0` gives `1.1.0`), the tag, the tag's 40-hex commit, and the
`sorted-ls-tree-r-v1` digest of that commit's tree, the digest every pin this
standard writes carries (`scripts/repo_shape.py`, `tree_digest`).

THE COMMITTED FILE IS UNSTAMPED: version 0.0.0 and no tag, commit or digest.
That is a build from a checkout rather than a release. It follows main, says
so in `openRepoShape --version`, and the release workflow refuses to publish
it.

`pyproject.toml` reads VERSION from here (`dynamic = ["version"]`), so the
version is written down once.
"""

VERSION = "0.0.0"
TAG = ""
COMMIT = ""
DIGEST = ""
