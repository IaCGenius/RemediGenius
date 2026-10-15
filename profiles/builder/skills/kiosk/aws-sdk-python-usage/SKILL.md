---
name: aws-sdk-python-usage
description: "Correct boto3/botocore patterns for kiosk function code: clients, typed errors, paginators, waiters, retries, S3 helpers, and testing with Stubber. Use whenever function code imports boto3 or botocore."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  upstream: aws/agent-toolkit-for-aws@2cb0fa1c2e668e1bb075028800b6b27efb95779e plugins/aws-core/skills/aws-sdk-python-usage
---

# aws-sdk-python-usage (adapted for the kiosk)

AWS's guidance for writing boto3 code. In a kiosk function:

- Create clients with `ctx.aws("<service>")` (adaptive retries already set). Do not build sessions or read
  credentials yourself: rights come only from the function's class role.
- Check every operation offline at the pinned version: `kiosk sdk <service> <Operation> --depth 2`
  (input/output shapes, paginator, errors). The SDK in the runtime layer is boto3/botocore 1.42.89.
- Use paginators for list calls (`kiosk sdk <service>` marks them with `*`).
- Catch only what you can act on; prefer `client.exceptions.<Name>`; otherwise read
  `e.response["Error"]["Code"]`.
- Test without network: `botocore.stub.Stubber(client)`, `add_response` / `add_client_error`, then
  `assert_no_pending_responses()`. The sandbox has no network and dummy credentials; an unstubbed call fails fast.
- Credentials, profiles, `~/.aws` and assume-role sections of upstream do not apply inside functions.

Read `references/upstream/UPSTREAM-SKILL.md` and `references/upstream/references/`
(`error-handling.md`, `pagination.md`, `waiters.md`, `configuration.md`, `s3.md`, `dynamodb.md`).
