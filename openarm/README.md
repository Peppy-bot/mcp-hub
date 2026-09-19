# OpenArm v2 over MCP

`openarm_v2.json5` (manifest `openarm_v2:v1`) is the robot's own surface: the same document is
served on the physical robot and on its simulated twin, so everything a model does through it
transfers between them. It publishes who the robot is, as one tool that answers within a request:

| Tool                   | Contract member                    | Policy         |
| ---------------------- | ---------------------------------- | -------------- |
| `openarm.get_identity` | `robot_identity:v1` `get_identity` | read only, 2 s |

It reports `robot`, the name the robot stands under everywhere, its `model` and the `core_node`
hosting it. An endpoint speaks for one robot, so this is how a model driving several tells them
apart, and when the robot runs in a simulation `robot` is its entry in the simulated world's
`scene.get_robots_list`. The robot's initializer serves it, on hardware and under every
simulation.

It publishes four moves of the OpenArm v2 backbone as tools backed by MCP tasks:

| Tool                    | Contract member             | Task deadline |
| ----------------------- | --------------------------- | ------------- |
| `openarm.move_to_ready` | `postures:v1` `move_to_ready` | 60 s        |
| `openarm.move_to_home`  | `postures:v1` `move_to_home`  | 60 s        |
| `openarm.move_arm`      | `limb_motion:v1` `move_arm`   | 60 s        |
| `openarm.move_gripper`  | `limb_motion:v1` `move_gripper` | 30 s      |

and the robot's three cameras, `wrist_left` and `wrist_right` (`rgb_camera:v1`, the Arducam B0495
wrist modules) and `chest` (`rgbd_camera:v1`, the ZED Mini), each as one resource and four tools:

| Name                         | Kind     | Contract member                                 | Policy |
| ---------------------------- | -------- | ----------------------------------------------- | ------ |
| `<camera>.latest_frame`      | resource | `video_stream`                                  | JPEG, 2 Hz at most, 2 s fresh, downscaled above 512 KiB |
| `<camera>.info`              | tool     | `video_stream_info`                             | read only, 2 s |
| `<camera>.set_exposure`      | tool     | `set_exposure` (`set_color_exposure` on `chest`) | wrists 1 to 5000, in units of 100 microseconds; `chest` automatic only |
| `<camera>.set_gain`          | tool     | `set_gain` (`set_color_gain`)                   | wrists 0 to 100, `chest` 0 to 8 |
| `<camera>.set_white_balance` | tool     | `set_white_balance` (`set_color_white_balance`) | 2800 to 6500 K |

Seventeen tools and three resources over six targets. Every `openarm` tool but
`openarm.get_identity` is `safety_sensitive` and moves the robot; none asks for confirmation. Every contract is pinned by sha256 to the
document this exposure was written against. The backbone's joint-space move (`move_arm_joints`),
the chest's depth stream, and the cameras' brightness and contrast stay private. So does
`camera_profile:v1`: no physical camera node implements it, so publishing it would split the
surface between hardware and simulation; the setters carry their bounds through `restrict` and
their modes and units in their descriptions, and its tools return here when the `uvc_camera` and
`zed_camera` nodes implement the contract. The server's `instructions` tell a model that this is
the surface to prefer over any simulation endpoint, how to address the limbs, which units and
frames apply, to look before moving, and to call `openarm.move_to_ready` before any
`openarm.move_arm`.

## Launching it

