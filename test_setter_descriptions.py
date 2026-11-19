"""The description of every covered setter says what holds after the call.

A model learns from a tool's description what a call changes and what
follows from it. For example: where an object comes to rest, what a robot
does next, and what nothing checks. So the description of every covered setter has a
sentence that begins with "After the call,". That sentence is the second of
the four parts that the README's "Writing tool texts" names. This test checks
that the sentence is there, not that it is true. A text states a fact only
when a test of the code behind the tool pins it.

A setter is an entry of a target's `services` or `actions` whose operation
is not read_only. peppy requires an operation on each entry: read_only or
mutating for a service, long_running for an action. The call-record tool,
the robot listing and the picture tools are not entries of a target's
services or actions, so they are not setters.

The sentence must begin a sentence, with the capital letter and the comma.
It opens the description, or it follows white space after a full stop, a
question mark or an exclamation mark. Several descriptions say "the
effective value after the call" inside a sentence, and that form does not
count.

Each target of each exposure document is in one of two explicit lists, so
its author decides whether the rule covers it. COVERED_TARGETS holds every
target of the simulated world's document, the posture and limb moves, the
motion planner and the brain's model of the robots' document, and the stack
and the fleet of the framework's document. A target that names a daemon
interface is read as a target that names a contract: its setters are the
entries of its services and actions too.
UNCOVERED_TARGETS
holds every other target, with the reason. A target in no list fails here, and so does a target in both lists.
A target left out because it has no setter fails here when it gets one. The
setters of the covered targets are an explicit list too. So a new setter, or
a tool whose operation changes, fails here until the list names it.

A tool whose request takes a point, a pose or a velocity takes it as a
record that names its frame and its timestamp, and the document's
instructions state what the two mean in a frame rule, a sentence that
begins with "Frame rule:". So the description of every such tool, a setter
or a read, names `frame` and `timestamp` as whole words and sends its reader
to the frame rule. STAMPED_TOOLS lists these tools per exposure document:
the tools whose contract member's request holds a record with frame and
timestamp, which `peppy mcp catalog <name>:<tag>` shows in each tool's
input schema. A listed tool that is not a tool of its document fails here.

A call leaves a timestamp out for the latest time. So the instructions of
a document with such tools say that a call may leave timestamp out, and
the description of each such tool spells no time 0: no RFC 3339 time of
1970-01-01, and no "time 0" or "timestamp 0" in words.

The documents are read with `exposure_json5`, since the pull request
workflow installs pytest and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
import pytest

from exposure_json5 import REPOSITORY_ROOT, document_name, exposure_documents, parse_json5, read_json5

AFTER_THE_CALL = "After the call,"
# The sentence opens the description, or follows the end of another sentence.
_AFTER_THE_CALL_SENTENCE = re.compile(r"(?:^|[.!?]\s+)" + re.escape(AFTER_THE_CALL))

SIMULATION_DOCUMENT = "simulation/simulation.json5"
ROBOT_DOCUMENT = "robot/robot_control.json5"
FRAMEWORK_DOCUMENT = "framework/framework_controls.json5"
WORKFLOW_DOCUMENT = "workflow/workflow_controls.json5"
RECORDING_DOCUMENT = "recording/camera_and_recording.json5"

# The targets whose setters the rule covers, per exposure document.
COVERED_TARGETS = {
    SIMULATION_DOCUMENT: (
        "scene",
        "controls",
        "lighting",
        "daylight",
        "materials",
        "view",
        "clock",
        "workspace",
        "sensor_streams",
        "world",
        "sweep",
    ),
    ROBOT_DOCUMENT: ("postures", "limb_motion", "planner", "brain_model"),
    FRAMEWORK_DOCUMENT: ("stack", "fleet"),
    WORKFLOW_DOCUMENT: ("director",),
}

# The reason of a target that has no setter.
NO_SETTER = "it has no setter"
# The targets the rule does not cover, per exposure document, each with the
# reason.
UNCOVERED_TARGETS = {
    ROBOT_DOCUMENT: {
        "identity": NO_SETTER,
        "guide": NO_SETTER,
        "limb_state": NO_SETTER,
        "collision": NO_SETTER,
        "motor_health": NO_SETTER,
        "alerts": NO_SETTER,
        "camera": "its setters set a camera's device controls",
        "depth_camera": "its setters set a camera's device controls",
        "camera_profile": "its setter resets a camera's device controls",
        "camera_geometry": NO_SETTER,
        "sensor_mounts": NO_SETTER,
        "transform_lookup": NO_SETTER,
        "workspace": NO_SETTER,
        "item_perception": "its actions are the brain's sequences",
        "item_manipulation": "its actions are the brain's sequences",
        "recorder": "its action records an episode",
    },
    RECORDING_DOCUMENT: {
        "camera": "its setter sets a camera's device control",
        "recorder": "its action records an episode",
    },
}

# The setters the covered targets give, per exposure document.
COVERED_SETTERS = {
    SIMULATION_DOCUMENT: frozenset(
        {
            "scene.load_scene",
            "scene.load_template",
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
            "daylight.set_daylight_time",
            "daylight.set_daylight_rate",
            "daylight.set_weather",
            "daylight.reset_daylight",
            "materials.set_material_color",
            "materials.set_material_finish",
            "materials.reset_materials",
            "clock.set_paused",
            "clock.step",
            "workspace.furnish",
            "workspace.stand_at",
            "workspace.raise_object",
            "workspace.name_location",
            "sensors.hold",
            "sensors.release",
            "world.get",
            "world.check",
            "world.expand",
            "world.apply",
            "world.reset",
            "world.run",
            "world.judge",
            "sweep.start",
            "sweep.abort",
        }
    ),
    ROBOT_DOCUMENT: frozenset(
        {
            "robot.move_to_ready",
            "robot.move_to_home",
            "robot.move_arm",
            "robot.move_arm_joints",
            "robot.execute_joint_path",
            "robot.move_gripper",
            "robot.stop",
            "planner.plan_joint_path",
            "planner.plan_cartesian_path",
            "planner.clear_occupancy_map",
            "planner.apply_collision_objects",
            "planner.apply_attached_collision_object",
            "planner.set_allowed_collision",
            "brain.switch_model",
            "brain.forget",
        }
    ),
    FRAMEWORK_DOCUMENT: frozenset({"stack.join", "stack.remove", "fleet.halt", "fleet.clear_halt"}),
    WORKFLOW_DOCUMENT: frozenset(
        {
            "workflow.confirm",
            "workflow.suspend",
            "workflow.judge_checks",
            "workflow.judge_ending",
            "workflow.run",
            "workflow.resume",
            "workflow.abort",
            "workflow.trial",
            "workflow.next_run",
        }
    ),
}


# The sentence of a document's instructions that opens its frame rule.
FRAME_RULE = "Frame rule:"
# The words of a tool description that send its reader to the frame rule.
FRAME_RULE_REFERENCE = "frame rule"
# The fields of a stamped value that a tool description names.
STAMPED_FIELDS = ("frame", "timestamp")

# The words of a document's instructions that say a call may leave its
# timestamp out.
TIMESTAMP_LEFT_OUT = "may leave timestamp out"
# The time 0 as a tool description can spell it: an RFC 3339 time of
# 1970-01-01, or "time 0" or "timestamp 0" in words, a field name such as
# target_timestamp included.
TIME_ZERO = re.compile(r"1970-01-01|\b(?:\w+_)?time(?:stamp)? 0(?!\.?\d)")

# The tools whose request takes a stamped value, per exposure document.
STAMPED_TOOLS = {
    ROBOT_DOCUMENT: frozenset(
        {
            "robot.move_arm",
            "robot.check_arm_move",
            "robot.lookup_transform",
            "robot.check_positions",
            "planner.plan_joint_path",
            "planner.plan_cartesian_path",
            "planner.apply_collision_objects",
            "brain.grab_item",
            "brain.place_item",
        }
    ),
    SIMULATION_DOCUMENT: frozenset(
        {
            "scene.spawn_object",
            "scene.move_object",
            "scene.apply_force",
            "scene.move_robot",
            "lighting.set_light_position",
            "lighting.set_light_direction",
            "lighting.set_light_orientation",
            "scene.look",
            "scene.locate_in_view",
            "scene.locate_points",
            "workspace.describe",
            "workspace.find_places",
            "workspace.furnish",
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


def tool_entries(document: dict) -> dict[str, dict]:
    """Every entry of the services and actions of `document`, by its tool."""
    return {
        entry["tool"]: entry
        for target in document["targets"].values()
        for entry in [*target.get("services", []), *target.get("actions", [])]
    }


def names_the_word(text: str, word: str) -> bool:
    """Whether `text` holds `word` as a whole word: `timestamp` in
    "source_timestamp" does not count."""
    return re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", text) is not None


def stamped_tool_violations(document: dict, tools: Iterable[str]) -> list[str]:
    """Each of `tools` that `document` does not hold, or whose description
    does not name `frame` and `timestamp` beside the name of the frame rule,
    and the frame rule; an empty list is the rule holding."""
    entries = tool_entries(document)
    violations = []
    for tool in sorted(tools):
        if tool not in entries:
            violations.append(f"{tool}: not a tool of the document")
            continue
        description = entries[tool].get("description", "")
        # The name of the rule holds the word frame, and names no field.
        fields_text = description.replace(FRAME_RULE_REFERENCE, "")
        missing = [f"`{word}`" for word in STAMPED_FIELDS if not names_the_word(fields_text, word)]
        if FRAME_RULE_REFERENCE not in description:
            missing.append(f'"{FRAME_RULE_REFERENCE}"')
        if missing:
            violations.append(f"{tool}: its description does not name " + ", ".join(missing))
    return violations


def states_the_frame_rule(document: dict) -> bool:
    """Whether a sentence of the document's instructions opens with "Frame rule:"."""
    instructions = document.get("server", {}).get("instructions", "")
    return re.search(r"(?:^|[.!?]\s+)" + re.escape(FRAME_RULE), instructions) is not None


