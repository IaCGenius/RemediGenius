# How to test this repository

Four tiers, cheapest first. Each catches something the one below it cannot, and none of them is evidence for the tier
above it. A green local suite has never been evidence that a release deploys.

| Tier | Command | Proves | Blind to |
| --- | --- | --- | --- |
| Unit and local integration | `python -m pytest tests -q` | logic, contracts, schema shape, local on-disk Iceberg | Glue, S3, containers, threads, IAM |
| Synthetic demo | `python tools/demo.py` | the board and IaC match end to end without AWS or a model | anything live |
| Image build | `terraform -chdir=deploy/ami apply -var-file=…` | the host image builds and the bake records itself | whether a boot uses it |
| Release gate | `python tools/spot_release_test.py …` | a fresh stack from the release's own Terraform, the real first boot, the dashboard, the agent | cost, scale, other regions |

Run pytest in one process. The suite writes shared temp state and this workstation runs out of memory quickly.

## The release gate

```bash
# 1. build the assets from the commit you will tag
python tools/package_release.py --release 0.6.0

# 2. bake the image from *that* archive (deploy/ami reads source_zip)
cp dist/v0.6.0/remedigenius-ce-0.6.0-spot.zip .rgce/bake/rgce-0.6.0-spot.zip
terraform -chdir=deploy/ami apply -var-file=<private tfvars>.json -auto-approve

# 3. gate a throwaway stack with the image id in the settings file
python tools/spot_release_test.py v0.6.0 \
  --settings .rgce/spot-test-settings-gate.json --local dist/v0.6.0 --name rgce-v060-gate3
```

The settings file is Terraform variables for `deploy/aws-single`; `ami_id` makes the run exercise the baked path. Use a
unique `--name` so a leftover stack cannot collide. The report lands in `.rgce/release-test-v0.6.0/report.md`; the stack
is destroyed at the end unless `--keep` is given.

### The invariant that keeps failing quietly

**The archive baked into the image must be the archive you publish.** The boot compares the SHA-256 of
`/opt/remedigenius/source.zip` with the stack's expected value; a mismatch silently falls back to downloading, which
passes every other check and costs the boot time back. The gate therefore asserts the line
`baked image: release archive already verified <sha>` and fails without it.

That is why `tools/package_release.py` reads the **committed** bytes (`git cat-file --batch` against the index) instead
of the working copy: a Windows checkout can hold CRLF in a file whose committed form is LF, and v0.6.0's first image was
baked from exactly such an archive, which a fresh build did not reproduce. Never verify a rebuild against a local
`dist/` from an earlier checkout — compare against the digest recorded in the release.

### Cost, measured on 2026-10-30

| Step | Time |
| --- | --- |
| Local suite (743 tests) | ~7 min |
| Image bake (EC2 Image Builder) | ~21 min |
| Gate: apply, boot, 56 checks, destroy | ~10 min |

The baked boot is what makes a Spot cycle short; the image build is the price of that, and it is per release **and per
archive digest**. If the release archive changes, bake again before trusting a gate result.

### Parking between sessions

The private stack is not left running. `python tools/spot_cycle.py status` reports the ASG; `down` applies
`-var running=false`, which takes desired capacity to 0 and leaves the bucket, Glue database and IAM in place; `up`
scales the same ASG back to one instance on the baked image. Both ASGs in the account sit at 0 between sessions, so
"is anything running?" is answered by two reads, not by memory:

```bash
aws autoscaling describe-auto-scaling-groups --region us-east-1 \
  --query "AutoScalingGroups[].[AutoScalingGroupName,DesiredCapacity,Instances[].InstanceId]" --output table
aws ec2 describe-instances --region us-east-1 --filters Name=instance-state-name,Values=running,pending --output text
```

`up` needs the release archive still present at the settings file's `source_zip` path, because the apply hashes it. The
parked stack is therefore a pair: an `ami_id` and a `dist/vX/…-spot.zip`. Details and the precedence that makes `down`
win over a settings file's `running: true` are in [deploy/README.md](../deploy/README.md#every-working-session).

### When a check fails

Read the `detail` column first: every check records the value it saw. Common shapes:

- `boot used the baked release archive` — the image and the archive disagree; re-bake, do not publish.
- `core plugins enabled at release version` — a `plugin.yaml` or `manifest.json` was not bumped;
  `test_every_declared_version_is_the_package_version` catches this locally first.
- a `terraform apply` failure — the stack name collides with an existing one, or the image id does not exist.

Fix in batches. One apply/boot/check/destroy cycle is ten minutes; guessing one fix per cycle is how a day disappears.

## What the gate does not prove

Read [RELEASE-VALIDATION.md](RELEASE-VALIDATION.md) after every run: it records what was not tested as carefully as what
was. As of v0.7.0 that includes a real S3/Glue outage, Spot replacement mid-scan, real GitHub publish/merge, other
regions or models, the Docker workstation path with the Dashboard tab, a manual refresh concurrent with the scheduled
scan, and a full campaign lifecycle on AWS (nothing yet derives a campaign from a scan).