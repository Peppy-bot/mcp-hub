# MCP Hub

A repository of Peppy **MCP exposures** (`peppy_schema: "mcp_exposure/v1"`).

An exposure selects members of the contracts in the [contracts hub](https://github.com/Peppy-bot/contracts-hub) and publishes them to [Model Context Protocol](https://modelcontextprotocol.io) clients: topics as resources, services as tools, and actions as tools backed by MCP tasks. Each member gets a stable public name, prose written for a model to read, and operational policies (freshness, update rate, deadlines, result size, confirmation). Anything the document does not name is not reachable through the endpoint.

The document is the whole artifact. A launcher lists exposures under `source: { exposures: ["<name>:<tag>", ...] }`, binds each exposure target to a running implementer of its contract through `links`, and the server built into `peppy` serves them: one process per deployment, each exposure at `http://127.0.0.1:<port>/<name>/<tag>/mcp`. The [launchers hub](https://github.com/Peppy-bot/launchers-hub) deploys `front_camera:v1` in `examples/mcp_front_camera.json5`. See the [MCP exposure guide](https://docs.peppy.bot/advanced_guides/mcp/) for the document format and the [launch files guide](https://docs.peppy.bot/guides/launch_files/) for the deployment.

`peppy` configures this repository by default, so a launcher on any machine can list what it publishes.

## Repository structure

Exposures are grouped by what they publish:

```text
cameras/      one camera as resources and tools
recording/    a camera plus an episode recorder driven through MCP tasks
openarm/      the OpenArm v2's own surface: its posture, arm, and gripper moves as tools backed by MCP tasks and its three cameras as resources and tools, with a Python client
manipulation/ an AI brain's item perception and manipulation as tools backed by MCP tasks, for any embodiment
simulation/   the simulated world's scene, lighting, and materials as one document; a simulation launch option only
```

An OpenArm v2 stack publishes two endpoints, one per family, and the boundary between them is
whether what a model does transfers to the physical robot:

| Family | Document | What it publishes | On the physical robot |
| --- | --- | --- | --- |
| Robot | [`openarm/openarm_v2.json5`](openarm/openarm_v2.json5) (`openarm_v2:v1`) | the arm and gripper moves, the three cameras and their controls | yes |
| Simulated world | [`simulation/simulation.json5`](simulation/simulation.json5) (`simulation:v1`) | the scene, its light sources, its materials | no |

A document is one catalog, one `instructions` block and one endpoint, so a family is a document. A
model reads two preambles: the robot's says it is the robot's own surface and is to be preferred,
the simulated world's says it sets the world up and is never a way to complete a task. On the
physical robot the second endpoint is absent.

The OpenArm v2 exposure, its client script, and its tests have their own guide:
[`openarm/README.md`](openarm/README.md).

## Adding an exposure

Create a `.json5` file under the relevant category:

```json5
{
  peppy_schema: "mcp_exposure/v1",
  manifest: { name: "<exposure_name>", tag: "<tag>" },
  server: { title: "<what a client sees>", instructions: "<prose for the model>" },
  targets: {
    "<logical_target>": {
      contract: { name: "<contract_name>", tag: "<tag>" }, // sha256 optional: pins the contract bytes
      topics:   [ /* member, resource, description, freshness, update, ... */ ],
      services: [ /* member, tool, description, operation, deadline_ms, ... */ ],
      actions:  [ /* member, tool, description, operation, deadline_ms, ... */ ],
    },
  },
}
```

This repository publishes what `peppy_repository.json5` says it publishes, and nothing else. An
exposure that is not listed there is invisible to peppy, so after adding, moving, or renaming one,
run:

```sh
peppy repo index .
```

Commit the updated `peppy_repository.json5` alongside your change. Before pushing, check the
document against the contracts it references and read what an endpoint for it advertises:

```sh
peppy repo refresh                                      # caches the contracts hub
peppy repo index . --check --validate-mcp-exposures     # the index, then every exposure against its contracts
peppy mcp catalog <exposure_name>:<tag>                 # the derived catalog: resources, tools, tasks, schemas
```

Generation refuses, naming both files, if your change claims a `name:tag` another one already
publishes. Rename yours: within one repository, a `name:tag` is claimed by exactly one file.

## Simulation contracts

An exposure is the one surface a model drives on the real robot and in simulation alike: the same
tools and resources, whatever the launcher binds behind its targets. The contracts hub's
`simulation/` category holds two kinds of contract, and this repository treats them differently.

### Ground truth and the internal camera channel, never published

A contract that reports what only a simulation can know has no real-world implementer, so a
target on it would exist only in simulation and split the two surfaces. Simulation ground truth
therefore stays inside the peppy framework, where harness tests, recorders and the evaluation of
simulated behaviour read it, and never reaches an endpoint. That is `object_state` (the pose and
velocities of every spawned object, streamed and answered on demand from the same snapshot),
`contact_state` (every contact the physics resolves, from both sides, with its normal force) and
`sensor_readout` (the reading of every sensor the simulated model declares). `sim_camera_control`
is refused the same way: it is the internal channel through which a rendered camera's relay
forwards the controls it receives to the engine, a relay drives it on a model's behalf, and the
relay's own `rgb_camera` / `rgbd_camera` surface is what an exposure publishes.
[`test_no_simulation_ground_truth.py`](test_no_simulation_ground_truth.py) reads every
`mcp_exposure/v1` document in the checkout and fails the pull request that targets such a
contract; extend its `GROUND_TRUTH_CONTRACTS` or `INTERNAL_CONTRACTS` when the contracts hub gains
another.

### Simulation configuration, published under a wording rule

`scene_manipulation` (assets, scene loading, spawned objects, the robots and their bases), `scene_lighting`
and `scene_materials` edit the simulated world and have no physical counterpart either, but a
model legitimately drives them to set the world up. Exposures on them live under `simulation/`:
today one document, [`simulation/simulation.json5`](simulation/simulation.json5), holding the
three contracts as its `scene`, `lighting` and `materials` targets. Only a simulation launch
option serves it: the `mcp_scene_commander` option of the `simulation_mcp` axis of the
[launchers hub](https://github.com/Peppy-bot/launchers-hub)'s `openarm_simulation_mcp` launcher,
at `http://127.0.0.1:8902/simulation/v1/mcp`, a process of its own beside the robot endpoint
`http://127.0.0.1:8900/openarm_v2/v1/mcp`. It binds the simulation alone, so it needs nothing
from a robot copy and outlives it. Waldo is the one simulation implementing the lighting and
materials contracts, so the launcher requires it beside that option. No real-robot fragment
lists the document.

The cameras are not simulation configuration. The rig the simulation renders publishes
`rgb_camera:v1` and `rgbd_camera:v1`, the contracts the physical `uvc_camera` and `zed_camera`
nodes implement, at the viewpoints of the physical rig, and reading a wrist frame is what a model
does on hardware. They are targets of the robot document, so a model never depends on the
simulated world's endpoint to see. The one camera contract with no physical implementer,
`camera_profile:v1`, is not published: the setters carry their bounds through `restrict` and
their modes and units in their descriptions, and its tools return to the robot document when the
physical camera nodes implement it.

A model reading one of these endpoints must never mistake it for a real-robot surface, so every
document under `simulation/` says what it is, and the same test enforces the wording:

- the server `title` ends with `(simulation only)`;
- the server `instructions` open with the exact sentence
  `This endpoint configures a simulated world. It has no effect on and no counterpart in the physical robot.`;
- every `description` of every topic, service and action contains the word `simulation` or
  `simulated` (a whole word, any case).

The test also fails an exposure that targets `scene_manipulation`, `scene_lighting` or
`scene_materials` from any other directory (its `SIMULATION_CONFIGURATION_CONTRACTS`). A pull
request that adds a `simulation/` document without the suffix, the opening sentence, or the word
in one of its descriptions fails, naming the part that is missing.

## Continuous integration

The [index workflow](.github/workflows/repository-index.yml) runs on every pull request with the
latest peppy release: it starts an isolated daemon, caches the contract repositories, and runs
`peppy repo index . --check --validate-mcp-exposures`, so an exposure selecting a member its
contract does not declare, breaking a policy rule, or pinning bytes the contracts hub no longer
serves fails the pull request that causes it. It also refuses artifacts derived from an exposure (a `*_mcp/`
directory or a `*.bundle.json` file): the server is built into peppy and the catalog is derived on
demand, so only the documents belong here.

The same workflow's `python-tests` job runs `pytest` from the repository root with no path and no
pattern: it collects every `test_*.py` and `*_test.py` under the checkout (`pytest.ini` lets it into
dot-directories such as `.github`), so a test added anywhere in the repository runs without the
workflow naming it.
