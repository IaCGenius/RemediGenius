# One Hermes profile for CE

Owner decision and deployment: 2026-10-13.

`ce-desk` is the single configured CE profile. It handles concise summaries,
investigation, scoped organizational knowledge and remediation proposals in one
conversation. The identifier stays unchanged so existing links and desk history
continue to work. Open a new chat after updating to load the combined instructions.
The upstream default profile is not a configured CE agent.

Profiles control behavior and configuration, not IAM authority. Deterministic
collection, read-only evidence and the independent execution boundary remain
separate. Organizational knowledge integration is still limited by the capabilities
documented in NATIVE-HERMES-SKETCH.md; prompt changes do not implement retrieval.

The former analyst source is preserved under `docs/archived/native-analyst-profile`.
Cloud bootstrap stops the gateway before moving an existing analyst home to
`/data/hermes/retired-profiles/ce-analyst-<timestamp>`. Its files are retained outside
the active profile list. No conversations are deleted or merged into desk history.

Validated on the replacement CE Spot host:

- Bootstrap completed; native gateway active.
- Active CE profile directories: exactly `ce-desk`.
- Combined instructions present; desk session database preserved.
- One archived analyst home retained on the persistent volume.
- Python bootstrap syntax and four existing evidence-helper tests passed.

Deployment bundle SHA256:
`e1c739eea82a80e8d77af44aeae6b5c08f406b04172dec1f5e3393c1bc5450d9`.
Private deployment and verification records are under `.rgce/native-sketch/`.
This change does not claim a new end-to-end model acceptance test; the existing
0.21.7 live model test is documented in NATIVE-HERMES-UPGRADE-0217.md.

V2's optional multi-profile design is documented separately in its
`docs/ideas/2026-10-13-hermes-profiles-ce-and-hosted.md`. No v2 runtime was changed.
