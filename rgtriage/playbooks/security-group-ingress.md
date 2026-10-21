# Security group open to the internet (EC2.2, EC2.13, EC2.14, EC2.18, EC2.19, EC2.53, EC2.54, Inspector network reachability)

**Means:** an ingress rule allows 0.0.0.0/0 or ::/0 to a port (SSH 22, RDP 3389, database ports, or all).
High risk when attached to running instances with public IPs; low risk if the group is unused.

**Verify:**
- `rgtriage aws ec2 describe_security_groups --params '{"GroupIds":["sg-..."]}'`
- Attached? `rgtriage aws ec2 describe_network_interfaces --params '{"Filters":[{"Name":"group-id","Values":["sg-..."]}]}'`
- Public IP / public subnet? An Inspector NETWORK_REACHABILITY finding confirms an open path.

**Terraform (provider v5 style):** narrow the CIDR or remove the rule; prefer SSM Session Manager over SSH/RDP.
```hcl
resource "aws_vpc_security_group_ingress_rule" "<name>_ssh" {
  security_group_id = aws_security_group.<name>.id
  cidr_ipv4         = var.admin_cidr # e.g. VPN egress /32, never 0.0.0.0/0
  from_port         = 22
  to_port           = 22
  ip_protocol       = "tcp"
}
```
If the code uses inline `ingress { cidr_blocks = ["0.0.0.0/0"] }` blocks, change `cidr_blocks` in place.
Do not mix inline blocks and separate rule resources on the same group; they overwrite each other.
EC2.2 (default SG): manage it with an `aws_default_security_group` that has no ingress/egress blocks.

**CloudFormation:** change `SecurityGroupIngress[].CidrIp` from `0.0.0.0/0` to a parameterized admin CIDR,
or use `SourceSecurityGroupId`.

**CLI:** `aws ec2 revoke-security-group-ingress --group-id sg-... --protocol tcp --port 22 --cidr 0.0.0.0/0`

**Trade-offs:** cutting access can lock out admins or break public services (80/443 on a load balancer
is usually intended; confirm before flagging). Provide SSM access before removing SSH.
