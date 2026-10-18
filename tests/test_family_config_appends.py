# SPDX-License-Identifier: Apache-2.0
"""The family tests' three helpers that add one `GIT_CONFIG_*` entry to git's
command scope build it with `appended_to_command_scope` (#835).

`on_disk` (`test_family_head_lost_gitmodules.py`), `with_config`
(`test_family_bootstrap_gate_order.py`) and `typed_with_local_remotes`
(`test_family_add_spellings_remedies.py`) each worked their count out by hand
from the environment's own, and were right for a count the Windows job sets.
`test_no_auto_maintenance.py`'s scan refuses that sum in a test file now, so
none of them repeats it, and these tests hold what each returns:

- under the two entries the Windows job sets (`GIT_CONFIG_COUNT=2`), `git
  config --show-origin --list` lists both, in order, and then the new one;
- under an EMPTY `GIT_CONFIG_COUNT`, which git reads as no entries and
  `appended_to_command_scope` counts as none, the new entry is the first:
  the sum written out by hand died on `int("")`.
"""

from __future__ import annotations

import os

import pytest

from conftest import JOB_ENTRIES, appended_to_command_scope, command_scope_at
import test_family_add_spellings_remedies as spellings
from test_family_bootstrap_gate_order import with_config
from test_family_head_lost_gitmodules import on_disk

#: The two entries a job holds (`JOB_ENTRIES`), and an empty count. Each is
#: built on purpose, to see that the helper keeps what it is given
#: (`OWN_COUNTS` allows this file the two).
HELD = appended_to_command_scope({}, JOB_ENTRIES)
EMPTY = {"GIT_CONFIG_COUNT": ""}

#: The helpers that take an environment and return it with one more entry:
#: each as a call of `env`, and the `key=value` it adds. `on_disk` is given
#: both values the disks of the family tests (`DISKS`) give it.
ADDERS = {
    "on_disk": (lambda env: on_disk(env, "true"), "core.ignorecase=true"),
    "on_disk-false": (lambda env: on_disk(env, "false"),
                      "core.ignorecase=false"),
    "with_config": (lambda env: with_config(env, "test.added", "yes"),
                    "test.added=yes"),
}

#: What `typed_with_local_remotes` adds.
FILE_ALLOWED = "protocol.file.allow=always"


@pytest.mark.parametrize("helper", ADDERS)
def test_a_helper_adds_one_entry_after_the_two_a_job_holds(helper, tmp_path):
    adder, added = ADDERS[helper]
    assert HELD["GIT_CONFIG_COUNT"] == "2", HELD
    env = adder(HELD)
    assert env["GIT_CONFIG_COUNT"] == "3", env
    assert command_scope_at(env, tmp_path) == [
        "test.heldone=one", "test.heldtwo=two", added]


@pytest.mark.parametrize("helper", ADDERS)
def test_a_helper_counts_an_empty_count_as_none(helper):
    adder, added = ADDERS[helper]
    env = adder(EMPTY)
    key, value = added.split("=")
    assert (env["GIT_CONFIG_COUNT"], env["GIT_CONFIG_KEY_0"],
            env["GIT_CONFIG_VALUE_0"]) == ("1", key, value), env


@pytest.mark.parametrize("held", ["two", "empty"])
def test_the_typing_helper_adds_one_entry_for_the_typing_alone(
        held, monkeypatch, tmp_path):
    """`typed_with_local_remotes` sets each entry for the typing and puts
    the environment back: what git reads while `typed_as_printed` runs is
    asked from inside it."""
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    for name, value in (HELD if held == "two" else EMPTY).items():
        monkeypatch.setenv(name, value)
    before = dict(os.environ)
    seen = {}

    def typing(root, said):
        seen.update(os.environ)
        return ["typed"]

    monkeypatch.setattr(spellings, "typed_as_printed", typing)
    assert spellings.typed_with_local_remotes(
        monkeypatch, tmp_path, "said") == ["typed"]
    assert command_scope_at(seen, tmp_path) == (
        ["test.heldone=one", "test.heldtwo=two", FILE_ALLOWED]
        if held == "two" else [FILE_ALLOWED])
    assert dict(os.environ) == before
