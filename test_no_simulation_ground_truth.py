"""Simulation contracts on MCP endpoints: what never reaches one, and how the
ones that do announce themselves.

An exposure is the one surface a model drives on the real robot and in
simulation alike: the same tools and resources, whatever the launcher binds
behind its targets. Two rules follow, both read from every ``mcp_exposure/v1``
document in the checkout.

Ground truth and the internal camera channel never reach an endpoint. A
contract that reports what only a simulation can know (``object_state``: the
pose and velocities of every spawned object, streamed and answered on demand
from the same snapshot; ``contact_state``: every contact the physics resolves,
with its normal force; ``sensor_readout``: the reading of every sensor the
simulated model declares) has no real-world implementer, so a target on it
would exist only in simulation and split the two surfaces. Ground truth stays
inside the peppy framework, for harness tests, recorders and the evaluation of
simulated behaviour. ``sim_camera_control``, the channel through which a
rendered camera's relay forwards the controls it receives to the engine, is
refused the same way: a relay drives it, never a model, and the relay's own
``rgb_camera`` / ``rgbd_camera`` surface is what an exposure publishes.

Simulation configuration reaches an endpoint under a wording rule.
``scene_manipulation``, ``object_controls``, ``scene_lighting`` and
``scene_materials`` edit the simulated world and have no physical counterpart
either, but a model legitimately drives them, as it does the cameras the
simulation renders. An exposure targeting one of the four lives under
``simulation/``, and every
document there says what it is: the server title ends with
``SIMULATION_TITLE_SUFFIX``, the instructions open with the sentence
``SIMULATION_INSTRUCTIONS_OPENING``, and every ``description`` of every topic,
service and action contains the word "simulation" or "simulated". A model
reading such an endpoint is never left to mistake it for a real-robot surface.

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
GROUND_TRUTH_CONTRACTS = frozenset({"object_state", "contact_state", "sensor_readout"})

# Contracts internal to the simulation stack: a relay drives them on a model's
# behalf, and their members name an engine's rendered cameras, which no model
# addresses.
INTERNAL_CONTRACTS = frozenset({"sim_camera_control"})

# Everything an exposure may not target.
FORBIDDEN_CONTRACTS = GROUND_TRUTH_CONTRACTS | INTERNAL_CONTRACTS

# Contracts that configure the simulated world. A model drives them, so an
# exposure may target them, from under `simulation/` only.
SIMULATION_CONFIGURATION_CONTRACTS = frozenset(
    {"scene_manipulation", "object_controls", "scene_lighting", "scene_materials"}
)

# The directory of every exposure that exists only in simulation, and the
# wording each document there carries so a model can tell.
SIMULATION_DIR = "simulation"
SIMULATION_TITLE_SUFFIX = "(simulation only)"
SIMULATION_INSTRUCTIONS_OPENING = (
    "This endpoint configures a simulated world. "
    "It has no effect on and no counterpart in the physical robot."
)
_SIMULATION_WORD = re.compile(r"\b(?:simulation|simulated)\b", re.IGNORECASE)

EXPOSURE_SCHEMA = "mcp_exposure/v1"

# Directories that hold no document of this repository.
_SKIP_DIRS = {".git", ".peppy", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}

_SCHEMA = re.compile(r"""peppy_schema\s*:\s*["']([^"']*)["']""")
# A target's `contract: { name, tag, sha256 }` block: no braces nest inside it.
_CONTRACT = re.compile(r"contract\s*:\s*\{([^{}]*)\}")
_NAME = re.compile(r"""\bname\s*:\s*["']([^"']*)["']""")
# A double-quoted string with its escapes, the form every prose field of the
# documents here takes. Group 1 is the raw body; `_unescape` reads it.
_STRING = r'"((?:[^"\\]|\\.)*)"'
_TITLE = re.compile(r"\btitle\s*:\s*" + _STRING)
_INSTRUCTIONS = re.compile(r"\binstructions\s*:\s*" + _STRING)
_DESCRIPTION = re.compile(r"\bdescription\s*:\s*" + _STRING)
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


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


def _unescape(body: str) -> str:
    """The text of a string literal's body: `\\"` reads as `"`, `\\\\` as
    `\\`, and the whitespace escapes as the whitespace they name."""
    return _ESCAPE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


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


def in_simulation_dir(path: Path, root: Path) -> bool:
    """Whether `path` sits under `root`'s `simulation/` directory."""
    return path.relative_to(root).parts[0] == SIMULATION_DIR


