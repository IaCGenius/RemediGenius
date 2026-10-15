# CloudTrail review patterns

Read exact event JSON when available; do not assume fields exist in a normalized preview.
- ConsoleLogin: responseElements.ConsoleLogin="Success" and additionalEventData.MFAUsed="No" warrant contextual review. MFAUsed is normally "Yes"/"No", not a Boolean. Missing fields are unknown; federation may require IdP context.
- CreateUser, CreateAccessKey, AttachUserPolicy and PutUserPolicy are review candidates, not automatically attacks. Record actor, target, outcome and any applicable change context.
- AuthorizeSecurityGroupIngress: inspect requested ranges/protocol/ports and outcome. 0.0.0.0/0 or ::/0 does not by itself prove end-to-end reachability.
- StopLogging/DeleteTrail: distinguish attempted versus successful calls; collect current status before asserting detection is off.
- AssumeRole is unexpected only against an explicit trusted-principal baseline. An unfamiliar principal alone is insufficient.

Record EventId, EventTime and errorCode (if present); an absent error field alone is not proof of successful console sign-in. Never infer all events failed from an error-only preview. LookupEvents is scoped regional management-event history, not S3 object data events or all-account coverage.
Reference: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-aws-console-sign-in-events.html
