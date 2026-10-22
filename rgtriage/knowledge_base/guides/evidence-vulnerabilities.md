---
type: Guide
title: "Evidence: vulnerabilities"
description: Whether a CVE finding matters here - affected package and version, fix availability, exploitability and reachability of the host.
tags: [remedigenius, evidence, inspector, cve]
sources:
  - {id: insp, resource: "https://docs.aws.amazon.com/inspector/latest/user/findings-understanding.html", title: Understanding findings in Amazon Inspector, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "do we need to patch this now?", "is this CVE exploitable here?", "which hosts are affected?".

## Reads that decide it
1. The finding: package name, installed and fixed version, `exploitAvailable`, EPSS, Inspector score[^insp]
   (`rg_triage action=show`).
2. Still present: `inspector2 list_findings` filtered by the finding ARN or resource id; `lastObservedAt`.
3. Exposure of the host: the network-exposure reads for the instance or image (public path, listening port).
4. Fleet size: `inspector2 list_findings` filtered by `vulnerabilityId` across resources.

## Limits to say out loud
- Inspector reports installed packages, not whether vulnerable code paths run.
- Container image findings describe the image, not every running task; say which.

## Stop when
You can state version → fixed version, exploitability, and whether the host is reachable, or which of those is unknown.

Related: [vulnerability and patching](/remedigenius/practices/vulnerability-and-patching.md) ·
[network exposure evidence](/remedigenius/guides/evidence-network-exposure.md)

[^insp]: Understanding findings in Amazon Inspector