def absent_timestamp_violations(document: dict, tool: str) -> list[str]:
    """What keeps a call of `tool` from leaving its timestamp out: each
    spelling of the time 0 in the tool's description, and instructions
    that do not say a call may leave timestamp out; an empty list is the
    rule holding."""
    description = tool_entries(document).get(tool, {}).get("description", "")
    violations = [
        f'{tool}: its description spells the time 0 as "{spelling}"' for spelling in TIME_ZERO.findall(description)
    ]
    if TIMESTAMP_LEFT_OUT not in document.get("server", {}).get("instructions", ""):
        violations.append(f'{tool}: the instructions do not say "{TIMESTAMP_LEFT_OUT}"')
    return violations


def read_document(relative: str) -> dict:
    return read_json5(REPOSITORY_ROOT / relative)


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


@pytest.mark.parametrize("relative", [document_name(path) for path in exposure_documents(REPOSITORY_ROOT)])
def test_every_target_is_covered_or_left_out_by_name(relative: str) -> None:
    targets = set(read_document(relative)["targets"])
    covered = set(COVERED_TARGETS.get(relative, ()))
    uncovered = set(UNCOVERED_TARGETS.get(relative, {}))
    assert not covered & uncovered, f"{relative}: both covered and left out: {sorted(covered & uncovered)}"
    assert covered | uncovered == targets, (
        f"{relative}: in no list {sorted(targets - covered - uncovered)}, "
        f"listed but not a target {sorted((covered | uncovered) - targets)}"
    )


