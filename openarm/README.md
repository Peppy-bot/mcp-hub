# OpenArm v2 over MCP

`openarm_v2.json5` (manifest `openarm_v2:v1`) publishes four moves of the OpenArm v2 backbone as
tools backed by MCP tasks:

| Tool                    | Contract member             | Task deadline |
| ----------------------- | --------------------------- | ------------- |
| `openarm.move_to_ready` | `postures:v1` `move_to_ready` | 60 s        |
| `openarm.move_to_home`  | `postures:v1` `move_to_home`  | 60 s        |
| `openarm.move_arm`      | `limb_motion:v1` `move_arm`   | 60 s        |
| `openarm.move_gripper`  | `limb_motion:v1` `move_gripper` | 30 s      |

Every tool is `safety_sensitive` and moves the robot; none asks for confirmation. Both contracts
are pinned by sha256 to the documents this exposure was written against, and the backbone's
joint-space move (`move_arm_joints`) stays private. The server's `instructions` tell a model how
to address the limbs, which units and frames apply, and to call `openarm.move_to_ready` before any
`openarm.move_arm`.

## Launching it

The [launchers hub](https://github.com/Peppy-bot/launchers-hub) serves the exposure as the
`mcp_commander` option of its `openarm_v2` launcher, under the real robot or either simulator:

```sh
peppy stack launch openarm_v2 --with=mujoco,mcp_commander
```

The endpoint is `http://127.0.0.1:8900/openarm_v2/v1/mcp`, listed by `peppy stack list` in its
`Instance endpoints` table. It needs peppy v0.26.2 or later.

## The client script

`openarm_v2_demo.py`, standard library only, drives the endpoint from the command line. It speaks
MCP (revision 2026-07-28) directly, in the stateless shape the built-in server expects: every
request carries its own protocol version and client capabilities in `_meta` and the `Mcp-Method`
and `Mcp-Name` headers, answers arrive as event streams, and a move is an MCP task polled through
`tasks/get` at the interval the server suggests. It doubles as a reference for any client of the
endpoint.

```sh
python3 openarm/openarm_v2_demo.py tools
python3 openarm/openarm_v2_demo.py move-to-ready --duration-s 4
python3 openarm/openarm_v2_demo.py move-arm --arm right_arm --position 0.3 -0.2 0.4 --orientation 0 0 0 1
python3 openarm/openarm_v2_demo.py move-gripper --gripper left_gripper --opening 0
python3 openarm/openarm_v2_demo.py move-to-home --duration-s 4
python3 openarm/openarm_v2_demo.py demo
```

`tools` asks the endpoint what it advertises (`server/discover`, then `tools/list`) and prints the
title, the instructions, and every tool with its description. Each tool has a subcommand;
`demo` brings the arms to ready, closes and opens both grippers, and returns home, stopping at the
first move that does not complete. `--endpoint <url>` points the script at another endpoint.
Ctrl-C cancels the move in flight through `tasks/cancel` and waits for the robot to settle.

Exit codes: 0 the move completed and the robot reported success; 1 the robot did not do it (a
refused goal, a failed move, or a completed move reporting no success); 2 the endpoint could not
be reached or refused the request; 130 the move was cancelled.

## Tests

`test_openarm_v2_demo.py` holds the script to that shape against a stand-in for the endpoint that
answers as the built-in server does: the same HTTP refusals, header requirements, task shapes,
error codes and statuses. Its tasks advance one step per poll, so no test waits on a clock, and it
needs no peppy, no daemon, and no robot. Run it from the repository root, as the pull request
workflow does:

```sh
pytest
```
