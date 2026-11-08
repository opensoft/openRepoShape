# SPDX-License-Identifier: Apache-2.0
"""A command scope a parameter hands a test is built at the test (#835, #818's
second review).

`appended_to_command_scope(os.environ, ...)` appends to the entries the
environment holds WHEN IT IS CALLED. A `pytest.param(command_scope(...))` is
called at collection, before the session fixture (`no_auto_maintenance`) has
put its `gc.auto=0` and `maintenance.auto=false` in the environment. Laid over
the environment at the test, that count drops the two: on a Linux run git read
only `user.name=Ada Lovelace`, or only `attr.tree=...`. The session's global
file still kept maintenance off, so no test failed.

Two parameters were built so (`test_adopt_reencoded_files.py`'s `attr.tree`
and `test_family_init_asks_every_value.py`'s `user.name`). Each is a `lambda`
now, called by its test, as `test_adopt_nested_attributes.py` already did. The
parameters are read off the tests' own marks and asked of git, which reads
the command scope and writes none.
"""

from __future__ import annotations

import pytest

from conftest import NO_AUTO_MAINTENANCE, command_scope_at
import test_adopt_reencoded_files as reencoded
import test_family_init_asks_every_value as family_init
from test_adopt_nested_attributes import EMPTY_TREE

#: The parametrized tests that hand a test a command scope: the module, the
#: test, its parameter, and the entry each param that names one holds.
SITES = {
    "attr-tree": (reencoded,
                  "test_a_tree_this_machine_names_steers_the_question_as_it_"
                  "steers_the_split",
                  "steer",
                  {"attr-tree-in-the-command-scope":
                   f"attr.tree={EMPTY_TREE}"}),
    "user-name": (family_init,
                  "test_each_exit_of_the_variables_remedy_goes_on_to_a_holder",
                  "env", {"unset-it": "user.name=Ada Lovelace"}),
}


def params_of(module, name: str, argument: str) -> list:
    """The `pytest.param`s a test's `parametrize` of `argument` holds."""
    marks = [mark for mark in getattr(module, name).pytestmark
             if mark.name == "parametrize" and mark.args[0] == argument]
    assert len(marks) == 1, marks
    return marks[0].args[1]


@pytest.mark.parametrize("site", SITES)
def test_each_param_is_built_at_the_test_beside_the_sessions_settings(
        site, tmp_path):
    module, name, argument, entries = SITES[site]
    seen = {}
    for param in params_of(module, name, argument):
        value = param.values[0]
        seen[param.id] = command_scope_at(
            value() if callable(value) else value, tmp_path)
    assert set(entries) <= set(seen), sorted(seen)
    for param_id, read in seen.items():
        for key, value in NO_AUTO_MAINTENANCE:
            assert f"{key}={value}" in read, (param_id, read)
    for param_id, entry in entries.items():
        assert entry in seen[param_id], (param_id, seen[param_id])
