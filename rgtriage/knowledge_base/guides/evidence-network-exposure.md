---
type: Guide
title: "Evidence: network exposure"
description: Whether a port or service is really reachable from the internet - security group, public address, subnet route, NACL and load balancer.
tags: [remedigenius, evidence, network, ec2]
sources:
  - {id: reach, resource: "https://docs.aws.amazon.com/vpc/latest/reachability/what-is-reachability-analyzer.html", title: What is Reachability Analyzer, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "is SSH open to the internet?", "is this instance exposed?", "which security groups allow 0.0.0.0/0?".

## Reads that decide it
1. The rule: `ec2 describe_security_groups GroupIds=[...]` → `IpPermissions` with `0.0.0.0/0` or `::/0`, port range
   and protocol (`-1` means all).
2. What uses it: `ec2 describe_network_interfaces Filters=[{Name: group-id, Values: [...]}]`. A group attached to
   nothing exposes nothing today.
3. A public path: the interface's `Association.PublicIp`, the subnet's route table (`ec2 describe_route_tables`, a
   `0.0.0.0/0` route to an `igw-`), and the subnet's network ACL (`ec2 describe_network_acls`). For load balancers:
   `elbv2 describe_load_balancers` (`Scheme: internet-facing`) and listeners.
4. Several groups: page with `NextToken` and say when the answer is partial.

## Limits to say out loud
- The desk does not run Reachability Analyzer (it creates analyses)[^reach]; the verdict is assembled from the reads
  above. Say "reachable on paper" when every hop allows it, and name any hop you did not read.
- Host firewalls and application authentication are not visible.

## Stop when
You can name the rule, what it is attached to, and whether a public path exists, or the missing hop.

Related: [network exposure](/remedigenius/practices/network-exposure.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^reach]: What is Reachability Analyzer