def simulation_documents(root: Path) -> list[Path]:
    """The exposures under `root`'s `simulation/` directory."""
    return [path for path in exposure_documents(root) if in_simulation_dir(path, root)]


def targeted_contracts(document: str) -> list[str]:
    """The contract names the document's targets bind, in file order."""
    names = []
    for block in _CONTRACT.finditer(strip_comments(document)):
        match = _NAME.search(block.group(1))
        if match:
            names.append(match.group(1))
    return names


def forbidden_targets(path: Path) -> list[str]:
    """The forbidden contracts `path` targets; an empty list is the rule
    holding."""
    targeted = targeted_contracts(path.read_text(encoding="utf-8"))
    return [name for name in targeted if name in FORBIDDEN_CONTRACTS]


def misplaced_configuration_targets(path: Path, root: Path) -> list[str]:
    """The simulation-configuration contracts `path` targets from outside
    `simulation/`; an empty list is the rule holding."""
    if in_simulation_dir(path, root):
        return []
    targeted = targeted_contracts(path.read_text(encoding="utf-8"))
    return [name for name in targeted if name in SIMULATION_CONFIGURATION_CONTRACTS]


def wording_violations(path: Path) -> list[str]:
    """Each part of the simulation wording rule `path` breaks, named; an
    empty list is the rule holding. The title and the instructions are
    checked whole; every description is checked for the word."""
    text = strip_comments(path.read_text(encoding="utf-8"))
    violations = []
    title = _TITLE.search(text)
    if not title or not _unescape(title.group(1)).endswith(SIMULATION_TITLE_SUFFIX):
        violations.append(f"title must end with `{SIMULATION_TITLE_SUFFIX}`")
    instructions = _INSTRUCTIONS.search(text)
    if not instructions or not _unescape(instructions.group(1)).startswith(
        SIMULATION_INSTRUCTIONS_OPENING
    ):
        violations.append(f"instructions must open with `{SIMULATION_INSTRUCTIONS_OPENING}`")
    for match in _DESCRIPTION.finditer(text):
        description = _unescape(match.group(1))
        if not _SIMULATION_WORD.search(description):
            violations.append(
                f'description "{description}" must contain "simulation" or "simulated"'
            )
    return violations


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_the_checkout_has_exposures_to_check() -> None:
    assert exposure_documents(ROOT), "no mcp_exposure/v1 document found: the walk is broken"


def test_the_checkout_has_simulation_documents_to_check() -> None:
    assert simulation_documents(ROOT), "no exposure under simulation/: the walk is broken"


@pytest.mark.parametrize("path", exposure_documents(ROOT), ids=_relative)
def test_no_exposure_targets_a_forbidden_contract(path: Path) -> None:
    offending = forbidden_targets(path)
    assert not offending, (
        f"{_relative(path)} targets {', '.join(offending)}: simulation ground truth and the "
        "internal camera channel stay inside the peppy framework and never reach an MCP endpoint"
    )


@pytest.mark.parametrize("path", exposure_documents(ROOT), ids=_relative)
def test_simulation_configuration_lives_under_simulation(path: Path) -> None:
    misplaced = misplaced_configuration_targets(path, ROOT)
    assert not misplaced, (
        f"{_relative(path)} targets {', '.join(misplaced)}: an exposure that configures the "
        f"simulated world lives under {SIMULATION_DIR}/"
    )


@pytest.mark.parametrize("path", simulation_documents(ROOT), ids=_relative)
def test_simulation_documents_say_what_they_are(path: Path) -> None:
    violations = wording_violations(path)
    assert not violations, f"{_relative(path)}: " + "; ".join(violations)


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


