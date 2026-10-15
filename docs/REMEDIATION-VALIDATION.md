# Deterministic remediation validation

Hermes generates the proposal using the security and format skills, then calls
`ce_validate`. Existing tools run in a separate Linux container; their diagnostics
return to Hermes for correction. The runtime permits at most three validation
attempts per format per user turn. The final screen shows the tool result,
attempt count and artifact hash separately from AI critique.

## Using it

Ask ce-desk: “Prepare a Terraform fix for this finding. Validate it with the
configured tools, correct any errors within the limit, and show what remains
before I can apply it.” You do not need to call the validation API yourself.
For an existing draft, paste the non-secret relevant files and ask it to validate
and repair them. Watch the **Tool validation** heading for the actual result and
attempt count; AI critique appears separately.

## One replaceable baseline

Edit [toolchain.json](../deploy/validator/toolchain.json) and rebuild to replace
versions deliberately. This baseline was selected on 2026-10-15:

| Component | Pin | Upstream latest observed |
|---|---|---|
| Terraform | 1.16.4 | 1.16.6 |
| HashiCorp AWS provider | 6.68.0 | 6.69.1 |
| AWS CLI v2 | 2.37.13 | 2.38.1 |
| AWS cfn-lint | 1.57.2 | 1.57.2 |

Terraform, provider and CLI are two releases behind the newest entries observed.
The runtime exposes its configured versions through `ce_validate capabilities`;
the skill reads those instead of assuming a version from model memory. These
pins qualify generated artifacts; they do not upgrade the provider used by your
existing Terraform repository or the CE deployment stack.

## What runs

| Format | Actual checks | What remains outside the check |
|---|---|---|
| Terraform | fmt; init with backend and module downloads disabled, installed AWS provider only; validate -json | Plan, state ownership, provider API behavior and apply |
| CloudFormation | AWS cfn-lint against us-east-1 schemas | Change set, live permissions and deployment |
| AWS CLI | Real CLI argument/input parsing with forced generate-cli-skeleton output | Resource existence, permissions and execution |

The supported command environment is Bash/Linux/WSL, not PowerShell quoting.
AWS CLI receives argument arrays and submitted JSON files; it never runs a shell.
Terraform returns its formatted files. A later edit invalidates the earlier
artifact check. Missing inputs remain placeholders, even if their types validate.
An incompatible provider constraint or missing external module is an environment
gap; CE does not replace your dependency choices automatically.

## Deployment and boundaries

The workstation launcher and AWS native bootstrap build the same validator
Dockerfile from the lock file. The first build downloads the official Terraform
and AWS CLI images, the AWS provider and cfn-lint; allow time and disk space.
Subsequent starts reuse the image keyed to validator source/configuration.
The official Hermes image is unchanged.

At runtime the validator has an internal Docker network, no published host port,
no AWS/model credentials, no evidence/session mounts, a read-only root filesystem,
and disposable temporary files. All capabilities are dropped. CPU, memory,
process and execution time limits bound the work. No Docker socket is given to
Hermes. Provider downloads occur at image build, not during an agent request.
Scratch files disappear after each request; diagnostics and returned source are
recorded in the retained Hermes conversation. Do not supply secrets in artifacts.

The initial scope is Linux amd64, one pinned AWS provider and no remote modules.
This is not a general-purpose terminal, arbitrary build service, security scanner
or proof that a proposed change achieves the intended security outcome. Reassess
that outcome with fresh AWS evidence after the operator applies the change.

Sources: [Terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate),
[AWS CLI input validation](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-skeleton.html),
[AWS cfn-lint](https://github.com/aws-cloudformation/cfn-lint).
