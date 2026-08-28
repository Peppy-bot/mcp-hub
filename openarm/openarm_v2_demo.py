#!/usr/bin/env python3
"""Drive an OpenArm v2 through the MCP server built into peppy.

The server serves the `openarm_v2:v1` exposure beside this file at
http://127.0.0.1:8900/openarm_v2/v1/mcp whenever the `openarm_v2` launcher
runs with its `mcp_commander` option:

    peppy stack launch openarm_v2 --with=mujoco,mcp_commander

This file talks MCP (revision 2026-07-28) over Streamable HTTP with nothing
but the standard library, in the stateless shape that server speaks: every
request is one POST carrying its own protocol version and client
capabilities, every answer is one JSON-RPC message, and a move is an MCP task
polled through `tasks/get` until it settles.

    openarm_v2_demo.py tools
    openarm_v2_demo.py move-to-ready --duration-s 4
    openarm_v2_demo.py move-gripper --gripper left_gripper --opening 0
    openarm_v2_demo.py move-arm --arm right_arm --position 0.3 -0.2 0.4 --orientation 0 0.7071068 0 0.7071068
    openarm_v2_demo.py move-to-home --duration-s 4
    openarm_v2_demo.py demo

Exit codes: 0 the move completed and the robot reported success; 1 the robot
did not do it (a refused goal, a failed move, or a completed move reporting
no success); 2 the endpoint could not be reached or refused the request;
130 the move was cancelled (Ctrl-C cancels the move in flight and waits for
the robot to settle).
"""

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "http://127.0.0.1:8900/openarm_v2/v1/mcp"

# --- The protocol the server speaks -----------------------------------------

PROTOCOL_VERSION = "2026-07-28"
TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
# Declared on every request: the server retains nothing between requests, and
# it creates a task only for a client that declares the tasks extension.
CLIENT_CAPABILITIES = {"extensions": {TASKS_EXTENSION: {}}}

# SEP-2243: under a 2026-07-28 protocol version the server requires the
# method in a header and, for the methods below, the body value it routes on.
HEADER_PROTOCOL_VERSION = "MCP-Protocol-Version"
HEADER_METHOD = "Mcp-Method"
HEADER_NAME = "Mcp-Name"
NAME_FIELD_BY_METHOD = {
    "tools/call": "name",
    "tasks/get": "taskId",
    "tasks/update": "taskId",
    "tasks/cancel": "taskId",
}
BASE64_HEADER_PREFIX = "=?base64?"
BASE64_HEADER_SUFFIX = "?="

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
INPUT_REQUIRED = "input_required"
DEFAULT_POLL_INTERVAL_S = 0.5
REQUEST_TIMEOUT_S = 30.0

# --- The surface the exposure publishes --------------------------------------

TOOL_MOVE_TO_READY = "openarm.move_to_ready"
TOOL_MOVE_TO_HOME = "openarm.move_to_home"
TOOL_MOVE_ARM = "openarm.move_arm"
TOOL_MOVE_GRIPPER = "openarm.move_gripper"
ARM_NAMES = ("left_arm", "right_arm")
GRIPPER_NAMES = ("left_gripper", "right_gripper")
# Openings as fractions of full jaw travel, the contract's unit.
GRIPPER_CLOSED = 0.0
GRIPPER_OPEN = 1.0
DEMO_POSTURE_DURATION_S = 4.0

EXIT_OK = 0
EXIT_NOT_DONE = 1
EXIT_ENDPOINT = 2
EXIT_CANCELLED = 130


class EndpointError(Exception):
    """The endpoint could not be reached, or refused the HTTP request itself."""


class ProtocolError(Exception):
    """The endpoint answered the request with a JSON-RPC error."""

    def __init__(self, code, message):
        super().__init__(f"({code}) {message}")
        self.code = code
        self.message = message


def sse_events(lines):
    """Yield the data of each event of a text/event-stream, one string each.

    `lines` yields the stream's lines without their terminators. Per the
    event-stream format, `data:` lines accumulate (joined by newlines) and a
    blank line dispatches the event; comment lines (a leading colon) and the
    other fields (`id`, `event`, `retry`) carry nothing this client reads. An
    event with no data dispatches nothing.
    """
    data = []
    for line in lines:
        if line == "":
            if data:
                yield "\n".join(data)
            data = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
    if data:
        yield "\n".join(data)


