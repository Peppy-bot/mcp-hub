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
openarm/      the OpenArm v2's posture, arm, and gripper moves as tools backed by MCP tasks, with a Python client
manipulation/ an AI brain's item perception and manipulation as tools backed by MCP tasks, for any embodiment
```

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