def test_the_lists_name_exposure_documents() -> None:
    documents = {document_name(path) for path in exposure_documents(REPOSITORY_ROOT)}
    listed = set(COVERED_TARGETS) | set(UNCOVERED_TARGETS)
    assert listed <= documents, f"listed but not an exposure document: {sorted(listed - documents)}"


@pytest.mark.parametrize("relative", sorted(UNCOVERED_TARGETS))
def test_a_target_left_out_for_having_no_setter_has_none(relative: str) -> None:
    no_setter = [target for target, reason in UNCOVERED_TARGETS[relative].items() if reason == NO_SETTER]
    tools = [entry["tool"] for entry in setters(read_document(relative), no_setter)]
    assert not tools, f"{relative}: a target listed with no setter gives {tools}"


@pytest.mark.parametrize("relative", sorted(STAMPED_TOOLS))
def test_every_tool_that_takes_a_stamped_value_names_frame_timestamp_and_the_frame_rule(relative: str) -> None:
    violations = stamped_tool_violations(read_document(relative), STAMPED_TOOLS[relative])
    assert not violations, f"{relative}: " + "; ".join(violations)


@pytest.mark.parametrize("relative", sorted(STAMPED_TOOLS))
def test_a_document_with_tools_that_take_a_stamped_value_states_the_frame_rule(relative: str) -> None:
    assert states_the_frame_rule(read_document(relative)), (
        f'{relative}: no sentence of its instructions begins with "{FRAME_RULE}"'
    )