@pytest.mark.parametrize(
    ("contract", "member"),
    [("object_state", "object_states"), ("contact_state", "contacts"), ("sensor_readout", "sensor_readings")],
)
def test_a_target_on_simulation_ground_truth_is_refused(
    tmp_path: Path, contract: str, member: str
) -> None:
    path = tmp_path / "sim_objects.json5"
    document = _OFFENDING.replace('member: "object_states"', f'member: "{member}"')
    document = document.replace('name: "object_state"', f'name: "{contract}"')
    path.write_text(document, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert forbidden_targets(path) == [contract]


_OFFENDING_CONTACTS_AND_SENSORS = """// Targets on the contact list and the sensor readout, refused too.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_touch", tag: "v1" },
  server: { title: "Touch", instructions: "Read what the gripper feels." },
  targets: {
    contacts: {
      contract: { name: "contact_state", tag: "v1" },
      topics: [
        { member: "contacts", resource: "touch.contacts", description: "What touches what.",
          freshness: { max_age_ms: 200 } },
      ],
    },
    sensors: {
      contract: { name: "sensor_readout", tag: "v1" },
      topics: [
        { member: "sensor_readings", resource: "touch.sensors", description: "The pads.",
          freshness: { max_age_ms: 200 } },
      ],
    },
  },
}
"""


_OFFENDING_SNAPSHOT = """// A tool on the on-demand object snapshot, refused like the stream.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_snapshot", tag: "v1" },
  server: { title: "Snapshot", instructions: "Ask where the objects are." },
  targets: {
    objects: {
      contract: { name: "object_state", tag: "v1" },
      services: [
        { member: "get_object_states", tool: "objects_snapshot", description: "Every spawned object." },
      ],
    },
  },
}
"""


_OFFENDING_CAMERA_CHANNEL = """// A tool on the relay-to-engine camera channel, refused: a relay drives it.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_camera_knobs", tag: "v1" },
  server: { title: "Camera knobs (simulation only)", instructions: "Drive the rendered cameras." },
  targets: {
    engine: {
      contract: { name: "sim_camera_control", tag: "v1" },
      services: [
        { member: "set_camera_exposure", tool: "engine.set_exposure", description: "Exposure by camera.",
          operation: "mutating", deadline_ms: 2000 },
      ],
    },
  },
}
"""


def test_a_target_on_the_object_snapshot_service_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sim_snapshot.json5"
    path.write_text(_OFFENDING_SNAPSHOT, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert forbidden_targets(path) == ["object_state"]


def test_targets_on_contacts_and_sensors_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "sim_touch.json5"
    path.write_text(_OFFENDING_CONTACTS_AND_SENSORS, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert forbidden_targets(path) == ["contact_state", "sensor_readout"]


def test_a_target_on_the_internal_camera_channel_is_refused(tmp_path: Path) -> None:
    (tmp_path / SIMULATION_DIR).mkdir()
    path = tmp_path / SIMULATION_DIR / "sim_camera_knobs.json5"
    path.write_text(_OFFENDING_CAMERA_CHANNEL, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    # Under simulation/ or not, the channel is refused outright.
    assert forbidden_targets(path) == ["sim_camera_control"]


def test_other_contracts_comments_and_prose_pass() -> None:
    document = """{
      peppy_schema: "mcp_exposure/v1",
      targets: {
        // contract: { name: "object_state", tag: "v1" },
        /* contract: { name: "sim_camera_control" } */
        cam: { contract: { name: "rgb_camera", tag: "v1", sha256: "ab" }, topics: [] },
        arms: { contract: { name: "postures", tag: 'v1' },
                actions: [ { member: "move_to_ready", description: "no object_state here" } ] },
      },
    }"""
    assert targeted_contracts(document) == ["rgb_camera", "postures"]
    assert not [name for name in targeted_contracts(document) if name in FORBIDDEN_CONTRACTS]


_COMPLIANT = """// A simulation-configuration exposure that follows every rule.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_lights", tag: "v1" },
  server: {
    title: "Scene lighting (simulation only)",
    instructions: "This endpoint configures a simulated world. It has no effect on and no counterpart in the physical robot. Read, then set.",
  },
  targets: {
    lighting: {
      contract: { name: "scene_lighting", tag: "v1" },
      services: [
        { member: "get_lighting", tool: "lighting.get_lighting",
          description: "Every light of the simulated scene, with \\"id\\" and kind.",
          operation: "read_only", deadline_ms: 5000 },
        { member: "reset_lighting", tool: "lighting.reset_lighting",
          description: "Authored lighting back, in the simulation.",
          operation: "mutating", deadline_ms: 5000 },
      ],
      topics: [],
    },
  },
}
"""


@pytest.mark.parametrize("contract", sorted(SIMULATION_CONFIGURATION_CONTRACTS))
def test_a_configuration_exposure_outside_simulation_is_caught(tmp_path: Path, contract: str) -> None:
    (tmp_path / "cameras").mkdir()
    path = tmp_path / "cameras" / "sim_lights.json5"
    path.write_text(_COMPLIANT.replace('name: "scene_lighting"', f'name: "{contract}"'), encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert misplaced_configuration_targets(path, tmp_path) == [contract]


def test_a_configuration_exposure_under_simulation_passes(tmp_path: Path) -> None:
    (tmp_path / SIMULATION_DIR).mkdir()
    path = tmp_path / SIMULATION_DIR / "sim_lights.json5"
    path.write_text(_COMPLIANT, encoding="utf-8")
    assert simulation_documents(tmp_path) == [path]
    assert misplaced_configuration_targets(path, tmp_path) == []
    assert forbidden_targets(path) == []
    assert wording_violations(path) == []


def test_a_camera_exposure_outside_simulation_is_not_misplaced(tmp_path: Path) -> None:
    (tmp_path / "cameras").mkdir()
    path = tmp_path / "cameras" / "front.json5"
    path.write_text(_COMPLIANT.replace('name: "scene_lighting"', 'name: "rgb_camera"'), encoding="utf-8")
    assert misplaced_configuration_targets(path, tmp_path) == []


@pytest.mark.parametrize(
    ("part", "before", "after"),
    [
        ("title", "Scene lighting (simulation only)", "Scene lighting"),
        (
            "instructions",
            "This endpoint configures a simulated world. It has no effect on and no counterpart in the physical robot. Read, then set.",
            "Read, then set, in the simulated scene.",
        ),
        ("description", "Authored lighting back, in the simulation.", "Authored lighting back."),
    ],
)
def test_a_simulation_document_missing_a_wording_part_is_caught(
    tmp_path: Path, part: str, before: str, after: str
) -> None:
    (tmp_path / SIMULATION_DIR).mkdir()
    path = tmp_path / SIMULATION_DIR / "sim_lights.json5"
    assert before in _COMPLIANT
    path.write_text(_COMPLIANT.replace(before, after), encoding="utf-8")
    violations = wording_violations(path)
    assert len(violations) == 1, violations
    assert violations[0].startswith(part), violations[0]


def test_a_simulation_document_missing_every_wording_part_names_each(tmp_path: Path) -> None:
    (tmp_path / SIMULATION_DIR).mkdir()
    path = tmp_path / SIMULATION_DIR / "sim_lights.json5"
    document = _COMPLIANT
    document = document.replace("Scene lighting (simulation only)", "Scene lighting")
    document = document.replace("This endpoint configures a simulated world. ", "")
    document = document.replace("Every light of the simulated scene", "Every light of the scene")
    document = document.replace("Authored lighting back, in the simulation.", "Authored lighting back.")
    path.write_text(document, encoding="utf-8")
    parts = [violation.split(" ", 1)[0] for violation in wording_violations(path)]
    assert parts == ["title", "instructions", "description", "description"]


def test_the_wording_word_is_matched_whole_and_case_insensitively() -> None:
    assert _SIMULATION_WORD.search("Latest frame from the Simulated camera.")
    assert _SIMULATION_WORD.search("in the SIMULATION.")
    assert not _SIMULATION_WORD.search("a simulator's frame")
    assert not _SIMULATION_WORD.search("simulations of the arm")


def test_documents_of_other_schemas_are_not_exposures(tmp_path: Path) -> None:
    (tmp_path / "peppy_repository.json5").write_text(
        '{ peppy_schema: "repository/v1", mcp_exposures: {} }', encoding="utf-8"
    )
    assert exposure_documents(tmp_path) == []


def test_strings_keep_their_comment_markers() -> None:
    assert strip_comments('{ a: "http://x", b: 1 /* c */ } // d') == '{ a: "http://x", b: 1  } '
    assert strip_comments("{ a: 'it\\'s // not a comment' }") == "{ a: 'it\\'s // not a comment' }"


def test_prose_with_escaped_quotes_is_read_whole() -> None:
    text = 'description: "mode is \\"auto\\" or \\"manual\\", in the simulation."'
    match = _DESCRIPTION.search(text)
    assert match
    assert _unescape(match.group(1)) == 'mode is "auto" or "manual", in the simulation.'
