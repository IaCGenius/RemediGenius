# RemediGenius CE __VERSION__ — private preview

Turn your existing security evidence into an investigation and a remediation proposal your team can review. Add your organization's guidance once, then reuse it with visible scope and receipts. Read the included source and skills in ordinary files; use Hermes or your existing AI workflow when you want interpretation.

## Start here: prebuilt Docker, no cloud or model key

Use Docker with Linux containers on an amd64 workstation. This image was tested on Docker Desktop/Windows and the AWS Linux host. macOS/Apple Silicon is not a tested prebuilt path. You do not need Python to run the container, and this route does not download application dependencies.

Extract this ZIP into a new folder. In a terminal **in that folder**:

```sh
docker load --input runtime.tar.gz
docker compose up -d --pull never
```

Open **http://127.0.0.1:8765**. Choose **Try the sample workspace**. Follow `FIRST-INVESTIGATION.md` for a short tour: inspect the SSH finding, prepare a proposal, add/review guidance, compare the sample snapshots, and download an investigation ZIP for your agent.

The console makes no LLM calls and has no AWS credentials by default. The sample is synthetic. Optional AWS source reads and selected-data/model sharing are separate choices.

To stop: `docker compose down`. To return: `docker compose up -d --pull never`. Data stays in the named `remedigenius-ce-preview_rgce-data` volume. **Do not use `down --volumes` unless you intentionally want to delete the local workspace.** This is local persistence, not a remote backup. Keep the port on loopback; this is a single-operator preview.

If port 8765 is occupied, set `RGCE_PORT` before starting: PowerShell `$env:RGCE_PORT='8877'`; a macOS/Linux shell uses `export RGCE_PORT=8877`. Then open the chosen localhost port. If Docker reports an unavailable daemon, start Docker and confirm Linux containers are enabled. `docker compose ps` shows health; `docker compose logs --tail 50` helps local diagnosis—review/redact any logs before sharing.

## Inspect what you received

- `source.zip`: complete committed source, documentation, tests, Terraform and the separately labeled experimental extensions. Extract it into a `source` folder to follow documentation links.
- `runtime.tar.gz`: the tested Linux/amd64 Docker image.
- `remedigenius_community-__VERSION__-py3-none-any.whl`: native Python package.
- `INVESTIGATION-SKILL.md`: readable instructions for your existing agent.
- `RELEASE.json`, `DEPENDENCIES.txt`, `SHA256SUMS`: exact source commit, artifact identities, validation summary and file hashes.
- `FEEDBACK.md`, `SECURITY.md`, `LICENSE`, `NOTICE`: scope, feedback and licensing.

Compare the outer ZIP's hash with the companion `.sha256` supplied by the sender. Windows: `Get-FileHash -Algorithm SHA256 PATH_TO_ZIP`; Linux: `sha256sum PATH_TO_ZIP`. Checksums detect an accidental change, not an untrusted sender or a forged checksum. To inspect the loaded image use `docker image inspect remedigenius-ce:__VERSION__`; its ID should match `RELEASE.json`.

## Optional: native Python or workstation collection

Use Python 3.12 for the tested native path. In this bundle folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install "./remedigenius_community-__VERSION__-py3-none-any.whl[aws,documents]"
.\.venv\Scripts\python -m rgce --home ./trial-workspace serve
```

Linux/macOS use `.venv/bin/python`; these platforms may build/install native dependencies and are not claimed as fresh Windows-install acceptance. The wheel installation downloads declared dependencies from your configured Python package index. There is no published PyPI package or required hosted subscription.

For a Docker/AWS console, collect on your workstation using the wheel's CLI, then import the selected JSON file. Activate the virtual environment first: PowerShell `.\.venv\Scripts\Activate.ps1`; Linux/macOS `source .venv/bin/activate`. Alternatively replace `python` in the generated command with the full `.venv` Python path. Follow `source/docs/AWS-ONBOARDING.md` to establish the scoped read role. Never give admin credentials to the investigation agent. The Docker console does not receive your AWS profile or keys.

Imported coverage is unverified; file transfer cannot grant itself a trusted clearance result. For native collector-backed before/after comparison, use a native local workspace. Optional S3 workspace storage and a separate AWS console are explained in `source/docs/DURABLE-WORKSPACE.md` and `source/docs/AWS-WORKSPACE.md`; they are not needed for the sample.

## Give us useful feedback

Use `FEEDBACK.md` and reply privately to the person who shared this bundle. Tell them where you got stuck, what decision it helped with, and whether evidence/knowledge/AI were clearly distinguished. Keep customer data, credentials and cloud identifiers out of feedback. There is no automatic telemetry or model submission in the console.

This preview prepares proposals; it does not execute remediation. Native Azure/GCP, GitHub OAuth, arbitrary agent-generated Lambda execution and hosted multi-user controls are outside this release. Hermes/model setup stays with your existing agent. Use readable exports by default; optional local stdio MCP is for a native local-data installation with the `mcp` extra.
