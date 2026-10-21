# Troubleshooting RemediGenius Community Edition

| Symptom | Check |
| --- | --- |
| The chat does not open with a board | `/triage` in chat. "No scan yet" means the first scan has not run: it runs about 3 minutes after start, or ask "scan now". |
| Board shows `denied` for a source | The read role lacks permission; attach `SecurityAudit` (Spot: the audit role already has it, so check SCPs). |
| Board shows `not_enabled` | That service is off in that region: a blind spot, not a clean result. |
| Health `not_available` | The Health API needs Business/Enterprise support; Health events still arrive through Security Hub. |
| IAM reads fail with `InvalidClientTokenId` (workstation) | GetSessionToken credentials cannot call IAM without MFA; use `--read-role-arn` (or a profile with direct credentials). |
| "rgtriage service unavailable at /run/rgtriage/rgtriage.sock" | The desk is down. Spot: `journalctl -u remedigenius-desk`. Workstation: `docker logs remedigenius-ce-desk`. |
| "Write denied … outside HERMES_WRITE_SAFE_ROOT" | Proposals must go to `/opt/data/proposals`; the agent is told this at session start. |
| Model errors (401/404) | 401: wrong key. 404 "model not exist": the endpoint does not serve that model id. Check `model_name`/`model_base_url` or set them in the dashboard. |
| Spot boot stops at the model secret with "Access to KMS is not allowed" | Apply the current Terraform (KMS decrypt is granted automatically for the secret's customer-managed key). |
| Spot instance never becomes ready | `aws ssm start-session` to the instance, then `cloud-init status` and `tail /var/log/cloud-init-output.log`. |
| Checkpoint log says `REFUSED … DIVERGED` | The home does not descend from the latest checkpoint (for example, a restore failed). Restore first; only use `rgtriage durable checkpoint --force` if you intend to discard the stored state. |
| `terraform validate` fails while downloading the provider | A transient network error from releases.hashicorp.com; retry. The desk caches providers afterwards. |
| `/triage` in `hermes -z` one-shot mode goes to the model | Slash commands are handled in interactive chat and gateways only. |

Diagnostics:
- Spot: `journalctl -u remedigenius-desk -u remedigenius-scan -u remedigenius-hermes`.
- Workstation: `python tools/workstation.py status`, `docker logs remedigenius-ce-desk`.
- Desk view: `rgtriage doctor` (Spot: run as uid 10000 with `PYTHONPATH=/opt/rgtriage/src RGTRIAGE_HOME=/data/rgtriage`).
