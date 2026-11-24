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
`tools`, the tools that robot answers: the `robot.` tools, and the `brain.`, `recorder.`,
`planner.` and `navigator.` tools of its brain, its recorder, its motion planner and its navigator
where it has them;
`resources`, the resources it publishes, each read at `peppy://resource/<name>`; `members`, its
camera names under `camera` (color) and `depth_camera` (carrying depth), and its motor-bearing
components under `motor_health` and `alerts`; `identity`, its model and the machine hosting it;
`limbs`, its arm and gripper names with the joints behind each arm; and
`notes`, anything that could not be read for it. A call naming a robot that is not there, a tool
it does not answer, or a camera it does not have is refused, and the refusal names what is there.
When the robots run in a simulation their names here are their names in the simulated world's
`scene.get_robots_list`.

Every other tool takes `robot`. The robot's identity, guide, moves and state:

| Tool or resource            | Contract member                     | Policy                          |
| --------------------------- | ----------------------------------- | ------------------------------- |
| `robot.get_identity`        | `robot_identity:v1` `get_identity`  | read only, 2 s                  |
| `robot.get_guide`           | `robot_guide:v1` `get_guide`        | read only, 2 s                  |
| `robot.get_limb_names`      | `limb_state:v1` `get_limb_names`    | read only, 2 s                  |
| `robot.move_to_ready`       | `postures:v1` `move_to_ready`       | task, 65 s                      |
| `robot.move_to_home`        | `postures:v1` `move_to_home`        | task, 75 s: the close of the grippers, at most 10 s, then the arm move |
| `robot.move_arm`            | `limb_motion:v1` `move_arm`         | task, 125 s                     |
| `robot.move_arm_joints`     | `limb_motion:v1` `move_arm_joints`  | task, 125 s                     |
| `robot.execute_joint_path`  | `limb_motion:v1` `execute_joint_path` | task, 125 s                   |
| `robot.move_gripper`        | `limb_motion:v1` `move_gripper`     | task, 65 s                      |
| `robot.stop`                | `robot_stop:v1` `stop`              | mutating, 2 s                   |
| `robot.check_arm_move`      | `limb_motion:v1` `check_arm_move`   | read only, 5 s                  |
| `robot.drive_base`          | `base_motion:v1` `drive_base`       | task, 125 s                     |
| `robot.move_base`           | `base_motion:v1` `move_base`        | task, 125 s                     |
| `robot.describe_base`       | `base_state:v1` `describe_base`     | read only, 2 s                  |
| `navigator.navigate_to_pose` | `base_navigation:v1` `navigate_to_pose` | task, 60 s progress window |
| `navigator.spin`            | `base_navigation:v1` `spin`         | task, 60 s progress window      |
| `navigator.drive_on_heading` | `base_navigation:v1` `drive_on_heading` | task, 60 s progress window |
| `navigator.back_up`         | `base_navigation:v1` `back_up`      | task, 60 s progress window      |
| `navigator.clear_grid`      | `base_navigation:v1` `clear_grid`   | mutating, 2 s                   |
| `navigator.get_map_state`   | `room_map:v1` `get_map_state`       | read only, 2 s                  |
| `navigator.start_mapping`   | `room_map:v1` `start_mapping`       | mutating, 4 s                   |
| `navigator.finish_mapping`  | `room_map:v1` `finish_mapping`      | mutating, 2 s                   |
| `navigator.list_maps`       | `room_map:v1` `list_maps`           | read only, 2 s                  |
| `navigator.remove_map`      | `room_map:v1` `remove_map`          | mutating, 2 s                   |
| `navigator.load_map`        | `room_map:v1` `load_map`            | mutating, 2 s                   |
| `navigator.set_initial_pose` | `room_map:v1` `set_initial_pose`    | mutating, 7 s                   |
| `navigator.reinitialize_global_localization` | `room_map:v1` `reinitialize_global_localization` | mutating, 4 s                   |
| `robot.describe_sensors`    | `sensor_mounts:v1` `describe_sensors` | read only, 2 s                |
| `robot.lookup_transform`    | `transform_lookup:v1` `lookup_transform` | read only, 3 s: a wait of at most 1 s, then the read |
| `robot.describe_workspace`  | `workspace:v1` `describe_workspace` | read only, 15 s                 |
| `robot.check_positions`     | `workspace:v1` `check_positions`    | read only, 15 s                 |
| `robot.limb_state`          | `limb_state:v1` `limb_states`       | resource, 5 Hz at most, 2 s fresh |
| `robot.collision_status`    | `collision_status:v1` `collision_status` | resource, 5 Hz at most     |
| `robot.base_state`          | `base_state:v1` `base_states`       | resource, 5 Hz at most, 2 s fresh |
| `navigator.map_pose`        | `room_map:v1` `map_poses`           | resource, 5 Hz at most, 2 s fresh |

