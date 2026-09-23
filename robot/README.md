# Every robot over MCP

`robot_control.json5` (manifest `robot_control:v1`) is the robots' own surface: one endpoint for
every robot of the stack, whatever its model, the same document served on the physical robots and
on their simulated twins, so everything a model does through it transfers between them. Every
target is a set the stack's robots fill, and every call names its robot, so one URL serves one
robot or ten and is the same before and after any join.

A model starts with the listing:

| Tool         | Policy         |
| ------------ | -------------- |
| `robot.list` | read only, 2 s |

It lists every robot present. Each entry carries `robot`, the name every other tool takes;
`capabilities`, the targets the robot fills, which say which tools and resources answer for it;
`members`, its camera names under `camera` (color) and `depth_camera` (carrying depth);
`identity`, its model and the machine hosting it; `limbs`, its arm and gripper names; and `notes`,
anything that could not be read for it. A call naming a robot that is not there, a capability it
does not fill, or a camera it does not have is refused, and the refusal names what is there. When
the robots run in a simulation their names here are their names in the simulated world's
`scene.get_robots_list`.

Every other tool takes `robot`. The robot's identity, moves and state:

| Tool or resource            | Contract member                     | Policy                          |
| --------------------------- | ----------------------------------- | ------------------------------- |
| `robot.get_identity`        | `robot_identity:v1` `get_identity`  | read only, 2 s                  |
| `robot.move_to_ready`       | `postures:v1` `move_to_ready`       | task, 60 s                      |
| `robot.move_to_home`        | `postures:v1` `move_to_home`        | task, 60 s                      |
| `robot.move_arm`            | `limb_motion:v1` `move_arm`         | task, 60 s                      |
| `robot.move_gripper`        | `limb_motion:v1` `move_gripper`     | task, 30 s                      |
| `robot.limb_state`          | `limb_state:v1` `limb_states`       | resource, 5 Hz at most, 2 s fresh |
| `robot.collision_status`    | `collision_status:v1` `collision_status` | resource, 5 Hz at most     |

`robot.move_arm` and `robot.move_gripper` name a limb as the listing reports it under `limbs`.
The cameras take `camera` too, one of the names the listing gives under `members`:

| Tool or resource                    | Contract                 | Policy                                              |
| ----------------------------------- | ------------------------ | --------------------------------------------------- |
| `camera.latest_frame`               | `rgb_camera:v1`          | resource, JPEG, 2 Hz at most, downscaled above 512 KiB |
| `camera.info`, `camera.set_exposure`, `camera.set_gain`, `camera.set_white_balance` | `rgb_camera:v1` | tools, the setters `safety_sensitive` |
| `depth_camera.latest_frame`         | `rgbd_camera:v1`         | resource, the color image as a JPEG                |
| `depth_camera.latest_depth`         | `rgbd_camera:v1`         | resource, a 16-bit PNG in the unit `depth_info` reports |
| `depth_camera.info`, `depth_camera.depth_info`, and the three color setters | `rgbd_camera:v1` | tools |
| `camera_profile.get`, `camera_profile.reset` | `camera_profile:v1` | the device's controls, their units and ranges |
| `camera_geometry.color_intrinsics`, `camera_geometry.depth_intrinsics`, `camera_geometry.depth_to_color` | `camera_geometry:v1` | read only |

A robot with a brain answers `brain.scan_items`, `brain.identify_item`, `brain.grab_item`,
`brain.place_item`, `brain.drop_item` and `brain.abort` as tasks and `brain.get_state` as a tool
(`item_perception:v1`, `item_manipulation:v1`), and one with a recorder
`recorder.record_episode` (`episode_recording:v1`), confirmation gated. Resources are published per
robot, `alpha/robot.limb_state`, `alpha/wrist_left/camera.latest_frame`,
`alpha/chest/depth_camera.latest_depth`, and the server sends `resources/list_changed` when a join
or a removal changes the list.

Every contract is pinned by sha256 to the document this exposure was written against. The
backbone's joint-space move (`move_arm_joints`) and the cameras' brightness and contrast stay
private. The server's `instructions` tell a model to list first, that this is the surface to
prefer over any simulation endpoint, how to address the limbs, which units and frames apply, to
look before moving, and to call `robot.move_to_ready` before any `robot.move_arm`.

## Launching it

