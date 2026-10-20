# Summarizing Security Hub CSPM Findings

## RemediGenius routing adaptation

For an unspecified "show Security Hub findings" request in an established ASFF
source, use Workflow D below. Workflows A and B are for explicitly requested
compliance/standards or failed-control views. Do not turn a general findings
request into a ProductName=Security Hub query: that excludes integrated threats.

### Workflow D: Combined ASFF findings overview

1. Collect get-findings with RecordState=ACTIVE and the user's explicit filters.
   Do not add ProductName, ComplianceStatus, severity or workflow-status filters.
2. Use deterministic counts and a compact projection over all collected records
   for Id, ProductArn, Title, Severity.Label, Compliance.SecurityControlId,
   Workflow.Status, UpdatedAt and Resources[].{Id:Id,Type:Type}. Use raw records
   for fields absent from the documented normalized shape; a missing GeneratorId
   in normalized data is not proof a finding has no originating standard.
3. Group supported related issues, distinguishing posture controls from threat
   alerts and vulnerabilities. Apply ce-security-brief to the selected population.
   Report partial inspection honestly. No enabled-standards query is needed just
   to show existing findings; use Workflow A if a standards assessment is requested.
4. Present the recommended next decision with evidence. Preserve source severity
   and IDs; do not create a compliance percentage or claim unique risk counts.

This is an explicit RemediGenius extension. The AWS procedures below are retained
for their named requests; their examples do not override the user's filter scope.

## Overview

Summarizes Security Hub CSPM compliance findings — standards-based posture results in ASFF format. Groups by standard (FSBP, CIS, PCI-DSS, NIST), control status (PASSED/FAILED/NOT_AVAILABLE), severity, and account.

**For an explicitly requested standards compliance summary (Workflow A), cover these (V1 APIs — no `-v2` suffix):**

1. Active compliance findings — `get-findings` filtered to ProductName=Security Hub, RecordState=ACTIVE
2. Enabled standard set — `get-enabled-standards` (FSBP, CIS, PCI-DSS, NIST)
3. Group results by standard, with a severity breakdown of FAILED findings
4. Report a finding-level pass percentage ONLY when PASSED and FAILED counts share a complete, matching scope; otherwise mark the rate unknown

Also covers third-party ASFF findings for customers using Security Hub CSPM as their primary hub.

This skill works from both standalone accounts and delegated administrator accounts.

**API constraint:** MUST use V1 APIs (no `-v2` suffix) only. MUST NOT use V2 APIs.

## Classify the Request

| Signal | Workflow |
|--------|----------|
| Compliance summary per standard, pass/fail rates | A: Standards Compliance Summary |
| Worst controls, most-failed checks | B: Failed Controls Summary |
| Third-party/integrated service findings (GuardDuty, Inspector, Macie in ASFF) | C: Third-Party ASFF Findings |

## Workflow A: Standards Compliance Summary

1. Get active compliance findings:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Security Hub","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --max-items 100
   ```

2. Get FAILED findings:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Security Hub","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}],"ComplianceStatus":[{"Value":"FAILED","Comparison":"EQUALS"}]}' --max-items 100
   ```

3. Get PASSED findings:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Security Hub","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}],"ComplianceStatus":[{"Value":"PASSED","Comparison":"EQUALS"}]}' --max-items 100
   ```

4. List enabled standards for context:

   ```bash
   aws securityhub get-enabled-standards
   ```

5. Summarize:

   - Per standard: PASSED / FAILED / NOT_AVAILABLE counts
   - Finding-level pass percentage only when PASSED and FAILED counts share a complete, matching scope; otherwise mark the rate unavailable or sampled. Do not call this a unique-control compliance score.
   - Severity breakdown of failed findings

## Workflow B: Failed Controls Summary

1. Get FAILED findings sorted by severity:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Security Hub","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}],"ComplianceStatus":[{"Value":"FAILED","Comparison":"EQUALS"}]}' --sort-criteria '{"Field":"SeverityNormalized","SortOrder":"desc"}' --max-items 100
   ```

2. Get CRITICAL failed findings:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Security Hub","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}],"ComplianceStatus":[{"Value":"FAILED","Comparison":"EQUALS"}],"SeverityLabel":[{"Value":"CRITICAL","Comparison":"EQUALS"}]}' --max-items 100
   ```

3. Summarize by:

   - Control ID (ComplianceSecurityControlId)
   - Severity
   - Resource type
   - Account (for org view)

## Workflow C: Third-Party ASFF Findings

For customers using Security Hub CSPM as their primary hub:

1. Get findings from integrated services:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"GuardDuty","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --max-items 100
   ```

2. Repeat for Inspector and Macie:

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Inspector","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --max-items 100
   ```

   ```bash
   aws securityhub get-findings --filters '{"ProductName":[{"Value":"Macie","Comparison":"EQUALS"}],"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}' --max-items 100
   ```

3. Summarize by ProductName, severity, and finding type.

## Constraints

- MUST filter ProductName='Security Hub' to isolate CSPM findings from integrations (Workflows A, B)
- MUST report compliance status counts (PASSED, FAILED, NOT_AVAILABLE)
- MUST distinguish finding records from unique controls and resources. State the denominator and scope for any percentage; do not add overlapping status queries or infer unique-control counts from finding totals.
- MUST prioritize CRITICAL and HIGH severity failed controls
- MUST filter RecordState=ACTIVE to exclude archived findings
- SHOULD break down by standard (use GeneratorId prefix)
- SHOULD note pagination — report sampled vs total when applicable

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No compliance findings | Confirm standards are enabled |
| All controls NOT_AVAILABLE | Resource types may not exist in account |
| Only from one account | Confirm delegated admin and cross-region aggregation |
| Stale compliance status | Controls evaluate periodically — check UpdatedAt |

## Output Sensitivity

Compliance findings contain resource ARNs, account IDs, control failure details, security group rules, IAM policy excerpts, and third-party integration data (GuardDuty, Inspector, Macie in ASFF). Present compliance pass/fail rates and severity breakdown first. Display full ASFF finding bodies only when the caller explicitly requests raw output.
