```
 ╔══════════════════════════════════════════════════════════════╗
 ║  K8s-on-EC2  –  Terraform Project  (College Edition)        ║
 ╚══════════════════════════════════════════════════════════════╝
```

# Kubernetes-on-EC2 Terraform Project

A modular Terraform project that provisions a self-managed Kubernetes
cluster on AWS EC2.  Designed for a college project: low cost, clean
code, and least-privilege IAM that you can defend in a viva.

---

## File Tree

```
k8s-terraform/
├── main.tf                      # Root module – wires all child modules
├── providers.tf                 # AWS provider & Terraform version pins
├── backend.tf                   # Remote state config (S3+DynamoDB, commented)
├── variables.tf                 # All input variables with defaults
├── outputs.tf                   # Exported values (IPs, ARNs, bucket name)
├── terraform.tfvars.example     # Copy → terraform.tfvars, fill in your values
│
└── modules/
    ├── network/                 # VPC, 2 public subnets, IGW, route table, SG
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    │
    ├── iam/                     # Two least-privilege roles + instance profiles
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    │
    ├── storage/                 # S3 bucket (versioned, encrypted, no public)
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    │
    └── compute/                 # 1 control-plane + 2 worker EC2 instances
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

---

## What Each File Does

| File | Purpose |
|------|---------|
| `main.tf` | Looks up the latest Ubuntu 22.04 AMI, then calls network → storage → iam → compute in dependency order. |
| `providers.tf` | Pins Terraform ≥ 1.5 and the `hashicorp/aws` provider ~> 5.0. Sets default tags. |
| `backend.tf` | Commented-out S3 backend block. Uncomment once you have a state bucket + DynamoDB lock table. |
| `variables.tf` | Declares every tuneable knob (region, instance types, CIDRs, key pair, etc.). |
| `outputs.tf` | Surfaces control-plane IP, worker IPs, S3 bucket name, and both role ARNs. |
| `terraform.tfvars.example` | Template – copy it, set your key pair and SSH CIDR. |

### Module: `network`
Creates a VPC with DNS support, an Internet Gateway, two public subnets
(one per AZ), a shared route table, and a security group with rules for:
SSH, K8s API (6443), intra-cluster traffic, NodePorts, HTTP/S, and all
outbound.

### Module: `storage`
Creates one S3 bucket with:
- **Versioning** enabled (protects against accidental overwrites).
- **SSE-S3 encryption** (AES-256) on all objects.
- **Public access block** on all four toggles.
- **Lifecycle rule** that expires old log versions after 30 days.

### Module: `iam`
Two IAM roles, each with its own instance profile:

1. **Node role** (`k8s-college-node-role`)
2. **Scaler role** (`k8s-college-scaler-role`)

See the IAM Policy Deep-Dive below.

### Module: `compute`
Launches 1 control-plane (`t3.medium`) and 2 workers (`t3.small`).
All instances:
- Use gp3 encrypted 20 GB root volumes.
- Run a `user_data` script that disables swap, loads `overlay` and
  `br_netfilter`, and sets the required sysctl params for kubelet.
- Are spread across the two subnets/AZs.

---

## IAM Policy Deep-Dive  (Viva-Ready Explanations)

### Role 1 – Node Role

| # | Policy | Actions | Resource | Why |
|---|--------|---------|----------|-----|
| 1a | `node-cw-policy` | `cloudwatch:PutMetricData` | `*` (with condition `cloudwatch:namespace = k8s-college/K8sMetrics`) | Nodes push custom K8s metrics (CPU, pod count) to CloudWatch. `PutMetricData` does **not** support resource-level ARNs per [AWS docs](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazoncloudwatch.html), so the resource is `*`. The namespace condition restricts writes to our project namespace only. |
| 1b | `node-s3-policy` | `s3:ListBucket` | `arn:aws:s3:::k8s-college-cluster-<acct>` | Nodes need to list objects in the bucket to find configs. Scoped to exactly one bucket. |
| 1b | `node-s3-policy` | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` | `arn:aws:s3:::k8s-college-cluster-<acct>/*` | Nodes read bootstrap scripts and write cluster state. Scoped to objects inside that single bucket only. |

