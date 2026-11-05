# Cost-per-Request Custom Autoscaler for Kubernetes on AWS EC2

> A self-built autoscaler that watches AWS CloudWatch metrics, decides pod replica counts by evaluating the **dollar cost per served request** of candidate configurations subject to an SLO feasibility ceiling, emits structured counterfactual decision logs, and is benchmarked under chaos-style traffic, injected telemetry delays, and safety ablations.

---

## 1. Project Overview & Motivation

Default Kubernetes autoscaling (e.g. Horizontal Pod Autoscaler - HPA) and AWS Auto Scaling rely primarily on static utilization thresholds (e.g., scale out when average CPU exceeds 50–70%). This project replaces standard threshold-based scaling with a **cost-optimal, SLO-aware decision loop (MAPE-K)**:

1. **Monitor**: Collects CPU, memory, request arrival rate (RPS), and p95 latency from AWS CloudWatch.
2. **Analyse**: Normalizes metrics and calculates a weighted pressure score $S = w_{\text{cpu}}\text{cpu} + w_{\text{mem}}\text{mem} + w_{\text{rps}}\text{rps} + w_{\text{lat}}\text{lat}$.
3. **Plan**: Evaluates candidate replica states ($n-1, n, n+1$). Filters out candidates that breach latency SLOs or capacity ceilings ($>70\%$ utilization). Among feasible candidates, selects the one minimizing **cost per request**:
   $$\text{cost\_per\_request}(n) = \frac{\text{cost\_per\_hour}(n)}{\text{served\_rps}(n) \times 3600}$$
4. **Execute**: Applies safety guardrails (cooldown, hysteresis, hard min/max limits, step size clamps) and executes `kubectl scale`.
5. **Knowledge**: Writes explainable JSON records containing **counterfactual rationales** (why each alternative was accepted or rejected) and syncs logs to an encrypted S3 bucket.

---

## 2. Research Contributions & Novelty Matrix

| ID | Contribution | Defense & Novelty Justification |
|---|---|---|
| **N1** | **Cost-per-Request Candidate Scoring** | While literature primarily evaluates cost retroactively in node-hours or replica counts, this scaler directly employs real-time dollars-per-served-request as the live optimization objective under an SLO constraint. |
| **N2** | **Counterfactual Explainable Decision Logs** | Emits JSON logs capturing candidate-by-candidate evaluations, explaining why $n-1$ or $n+1$ were rejected (e.g. predicted SLO breach or sub-optimal unit cost). |
| **N3** | **Delay-Stratified Chaos Benchmarking** | Injects artificial telemetry delays $D \in \{0, 60, 120, 180\}$ seconds to systematically quantify how CloudWatch aggregation delays degrade reactive controllers versus cost-aware controllers. |
| **N4** | **Cost-of-Safety Ablation Study** | Systematically disables guardrails (cooldown, hysteresis) to measure the exact trade-off between infrastructure spend, replica churn, and SLO breaches. |

---

## 3. System Architecture

```
                         OPERATOR / AWS CLOUDSHELL
             (AWS CLI scripts, Terraform, Ansible, Locust Loadgen)
                                   │
                                   ▼
  ┌───────────────────────── AWS LAB ENVIRONMENT ─────────────────────────┐
  │  VPC: 10.0.0.0/16 (2 Public Subnets, IGW, Route Tables, Security Group) │
  │                                                                        │
  │   ┌──────────────────┐      ┌──────────────────┐ ┌──────────────────┐  │
  │   │ Control Plane    │      │ Worker 1         │ │ Worker 2         │  │
  │   │ t3.medium        │      │ t3.small         │ │ t3.small         │  │
  │   │ - kube-apiserver │◄────►│ - kubelet        │◄│ - kubelet        │  │
  │   │ - etcd           │      │ - Flask Pods     │ │ - Flask Pods     │  │
  │   │ - Custom Scaler  │      │ - Metric Daemon  │ │ - Metric Daemon  │  │
  │   └────────┬─────────┘      └────────┬─────────┘ └────────┬─────────┘  │
  │            │ kubectl scale           │ PutMetricData      │            │
  │            ▼                         ▼                    ▼            │
  │      ┌───────────┐           ┌────────────────────────────────┐        │
  │      │ K8s API   │           │      AWS CloudWatch            │        │
  │      │ (No HPA)  │           │  Namespace: AutoScaler/App     │        │
  │      └───────────┘           └───────────────┬────────────────┘        │
  │                                              │ GetMetricData           │
  │                                              ▼                         │
  │            ┌───────────────────────────────────────────┐               │
  │            │ S3 Bucket: Decision Logs, CSVs, Configs   │               │
  │            └───────────────────────────────────────────┘               │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Repository Structure

```
autoscaler/
├── infra-cli/                  # Phase 1: AWS CLI provisioning scripts (CloudShell/Lab safe)
│   ├── 01-prereqs.sh           # Validates AWS credentials, region, key pairs
│   ├── 02-network.sh           # VPC, 2 subnets, IGW, route table, security group
│   ├── 03-storage.sh           # S3 bucket, server-side encryption, lifecycle policy
│   ├── 04-compute.sh           # EC2 instances: 1 control plane + 2 workers
│   ├── 05-inventory.sh         # Generates Ansible inventory & state.env
│   ├── 06-refresh-ips.sh       # Updates IPs if EC2 instances restart
│   ├── 99-destroy.sh           # Safe cleanup of all AWS resources
│   └── policies/               # Least-privilege IAM policy documents
├── terraform/                  # Modular Terraform alternate IaC
│   ├── main.tf
│   ├── variables.tf
│   └── modules/ (network, storage, compute, iam)
├── ansible/                    # Phase 2: Configuration management
│   ├── inventory.ini
│   ├── site.yml
│   └── roles/ (common, k8s-control, k8s-worker)
├── app/                        # Phase 2: Workload
│   ├── app.py                  # Flask REST API with synthetic CPU/latency endpoints
│   ├── Dockerfile              # Container image
│   └── publisher.py            # Metric publisher daemon for CloudWatch
├── k8s/                        # Phase 2: Kubernetes resources (No HPA!)
│   ├── namespace.yaml
│   ├── deployment.yaml         # Resource requests/limits configured
│   └── service.yaml
├── scaler/                     # Phase 3 & 4: Custom autoscaler
│   ├── config.yaml             # Tunable weights, SLO limits, pricing table
│   ├── metrics.py              # CloudWatch reader
│   ├── cost.py                 # Dollars-per-request calculation engine
│   ├── guardrails.py           # Cooldown, bounds, hysteresis rules
│   ├── scaler.py               # MAPE-K control loop with counterfactual JSON logging
│   └── tests/                  # Unit tests for candidate selection
├── benchmarks/                 # Phase 5: Experimentation & evaluation
│   ├── loadgen.py              # Synthetic traffic generator (steady, ramp, spike)
│   ├── delay_wrapper.py        # Injects telemetry delay D in {0, 60, 120, 180s}
│   ├── baselines/              # Default HPA & Tuned HPA simulators
│   ├── run_matrix.py           # Benchmark runner for all 35 test blocks
│   └── analysis.py             # Generates publication-ready graphs & CSV summaries
└── docs/                       # Research documentation
    ├── SRS.md                  # Software Requirements Specification
    └── EXPERIMENTS.md          # 35-run benchmark methodology
```

---

## 5. Quick-Start Guide (Video Recording Ready)

Follow the step-by-step commands provided in the project runbook to provision, configure, run, and benchmark the cluster.
