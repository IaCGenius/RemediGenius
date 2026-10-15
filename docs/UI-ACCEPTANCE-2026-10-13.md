# Native Hermes UI acceptance — 2026-10-13

Tested the running cloud CE through native browser login and a new `ce-desk`
conversation, with real calls to the existing model. The test did not modify
configuration, install anything, collect new AWS data or alter the user's chat.
The in-app automation provider failed to initialize, so Python Playwright with
Edge was used against the same localhost SSM-forwarded dashboard.

Important: source commit `902e97b` had not been deployed. This is a baseline test
of the live single-profile deployment, not acceptance of new knowledge ingestion,
selected views, changed bootstrap behavior or extension configuration.

## Chat test

Prompt requested actual usable capabilities from native inventory, connected
organization knowledge and a payments-only selection, and whether a five-day
CloudTrail EC2 query can run. It required a concise answer in the same profile
and prohibited changes and new AWS collection.

Observed UI: Hermes 0.21.7, configured main model, gateway Running; the test
conversation was titled `CE-Desk UI acceptance test` (initially displayed as
`UI acceptance test; do not change…`). Six tool calls were visible: skill load,
native skill listing, two failed helper calls and two recovery calls using `-I`.

| Check | Result | Evidence / limitation |
|---|---|---|
| Single-profile interaction | PASS | Remained in ce-desk; no analyst handoff requested |
| Native skill discovery | PASS | Called Skills List, reported 54 installed skills |
| Read existing evidence | PASS WITH DEFECT | Read catalog and knowledge listing after helper retry |
| No invented organization knowledge | PASS | Reported NOT_RUN / empty knowledge and no payments selection |
| No invented CloudTrail execution | PASS | Said it cannot collect and can only draft a request |
| Installed vs usable capability distinction | FAIL | Called 53 generic installed skills "usable" without validating their dependencies/access |
| Clean operation without retries | FAIL | Reproduced inspect.py stdlib shadowing; source rename is not live |
| Knowledge import and selected-view behavior | NOT RUN | Neither the new skill nor view is deployed |
| Additional plugin use / utility routing | NOT RUN | No new plugin/provider was enabled for this test |

The wording also says existing evidence is availability-only before acknowledging
Security Hub samples. The summary should distinguish discovery records from sampled
findings consistently and say "no agent-triggered collection" rather than imply
the separately deployed collector does not exist.

## Artifacts and conclusion

Also navigated the native Models, Skills and Plugins pages through the browser:

- Models shows the existing main route and **12 auxiliary tasks, all auto**.
  This confirms UI visibility, not a separately tested utility model. The Mixture
  of Agents card displays reference defaults; that is not proof those providers
  are authenticated or were called.
- Skills shows **54/54 enabled**, including shared-evidence. The newly committed
  ce-knowledge and ce-source-tools skills are not deployed.
- Plugins displays bundled plugin status and enable/disable controls. No controls
  were changed. A plugin marked enabled may still require configuration before
  its behavior activates; no new plugin execution was tested.
- Private artifacts: `ui-models`, `ui-skills`, `ui-plugins` text/PNG pairs and
  `ui_settings_check.py`, in the same private artifact directory.

Private browser text and screenshots: `.rgce/native-sketch/ui-capabilities.txt`
and `ui-capabilities.png`; automation script: `ui_capabilities.py`. These may
contain account details and are not release artifacts. Saved UI text is a terminal
rendering, not an authoritative tool transcript; it is used here for visible UX.

The live agent follows the single-profile instruction and mostly acknowledges
missing capabilities. The intended source-to-answer and selected-knowledge flows
are not ready for user acceptance. Deploy the implementation and test actual
ingestion/retrieval, execution receipts, extension exposure and model routing
before claiming those capabilities are honored.
