"""The framework family, and the kind of target that each family holds.

A call to the framework, to the simulated world and to the robot each goes
to its own endpoint, so the user and the model can always tell where a call
goes. Two rules of `exposure_families` hold this, read from every
``mcp_exposure/v1`` document in the checkout:

- every document under ``framework/`` says what it is, by the wording of
  ``FRAMEWORK``: the server title ends with "(peppy framework)", the
  instructions open with its sentence, and every ``description`` of every
  topic, service and action, and of the call record, contains the word
  "stack";
- a ``framework/`` document names daemon interfaces only, and only a
  ``framework/`` document names one: a ``robot/``, ``simulation/`` or
  ``recording/`` document names contracts only.

`test_no_simulation_ground_truth.py` applies the wording of ``SIMULATION``.

pytest collects it from the repository root without the workflow naming it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exposure_families import FRAMEWORK, TargetError, TargetKind, TargetSource, target_kind_violations, target_sources
from exposure_json5 import REPOSITORY_ROOT, document_name, exposure_documents, parse_json5


def test_the_checkout_has_framework_documents_to_check() -> None:
    assert FRAMEWORK.documents(REPOSITORY_ROOT), "no exposure under framework/: the walk is broken"


@pytest.mark.parametrize("path", FRAMEWORK.documents(REPOSITORY_ROOT), ids=document_name)
def test_framework_documents_say_what_they_are(path: Path) -> None:
    violations = FRAMEWORK.wording_violations(path)
    assert not violations, f"{document_name(path)}: " + "; ".join(violations)


@pytest.mark.parametrize("path", exposure_documents(REPOSITORY_ROOT), ids=document_name)
def test_every_target_names_the_kind_its_family_holds(path: Path) -> None:
    violations = target_kind_violations(path, REPOSITORY_ROOT)
    assert not violations, f"{document_name(path)}: " + "; ".join(violations)


_COMPLIANT = """// A framework exposure that follows every rule.
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "robot_stack", tag: "v1" },
  server: {
    title: "Robot stack (peppy framework)",
    instructions: "This endpoint controls the peppy framework that runs the robots: the stack of nodes, not the world and not the motion of a robot. Change rule: one change at a time.",
  },
  call_record: {
    tool: "stack.recent_calls",
    description: "The last calls that could change the stack.",
    keep: 200,
  },
  targets: {
    stack: {
      daemon: { name: "stack_copies", tag: "v1" },
      services: [
        { member: "list", tool: "stack.list", description: "Report what this Stack can add and remove.",
          operation: "read_only", deadline_ms: 5000 },
      ],
      actions: [
        { member: "join", tool: "stack.join",
          description: "Add a robot to the stack. After the call, its software runs.",
          operation: "long_running", progress_timeout_ms: 660000 },
      ],
    },
  },
}
"""
_TITLE = "Robot stack (peppy framework)"
_OPENING = "This endpoint controls the peppy framework that runs the robots: the stack of nodes, not the world and not the motion of a robot. "
_LIST_DESCRIPTION = "Report what this Stack can add and remove."
_JOIN_DESCRIPTION = "Add a robot to the stack. After the call, its software runs."
_DAEMON_SOURCE = 'daemon: { name: "stack_copies", tag: "v1" }'


def test_a_framework_document_that_follows_every_rule_passes(tmp_path: Path) -> None:
    path = FRAMEWORK.write_document(tmp_path, "robot_stack.json5", _COMPLIANT)
    assert FRAMEWORK.documents(tmp_path) == [path]
    assert FRAMEWORK.wording_violations(path) == []
    assert target_kind_violations(path, tmp_path) == []


@pytest.mark.parametrize(
    ("part", "before", "after"),
    [
        ("title", _TITLE, "Robot stack"),
        ("instructions", _OPENING, "This endpoint adds robots to the stack. "),
        ("description", _JOIN_DESCRIPTION, "Add a robot. After the call, its software runs."),
    ],
    ids=["title", "instructions", "description"],
)
def test_a_framework_document_missing_a_wording_part_is_caught(
    tmp_path: Path, part: str, before: str, after: str
) -> None:
    assert before in _COMPLIANT
    path = FRAMEWORK.write_document(tmp_path, "robot_stack.json5", _COMPLIANT.replace(before, after))
    violations = FRAMEWORK.wording_violations(path)
    assert len(violations) == 1, violations
    assert violations[0].startswith(part), violations[0]


def test_a_framework_document_missing_every_wording_part_names_each(tmp_path: Path) -> None:
    document = _COMPLIANT
    document = document.replace(_TITLE, "Robot options")
    document = document.replace(_OPENING, "")
    document = document.replace("The last calls that could change the stack.", "The last calls.")
    document = document.replace(_LIST_DESCRIPTION, "Report what can be added.")
    document = document.replace(_JOIN_DESCRIPTION, "Add a robot.")
    path = FRAMEWORK.write_document(tmp_path, "robot_stack.json5", document)
    violations = FRAMEWORK.wording_violations(path)
    assert [violation.split(" ", 1)[0] for violation in violations] == [
        "title",
        "instructions",
        "description",
        "description",
        "description",
    ]
    assert violations[2] == 'description "The last calls." must contain "stack"'


def test_the_framework_word_is_matched_whole_and_case_insensitively() -> None:
    assert FRAMEWORK.has_a_description_word("Report what this Stack can add.")
    assert FRAMEWORK.has_a_description_word("THE STACK of nodes")
    assert not FRAMEWORK.has_a_description_word("a stacked tray")
    assert not FRAMEWORK.has_a_description_word("two stacks of plates")
    assert not FRAMEWORK.has_a_description_word("the interface stack_copies")


def test_a_contract_target_under_framework_is_caught(tmp_path: Path) -> None:
    document = _COMPLIANT.replace(_DAEMON_SOURCE, 'contract: { name: "postures", tag: "v1" }')
    path = FRAMEWORK.write_document(tmp_path, "robot_stack.json5", document)
    assert target_kind_violations(path, tmp_path) == [
        "target `stack` names the contract `postures`: a document under framework/ names daemon interfaces only"
    ]


@pytest.mark.parametrize("directory", ["robot", "simulation", "recording"])
def test_a_daemon_target_outside_framework_is_caught(tmp_path: Path, directory: str) -> None:
    (tmp_path / directory).mkdir()
    path = tmp_path / directory / "robot_stack.json5"
    path.write_text(_COMPLIANT, encoding="utf-8")
    assert exposure_documents(tmp_path) == [path]
    assert target_kind_violations(path, tmp_path) == [
        "target `stack` names the daemon interface `stack_copies`: only a document under framework/ names a "
        "daemon interface"
    ]


def test_each_target_of_the_wrong_kind_is_named_alone(tmp_path: Path) -> None:
    # A framework document with a second target, on a contract: only that one
    # breaks the rule.
    second = 'targets: {\n    arms: { contract: { name: "postures", tag: "v1" }, actions: [] },'
    document = _COMPLIANT.replace("targets: {", second)
    assert document != _COMPLIANT
    path = FRAMEWORK.write_document(tmp_path, "robot_stack.json5", document)
    assert [violation.split(":", 1)[0] for violation in target_kind_violations(path, tmp_path)] == [
        "target `arms` names the contract `postures`"
    ]


def test_each_target_is_read_by_the_kind_of_its_source() -> None:
    document = """{
      targets: {
        arms: { "contract": { name: "postures", tag: "v1", sha256: "ab" } },
        stack: { 'daemon': { "name": 'stack_copies', tag: "v1" } },
      },
    }"""
    assert target_sources(parse_json5(document)) == {
        "arms": TargetSource(TargetKind.CONTRACT, "postures"),
        "stack": TargetSource(TargetKind.DAEMON, "stack_copies"),
    }


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("{ services: [] }", "names neither a contract nor a daemon interface"),
        (
            '{ contract: { name: "postures", tag: "v1" }, daemon: { name: "stack_copies", tag: "v1" } }',
            "names both a contract and a daemon interface",
        ),
    ],
    ids=["neither", "both"],
)
def test_a_target_that_does_not_name_exactly_one_source_is_refused(target: str, message: str) -> None:
    with pytest.raises(TargetError, match=f"target `stack` {message}"):
        target_sources(parse_json5(f"{{ targets: {{ stack: {target} }} }}"))
