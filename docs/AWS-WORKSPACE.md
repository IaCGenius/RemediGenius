# Standalone CE on AWS

This deployment runs the same CE container as the workstation option. S3 owns durable records and original documents; the container uses a temporary in-memory data directory and rebuilds its index at startup. It is a private, single-operator console, not the hosted multi-tenant product.

## Identities and boundaries

| Identity | Purpose | Permissions |
|---|---|---|
| Deployment operator | Review/apply infrastructure | Existing provisioning access; never passed to the container |
| CE host instance role | Retrieve the reviewed image and persist workspace records | Exact image read, workspace prefix list/read/conditional create, SSM managed-instance communication |
| Source read role | Collect selected AWS evidence | Separate role from `deploy/aws-access`; not automatically granted to the console |
| Hermes | Interpret selected exports | Separate runtime and model credentials; no host or storage identity required |

The host uses IMDSv2 with hop limit two so the CE container can obtain and refresh the **restricted host role** through the standard AWS SDK provider. This deliberately grants the CE process that role; it is not credential isolation from the host. Do not colocate an untrusted agent or builder on this host. The instance role cannot remediate cloud resources. It explicitly denies Parameter Store reads that the standard SSM managed-instance policy would otherwise grant. CE does not require parameter-backed SSM associations. Access to the host through SSM is administrative access and should be restricted to operators.

The security group has no inbound rules. The console is published only on host loopback and accessed through SSM port forwarding. The example uses a public IPv4 address for outbound package/S3/SSM access in an existing internet-routed subnet; it does not expose a public web service. A private-subnet alternative needs working outbound access or endpoints and is not automatically provisioned here.

## Provision in small steps

1. Create the durable bucket and storage identity using `deploy/aws-storage`, or select an existing protected bucket. The root creates public-access blocking, encryption, versioning and a TLS-only bucket policy. Terraform prevents accidental bucket destruction. Keep state and parameter files private.
2. Build `docker build -t remedigenius-ce:0.1.0rc7 .`, then run `python tools/package_runtime.py`. Upload that archive to a private artifact key in the bucket using your existing AWS CLI. Retain the returned SHA256. The image contains application code, not your workspace or credentials.
3. Supply `account_id`, `region`, `subnet_id`, `name`, `bucket_name`, `workspace_prefix`, `image_key`, and `image_sha256` to the `deploy/aws-workspace` Terraform root. It creates the host and IAM/network boundary; it does not enable cloud security products or deploy Hermes. Review `terraform plan -out=host.tfplan`, then apply that exact plan.
4. Wait for bootstrap and SSM registration. Bootstrap downloads the image archive, verifies its SHA256, loads it, and starts the console. Do not interpret EC2's running state as proof that the app is ready; check container health through SSM.
5. Forward the port with AWS's `AWS-StartPortForwardingSession` document: remote `portNumber` 8765, a chosen `localPortNumber`, and the returned instance ID. Open the forwarded localhost URL. The AWS CLI Session Manager plugin is needed on the workstation.

All source is under `deploy/aws-workspace/`. No generated agent code is deployed by this path. The host uses a 16GB encrypted root disk and a t3.small instance. EC2, public IPv4, retained EBS, S3 requests/storage and any logs have AWS charges. Stopping the instance ends its compute runtime but does not delete retained storage. No schedule is created.

## Replace, recover and stop

Only one active writer may use a workspace prefix. Stop the old console before replacement. Starting a new container with the same bucket/prefix reconstructs the cache and restores document originals; invalid or unavailable durable records fail startup. The old cache is not a required recovery input. Model sessions and Terraform state are outside this workspace contract.

For routine retirement, stop the instance through the AWS console/CLI after reviewing its ID. To remove the compute stack, review a destroy plan for **this root only**. The durable bucket belongs to another root and remains. Never reuse the main product's state or attach its data volume to this stack.

Source collection remains an explicit operator workflow. Do not grant storage identities broad read access merely to make collection convenient. Workstation collectors can continue using a scoped source role and a dedicated storage profile. Cloud-native collector scheduling, agent hosting and automatic remediation are separate features.

## Give the investigation to your agent

In Connections, export the selected assessment and choose **Download investigation ZIP**. Extract it on your workstation, then give Hermes the extracted `START-HERE.md` and investigation skill. This works for local Docker and an SSM-forwarded AWS console; container paths do not need to exist on the workstation. The download verifies the export manifest and rejects modified files. It does not send anything to a model.

IAM reference: [AWS SSM managed-instance policy contents](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedInstanceCore.html).
