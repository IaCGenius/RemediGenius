# Your context, with receipts

CE should help answer “what matters in our environment?” Start with one useful
document, not an entire wiki. Hermes helps draft and explain it; ordinary files
remain the durable source. This is OKF-inspired knowledge, not a separate agent
framework or a claim of full OKF schema compatibility.

## Start in the Hermes chat

Try: **“Help me build useful knowledge for this AWS account. Tell me what you
already have, then ask for the most useful missing context.”**

Give a short application description, an ownership note, or a real policy.
Ask Hermes to **stage a knowledge note** with its title, collection and scope.
Review the exact Markdown. Then send the returned `publish knowledge <id>` phrase
as a separate message. Publication saves the hashed note in the retained profile
and makes it available to later investigations. The note also enters private
runtime checkpoints. Ask Hermes to list the knowledge and explain which note
changed its recommendation.

Staging alone does not publish. Do not put secrets in a note. Unknown scope,
conflicting policies or an unconfirmed exception remain explicit uncertainties;
a note does not change AWS findings or grant cloud permissions.

For larger files, use the operator tools below. A chat attachment or pasted URL
is not automatically imported into the shared library.

## Prepare the operator tools

From your cloned CE repository, activate its Python environment and run
`python -m pip install -e ".[aws,documents]"`. These commands run on your
workstation, not inside the read-only agent chat. Complete either deployment
quickstart first; keep its private JSON configuration for publication.

## Add one document and see what is available

Save your reviewed text as `selected-policy.md`, or use an existing supported file.
Replace the scope below with its actual applicability; it is not an IAM permission.

```powershell
python -m rgce.knowledge_library --root ./library add --collection org/security --file ./selected-policy.md --scope "Describe the actual applications/accounts this applies to"
python -m rgce.knowledge_library --root ./library list --collection org/security
python -m rgce.knowledge_library --root ./library view --collection org/security --output ./views/security-001
```

`list` shows document IDs, titles, scope and ACTIVE/REPLACED status. ACTIVE means
selected for a new view, not certified or approved. Use `--json` for structured
inventory. The library keeps original files, converted Markdown and metadata.
The view is a readable copy of explicitly selected collections. Repeat
`--collection` to include others; selecting `org` does not recursively select
`org/security`. Suggested collections: `org/security`, `apps/<name>`,
`operations/<topic>`. Adapt them to your work; no mandatory taxonomy.

For workstation Docker, set `knowledge_dir` in your workstation configuration to
the reviewed view directory and restart through the existing launcher. An S3 copy
is optional for this local read-only mount. On the single-host Spot stack, use
the chat note workflow above. That stack does not yet mount an operator-published
file view automatically; do not add a `knowledge_view` Terraform variable.

## Preview and publish to S3

For an optional file-view archive, use the workstation JSON or a separate private
JSON containing `bucket`, `prefix`, `region` and optional `aws_profile`.
On Spot, obtain the bucket with `terraform output -raw bucket` and use prefix
`ce`. This archive is not automatically activated on Spot. Do not pass Terraform
HCL inputs to this publisher. The command reads destination fields, not model
credentials:

```powershell
python -m rgce.knowledge_publish --view ./views/security-001 --config ./ce-config.json
```

The first run makes **no AWS calls**. It shows the destination, document titles and
scope, exact filenames/hashes and a preview token. Review those files, then repeat
the command with `--publish TOKEN`, using the complete token from that preview.
Use `--json` if you need structured output. A changed view, destination or profile
requires a fresh token. Do not paste credentials into Hermes.

Publishing uses your normal operator AWS credentials and needs the CE `aws` extra.
It creates a new hash-named view under your workspace's `knowledge/` prefix,
never overwrites a different object, and verifies remote bytes. Unlisted files
(including accidentally copied originals) are rejected. Existing matching objects
are verified and reused, so an interrupted upload can be retried with the same
command. Bucket default encryption is retained. It does not change IAM or activate
the view. Permissions needed: list the selected prefix, get/put its objects, and
any permissions required by the bucket's configured KMS key.

`PUBLISHED_VERIFIED_NOT_ACTIVATED` means the archive upload succeeded, not that
Hermes can use the view. On workstation, set `knowledge_dir` to the reviewed local
view and restart the launcher. Ask Hermes to read its index and source to confirm
access. On Spot, use reviewed chat notes for this release. Importing or uploading
on your laptop alone does not update the running agent.

## Sources you can use today

| Source | Simple path into knowledge |
|---|---|
| Your description or pasted policy | Review Hermes's Markdown draft; save and import it |
| Markdown, text, CSV | Import the selected file |
| PDF, Word, PowerPoint, Excel | Existing MarkItDown conversion; install the documents extra |
| Confluence page | Export selected readable content; retain page URL/version when known |
| Repository documentation | Select non-secret files; retain repository, commit and path |

Files are limited to 5 MB; scanned/image-only documents need a readable/OCR export.
`--source-ref "page URL or repository commit/path"` records a reference without
fetching it. Do not put credentials or signed access URLs in that field.
Authenticated Confluence synchronization is not shipped.

## See the difference it makes

Ask: **“Assess this finding using our context. Show the source, why it applies,
what it changed, and what remains unknown.”**

For the operator-supplied S3 policy, a confirmed logs-only bucket may use AES256;
business-data buckets require customer-managed KMS. If purpose is unknown, the
exception is unresolved. The observed encryption and AWS finding remain unchanged.
This policy is an example supplied by this project's operator, not a default policy
installed for every CE user.

Hermes should cite the selected document and its scope/version, explain the effect
on its recommendation, and distinguish that interpretation from the AWS receipt.
Hashes establish which bytes were read, not whether a policy is true. If knowledge
made no difference, it should say so. It should not require uploads to answer an
unrelated AWS question.

## Refresh without losing history

Edit the original file. Use `list` to find the active document ID, then:

```powershell
python -m rgce.knowledge_library --root ./library add --collection org/security --file ./selected-policy.md --scope "Actual applicability" --replaces ACTIVE_DOCUMENT_ID
python -m rgce.knowledge_library --root ./library view --collection org/security --output ./views/security-002
```

Replace `ACTIVE_DOCUMENT_ID` with the ID from the listing. Old originals and old
views remain intact. New views omit explicitly replaced revisions. Publish/select
the new view to update Hermes. Without `--replaces`, both versions remain active:
import time alone never decides which policy wins. The operator determines scope
and replacement; CE does not infer approval, effective dates or expiry.
When replacing, omit `--scope` to keep the previous document's scope, or supply it
to explicitly change applicability. New documents always need a scope.

Editing generated views directly is discouraged: content hash checks will reject
changed content. Review them freely, or ask Hermes to explain them; change the
original and re-import when correcting it.
