"""The robots' endpoint names no other endpoint.

The robots' document is served on the physical robots and in every
simulation, and a client can read it alone: a client of the physical robots,
where no simulated world's endpoint runs, or a client that drives the robots
for one task and is given no other endpoint. Such a client cannot call a tool
of another endpoint, and a text that names one tells it of a world it does
not have. So the robots' texts name no other endpoint and no tool of one. A
fact that joins the robots' endpoint to another lives in the texts of the
other endpoint: the simulated world's instructions say that a robot's name
there is its name on the robots' endpoint, how its world frame maps to the
robot frame, and that it never completes a task.

So the server title, the instructions and every description of a document
under ``robot/`` (``ROBOT_DIRECTORY``):

- name no tool of a document of the other endpoints, the families of
  ``OTHER_ENDPOINTS``, compared whole: ``scene.look`` is not a tool name
  inside ``scene.look_up``;
- say "endpoint" only as "this endpoint" or "this one endpoint", whatever
  the case.

The tool names come from the documents of the checkout, so a tool that a
document of the other endpoints adds is a name the robots' texts may not
hold from the moment it is added.

pytest collects it from the repository root without the workflow naming it.
It reads each document with `exposure_json5`, so a rule reads the document's
structure, whatever json5 form a key or a string takes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from exposure_families import FRAMEWORK, SIMULATION, texts, tool_names
from exposure_json5 import REPOSITORY_ROOT, document_name, exposure_documents, read_json5

# The directory of the robots' documents.
ROBOT_DIRECTORY = "robot"

# The families of the endpoints that a stack publishes beside the robots'.
OTHER_ENDPOINTS = (SIMULATION, FRAMEWORK)

# "endpoint" where it names this endpoint, which `named_endpoints` passes.
_THIS_ENDPOINT = re.compile(r"\bthis (?:one )?endpoint\b", re.IGNORECASE)
_ENDPOINT = re.compile(r"\bendpoints?\b", re.IGNORECASE)
# How many characters of the text a mention shows on each side of what it
# names.
_CONTEXT = 60


def robot_documents(root: Path) -> list[Path]:
    """The exposures under ``ROBOT_DIRECTORY`` in `root`."""
    return [path for path in exposure_documents(root) if path.relative_to(root).parts[0] == ROBOT_DIRECTORY]


def other_endpoint_tools(root: Path) -> frozenset[str]:
    """The name of every tool of the documents of ``OTHER_ENDPOINTS`` in
    `root`."""
    return frozenset(
        name for family in OTHER_ENDPOINTS for path in family.documents(root) for name in tool_names(read_json5(path))
    )


def _shown(text: str, match: re.Match[str]) -> str:
    """`match` in `text`, with ``_CONTEXT`` characters on each side."""
    return text[max(0, match.start() - _CONTEXT) : match.end() + _CONTEXT]


def named_tools(text: str, tools: frozenset[str]) -> list[str]:
    """Each tool of `tools` that `text` names, whole, with the text around
    it, in the order of the tool names."""
    found = []
    for tool in sorted(tools):
        match = re.search(rf"(?<![\w.]){re.escape(tool)}(?!\w)", text)
        if match:
            found.append(f'{tool}: "{_shown(text, match)}"')
    return found


def named_endpoints(text: str) -> list[str]:
    """Each "endpoint" of `text` that is not "this endpoint" or "this one
    endpoint", with the text around it."""
    this_endpoint_ends = {match.end() for match in _THIS_ENDPOINT.finditer(text)}
    return [
        f'an endpoint other than this one: "{_shown(text, match)}"'
        for match in _ENDPOINT.finditer(text)
        if match.end() not in this_endpoint_ends
    ]


def other_endpoint_mentions(path: Path, tools: frozenset[str]) -> list[str]:
    """Each text of `path` that names another endpoint or a tool of
    `tools`, with what it names; an empty list is the rule holding."""
    return [
        f"{part} names {name}"
        for part, text in texts(read_json5(path))
        for name in named_tools(text, tools) + named_endpoints(text)
    ]


def test_the_checkout_has_robot_documents_to_check() -> None:
    assert robot_documents(REPOSITORY_ROOT), f"no exposure under {ROBOT_DIRECTORY}/: the walk is broken"


def test_the_checkout_has_other_endpoint_tools_to_look_for() -> None:
    tools = other_endpoint_tools(REPOSITORY_ROOT)
    assert {"scene.get_robots_list", "workspace.stand_at", "stack.join"} <= tools, sorted(tools)


@pytest.mark.parametrize("path", robot_documents(REPOSITORY_ROOT), ids=document_name)
def test_robot_documents_name_no_other_endpoint(path: Path) -> None:
    mentions = other_endpoint_mentions(path, other_endpoint_tools(REPOSITORY_ROOT))
    assert not mentions, (
        f"{document_name(path)}: a client can read the robots' endpoint alone; say what joins it to another "
        "endpoint in the texts of the other endpoint: " + "; ".join(mentions)
    )


