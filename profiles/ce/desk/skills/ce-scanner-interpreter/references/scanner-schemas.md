# Reading selected scanner excerpts

Formats vary by scanner/version/export. Inspect supplied structure; do not claim an implemented scanner adapter.
- Prowler may use ASFF/OCSF or older CheckID/Status/ResourceId/Severity exports. Identify actual field names and metadata before interpreting.
- Checkov results commonly nest passed_checks/failed_checks/skipped_checks under results, sometimes in a list by check_type. Preserve check_id, resource, file_path and check_result as present; a severity may be absent.
- Trivy commonly nests Target and Vulnerabilities/Misconfigurations under Results. Distinguish package vulnerabilities from IaC misconfigurations and preserve status/severity as supplied.

If the selected view cannot expose raw JSON/CSV, request a bounded readable text/Markdown export through the existing knowledge workflow. No arbitrary filesystem access, scanner execution or counts over unseen/truncated results. Cite report/version/time and label imported claims as scanner-reported, not fresh AWS observations. Unknown schemas require clarification, not invented mappings.
