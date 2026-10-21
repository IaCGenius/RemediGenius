# Add RemediGenius Community Edition to an existing Hermes

If you already run Hermes on your machine, you can add the `remedigenius` profile to it instead of using the Docker
workstation path.

```sh
python -m pip install -e .                                     # provides the `rgtriage` command (needs boto3, PyYAML)
python tools/install_local_hermes.py --clone-from default      # creates/updates profile `remedigenius`
rgtriage doctor                                                # what can be read, what is off, what is denied
hermes -p remedigenius chat                                    # opens with the attention board
```

`--clone-from` copies the model/provider settings of one of your existing profiles, so the desk uses a model that
already works for you. The installer adds the SOUL, skills and plugin, enables the `rg_triage` toolset, writes
`~/.rgtriage/triage.yaml` from your current AWS identity, and keeps a timestamped backup of the profile's `config.yaml`.

## Differences from the containerized paths

- The desk runs as a subprocess of Hermes with **your** AWS credentials (the read-only botocore guard still refuses
  every write). For stronger separation use the [Docker workstation](WORKSTATION.md) path.
- State lives in `~/.rgtriage` (desk) and your Hermes home; durable checkpoints are up to you
  (`rgtriage durable checkpoint --url <folder or s3://…> --home desk=$HOME/.rgtriage`).
- Optional alerts: `hermes -p remedigenius cron create "every 2h" --name security-watch --no-agent --script rgtriage-watch.py --deliver local`.
  Hermes cron runs only while a Hermes gateway is running for that profile.
