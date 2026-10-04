"""Every setter's description says what holds after the call.

A model learns from a tool's description what a call changes and what
follows from it: where an object comes to rest, what a robot does next, what
nothing checks. So the description of every tool that changes the world or
moves a robot has a sentence that begins with "After the call,", the second
of the four parts that the README's "Writing tool texts" names. This test
checks that the sentence is there, not that it is true: a text states a fact
only when a test of the code behind the tool pins it.

A setter is an entry of a target's `services` or `actions` whose operation
is not read_only (peppy requires an operation on each entry: read_only or
mutating for a service, long_running for an action). The call-record tool,
the robot listing and the picture tools are not entries of a target's
services or actions, so they are not setters.

The sentence must begin a sentence, with the capital letter and the comma:
it opens the description or follows a full stop, a question mark or an
exclamation mark and white space. Several descriptions say "the effective
value after the call" inside a sentence, and that form does not count.

The covered targets are an explicit list, so a target is covered because its
author decided it: every target of the simulated world's document, and the
posture and limb moves of the robots' document. The other targets of the
robots' document, its cameras, brain and recorder among them, are not
covered. The setters the covered targets give are an explicit list too, so
a new setter, or a tool whose operation changes, fails here until the list
names it.

The documents are read with `exposure_json5`, since the pull request
workflow installs pytest and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest

from exposure_json5 import parse_json5

ROOT = Path(__file__).resolve().parent

AFTER_THE_CALL = "After the call,"
# The sentence opens the description, or follows the end of another sentence.
_AFTER_THE_CALL_SENTENCE = re.compile(r"(?:^|[.!?]\s+)" + re.escape(AFTER_THE_CALL))

SIMULATION_DOCUMENT = "simulation/simulation.json5"
ROBOT_DOCUMENT = "robot/robot_control.json5"

# The targets whose setters the rule covers, per exposure document.
COVERED_TARGETS = {
    SIMULATION_DOCUMENT: ("scene", "controls", "lighting", "materials", "view", "clock", "workspace"),
    ROBOT_DOCUMENT: ("postures", "limb_motion"),
}

# The setters the covered targets give, per exposure document.
COVERED_SETTERS = {
    SIMULATION_DOCUMENT: frozenset(
        {
            "scene.load_scene",
            "scene.clear_scene",
            "scene.spawn_object",
            "scene.move_object",
            "scene.remove_object",
            "scene.apply_force",
            "scene.move_robot",
            "controls.set_object_control",
            "lighting.set_light_intensity",
            "lighting.set_light_color",
            "lighting.set_light_position",
            "lighting.set_light_direction",
            "lighting.set_light_cone",
            "lighting.set_light_orientation",
            "lighting.reset_lighting",
            "materials.set_material_color",
            "materials.set_material_finish",
            "materials.reset_materials",
            "clock.set_paused",
            "clock.step",
        }
    ),
    ROBOT_DOCUMENT: frozenset(
        {
            "robot.move_to_ready",
            "robot.move_to_home",
            "robot.move_arm",
            "robot.move_arm_joints",
            "robot.move_gripper",
            "robot.stop",
        }
    ),
}


def has_an_after_the_call_sentence(description: str) -> bool:
    """Whether a sentence of `description` begins with "After the call,"."""
    return _AFTER_THE_CALL_SENTENCE.search(description) is not None


def setters(document: dict, targets: Iterable[str]) -> list[dict]:
    """The entries of the services and actions of `targets` in `document`
    whose operation is not read_only, target by target, services first."""
    found = []
    for name in targets:
        target = document["targets"][name]
        entries = [*target.get("services", []), *target.get("actions", [])]
        found.extend(entry for entry in entries if entry.get("operation") != "read_only")
    return found


def setter_violations(document: dict, targets: Iterable[str]) -> list[str]:
    """Each setter of `targets` whose description has no sentence that
    begins with "After the call,", named by its tool; an empty list is the
    rule holding."""
    return [
        f'{entry["tool"]}: no sentence of its description begins with "{AFTER_THE_CALL}"'
        for entry in setters(document, targets)
        if not has_an_after_the_call_sentence(entry.get("description", ""))
    ]


def read_document(relative: str) -> dict:
    return parse_json5((ROOT / relative).read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative", sorted(COVERED_TARGETS))
def test_every_setter_description_has_an_after_the_call_sentence(relative: str) -> None:
    violations = setter_violations(read_document(relative), COVERED_TARGETS[relative])
    assert not violations, f"{relative}: " + "; ".join(violations)


@pytest.mark.parametrize("relative", sorted(COVERED_TARGETS))
def test_the_covered_setters_are_the_listed_ones(relative: str) -> None:
    found = {entry["tool"] for entry in setters(read_document(relative), COVERED_TARGETS[relative])}
    assert found == COVERED_SETTERS[relative], (
        f"{relative}: not listed {sorted(found - COVERED_SETTERS[relative])}, "
        f"listed but not found {sorted(COVERED_SETTERS[relative] - found)}"
    )


def test_every_target_of_the_simulated_world_is_covered() -> None:
    targets = read_document(SIMULATION_DOCUMENT)["targets"]
    assert sorted(targets) == sorted(COVERED_TARGETS[SIMULATION_DOCUMENT])


_FIXTURE = """// Two covered targets, the tools that are not setters, and a target
// the rule does not cover.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_lights", tag: "v1" },
  server: { title: "Lights (simulation only)", instructions: "Read, then set." },
  call_record: { tool: "lights.recent_calls", description: "The last calls.", keep: 200 },
  targets: {
    lighting: {
      contract: { name: "scene_lighting", tag: "v1" },
      services: [
        { member: "get_lighting", tool: "lighting.get_lighting", description: "Every light.",
          operation: "read_only", deadline_ms: 5000 },
        { member: "set_light_intensity", tool: "lighting.set_light_intensity",
          description: "Set a light's strength. After the call, the light's strength is current_value.",
          operation: "mutating", deadline_ms: 5000, restrict: { value: { min: 0, max: 10 } } },
      ],
      topics: [
        { member: "frames", resource: "lighting.frame", description: "The latest frame.",
          picture: { tool: "lighting.look", description: "Look at the lights." } },
      ],
    },
    clock: {
      contract: { name: "simulation_clock", tag: "v1" },
      actions: [
        { member: "step", tool: "clock.step",
          description: "Advance the clock. After the call, the clock stands still again.",
          operation: "long_running", deadline_ms: 60000 },
      ],
    },
    camera: {
      contract: { name: "rgb_camera", tag: "v1" },
      services: [
        { member: "set_exposure", tool: "camera.set_exposure", description: "Set the exposure.",
          operation: "mutating", deadline_ms: 2000 },
      ],
    },
  },
}
"""
_FIXTURE_TARGETS = ("lighting", "clock")
_INTENSITY_SENTENCE = "After the call, the light's strength is current_value."


def test_a_document_whose_setters_have_the_sentence_passes() -> None:
    assert setter_violations(parse_json5(_FIXTURE), _FIXTURE_TARGETS) == []


def test_only_the_services_and_actions_of_covered_targets_are_setters() -> None:
    # Not the read_only service, the call-record tool, the picture tool, or
    # the setter of the target the rule does not cover.
    tools = [entry["tool"] for entry in setters(parse_json5(_FIXTURE), _FIXTURE_TARGETS)]
    assert tools == ["lighting.set_light_intensity", "clock.step"]


@pytest.mark.parametrize(
    "replacement",
    [
        "Answers with current_value.",
        "Answers with current_value, the effective value after the call.",
        "after the call, the light's strength is current_value.",
        "The light's strength After the call, is current_value.",
        "After the call the light's strength is current_value.",
    ],
    ids=["no sentence", "inside a sentence", "lower case", "not at a sentence start", "no comma"],
)
def test_a_setter_without_the_sentence_is_named(replacement: str) -> None:
    assert _INTENSITY_SENTENCE in _FIXTURE
    document = parse_json5(_FIXTURE.replace(_INTENSITY_SENTENCE, replacement))
    assert setter_violations(document, _FIXTURE_TARGETS) == [
        'lighting.set_light_intensity: no sentence of its description begins with "After the call,"'
    ]


def test_a_read_only_tool_is_not_checked() -> None:
    # The read_only service has no such sentence; as a mutating one it fails.
    flipped = _FIXTURE.replace('description: "Every light.",\n          operation: "read_only"',
                               'description: "Every light.",\n          operation: "mutating"')
    assert flipped != _FIXTURE
    violations = setter_violations(parse_json5(flipped), _FIXTURE_TARGETS)
    assert [violation.split(":", 1)[0] for violation in violations] == ["lighting.get_lighting"]


@pytest.mark.parametrize(
    ("description", "has_it"),
    [
        ("After the call, the lamp sits at current_position.", True),
        ("Set it. After the call, the lamp sits at current_position.", True),
        ("Set it?  After the call, the lamp sits at current_position.", True),
        ("Set it!\nAfter the call, the lamp sits at current_position.", True),
        ("Set it; After the call, the lamp sits at current_position.", False),
        ("Set it: After the call, the lamp sits at current_position.", False),
        ("Set it.After the call, the lamp sits at current_position.", False),
        ("Answers with current_position, the effective position after the call.", False),
        ("", False),
    ],
)
def test_the_sentence_begins_a_sentence_with_its_capital_and_comma(description: str, has_it: bool) -> None:
    assert has_an_after_the_call_sentence(description) is has_it
