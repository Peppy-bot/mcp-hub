#!/usr/bin/env python3
"""Tests for openarm_v2_demo.py against a stand-in for the endpoint.

The stand-in is an http.server on an ephemeral port that answers the way
the server built into peppy does (peppy-mcp-runtime on rmcp's Streamable
HTTP transport, sessions off): the same HTTP refusals (406, 415, 405, 404),
the same per-request `_meta` and SEP-2243 header requirements, the same
task-handle and `tasks/get` shapes, the same error codes and HTTP statuses
for them. Its tasks advance one step per `tasks/get`, so no test waits on a
clock: the script's sleep is injected and recorded, never run.

    pytest    # from the repository root, as the pull request workflow runs it
"""

import base64
import http.server
import io
import json
import os
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openarm_v2_demo as demo  # noqa: E402

ENDPOINT_PATH = "/openarm_v2/v1/mcp"
TITLE = "OpenArm v2"
INSTRUCTIONS = "Two arms and two grippers, addressed by name."
TIMESTAMP = "2026-08-27T12:00:00Z"
# The goal fields of each tool and their JSON types, as the derived catalog
# publishes them (every field required, nothing else allowed).
TOOL_FIELDS = {
    demo.TOOL_MOVE_TO_READY: {"duration_s": "number"},
    demo.TOOL_MOVE_TO_HOME: {"duration_s": "number"},
    demo.TOOL_MOVE_ARM: {
        "arm_name": "string",
        "position": "array",
        "orientation": "array",
        "duration_s": "number",
        "plan_position_tolerance_m": "number",
        "plan_orientation_tolerance_rad": "number",
    },
    demo.TOOL_MOVE_GRIPPER: {"gripper_name": "string", "opening": "number", "max_effort": "number"},
}
DEADLINE_MS = {
    demo.TOOL_MOVE_TO_READY: 60000,
    demo.TOOL_MOVE_TO_HOME: 60000,
    demo.TOOL_MOVE_ARM: 60000,
    demo.TOOL_MOVE_GRIPPER: 30000,
}
TTL_GRACE_MS = 1000
STANDARD_HEADERS_VERSION = "2026-07-28"
HTTP_STATUS_BY_CODE = {-32600: 400, -32602: 400, -32020: 400, -32021: 400, -32601: 404}
# The transport's own refusal texts, before any JSON-RPC message is read.
NOT_ACCEPTABLE = "Not Acceptable: Client must accept both application/json and text/event-stream"
UNSUPPORTED_MEDIA_TYPE = "Unsupported Media Type: Content-Type must be application/json"


# --- Task views: what successive tasks/get calls report ---------------------


def working(message=None):
    view = {"status": "working"}
    if message is not None:
        view["statusMessage"] = message
    return view


def completed(outcome):
    """The completed payload: the tool result the runtime builds from the
    action's result."""
    result = {
        "resultType": "complete",
        "content": [{"type": "text", "text": json.dumps(outcome)}],
        "structuredContent": outcome,
        "isError": False,
    }
    return {"status": "completed", "result": result}


def failed(message):
    return {"status": "failed", "error": {"code": -32603, "message": message}}


def cancelled():
    return {"status": "cancelled"}


def confirmation_required(tool):
    """The parked view of a confirmation_required tool: one elicitation under
    the runtime's `confirmation` key."""
    request = {
        "method": "elicitation/create",
        "params": {"message": f"Confirm running `{tool}`", "requestedSchema": {"type": "object", "properties": {}}},
    }
    return {"status": "input_required", "inputRequests": {"confirmation": request}}


def posture_done():
    return completed({"success": True, "message": "both arms at the posture"})


def gripper_done(opening):
    return completed({"success": True, "message": "done", "final_opening": opening, "action_time": 0.4})


class Scenario:
    """What the stand-in does with the tasks it is asked to run: the views a
    task of each tool walks through, one per tasks/get (the last one repeats),
    the view a task settles on after tasks/cancel, and the poll interval the
    handles suggest."""

    def __init__(self, steps_by_tool=None, after_cancel=None, poll_interval_ms=0, tools=None):
        self.steps_by_tool = steps_by_tool or {}
        self.after_cancel = after_cancel or cancelled()
        self.poll_interval_ms = poll_interval_ms
        self.tools = tuple(TOOL_FIELDS) if tools is None else tuple(tools)

    def steps_for(self, tool):
        return list(self.steps_by_tool.get(tool, [working(), posture_done()]))


