# Version-aware control mapping

Use the actual finding's Compliance.SecurityControlId and Compliance.AssociatedStandards, or legacy ProductFields standard/control metadata. Preserve standard ARN/version, control ID, status and finding ID. Do not infer a numbered CIS requirement from a title or resource type.

If a versioned operator-supplied mapping is available, cite its exact entry and provenance. Otherwise report the observed Security Hub control and say that the CIS requirement/version is not established. Never mix CIS benchmark versions or equate FSBP IDs with CIS requirement numbers. A mapping is not proof of compliance; an absent mapping is unknown.

AWS reference: https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html
