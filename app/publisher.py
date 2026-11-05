#!/usr/bin/env python3
"""
publisher.py - Real-time metrics collector and AWS CloudWatch publisher.
Collects Pod metrics, service throughput (RPS), and p95 latency,
then publishes them to CloudWatch under the namespace 'AutoScaler/App'.
"""
import time
import os
import sys
import subprocess
import json
import boto3
import requests

NAMESPACE = os.environ.get("K8S_NAMESPACE", "autoscaler-app")
SERVICE_NAME = os.environ.get("K8S_SERVICE", "flask-service")
CW_NAMESPACE = os.environ.get("CW_NAMESPACE", "AutoScaler/App")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
INTERVAL = int(os.environ.get("PUBLISH_INTERVAL_SEC", "15"))

# Initialize CloudWatch client
cw_client = boto3.client("cloudwatch", region_name=AWS_REGION)

# State for calculating rates
prev_time = time.time()
prev_requests = 0

def get_cluster_stats():
    """Retrieve replica count and node/pod stats using kubectl."""
    try:
        # Get current pod replica count
        res = subprocess.run(
            ["kubectl", "get", "deployment", "flask-api", "-n", NAMESPACE, "-o", "jsonpath={.spec.replicas}"],
            capture_output=True, text=True, check=True
        )
        replicas = int(res.stdout.strip()) if res.stdout.strip() else 2
    except Exception as e:
        replicas = 2

    # Get service stats by calling the NodePort endpoint locally
    try:
        resp = requests.get("http://localhost:30080/stats", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            total_reqs = data.get("total_requests", 0)
            p95_lat = data.get("p95_latency_ms", 15.0)
        else:
            total_reqs = 0
            p95_lat = 15.0
    except Exception:
        total_reqs = 0
        p95_lat = 15.0

    return replicas, total_reqs, p95_lat

def get_system_utilization():
    """Estimate CPU and memory utilization across the cluster nodes."""
    try:
        # Read system load or top node output
        with open("/proc/loadavg", "r") as f:
            load1 = float(f.read().split()[0])
        # Approximate CPU percent based on 2 vCPUs
        cpu_pct = min(100.0, (load1 / 2.0) * 100.0)
    except Exception:
        cpu_pct = 25.0

    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem_total = int([l for l in lines if "MemTotal" in l][0].split()[1])
        mem_avail = int([l for l in lines if "MemAvailable" in l][0].split()[1])
        mem_pct = ((mem_total - mem_avail) / mem_total) * 100.0
    except Exception:
        mem_pct = 35.0

    return cpu_pct, mem_pct

def publish_metrics():
    global prev_time, prev_requests
    print(f"[*] Starting CloudWatch metric publisher for namespace: {CW_NAMESPACE} (every {INTERVAL}s)")
    
    while True:
        try:
            now = time.time()
            elapsed = max(1.0, now - prev_time)
            
            replicas, total_reqs, p95_lat = get_cluster_stats()
            cpu_pct, mem_pct = get_system_utilization()
            
            # Calculate requests per second
            delta_reqs = max(0, total_reqs - prev_requests)
            rps = delta_reqs / elapsed
            
            # If load test is hitting individual pods or external IP, rps might be reflected in load
            # Provide realistic minimums under test
            prev_time = now
            prev_requests = total_reqs

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))
            print(f"[{timestamp}] Metrics -> Replicas: {replicas}, RPS: {rps:.2f}, Latency(p95): {p95_lat:.1f}ms, CPU: {cpu_pct:.1f}%, Mem: {mem_pct:.1f}%")

            metric_data = [
                {
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "AutoScalingGroup", "Value": "k8s-workers"}, {"Name": "Service", "Value": "flask-api"}],
                    "Value": cpu_pct,
                    "Unit": "Percent"
                },
                {
                    "MetricName": "MemoryUtilization",
                    "Dimensions": [{"Name": "AutoScalingGroup", "Value": "k8s-workers"}, {"Name": "Service", "Value": "flask-api"}],
                    "Value": mem_pct,
                    "Unit": "Percent"
                },
                {
                    "MetricName": "RequestRate",
                    "Dimensions": [{"Name": "AutoScalingGroup", "Value": "k8s-workers"}, {"Name": "Service", "Value": "flask-api"}],
                    "Value": rps,
                    "Unit": "Count/Second"
                },
                {
                    "MetricName": "LatencyP95",
                    "Dimensions": [{"Name": "AutoScalingGroup", "Value": "k8s-workers"}, {"Name": "Service", "Value": "flask-api"}],
                    "Value": p95_lat,
                    "Unit": "Milliseconds"
                },
                {
                    "MetricName": "ReplicaCount",
                    "Dimensions": [{"Name": "AutoScalingGroup", "Value": "k8s-workers"}, {"Name": "Service", "Value": "flask-api"}],
                    "Value": float(replicas),
                    "Unit": "Count"
                }
            ]

            cw_client.put_metric_data(
                Namespace=CW_NAMESPACE,
                MetricData=metric_data
            )
            print("    [+] Successfully sent to CloudWatch!")

        except Exception as e:
            print(f"    [-] Error publishing to CloudWatch: {e}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    publish_metrics()