The [launchers hub](https://github.com/Peppy-bot/launchers-hub) serves the exposure as the
`mcp_commander` option of its OpenArm robot fragments. A deployment's exposure list is fixed and
every target takes a link, so the option requires the robot's camera rig, `cameras` on hardware
and `cameras_sim` in simulation, which fills the three camera targets under the same ids:

```sh
peppy stack launch openarm_simulation_mcp                                     # Waldo, beside the simulated world's endpoint
peppy stack launch openarm_simulation_mcp --with mujoco,simulation_mcp=none   # MuJoCo, this endpoint alone
peppy stack launch fleet
peppy stack join openarm_v2 -i alpha --with mcp_commander,cameras             # the real robot
```

The endpoint, the tools, the resources, and every command below are identical under all of them:
the backbone fills the two move targets whichever robot option is selected, and the rig fills the
camera targets, the `uvc_camera` and `zed_camera` nodes on hardware and the simulation's relays on
the twin. Only Waldo models the cameras' response, so under MuJoCo and Isaac Sim the frames and
`<camera>.info` work and the three setters refuse with a message, as the `instructions` tell a
model to expect. The first launch also serves the simulated world's own endpoint,
[`simulation:v1`](../simulation/simulation.json5), on port 8902; it has no counterpart on the
real robot, and a client moving there drops that one entry.

The endpoint is `http://127.0.0.1:8900/openarm_v2/v1/mcp`, listed by `peppy stack list` in its
`Instance endpoints` table. It needs peppy v0.26.2 or later.

## The client script

`openarm_v2_demo.py`, standard library only, drives the endpoint from the command line. It speaks
MCP (revision 2026-07-28) directly, in the stateless shape the built-in server expects: every
request carries its own protocol version and client capabilities in `_meta` and the `Mcp-Method`
and `Mcp-Name` headers, answers arrive as event streams, and a move is an MCP task polled through
`tasks/get` at the interval the server suggests. It doubles as a reference for any client of the
endpoint. Its commands run from this directory, where uv finds the project:

```sh
uv run openarm_v2_demo.py tools
uv run openarm_v2_demo.py move-to-ready --duration-s 4
uv run openarm_v2_demo.py move-arm --arm right_arm --position 0.3 -0.2 0.4 --orientation 0 0.7071068 0 0.7071068
uv run openarm_v2_demo.py move-gripper --gripper left_gripper --opening 0
uv run openarm_v2_demo.py move-to-home --duration-s 4
uv run openarm_v2_demo.py demo
```

`tools` asks the endpoint what it advertises (`server/discover`, then `tools/list`) and prints the
title, the instructions, and every tool with its description, the camera tools included. Each move
has a subcommand; the script drives the moves alone and reads no camera;
`demo` brings the arms to ready, closes and opens both grippers, and returns home, stopping at the
first move that does not complete. `--endpoint <url>` points the script at another endpoint.
Ctrl-C cancels the move in flight through `tasks/cancel` and waits for the robot to settle.

Exit codes: 0 the move completed and the robot reported success; 1 the robot did not do it (a
refused goal, a failed move, or a completed move reporting no success); 2 the endpoint could not
be reached or refused the request; 130 the move was cancelled.

## The environment

`pyproject.toml` declares this directory as a uv project. The script itself takes nothing from it:
the only dependency is pytest, pinned to the release the pull request workflow installs, and
`uv.lock` fixes that resolution so a run here and a run in CI test against the same pytest.
`.python-version` holds the 3.12 the workflow runs on. Nothing here is a package, so `.venv` holds
pytest and nothing else:

```sh
uv sync
```

Every `uv run` syncs that environment first, so `uv sync` is only worth running on its own to
build it up front. Any Python 3.12 or later runs the script as it stands, with or without uv,
since it imports nothing outside the standard library.

## Tests

`test_openarm_v2_demo.py` holds the script to that shape against a stand-in for the endpoint that
answers as the built-in server does: the same HTTP refusals, header requirements, task shapes,
error codes and statuses. Its tasks advance one step per poll, so no test waits on a clock, and it
needs no peppy, no daemon, and no robot:

```sh
uv run pytest
```

pytest takes its configuration from the repository's `pytest.ini`, found from here as from
anywhere else in the checkout, so this run and the `pytest` the pull request workflow runs from
the repository root over every test in the repository collect these tests the same way.