class StandInTask:
    def __init__(self, task_id, views):
        self.task_id = task_id
        self.views = views
        self.index = -1
        self.settled = None
        self.released = False

    def current_view(self):
        if self.settled is not None:
            return self.settled
        if self.index < 0:
            return working()
        return self.views[self.index]

    def is_terminal(self):
        return self.current_view()["status"] in demo.TERMINAL_STATUSES

    def is_parked(self):
        return self.index >= 0 and self.current_view()["status"] == demo.INPUT_REQUIRED and not self.released

    def advance(self):
        if self.settled is None and self.index < len(self.views) - 1:
            self.index += 1
            self.released = False

    def next_view(self):
        """One tasks/get: a parked or settled task repeats its view, any other
        moves one step."""
        if not self.is_parked() and not self.is_terminal():
            self.advance()
        return self.current_view()

    def answer(self, key, response, after_decline):
        """One entry of tasks/update: an accepted confirmation releases the
        task, which reports the next view from the next tasks/get on; any
        other answer settles it as declined."""
        parked_on = self.current_view().get("inputRequests", {})
        if not self.is_parked() or key not in parked_on:
            return
        if response.get("action") == "accept":
            self.released = True
        else:
            self.settled = after_decline

    def cancel(self, after_cancel):
        if not self.is_terminal():
            self.settled = after_cancel