`robot.move_arm`, `robot.move_arm_joints`, `robot.execute_joint_path` and `robot.move_gripper` name
limbs as the listing reports them under `limbs`. Every point and pose names its `frame` and its
`timestamp`, by the frame rule of the server's `instructions`: a frame of the robot's tree, which a
call leaves out for the robot frame, the frame whose name `robot.describe_sensors` gives in
`robot_frame`, fixed to the robot's base, its origin where the robot's URDF puts its root link, +X
the way the robot faces, +Y to its left, +Z up; and an RFC 3339 time on the robot's clock, which a
call leaves out for the latest time. The robot places a pose by its tree at its timestamp when it
takes the call, so a pose read before the robot moved names the same place after. On a wheeled
base the robot frame's origin is on the floor at the point the base turns about in place, midway
between the driven wheels of a differential base. A velocity names its `frame` and its `timestamp`
by the same rule.
`robot.check_arm_move` says whether a `robot.move_arm` goal has a plan, and moves nothing.
`robot.stop` ends every planned move in flight on the robot, whoever started it, through the
robot's backbone, which implements `robot_stop`. Then each arm holds where it stands, each gripper
holds where it was commanded to be when the stop came, no gripper opens, and a mobile base comes to
rest at its deceleration limits and is held at rest against the leader that streams velocities to
it on `drive_link` until 0.5 s pass, from the stop on, with no velocity from it. An arm move with
`contact_gap_m` above 0 also ends on contact: it completes with `ended_on_contact` true once the
measured grasp point falls farther behind its command than the gap, as it does when the arm sets a
held item down. After an arm move that ended on contact, failed or was cancelled, the arm holds
where it stands. A robot that is a mobile base has no limbs: the listing reports its `limbs` as null, with a note
under `notes`. `robot.move_base` moves it to a `target` pose, which the robot places in `odom`, and
`robot.drive_base` drives it at one `velocity` for a time, which the robot places in the robot
frame and drives in it as the base moves, each by the frame rule when the robot takes the call.
`odom` is the robot frame where the base stood when its odometry started, fixed to the floor. Both
moves report `final_pose`, where the base's odometry placed the robot frame in `odom` when the move
ended, and how long the call took, and check no obstacle; `robot.move_base` steers by the base's
odometry. A base runs one move at a time. A move is checked in this order: a value it does not take
is refused with `rejected`, a target or a velocity the robot cannot place with a kind of the frame
rule, a placed target or velocity off the floor's plane or outside the base's limits with
`rejected`, a move while the base's motion sensing is silent with `resource_unavailable`, a move
while the base's mode is neither standing nor moving with `precondition_failed`, a move while a
leader streams to the base with `leader_streaming`, and a move while another runs with
`precondition_failed`. A leader that streams during a move does not move the base until the move
ends. `robot.describe_base` reports the base's odometry source, the limits of its velocity along x
and y and of its turn rate, each with its acceleration, deceleration, deadband and rest bound, and
its outline in the robot frame, and the `robot.base_state` resource where its odometry places it in
`odom`, the velocity it executes in the robot frame, and its mode. On a robot with a navigator,
`navigator.navigate_to_pose` drives its mobile base to a `target` pose around what the robot's
sensors have seen, the depth cameras fixed to the base: it plans a path, plans again as the
sensors see more, slows and stops the base before an obstacle ahead and before a drop in the
floor, and, when a try fails, empties its grid, turns in place, waits and backs up, once each,
before it fails with `no_path` or `blocked`. `navigator.spin` turns the base in place, and
`navigator.drive_on_heading` and `navigator.back_up` drive it straight ahead and back, each
sweeping the base's padded footprint ahead of the move. Each runs in `odom` and gives its result
there, keeps the base's footprint clear and no part outside it, and replaces the navigator's goal
that runs; a `target` in `map` is refused with `not_localized` while no map is loaded. A call
waits on them while the goal reports, at least once a second, and fails after 60 s with no
report, the goal running on. `navigator.clear_grid` empties the navigator's grid of the floor.
`robot.move_to_ready`
and `robot.move_to_home` report `frame`, `timestamp`, `arm_names` and `grasp_points`: the grasp
point of each arm in the robot frame, at the time the robot measured it when the move ended.
`arm_names` and `grasp_points` are empty when the robot has no fresh measured pose of an arm.
`robot.move_gripper` answers once the gripper stands still, or at its settle timeout. Its
`final_opening` is the opening measured then: the target, where an object or the effort cap holds
the jaws, or wherever they stood at the timeout.
`robot.describe_sensors` names the robot frame and the frame of each sensor of the robot's design
in the robot's tree of frames, with the arm that carries it, and `robot.lookup_transform` places
one frame of the tree, where it stood at one time, in another as it stands at a time, such as a
camera's frame at the capture time of a picture in the robot frame now. A pixel and its depth
become a point of the frame the picture's header names, which `robot.move_arm` takes with the
picture's timestamp. A call whose frame or time the robot cannot place gives `unknown_frame`,
`no_chain`, `extrapolation` or `broken_tree`.
`robot.describe_workspace` says where on a flat surface at a given height the robot can
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
gives the message without its `data` as JSON, its `header` naming the camera's frame, and the
picture as a blob. A picture tool answers with the picture as an image, which is what a model
sees, so the two pictures are tools too and the samples stay a resource.

