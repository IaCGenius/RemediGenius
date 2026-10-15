# Diagram 1: Hermes-first control-flow outline

Status: proposed direction, not the deployed rc10 architecture. Open [the Archify diagram](hermes-first-control.html).

## Major components and boundaries

- **Operator:** native Hermes interface, or a small optional wrapper.
- **Agent-runtime boundary:** upstream Hermes with CE skills. Owns conversation, planning, capability selection and coordination. Skills are inside this boundary, not a second workflow engine.
- **Model provider:** outside the agent runtime; accessed through Hermes' native provider support.
- **Execution boundary:** independently enforced kiosk controls and scoped runtime roles. The gate is existing platform machinery to reuse, not a proposed replacement for Hermes reasoning. A request to run an approved function is distinct from submitting newly generated code.
- **Disposable compute:** approved collectors or processors. They read the permitted source and write results, then finish.
- **Existing AWS sources:** native findings, configuration and explicitly enabled telemetry. Source-read permissions are separate from permission to run compute.
- **Durable S3/object storage:** evidence, reviewed knowledge, coverage and receipts. It survives compute replacement and has its own access policy; it is not inside the Hermes process.

## Numbered control flow

1. **Ask:** the operator gives Hermes a question or goal. Later, a configured heartbeat can trigger the same skills.
2. **Investigate:** Hermes selects a skill, retrieves relevant existing knowledge/evidence and uses the model to plan. If existing information is sufficient, it can answer without collection.
3. **Request work:** if something is missing, Hermes selects an existing tool/function and submits a bounded work request. No collection is necessary merely because the diagram includes compute.
4. **Execute:** platform checks and runtime IAM constrain dispatch, source scope and budgets. The approved worker reads the specified AWS source.
5. **Save:** the worker persists outputs, timestamps, coverage/errors and receipts in object storage. It can then disappear.
6. **Reason and respond:** Hermes retrieves the new results, applies applicable knowledge, explains uncertainty and returns a cited answer or proposal. No production remediation is implied.

Green arrows show control requests/dispatch. Grey arrows show retrieval, persistence, source access and model calls. Responses along request connections, model iteration, final operator response and saving an agent-authored decision are omitted as separate return arrows to keep the first overview legible. This is a component/control-flow outline, not a complete sequence or network/IAM diagram.

## Next diagrams, one at a time

2. **Inside the Hermes boundary:** skills, tools/CLI, shared knowledge, native sessions and optional MCP integration.
3. **Build versus run:** reuse registry; builder generates a missing capability; kiosk validates/signs/promotes; runtime executes with scoped rights.
4. **Persistence and refresh:** original evidence, knowledge variations, generated summaries, expiry and recovery after compute loss.

Do not implement another platform from this overview before reviewing the responsibility boundaries with the owner. Keep the previously built work preserved.

## Diagram evidence

Archify architecture, showcase profile. Nine artifact checks passed, zero composition errors/warnings. Automated browser checks passed at 1440×900, 1600×1000, 1920×1080 and 2048×1320. Large light and laptop dark renders were visually inspected; the boundaries, labels and connections are readable and unobstructed. Editable JSON, delivery hash receipt, screenshots and browser receipt are stored beside the HTML.
