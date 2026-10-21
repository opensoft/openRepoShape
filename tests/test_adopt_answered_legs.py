# SPDX-License-Identifier: Apache-2.0
"""`_answered_legs` looks up each path's own names (#914's L1-85).

It held every plan entry against every path through `_covering`, which was
6.90 s for 120,000 files and 300 entries in lane 1's measurement, and 3.65 s
on this branch's host. Each path now looks up the names `_covering_names`
lists, which costs its depth (0.26 s there), and the answer is the one the
old loop gave: these tests hold it to that loop, spelled here, over the
cases where the two could part -- an entry spelled twice, a directory entry
and a file entry over one path, a path that ends in `/`, a null path or
leg -- and over a seeded fuzz.
"""

from __future__ import annotations

import importlib.util
import random

import pytest

from conftest import ADOPT


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` as a module."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_answered_legs", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def held_against_every_entry(adopter, entries: list, paths: list) -> dict:
    """The answer as main's loop gave it: every entry held against every
    path by `_covering`."""
    entry_paths = [str(entry.get("path")) for entry in entries]
    legs = {str(entry.get("path")): str(entry.get("leg"))
            for entry in entries}
    out = {}
    for path in paths:
        covering = adopter._covering(entry_paths, path)
        if len(covering) == 1 and legs[covering[0]] in adopter.LEG_VALUES:
            out[path] = (legs[covering[0]], covering[0])
    return out


#: `(entries as `(path, leg)`, paths, what is answered)`.
CASES = [
    pytest.param([("src/", "code")], ["src/a.py", "src/b/c.py", "docs/x"],
                 {"src/a.py": ("code", "src/"),
                  "src/b/c.py": ("code", "src/")}, id="a-directory"),
    pytest.param([("src/", "code"), ("src/", "spec")], ["src/a.py"], {},
                 id="one-entry-spelled-twice"),
    pytest.param([("src/", "code"), ("src/a.py", "spec")],
                 ["src/a.py", "src/b.py"], {"src/b.py": ("code", "src/")},
                 id="a-directory-and-a-file-over-one-path"),
    pytest.param([("a/", "code")], ["a/"], {"a/": ("code", "a/")},
                 id="a-path-that-ends-in-a-slash"),
    pytest.param([("x", None), ("y", "elsewhere"), ("z", "drop")],
                 ["x", "y", "z"], {"z": ("drop", "z")},
                 id="an-unanswered-leg-and-an-odd-one"),
    pytest.param([(None, "code")], ["None", "x"], {"None": ("code", "None")},
                 id="a-null-path"),
    pytest.param([("a//", "spec")], ["a//b", "a/b"],
                 {"a//b": ("spec", "a//")}, id="a-doubled-slash"),
]


@pytest.mark.parametrize("entries, paths, answered", CASES)
def test_each_path_is_answered_as_the_old_loop_answered_it(
        adopter, entries, paths, answered):
    """The cases where a lookup by name could part from the old loop."""
    plan = [{"path": path, "leg": leg} for path, leg in entries]
    got = adopter._answered_legs(plan, paths)
    assert got == answered
    assert got == held_against_every_entry(adopter, plan, paths)


def test_a_seeded_fuzz_answers_as_the_old_loop(adopter):
    """Small trees, entries drawn from their own paths and prefixes and from
    noise, some spelled twice: every answer, in its order, the old loop's."""
    rng = random.Random(914)
    alphabet = ["a", "b", "a/", "b/", "/", "", "a/b", "x.py"]
    legs = ["spec", "code", "root", "drop", None, "elsewhere"]
    for _ in range(3000):
        paths = ["".join(rng.choice(alphabet)
                         for _ in range(rng.randint(1, 4)))
                 for _ in range(rng.randint(0, 6))]
        plan = []
        for _ in range(rng.randint(0, 6)):
            if paths and rng.random() < 0.7:
                base = rng.choice(paths)
                cuts = [index + 1 for index, char in enumerate(base)
                        if char == "/"]
                path = (base[:rng.choice(cuts)]
                        if cuts and rng.random() < 0.5 else base)
            else:
                path = "".join(rng.choice(alphabet)
                               for _ in range(rng.randint(0, 3)))
            plan.append({"path": path, "leg": rng.choice(legs)})
        if plan and rng.random() < 0.2:
            plan.append(dict(rng.choice(plan)))
        got = adopter._answered_legs(plan, paths)
        expected = held_against_every_entry(adopter, plan, paths)
        assert list(got.items()) == list(expected.items()), (plan, paths)


def test_no_entry_is_held_against_every_path(adopter, monkeypatch):
    """The lookup is by name: `_covering`, which holds every entry against
    one path, is not asked at all, so a path costs its depth and not the
    plan's length."""
    def refused(*_):
        raise AssertionError("_answered_legs held every entry against a path")

    monkeypatch.setattr(adopter, "_covering", refused)
    plan = [{"path": f"pkg{index}/", "leg": "code"} for index in range(300)]
    files = [f"pkg{index}/sub/file{leaf}.py" for index in range(300)
             for leaf in range(10)]
    answered = adopter._answered_legs(plan, files)
    assert len(answered) == len(files)
    assert answered["pkg7/sub/file3.py"] == ("code", "pkg7/")