The motor-bearing components of a robot, an OpenArm's arm and gripper drivers or an SO-101's
follower, are named in the resource, as the listing gives them under `members`:

| Resource                     | Contract          | Policy                                            |
| ---------------------------- | ----------------- | ------------------------------------------------- |
| `motor_health.latest_report` | `motor_health:v1` | resource per component, 5 Hz at most, 1.5 s fresh |
| `alerts.active`              | `alert:v1`        | resource per component, 5 Hz at most, 6 s fresh   |

`alpha/left_arm_inst/motor_health.latest_report` is the left arm driver's report, `level` per
motor and the readings behind it, and `alpha/left_arm_inst/alerts.active` the set of alerts it
holds, each naming its motor in words. A component that goes quiet reads as stale 1.5 s after its
last report and 6 s after its last alert set. A simulated robot has no motors to report on and
lists no component.

A robot with a brain answers `brain.scan_items`, `brain.identify_item`, `brain.grab_item`,
`brain.place_item`, `brain.drop_item`, `brain.abort` and `brain.switch_model` as tasks and
`brain.get_state`, `brain.get_model` and `brain.list_models` as tools (`item_perception:v1`,
`item_manipulation:v1`, `brain_model:v1`), and one with a recorder
`recorder.record_episode` (`episode_recording:v1`), confirmation gated. A scan and an identify
report each item's region in the picture `depth_camera.look` gives for the camera they name, with
the picture's size, and each item's point in the robot frame at that picture's capture time.
Resources are published per robot, `alpha/robot.limb_state`, `alpha/wrist_left/camera.latest_frame`,
`alpha/chest/depth_camera.latest_depth_samples`, `alpha/left_arm_inst/alerts.active`, and the
server sends `resources/list_changed` when a join or a removal changes the list.

A robot with a motion planner answers `planner.plan_joint_path` and
`planner.plan_cartesian_path` as tasks, 65 s and 15 s, `planner.check_joint_path`,
`planner.describe_arms` and `planner.get_planning_scene` as read-only
tools, 15 s, 2 s and 2 s, and `planner.clear_occupancy_map`, `planner.apply_collision_objects`,
`planner.apply_attached_collision_object` and `planner.set_allowed_collision` as mutating tools, 2 s
each (`motion_planning:v1`). A plan moves nothing: it gives a path of joint waypoints for one arm
or both, which pass their k-th waypoints together, around what the robot's depth camera has seen,
the objects of its planning scene and each other, which `robot.execute_joint_path` runs, each arm's
start passed as its expected start. `path_orientation_constraints` holds orientations along the whole
path, such as a carried cup kept upright, at every state the move runs, in any order of the list.
`so101` has no depth camera, so its plan keeps clear of the objects a client enters and its own
links alone, and what its hand holds of the links it may not touch; folded onto itself as it rests, its arm refuses a
plan with `start_in_collision`: move it to `robot.move_to_home`, out of contact, and plan from there; and with five
joints its goal takes an
orientation with slack: `tolerance_rad` or `free_axis` reaches a pose `robot.move_arm` refuses for
its orientation. A Cartesian path gives such a path for one arm whose link follows
straight lines through poses, as much of them as is valid, and the fraction covered. The scene holds the objects a client adds, such as a table top
or an item the brain found, the objects attached to an arm's grasp link, which move with it, and the
pairs allowed to touch.

