# Deploying RemediGenius-CE

Four Terraform roots, one purpose each. The community install stays a single apply; the maintainer's stack splits the
durable parts from the disposable ones so a Spot replacement is minutes, not a re-provision.

| Root | Creates | Lifecycle |
| --- | --- | --- |
| `bootstrap` | the S3 bucket that holds Terraform state | **once per account**, local state, keep a copy of it |
| `aws-static` | data bucket, Glue database, instance role + read-only audit role | **once**, changes only when the installation changes |
| `ami` | the host image: runtime wheels, Terraform/tflint, Hermes image by digest, release archive | one image per release |
| `aws-single` | everything above in one root, on plain AL2023 | the community install, and the release gate |
| `aws-private` | security group, launch template, Spot ASG only | start / park many times a day |

## First time (once)

```bash
terraform -chdir=deploy/bootstrap init
terraform -chdir=deploy/bootstrap apply -var account_id=<id>
terraform -chdir=deploy/bootstrap state pull > bootstrap.tfstate   # keep this somewhere safe

cp deploy/backend.hcl.example deploy/backend.hcl                    # paste the bucket from the output
terraform -chdir=deploy/aws-static init -backend-config=../backend.hcl
terraform -chdir=deploy/aws-static apply -var account_id=<id> -var subnet_id=... -var name=remedigenius-ce
```

`deploy/backend.hcl` is git-ignored. State locking uses the S3 lock file (`use_lockfile`), so there is no DynamoDB table
to run.

## Each release

```bash
python tools/package_release.py --release 0.6.0
terraform -chdir=deploy/ami init -backend-config=../backend.hcl
terraform -chdir=deploy/ami apply -var account_id=<id> -var release=0.6.0 \
  -var source_zip=dist/v0.6.0/remedigenius-ce-0.6.0-spot.zip -var state_bucket=<bucket> -var subnet_id=... | tee /tmp/ami.txt
```

The image is built on apply and blocks until it exists, so "one image per release" is the default and old images are not
needed: keep the previous one until the new one has passed the gate, then deregister it.

## Every working session

```bash
python tools/spot_cycle.py up --init      # ASG desired 1, ~2-3 minutes
python tools/spot_cycle.py status
python tools/spot_cycle.py down           # ASG desired 0; bucket, Glue and IAM stay
```

Settings live in `.rgce/private-stack.json` (git-ignored) and are passed to Terraform as-is, so any variable of
`deploy/aws-private` can be set there: `account_id`, `subnet_id`, `state_bucket`, `ami_id`, `source_zip`,
`model_secret_arn`, `model_base_url`, `running`, and the rest.

## What still has to be a full apply

`deploy/aws-single` from nothing remains the release gate. It provisions the bucket, Glue database, roles, security
group and instance in one apply and is what `tools/spot_release_test.py` drives, so the published path stays the tested
path. The split stack exists to make iteration cheap, not to replace that check.

## Boot with and without an image

| | plain AL2023 (`ami_id` empty) | baked image (`ami_id` from `deploy/ami`) |
| --- | --- | --- |
| `dnf install`, `pip install`, Terraform/tflint download | at boot | already in the image |
| `docker pull` of the Hermes digest | at boot | already in the image |
| release archive | downloaded from S3 and hash-checked | read from the image, hash re-checked |
| state restore, systemd units, profile install, plugin enable | at boot | at boot |

The image records what it baked in `/opt/rgtriage/.baked` (version, image digest, wheel pins, archive hash). `host.py`
refuses to boot an image whose Hermes digest does not match the stack's, and re-installs the wheels only when the
release pins a different set — so a newer release on an older image cannot silently run mismatched packages.