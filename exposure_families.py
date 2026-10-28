"""The families of this repository's exposures, and what each one holds.

mcp-hub groups its exposures by where a call goes. The family of a document
is the first directory of its path in the repository:

- `robot/`: the robot itself, its moves, limbs, cameras and brain;
- `simulation/`: the simulated world, its scene, objects, light and clock;
- `framework/`: the peppy framework, the stack of nodes that runs the robots.

A target names exactly one source. `contract` names a contract of the
contracts hub, which a node implements. `daemon` names an interface that is
compiled into peppy, which the peppy daemon serves and no node implements. A
`framework/` document names daemon interfaces only, and only a `framework/`
document names one. So a call to the framework never reaches the endpoint of
the robots or of the simulated world, and a call to a node never reaches the
endpoint of the framework. `target_kind_violations` checks this rule.

An exposure selects three members of the daemon interface `robot_leases`: the
fleet listing, the halt of the stack and its clearance. The other members, the
contract documents, the leases, the move check and the changes of the fleet,
are for programs. `robot_leases_member_violations` checks this rule.

The documents of `simulation/` and of `framework/` say what they are, so a
model can always tell where a call goes. A `Family` holds the wording of one
of them: the suffix of the server title, the sentence that opens the
instructions, and the words of which every description holds one. `SIMULATION`
and `FRAMEWORK` are the two families. `test_no_simulation_ground_truth.py`
applies the wording of `SIMULATION`, and `test_exposure_families.py` applies
the wording of `FRAMEWORK`, the rule of the target kinds and the rule of the
members of `robot_leases`.

`texts` gives each text of a document that a model reads, and `tool_names`
the name of each tool of a document, for the rules on what a text names.

Each function reads the structure of a document with `exposure_json5`, so a
rule reads the same document whatever json5 form a key or a string takes.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from exposure_json5 import exposure_documents, read_json5


class TargetKind(Enum):
    """The key with which a target names its source."""

    CONTRACT = "contract"
    DAEMON = "daemon"

    @property
    def noun(self) -> str:
        """How a message names a source of this kind."""
        return "the contract" if self is TargetKind.CONTRACT else "the daemon interface"


class TargetError(ValueError):
    """A target that names neither a contract nor a daemon interface, or
    both. peppy refuses such a target too."""


@dataclass(frozen=True)
class TargetSource:
    """What a target names: the kind of its source, and the name of the
    contract or of the daemon interface."""

    kind: TargetKind
    name: str


def parse_target_source(target_name: str, target: dict) -> TargetSource:
    """What the target `target_name` names. Raises TargetError when the
    target names no source, or names both a contract and a daemon
    interface."""
    kinds = [kind for kind in TargetKind if kind.value in target]
    if not kinds:
        raise TargetError(f"target `{target_name}` names neither a contract nor a daemon interface")
    if len(kinds) > 1:
        raise TargetError(f"target `{target_name}` names both a contract and a daemon interface")
    (kind,) = kinds
    return TargetSource(kind, target[kind.value]["name"])


def target_sources(document: dict) -> dict[str, TargetSource]:
    """What each target of `document` names, by target name, in document
    order. Raises TargetError for a target that `parse_target_source`
    refuses."""
    return {name: parse_target_source(name, target) for name, target in document.get("targets", {}).items()}


def values_of(key: str, value: object) -> Iterator[object]:
    """Every value of `key` in `value`, at any depth, in document order. A
    value of `key` is not searched further."""
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key:
                yield item
            else:
                yield from values_of(key, item)
    elif isinstance(value, list):
        for item in value:
            yield from values_of(key, item)


def descriptions(value: object) -> Iterator[str]:
    """Every value of a `description` key in `value`, at any depth, in
    document order: the call record's, each tool's, each resource's and
    each picture tool's."""
    yield from values_of("description", value)


def tool_names(value: object) -> Iterator[str]:
    """Every value of a `tool` key in `value`, at any depth, in document
    order: the name of each tool, the call record's and the listing's
    included."""
    yield from values_of("tool", value)


def texts(document: dict) -> list[tuple[str, str]]:
    """Each text of `document` a model reads, named: its server title, its
    instructions and every description."""
    server = document.get("server", {})
    named = [("title", server.get("title", "")), ("instructions", server.get("instructions", ""))]
    return named + [("description", description) for description in descriptions(document)]


def sits_under(path: Path, root: Path, directory: str) -> bool:
    """Whether `path` sits under the top-level `directory` of `root`."""
    return path.relative_to(root).parts[0] == directory


def documents_under(root: Path, directory: str) -> list[Path]:
    """The exposures under the top-level `directory` of `root`."""
    return [path for path in exposure_documents(root) if sits_under(path, root, directory)]