@pytest.mark.parametrize(
    ("relative", "tool"), [(relative, tool) for relative, tools in sorted(STAMPED_TOOLS.items()) for tool in sorted(tools)]
)
def test_a_tool_that_takes_a_stamped_value_takes_it_with_no_timestamp(relative: str, tool: str) -> None:
    violations = absent_timestamp_violations(read_document(relative), tool)
    assert not violations, f"{relative}: " + "; ".join(violations)


def test_the_stamped_tool_lists_name_exposure_documents() -> None:
    documents = {document_name(path) for path in exposure_documents(REPOSITORY_ROOT)}
    assert set(STAMPED_TOOLS) <= documents, f"listed but not an exposure document: {sorted(set(STAMPED_TOOLS) - documents)}"


_STAMPED_FIXTURE = """{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "arm", tag: "v1" },
  server: { title: "Arm", instructions: "Every robot. Frame rule: every pose names its frame and its timestamp, and a call may leave timestamp out for the latest time." },
  targets: {
    limb_motion: {
      contract: { name: "limb_motion", tag: "v1" },
      actions: [
        { member: "move_arm", tool: "robot.move_arm",
          description: "Move the arm. target gives frame and timestamp, by the frame rule. After the call, the arm stands still.",
          operation: "long_running", deadline_ms: 125000 },
      ],
      services: [
        { member: "check_arm_move", tool: "robot.check_arm_move",
          description: "Check a move. target gives frame and timestamp, by the frame rule.",
          operation: "read_only", deadline_ms: 5000 },
      ],
    },
  },
}
"""
_STAMPED_FIXTURE_TOOLS = ("robot.move_arm", "robot.check_arm_move")
_MOVE_ARM_SENTENCE = "Move the arm. target gives frame and timestamp, by the frame rule."


def test_a_document_whose_stamped_tools_name_their_fields_and_the_rule_passes() -> None:
    document = parse_json5(_STAMPED_FIXTURE)
    assert stamped_tool_violations(document, _STAMPED_FIXTURE_TOOLS) == []
    assert states_the_frame_rule(document)


@pytest.mark.parametrize(
    ("replacement", "missing"),
    [
        ("Move the arm. target gives timestamp, by the frame rule.", "`frame`"),
        ("Move the arm. target gives frame and source_timestamp, by the frame rule.", "`timestamp`"),
        ("Move the arm. target gives frame and timestamp, in the robot frame.", '"frame rule"'),
        ("Move the arm to a pose.", '`frame`, `timestamp`, "frame rule"'),
    ],
    ids=["no frame", "timestamp inside a word", "no frame rule", "none"],
)
def test_a_stamped_tool_that_does_not_name_a_field_or_the_rule_is_named(replacement: str, missing: str) -> None:
    assert _MOVE_ARM_SENTENCE in _STAMPED_FIXTURE
    document = parse_json5(_STAMPED_FIXTURE.replace(_MOVE_ARM_SENTENCE, replacement))
    assert stamped_tool_violations(document, _STAMPED_FIXTURE_TOOLS) == [
        f"robot.move_arm: its description does not name {missing}"
    ]


