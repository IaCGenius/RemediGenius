# rc2 knowledge intake validation

This increment adds a local document-source library alongside the existing reviewed
assessment notes. Only architecture/protocol concepts were read from the reference
memory experiment; no curated memory, index or personal document was ingested.

Verified with synthetic data:

Final checks: 64 core/adapter/document/MCP/privacy tests passed, alongside 30
kiosk tests and 38 rule cases. Browser smoke passed. `pip check` reported no broken
requirements, and the rc2 wheel built successfully.

- MD/TXT source preservation, repeat-import deduplication, source/conversion hashes
  and portable Markdown/receipt files.
- Actual MarkItDown 0.1.8 conversion of PDF, DOCX, PPTX, XLSX and CSV fixtures.
- Rejection of path/URL filenames, unsupported ZIP/macro formats, invalid PDF and
  oversized input; renamed macro-bearing Office containers rejected.
- Source upload requires the local session token. Upload does not approve knowledge.
- Approved insight notes pin document source IDs; approving an insight leaves its
  source unreviewed.
- MCP search and bounded excerpt retrieval preserve provenance and unreviewed status.
- Browser upload, pasted source, search, source selection and existing review flow.
- Existing community/rule/kiosk tests continue to pass.

Limitations remain explicit: parser subprocess is not an OS sandbox; no OCR,
automatic secret screening, watched folder, native Hermes attachment bridge,
connector synchronization, global approved-concept lifecycle or semantic index.
The conversion library is an optional `documents` dependency group. No LLM or cloud
OCR client is configured, and no real customer documents were used in validation.

The prior rc1 receipt remains historical. See KNOWLEDGE-INTAKE.md for the design,
supported entry points, organization, trust lifecycle and deployment limits.
