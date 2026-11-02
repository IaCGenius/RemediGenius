-- Evaluation recipes for CE's Glue-cataloged Iceberg tables.
-- Select the CE database and restricted analytics workgroup outside this file.
-- These use current table snapshots, not the desk's cross-table as-of contract.

-- Current queue: observation history must not be substituted for current_findings.
SELECT priority, count(*) AS findings, count(DISTINCT finding_key) AS distinct_findings
FROM current_findings GROUP BY priority ORDER BY priority;

-- Coverage observations, not a claim that these source checks all succeeded.
SELECT source, status, count(*) AS observations
FROM (SELECT DISTINCT event_id, source, status FROM coverage)
GROUP BY source, status ORDER BY source, status;

-- Distinguish repeated observations from distinct findings. This is not recurrence.
SELECT event_day, count(DISTINCT event_id) AS observations,
       count(DISTINCT ce.finding_key) AS distinct_findings
FROM findings GROUP BY event_day ORDER BY event_day DESC LIMIT 30;

-- An empty result means no recorded attempts, not successful remediation.
SELECT outcome, count(DISTINCT event_id) AS attempts
FROM verification_attempts GROUP BY outcome ORDER BY outcome;

-- Join scan counts with coverage; source-specific comparisons still require scope checks.
WITH c AS (
  SELECT run_id, count(*) AS source_checks,
         count_if(status <> 'ok' OR truncated) AS gaps
  FROM (SELECT DISTINCT event_id, run_id, status, truncated FROM coverage)
  GROUP BY run_id
), s AS (
  SELECT run_id, max(completed_at) AS completed_at, max(findings_count) AS findings_count
  FROM scan_runs GROUP BY run_id
)
SELECT s.completed_at, s.findings_count, c.source_checks, c.gaps
FROM s LEFT JOIN c ON s.run_id = c.run_id
ORDER BY s.completed_at DESC LIMIT 10;