A robot whose mobile base measures its odometry and carries a 2-D lidar fixed to it can have a
navigator that maps rooms with that lidar, which answers the `room_map:v1` tools and resource of the
table; they move nothing. `navigator.start_mapping` `{map_name: "lab"}` starts a map whose map frame
is `odom` as it stands then, the base drives the room under `robot.move_base` or `robot.drive_base`,
and `navigator.finish_mapping` saves `lab` on the navigator's machine and keeps it loaded. After the
navigator restarts, `navigator.load_map` `{map_name: "lab"}` loads it, and
`navigator.set_initial_pose` `{target: {frame: "map", position: [2.0, 1.0, 0.0], orientation: [0.0,
0.0, 0.7071, 0.7071]}, search_radius_m: 0.5, search_angle_rad: 0.5}` matches the lidar's next scan
against the map near that pose and answers with the matched pose in `current_pose`, or fails with
`no_match`. A client that does not know where the base stands calls
`navigator.reinitialize_global_localization`, which searches the whole map, and turns the base in
place with `robot.drive_base` until `navigator.map_pose` reports it `localized`. To map the room
again, `navigator.remove_map` `{map_name: "lab"}` unloads and removes `lab`, and
`navigator.start_mapping` `{map_name: "lab"}` starts over. `navigator.get_map_state` and
`navigator.map_pose` report the loaded map, whether mapping or a search runs, where the robot frame
stands in `map` and whether the base is localized there.

`robot.recent_calls` is the endpoint's own tool: the last 200 calls of every tool that is not read
only, tasks included, newest first, with the client that made each, its arguments and how it ended,
with the failure kind and the message of a call that a robot refused or that failed, so a client
that finds a robot in a state it did not command can tell whether another client of the endpoint
did it. A motion a teleoperation or another node commanded is not in it.

Every contract is pinned by sha256 to the document this exposure was written against. The
cameras' brightness and contrast and the navigator's occupancy grid, `map_grids`, stay private.
The server's `instructions` tell a model:

- to list first, and that what a robot cannot do through these tools, it cannot do;
- how to address the limbs, that a mobile base has none, which units apply, and the frame rule:
  the frame and the timestamp of every point, pose and velocity, and the kinds of a call whose
  frame the robot cannot place;
- how a mobile base moves, in which frame each base move places its target or its velocity and
  gives its result, and that a base runs one move at a time, a navigator goal replacing the
  navigator's goal that runs;
- how a navigator maps a room, saves and loads the map and localizes the base in it, and the map
  rule: the loaded map, the map frame, when the base is localized, the map names, where the maps are
  saved, the read of the base's odometry source that three of its tools wait for, and the order of a
  map tool's refusals;
- that a robot's motor health and alerts are resources, one of each per component named under
  `members`;
- to call `robot.move_to_ready` before any `robot.move_arm`;
- that no move of the `robot.` tools checks the floor, a table, an object or a held item, and no
  base move of them an obstacle, and that the moves of the `navigator.` tools drive a base around
  what the robot's sensors see;
- how a call that a robot refuses, or that fails, ends: with `outcome`, `failure_kind` and
  `message`, the kinds of every robot and the kinds of the tools (`unreachable`, `blocked`,
  `not_localized`, `leader_streaming`, `not_found`, `no_match`), how a cancelled move gives its
  reason and its result, and that a robot stop during a silence of the base's motion sensing ends a
  navigator goal with `resource_unavailable`;
- that an arm move completes only once the measured arm settled within the tolerances the call
  names, and fails with `timeout` otherwise, and that a gripper move never fails on its settle;
- what the result of `robot.move_to_ready` and `robot.move_to_home` reports.

