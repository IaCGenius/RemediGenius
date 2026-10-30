# Operational relationship graph

Typed, scoped, time-aware edges between things that exist in AWS and in the installation. It answers "what runs this
image", "which workloads share this base package", "which plan touched this target" — with the evidence for the answer
and the time it was true.

Not a graph database: assertions live in one Iceberg table (`relationships`) and are queried through the desk.

## Identity is scoped

| Kind | Identity | Scope |
| --- | --- | --- |
| `image` | `sha256:` digest (a tag is refused) | platform, registry |
| `package` | `purl` or `cpe` | — |
| `workload`, `deployment`, `finding`, `plan`, `resource` | the installation's id | account, region, resource type |
| `owner` | team or person id | — |

The entity key hashes kind, identity *and* scope, so two workloads called `api` in different accounts are two entities,
and an image tag that now points somewhere else cannot silently inherit the old edges.

## What may be believed

| Status | Meaning | Authoritative | Can authorize closure or execution |
| --- | --- | --- | --- |
| `observed` | someone saw it; requires retained evidence | yes | yes |
| `derived` | an approved deterministic derivation; requires its version | yes | yes |
| `hypothesis` | a suggestion, including anything an LLM proposes | no | **never** |
| `retracted` | withdrawn; must name the assertion it supersedes | no | no |

`explain(edge)` returns the evidence ids or the derivation version, so an authoritative edge can always be traced to
something retained. A hypothesis is stored and visible, and `may_authorize()` is false for it by construction.

## History and rebuilds

The table is append-only. A retraction or a correction is a new row with its own deterministic id that supersedes the
old one; the old row stays readable, and `current()` returns only the latest authoritative, currently valid edge per
`(subject, predicate, object)`.

Derivations are deterministic functions with a version (for example `ce.image-contains-package/v1`), so replaying the
same inputs produces the same assertion ids and a rebuild is idempotent. A rebuild carries a cursor
(`version`, `last_event`, `complete`): if it is interrupted, the previous complete graph stays active instead of being
replaced with a partial one.

Graph freshness is reported on its own (`graph_lag`) — how far the graph is behind the latest event — and says nothing
about whether AWS is healthy.

## Queries

- `relationships(subject|object, predicate, status, as_of, limit)` — edges touching an entity key or identity, filtered
  by predicate, status or validity time; retracted rows are hidden unless asked for. Every row carries
  `authoritative`, and the answer carries the graph's own freshness block.
- `graph(entity, depth, limit)` — bounded neighbourhood: depth is capped at 2 and the edge count at the query limit, so
  "explore the graph" cannot turn into an unbounded walk.

Relationships pointing at an image or package are derived by CE-20's lineage ingestion; campaign membership and
deployment receipts arrive from CE-16 and CE-17. Nothing in this layer writes AWS, and there is no LLM write path to
observed edges.