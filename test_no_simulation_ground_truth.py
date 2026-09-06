"""Simulation ground truth never reaches an MCP endpoint.

An exposure is the one surface a model drives on the real robot and in
simulation alike: the same tools and resources, whatever the launcher binds
behind its targets. A contract that reports what only a simulation can know
(``object_state``: the live pose, velocities and contacts of every object a
scene commander spawned) has no real-world implementer, so a target on it
would exist only in simulation and split the two surfaces. Ground truth stays
inside the peppy framework, for harness tests, recorders and the evaluation
of a trained behaviour. This test reads every ``mcp_exposure/v1`` document in
the checkout and fails on one that targets such a contract.

pytest collects it from the repository root without the workflow naming it;
the exposures it checks are discovered the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent

# Contracts whose members are simulation ground truth: an engine's report of
# what it alone can know. Nothing on a real robot implements them, so no
# exposure may select their members. Contract names, any tag. Extend it when
# the contracts hub gains another such contract.
GROUND_TRUTH_CONTRACTS = frozenset({"object_state"})

EXPOSURE_SCHEMA = "mcp_exposure/v1"

# Directories that hold no document of this repository.
_SKIP_DIRS = {".git", ".peppy", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}

_SCHEMA = re.compile(r"""peppy_schema\s*:\s*["']([^"']*)["']""")
# A target's `contract: { name, tag, sha256 }` block: no braces nest inside it.
_CONTRACT = re.compile(r"contract\s*:\s*\{([^{}]*)\}")
_NAME = re.compile(r"""\bname\s*:\s*["']([^"']*)["']""")


def strip_comments(text: str) -> str:
    """The document without its `//` and `/* */` comments. String contents
    are kept as they are, comment markers inside them included."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def exposure_documents(root: Path) -> list[Path]:
    """Every json5 document under `root` whose schema is an MCP exposure,
    listed in the repository index or not: the rule holds for any document
    that could be published."""
    found = []
    for path in sorted(root.rglob("*.json5")):
        if _SKIP_DIRS.intersection(path.relative_to(root).parts):
            continue
        match = _SCHEMA.search(strip_comments(path.read_text(encoding="utf-8")))
        if match and match.group(1) == EXPOSURE_SCHEMA:
            found.append(path)
    return found


def targeted_contracts(document: str) -> list[str]:
    """The contract names the document's targets bind, in file order."""
    names = []
    for block in _CONTRACT.finditer(strip_comments(document)):
        match = _NAME.search(block.group(1))
        if match:
            names.append(match.group(1))
    return names


def ground_truth_targets(path: Path) -> list[str]:
    """The ground-truth contracts `path` targets; an empty list is the rule
    holding."""
    targeted = targeted_contracts(path.read_text(encoding="utf-8"))
    return [name for name in targeted if name in GROUND_TRUTH_CONTRACTS]


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_the_checkout_has_exposures_to_check() -> None:
    assert exposure_documents(ROOT), "no mcp_exposure/v1 document found: the walk is broken"


@pytest.mark.parametrize("path", exposure_documents(ROOT), ids=_relative)
def test_no_exposure_targets_simulation_ground_truth(path: Path) -> None:
    offending = ground_truth_targets(path)
    assert not offending, (
        f"{_relative(path)} targets {', '.join(offending)}: simulation ground truth stays "
        "inside the peppy framework and never reaches an MCP endpoint"
    )


_OFFENDING = """// A target on ground truth, which this repository refuses.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_objects", tag: "v1" },
  server: { title: "Objects", instructions: "Read where the objects are." },
  targets: {
    objects: {
      contract: { name: "object_state", tag: "v1" },
      topics: [
        { member: "object_states", resource: "objects.states", description: "Live poses.",
          freshness: { max_age_ms: 200 } },
      ],
    },
  },
}
"""


def test_a_target_on_object_state_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sim_objects.json5"
    path.write_text(_OFFENDING, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert ground_truth_targets(path) == ["object_state"]


def test_other_contracts_comments_and_prose_pass() -> None:
    document = """{
      peppy_schema: "mcp_exposure/v1",
      targets: {
        // contract: { name: "object_state", tag: "v1" },
        /* contract: { name: "object_state" } */
        cam: { contract: { name: "rgb_camera", tag: "v1", sha256: "ab" }, topics: [] },
        arms: { contract: { name: "postures", tag: 'v1' },
                actions: [ { member: "move_to_ready", description: "no object_state here" } ] },
      },
    }"""
    assert targeted_contracts(document) == ["rgb_camera", "postures"]
    assert not [name for name in targeted_contracts(document) if name in GROUND_TRUTH_CONTRACTS]


def test_documents_of_other_schemas_are_not_exposures(tmp_path: Path) -> None:
    (tmp_path / "peppy_repository.json5").write_text(
        '{ peppy_schema: "repository/v1", mcp_exposures: {} }', encoding="utf-8"
    )
    assert exposure_documents(tmp_path) == []


def test_strings_keep_their_comment_markers() -> None:
    assert strip_comments('{ a: "http://x", b: 1 /* c */ } // d') == '{ a: "http://x", b: 1  } '
    assert strip_comments("{ a: 'it\\'s // not a comment' }") == "{ a: 'it\\'s // not a comment' }"