class McpRefusal(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


Received = namedtuple("Received", "method params headers")


def decode_header_value(value):
    if value.startswith(demo.BASE64_HEADER_PREFIX) and value.endswith(demo.BASE64_HEADER_SUFFIX):
        inner = value[len(demo.BASE64_HEADER_PREFIX) : -len(demo.BASE64_HEADER_SUFFIX)]
        return base64.b64decode(inner).decode("utf-8")
    return value


JSON_TYPES = {"number": (int, float), "string": str, "array": list}


def argument_problems(tool, arguments):
    fields = TOOL_FIELDS[tool]
    problems = [f"`{name}` is required" for name in fields if name not in arguments]
    problems += [f"`{name}` is not a field of the goal" for name in arguments if name not in fields]
    for name, value in arguments.items():
        expected = fields.get(name)
        if expected and (isinstance(value, bool) or not isinstance(value, JSON_TYPES[expected])):
            problems.append(f"`{name}` is not a {expected}")
    return problems


class StandInHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self._method_not_allowed()

    def do_DELETE(self):
        self._method_not_allowed()

    def do_POST(self):
        if self.path != ENDPOINT_PATH:
            return self._text(404, "not found")
        accept = self.headers.get("Accept", "")
        if not ("application/json" in accept and "text/event-stream" in accept):
            return self._text(406, NOT_ACCEPTABLE)
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._text(415, UNSUPPORTED_MEDIA_TYPE)
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        message = json.loads(body)
        if "id" not in message:
            return self._accepted()
        request_id = message["id"]
        method = message.get("method", "")
        params = message.get("params") or {}
        meta = params.get("_meta") or {}
        headers = {name.lower(): value for name, value in self.headers.items()}
        with self.server.lock:
            self.server.received.append(Received(method, params, headers))
            try:
                self._check_protocol_metadata(method, meta)
                self._check_standard_headers(method, params)
                result = self._dispatch(method, params, meta)
            except McpRefusal as refusal:
                return self._json_error(request_id, refusal)
        return self._event_stream(request_id, result)

    # The checks rmcp's server transport runs before any handler, in its order.

    def _check_protocol_metadata(self, method, meta):
        header_version = self.headers.get(demo.HEADER_PROTOCOL_VERSION)
        meta_version = meta.get(demo.META_PROTOCOL_VERSION)
        if meta_version is None:
            requires_metadata = method == "server/discover" or (
                header_version is not None and header_version >= STANDARD_HEADERS_VERSION
            )
            if requires_metadata:
                missing = [
                    key for key in (demo.META_PROTOCOL_VERSION, demo.META_CLIENT_CAPABILITIES) if key not in meta
                ]
                raise McpRefusal(
                    -32602,
                    "Invalid params: request _meta is missing or has malformed required fields: " + ", ".join(missing),
                )
            return
        if header_version is None:
            raise McpRefusal(-32020, "request _meta protocolVersion requires MCP-Protocol-Version header")
        if header_version != meta_version:
            raise McpRefusal(
                -32020,
                f"MCP-Protocol-Version header ({header_version}) does not match "
                f"request _meta protocolVersion ({meta_version})",
            )

    def _check_standard_headers(self, method, params):
        header_version = self.headers.get(demo.HEADER_PROTOCOL_VERSION)
        if header_version is None or header_version < STANDARD_HEADERS_VERSION:
            return
        header_method = self.headers.get(demo.HEADER_METHOD)
        if header_method is None:
            raise McpRefusal(-32020, "missing required Mcp-Method header")
        if header_method != method:
            raise McpRefusal(-32020, f"Mcp-Method header `{header_method}` does not match body method `{method}`")
        name_field = demo.NAME_FIELD_BY_METHOD.get(method)
        expected = params.get(name_field) if name_field else None
        if expected is None:
            return
        header_name = self.headers.get(demo.HEADER_NAME)
        if header_name is None:
            raise McpRefusal(-32020, f"missing required Mcp-Name header for `{method}`")
        if decode_header_value(header_name) != expected:
            raise McpRefusal(-32020, f"Mcp-Name header `{header_name}` does not match body value `{expected}`")

    def _dispatch(self, method, params, meta):
        handlers = {
            "server/discover": self._discover,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
            "tasks/get": self._tasks_get,
            "tasks/update": self._tasks_update,
            "tasks/cancel": self._tasks_cancel,
        }
        handler = handlers.get(method)
        if handler is None:
            raise McpRefusal(-32601, "Method not found")
        return handler(params, meta)

    def _discover(self, params, meta):
        return {
            "resultType": "complete",
            "supportedVersions": [demo.PROTOCOL_VERSION],
            "capabilities": {"tools": {"listChanged": True}, "extensions": {demo.TASKS_EXTENSION: {}}},
            "instructions": INSTRUCTIONS,
            "ttlMs": 3600000,
            "cacheScope": "private",
            "_meta": {demo.META_SERVER_INFO: {"name": "openarm_v2", "version": "v1", "title": TITLE}},
        }

    def _tools_list(self, params, meta):
        tools = [
            {
                "name": tool,
                "description": f"Run {tool}.",
                "inputSchema": {
                    "type": "object",
                    "properties": {name: {"type": kind} for name, kind in TOOL_FIELDS[tool].items()},
                    "required": list(TOOL_FIELDS[tool]),
                    "additionalProperties": False,
                },
            }
            for tool in self.server.scenario.tools
        ]
        return {"tools": tools, "ttlMs": 3600000, "cacheScope": "private"}

    def _tools_call(self, params, meta):
        tool = params.get("name")
        if tool not in self.server.scenario.tools:
            raise McpRefusal(-32602, f"`{tool}` is not a tool of this exposure")
        capabilities = meta.get(demo.META_CLIENT_CAPABILITIES) or {}
        if demo.TASKS_EXTENSION not in (capabilities.get("extensions") or {}):
            raise McpRefusal(-32021, "Missing required client capability")
        problems = argument_problems(tool, params.get("arguments") or {})
        if problems:
            raise McpRefusal(-32602, f"invalid arguments for `{tool}`: " + "; ".join(problems))
        task_id = f"task-{len(self.server.tasks) + 1}"
        task = StandInTask(task_id, self.server.scenario.steps_for(tool))
        self.server.tasks[task_id] = task
        return {"resultType": "task", **self._task_fields(task, DEADLINE_MS[tool] + TTL_GRACE_MS), **working()}

    def _task(self, params):
        task = self.server.tasks.get(params.get("taskId"))
        if task is None:
            raise McpRefusal(-32602, f"unknown task: {params.get('taskId')}")
        return task

    def _task_fields(self, task, ttl_ms):
        return {
            "taskId": task.task_id,
            "createdAt": TIMESTAMP,
            "lastUpdatedAt": TIMESTAMP,
            "ttlMs": ttl_ms,
            "pollIntervalMs": self.server.scenario.poll_interval_ms,
        }

    def _tasks_get(self, params, meta):
        task = self._task(params)
        return {"resultType": "complete", **self._task_fields(task, 61000), **task.next_view()}

    def _tasks_update(self, params, meta):
        task = self._task(params)
        for key, response in (params.get("inputResponses") or {}).items():
            task.answer(key, response, cancelled())
        return {"resultType": "complete"}

    def _tasks_cancel(self, params, meta):
        self._task(params).cancel(self.server.scenario.after_cancel)
        return {"resultType": "complete"}

    # Responses, in the transport's shapes.

    def _event_stream(self, request_id, result):
        payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})
        # A comment line first, as the transport's keep-alive would send.
        body = f": keep-alive\n\ndata: {payload}\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, request_id, refusal):
        error = {"code": refusal.code, "message": refusal.message}
        body = json.dumps({"jsonrpc": "2.0", "id": request_id, "error": error}).encode("utf-8")
        self.send_response(HTTP_STATUS_BY_CODE[refusal.code])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status, text):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _accepted(self):
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self):
        body = b"Method Not Allowed"
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class StandInServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, scenario):
        super().__init__(("127.0.0.1", 0), StandInHandler)
        self.scenario = scenario
        self.received = []
        self.tasks = {}
        self.lock = threading.Lock()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}{ENDPOINT_PATH}"

    def calls(self, method):
        return [received for received in self.received if received.method == method]


