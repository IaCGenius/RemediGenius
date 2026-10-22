# Scope and limits — RemediGenius Community Edition

## Your responsibility

RemediGenius Community Edition (RemediGenius-CE) is provided as-is under the Apache-2.0 license, without warranty.
You choose and configure your model provider, AWS accounts, IAM, regions and storage. You are responsible for what data
reaches your model provider, for every change you make to your cloud, and for AWS and model charges.

## What it does and does not do

- **Reads, never writes AWS.** Fixes are proposals (diffs, CLI commands) that you review and apply.
  `terraform validate` checks syntax and provider schema only; it is not a plan and not an approval.
- **Sources are the AWS security services you enable.** RemediGenius-CE has no detectors of its own. A source that is
  off, denied or unavailable is reported as a blind spot, never as "clean".
- **Volumes are capped, and the caps are stated.** Detail is read up to `detail_limits` per source/account/region,
  totals come from aggregation APIs where AWS offers them, and capped tiers are labelled "at least N".
- **Priorities are a transparent heuristic,** not a risk assessment of your business. Reviewed knowledge concepts
  (applications, accounts, risk exceptions, goals) and `triage.yaml` change them; the reasons always cite what did.
- **Improvement is offline and gated.** Skills change only after evaluation on the fixed Acme organization, the
  security gate and your approval; the evaluation set is small, so the gate is conservative. See [IMPROVEMENT.md](IMPROVEMENT.md).
- **Knowledge is what people put in.** Search is lexical, matching uses exact tags and ids, and the agent's drafts are
  only applied after a person approves them. See [KNOWLEDGE.md](KNOWLEDGE.md).
- **Investigations are bounded.** CloudTrail `LookupEvents` covers 90 days of management events per region. S3/Lambda
  data events are not visible through it; the agent says so.
- **Evidence has known gaps.** Service control and resource control policy texts are readable only from the management
  or a delegated administrator account; from a member account the IAM simulator's verdict is the evidence. Network
  reachability is assembled from security groups, routes, NACLs and load balancers (Reachability Analyzer is not run).
  Whether data is sensitive comes from Macie findings, tags or knowledge; the desk never reads object contents.
  Each AWS read says its account, time and whether it was complete; the agent labels what it inferred.
- **Decisions are local triage records.** They do not archive or suppress findings in AWS.
- **Single operator.** The dashboard has one login and is reachable only on localhost (workstation) or through SSM
  (Spot). It is not a multi-user or multi-tenant service.
- **Durable state, not zero loss.** Checkpoints run every 2 minutes and after scans and decisions. A crash or
  interruption can lose the last moments of chat activity.
- **IaC matching is evidence-ranked.** Low-confidence matches must be confirmed. Resources created outside the indexed
  repositories are reported as such, with an import snippet.

## Data that reaches your model provider

Finding titles, resource identifiers, account ids, tags, CloudTrail excerpts the agent reads, your IaC excerpts,
knowledge concepts the agent reads, documents you choose to *Draft with AI* (the Knowledge tab shows the token estimate
and asks first), your chat messages, and (only when you run evaluate, optimize or probe) replays of the fictional evaluation
organization plus redacted lesson excerpts from your traces. Self-hosting compute does not make inference local. Choose a provider and retention policy your
organization permits; see [MODELS.md](MODELS.md).

## Upstream prompts

Hermes may show **Help improve Hermes? Send to Nous**. This is an upstream opt-in, not RemediGenius-CE telemetry;
choose **No thanks** if you do not want it. RemediGenius-CE itself collects no telemetry.
