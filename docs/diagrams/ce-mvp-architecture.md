# CE MVP architecture diagram

Open [the interactive diagram](ce-mvp-architecture.html), or view the [README image](ce-mvp-architecture.png). The [editable Archify specification](ce-mvp-architecture.json) is the source.

This is a component/control-flow overview, not an exhaustive network topology. The preview baseline is AWS **us-east-1** and **Qwen 3.8 Max**, using the operator's own AWS/model credentials.

## How to read it

- Choose workstation Docker **or** AWS Spot for the same native Hermes `ce-desk` experience. The AWS execution/storage backend is still needed with workstation Docker.
- Hermes loads skills and selected organizational context. Its CE runtime plugin admits bounded tools; the independent Lambda reader enforces supported operations and scoped IAM. Return values and receipt references travel back through that tool call; return arrows are omitted for readability.
- Existing security sources must be enabled and accessible. A listed source is not a claim that findings have already been collected.
- Scheduled checks use EventBridge Scheduler and a deterministic orchestration Lambda independently of Hermes. Frequency and enabled state are deployment inputs.
- S3 preserves evidence and published knowledge views. Knowledge is explicitly selected and activated; publication alone does not change a running session's context.
- Hermes conversations and Kanban cases use the retained Docker volume or EBS volume. They are not automatically restored from the evidence bucket.
- The output is a supported investigation, a prepared remediation proposal and follow-up/reassessment. The operator applies cloud changes.

## Implementation references

| Diagram element | Implementation |
|---|---|
| Workstation runtime and scoped credentials | `tools/native_workstation.py`, `deploy/aws-workstation/main.tf` |
| Spot, EBS and Secrets Manager inputs | `deploy/aws-native-sketch/main.tf` |
| Tool admission and shared critic context | `profiles/native-sketch/desk/plugins/ce-runtime/__init__.py` |
| Deterministic AWS operations | `modules/aws-read-executor/executor.py`, `operations.json` |
| Independent scheduled collection | `modules/assurance-schedule/main.tf` |
| Knowledge collections and publication | `rgce/knowledge_library.py`, `rgce/knowledge_publish.py` |
| Skills and remediation guidance | `profiles/native-sketch/desk/skills/` |

## Artifact checks

Generated with the installed [Archify](https://github.com/tt-a1i/archify) skill, using newly authored CE-specific content.

- Architecture validation: **9/9 showcase checks; zero errors and warnings**.
- Browser evidence: **passed** at 1440×900, 1600×1000, 1920×1080 and 2048×1320. No page overflow.
- Visual review: **passed** after inspecting light and dark screenshots at both endpoint sizes. No node/label crossings, clipped cards or conspicuous empty lower band. No visual correction rounds were needed.
- The README PNG is an exact copy of the 2048×1320 light browser capture. It includes the viewer chrome; it is a screenshot, not a canonical SVG export.
- [Delivery receipt](ce-mvp-architecture.delivery.json) binds source/artifact bytes. [Browser receipt](ce-mvp-architecture.visual-check.json) records measurements. [Contact sheet](ce-mvp-architecture.visual-check.html) shows the four screenshots.

Specification SHA-256: `d836a2580c6660787252f41758642878ee455555b9623867c8542f671efd4d2f`

HTML SHA-256: `7c5e8fe2df6c9da8c353ecee6840d7e8be97afa2fb04e80c09b5bbc40c5736c6`
