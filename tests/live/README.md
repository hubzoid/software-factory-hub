# Live-run stand-ins (proof only)

`factory_live.py` and `sitecustomize.py` let the Software Factory run end to end in a real browser on a machine with no container runtime. They are test assets, never part of the hub.

- `FACTORY_LIVE_SANDBOX=standin`: the analyst, implementer and reviewer return scripted results, labelled as stand-ins in everything they produce. The "implementer" commits the fixture's known fix in a host clone made by test code: no model and no agent command runs on the host. The classifier and researcher, the chat agent, routing, approvals, the Console and GitHub stay real.
- `FACTORY_LIVE_GITHUB=fake`: a file-backed GitHub stand-in and a local bare repository, for runs before a real scratch repository and token exist.

```sh
export FACTORY_LIVE_STATE=/tmp/factory-live FACTORY_LIVE_SANDBOX=standin
export PYTHONPATH=/path/to/software-factory-hub/tests/live:$PYTHONPATH
hubzoid run . --port 8701 --bridge-port 8702
```

A real run needs a container runtime (Docker today, hosted sandboxes later) and none of this.
