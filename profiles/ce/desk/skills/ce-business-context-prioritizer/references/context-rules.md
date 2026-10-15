# Context matching rules

- Match on exact resource ARN or ID found in both the receipt and a knowledge file.
- Match on tag key/value pairs present in the receipt and declared in knowledge.
- An exception note in knowledge lowers priority only for the matched resource and only if the exception scope matches the finding.
- Record the knowledge file path and the matched field for every reordering.