def header_value(value):
    """The SEP-2243 header form of a body value: bare when it can travel as an
    HTTP header value, Base64-wrapped when it cannot (leading or trailing
    blanks, control or non-ASCII characters, or a value that already looks
    like the wrapper)."""
    needs_wrapping = (
        value.startswith((" ", "\t"))
        or value.endswith((" ", "\t"))
        or any(not 0x20 <= ord(char) <= 0x7E for char in value)
        or (value.startswith(BASE64_HEADER_PREFIX) and value.endswith(BASE64_HEADER_SUFFIX))
    )
    if not needs_wrapping:
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"{BASE64_HEADER_PREFIX}{encoded}{BASE64_HEADER_SUFFIX}"


class McpClient:
    """One endpoint, one request at a time, no session."""

    def __init__(self, endpoint, client_capabilities=CLIENT_CAPABILITIES, timeout_s=REQUEST_TIMEOUT_S):
        self.endpoint = endpoint
        self.client_capabilities = client_capabilities
        self.timeout_s = timeout_s
        self._last_id = 0

    def request(self, method, params=None):
        """POST one JSON-RPC request and return its result.

        Raises ProtocolError for a JSON-RPC error and EndpointError when the
        endpoint cannot be reached or refuses the HTTP request itself.
        """
        self._last_id += 1
        request_id = self._last_id
        params = dict(params or {})
        params["_meta"] = {
            META_PROTOCOL_VERSION: PROTOCOL_VERSION,
            META_CLIENT_CAPABILITIES: self.client_capabilities,
        }
        body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            HEADER_PROTOCOL_VERSION: PROTOCOL_VERSION,
            HEADER_METHOD: method,
        }
        name_field = NAME_FIELD_BY_METHOD.get(method)
        if name_field is not None:
            headers[HEADER_NAME] = header_value(str(params[name_field]))
        http_request = urllib.request.Request(self.endpoint, data=body.encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_s) as response:
                message = self._answer(response, request_id, method)
        except urllib.error.HTTPError as error:
            message = self._refusal(error)
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise EndpointError(f"cannot reach {self.endpoint}: {reason}") from error
        if "error" in message:
            error = message["error"]
            raise ProtocolError(error.get("code"), error.get("message", ""))
        return message.get("result", {})

    def _answer(self, response, request_id, method):
        """The JSON-RPC message answering `request_id` in a 2xx response: the
        server answers over an event stream, read only as far as the answer."""
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            return json.loads(response.read().decode("utf-8"))
        if not content_type.startswith("text/event-stream"):
            raise EndpointError(
                f"{self.endpoint} answered HTTP {response.status} with {content_type or 'no content type'}"
            )
        lines = (raw.decode("utf-8").rstrip("\r\n") for raw in response)
        for data in sse_events(lines):
            message = json.loads(data)
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        raise EndpointError(f"{self.endpoint} closed the stream without answering {method}")

    def _refusal(self, error):
        """The JSON-RPC error a non-2xx response carries, or an EndpointError
        when the refusal is the HTTP layer's own (a wrong header, a wrong
        method, a wrong path)."""
        content_type = error.headers.get("Content-Type", "") if error.headers else ""
        body = error.read().decode("utf-8", "replace")
        if content_type.startswith("application/json"):
            try:
                message = json.loads(body)
            except ValueError:
                message = None
            if isinstance(message, dict) and "error" in message:
                return message
        detail = body.strip() or error.reason
        raise EndpointError(f"{self.endpoint} answered HTTP {error.code}: {detail}") from error


# --- Driving one move --------------------------------------------------------


