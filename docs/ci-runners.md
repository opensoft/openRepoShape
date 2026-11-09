# CI runners

The project and family validation templates accept the repository or organization
variable `CI_LINUX_RUNNER` as their Linux runner selector. With no value, they
retain `ubuntu-latest`. Set it only to a compatible Linux runner label that the
repository is allowed to use. This changes compute placement, not validation.

The upstream repository uses `eagle-linux-ubuntu24`, a disposable Ubuntu 24.04
x64 worker. Its Python 3.9 floor checks keep that Ubuntu version. Native Windows
and macOS test and release rows retain their original selectors and commands.

Existing copied templates must be updated through `update-shape.py check` and
its reviewed apply operation. Do not hand-edit copied workflows or their digests.
