#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classify repository names against `contracts/repository-naming.yaml`.

USAGE
    validate-repository-naming.py NAME [NAME ...]
    validate-repository-naming.py --project project.yaml
    printf '%s\\n' openChart MedxChart | validate-repository-naming.py
    validate-repository-naming.py --explain openxFactory
    validate-repository-naming.py --explain --role assembly MedxScribe
    validate-repository-naming.py --pins openChart --explain MedxChart
    validate-repository-naming.py --pins openXdox \\
        --referent-chain openXdox,openDox --explain codexDox

A NAME may be given bare (`openChart`) or fully qualified (`opensoft/openChart`);
only the part after the last `/` is classified, because the organisation login
is not part of any family.

WHAT `--role` AND `--pins` ARE FOR. A name in `<Domainx><Product>` form is a
CLAIM of descent, and since the 2026-09-02 ruling a claim needs a REFERENT: it
classifies as a domain descendant only when the project declares a pin on the
matching `open<Product>`. `--pins` supplies those declarations for a one-off
check and `--role` supplies the role the project would declare, so a name can
be classified here on exactly the facts `project.yaml` would carry. With
`--project` both are READ from the manifest instead — the legs' roles, and
`neutral_product_pins:` — which is what the scaffolded project's own gate runs.

`--role` IS ALSO WHAT ASKS WHETHER AN ELECTED FORM CARRIES ITS ROLE. Since
2026-09-05 a neutral product may ELECT the shape and be its own assembly root,
so `--explain --role assembly openDox` answers `neutral-product / assembly`
and names the admission, while `--explain openDox` — nothing declared — answers
`neutral-product` as it always did. The form is never overridden by the
declaration; the role is ADDED to it, and the leg form it also satisfies stays
in `also_matches`.

ONLY A FORM THAT NEEDS A DECLARATION IS A `--role` VALUE. `family` is one,
because the holder form is declared-only and the characters cannot tell you.
`workspace` is not, for the same reason `install` and `neutral-product` are
not: `<user>-wip` is unambiguous by construction, so there is nothing to
declare and `--role workspace` is refused as the unknown choice it is. A role
that IS a choice, declared over such a name, is ignored rather than carried —
`--role assembly brett-wip` answers `workspace`, exactly as it does for
`<X>-Install`.

WHAT `--referent-chain` AND `--link-source` ARE FOR. Since 2026-09-05 the
referent may be reached through a CHAIN of neutral-product pins: `codexDox`
pins `openXdox`, and `openXdox` pins `openDox`. The chain is RECORDED, in the
descendant's own manifest under `naming.referent_chain:` (which `--project`
reads); `--referent-chain openXdox,openDox` supplies the same record for a
one-off check. Every link beyond the first is a declaration in ANOTHER tree,
and `--link-source [PRODUCT=]PATH` — like `SHAPE_PIN_SOURCE_<PRODUCT>` and a
checkout sitting beside the project — says where that tree is. A link no
source answers for is reported as `declared-unverified` and the name STILL
classifies as a descendant: the check is offline, and a recorded declaration
is the fact it reads.

