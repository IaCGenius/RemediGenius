# Local collector provenance

executor.py and operations.json: IaCGenius/RemediGenius@f33b42c:
modules/aws-read-executor/. discovery.py: same commit, modules/native-source-discovery/collector.py.
evidence_compare.py: same commit, profiles/ce/desk/skills/ce-aws-read/scripts/evidence_compare.py.
Apache-2.0. Existing bounded collection/receipt logic is reused, not replaced with
LLM-generated collection. server.py adds local Unix-socket transport.

Dependencies are pinned in requirements.txt. AWS SDK uses instance-profile
credentials on Spot; none are returned to Hermes. Workstation uses the operator's
AWS credential chain in the collector only. Python image digest is a deployment pin.
