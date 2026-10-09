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

The documents of `simulation/` and of `framework/` say what they are, so a
model can always tell where a call goes. A `Family` holds the wording of one
of them: the suffix of the server title, the sentence that opens the
instructions, and the words of which every description holds one. `SIMULATION`
and `FRAMEWORK` are the two families. `test_no_simulation_ground_truth.py`
applies the wording of `SIMULATION`, and `test_exposure_families.py` applies
the wording of `FRAMEWORK` and the rule of the target kinds.

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


def descriptions(value: object) -> Iterator[str]:
    """Every value of a `description` key in `value`, at any depth, in
    document order: the call record's, each tool's, each resource's and
    each picture tool's."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "description":
                yield item
            else:
                yield from descriptions(item)
    elif isinstance(value, list):
        for item in value:
            yield from descriptions(item)


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
        return path.relative_to(root).parts[0] == self.directory

    def documents(self, root: Path) -> list[Path]:
        """The exposures under the directory of this family in `root`."""
        return [path for path in exposure_documents(root) if self.holds(path, root)]

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
