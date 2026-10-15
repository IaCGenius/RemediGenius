# lambda-kiosk (Terraform module)

Lets agents vend their own Lambda functions (build, test, deploy, promote, run, reuse) inside limits they
cannot change. Nothing here knows about RemediGenius or Hermes: any agent that can run a CLI can use it.

| Part | What |
|---|---|
| `src/runtime/kiosk_runtime/` | the function contract (`handle(unit, ctx)`), `entry.main` for Lambda, `testing` helpers, `rules` (static checks shared by the gate and the agent's `kiosk test`) |
| `src/gate/gate.py` | the only code that creates or changes functions: validate, sandbox test, sign, deploy, promote, run, receipts, caps, auto-rollback |
| `src/sandbox/sandbox.py` | runs a bundle's tests offline (no route out, no rights, dummy credentials) |
| `statemachines/` | gate, promote, run (Step Functions) |
| `layers/*.lock` | hash-pinned runtime (boto3/botocore 1.42.89) and test (pytest 9.1.1) layers; the runtime layer is signed by the kiosk profile (code signing Enforce checks layers too) |
| `build.py` | deterministic zips for the layers and code (`tf.sh` runs it before every kiosk plan) |
| `tests/` | offline tests: `python -m pytest -q tests` |

Inputs: `name`, `agents` (principals, classes, promotion policy), sandbox subnet and security group, limits,
alert email. Outputs: bucket, config parameter, agent role ARNs, state machines, alert topic, freeze command.

Agent side: the Hermes skill `profiles/builder/skills/kiosk/lambda-kiosk` and its `kiosk` command.
A new agent: add it to `agents`, apply, give it short-lived credentials for `kiosk-<name>-agent-<agent>`
(on the Hermes host: a `kiosk.json` in the profile), install the skill, run `kiosk doctor --e2e`.
