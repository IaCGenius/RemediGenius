> Historical full-engine / advanced-kiosk guide. This is not the private-preview console installer. Start with [the current quickstart](V0.1-QUICKSTART.md) and [AWS console guide](AWS-WORKSPACE.md).

# Operating the engine

> For the v0.1 local console start with [V0.1-QUICKSTART.md](V0.1-QUICKSTART.md).
> This older guide operates the separate experimental AWS host and optional kiosk.
> It does not deploy the new console; a fresh AWS deployment test remains a release gate.

All commands from `deploy/aws/` unless noted. Host commands run in a shell from `./connect.sh shell`.

## First run

```bash
sudo /opt/rg/dist/collect.py --all                     # every connected account; prints one JSON line each
sudo docker exec -u hermes hermes hermes -p desk chat -q "Run the analyst checks for every account and summarise"
```

Or open Hermes Desktop on the tunnel and ask the desk agent. Results land in `/data/hermes/results/<account>/<date>/`
(container: `/opt/data/results/...`) and are copied to `s3://<bucket>/results/`.

## Daily runs

Set `schedule_enabled = true` (and `collect_on_calendar` if 05:00 UTC does not suit) and `terraform apply`. The
host is replaced with the new setting (about 5 minutes; agent state is on the data volume). On boot it enables the collector timer and resumes the analyst (05:30) and desk (07:00) jobs. Set it back to false to
pause everything. Check that your model plan allows automated use first (docs/MODELS.md).

## Connect another AWS account

1. Add it to `accounts` in `terraform.tfvars`, `terraform apply`.
2. Run the command from `terraform output onboarding` **with that account's credentials**. It deploys the read-only
   role there, trusting only your engine's host role and only with the generated ExternalId.
3. Next collector run includes it. Check: `sudo /opt/rg/dist/collect.py <key>`.

To disconnect: delete the stack in that account (`aws cloudformation delete-stack --stack-name <prefix>-readonly`), remove
it from `accounts`, `terraform apply`.

## Lambda kiosk and the builder (optional)

```bash
python ../../modules/lambda-kiosk/build.py             # before every plan with enable_kiosk = true (needs uv)
terraform apply                                         # enable_kiosk = true
./refresh.sh                                            # installs the builder profile and its credentials timer
```

On the host:

```bash
sudo docker exec -u hermes hermes python3 /opt/data/profiles/builder/skills/kiosk/lambda-kiosk/scripts/kiosk.py doctor --e2e
sudo docker exec -u hermes -w /opt/data/work hermes hermes -p builder chat -q "Build a function that ..."
```

`doctor --e2e` checks the builder's rights (denied where they must be) and runs a hello function through gate, canary
and run. Freeze all submissions and promotions: `terraform output -raw kiosk_freeze` and run it.

Logs: builder `/data/hermes/profiles/builder/logs/agent.log`; gate and sandbox in CloudWatch
`/aws/lambda/kiosk-<prefix>-gate|sandbox`; run receipts in the kiosk bucket under `runs/`.

## Day 2

| Task | How |
|---|---|
| Stop paying for compute | `running = false`, apply (data volume, results and secrets stay) |
| Apply profile or host-script changes | `terraform apply`, then `./refresh.sh` (re-runs `boot.sh` over SSM) |
| Rotate the model key | `set_model_key` again, then on the host `sudo systemctl start rg-hermes-secrets` |
| Logs | host boot `/var/log/user-data.log`, `journalctl -u rg-hermes -u rg-hermes-collect`; agents `/data/hermes/profiles/<p>/logs/agent.log` |
| Restore agent state | Data volume snapshots (daily, keep 7): create a volume from one, swap it in, `boot.sh` |
| Upgrade Hermes | Change `hermes_image` (pin a digest), apply (replaces the host) |

## Team use: remote state

State is local by default (it holds no keys, but it does hold the dashboard password). For a team, add to `versions.tf`:

```hcl
terraform { backend "s3" {} }
```

and `terraform init -backend-config="bucket=<state bucket>" -backend-config="key=rgce.tfstate" -backend-config="region=<region>" -backend-config="use_lockfile=true"`.

## Teardown

`terraform destroy`. By default it stops at the results bucket (`destroy_data_on_teardown = false` keeps your
findings). Set it to true and apply first to delete everything. Then delete the read-only stacks you deployed in other
accounts. Lambda functions the builder made are created by the kiosk gate, not by Terraform. With
`destroy_data_on_teardown = true` the kiosk bucket goes too; delete leftover `kiosk-<prefix>-fn-*` functions by hand.