The [launchers hub](https://github.com/Peppy-bot/launchers-hub) serves the exposure as the
`robot_control` axis of every launcher with robots, deployed by `simulation_mcp` and selected with
`--with robot_control` on the others, one server for the stack, `mcp/fragments/robot_control.json5`. Every robot beside it is listed with its identity and limb state, and
with its brain and recorder whenever they run; its `mcp_commander` option adds the backbone's
moves, and its camera rig adds the cameras under that option, `cameras` on hardware and
`cameras_sim` in simulation, so a robot without a rig is listed with no camera. The server reads
one clock, the simulation's beside a simulation and wall time on the physical robots, so a stack
under it is real or simulated. A join adds its robot to the running server and a removal takes
it out:

```sh
peppy stack launch simulation_mcp                                                   # Waldo, alpha over MCP, beside the simulated world's endpoint
peppy stack launch simulation_mcp --join so101_sim:charlie                          # alpha and an SO-101 on the one URL
peppy stack join openarm_v2_sim -i bravo                                            # listed when the join returns
peppy stack launch simulation_mcp --with mujoco,world_control=none                      # MuJoCo, this endpoint alone
peppy stack launch physical --with robot_control
peppy stack join openarm_v2 -i alpha --with mcp_commander,cameras                   # the real robot
```

The endpoint, the tools, the resources, and every command below are identical under all of them.
Only Waldo models the cameras' response, so under MuJoCo and Isaac Sim the frames, `camera.info`
and the geometry tools work and the setters refuse with a message, as the `instructions` tell a
model to expect. On hardware the `uvc_camera_linux` and `zed_camera` nodes describe no profile or
geometry, so those tools refuse for their cameras and the listing's capabilities say so. The
`simulation_mcp` launch also serves the simulated world's own endpoint,
[`simulation:v1`](../simulation/simulation.json5), on port 8902; it has no counterpart on the real
robots, and a client moving there drops that one entry.

The endpoint is `http://127.0.0.1:8900/robot_control/v1/mcp`, listed by `peppy stack list` in its
`Instance endpoints` table.

## The client script

`robot_control_demo.py`, standard library only, drives the endpoint from the command line. It
speaks MCP (revision 2026-07-28) directly, in the stateless shape the built-in server expects:
every request carries its own protocol version and client capabilities in `_meta` and the
`Mcp-Method` and `Mcp-Name` headers, answers arrive as event streams, and a move is an MCP task
polled through `tasks/get` at the interval the server suggests. It doubles as a reference for any
client of the endpoint. Its commands run from this directory, where uv finds the project:

```sh
uv run robot_control_demo.py tools
uv run robot_control_demo.py list
uv run robot_control_demo.py move-to-ready --robot alpha --duration-s 4
uv run robot_control_demo.py move-arm --robot alpha --arm right_arm --position 0.3 -0.2 0.4 --orientation 0 0.7071068 0 0.7071068
uv run robot_control_demo.py move-gripper --robot alpha --gripper left_gripper --opening 0
uv run robot_control_demo.py move-to-home --robot alpha --duration-s 4
uv run robot_control_demo.py demo --robot alpha
```

`tools` asks the endpoint what it advertises (`server/discover`, then `tools/list`) and prints the
title, the instructions, and every tool with its description, the camera tools included. `list`
calls `robot.list` and prints every robot with its limbs, cameras and capabilities. Each move has
a subcommand naming its robot; the script drives the moves alone and reads no camera. `demo`
brings the robot's arms to ready, closes and opens every gripper the listing gives it, and returns
home, stopping at the first move that does not complete. `--endpoint <url>` points the script at
another endpoint. Ctrl-C cancels the move in flight through `tasks/cancel` and waits for the robot
to settle.

Exit codes: 0 the move completed and the robot reported success; 1 the robot did not do it (a
refused goal, a robot that is not listed, a failed move, or a completed move reporting no
success); 2 the endpoint could not be reached or refused the request; 130 the move was cancelled.

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

`test_robot_control_demo.py` holds the script to that shape against a stand-in for the endpoint
that answers as the built-in server does: the same HTTP refusals, header requirements, task
shapes, error codes and statuses, a listing of two robots, and the refusal of a robot that is not
listed. Its tasks advance one step per poll, so no test waits on a clock, and it needs no peppy,
no daemon, and no robot:

```sh
uv run pytest
```

pytest takes its configuration from the repository's `pytest.ini`, found from here as from
anywhere else in the checkout, so this run and the `pytest` the pull request workflow runs from
the repository root over every test in the repository collect these tests the same way.