A BARE PATH IS THE FIRST LINK'S TREE AND NO OTHER'S (#441). A `--link-source`
with no `PRODUCT=` is read for the chain's first link, the pin the project
holds, when nothing more specific answers for it, and never for a later link:
one tree cannot be two links' declarations, and reading `openXdox`'s
`project.yaml` again as `openYdox`'s called a chain that holds broken. A later
link needs its own `PRODUCT=PATH`, its variable or a checkout beside the
project. While the chains read in one run begin at more than one link, a bare
PATH is read for none of them. A value that names no path — `PRODUCT=`, or an
empty one — is refused (#442): an empty path is the current directory, and
`.` is how to mean that.

A CALLER THAT PASSES A SOURCE FOR SOMEONE ELSE SAYS IT IN ITS OWN WORDS
(#661). `--link-source-label=FLAG` is the flag the person typed for the bare
PATH (setup's step (4) passes `--pin-source`): the `link-source-unreadable`
WARNING and the "not used" NOTE name that value by FLAG, and neither says a
value holding `=` was read as a PATH. The `link-source-no-path` REFUSED
line, and the NOTE's advice to name the link (`--link-source <link>=PATH`)
where the chains begin at more than one link, keep this script's own flag.
`--link-remedy LINK=TEXT` is what would let LINK's tree be read in that
caller's sources, offered in place of this script's own for a link that is
declared-unverified. A project's own runs pass neither. Every `--link-source`
value and path this prints, and the path of a `SHAPE_PIN_SOURCE_<PRODUCT>`
or of a checkout beside the project it names, is named as it is, or as
Python's `repr` spells it where a character in it is not printable
(`_shown`). A caller's FLAG and the words it offers for a link, a chain
link's name, and the `--project` and `--policy` paths are printed as given.

EXIT CODES, the same three in every validator this standard ships:
    0  every name classified (and, with `--project`, every declared role and
       the topic agreed with the classification)
    1  a FINDING: at least one name matches no family, or a leg's declared role
       disagrees with the form of its name, or (#443) `neutral_product_pins:`
       or a leg's `naming.referent_chain:` is not a list
    2  a REFUSAL: the question could not be asked at all — the policy file is
       missing, unparsable, or not a naming policy, or a `--link-source`
       names no path

A chain link whose tree could not be read prints a WARNING and changes no exit
code, deliberately: see `--link-source` below. A SOURCE that could not answer
is a WARNING too, with the system's reason (#338): a `--link-source` given
here, a `SHAPE_PIN_SOURCE_<PRODUCT>`, or a checkout beside the project that is
there and still cannot answer. An explicit source stays a warning here, where
`validate-pins.py` makes its `--pin-source` a finding (#295): the variable
answers that validator's digest question too, from a checkout that need not
carry a manifest, and a source that cannot answer is passed over for the next
one in the order, which may. A `--link-source` no link used is a NOTE saying
why.

The 1/2 split is deliberate. "This name is wrong" and "I could not read the
policy" are different facts and a gate that renders them identically invites a
workflow that treats the second as the first.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    CHAIN_RECORD_FIELD, LINK_SOURCE_ABSENT, LINK_SOURCE_NO_MANIFEST,
    UNAMBIGUOUS_FORMS, Classification, NamingPolicy, Refusal,
    link_pins_from_trees, load_yaml, pin_product_key, repo_basename,
)

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "contracts" / "repository-naming.yaml"


def _shown(path) -> str:
    """A path as a line about it names it: as it is, unless a character in
    it is not printable (`str.isprintable`), and then as Python's `repr`
    spells it (#610). It is `repo_shape.shown_path`, which spells the
    manifest in a `link-source-unreadable` reason, so one line holds one
    spelling. Written here rather than imported: this file is copied into
    every project and may meet a `scripts/repo_shape.py` older than itself,
    which has no such name, and the gate would end in an `ImportError` before
    it classified a name."""
    text = str(path)
    return text if text.isprintable() else repr(text)


def _library_takes_remedies() -> bool:
    """Does this root's `scripts/repo_shape.py` take `remedies=`? The
    skew rule `validate-manifest.py` states (#661): an older library has
    none, and passing it would end the gate in a `TypeError`."""
    try:
        return "remedies" in inspect.signature(
            link_pins_from_trees).parameters
    except (TypeError, ValueError):
        return False


def _link_remedy(value: str) -> tuple[str, str]:
    """One `--link-remedy LINK=TEXT`: the link, by `repo_basename`, and
    the words. The text before the first `=` is the link; a value with no
    `=`, no link or no words is refused, exit 2."""
    link, sep, text = value.partition("=")
    link = repo_basename(link.strip())
    if not (sep and link and text.strip()):
        raise argparse.ArgumentTypeError(
            f"{_shown(value)} is not LINK=TEXT: name a chain link, then `=`, "
            "then the words for what would let its tree be read")
    return link, text


class Target:
    """One name to classify, with everything DECLARED about it.

    `chain` is the recorded `naming.referent_chain:` and `root` is the tree the
    chain's links are looked for beside, which is why a target is a small
    object rather than the tuple it used to be: a link is read from another
    repository's manifest, so the question "where am I standing?" is now part
    of the question being asked.
    """

    def __init__(self, name: str, role: str | None, pins: set[str],
                 chain=(), root: Path | None = None):
        self.name = name
        self.role = role
        self.pins = pins
        self.chain = tuple(chain)
        self.root = root


class LinkSources:
    """Every `--link-source` value AS TYPED, read against the chain links this
    run names, and what each lookup made of it (#338).

    THE READING. `PRODUCT=PATH` and a bare `PATH` are told apart by an `=`,
    and a path may hold one: a link tree cloned under `a=b/` is
    `--link-source a=b/openXdox`. Splitting every value at its first `=` made
    that a source keyed to a link `a` that no chain names, which no lookup
    ever asked for — the link stayed declared-unverified, exit 0, under a
    WARNING suggesting the very `--link-source` the person had passed. So the
    text before the first `=` is a LINK only when it names a link of a
    referent chain this run reads (`--referent-chain`'s, or a leg's
    `naming.referent_chain:` under `--project`) by `pin_product_key`, the key
    the lookup uses, and any other value is a bare PATH, whole. A link's name
    wins even where a directory is spelled like the whole value: the reading
    is decided by the chains and never by the disk, and `./` asks for the
    directory.
    That is `validate-pins.py`'s reading of `--pin-source` (#295), with a
    chain link where that file has a declared pin, so the two copied tools
    read `[PRODUCT=]PATH` one way OVER ASCII ONLY (#444). Outside it they part
    company: `templates/assembly-root/scripts/validate-pins.py` still keys
    `--pin-source PRODUCT=` by `casefold()`, in `PinSources.__init__`, which
    builds the table, and in `resolve_neutral_pin_source`, which looks a pin
    up in it, so `--pin-source openss=` answers for a declared `openß`
    where `--link-source openss=` no longer answers for the link `openß`. It
    is left, and the issue leaves it as its own change, because a pin's digest
    stops a wrong source from passing: `validate-pins.py` checks it, a wrong
    source cannot match it, and so that reading can turn a wrong source into
    a finding and never into a pass. The follow-up is on #459's checklist
    (the shipped validators and the helpers they share).

    WHAT EACH VALUE CAME TO. Every lookup records what it asked
    (`link_pins_from_trees(..., tried=)`), so once every name is classified a
    value is USED (a link that holds a pin read it), UNREAD (asked for one,
    and it could not answer: a WARNING with the system's reason) or NOT USED
    (never asked for one: a NOTE saying why). A `SHAPE_PIN_SOURCE_<PRODUCT>`,
    or a checkout beside the project that is there and cannot answer, is
    named the same way when such a link needed it. None of these is a
    finding, and none ends the run: a link whose tree could not be read is a
    warning in this validator, deliberately, and an explicit source is no
    exception — the module docstring says why.

    ONE VALUE, ONE LINK (#441). A keyed value is asked for its own link
    alone. The bare PATH is asked for the FIRST link of a chain a name here
    reads (`link_pins_from_trees` offers it to no later link), and only
    while every such chain begins at that one link, so it is never counted
    as the answer for two. `firsts` are those first links, found before any
    chain is read (`_first_links_read`). A chain of one link has no holder,
    reads no declaration, and so adds none.

    A VALUE THAT NAMES NO PATH IS REFUSED (#442). `openXdox=` is
    `Path("")`, which is `.`: run from a project root it read the project's
    own manifest as openXdox's, and a chain that holds was broken. That and
    an empty bare value are in `no_path`, and `no_path_refusal` says so.

    EVERY LINK IS KEYED BY `pin_product_key` (#444), the pin file's own fold,
    as `repo_shape.py`'s chain readers key it. With `casefold()` here,
    `openß` and `openss` were one link: `--link-source openss=` answered for
    `openß`, two values for the pair replaced each other, and two chains
    beginning at them counted one first link, so a bare PATH was read as both
    products' trees.
    """

    def __init__(self, values: list[str], links, firsts=(),
                 label: str | None = None, remedies=()) -> None:
        #: The caller's own name for the bare PATH it passes, or None
        #: (`--link-source-label`, #661).
        self.label = label
        #: `{pin_product_key(link): the caller's words}` from
        #: `--link-remedy`, the last value given for a link wins (#661).
        self.remedies: dict[str, str] = {
            pin_product_key(link): text for link, text in remedies}
        #: Every link of every chain this run reads, in its first spelling.
        self.links: list[str] = []
        names: dict[str, str] = {}
        for link in links:
            name = repo_basename(str(link))
            if name and pin_product_key(name) not in names:
                names[pin_product_key(name)] = name
                self.links.append(name)
        #: `{pin_product_key: first spelling}` of the first link of every
        #: chain a name here reads (#441). `link_pins` adds a chain's first
        #: link as it reads it, which matters only for names read from stdin:
        #: they come when no other name does, all with `--referent-chain`.
        self.firsts: dict[str, str] = {}
        for link in firsts:
            name = repo_basename(str(link))
            self.firsts.setdefault(pin_product_key(name), name)
        #: `{pin_product_key(link): (typed, path)}`, the last value given
        #: wins.
        self.keyed: dict[str, tuple[str, Path]] = {}
        #: `(typed, path)` of the last bare value, if any.
        self.bare: tuple[str, Path] | None = None
        #: Every distinct value in the order given, and the link it was read
        #: as keyed to, or None for a bare PATH.
        self.reading: dict[str, str | None] = {}
        #: `{typed: the later value that took its place}`.
        self.replaced: dict[str, str] = {}
        for typed in values:
            key, sep, path = typed.partition("=")
            link = names.get(pin_product_key(key)) if sep else None
            self.reading[typed] = link
            if link is not None:
                earlier = self.keyed.get(pin_product_key(link))
                self.keyed[pin_product_key(link)] = (typed, Path(path))
            else:
                earlier = self.bare
                self.bare = (typed, Path(typed))
            self.replaced.pop(typed, None)
            if earlier is not None and earlier[0] != typed:
                self.replaced[earlier[0]] = typed
        #: The values that name no path (#442), in the order given: a keyed
        #: value with nothing after its `=`, and an empty bare one.
        self.no_path: list[str] = [
            typed for typed, link in self.reading.items()
            if not (typed.partition("=")[2] if link is not None else typed)]
        #: The links some name's lookup asked about, by `pin_product_key`.
        self.asked: set[str] = set()
        #: The values a link read: each the answer for one link (#441).
        self.used: set[str] = set()
        #: `{typed: (path, how, why, [links])}` for a value asked and never
        #: answering.
        self.unread: dict[str, tuple] = {}
        #: `{(path, how, why): [links]}` for a `SHAPE_PIN_SOURCE_<PRODUCT>`
        #: or a checkout beside the project that could not answer.
        self.unanswered: dict[tuple, list[str]] = {}

    def link_pins(self, policy: NamingPolicy, target: Target) -> dict:
        """What the chain's links declare, for the links whose trees answer,
        with what each lookup asked recorded against the values given.

        A chain no classification reads asks nothing and says nothing:
        `policy.classify` consults a link's declaration only for a name that
        claims a referent, with a chain whose shape holds. A source asked for
        any other chain (a spec leg's record, a name with no `open<Product>`
        to reach, a chain that does not begin at a held pin) was reported
        unreadable, or counted as used, for a question nobody asked."""
        if not policy.reads_link_declarations(target.name, target.pins,
                                              target.chain):
            return {}
        if len(target.chain) > 1:
            first = repo_basename(str(target.chain[0]))
            self.firsts.setdefault(pin_product_key(first), first)
        tried: dict = {}
        offered = ({"remedies": self.remedies}
                   if self.remedies and _library_takes_remedies() else {})
        found = link_pins_from_trees(
            target.chain, target.root,
            {key: path for key, (_typed, path) in self.keyed.items()},
            self._bare_path(), tried=tried, **offered)
        # ONLY A LINK THAT HOLDS A PIN COUNTS. The lookup asks for every link,
        # the last one too, but only a holder's own declaration is ever read
        # (`_chain_link_findings`): a source asked only for the chain's end
        # decided nothing, and saying it answered, or failed to, would be a
        # report about a question nobody asked.
        holders = {pin_product_key(repo_basename(str(link)))
                   for link in target.chain[:-1]}
        for link, asked in tried.items():
            if pin_product_key(link) not in holders:
                continue
            self.asked.add(pin_product_key(link))
            for rule, how, path, why in asked:
                self._record(link, rule, how, path, why)
        return found

    def _bare_path(self) -> Path | None:
        """The bare PATH for `link_pins_from_trees`, which asks it for a
        chain's first link alone (#441), or None: none was given, or the
        chains read here begin at more than one link, and one tree read as
        two first links' would be the defect over again."""
        if self.bare is None or len(self.firsts) > 1:
            return None
        return self.bare[1]

    def _record(self, link: str, rule: str, how: str, path: Path,
                why: str | None) -> None:
        """One source a holder's lookup asked. A value typed here is
        accounted for whatever the answer; a variable whenever it could not
        answer; a checkout beside the project only where it is there and
        still could not answer, since one that is absent, or holds no
        manifest, is the ordinary case."""
        if rule in ("keyed", "bare"):
            typed = (self.keyed[pin_product_key(link)] if rule == "keyed"
                     else self.bare)[0]
            if why is None:
                self.used.add(typed)
                return
            if rule == "bare" and self.label:
                how = self.label
            links = self.unread.setdefault(typed, (path, how, why, []))[3]
        elif why is None or (rule == "sibling" and why in (
                LINK_SOURCE_ABSENT, LINK_SOURCE_NO_MANIFEST)):
            return
        else:
            # A checkout beside the project is named in `how` too (#661).
            how = how.replace(str(path), _shown(path))
            links = self.unanswered.setdefault((path, how, why), [])
        if link not in links:
            links.append(link)

    def read_as_path(self, typed: str) -> str:
        """The sentence saying a value holding `=` was read as a bare PATH,
        or `""` — the only trace in the run of a mistyped link name. Nothing
        when no chain names a link: the note has already said so."""
        if self.reading.get(typed) is not None or "=" not in typed \
                or not self.links or self.label:
            return ""
        key = typed.partition("=")[0]
        what = f"`{_shown(key)}` is not" if key else "nothing before its `=` is"
        return (f"It was read as a PATH: {what} a link of a referent chain "
                f"here (links: {', '.join(self.links)}).")

    def _also_a_directory(self, typed: str) -> str:
        """The line for a value read as `LINK=PATH` that ALSO names an
        existing directory whole: the keyed reading won, and this is how to
        ask for the other one. `os.path.isdir`, which is False for every
        `OSError` on every Python."""
        if self.reading.get(typed) is None or not os.path.isdir(typed):
            return ""
        named = _shown(typed)
        return (f"`{named}` is also a directory; `--link-source ./{named}` "
                "reads it as one.")

    def unread_lines(self) -> list[str]:
        """One `link-source-unreadable` WARNING per source that was asked and
        could not answer, with the system's reason, in the order given."""
        lines = []
        for typed in self.reading:
            # A value is read as ONE link's keyed source, or is the one bare
            # PATH, so every lookup that asked it asked the same path and got
            # the same answer: it is `used` or `unread`, never both.
            if typed not in self.unread:
                continue
            path, how, why, links = self.unread[typed]
            lines.append(
                f"link-source-unreadable: {_shown(path)} ({how}) could not "
                f"answer for {', '.join(links)}: {why}"
                + "".join(f"\n  {line}" for line in (
                    self.read_as_path(typed), self._also_a_directory(typed))
                    if line))
        for (path, how, why), links in self.unanswered.items():
            lines.append(f"link-source-unreadable: {_shown(path)} ({how}) "
                         f"could not answer for {', '.join(links)}: {why}")
        return lines

    def no_path_refusal(self) -> str:
        """The `REFUSED` line naming every value that names no path (#442),
        each by the link it is keyed to, or `""` when there is none."""
        if not self.no_path:
            return ""
        said = [f"`--link-source {_shown(typed)}` names no path for "
                f"{self.reading[typed]}" if typed
                else "`--link-source ''` names no path"
                for typed in self.no_path]
        return ("REFUSED link-source-no-path: " + "; ".join(said)
                + ". An empty path would be read as the directory this runs "
                "in. Give the tree's path (`--link-source <link>=<path>`), "
                "or `.` to mean this directory.")

    def _not_asked_why(self) -> str:
        """Why the bare PATH was never asked, where a chain link's own
        declaration was read: it is a chain's first link's tree alone
        (#441), and that link had a more specific source, or the chains read
        here begin at more than one link. Where only first links are read,
        the sentence is the one it always was."""
        if len(self.firsts) > 1:
            return ("a bare PATH is one first link's tree, and the chains "
                    "read here begin at " + ", ".join(self.firsts.values())
                    + ": name the link it is, as --link-source <link>=PATH")
        keyed = "" if self.label else "a keyed --link-source, "
        sources = (f"a more specific source ({keyed}"
                   "SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout beside the "
                   "project)")
        if self.asked <= set(self.firsts):
            return f"each link whose own declaration is read had {sources}"
        return ("a bare PATH is the tree of a chain's first link alone, "
                f"{', '.join(self.firsts.values())}, which had {sources}")

    def unused_lines(self) -> list[str]:
        """A NOTE for each value no lookup asked, named as typed, with why:
        a later value replaced it, no name reads its link's declaration, no
        name records a chain, none reads a link's declaration, or the one
        link a bare PATH answers for had a more specific source
        (`_not_asked_why`). A value holding `=` that was read as a PATH says
        so too."""
        lines = []
        for typed, link in self.reading.items():
            if typed in self.used or typed in self.unread:
                continue
            flag = self._flag(link)
            later = self.replaced.get(typed)
            if later is not None:
                why = f"the later `{flag} {_shown(later)}` replaced it"
            elif link is not None:
                why = f"no name classified here reads {link}'s own declaration"
            elif not self.links:
                why = "no name classified here records a referent chain"
            elif not self.asked:
                why = ("no name classified here reads a chain link's own "
                       "declaration")
            else:
                why = self._not_asked_why()
            lines.append(" ".join(filter(None, (
                f"{flag} {_shown(typed)}: not used — {why}.",
                self.read_as_path(typed)))))
        return lines

    def _flag(self, link: str | None) -> str:
        """The flag a value is named by: `--link-source`, or for a bare
        PATH the caller's label where it gave one (#661)."""
        return self.label if link is None and self.label else "--link-source"


def _no_family_lines(policy: NamingPolicy, name: str) -> list[str]:
    """The `--explain` lines for a name that matches no family at all.

    Split from `_describe` for #136: what to print when nothing classifies is
    one question, answered once, so the per-family row below never has to
    guard against a `found` that does not exist.
    """
    lines = [f"  {name}: NO FAMILY"]
    lines.append(f"    the {len(policy.families)} families are: " + ", ".join(
        f["id"] for f in policy.families))
    for family in policy.families:
        lines.append(f"    {family['id']:<18} {family['pattern']}")
    return lines


def _admission_note(family: dict, role: str | None, carried: str | None) -> str:
    """The `[ADMITS ...]` note for a family whose data admits a declared role.

    Split from `_describe` for #136: THREE ANSWERS, not two — nothing
    declared, a role declared and ADMITTED, or a role declared and REFUSED
    (`--role spec openDox` declares a role this family does not admit).
    Collapsing the last two into "none is declared here" told the reader a
    declaration was absent when it was in fact refused (2026-09-05); giving
    the three answers their own function is what keeps them three.
    """
    admits = ", ".join(str(r) for r in family["admits_declared_role"])
    if role is None:
        admission = "; none is declared here"
    elif carried:
        admission = f" — this name carries {carried}"
    else:
        admission = f"; {role} is declared here and is not admitted"
    return (f" [ADMITS a declared role of {admits}: the form still "
            "wins and carries the role the project declares, where "
            "the name also satisfies that leg form"
            + admission
            + "]")


def _referent_claim_note(policy: NamingPolicy, family: dict, name: str) -> str:
    """The `[a CLAIM: ...]` note for a family that `requires_referent`.

    Split from `_family_claim_and_role_note` for #136: WHAT WOULD BE
    ACCEPTED, both halves of it. Naming only the direct pin is what sent
    `codexDox` looking for an `openDox` pin its family does not hold
    (2026-09-05).
    """
    return (" [a CLAIM: needs a declared pin on " + " or ".join(
        policy.descendant_referents(name))
        + ", or a declared chain (`"
        + str(policy.chain_rule().get("record_field")
              or CHAIN_RECORD_FIELD)
        + "`) of pins ending in one of them]")


def _declared_only_note(family: dict) -> str:
    """The `[DECLARED-ONLY: ...]` note for a family only reported by name.

    Split from `_family_claim_and_role_note` for #136.
    """
    return (" [DECLARED-ONLY: reported only with --role "
             + family["id"] + "; " + str(family.get("declared_by") or
                                         "a declaration").strip() + "]")


def _unambiguous_note() -> str:
    """The `[UNAMBIGUOUS BY CONSTRUCTION: ...]` note.

    Split from `_family_claim_and_role_note` for #136: WHY THIS ROW NEEDED
    NOTHING. The other three notes are each a reason a reader might have to
    declare something; this is the answer for `<X>-Install` and
    `<user>-wip` — nothing to declare, and admitted into no role either.
    `neutral-product` is unambiguous too and answered by `_admission_note`
    instead, because it has the further thing to say about the role it
    admits.
    """
    return (" [UNAMBIGUOUS BY CONSTRUCTION: nothing else spells this "
             "form, so it needs nothing declared — no --role and no "
             "pin — and it is admitted into no role either]")


def _admission_row(role_note: str, family: dict, role: str | None,
                   found: Classification) -> tuple[str, str]:
    """`(role_note, claim)` for a family whose data admits a declared role.

    Split from `_family_claim_and_role_note` for #136: NAME THE ADMISSION,
    not just its effect — a reader who sees `openDox: neutral-product /
    assembly` and no explanation has to go and read the classifier to learn
    that the form still won and the role was ADDED to it (2026-09-05).
    `role_note` is the plain note the caller already computed, kept
    as-is unless this name CARRIES the admitted role.
    """
    carried = (found.role if found.family == family["id"]
               and found.role else None)
    claim = _admission_note(family, role, carried)
    if carried:
        role_note = f" (role {carried}, ADMITTED)"
    return role_note, claim


def _family_claim_and_role_note(policy: NamingPolicy, family: dict, hits: list,
                                role: str | None, name: str,
                                found: Classification) -> tuple[str, str]:
    """The `(role_note, claim)` suffixes for one family's `--explain` row.

    Split from `_describe` for #136: what a family's row says about what
    claiming it would need is one question with four mutually exclusive
    answers, each now its own named note, asked once per family instead of
    inline in the row loop.
    """
    role_note = f" (role {hits[0][1]})" if hits and hits[0][1] else ""
    claim = ""
    if hits and policy.requires_referent(family["id"]):
        claim = _referent_claim_note(policy, family, name)
    elif policy.declared_only(family["id"]):
        claim = _declared_only_note(family)
    elif hits and family.get("admits_declared_role"):
        role_note, claim = _admission_row(role_note, family, role, found)
    elif hits and family["id"] in UNAMBIGUOUS_FORMS:
        claim = _unambiguous_note()
    return role_note, claim


def _family_row(policy: NamingPolicy, family: dict, matches: list,
                role: str | None, name: str, found: Classification) -> str:
    """The one `--explain` line for a single family, MATCH or not.

    Split from `_describe` for #136: composing one family's row — whether it
    matched, and what it would need declared — is one question, asked once
    per family instead of inline in the name's own loop.
    """
    hits = [m for m in matches if m[0] == family["id"]]
    mark = "MATCH " if hits else "      "
    role_note, claim = _family_claim_and_role_note(
        policy, family, hits, role, name, found)
    return f"    {mark}{family['id']:<18} {family['pattern']}{role_note}{claim}"


def _referent_lines(target: Target, matches: list,
                    found: Classification) -> list[str]:
    """The CHAIN / WARNING / OVERLAP lines after a name's family rows.

    Split from `_describe` for #136: what to say about the referent, and
    about an overlap, are two more questions asked once per name after every
    row has already been printed, not per family.
    """
    lines: list[str] = []
    if target.chain:
        lines.append("    CHAIN " + " → ".join(target.chain)
                     + f"   [{found.referent.status}]")
    for warning in found.referent.warnings:
        lines.append("    WARNING " + warning)
    if len(matches) > 1:
        lines.append("    OVERLAP " + found.reason)
        lines.append("    also_matches: " + ", ".join(found.also_matches))
    return lines


def _describe(policy: NamingPolicy, target: Target, link_pins: dict) -> list[str]:
    """Every family `target.name` satisfies, why one of them won, and what
    the others are recorded as — the full `--explain` report for one name.

    Split into `_family_row` (one family's line) and `_referent_lines` (the
    CHAIN/WARNING/OVERLAP trailer) for #136: this function now only decides
    WHICH lines to assemble, not how each one reads.
    """
    name, role, pins = target.name, target.role, target.pins
    matches = policy.matches(name, role)
    if not matches:
        return _no_family_lines(policy, name)
    found = policy.classify(name, role, pins, target.chain, link_pins)
    lines = [f"  {name}: {found[0]}" + (f" / {found[1]}" if found[1] else "")]
    for family in policy.families:
        lines.append(_family_row(policy, family, matches, role, name, found))
    lines.extend(_referent_lines(target, matches, found))
    return lines


def _pins_from_project(data: dict) -> set[str]:
    """The neutral products the manifest DECLARES a pin on.

    `neutral_product_pins:` and nothing else. A leg's
    `naming.referent_declared:` is a RECORD of a declaration, checked by
    `validate-manifest.py` against this list; reading it as a declaration here
    would let a claim vouch for itself.

    A VALUE THAT IS NOT A LIST DECLARES NOTHING (#443), and
    `_pins_field_findings` says so. Iterated as it stood, `5`, `true` or `1.5`
    ended this gate, the first command of `make validate`, in a `TypeError`;
    a scalar `openXdox` was read as the pins `X`, `d`, `e`, `n`, `o`, `p`,
    `x`, and a mapping as its keys, and the names classified, exit 0.
    """
    declared = data.get("neutral_product_pins")
    if not isinstance(declared, list):
        return set()
    return {str(pin) for pin in declared if pin}


def _pins_field_findings(data: dict) -> list[str]:
    """`validate-manifest.py`'s finding for a `neutral_product_pins:` that is
    not a list, in its words (#443), so the first command of `make validate`
    names the field where it used to end in a traceback, and every validator
    that reads the field says the same sentence. Absent or null declares no
    pin and is no finding; anything else that is not a list is one, `0`,
    `false` and `''` included, as that validator says."""
    declared = data.get("neutral_product_pins")
    if declared is None or isinstance(declared, list):
        return []
    return [f"manifest-neutral-product-pins: neutral_product_pins is "
            f"{declared!r}, expected a list of neutral product names"]


def _chain_from_leg(leg: dict) -> tuple:
    """The pin chain a leg's `naming:` block RECORDS, if it records one.

    Read from the manifest and nowhere else: the chain is a declaration, and
    inferring one from the pins would be the classifier writing the record it
    then checks.

    `validate-manifest.py`'s `_recorded_chain`, rule for rule (#443): a
    string is a one-link chain, and anything else that is not a list records
    no chain, which `_chain_field_findings` reports. This copy had the string
    rule and not the list rule, so `5`, `true` or `1.5` ended the gate in a
    `TypeError` and a mapping was read as a chain of its keys.
    """
    naming = leg.get("naming")
    if not isinstance(naming, dict):
        return ()
    recorded = naming.get(CHAIN_RECORD_FIELD)
    if isinstance(recorded, str):
        recorded = [recorded]
    if not isinstance(recorded, list):
        return ()
    return tuple(str(link) for link in recorded if str(link).strip())


def _chain_field_findings(leg: dict) -> list[str]:
    """`validate-manifest.py`'s finding for a leg's `naming.referent_chain:`
    that is neither a string nor a list, in its words (#443): the leg named
    by its declared `role:`, as that validator names it. Absent or null
    records no chain, and a string is one link, so neither is a finding."""
    naming = leg.get("naming")
    if not isinstance(naming, dict):
        return []
    recorded = naming.get(CHAIN_RECORD_FIELD)
    if recorded is None or isinstance(recorded, (str, list)):
        return []
    return [f"naming-referent-chain: leg {leg.get('role')!r}: "
            f"{CHAIN_RECORD_FIELD} is {recorded!r}, expected a list of "
            "neutral-product names"]


def _leg_target(policy: NamingPolicy, path: Path, leg, root: Path,
                pins: set, sources: LinkSources
                ) -> tuple[Target | None, list[str]]:
    """One leg's `Target` and what is wrong with it, from its manifest entry.

    Split from `_targets_from_project` for #136: what one leg's own entry
    says is a question asked once per leg, not folded into the loop that
    walks every leg in the manifest. `(None, [finding])` is a leg with no
    `repository:` to classify at all — the same case the loop's own `finding`
    list has always carried, now returned instead of appended in place.
    """
    if not isinstance(leg, dict) or "repository" not in leg:
        return None, [f"{path}: a leg has no `repository:`"]
    name = repo_basename(str(leg["repository"]))
    declared = leg.get("role")
    declared = str(declared) if declared else None
    target = Target(name, declared, pins, _chain_from_leg(leg), root)
    found = policy.classify(name, declared, pins, target.chain,
                            sources.link_pins(policy, target))
    # A chain record that is not a list is said FIRST, where
    # `validate-manifest.py` says it first, and the leg is classified as one
    # that records no chain (#443).
    findings: list[str] = _chain_field_findings(leg)
    # `declared_role` only wins where the NAME satisfies it, so a role that
    # disagrees with its own name still lands here rather than being made
    # true by declaring it.
    if found and found[0] == "project-leg" and declared and found[1] != declared:
        findings.append(
            f"{name}: declared role {declared!r} but the name is the "
            f"{found[1]!r} form of the project-leg family"
        )
    # A RECORDED chain that does not hold is drift in the record, and the
    # finding names the link. Unverified is not this: it is a warning,
    # printed by the caller, and never an exit code.
    if found and found.referent.status == "broken":
        findings.append(f"{name}: {found.referent.reason}")
    return target, findings


def _topic_finding(policy: NamingPolicy, project_id, topic) -> str | None:
    """The one finding a manifest's `topic:` disagreeing with its `id:` needs.

    Split from `_targets_from_project` for #136.
    """
    if project_id is None:
        return None
    expected = policy.topic_for(str(project_id))
    if topic is not None and topic != expected:
        return f"topic {topic!r} != {expected!r} derived from id {project_id!r}"
    return None


def _project_manifest(path: Path) -> dict:
    """The `project.yaml` mapping `--project` names, or a `Refusal`."""
    data = load_yaml(path)
    if not isinstance(data, dict):
        raise Refusal("manifest-unreadable", f"{path}: not a mapping")
    return data


def _project_leg_chains(data: dict) -> list[tuple[str, tuple]]:
    """`(name, the chain it records)` for each leg `_leg_target` makes a
    target of, and no other."""
    return [(repo_basename(str(leg["repository"])), _chain_from_leg(leg))
            for leg in data.get("legs") or []
            if isinstance(leg, dict) and "repository" in leg]


def _project_chain_links(data: dict) -> list[str]:
    """Every link every leg's `naming.referent_chain:` records.

    Read BEFORE any leg is classified, because whether `openXdox=../x` is a
    source keyed to a link or a bare path depends on the links the chains
    name (#338), and the first leg is classified with the sources already
    read. The same legs `_leg_target` makes targets of, and no others.
    """
    return [link for _name, chain in _project_leg_chains(data)
            for link in chain]


def _first_links_read(policy: NamingPolicy, targets: list,
                      data: dict | None) -> list[str]:
    """The first link of every chain a name here READS, found before any is
    read (#441): a bare `--link-source` is that link's tree, and only while
    the chains begin at one link. A chain of one link has no holder, reads
    no declaration, and so has no first link to count. The names on the
    command line and the legs `_leg_target` makes targets of; names on stdin
    come only when there are neither, all with `--referent-chain`, so they
    cannot add a second."""
    readers = [(target.name, target.pins, target.chain) for target in targets]
    if data is not None:
        pins = _pins_from_project(data)
        readers.extend((name, pins, chain)
                       for name, chain in _project_leg_chains(data))
    return [chain[0] for name, pins, chain in readers
            if len(chain) > 1
            and policy.reads_link_declarations(name, pins, chain)]


def _targets_from_project(policy: NamingPolicy, path: Path, data: dict,
                          sources: LinkSources) -> tuple[list, list[str]]:
    """Return ([Target], findings) for a `project.yaml` manifest."""
    pins = _pins_from_project(data)
    root = path.resolve().parent
    targets: list[Target] = []
    # Pins that are not a list are said before any leg's finding, and every
    # leg is classified as declaring none (#443).
    findings: list[str] = _pins_field_findings(data)
    for leg in data.get("legs") or []:
        target, leg_findings = _leg_target(policy, path, leg, root, pins,
                                           sources)
        if target is not None:
            targets.append(target)
        findings.extend(leg_findings)
    topic_finding = _topic_finding(policy, data.get("id"), data.get("topic"))
    if topic_finding is not None:
        findings.append(topic_finding)
    return targets, findings


def _targets_from_stdin(role: str | None, pins: set, chain: tuple,
                        here: Path) -> list[Target]:
    """The targets read from stdin, one per non-blank line.

    Split from `main` for #136: reading the stdin fallback is its own
    question, asked only once `main` has decided no other source answered.
    """
    return [Target(repo_basename(line.strip()), role, pins, chain, here)
            for line in sys.stdin if line.strip()]


def _print_classification(name: str, found: Classification | None) -> None:
    """The one plain-listing line `main` prints for a name, un-`--explain`d.

    Split from `main` for #136: composing this line is a single question —
    what to call the name, and what else it also matched — asked once per
    name instead of inline in the classify loop.
    """
    # An independent statement rather than a ternary nested inside a
    # ternary (python:S3358): the family/role suffix is decided on
    # its own before it is appended to the label.
    if not found:
        label = "NO FAMILY"
    else:
        role_suffix = f"/{found[1]}" if found[1] else ""
        label = found[0] + role_suffix
    also = f"   also_matches {','.join(found.also_matches)}" \
        if found and found.also_matches else ""
    print(f"  {name:<32} {label}{also}")


def _classify_targets(policy: NamingPolicy, targets: list, args,
                      sources: LinkSources) -> tuple[list[str], list[str]]:
    """Classify every target, printing as `args` asks; return `(unclassified
    names, warnings)`.

    Split from `main` for #136: walking every target and deciding what to
    print for EACH is one question; what to do with the totals afterwards
    (the exit code, the FINDING/WARNING lines) stays `main`'s, unchanged.
    """
    unclassified: list[str] = []
    warnings: list[str] = []
    for target in targets:
        name = target.name
        link_pins = sources.link_pins(policy, target)
        found = policy.classify(name, target.role, target.pins, target.chain,
                                link_pins)
        if args.explain:
            print("\n".join(_describe(policy, target, link_pins)))
        elif not args.quiet:
            _print_classification(name, found)
        if found:
            warnings.extend(f"{name}: {text}"
                            for text in found.referent.warnings)
        else:
            unclassified.append(name)
    return unclassified, warnings


def _emit_reports(args, unclassified: list[str], warnings: list[str],
                  findings: list[str], sources: LinkSources) -> int:
    """Print the WARNING/NOTE/FINDING lines owed once, and return the exit
    code.

    Split from `main` for #136: what to print once classification is
    finished, and what code to exit with, is one question asked once at the
    end, not interleaved with the loop that classifies.

    What became of each `--link-source` (#338) is said here too, after every
    name's own WARNINGs and before the FINDINGs, under `--explain` as well:
    it is about the run's sources, not one name's, so no name's `--explain`
    block carries it. `--quiet` drops it with the WARNINGs.
    """
    # A WARNING IS NOT A FINDING. An unread link tree is the ordinary case in
    # a fork-and-run checkout, and an exit code that punished it would make the
    # answer depend on which repositories happen to be on the disk.
    for warning in warnings:
        if not args.quiet and not args.explain:
            print(f"WARNING {warning}", file=sys.stderr)
    if not args.quiet:
        for line in sources.unread_lines():
            print(f"WARNING {line}", file=sys.stderr)
        for line in sources.unused_lines():
            print(f"NOTE {line}", file=sys.stderr)
    for finding in findings:
        print(f"FINDING {finding}", file=sys.stderr)
    if unclassified:
        print(
            "FINDING naming-unclassified: "
            + ", ".join(unclassified)
            + "\n  These names match none of the families in "
            + str(args.policy)
            + ".\n  A project's three repositories are `<Project>`, "
            "`<Project>-spec` and `<Project>-code`; `<Project>` is one "
            "CamelCase token with no hyphen, underscore, dot or space.",
            file=sys.stderr,
        )
    return 1 if (unclassified or findings) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="repository names to classify")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--project", type=Path, default=None,
                        help="read the leg names, their roles and the declared "
                             "neutral-product pins from a project.yaml manifest")
    parser.add_argument("--role", default=None,
                        choices=("assembly", "spec", "code", "family"),
                        help="the role the NAMES on the command line are "
                             "offered as; a descendant-form name with no "
                             "referent pin is classified by this, and "
                             "`family` is what asks whether a name is a valid "
                             "HOLDER — a form spelled exactly like an assembly "
                             "root, so it is reported only when declared")
    parser.add_argument("--pins", default="",
                        help="comma-separated neutral products the project "
                             "declares a pin on, e.g. --pins openChart. A "
                             "`<Domainx><Product>` name is a domain descendant "
                             "only when its `open<Product>` is in this list.")
    parser.add_argument("--referent-chain", default="",
                        help="the pin chain the project RECORDS as reaching "
                             "its referent, e.g. --referent-chain "
                             "openXdox,openDox. The first entry must be in "
                             "--pins and the last must be the name's "
                             "`open<Product>`; with --project it is read from "
                             "each leg's `naming.referent_chain:` instead.")
    parser.add_argument("--link-source", action="append", default=[],
                        metavar="[PRODUCT=]PATH",
                        help="where a chain LINK's own tree is, so its "
                             "`neutral_product_pins:` can be read and the "
                             "link VERIFIED — e.g. --link-source "
                             "openXdox=../openXdox. The text before the "
                             "first `=` is a PRODUCT only when it names a "
                             "chain link (an entry of --referent-chain, or "
                             "of a leg's naming.referent_chain: under "
                             "--project), and then that reading wins even "
                             "over a directory spelled like the whole value "
                             "(./PATH reads that directory); any other value "
                             "is a bare PATH: the tree of the chain's FIRST "
                             "link (the pin the project holds), read when "
                             "that link has no more specific answer, and "
                             "never a later link's, which needs its own "
                             "PRODUCT=PATH, its SHAPE_PIN_SOURCE_<PRODUCT> "
                             "or a checkout beside the project. When the "
                             "chains read here begin at two different "
                             "links, a bare PATH is read for neither. A "
                             "value that names no path (PRODUCT=, or "
                             "empty) is refused. Repeatable; a value no "
                             "link used is noted. Every link is tried "
                             "against PRODUCT=PATH, SHAPE_PIN_SOURCE_"
                             "<PRODUCT> and a checkout beside the project, "
                             "in that order, and a bare PATH last, for the "
                             "first link alone. A link no "
                             "source answers for is declared-unverified, and "
                             "a source that cannot be read is named with the "
                             "system's reason: both are warnings and not "
                             "findings, an explicit source included.")
    parser.add_argument("--link-source-label", default=None,
                        metavar="FLAG",
                        help="the caller's own name for the bare "
                             "--link-source it passes, such as --pin-source "
                             "(a FLAG that starts with - is given after an "
                             "=): the link-source-unreadable WARNING and the "
                             "not-used NOTE name that value by FLAG, and "
                             "neither says a value holding = was read as a "
                             "PATH")
    parser.add_argument("--link-remedy", action="append", default=[],
                        type=_link_remedy, metavar="LINK=TEXT",
                        help="the caller's words for what would let LINK's "
                             "tree be read, offered in place of this "
                             "script's own where that link is "
                             "declared-unverified. Repeatable; the last "
                             "value for a link wins.")
    parser.add_argument("--explain", action="store_true",
                        help="print every family each name satisfies, why one "
                             "of them won, and what the others are recorded as")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        policy = NamingPolicy.load(args.policy)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    cli_pins = {p.strip() for p in args.pins.split(",") if p.strip()}
    cli_chain = tuple(c.strip() for c in args.referent_chain.split(",")
                      if c.strip())
    here = Path.cwd()
    targets: list[Target] = [
        Target(repo_basename(n), args.role, cli_pins, cli_chain, here)
        for n in args.names]
    findings: list[str] = []
    data = None
    if args.project is not None:
        try:
            data = _project_manifest(args.project)
        except Refusal as exc:
            print(str(exc), file=sys.stderr)
            return 2
    # The `--link-source` values are READ here, once every chain this run
    # reads is known and before any name is classified (#338, #441).
    sources = LinkSources(args.link_source, [
        *cli_chain, *(_project_chain_links(data) if data is not None
                      else ())], _first_links_read(policy, targets, data),
        args.link_source_label, args.link_remedy)
    if sources.no_path:
        print(sources.no_path_refusal(), file=sys.stderr)
        return 2
    if data is not None:
        extra, findings = _targets_from_project(policy, args.project, data,
                                                sources)
        targets.extend(extra)
    if not targets and not sys.stdin.isatty():
        targets = _targets_from_stdin(args.role, cli_pins, cli_chain, here)
    if not targets:
        print("REFUSED naming-no-target: no names given. Pass names, "
              "`--project project.yaml`, or names on stdin.", file=sys.stderr)
        return 2

    unclassified, warnings = _classify_targets(policy, targets, args, sources)
    return _emit_reports(args, unclassified, warnings, findings, sources)


if __name__ == "__main__":
    sys.exit(main())