def run_move(client, tool, arguments, out, sleep):
    """Start `tool` as a task, follow it to its end, report; returns the exit
    code. Ctrl-C while the move runs asks the server to cancel it, then keeps
    following it: the robot's own terminal outcome decides."""
    handle = client.request("tools/call", {"name": tool, "arguments": arguments})
    task_id = handle["taskId"]
    print(f"{tool}: task {task_id} {handle.get('status')}", file=out)
    try:
        task = follow_task(client, task_id, handle, out, sleep)
    except KeyboardInterrupt:
        print(f"{tool}: cancelling task {task_id}", file=out)
        client.request("tasks/cancel", {"taskId": task_id})
        task = follow_task(client, task_id, handle, out, sleep)
    return report_outcome(tool, task, out)


def follow_task(client, task_id, task, out, sleep):
    """Poll `tasks/get` until the task settles, at the interval the server
    suggests, accepting a confirmation the task parks on; returns the
    terminal task."""
    seen = (task.get("status"), task.get("statusMessage"))
    while seen[0] not in TERMINAL_STATUSES:
        if seen[0] == INPUT_REQUIRED:
            answers = {key: {"action": "accept"} for key in task.get("inputRequests", {})}
            print(f"  confirming: {', '.join(answers)}", file=out)
            client.request("tasks/update", {"taskId": task_id, "inputResponses": answers})
        else:
            sleep(task.get("pollIntervalMs", DEFAULT_POLL_INTERVAL_S * 1000) / 1000)
        task = client.request("tasks/get", {"taskId": task_id})
        now = (task.get("status"), task.get("statusMessage"))
        if now != seen:
            seen = now
            print(f"  {seen[0]}" + (f": {seen[1]}" if seen[1] else ""), file=out)
    return task


def report_outcome(tool, task, out):
    """Say how the task ended, quoting the robot's own words; returns the exit
    code."""
    status = task.get("status")
    if status == "completed":
        outcome = task.get("result", {}).get("structuredContent", {})
        message = outcome.get("message", "")
        if outcome.get("success"):
            print(f"{tool}: completed: {message}", file=out)
            print(json.dumps(outcome, indent=2), file=out)
            return EXIT_OK
        print(f"{tool}: completed without success: {message}", file=out)
        print(json.dumps(outcome, indent=2), file=out)
        return EXIT_NOT_DONE
    if status == "failed":
        print(f"{tool}: failed: {task.get('error', {}).get('message', '')}", file=out)
        return EXIT_NOT_DONE
    print(f"{tool}: cancelled", file=out)
    return EXIT_CANCELLED


# --- Subcommands -------------------------------------------------------------


def command_tools(client, args, out, sleep):
    discovered = client.request("server/discover")
    server_info = discovered.get("_meta", {}).get(META_SERVER_INFO, {})
    print(server_info.get("title") or server_info.get("name") or client.endpoint, file=out)
    instructions = discovered.get("instructions")
    if instructions:
        print(instructions, file=out)
    print("", file=out)
    for tool in client.request("tools/list").get("tools", []):
        print(f"{tool['name']}: {tool.get('description', '')}", file=out)
    return EXIT_OK


def command_move_to_ready(client, args, out, sleep):
    return run_move(client, TOOL_MOVE_TO_READY, {"duration_s": args.duration_s}, out, sleep)


def command_move_to_home(client, args, out, sleep):
    return run_move(client, TOOL_MOVE_TO_HOME, {"duration_s": args.duration_s}, out, sleep)


def command_move_arm(client, args, out, sleep):
    goal = {
        "arm_name": args.arm,
        "position": args.position,
        "orientation": args.orientation,
        "duration_s": args.duration_s,
        "plan_position_tolerance_m": args.plan_position_tolerance_m,
        "plan_orientation_tolerance_rad": args.plan_orientation_tolerance_rad,
    }
    return run_move(client, TOOL_MOVE_ARM, goal, out, sleep)


def gripper_goal(gripper_name, opening, max_effort=0.0):
    return {"gripper_name": gripper_name, "opening": opening, "max_effort": max_effort}


def command_move_gripper(client, args, out, sleep):
    goal = gripper_goal(args.gripper, args.opening, args.max_effort)
    return run_move(client, TOOL_MOVE_GRIPPER, goal, out, sleep)


