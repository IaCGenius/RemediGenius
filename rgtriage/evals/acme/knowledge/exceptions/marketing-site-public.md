---
type: Risk Exception
title: Marketing website bucket is public
description: Static website content only; no customer data.
stale_after: "2099-01-01T00:00:00Z"
generated: {by: "human:eval", at: "2026-10-01T00:00:00Z"}
verified: [{by: "human:eval", at: "2026-10-01T00:00:00Z"}]
remedigenius:
  control_id: S3.8
  resource: acme-marketing-site
  expires: "2099-01-01"
  approved_by: CISO
---

The bucket holds only build output from the website pipeline.