class InterruptOnce:
    """A sleep that raises KeyboardInterrupt the first time it is called, as
    Ctrl-C during the wait between two polls would, and returns after that."""

    def __init__(self):
        self.interrupted = False

    def __call__(self, seconds):
        if not self.interrupted:
            self.interrupted = True
            raise KeyboardInterrupt


def proper_headers(method, name=None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        demo.HEADER_PROTOCOL_VERSION: demo.PROTOCOL_VERSION,
        demo.HEADER_METHOD: method,
    }
    if name is not None:
        headers[demo.HEADER_NAME] = name
    return headers


def proper_params(**params):
    params["_meta"] = {
        demo.META_PROTOCOL_VERSION: demo.PROTOCOL_VERSION,
        demo.META_CLIENT_CAPABILITIES: demo.CLIENT_CAPABILITIES,
    }
    return params


def raw_request(url, headers, body, method="POST"):
    """Status, headers, and body of one HTTP exchange, refusals included."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


class StandInCase(unittest.TestCase):
    def serve(self, scenario=None):
        server = StandInServer(scenario or Scenario())
        # A short poll so shutdown returns as soon as the last request is
        # answered rather than at the next half-second tick.
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def run_script(self, server, *arguments, sleep=None):
        out, err = io.StringIO(), io.StringIO()
        sleeps = []
        code = demo.main(["--endpoint", server.url, *arguments], out=out, err=err, sleep=sleep or sleeps.append)
        return code, out.getvalue(), err.getvalue(), sleeps


class ScriptTests(StandInCase):
    def test_tools_prints_what_the_endpoint_advertises(self):
        server = self.serve()
        code, out, err, _ = self.run_script(server, "tools")
        self.assertEqual(code, demo.EXIT_OK, err)
        self.assertIn(TITLE, out)
        self.assertIn(INSTRUCTIONS, out)
        for tool in TOOL_FIELDS:
            self.assertIn(tool, out)
        self.assertEqual([received.method for received in server.received], ["server/discover", "tools/list"])

    def test_a_move_completes_and_quotes_the_result(self):
        server = self.serve(Scenario({demo.TOOL_MOVE_TO_READY: [working(), working("planning"), posture_done()]}))
        code, out, err, sleeps = self.run_script(server, "move-to-ready", "--duration-s", "3")
        self.assertEqual(code, demo.EXIT_OK, err)
        self.assertIn("openarm.move_to_ready: completed: both arms at the posture", out)
        self.assertIn("planning", out)
        self.assertIn('"success": true', out)
        (call,) = server.calls("tools/call")
        self.assertEqual(call.params["name"], demo.TOOL_MOVE_TO_READY)
        self.assertEqual(call.params["arguments"], {"duration_s": 3.0})
        self.assertEqual(len(server.calls("tasks/get")), 3)
        self.assertEqual(sleeps, [0.0, 0.0, 0.0])

    def test_every_request_carries_the_stateless_shape(self):
        server = self.serve()
        code, _, err, _ = self.run_script(server, "move-gripper", "--gripper", "left_gripper", "--opening", "0")
        self.assertEqual(code, demo.EXIT_OK, err)
        for received in server.received:
            meta = received.params["_meta"]
            self.assertEqual(meta[demo.META_PROTOCOL_VERSION], demo.PROTOCOL_VERSION)
            self.assertIn(demo.TASKS_EXTENSION, meta[demo.META_CLIENT_CAPABILITIES]["extensions"])
            self.assertEqual(received.headers["mcp-protocol-version"], demo.PROTOCOL_VERSION)
            self.assertEqual(received.headers["mcp-method"], received.method)
            self.assertEqual(received.headers["accept"], "application/json, text/event-stream")
            self.assertTrue(received.headers["content-type"].startswith("application/json"))
        (call,) = server.calls("tools/call")
        self.assertEqual(call.headers["mcp-name"], demo.TOOL_MOVE_GRIPPER)
        for poll in server.calls("tasks/get"):
            self.assertEqual(poll.headers["mcp-name"], poll.params["taskId"])

    def test_a_refused_goal_is_a_failed_task_quoting_the_reason(self):
        reason = "the provider rejected the goal: opening 2 outside [0, 1]"
        server = self.serve(Scenario({demo.TOOL_MOVE_GRIPPER: [failed(reason)]}))
        code, out, _, _ = self.run_script(server, "move-gripper", "--gripper", "right_gripper", "--opening", "2")
        self.assertEqual(code, demo.EXIT_NOT_DONE)
        self.assertIn(f"openarm.move_gripper: failed: {reason}", out)

    def test_an_abandoned_goal_is_a_failed_task(self):
        server = self.serve(Scenario({demo.TOOL_MOVE_ARM: [working(), failed("the provider abandoned the goal")]}))
        code, out, _, _ = self.run_script(
            server,
            "move-arm",
            "--arm",
            "left_arm",
            "--position",
            "0.3",
            "0.2",
            "0.4",
            "--orientation",
            "0",
            "0",
            "0",
            "1",
        )
        self.assertEqual(code, demo.EXIT_NOT_DONE)
        self.assertIn("openarm.move_arm: failed: the provider abandoned the goal", out)
        (call,) = server.calls("tools/call")
        self.assertEqual(
            call.params["arguments"],
            {
                "arm_name": "left_arm",
                "position": [0.3, 0.2, 0.4],
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "duration_s": 0.0,
                "plan_position_tolerance_m": 0.0,
                "plan_orientation_tolerance_rad": 0.0,
            },
        )

    def test_a_move_the_robot_did_not_finish_is_reported_without_success(self):
        outcome = {"success": False, "message": "goal cancelled", "final_opening": 0.4, "action_time": 1.2}
        server = self.serve(Scenario({demo.TOOL_MOVE_GRIPPER: [completed(outcome)]}))
        code, out, _, _ = self.run_script(server, "move-gripper", "--gripper", "left_gripper", "--opening", "1")
        self.assertEqual(code, demo.EXIT_NOT_DONE)
        self.assertIn("openarm.move_gripper: completed without success: goal cancelled", out)
        self.assertIn('"final_opening": 0.4', out)

    def test_ctrl_c_cancels_the_move_in_flight_and_waits_for_it_to_settle(self):
        server = self.serve(Scenario({demo.TOOL_MOVE_TO_HOME: [working(), working(), posture_done()]}))
        code, out, _, _ = self.run_script(server, "move-to-home", sleep=InterruptOnce())
        self.assertEqual(code, demo.EXIT_CANCELLED)
        self.assertIn("openarm.move_to_home: cancelling task task-1", out)
        self.assertIn("openarm.move_to_home: cancelled", out)
        (cancel,) = server.calls("tasks/cancel")
        self.assertEqual(cancel.params["taskId"], "task-1")
        self.assertEqual(cancel.headers["mcp-name"], "task-1")

    def test_a_move_that_completes_despite_the_cancel_reads_completed(self):
        server = self.serve(Scenario(after_cancel=posture_done()))
        code, out, _, _ = self.run_script(server, "move-to-ready", sleep=InterruptOnce())
        self.assertEqual(code, demo.EXIT_OK)
        self.assertEqual(len(server.calls("tasks/cancel")), 1)
        self.assertIn("openarm.move_to_ready: completed: both arms at the posture", out)

    def test_a_confirmation_request_is_accepted_before_the_goal_runs(self):
        steps = [confirmation_required(demo.TOOL_MOVE_TO_READY), working(), posture_done()]
        server = self.serve(Scenario({demo.TOOL_MOVE_TO_READY: steps}))
        code, out, _, _ = self.run_script(server, "move-to-ready")
        self.assertEqual(code, demo.EXIT_OK)
        self.assertIn("confirming: confirmation", out)
        (update,) = server.calls("tasks/update")
        self.assertEqual(update.params["inputResponses"], {"confirmation": {"action": "accept"}})
        self.assertEqual(update.headers["mcp-name"], update.params["taskId"])
        methods = [received.method for received in server.received]
        self.assertEqual(methods, ["tools/call", "tasks/get", "tasks/update", "tasks/get", "tasks/get"])

    def test_the_poll_interval_the_server_suggests_is_honored(self):
        server = self.serve(Scenario({demo.TOOL_MOVE_TO_HOME: [working(), posture_done()]}, poll_interval_ms=250))
        code, _, _, sleeps = self.run_script(server, "move-to-home")
        self.assertEqual(code, demo.EXIT_OK)
        self.assertEqual(sleeps, [0.25, 0.25])

    def test_the_demo_runs_the_sequence_in_order(self):
        server = self.serve(Scenario({demo.TOOL_MOVE_GRIPPER: [gripper_done(0.0)]}))
        code, out, _, _ = self.run_script(server, "demo", "--duration-s", "2")
        self.assertEqual(code, demo.EXIT_OK)
        self.assertIn("demo complete", out)
        goals = [(call.params["name"], call.params["arguments"]) for call in server.calls("tools/call")]
        self.assertEqual(
            goals,
            [
                (demo.TOOL_MOVE_TO_READY, {"duration_s": 2.0}),
                (demo.TOOL_MOVE_GRIPPER, demo.gripper_goal("left_gripper", demo.GRIPPER_CLOSED)),
                (demo.TOOL_MOVE_GRIPPER, demo.gripper_goal("right_gripper", demo.GRIPPER_CLOSED)),
                (demo.TOOL_MOVE_GRIPPER, demo.gripper_goal("left_gripper", demo.GRIPPER_OPEN)),
                (demo.TOOL_MOVE_GRIPPER, demo.gripper_goal("right_gripper", demo.GRIPPER_OPEN)),
                (demo.TOOL_MOVE_TO_HOME, {"duration_s": 2.0}),
            ],
        )

    def test_the_demo_stops_at_the_first_move_the_robot_did_not_do(self):
        refusal = "the provider rejected the goal: gripper is already executing a move"
        server = self.serve(Scenario({demo.TOOL_MOVE_GRIPPER: [failed(refusal)]}))
        code, out, _, _ = self.run_script(server, "demo")
        self.assertEqual(code, demo.EXIT_NOT_DONE)
        self.assertIn("demo stopped at step 2", out)
        self.assertEqual(
            [call.params["name"] for call in server.calls("tools/call")],
            [demo.TOOL_MOVE_TO_READY, demo.TOOL_MOVE_GRIPPER],
        )

    def test_a_refused_request_exits_2_with_the_endpoint_message(self):
        server = self.serve(Scenario(tools=[demo.TOOL_MOVE_GRIPPER]))
        code, _, err, _ = self.run_script(server, "move-to-ready")
        self.assertEqual(code, demo.EXIT_ENDPOINT)
        self.assertIn("refused the request (-32602): `openarm.move_to_ready` is not a tool of this exposure", err)
        self.assertEqual(server.tasks, {})

    def test_an_unreachable_endpoint_exits_2(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        url = f"http://127.0.0.1:{port}{ENDPOINT_PATH}"
        out, err = io.StringIO(), io.StringIO()
        code = demo.main(["--endpoint", url, "move-to-home"], out=out, err=err, sleep=lambda seconds: None)
        self.assertEqual(code, demo.EXIT_ENDPOINT)
        self.assertIn(f"cannot reach {url}", err.getvalue())


class ClientTests(StandInCase):
    def test_without_the_tasks_capability_no_task_is_created(self):
        server = self.serve()
        client = demo.McpClient(server.url, client_capabilities={})
        with self.assertRaises(demo.ProtocolError) as refused:
            client.request("tools/call", {"name": demo.TOOL_MOVE_TO_READY, "arguments": {"duration_s": 1.0}})
        self.assertEqual(refused.exception.code, -32021)
        self.assertEqual(server.tasks, {})

    def test_an_unknown_tool_is_invalid_params_before_the_capability(self):
        server = self.serve()
        client = demo.McpClient(server.url, client_capabilities={})
        with self.assertRaises(demo.ProtocolError) as refused:
            client.request("tools/call", {"name": "openarm.dance", "arguments": {}})
        self.assertEqual(refused.exception.code, -32602)
        self.assertIn("`openarm.dance` is not a tool", refused.exception.message)

    def test_arguments_failing_the_schema_never_make_a_task(self):
        server = self.serve()
        client = demo.McpClient(server.url)
        with self.assertRaises(demo.ProtocolError) as refused:
            client.request(
                "tools/call", {"name": demo.TOOL_MOVE_GRIPPER, "arguments": {"gripper_name": "left_gripper"}}
            )
        self.assertEqual(refused.exception.code, -32602)
        self.assertIn("`opening` is required", refused.exception.message)
        self.assertEqual(server.tasks, {})

    def test_an_unknown_task_is_invalid_params(self):
        server = self.serve()
        client = demo.McpClient(server.url)
        for method in ("tasks/get", "tasks/cancel", "tasks/update"):
            with self.subTest(method=method), self.assertRaises(demo.ProtocolError) as refused:
                client.request(method, {"taskId": "nope"})
            self.assertEqual(refused.exception.code, -32602)

    def test_an_unknown_method_is_method_not_found(self):
        server = self.serve()
        with self.assertRaises(demo.ProtocolError) as refused:
            demo.McpClient(server.url).request("resources/list")
        self.assertEqual(refused.exception.code, -32601)

    def test_a_wrong_path_is_an_endpoint_error(self):
        server = self.serve()
        client = demo.McpClient(server.url.replace(ENDPOINT_PATH, "/mcp"))
        with self.assertRaises(demo.EndpointError) as refused:
            client.request("tools/list")
        self.assertIn("HTTP 404", str(refused.exception))


class WireTests(unittest.TestCase):
    def test_sse_events_yields_the_data_of_each_event(self):
        stream = [
            ": keep-alive",
            "",
            "id: 7",
            "retry: 3000",
            'data: {"a":',
            "data:1}",
            "",
            "",
            "event: message",
            "data: last",
        ]
        self.assertEqual(list(demo.sse_events(stream)), ['{"a":\n1}', "last"])

    def test_header_value_wraps_only_what_cannot_travel_bare(self):
        self.assertEqual(demo.header_value("openarm.move_arm"), "openarm.move_arm")
        self.assertEqual(demo.header_value("two words"), "two words")
        self.assertEqual(demo.header_value(""), "")
        wrapped = demo.header_value(" leading")
        self.assertTrue(wrapped.startswith(demo.BASE64_HEADER_PREFIX) and wrapped.endswith(demo.BASE64_HEADER_SUFFIX))
        self.assertEqual(decode_header_value(wrapped), " leading")
        self.assertEqual(decode_header_value(demo.header_value("café")), "café")
        self.assertEqual(decode_header_value(demo.header_value("=?base64?x?=")), "=?base64?x?=")


class StandInFidelityTests(StandInCase):
    """The request mistakes the real transport refuses, refused here the same
    way, so the tests above hold the script to the real endpoint's shape."""

    def setUp(self):
        self.server = self.serve()
        self.body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": proper_params()}).encode(
            "utf-8"
        )

    def test_a_proper_request_is_answered_over_an_event_stream(self):
        status, headers, body = raw_request(self.server.url, proper_headers("tools/list"), self.body)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/event-stream")
        self.assertTrue(body.startswith(b": keep-alive\n\ndata: "))

    def test_accept_must_name_both_media_types(self):
        for accept in ("application/json", "text/event-stream", "*/*"):
            headers = {**proper_headers("tools/list"), "Accept": accept}
            with self.subTest(accept=accept):
                status, _, body = raw_request(self.server.url, headers, self.body)
                self.assertEqual((status, body), (406, NOT_ACCEPTABLE.encode()))

    def test_the_body_must_be_json(self):
        headers = {**proper_headers("tools/list"), "Content-Type": "text/plain"}
        status, _, body = raw_request(self.server.url, headers, self.body)
        self.assertEqual((status, body), (415, UNSUPPORTED_MEDIA_TYPE.encode()))

    def test_only_post_is_allowed(self):
        for method in ("GET", "DELETE"):
            with self.subTest(method=method):
                status, headers, _ = raw_request(self.server.url, proper_headers("tools/list"), None, method=method)
                self.assertEqual((status, headers["Allow"]), (405, "POST"))

    def test_a_notification_is_accepted_and_ignored(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode("utf-8")
        status, _, payload = raw_request(self.server.url, proper_headers("notifications/initialized"), body)
        self.assertEqual((status, payload), (202, b""))
        self.assertEqual(self.server.received, [])

    def test_the_standard_headers_are_required_under_2026_07_28(self):
        without_method = {
            name: value for name, value in proper_headers("tools/list").items() if name != demo.HEADER_METHOD
        }
        status, _, body = raw_request(self.server.url, without_method, self.body)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], {"code": -32020, "message": "missing required Mcp-Method header"})

        call = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": proper_params(name=demo.TOOL_MOVE_TO_HOME, arguments={"duration_s": 1}),
            }
        ).encode("utf-8")
        status, _, body = raw_request(self.server.url, proper_headers("tools/call"), call)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], -32020)
        self.assertIn("Mcp-Name", json.loads(body)["error"]["message"])
        self.assertEqual(self.server.tasks, {})

    def test_the_request_meta_is_required_under_2026_07_28(self):
        bare = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}}).encode("utf-8")
        status, _, body = raw_request(self.server.url, proper_headers("tools/list"), bare)
        self.assertEqual(status, 400)
        error = json.loads(body)["error"]
        self.assertEqual(error["code"], -32602)
        self.assertIn(demo.META_PROTOCOL_VERSION, error["message"])
        self.assertIn(demo.META_CLIENT_CAPABILITIES, error["message"])

    def test_the_meta_version_needs_the_matching_header(self):
        without_version = {
            name: value for name, value in proper_headers("tools/list").items() if name != demo.HEADER_PROTOCOL_VERSION
        }
        status, _, body = raw_request(self.server.url, without_version, self.body)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], -32020)
        mismatched = {**proper_headers("tools/list"), demo.HEADER_PROTOCOL_VERSION: "2025-11-25"}
        status, _, body = raw_request(self.server.url, mismatched, self.body)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"]["code"], -32020)

    def test_a_missing_tasks_capability_is_400_json_before_any_task(self):
        params = proper_params(name=demo.TOOL_MOVE_TO_HOME, arguments={"duration_s": 1})
        params["_meta"][demo.META_CLIENT_CAPABILITIES] = {}
        call = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": params}).encode("utf-8")
        status, headers, body = raw_request(self.server.url, proper_headers("tools/call", demo.TOOL_MOVE_TO_HOME), call)
        self.assertEqual((status, headers["Content-Type"]), (400, "application/json"))
        self.assertEqual(json.loads(body)["error"]["code"], -32021)
        self.assertEqual(self.server.tasks, {})

    def test_an_unknown_method_is_404_json(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 5, "method": "prompts/list", "params": proper_params()}).encode(
            "utf-8"
        )
        status, headers, payload = raw_request(self.server.url, proper_headers("prompts/list"), body)
        self.assertEqual((status, headers["Content-Type"]), (404, "application/json"))
        self.assertEqual(json.loads(payload)["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
