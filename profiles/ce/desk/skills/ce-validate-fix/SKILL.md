---
name: ce-validate-fix
description: Validate generated AWS CLI, Terraform or CloudFormation using actual Linux tools; correct from diagnostics with at most three attempts. Use before presenting a concrete remediation artifact.
license: Apache-2.0
---

# Generate, validate, correct, deliver

Use `ce_validate`, not another model, for syntax/schema checks. Start with
`action=capabilities` to obtain the actual configured toolchain. The baseline is
pinned in `deploy/validator/toolchain.json`; do not assume the operator has the
same version or silently upgrade their repository. Validation runs in Linux
amd64 without AWS credentials or outbound network. Produce Bash/Linux/WSL
commands; do not label them PowerShell-compatible. JSON files avoid shell quoting.

1. Ground the desired change in the finding, current settings, ownership and
   chosen format. Follow ce-aws-security fix preparation. Required unknowns stay
   unknown; a schema-valid placeholder is not an actual resource identifier.
2. Submit the complete relevant artifact through `action=validate`. `files` is
   an object mapping plain filenames to their text, not local filesystem paths.
3. Read the real tool diagnostics. Correct only the reported problems while
   preserving the requested security outcome and repository constraints. At most
   **three validation attempts per format per turn**, including the first attempt.
   Stop immediately on missing toolchain/dependency or unreachable service; do not
   change provider versions or tool routes to evade that gap. No endless retry.
4. Deliver the returned formatted files unchanged after a pass. If you change
   validated code, it needs validation again within the same budget. Show a short
   result: tool/version, pass/fail, artifact hash and remaining deployment checks.
   If attempts run out, show the last errors and the incomplete draft, not a pass.
5. Use the normal single ce_review for the surrounding security interpretation.
   A critic cannot overrule a failing tool, approve execution or certify impact.

## Terraform

Use `format=terraform`, with complete `.tf` files (for example `main.tf` and
`variables.tf`). The tool runs `terraform fmt`, offline `init -backend=false
-get=false`, then `terraform validate -json`. It returns formatted files and
actual diagnostic exit codes. Only the pinned HashiCorp AWS provider is installed.
For a new standalone proposal declare that exact provider version from capabilities.
For existing source preserve its constraints: an incompatible version or external
module is an environment gap, not permission to rewrite their dependencies.
No backend, state, Terraform plan or apply is run. No credentials are required.
Do not claim validation of an isolated resource fragment proves its complete module.

## CloudFormation

Use `format=cloudformation` and one complete JSON/YAML template. The tool runs
AWS cfn-lint with us-east-1 schemas. Fix actual property/type/placement errors;
do not translate Terraform attributes by analogy. Warnings remain visible.
No CloudFormation API, change set, resource lookup or deployment is executed.

## AWS CLI

Use `format=aws-cli`, `argv` as a list of command arguments **without `aws`**,
and any JSON input files in `files`. Example shape:
`{"action":"validate","format":"aws-cli","argv":["configservice",
"start-configuration-recorder","--region","us-east-1","--cli-input-json",
"file://change.json"],"files":{"change.json":"{\"ConfigurationRecorderName\":\"REPLACE_WITH_CONFIRMED_NAME\"}"}}`.
This example is an unresolved template, not evidence of an actual recorder.
The runner appends `--generate-cli-skeleton output` itself. The real AWS CLI
validates arguments and input types without sending the operation to AWS.
Do not include that validator flag yourself, shell pipelines, substitutions,
multiple commands or arbitrary file paths. Submit each chosen API command
separately; keep within the three-attempt format budget. For a longer setup,
validate the principal change and mark other steps unchecked rather than claiming
all were validated. High-level `aws s3` commands are outside this mechanism.

A PASS means the submitted artifact passed these specific tool checks. It does
not prove the resource exists, caller has permission, the business decision is
correct, the change is non-disruptive or rollback works. Continue to explain those
inputs and the fresh-evidence reassessment after the operator's change process.