def command_demo(client, args, out, sleep):
    """Ready, both grippers closed then opened, home; stops at the first move
    the robot did not complete."""
    steps = [
        (TOOL_MOVE_TO_READY, {"duration_s": args.duration_s}),
        (TOOL_MOVE_GRIPPER, gripper_goal("left_gripper", GRIPPER_CLOSED)),
        (TOOL_MOVE_GRIPPER, gripper_goal("right_gripper", GRIPPER_CLOSED)),
        (TOOL_MOVE_GRIPPER, gripper_goal("left_gripper", GRIPPER_OPEN)),
        (TOOL_MOVE_GRIPPER, gripper_goal("right_gripper", GRIPPER_OPEN)),
        (TOOL_MOVE_TO_HOME, {"duration_s": args.duration_s}),
    ]
    for number, (tool, goal) in enumerate(steps, start=1):
        print(f"demo step {number}/{len(steps)}", file=out)
        code = run_move(client, tool, goal, out, sleep)
        if code != EXIT_OK:
            print(f"demo stopped at step {number}", file=out)
            return code
    print("demo complete", file=out)
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        description="Drive an OpenArm v2 through the MCP server built into peppy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="the exposure's MCP endpoint")
    commands = parser.add_subparsers(dest="command", required=True)

    tools = commands.add_parser("tools", help="print what the endpoint advertises")
    tools.set_defaults(run=command_tools)

    duration_help = "requested move time in seconds; 0 is as fast as the joint limits allow"
    ready = commands.add_parser("move-to-ready", help="bring both arms to the working posture")
    ready.add_argument("--duration-s", type=float, default=0.0, help=duration_help)
    ready.set_defaults(run=command_move_to_ready)

    home = commands.add_parser("move-to-home", help="bring both arms to the rest posture")
    home.add_argument("--duration-s", type=float, default=0.0, help=duration_help)
    home.set_defaults(run=command_move_to_home)

    arm = commands.add_parser("move-arm", help="move one arm's grasp point to a world-frame pose")
    arm.add_argument("--arm", choices=ARM_NAMES, required=True)
    arm.add_argument("--position", type=float, nargs=3, metavar=("X", "Y", "Z"), required=True, help="meters")
    arm.add_argument(
        "--orientation", type=float, nargs=4, metavar=("X", "Y", "Z", "W"), required=True, help="unit quaternion"
    )
    arm.add_argument("--duration-s", type=float, default=0.0, help=duration_help)
    arm.add_argument(
        "--plan-position-tolerance-m",
        type=float,
        default=0.0,
        help="how far the planned position may sit from the requested one; 0 is the planner's default",
    )
    arm.add_argument(
        "--plan-orientation-tolerance-rad",
        type=float,
        default=0.0,
        help="how far the planned orientation may sit from the requested one; 0 is the planner's default",
    )
    arm.set_defaults(run=command_move_arm)

    gripper = commands.add_parser("move-gripper", help="drive one gripper to an opening")
    gripper.add_argument("--gripper", choices=GRIPPER_NAMES, required=True)
    gripper.add_argument("--opening", type=float, required=True, help="fraction of jaw travel: 0 closed, 1 fully open")
    gripper.add_argument(
        "--max-effort", type=float, default=0.0, help="effort cap toward the target; 0 is no preference"
    )
    gripper.set_defaults(run=command_move_gripper)

    demo = commands.add_parser("demo", help="ready, grippers closed and opened, home")
    demo.add_argument("--duration-s", type=float, default=DEMO_POSTURE_DURATION_S, help=duration_help)
    demo.set_defaults(run=command_demo)
    return parser


def main(argv=None, out=sys.stdout, err=sys.stderr, sleep=time.sleep):
    args = build_parser().parse_args(argv)
    client = McpClient(args.endpoint)
    try:
        return args.run(client, args, out, sleep)
    except ProtocolError as error:
        print(f"{client.endpoint} refused the request ({error.code}): {error.message}", file=err)
        return EXIT_ENDPOINT
    except EndpointError as error:
        print(error, file=err)
        return EXIT_ENDPOINT
    except KeyboardInterrupt:
        print("interrupted", file=err)
        return EXIT_CANCELLED


if __name__ == "__main__":
    sys.exit(main())
