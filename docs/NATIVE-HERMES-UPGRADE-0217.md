# Native Hermes 0.21.7 upgrade

Owner direction: upgrade Hermes first; no Snyk or additional external API
integrations. Memory Wiki is only a future candidate, not part of this upgrade.

The official [latest release](https://github.com/NousResearch/hermes-agent/releases/tag/v0.21.7)
was checked on 2026-10-13. A temporary container with no network, credentials or
session volume reported Hermes 0.21.7, upstream `71d34bad`.

Pinned image:

```
nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b
```

The digest fixes the bytes even though the readable tag is `stable`. The previous
0.21.5 pin remains in Git history. Before upgrading, the gateway was stopped and
the session filesystem flushed; an encrypted EBS recovery snapshot completed.
Snapshot identifiers and detailed AWS results are retained privately under
`.rgce/native-sketch/`. Terraform reviewed changes were limited to the native CE
launch template and ASG. No v2 resources or model-provider credentials changed.

## Profile simplification recommendation

`ce-desk` and `ce-analyst` are agent profiles, not user accounts or IAM roles.
Their current value is different instructions and conversation histories: brief
orientation versus deeper investigation. They share tools, the model credential,
and read-only evidence, so they provide no privilege separation.

For initial CE, prefer one main agent with both behaviors, selected by the user's
question. Keep the deterministic collector and any future builder/execution role
separate because those boundaries concern actual permissions. Profile consolidation
is a recommendation; this runtime upgrade preserves the existing profiles/history.

## Memory and knowledge boundary

- Conversations: useful historical context; not authoritative security facts.
- Reviewed organizational knowledge: explicit business context, scope, variations,
  review status and sources in our own knowledge layer.
- AWS evidence: original observations and deterministic transforms with receipts.
- AI interpretation: labelled drafts that cite the preceding layers.

If evaluated later, Memory Wiki should be a view over conversation history and
memory, not a second approval process or a replacement knowledge store. No automatic
promotion of conversation statements into reviewed knowledge, and no rewriting of
AWS observations. The CE profiles currently disable native persistent-memory
features; this upgrade does not enable them or install Memory Wiki.

The existing bootstrap `--force-config` behavior remains a known onboarding gap.
Before users customize profiles, replace that behavior with an explicit distinction
between packaged defaults and preserved user settings. A retained disk alone does
not protect settings from application-level overwrite.

## Live acceptance — 2026-10-13

- Replacement Spot host bootstrapped successfully; native gateway and hydration
  timer are active. Running Hermes and native dashboard both report **0.21.7**.
- Native browser login and chat worked with the existing model. The dashboard
  initially showed Off during startup, then Running with an active session.
- Browser acceptance session `20261013_171114_d5b159` loaded `shared-evidence`,
  read the real normalized Security Hub sample and compared two receipts to pick
  the newer observation. Its completed answer correctly reported CRITICAL 2,
  HIGH 2, MEDIUM 1, LOW 15, `returned_count: 20`, and `has_more: true`, with an
  evidence path, receipt, producer and the bounded-sample limitation.
- The browser capture occurred while reasoning was still underway; the completed
  answer was verified separately from that exact session's persisted database.
  Private captures and SSM results remain under `.rgce/native-sketch/`.
- Existing session databases and the prior model trace survived replacement.
- Isolation recheck: no AWS credentials in the agent environment; evidence writes
  fail on the read-only mount; metadata and private-host requests are blocked.
  Both CE profiles retain disabled persistent memory and empty MCP configuration.
- No Snyk, new external integration, or Memory Wiki was installed. The new
  telemetry prompt was declined in the test browser.

This validates this upgrade and one bounded native-chat workflow, not general CE
release readiness. In particular, the profile customization issue above and the
unfinished capabilities documented in NATIVE-HERMES-SKETCH.md remain outstanding.
Retained EBS is session persistence; S3 evidence storage is not a session backup.
