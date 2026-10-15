# Retired CE analyst profile

Historical source retained on 2026-10-13. This directory is not part of the native
deployment bundle and is not installed as an active CE profile. Its investigation
behavior is now part of `profiles/native-sketch/desk/SOUL.md`.

On an existing native deployment the old analyst home, including conversation
databases, is moved to `/data/hermes/retired-profiles/ce-analyst-<timestamp>` while
the gateway is stopped. It is preserved for recovery, not loaded as a second CE
agent. The upstream default profile is still an upstream implementation detail;
`ce-desk` is the single configured CE entry point.
