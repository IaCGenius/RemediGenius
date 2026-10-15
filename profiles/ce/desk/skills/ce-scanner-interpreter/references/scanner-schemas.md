# Local scanner schemas (expected fields)

Operator-supplied files only.

- **Prowler JSON**: look for `CheckID`, `Status`, `ResourceId`, `Severity`.
- **Checkov JSON**: look for `check_id`, `resource`, `file_path`, `check_result`.
- **Trivy JSON**: look for `Target`, `Vulnerabilities` or `Misconfigurations` with `ID` and `Severity`.

If the file lacks these fields, report “schema not recognized” and stop.
