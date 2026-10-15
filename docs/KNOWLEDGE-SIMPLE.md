# Your knowledge: the everyday workflow

Open **Knowledge**. Write what RemediGenius should know, choose **Review this
guidance**, check the wording and where it applies, then choose **Use this guidance**.
You do not need concept IDs, hashes, YAML or a model key. Those details are generated
or kept under Advanced.

Use **Where it applies** when the guidance is specific to an application, environment
or component. Choose existing guidance if this is a contextual variation. Otherwise
the default is this local workspace; the review screen shows that explicitly.
You can add a review date and a name, but neither is required for a local note.

You are responsible for the accuracy and applicability of what you provide.
RemediGenius organizes it, checks supported relationships and surfaces some gaps;
it does not certify organizational facts. Keep guidance concise enough to review.

## Documents and AI help

**Add documents** opens file upload and the source library. Optional document
metadata is collapsed. Uploading preserves a source; it does not automatically
turn the document into approved guidance.

Under **Use my AI to draft or review knowledge**, choose a document and prepare a
review request. Copy it to Hermes or your chosen assistant. You control whether
that content is shared with its model. Connected MCP agents can call the read-only
`prepare_knowledge_review` tool instead, using a selected source or concept ID.

Bring the assistant's suggestion back by pasting its reply or loading its JSON/text
response file. A plain-text response is also accepted as draft wording. Structured
responses can include title, statement, scope, baseline_id and source_ids. Review
the result and confirm before use. Imported AI suggestions remain drafts.

Every saved guidance card also has **Review with my AI**, **Edit** and **Download
Markdown**. The console prepares context and receives suggestions; it does not
run a model, manage provider keys or introduce another inference client. It uses
the user's existing AI workflow. Review briefs bound source excerpts to 12,000
characters and disclose truncation; the agent can retrieve more using get_record.

## Review in ordinary files

Open **Review as Markdown files → Prepare review folder**. The console shows the
actual path. By default it is:

```text
RGCE_HOME/knowledge/review/README.md
RGCE_HOME/knowledge/review/<version>.md
```

The README links readable Markdown/OKF copies by title. Open these in any text
editor or let your agent read them. Run Prepare review folder again to regenerate
the current index and copies. Earlier version files can remain for history; the
current README is the entry point.

**Direct edits to generated review files, originals or the internal database are
discouraged.** Generated copies are not the active knowledge store. Editing them
does not change what investigations use. Prefer Edit in the console; for file-based
changes, edit a downloaded copy and import/review it under Advanced. Never have an
agent edit the SQLite database to update knowledge.

## Navigation

- **Workspace:** investigate findings and prepare proposals.
- **Knowledge:** notes, reviewed guidance and optional AI/document/file workflows.
- **Connections:** existing tools and agent configuration.
- **More:** evidence library and information about this edition.

Assessment-only notes and the detailed OKF editor remain in collapsed sections.
The deterministic applicability, source refresh and historical receipts from rc3
remain intact; see KNOWLEDGE-QUICKSTART.md for those advanced operations.
