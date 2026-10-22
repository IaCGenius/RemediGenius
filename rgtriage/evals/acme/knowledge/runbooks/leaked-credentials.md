---
type: Runbook
title: Leaked or misused credentials
description: First steps when keys or role credentials are used from outside Acme.
generated: {by: "human:eval", at: "2026-10-01T00:00:00Z"}
verified: [{by: "human:eval", at: "2026-10-01T00:00:00Z"}]
---

1. The operator revokes the role's active sessions (an inline deny on aws:TokenIssueTime) or deactivates the key.
2. Look up the calls in CloudTrail by access key id and list what was read.
3. Notify the Security team in #sec-incidents within 1 hour.
