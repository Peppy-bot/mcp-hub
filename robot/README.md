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
`tools`, the tools that robot answers, including its brain's and its recorder's where it has them;
`resources`, the resources it publishes, each read at `peppy://resource/<name>`; `members`, its
camera names under `camera` (color) and `depth_camera` (carrying depth); `identity`, its model and
the machine hosting it; `limbs`, its arm and gripper names with the joints behind each arm; and
`notes`, anything that could not be read for it. A call naming a robot that is not there, a tool
it does not answer, or a camera it does not have is refused, and the refusal names what is there.
When the robots run in a simulation their names here are their names in the simulated world's
`scene.get_robots_list`.

Every other tool takes `robot`. The robot's identity, moves and state:

| Tool or resource            | Contract member                     | Policy                          |
| --------------------------- | ----------------------------------- | ------------------------------- |
| `robot.get_identity`        | `robot_identity:v1` `get_identity`  | read only, 2 s                  |
| `robot.get_limb_names`      | `limb_state:v1` `get_limb_names`    | read only, 2 s                  |
| `robot.move_to_ready`       | `postures:v1` `move_to_ready`       | task, 60 s                      |
| `robot.move_to_home`        | `postures:v1` `move_to_home`        | task, 60 s                      |
| `robot.move_arm`            | `limb_motion:v1` `move_arm`         | task, 60 s                      |
| `robot.move_arm_joints`     | `limb_motion:v1` `move_arm_joints`  | task, 60 s                      |
| `robot.move_gripper`        | `limb_motion:v1` `move_gripper`     | task, 30 s                      |
| `robot.stop`                | `limb_motion:v1` `stop`             | mutating, 2 s                   |
| `robot.check_arm_move`      | `limb_motion:v1` `check_arm_move`   | read only, 5 s                  |
| `robot.get_camera_poses`    | `camera_mounts:v1` `get_camera_poses` | read only, 2 s                |
| `robot.describe_workspace`  | `workspace:v1` `describe_workspace` | read only, 15 s                 |
| `robot.check_positions`     | `workspace:v1` `check_positions`    | read only, 15 s                 |
| `robot.limb_state`          | `limb_state:v1` `limb_states`       | resource, 5 Hz at most, 2 s fresh |
| `robot.collision_status`    | `collision_status:v1` `collision_status` | resource, 5 Hz at most     |

`robot.move_arm`, `robot.move_arm_joints` and `robot.move_gripper` name a limb as the listing
reports it under `limbs`. A pose is in the robot frame: fixed to the robot's base, its origin the
point the base stands on, +X the way the robot faces, +Y to its left, +Z up. `robot.check_arm_move`
says whether a `robot.move_arm` goal has a plan, and moves nothing. `robot.stop` ends every planned
move in flight on the robot, whoever started it. Then each limb holds where it was commanded to be
when the stop came, and no gripper opens. `robot.move_to_ready` and `robot.move_to_home` report
`arm_names`, `positions` and `orientations`: the grasp point of each arm in the robot frame,
measured when the move ended. The three arrays are empty when the robot has no fresh measured pose
of an arm. `robot.move_gripper` answers when the gripper stands still. Its `final_opening` is the
opening measured then: the target, or where an object or the effort cap holds the jaws.
`robot.get_camera_poses` reports where each camera of the robot's design stands in the robot
frame, from the joints measured now, so a pixel and its depth become a point `robot.move_arm`
takes. `robot.describe_workspace` says where on a flat surface at a given height the robot can
work, with the largest rectangle in the robot frame to put items in, and `robot.check_positions`
whether it can work given points: which arm reaches each, and for a point no arm reaches, how far
short the closest arm stops. Both answer from the robot's design and the field of view of its
perception camera, the depth camera no arm carries, and know nothing of the room: no surface, no
obstacle. A robot without a perception camera, an SO-101 for example, whose one camera is on its
arm, is judged on reach alone. The cameras take `camera` too, one of the names the listing gives
under `members`:

| Tool or resource                    | Contract                 | Policy                                              |
| ----------------------------------- | ------------------------ | --------------------------------------------------- |
| `camera.latest_frame`               | `rgb_camera:v1`          | resource, the frame as a JPEG blob, 2 Hz at most, downscaled above 512 KiB |
| `camera.look`                       | `rgb_camera:v1`          | picture tool, the same frame as an image           |
| `camera.info`, `camera.set_exposure`, `camera.set_gain`, `camera.set_white_balance` | `rgb_camera:v1` | tools, the setters `safety_sensitive` |
| `depth_camera.latest_frame`         | `rgbd_camera:v1`         | resource, the color image as a JPEG blob           |
| `depth_camera.look`                 | `rgbd_camera:v1`         | picture tool, the color image                      |
| `depth_camera.latest_depth_picture` | `rgbd_camera:v1`         | resource, the depth as a grayscale JPEG blob, white near and black far |
| `depth_camera.look_depth`           | `rgbd_camera:v1`         | picture tool, the depth picture                    |
| `depth_camera.latest_depth_samples` | `rgbd_camera:v1`         | resource, a 16-bit PNG blob in the unit `depth_info` reports |
| `depth_camera.info`, `depth_camera.depth_info`, and the three color setters | `rgbd_camera:v1` | tools |
| `camera_profile.get`, `camera_profile.reset` | `camera_profile:v1` | the device's controls, their units and ranges |
| `camera_geometry.color_intrinsics`, `camera_geometry.depth_intrinsics`, `camera_geometry.depth_to_color` | `camera_geometry:v1` | read only |