@dataclass(frozen=True)
class Family:
    """A family whose documents say what they are. Every document under
    `directory` has a server title that ends with `title_suffix` and
    instructions that open with the sentence `instructions_opening`, and
    every description holds one of `description_words` as a whole word,
    whatever the case."""

    directory: str
    title_suffix: str
    instructions_opening: str
    description_words: tuple[str, ...]

    def holds(self, path: Path, root: Path) -> bool:
        """Whether `path` sits under the directory of this family in
        `root`."""
        return sits_under(path, root, self.directory)

    def documents(self, root: Path) -> list[Path]:
        """The exposures under the directory of this family in `root`."""
        return documents_under(root, self.directory)

    def write_document(self, root: Path, name: str, document: str) -> Path:
        """Writes `document` as `name` under the directory of this family in
        `root`, which it makes when missing: the path written."""
        (root / self.directory).mkdir(exist_ok=True)
        path = root / self.directory / name
        path.write_text(document, encoding="utf-8")
        return path

    def has_a_description_word(self, text: str) -> bool:
        """Whether `text` holds one of `description_words` as a whole word,
        whatever the case."""
        return any(re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) for word in self.description_words)

    def wording_violations(self, path: Path) -> list[str]:
        """Each part of the wording of this family that `path` breaks,
        named; an empty list is the rule holding. The title and the
        instructions are checked whole; every description is checked for
        the word."""
        document = read_json5(path)
        server = document.get("server", {})
        violations = []
        if not server.get("title", "").endswith(self.title_suffix):
            violations.append(f"title must end with `{self.title_suffix}`")
        if not server.get("instructions", "").startswith(self.instructions_opening):
            violations.append(f"instructions must open with `{self.instructions_opening}`")
        words = " or ".join(f'"{word}"' for word in self.description_words)
        for description in descriptions(document):
            if not self.has_a_description_word(description):
                violations.append(f'description "{description}" must contain {words}')
        return violations


# The simulated world: no document of it has a counterpart on the physical
# robots.
SIMULATION = Family(
    directory="simulation",
    title_suffix="(simulation only)",
    instructions_opening=(
        "This endpoint configures a simulated world. "
        "It has no effect on and no counterpart in the physical robot."
    ),
    description_words=("simulation", "simulated"),
)

# The peppy framework: the stack of nodes that runs the robots, served by the
# peppy daemon through daemon interfaces.
FRAMEWORK = Family(
    directory="framework",
    title_suffix="(peppy framework)",
    instructions_opening=(
        "This endpoint controls the peppy framework that runs the robots: "
        "the stack of nodes, not the world and not the motion of a robot."
    ),
    description_words=("stack",),
)


def target_kind_violations(path: Path, root: Path) -> list[str]:
    """Each target of `path` whose kind the directory of `path` does not
    hold, named: a contract under `framework/`, a daemon interface anywhere
    else. An empty list is the rule holding."""
    if FRAMEWORK.holds(path, root):
        expected = TargetKind.DAEMON
        rule = f"a document under {FRAMEWORK.directory}/ names daemon interfaces only"
    else:
        expected = TargetKind.CONTRACT
        rule = f"only a document under {FRAMEWORK.directory}/ names a daemon interface"
    return [
        f"target `{name}` names {source.kind.noun} `{source.name}`: {rule}"
        for name, source in target_sources(read_json5(path)).items()
        if source.kind is not expected
    ]


# The daemon interface of the leases of the robots and the halt of a stack, and
# the members of it that an exposure selects: the fleet listing, the halt and
# its clearance.
ROBOT_LEASES_INTERFACE = "robot_leases"
ROBOT_LEASES_MEMBERS_FOR_EXPOSURES = ("list", "halt", "clear_halt")


def robot_leases_member_violations(document: dict) -> list[str]:
    """Each entry of `document` that selects a member of the daemon
    interface `ROBOT_LEASES_INTERFACE` other than
    `ROBOT_LEASES_MEMBERS_FOR_EXPOSURES`, named by its target and its member.
    An empty list is the rule holding."""
    robot_leases = TargetSource(TargetKind.DAEMON, ROBOT_LEASES_INTERFACE)
    allowed = ", ".join(ROBOT_LEASES_MEMBERS_FOR_EXPOSURES[:-1]) + f" and {ROBOT_LEASES_MEMBERS_FOR_EXPOSURES[-1]}"
    return [
        f"target `{name}` selects `{entry.get('member')}` of the daemon interface `{ROBOT_LEASES_INTERFACE}`: "
        f"an exposure selects {allowed} alone, and the other members are for programs"
        for name, source in target_sources(document).items()
        if source == robot_leases
        for kind in ("topics", "services", "actions")
        for entry in document["targets"][name].get(kind, [])
        if entry.get("member") not in ROBOT_LEASES_MEMBERS_FOR_EXPOSURES
    ]