def test_a_listed_stamped_tool_that_the_document_does_not_hold_is_named() -> None:
    document = parse_json5(_STAMPED_FIXTURE)
    assert stamped_tool_violations(document, (*_STAMPED_FIXTURE_TOOLS, "robot.move_arms")) == [
        "robot.move_arms: not a tool of the document"
    ]


def test_a_stamped_tool_whose_call_may_leave_its_timestamp_out_passes() -> None:
    document = parse_json5(_STAMPED_FIXTURE)
    assert absent_timestamp_violations(document, "robot.move_arm") == []


@pytest.mark.parametrize(
    ("replacement", "spelling"),
    [
        ("Move the arm. target gives frame and timestamp 1970-01-01T00:00:00Z, by the frame rule.", "1970-01-01"),
        ("Move the arm. target gives frame and timestamp, by the frame rule, timestamp 0 for now.", "timestamp 0"),
        ("Move the arm. target gives frame and timestamp, by the frame rule, at the time 0.", "time 0"),
        ("Move the arm. target gives frame and timestamp, by the frame rule, and target_timestamp 0.", "target_timestamp 0"),
    ],
    ids=["rfc 3339", "timestamp 0", "time 0", "a field name"],
)
def test_a_stamped_tool_that_spells_the_time_0_is_named(replacement: str, spelling: str) -> None:
    document = parse_json5(_STAMPED_FIXTURE.replace(_MOVE_ARM_SENTENCE, replacement))
    assert absent_timestamp_violations(document, "robot.move_arm") == [
        f'robot.move_arm: its description spells the time 0 as "{spelling}"'
    ]


@pytest.mark.parametrize(
    "description",
    [
        "Move the arm. target gives frame and timestamp, by the frame rule, within 0.5 s.",
        "Move the arm. target gives frame and timestamp, by the frame rule; timeout 0 answers at once.",
    ],
    ids=["a decimal", "another word"],
)
def test_a_number_that_is_not_the_time_0_passes(description: str) -> None:
    document = parse_json5(_STAMPED_FIXTURE.replace(_MOVE_ARM_SENTENCE, description))
    assert absent_timestamp_violations(document, "robot.move_arm") == []


def test_instructions_that_do_not_say_a_call_may_leave_timestamp_out_are_named() -> None:
    document = parse_json5(_STAMPED_FIXTURE.replace(", and a call may leave timestamp out for the latest time", ""))
    assert absent_timestamp_violations(document, "robot.move_arm") == [
        'robot.move_arm: the instructions do not say "may leave timestamp out"'
    ]


@pytest.mark.parametrize(
    ("instructions", "states_it"),
    [
        ("Frame rule: every pose names its frame.", True),
        ("Every robot. Frame rule: every pose names its frame.", True),
        ("Every robot; Frame rule: every pose names its frame.", False),
        ("Every robot, by the frame rule: every pose names its frame.", False),
        ("Every robot.", False),
    ],
)
def test_the_frame_rule_opens_a_sentence_of_the_instructions(instructions: str, states_it: bool) -> None:
    assert states_the_frame_rule({"server": {"instructions": instructions}}) is states_it


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
        ("After the call, the lamp sits at the position of current.", True),
        ("Set it. After the call, the lamp sits at the position of current.", True),
        ("Set it?  After the call, the lamp sits at the position of current.", True),
        ("Set it!\nAfter the call, the lamp sits at the position of current.", True),
        ("Set it; After the call, the lamp sits at the position of current.", False),
        ("Set it: After the call, the lamp sits at the position of current.", False),
        ("Set it.After the call, the lamp sits at the position of current.", False),
        ("Answers with current, the effective position after the call.", False),
        ("", False),
    ],
)
def test_the_sentence_begins_a_sentence_with_its_capital_and_comma(description: str, has_it: bool) -> None:
    assert has_an_after_the_call_sentence(description) is has_it