The one `depth_stream` member of a depth camera is published twice: the picture for a model to see
how far things are, and the samples for a program to compute with. A read of an image resource
gives the message without its frame as JSON, and the frame as a blob. A picture tool answers with
the frame as an image, which is what a model sees, so the two pictures are tools too and the
samples stay a resource.

A robot with a brain answers `brain.scan_items`, `brain.identify_item`, `brain.grab_item`,
`brain.place_item`, `brain.drop_item` and `brain.abort` as tasks and `brain.get_state` as a tool
(`item_perception:v1`, `item_manipulation:v1`), and one with a recorder
`recorder.record_episode` (`episode_recording:v1`), confirmation gated. A scan and an identify
report each item's region in the picture `depth_camera.look` gives for the camera they name, with
the frame's size and capture time. Resources are published per
robot, `alpha/robot.limb_state`, `alpha/wrist_left/camera.latest_frame`,
`alpha/chest/depth_camera.latest_depth_samples`, and the server sends `resources/list_changed` when
a join or a removal changes the list.

`robot.recent_calls` is the endpoint's own tool: the last 200 calls of every tool that is not read
only, tasks included, newest first, with the client that made each, its arguments and how it ended,
so a client that finds a robot in a state it did not command can tell whether another client of
the endpoint did it. A motion a teleoperation or another node commanded is not in it.

Every contract is pinned by sha256 to the document this exposure was written against. The
cameras' brightness and contrast stay private. The server's `instructions` tell a model:

- to list first, and that this is the surface to prefer over any simulation endpoint;
- how to address the limbs, and which units and robot frame apply;
- to call `robot.move_to_ready` before any `robot.move_arm`;
- that no robot move checks the floor, a table, an object or a held item;
- that a move with success true does not prove that the arm arrived;
- what the result of `robot.move_to_ready` and `robot.move_to_home` reports.

The description of each move and of `robot.stop` says what holds after the call. That sentence
begins with `After the call,`, as [Writing tool texts](../README.md#writing-tool-texts) requires.

## Launching it

The [launchers hub](https://github.com/Peppy-bot/launchers-hub) serves the exposure as the
`robot_control` axis of every launcher with robots, deployed by `simulation_mcp` and selected with
`--with robot_control` on the others, one server for the stack, `mcp/fragments/robot_control.json5`.
Every robot beside it is listed with its identity, its limb state and where its design lets it
work, on an OpenArm with its collision readout and its camera mounts too, and with its brain and
recorder whenever they run; its `mcp_commander` option adds the backbone's
moves, and its camera rig adds the cameras under that option, `cameras` on hardware and
`cameras_sim` in simulation, so a robot without a rig is listed with no camera. The server reads
one clock, the simulation's beside a simulation and wall time on the physical robots, so a stack
under it is real or simulated. A join adds its robot to the running server and a removal takes
it out, whether it comes from the command line or from `stack.join` and `stack.remove` on the
framework's endpoint:

```sh
peppy stack launch simulation_mcp                                                   # Waldo, this endpoint beside the simulated world's and the framework's, no robot listed
peppy stack launch simulation_mcp --join openarm_sim:alpha                          # alpha, an OpenArm v2 over MCP
peppy stack launch simulation_mcp --join openarm_sim:alpha,so101_sim:charlie        # alpha and an SO-101 on the one URL
peppy stack join openarm_sim:bravo                                                  # listed when the join returns
peppy stack launch simulation_mcp --with mujoco,world_control=none                  # MuJoCo, this endpoint and the framework's
peppy stack launch physical --with robot_control
peppy stack join openarm:alpha --with v2,mcp_commander,cameras                      # the real robot
```

The endpoint, the tools, the resources, and every command below are identical under all of them.
Only Waldo models the cameras' response, so under MuJoCo and Isaac Sim the frames, `camera.info`
and the geometry tools work and the setters refuse with a message, as the `instructions` tell a
model to expect. On hardware the `uvc_camera_linux` and `zed_camera` nodes describe no profile or
geometry, so the listing leaves those tools out of such a robot's `tools` and a call on them is
refused. The `simulation_mcp` launch also serves the two other endpoints of a simulation stack, one
per family, as the [repository README](../README.md#repository-structure) describes. The simulated
world's endpoint, [`simulation:v1`](../simulation/simulation.json5), is on port 8902. It has no
counterpart on the real robots, and a client moving there drops that entry. The framework's
endpoint, [`framework_controls:v1`](../framework/framework_controls.json5), is on port 8903, and
the `robot_control` option of `simulation_mcp` deploys it with this endpoint. Its `stack.join`
adds a robot to the stack, and this endpoint lists the robot when the call ends with success. Its
`stack.remove` removes a robot, and this endpoint stops listing it. A client moving to the real
robots keeps that entry where the launcher of the real robots deploys the framework's endpoint. No
launcher of the launchers hub deploys it on the real robots.

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
calls `robot.list` and prints every robot with its limbs, its cameras, the tools it answers and
the resources it publishes. Each move has a subcommand naming its robot; the script drives the
moves alone and reads no camera. `demo` brings the robot's arms to ready, closes and opens every
gripper the listing gives it, and returns home, stopping at the first move that does not complete.
`--endpoint <url>` points the script at another endpoint. Ctrl-C cancels the move in flight
through `tasks/cancel` and waits for the robot to settle.

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
