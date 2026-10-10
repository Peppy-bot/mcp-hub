"""The simulated world's endpoint and the framework's endpoint name no robot
model.

A world never names a robot model and never depends on one: a world and its
work surfaces say nothing of which robots can work there,
``workspace.stand_at`` stands any robot at a surface by its stance, and
``workspace.describe`` and ``workspace.check`` measure whether that robot can
work it. The framework's endpoint adds the robots that the launcher's scope
names, with the description the scope gives each, so one document serves
every launcher. So every document under ``simulation/`` and under
``framework/`` (``MODEL_FREE_FAMILIES``) describes robots in general terms
("a standing robot", "a mounted robot", "a robot option"): its server title,
its instructions and every description of a topic, a service, an action, a
picture tool or the call record name no robot model and no field that lists
robots (``ROBOT_LISTING_FIELDS``). A model is named by its id or by its
label, compared without case.

mcp-hub does not read the simulation's catalogue, so ``ROBOT_MODELS`` holds
the ids and the labels of the robot models the hubs simulate: the robots of
Waldo's catalogue (its ``robots.json``). The change that brings a new model
into that catalogue adds it here.

pytest collects it from the repository root without the workflow naming it.
It reads each document with `exposure_json5`, so a rule reads the document's
structure, whatever json5 form a key or a string takes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exposure_families import FRAMEWORK, SIMULATION, Family, descriptions
from exposure_json5 import REPOSITORY_ROOT, document_name, read_json5

# The robot models the hubs simulate, each by its id and its label.
ROBOT_MODELS = (
    ("openarm_v1", "OpenArm v1"),
    ("openarm_v2", "OpenArm v2"),
    ("so101", "SO-101"),
)

# The fields that list robots, which a world never carries.
ROBOT_LISTING_FIELDS = ("workable_by", "workableBy")

# The families whose documents name no robot model.
MODEL_FREE_FAMILIES = (SIMULATION, FRAMEWORK)

# Every name the texts may not hold, in lower case.
_FORBIDDEN = tuple(
    name.lower() for model in ROBOT_MODELS for name in model
) + tuple(field.lower() for field in ROBOT_LISTING_FIELDS)


def model_free_documents(root: Path) -> list[Path]:
    """The exposures under the directory of each family of
    ``MODEL_FREE_FAMILIES`` in `root`, family by family."""
    return [path for family in MODEL_FREE_FAMILIES for path in family.documents(root)]


def named_in(text: str) -> list[str]:
    """The robot model names and robot-listing fields `text` holds,
    whatever the case, each once in the order of ``_FORBIDDEN``."""
    lowered = text.lower()
    return [name for name in _FORBIDDEN if name in lowered]


def texts(document: dict) -> list[tuple[str, str]]:
    """Each text of `document` a model reads, named: its server title, its
    instructions and every description."""
    server = document.get("server", {})
    named = [("title", server.get("title", "")), ("instructions", server.get("instructions", ""))]
    return named + [("description", description) for description in descriptions(document)]


def model_mentions(path: Path) -> list[str]:
    """Each text of `path` that names a robot model or a field that lists
    robots, with what it names; an empty list is the rule holding."""
    found = []
    for part, text in texts(read_json5(path)):
        names = named_in(text)
        if names:
            found.append(f'{part} names {", ".join(names)}: "{text[:120]}"')
    return found


@pytest.mark.parametrize("path", model_free_documents(REPOSITORY_ROOT), ids=document_name)
def test_simulation_and_framework_documents_name_no_robot_model(path: Path) -> None:
    mentions = model_mentions(path)
    assert not mentions, (
        f"{document_name(path)}: a world and the framework name no robot model; describe a robot by "
        "its stance, and leave the robots a stack can add to the launcher's scope: " + "; ".join(mentions)
    )


_SIMULATION_DOCUMENT = """// A simulation-only exposure that names no robot model.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "sim_workspace", tag: "v1" },
  server: {
    title: "Workspace (simulation only)",
    instructions: "This endpoint configures a simulated world. It has no effect on and no counterpart in the physical robot. A standing robot rests on its base; a mounted robot is fixed where it is placed.",
  },
  targets: {
    workspace: {
      contract: { name: "scene_workspace", tag: "v1" },
      actions: [
        { member: "stand_at", tool: "workspace.stand_at",
          description: "Stand a simulated robot at a work surface by its stance.",
          operation: "long_running", deadline_ms: 30000 },
      ],
    },
  },
}
"""

_FRAMEWORK_DOCUMENT = """// A framework exposure that names no robot model.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "robot_stack", tag: "v1" },
  server: {
    title: "Robot stack (peppy framework)",
    instructions: "This endpoint controls the peppy framework that runs the robots: the stack of nodes, not the world and not the motion of a robot. stack.list reports the robot options of the stack.",
  },
  targets: {
    stack: {
      daemon: { name: "stack_copies", tag: "v1" },
      actions: [
        { member: "join", tool: "stack.join",
          description: "Add a robot of an option to the stack.",
          operation: "long_running", progress_timeout_ms: 660000 },
      ],
    },
  },
}
"""

# The document of each model-free family that the tests below edit.
_DOCUMENTS = {SIMULATION: _SIMULATION_DOCUMENT, FRAMEWORK: _FRAMEWORK_DOCUMENT}


@pytest.mark.parametrize("family", MODEL_FREE_FAMILIES, ids=lambda family: family.directory)
def test_a_document_that_names_no_model_passes(tmp_path: Path, family: Family) -> None:
    path = family.write_document(tmp_path, "document.json5", _DOCUMENTS[family])
    assert model_free_documents(tmp_path) == [path]
    assert model_mentions(path) == []


@pytest.mark.parametrize(
    ("family", "before", "after", "part", "name"),
    [
        (
            SIMULATION,
            "Stand a simulated robot at a work surface by its stance.",
            "Stand a simulated robot, such as openarm_v2, at a work surface.",
            "description",
            "openarm_v2",
        ),
        (
            SIMULATION,
            "a mounted robot is fixed where it is placed.",
            "a mounted robot, such as the SO-101, is fixed where it is placed.",
            "instructions",
            "so-101",
        ),
        (
            SIMULATION,
            "Stand a simulated robot at a work surface by its stance.",
            "Stand a simulated robot at a surface its workable_by names.",
            "description",
            "workable_by",
        ),
        (SIMULATION, "Workspace (simulation only)", "OPENARM V1 workspace (simulation only)", "title", "openarm v1"),
        (
            FRAMEWORK,
            "Add a robot of an option to the stack.",
            "Add a robot of an option, such as an SO-101 on a table, to the stack.",
            "description",
            "so-101",
        ),
        (
            FRAMEWORK,
            "stack.list reports the robot options of the stack.",
            "stack.list reports the robot options of the stack, such as openarm_v2.",
            "instructions",
            "openarm_v2",
        ),
        (FRAMEWORK, "Robot stack (peppy framework)", "OpenArm v1 stack (peppy framework)", "title", "openarm v1"),
    ],
    ids=[
        "simulation model id in a description",
        "simulation model label in the instructions",
        "simulation listing field",
        "simulation title",
        "framework model label in a description",
        "framework model id in the instructions",
        "framework title",
    ],
)
def test_a_text_that_names_a_model_is_caught(
    tmp_path: Path, family: Family, before: str, after: str, part: str, name: str
) -> None:
    assert before in _DOCUMENTS[family]
    document = _DOCUMENTS[family].replace(before, after)
    mentions = model_mentions(family.write_document(tmp_path, "document.json5", document))
    assert len(mentions) == 1, mentions
    assert mentions[0].startswith(f"{part} names {name}"), mentions[0]


def test_every_model_is_named_by_its_id_and_its_label() -> None:
    for model_id, label in ROBOT_MODELS:
        assert named_in(f"a {model_id} here") == [model_id.lower()]
        assert label.lower() in named_in(f"the {label.upper()} there")
