# Rule provenance

The sg, s3, iam and skillresult modules are copied from this repository's
profiles/analyst/skills/remedigenius at baseline commit
1edece22389ad23288c3e84503e6c98477f9e3b9. The only packaging change is a relative
import of skillresult. Existing rule algorithms and identifiers are preserved.
Upstream concepts originate in jhkchan/aws-agent-skills at eeace51 (Apache-2.0).
See the original PROVENANCE.md and references/upstream/LICENSE in each skill,
and the repository NOTICE. These modules are narrow configuration checks, not
proof of effective exploitability or a replacement for native cloud findings.

The knowledge lifecycle borrows the OKF design principles of immutable approved
versions, content hashes and explicit provenance. It is a small independent
implementation; no OKF runtime, legacy agent launcher or private knowledge was copied.
