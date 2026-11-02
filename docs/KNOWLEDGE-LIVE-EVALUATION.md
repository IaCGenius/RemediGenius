# Knowledge live evaluation — 2026-11-01

Status: working changes for maintainer review, not a released or fully certified connector feature.

The baseline was the published v0.7.0 archive, deployed on a newly created disposable AWS Spot stack.
Host checks passed before changes. Each patch was copied from the local working tree with a SHA-256 manifest;
the lab retains baseline backups. Private identifiers, manifests, screenshots and transcripts remain in ignored
`.rgce/knowledge-live-20261101/` and `/data/rg-lab/` on that lab. No maintainer stack was changed.

## Changes and practical benefit

| Change | Benefit | Live evidence |
| --- | --- | --- |
| Knowledge Sources screen links to Hermes connection manager | Reuse existing catalog/OAuth flows instead of writing provider clients | Nine configured connections rendered; native MCP page opened; no browser JavaScript errors |
| Source URI and revision on imports | Keep the original document identity with the captured Reference | Canonical URI and revision retained; same revision deduplicated; changed revision created a separate unreviewed Reference |
| Explicit source links in generated concepts | Let OKF graph traversal follow the document behind a claim | All three live drafts passed positive source-link assertions; Application owner link matched the Team's actual target |
| Resolve owner against unique Team concepts/drafts | Avoid an Application pointing at an invented Team path | Initial live owner path differed from generated Team; repeated model drafting after the fix produced the correct Team path |
| Separate public-document requests from account briefings | Avoid unrelated account details in knowledge answers | Same live AWS documentation request replayed after guidance change; unrelated account names and incorrect API alias absent |

Source URI fields preserve citation metadata; they do not fetch the URL. They reject userinfo, query strings,
fragments and control characters. Existing OKF files/bundles carry their own source metadata. Imported content
and generated concepts remain unverified until human review. Missing or ambiguous owners remain names requiring
review, rather than automatically becoming graph links. Review Teams before Applications that depend on them.

## What ran

- AWS Knowledge and DeepWiki connected using native Hermes MCP installation/testing. AWS Knowledge returned
  real AWS documentation and the running agent used it in an answer. DeepWiki returned Prowler's repository
  structure (866 characters) through its existing read tool; this is not a repository-content quality evaluation.
- The native converter imported fictional PDF, DOCX, PPTX and XLSX files. TXT, CSV and Markdown imports also
  passed. Every resulting Reference retained the expected sentence and remained unverified. This exercises
  small text fixtures, not scanned PDF OCR, complex tables, embedded media or maximum-size documents.
- Six live provenance assertions passed, including revision identity, deduplication and rejection of a
  credential-like query URL. The model drafted an Application, Team and Runbook from fictional organization text.
- Two focused local regression checks passed for valid source/owner links and missing/ambiguous owner handling.
  The initial sandbox invocation could not create its Windows temporary directory; the host rerun passed.

## Connection status and remaining proof

| Source | Status in the lab | Still needed |
| --- | --- | --- |
| AWS Knowledge | Connected; document retrieval and agent use demonstrated | Broader answer-quality evaluation |
| DeepWiki | Connected; Prowler repository structure read succeeded | Document-content reads and citation quality |
| Jira / Confluence (Atlassian) | Existing catalog entry staged, disabled | Provider sign-in, selected page/issue read, capture and review |
| Notion, Dropbox, GitLab, Linear, Craft | Existing catalog entries staged, disabled | Provider sign-in and representative document reads |
| Google Drive | Official MCP endpoint configured, disabled | OAuth client/eligibility, sign-in and selected document read |
| S3 / existing knowledge base | Not connected | Qualify an existing scoped connector; audit credentials must not become general document access |

Configured or enabled is not proof of successful authentication or retrieval. Provider credentials were not
invented, copied from this assistant's connectors, or embedded in the product. Authenticated provider tests remain
pending maintainer sign-in/material. There is no automatic source refresh, revocation handling, deletion handling,
dependent-concept invalidation or scheduler in these changes. Prowler intake and complete AWS remediation coverage
are not certified by this exercise.

The Spot lab is retained for live review. Release packaging, broader release gates and teardown follow the
maintainer's review; no release tag or publication was performed.