### Role 2 – Scaler Role

| # | Policy | Actions | Resource | Why |
|---|--------|---------|----------|-----|
| 2a | `scaler-cw-policy` | `cloudwatch:GetMetricData` | `*` | The scaler reads metrics to decide when to scale. `GetMetricData` is a batch read-only API; it does not support resource-level ARNs. |
| 2b | `scaler-ec2-policy` | `ec2:DescribeInstances`, `ec2:DescribeSpotPriceHistory` | `*` | The scaler must discover running nodes and query spot prices. All EC2 `Describe*` actions are read-only and do not support resource-level permissions. |
| 2c | `scaler-s3-policy` | `s3:PutObject` | `arn:aws:s3:::k8s-college-cluster-<acct>/logs/*` | The scaler writes scaling-decision logs. Access is restricted to **only** the `logs/` prefix – it cannot read objects, list the bucket, or write to any other prefix. |

### Why Some Resources Are `*`

> Several AWS APIs (CloudWatch `PutMetricData`/`GetMetricData`,
> EC2 `Describe*`) do not support resource-level permissions.
> AWS documents this in the Service Authorization Reference.
> We compensate by granting **only the single action needed**
> and adding conditions where supported (e.g., the CloudWatch
> namespace condition on `PutMetricData`).

### No Wildcards

- **No wildcard actions**: every `actions` list names explicit API calls.
- **No wildcard resources** (except where AWS requires `*`): S3 policies
  use the exact bucket ARN; the scaler S3 policy even narrows to `/logs/*`.

---

## Quick-Start Commands

```bash
# 0.  Prerequisites
#     - Terraform >= 1.5 installed
#     - AWS CLI configured  (aws configure)
#     - An EC2 key pair created in the target region

# 1.  Clone & configure
cd k8s-terraform
cp terraform.tfvars.example terraform.tfvars
#     → edit terraform.tfvars: set key_pair_name, allowed_ssh_cidrs

# 2.  Initialize (downloads providers, initialises modules)
terraform init

# 3.  Preview what will be created
terraform plan

# 4.  Create the infrastructure
terraform apply
#     → type "yes" when prompted
#     → note the outputs: IPs, bucket name, role ARNs

# 5.  SSH into the control-plane
ssh -i ~/.ssh/my-key.pem ubuntu@<control_plane_public_ip>

# 6.  Tear down everything when finished
terraform destroy
#     → type "yes" to confirm
```

---

## Outputs Reference

| Output | Description |
|--------|-------------|
| `control_plane_public_ip` | Public IP of the control-plane EC2 instance |
| `worker_public_ips` | List of public IPs for worker nodes |
| `s3_bucket_name` | Name of the versioned/encrypted S3 bucket |
| `s3_bucket_arn` | Full ARN of the S3 bucket |
| `node_role_arn` | ARN of the node IAM role |
| `scaler_role_arn` | ARN of the scaler IAM role |
| `vpc_id` | ID of the VPC |

---

## Cost Notes

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| 1 × t3.medium (control-plane) | ~$30 |
| 2 × t3.small (workers) | ~$30 |
| S3 bucket (minimal storage) | < $1 |
| Data transfer (minimal) | < $1 |
| **Total** | **~$61/month** |

> **Tip:** Stop instances when not in use (`aws ec2 stop-instances`)
> to save money.  Use `t3.micro` (free-tier eligible for 12 months)
> for even lower cost, though K8s will be tight on 1 GB RAM.

---

## Next Steps (After `terraform apply`)

1. SSH into the control-plane and install `containerd` + `kubeadm`.
2. Run `kubeadm init` on the control-plane.
3. Join workers with `kubeadm join`.
4. Install a CNI plugin (Flannel or Calico).
5. Deploy your workloads!

---

## License

MIT – use freely for your college project.
