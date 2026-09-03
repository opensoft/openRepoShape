#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classify the paths of an existing repository against a path policy.

The classifier behind `adopt-project.py plan`. It reads
`contracts/path-classification.yaml` — ordered glob rules, an extension
majority for what no rule names, and a default — and answers, for one path,
which leg it belongs in and WHY.

THREE PROPERTIES, EACH LOAD-BEARING.

FIRST MATCH WINS, so the order in the data file is semantic and a reader can
resolve an overlap by reading downwards. `docs/api/**` above `docs/**` is how
"except generated API documentation" becomes a thing that runs.

A DIRECTORY IS ONE ENTRY UNTIL ITS CHILDREN DISAGREE. Emitting 167 rows for
167 files would bury the four decisions a human actually has to make. So a
directory whose files all land in one leg is reported as ONE path, and only a
directory whose children split — `.github/`, with workflows in the code leg
and CODEOWNERS in the root — is descended into.

AMBIGUOUS IS AN ANSWER. `leg: null` plus the question to ask is what the tool
owes a reader when the honest state is that it does not know; a guess dressed
as a classification is worse, because nobody reviews a confident answer.

STANDARD LIBRARY ONLY, like everything else here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import Refusal, load_yaml  # noqa: E402

LEGS = ("spec", "code", "root", "ambiguous")
DEFAULT_MAJORITY = 0.75


class Verdict:
    """One path's answer, carrying the rule and the sentence behind it.

    `leg` is `None` for `ambiguous`, because that is what the plan writes and
    a single spelling of "unknown" is one fewer thing to get wrong.
    """

    __slots__ = ("leg", "rule", "reason", "confidence", "question")

    def __init__(self, leg: str | None, rule: str, reason: str,
                 confidence: str, question: str | None = None):
        self.leg = None if leg in (None, "ambiguous") else leg
        self.rule = rule
        self.reason = " ".join(str(reason).split())
        # An ambiguous path has no confidence to report: the rule that matched
        # may be a certain one, and what it says with certainty is that this
        # needs a human. Recording `high` beside `leg: null` would have read
        # as a confident answer to a question nobody has answered.
        self.confidence = "review" if self.leg is None else confidence
        self.question = " ".join(str(question).split()) if question else None

    @property
    def review_required(self) -> bool:
        return self.leg is None

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Verdict({self.leg!r}, {self.rule!r}, {self.confidence!r})"


def glob_to_regex(pattern: str) -> re.Pattern:
    """The small glob dialect this policy is written in.

    `**` crosses directory separators, `*` does not, `?` is one non-separator
    character. Deliberately smaller than `fnmatch`, whose `*` crosses `/` and
    would make `*.yaml` match `tests/fixtures/x.yaml` — which is the opposite
    of what "a TOP-LEVEL yaml file" means in the policy above it.
    """
    out = ["^"]
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    out.append("$")
    return re.compile("".join(out))