_ROBOT_DOCUMENT = """// A robots' exposure that names no other endpoint.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "robot_arm", tag: "v1" },
  server: {
    title: "Robots",
    instructions: "Every robot of the stack, by name on this one endpoint. Call robot.list first. This endpoint's tools take robot.",
  },
  call_record: {
    tool: "robot.recent_calls",
    description: "List the last calls of this endpoint that could change a robot's state.",
    keep: 200,
  },
  targets: {
    camera: {
      contract: { name: "rgb_camera", tag: "v1" },
      services: [
        { member: "look", tool: "camera.look",
          description: "Look through a camera of the robot.",
          operation: "read_only", deadline_ms: 2000 },
      ],
    },
  },
}
"""

_SIMULATION_DOCUMENT = """// A simulated world's exposure, whose tools the robots' texts may not name.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_scene", tag: "v1" },
  server: {
    title: "Scene (simulation only)",
    instructions: "This endpoint configures a simulated world. It has no effect on and no counterpart in the physical robot.",
  },
  targets: {
    scene: {
      contract: { name: "scene_manipulation", tag: "v1" },
      services: [
        { member: "look", tool: "scene.look",
          description: "Look at the simulated world.",
          operation: "read_only", deadline_ms: 2000 },
      ],
    },
  },
}
"""

_FRAMEWORK_DOCUMENT = """// A framework exposure, whose tools the robots' texts may not name.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "robot_stack", tag: "v1" },
  server: {
    title: "Robot stack (peppy framework)",
    instructions: "This endpoint controls the peppy framework that runs the robots: the stack of nodes, not the world and not the motion of a robot.",
  },
  targets: {
    stack: {
      daemon: { name: "stack_copies", tag: "v1" },
      services: [
        { member: "list", tool: "stack.list",
          description: "Report what this stack can add and remove.",
          operation: "read_only", deadline_ms: 2000 },
      ],
    },
  },
}
"""


def write_checkout(root: Path, robot_document: str) -> Path:
    """Writes `robot_document` under ``ROBOT_DIRECTORY`` in `root`, beside a
    document of each family of ``OTHER_ENDPOINTS``: the path of the robots'
    document."""
    SIMULATION.write_document(root, "scene.json5", _SIMULATION_DOCUMENT)
    FRAMEWORK.write_document(root, "stack.json5", _FRAMEWORK_DOCUMENT)
    (root / ROBOT_DIRECTORY).mkdir()
    path = root / ROBOT_DIRECTORY / "robot.json5"
    path.write_text(robot_document, encoding="utf-8")
    return path


def test_a_robot_document_that_names_no_other_endpoint_passes(tmp_path: Path) -> None:
    path = write_checkout(tmp_path, _ROBOT_DOCUMENT)
    assert robot_documents(tmp_path) == [path]
    assert other_endpoint_tools(tmp_path) == {"scene.look", "stack.list"}
    assert other_endpoint_mentions(path, other_endpoint_tools(tmp_path)) == []


@pytest.mark.parametrize(
    ("before", "after", "mention"),
    [
        (
            "Call robot.list first.",
            "Call robot.list first; their names are the names scene.look shows.",
            "instructions names scene.look",
        ),
        (
            "Look through a camera of the robot.",
            "Look through a camera of the robot; stack.list names the robots.",
            "description names stack.list",
        ),
        (
            "Call robot.list first.",
            "Call robot.list first, and prefer it over any simulation endpoint.",
            "instructions names an endpoint other than this one",
        ),
        (
            "could change a robot's state.",
            "could change a robot's state, not the calls of the framework's ENDPOINT.",
            "description names an endpoint other than this one",
        ),
        ('title: "Robots"', 'title: "Robots and their endpoints"', "title names an endpoint other than this one"),
    ],
    ids=[
        "simulation tool in the instructions",
        "framework tool in a description",
        "simulation endpoint in the instructions",
        "framework endpoint in a description, upper case",
        "endpoints in the title",
    ],
)
def test_a_text_that_names_another_endpoint_is_caught(tmp_path: Path, before: str, after: str, mention: str) -> None:
    assert before in _ROBOT_DOCUMENT
    path = write_checkout(tmp_path, _ROBOT_DOCUMENT.replace(before, after))
    mentions = other_endpoint_mentions(path, other_endpoint_tools(tmp_path))
    assert len(mentions) == 1, mentions
    assert mentions[0].startswith(mention), mentions[0]


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("Call scene.look.", ["scene.look"]),
        ("(scene.look)", ["scene.look"]),
        ("Call scene.look_up.", []),
        ("Call myscene.look.", []),
        ("Call my.scene.look.", []),
        ("Call robot.list.", []),
    ],
)
def test_a_tool_name_is_matched_whole(text: str, named: list[str]) -> None:
    assert [mention.split(":")[0] for mention in named_tools(text, frozenset({"scene.look"}))] == named


@pytest.mark.parametrize(
    "text",
    [
        "Every robot, on this one endpoint.",
        "This endpoint's instructions say it.",
        "The calls of THIS ENDPOINT.",
    ],
)
def test_this_endpoint_is_not_another_endpoint(text: str) -> None:
    assert named_endpoints(text) == []


def test_each_other_endpoint_is_named_once_with_its_text() -> None:
    mentions = named_endpoints("On this endpoint, not the simulated world's endpoint or the framework's endpoint.")
    assert len(mentions) == 2, mentions
    assert "simulated world's endpoint" in mentions[0], mentions[0]
    assert "framework's endpoint" in mentions[1], mentions[1]
