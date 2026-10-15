# High-risk CloudTrail event patterns (local)

Flag when the receipt contains:

- ConsoleLogin with MFAUsed=false (successful)
- CreateUser, CreateAccessKey, AttachUserPolicy, PutUserPolicy
- AuthorizeSecurityGroupIngress with CidrIp 0.0.0.0/0
- StopLogging or DeleteTrail
- AssumeRole from an unexpected principal (principal observed in the event)

Record EventId, EventTime, and ErrorCode (if present) for each match.