class PathPolicy:
    """The ordered rules, the extension classes and the default, as loaded."""

    def __init__(self, data: dict):
        self.data = data
        rules = data.get("rules") or []
        if not rules:
            raise Refusal("path-policy-empty",
                          "the path classification policy declares no rules")
        self.rules = []
        for rule in rules:
            if not isinstance(rule, dict) or not rule.get("id"):
                raise Refusal("path-policy-rule",
                              f"a rule is not a mapping with an id: {rule!r}")
            leg = rule.get("leg")
            if leg not in LEGS:
                raise Refusal(
                    "path-policy-leg",
                    f"rule {rule['id']!r} declares leg {leg!r}; the classes "
                    f"are {list(LEGS)}")
            compiled = [(p, glob_to_regex(str(p)))
                        for p in (rule.get("paths") or [])]
            if not compiled:
                raise Refusal("path-policy-rule",
                              f"rule {rule['id']!r} matches no paths")
            self.rules.append((rule, compiled))
        self.extension_classes: dict[str, str] = {}
        for leg, extensions in (data.get("extension_classes") or {}).items():
            for extension in extensions or []:
                self.extension_classes[str(extension).lower()] = leg
        self.majority = float(data.get("extension_majority") or DEFAULT_MAJORITY)
        self.default = data.get("default") or {}

    @classmethod
    def load(cls, path: Path) -> "PathPolicy":
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("path-policy-unreadable", f"{path}: not a mapping")
        if data.get("kind") != "path-classification-policy":
            raise Refusal(
                "path-policy-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'path-classification-policy'")
        return cls(data)

    # -- one path -----------------------------------------------------------

    def rule_for(self, path: str) -> dict | None:
        """The FIRST rule whose globs match, or None.

        A rule written as `foo/**` also matches the bare directory `foo`,
        because a policy that classified every file under a directory but not
        the directory itself would descend into it for no reason.
        """
        for rule, compiled in self.rules:
            for pattern, regex in compiled:
                if regex.match(path):
                    return rule
                if pattern.endswith("/**") and path == pattern[:-3]:
                    return rule
        return None

    def classify_file(self, path: str) -> Verdict:
        rule = self.rule_for(path)
        if rule is not None:
            return Verdict(rule["leg"], str(rule["id"]), rule.get("reason", ""),
                           "high", rule.get("question"))
        suffix = ("." + path.rsplit(".", 1)[1].lower()) if "." in \
            Path(path).name.lstrip(".") else ""
        leg = self.extension_classes.get(suffix)
        if leg is not None and leg != "ambiguous":
            return Verdict(
                leg, "extension-majority",
                f"no rule names this path; the `{suffix}` extension is "
                f"classified as {leg} by the policy's extension table",
                "medium")
        return Verdict(None, "default", self.default.get("reason", ""), "low",
                       self.default.get("question"))

    # -- a directory --------------------------------------------------------

    def fold(self, verdicts: list[Verdict], files: list[str]) -> Verdict | None:
        """One verdict for a whole directory, or None — meaning DESCEND.

        Three ways a directory answers as one path, in order:
          1. every file agrees on the leg AND on the rule that said so;
          2. every file agrees on the leg by DIFFERENT rules (recorded as
             `consensus`, at medium confidence, because agreement reached by
             several routes is weaker evidence than one rule covering the lot);
          3. no file matched an explicit rule at all and the extension
             majority clears the policy's threshold — which is how an
             unrecognised source package answers `code` without this policy
             having to know the project's own nouns.
        Anything else descends, because a directory that is half specification
        and half implementation has no single honest answer.
        """
        if not verdicts:
            return None
        legs = {v.leg for v in verdicts}
        if len(legs) == 1:
            leg = verdicts[0].leg
            rules = {v.rule for v in verdicts}
            if len(rules) == 1:
                return Verdict(leg, verdicts[0].rule, verdicts[0].reason,
                               verdicts[0].confidence, verdicts[0].question)
            return Verdict(
                leg, "consensus",
                "every file under this path classifies as "
                f"{leg or 'ambiguous'}, by {len(rules)} different rules: "
                + ", ".join(sorted(rules)),
                "medium",
                next((v.question for v in verdicts if v.question), None))
        if any(v.rule not in ("extension-majority", "default") for v in verdicts):
            return None
        counts: dict[str | None, int] = {}
        for verdict in verdicts:
            counts[verdict.leg] = counts.get(verdict.leg, 0) + 1
        leg, count = max(counts.items(), key=lambda kv: kv[1])
        share = count / len(verdicts)
        if leg is not None and share >= self.majority:
            return Verdict(
                leg, "extension-majority",
                f"{count} of {len(verdicts)} files under this path "
                f"({share:.0%}) carry extensions the policy classifies as "
                f"{leg}, which clears the {self.majority:.0%} majority",
                "medium")
        return None