A client can read this endpoint alone, on the physical robots or for one task, so no text of the
document names another endpoint or a tool of one. The simulated world's instructions say that a
robot's name there is its name here, how its world frame maps to the robot frame, and that it never
completes a task. The rule and its test are in
[The robots' endpoint names no other endpoint](../README.md#the-robots-endpoint-names-no-other-endpoint).

The description of each move, of `robot.stop`, and of each setter of the motion planner, the
navigator and the brain's model says what holds after the call. That sentence begins with
`After the call,`, as [Writing tool texts](../README.md#writing-tool-texts) requires.

## Launching it

The [launchers hub](https://github.com/Peppy-bot/launchers-hub) serves the exposure as the
`robot_control` axis of every launcher with robots, deployed by `simulation_mcp` and selected with
`--with robot_control` on the others, one server for the stack, `mcp/fragments/robot_control.json5`.
Every robot beside it is listed with its identity, where it carries its sensors and where each of
its frames stands. An arm robot is listed with its limb state and where its design lets it work,
on an OpenArm with its collision readout too, on an OpenArm v2 with its motion planner, on the
physical robots with their drivers' motor health and alerts, with the backbone's moves, and with its
brain and recorder whenever they run. A mobile base is listed with its base state and its moves, its
backbone's, and its navigator's when it runs one, and with the navigator's map tools when its copy
runs a room mapper. A robot's camera rig adds the cameras, `cameras` on hardware and `cameras_sim`
in simulation, so a robot without a rig is listed with no camera. The server reads one clock, the
simulation's beside a simulation and wall time on the physical robots, so a stack under it is real
or simulated. A join adds its robot to the running server and a removal takes it out, whether it
comes from the command line or from `stack.join` and `stack.remove` on the framework's endpoint:

```sh
peppy stack launch simulation_mcp                                                   # Waldo, this endpoint beside the simulated world's and the framework's, no robot listed
peppy stack launch simulation_mcp --join openarm_sim:alpha                          # alpha, an OpenArm v2 on this endpoint
peppy stack launch simulation_mcp --join openarm_sim:alpha,so101_sim:charlie        # alpha and an SO-101 on the one URL
peppy stack join openarm_sim:bravo                                                  # listed when the join returns
peppy stack launch simulation_mcp --with mujoco,world_control=none                  # MuJoCo, this endpoint and the framework's
peppy stack launch physical --with robot_control
peppy stack join openarm:alpha --with openarm_v2,cameras                            # the real robot
```

The endpoint, the tools, the resources, and every command below are identical under all of them.
Only Waldo models the cameras' response, so under MuJoCo and Isaac Sim the frames, `camera.info`
and the geometry tools work and the setters refuse, with a failure kind and a message, as the
`instructions` tell a model to expect. On hardware the `uvc_camera_linux` and `zed_camera` nodes
describe no profile or geometry, so the listing leaves those tools out of such a robot's `tools`
and a call on them is refused. The `simulation_mcp` launch also serves the two other endpoints of a simulation stack, one
per family, as the [repository README](../README.md#repository-structure) describes. The simulated
world's endpoint, [`simulation:v1`](../simulation/simulation.json5), is on port 8902. It has no
counterpart on the real robots, and a client moving there drops that entry. The framework's
endpoint, [`framework_controls:v1`](../framework/framework_controls.json5), is on port 8903, and
the `robot_control` option of `simulation_mcp` deploys it with this endpoint. Its `stack.join`
adds a robot to the stack, and this endpoint lists the robot when the call completes. Its
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
uv run robot_control_demo.py move-arm --robot alpha --arm right_arm --position 0.3 -0.2 0.3 --contact-gap-m 0.004
uv run robot_control_demo.py move-gripper --robot alpha --gripper left_gripper --opening 0
uv run robot_control_demo.py move-to-home --robot alpha --duration-s 4
uv run robot_control_demo.py demo --robot alpha
```

`tools` asks the endpoint what it advertises (`server/discover`, then `tools/list`) and prints the
title, the instructions, and every tool with its description, the camera tools included. `list`
calls `robot.list` and prints every robot with its limbs, its cameras, the tools it answers and
the resources it publishes. Each move has a subcommand naming its robot; the script drives the
moves alone and reads no camera. `move-arm` gives its pose in the robot frame, whose name it reads
from `robot.describe_sensors`, with no timestamp, for the latest time, and with no orientation when
`--orientation` is left out. `demo` brings the robot's arms to ready, closes and opens every
gripper the listing gives it, and returns home, stopping at the first move that does not complete.
`--endpoint <url>` points the script at another endpoint. Ctrl-C cancels the move in flight
through `tasks/cancel` and waits for the robot to settle.

A move that the robot refuses, or that fails, ends its task `failed`, and the error of the task
carries the robot's failure in its data: `outcome` (`refused` or `failed`), `failure_kind` and
`message`. The script prints the three, or the endpoint's own words for a task that failed without
a failure kind, such as a goal that the robot abandoned.

Exit codes: 0 the move completed; 1 the robot did not do it (a refused goal, a failed move, or a
robot that is not listed); 2 the endpoint could not be reached or refused the request; 130 the move
was cancelled.

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
shapes, error codes and statuses, the same failure kinds in a failed task and in the tool error of
a call, the same reason and result of a cancelled goal, a listing of two robots, and the refusal
of a robot that is not listed. Its tasks advance one step per poll, so no test waits on a clock, and it needs no peppy,
no daemon, and no robot:

```sh
uv run pytest
```

pytest takes its configuration from the repository's `pytest.ini`, found from here as from
anywhere else in the checkout, so this run and the `pytest` the pull request workflow runs from
the repository root over every test in the repository collect these tests the same way.
