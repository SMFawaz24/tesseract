#!/usr/bin/env python3
"""
default_hpa.py - Baseline 1: Standard Kubernetes Horizontal Pod Autoscaler simulator.
Mimics default HPA behavior:
- Metric: CPU Utilization
- Target: 50% average CPU
- Formula: desiredReplicas = ceil[currentReplicas * (currentMetricValue / desiredMetricValue)]
- Default 5-minute scale-down stabilization window.
"""
import time
import math
import subprocess
import argparse
import pandas as pd
import boto3

class DefaultHPASimulator:
    def __init__(self, target_cpu=50.0, min_replicas=1, max_replicas=8):
        self.target_cpu = target_cpu
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.last_scale_down_time = 0.0
        self.scale_down_stabilization_sec = 300  # Default 5-minute HPA scale-down stabilization
        self.cw = boto3.client("cloudwatch", region_name="us-east-1")

    def get_current_replicas(self):
        try:
            res = subprocess.run(
                ["kubectl", "get", "deployment", "flask-api", "-n", "autoscaler-app", "-o", "jsonpath={.spec.replicas}"],
                capture_output=True, text=True, check=True
            )
            return int(res.stdout.strip())
        except Exception:
            return 2

    def get_cpu_utilization(self):
        try:
            # Query recent CPU from CloudWatch
            now = pd.Timestamp.utcnow()
            res = self.cw.get_metric_data(
                MetricDataQueries=[{
                    "Id": "cpu",
                    "MetricStat": {
                        "Metric": {"Namespace": "AutoScaler/App", "MetricName": "CPUUtilization", "Dimensions": [{"Name": "Service", "Value": "flask-api"}]},
                        "Period": 60, "Stat": "Average"
                    },
                    "ReturnData": True
                }],
                StartTime=now - pd.Timedelta(seconds=120),
                EndTime=now
            )
            vals = res["MetricDataResults"][0]["Values"]
            return vals[0] if vals else 25.0
        except Exception:
            return 25.0

    def evaluate(self):
        current = self.get_current_replicas()
        cpu = self.get_cpu_utilization()
        
        # Standard HPA algorithm
        ratio = cpu / self.target_cpu
        # Tolerance band (+/- 10%)
        if 0.9 <= ratio <= 1.1:
            desired = current
        else:
            desired = math.ceil(current * ratio)
            
        desired = max(self.min_replicas, min(self.max_replicas, desired))
        now = time.time()

        if desired < current:
            # Check scale-down stabilization
            if now - self.last_scale_down_time < self.scale_down_stabilization_sec:
                print(f"[Default-HPA] Scale down to {desired} delayed by 5-min stabilization window.")
                desired = current
            else:
                self.last_scale_down_time = now

        if desired != current:
            print(f"[Default-HPA] CPU={cpu:.1f}%, Target={self.target_cpu}%. Scaling: {current} -> {desired}")
            subprocess.run(["kubectl", "scale", "deployment", "flask-api", "-n", "autoscaler-app", f"--replicas={desired}"])
        else:
            print(f"[Default-HPA] Holding {current} replicas (CPU={cpu:.1f}%)")

if __name__ == "__main__":
    hpa = DefaultHPASimulator()
    while True:
        hpa.evaluate()
        time.sleep(15)  # Default HPA sync period is 15s

