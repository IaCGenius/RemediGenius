# Shared knowledge: sources, concepts and receipts

**Historical console workflow.** For the current native Hermes CE use
[current offering](CURRENT-CE-OFFERING.md) and
[native knowledge staging](KNOWLEDGE-USE-AND-CONTROL-MAPPING.md).
Console uploads and SQLite concepts below are not the native chat's intake path.

For rc3's implemented concept authoring, reuse, variations and refresh, follow
[Reusable knowledge in CE](KNOWLEDGE-QUICKSTART.md). The intake details below remain
applicable; earlier statements about future concept support describe the rc2 baseline.

See [Knowledge foundation](KNOWLEDGE-FOUNDATION.md) for the proposed reuse,
contextual-variation and refresh lifecycle and its distinction from current intake.

The initial assessment-only note is too narrow for an organizational second brain.
Policies, architecture, ownership, runbooks and decisions should exist independently
of a scan. An investigation selects the relevant versions and cites them.

Only design concepts were borrowed from the local ai-memory experiment: an intake
inbox, typed concepts, human promotion, generated navigation and a replaceable
search index. No personal memory entries, curated content, index or code were copied.

## Useful entry points

| Entry point | Now | Next |
|---|---|---|
| Drop/upload files | Multi-file console upload, local conversion | Conversion queue and richer preview |
| Paste text | Saves a Markdown source without an assessment | Typed reusable concept templates |
| Folder import | Explicit CLI import of a flat folder, up to 50 supported files | Opt-in watched inbox, never broad machine scanning |
| Git repository | Existing committed Terraform snapshot reader | Versioned Markdown/runbook Git connector |
| Hermes attachment | Native chat can hold attachments; no automatic CE ingestion | Explicit “add this attachment to knowledge” adapter |
| Web links | Not fetched by CE intake | Separate fetcher with redirect, network and scope controls |
| Drive / SharePoint / Confluence | Not connected | Selected folders/pages, source permissions and change tracking |

Uploading a file into a chat is not equivalent to preserving an organization-wide
source with versioning, review state and portable provenance. Keep the CE intake
pipeline independent of the chat runtime. A future Hermes attachment adapter should
submit the selected bytes and metadata to this same pipeline; it must not silently
import all chat attachments or promote the agent's interpretation.

## Conversion choices

Use [Microsoft MarkItDown](https://github.com/microsoft/markitdown) as the initial
Python adapter. CE calls the narrow byte-stream API with plugins and cloud/model
clients unconfigured. Selected extras support PDF, Word, PowerPoint and Excel;
plain UTF-8 Markdown/text are preserved directly. No custom Office/PDF parsers.

[Docling](https://docling-project.github.io/docling/) is a good optional candidate
for complex PDF layout, table extraction and OCR. It should be a separately installed
converter, evaluated on representative documents. Do not install another heavy
pipeline for every user by default. Cloud document/OCR services can be explicit
options later, with provider choice, data disclosure and cost visible before use.

MarkItDown supports more formats than CE enables. v0.1 intake deliberately accepts
MD, TXT, CSV, PDF, DOCX, PPTX and XLSX. No ZIP upload, executable, macro-enabled Office,
audio/video or URL conversion. Scanned/image-heavy PDFs may need OCR; an empty
conversion is marked `needs_ocr_or_review`, never summarized as if complete.
Nonempty extraction is also not a guarantee of completeness.

## Organization

The first library uses two explicit fields rather than guessing with a model:

- **Topic:** policies, architecture, ownership, runbooks, decisions, exceptions, other.
- **Scope:** organization, an account, an application or another user-chosen label.

Owner is optional. Scope labels are retrieval metadata, **not access controls**;
separate customer workspaces still require separate RGCE_HOME directories. Sources
can later produce multiple small concepts: a policy requirement, a service owner,
an architecture constraint or an accepted exception. Do not convert a 70-page
document into one giant approved “memory.”

```text
RGCE_HOME/
  evidence.sqlite3                    CE records and approval receipts
  knowledge/
    originals/<source-sha>/source.ext immutable through intake; original bytes
    documents/<record-hash>/
      content.md                     readable conversion
      receipt.json                   scope, topic, original/conversion hashes, converter
```

Original files are copied, never moved or deleted. Repeated identical bytes and
metadata deduplicate. Changed bytes or metadata produce another source record.
All versions remain available; current-version/supersession selection is not yet
implemented. The user chooses a source version when citing it in a note.

The CE record is authoritative in this implementation; generated Markdown is an
export of that record, not an independently editable second authority. Edits must
be reimported as a new source. This differs from ai-memory's Markdown-authoritative
workflow and avoids silently changing existing evidence/approval semantics.
Future curated concept files can be made portable with the same explicit import
and review contract. Search is currently literal-word filtering over the newest
500 source records, not vector search. A future index must be rebuildable from
durable source/concept records and never determine truth.

## Trust lifecycle

1. Receive source → validate type and limits → preserve original bytes.
2. Convert locally → preserve Markdown and converter version/hash receipt.
3. Show **source document / unreviewed** and extraction limitations.
4. Human or agent proposes a small insight, citing exact source hashes.
5. Human reviews the insight, its scope and supporting source. The existing
   exact-assessment approval flow now carries document source citations.
6. Retrieve only relevant versions for the investigation. An agent must distinguish
   unreviewed source assertions from approved context and its own interpretation.

Approving one insight does not approve every statement in its source document.
Organization-wide approved concepts, expiry, supersession and conflict resolution
are the next step; this update implements reusable sources, not that full lifecycle.

## Running it

```powershell
.\.venv\Scripts\python -m pip install -e ".[aws,mcp,documents,test]"
.\.venv\Scripts\python -m rgce documents C:\selected\folder --topic policies --scope organization --owner "Security team"
```

Folder import is nonrecursive, skips symlinks and unsupported extensions, and stops
on an error; earlier successful files remain imported. The console accepts up to
20 files per selection, processed sequentially. Each file is limited to 5MB,
Office containers to 30MB expanded/2,000 entries, converted text to 2MB, and a worker
to 45 seconds. Failed conversion retains the hashed original but creates no
searchable source record. Review this storage when troubleshooting failures.

The worker receives bytes and a small environment without model/cloud credentials.
It does not receive user-selected URLs or arbitrary parser paths. This is a
subprocess, **not an OS sandbox**; parsers have local process privileges, and timeout
is not a hard memory limit. A network-disabled, resource-limited container worker
is the production hardening path for untrusted documents. Do not advertise malware
scanning or guaranteed secret detection. Uploaded text is always untrusted data.

For actual use, exception handling and remaining release gates, see
[Knowledge use and exception decisions](KNOWLEDGE-USE-AND-EXCEPTIONS.md).

Agents get the read-only `search_knowledge_sources` MCP tool and retrieve selected
records through `get_record`. They do not get upload or approval tools. Clients can
request more text using the returned next_offset. Document excerpts default to
12,000 characters, capped at 16,000 per call, to avoid injecting an entire source
library into the model context. The source hash always identifies the full record.
Humans may
use the local UI/CLI intake; future writable agent intake should be inbox-only,
separate from approval and explicitly authorized.
