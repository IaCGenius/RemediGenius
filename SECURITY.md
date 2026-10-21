# Security — RemediGenius Community Edition (RemediGenius-CE)

## Reporting a vulnerability

Report suspected vulnerabilities or credential exposure privately through GitHub's private vulnerability reporting
for this repository. Do not open a public issue or paste secrets anywhere.

## Security model

RemediGenius-CE is a **single-operator** tool. It is not a multi-user or multi-tenant service; do not expose the
dashboard publicly. The workstation binds it to `127.0.0.1`; Spot exposes it only through SSM port forwarding.

- **AWS access is read-only and isolated.** Only the desk service holds AWS credentials. Every call passes a botocore
  guard that refuses non-read operations and reads that return secrets or data. Deployments use a read-only role with
  explicit denies. See [docs/IAM.md](docs/IAM.md).
- **The agent has no AWS credentials and no shell.** It reaches the desk through a Unix socket that accepts a fixed
  list of triage commands. It cannot write outside its proposals folder or read credential stores, keys, `.env`
  files or Terraform state. Triage decisions require approval in Hermes.
- **On Spot**, the Hermes container's egress is limited to HTTPS: no instance metadata and no private address ranges.
  IMDSv2 uses hop limit 1 and the security group has no inbound rules.
- **Data leaves to your model provider:** finding details, resource identifiers, account ids, CloudTrail excerpts, IaC
  excerpts and your messages. Choose a provider your organization permits.
- **Checkpoints are sensitive.** The S3 bucket or local folder holds conversations, decisions, settings and possibly the
  model key. Restrict access to it like any secret store.
- Host administrators (Spot instance root, Docker host) are trusted.

Tool output, finding text, tags and documents are treated as data, never as instructions to the agent. Model output
can still be wrong; review every proposed change before applying it.
