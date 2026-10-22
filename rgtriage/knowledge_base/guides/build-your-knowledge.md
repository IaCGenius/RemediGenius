---
type: Guide
title: Build on this knowledge
description: What the shipped OKF knowledge gives you today, and how adding your own concepts changes what the desk does.
tags: [remedigenius, knowledge, okf, getting-started]
sources:
  - {id: okf, resource: "https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md", title: Open Knowledge Format v0.2, author: org:google-cloud}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

# What ships with RemediGenius-CE

The `remedigenius/` folder is a small security knowledge base in Open Knowledge Format,[^okf] linked so you can
explore it as a graph:

| Layer | Concepts | Answers |
|---|---|---|
| Frameworks | [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md), [AWS Foundational Security Best Practices](/remedigenius/frameworks/aws-foundational-security-best-practices.md) | Which baseline does this finding come from? |
| Practices | [identity and root](/remedigenius/practices/identity-and-root.md), [logging and detection](/remedigenius/practices/logging-and-detection.md), [data protection](/remedigenius/practices/data-protection.md), [network exposure](/remedigenius/practices/network-exposure.md), [vulnerability and patching](/remedigenius/practices/vulnerability-and-patching.md), [incident readiness](/remedigenius/practices/incident-readiness.md) | Why does it matter, which controls check it, how is it ranked? |
| Source guides | one per finding source, for example [GuardDuty](/remedigenius/sources/guardduty.md) | What does this service see, and what can it not see? |
| Playbooks | for example [S3 public access](/remedigenius/playbooks/s3-public-access.md) | How do I verify and fix it in code? |
| Guides | [how the desk works](/remedigenius/guides/how-the-desk-works.md), [where to look](/remedigenius/guides/where-to-look.md), [organization knowledge](/remedigenius/guides/organization-knowledge.md) | How do I investigate, and how does knowledge change triage? |

Every finding's control id maps to its practice, so `rgtriage show`, `rgtriage fix` and the agent tell you which
practice a finding belongs to and link the playbook. This part is generic: it is the same for every organization.

# What only you can add

The benchmark knows a bucket is public; it does not know the bucket is your marketing website, that `payments-db`
holds card data, or that the platform team must be paged at night. That is what your concepts add, and each one
changes something you can see:

| You add | The desk then |
|---|---|
| Application (tags, criticality, data, owner) | ranks findings on those resources by business impact and names the owner |
| Account (id, environment, criticality) | separates production from sandbox for every finding in it |
| Team (contact, escalation) | tells you whom to call for a P1 |
| Risk Exception (control or resource, expiry, approver) | stops re-raising an accepted risk until it expires, then brings it back |
| Security Goal (resource types, signals) | raises what matters this quarter |
| Policy, Runbook | proposes fixes and steps that follow your rules instead of generic advice |
| Architecture, Note, Reference | answers "is this meant to be public?" and "what depends on it?" |

Start with the Knowledge tab's *What the desk is missing* list: it names the gaps that change priorities right now.

# Three examples to copy

```markdown
---
type: Application
title: Payments
description: Card payment API and its database (PCI scope).
remedigenius:
  match_tags: {app: payments}
  criticality: mission_critical
  data: cardholder data
  owner: /teams/payments-team.md
---
An outage or breach stops card payments for all customers.
```

```markdown
---
type: Risk Exception
title: Marketing website bucket is public
description: Static website content only; no customer data.
stale_after: 2027-03-31T00:00:00Z
remedigenius:
  control_id: S3.8
  resource: marketing-site-bucket
  expires: 2027-03-31
  approved_by: CISO
---
Compensating control: the bucket holds only build output from the website pipeline.
```

```markdown
---
type: Policy
title: No SSH or RDP from the internet
description: Administration goes through Session Manager.
---
Security groups never allow 22 or 3389 from 0.0.0.0/0 or ::/0. Fixes for EC2.53, EC2.54 and EC2.19 remove the rule
and add Session Manager access instead. Links: [network exposure](/remedigenius/practices/network-exposure.md).
```

Add them in the Knowledge tab (Add form, or Import a Markdown file), approve the drafts the agent writes when you tell
it something, or import your existing runbooks and policies as PDF or Word.

# Taking it further

- **Your own frameworks.** Add a Framework concept for PCI DSS, ISO 27001 or an internal standard, and Policy concepts
  that link controls to it; the agent can then answer "which open findings affect our PCI scope?" from the graph.
- **Version it.** The bundle is plain files: keep a copy in git and review knowledge changes like code.
- **Share it.** Any OKF tool can read it: render it, validate it, or serve it to other agents.
- **Keep it fresh.** Set `stale_after` on concepts that age (exceptions, contacts); the desk flags them when they expire.

[^okf]: Open Knowledge Format v0.2
