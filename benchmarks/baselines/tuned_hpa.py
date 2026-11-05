#!/usr/bin/env python3
"""
tuned_hpa.py - Baseline 2: Tuned HPA Controller.
Uses optimized dual-threshold logic with faster stabilization (60s)
and tuned target utilization (65%) to provide a strong, fair baseline.
"""
import time
import math
import subprocess
import boto3
import pandas as pd

class TunedHPA:
    def __init__(self, target_cpu=65.0, up_threshold=70.0, down_threshold=40.0, min_replicas=1, max_replicas=8):
        self.target_cpu = target_cpu
        self.up_threshold = up_threshold
        self.down_threshold = down_threshold
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.last_scale_time = 0.0
        self.cooldown_sec = 60
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
        now = time.time()

        desired = current
        if cpu > self.up_threshold:
            desired = min(self.max_replicas, current + 1)
        elif cpu < self.down_threshold and current > self.min_replicas:
            desired = max(self.min_replicas, current - 1)

        if desired != current:
            if now - self.last_scale_time < self.cooldown_sec:
                print(f"[Tuned-HPA] Action blocked by cooldown ({int(now - self.last_scale_time)}s < {self.cooldown_sec}s)")
                return
            print(f"[Tuned-HPA] CPU={cpu:.1f}%. Scaling: {current} -> {desired}")
            subprocess.run(["kubectl", "scale", "deployment", "flask-api", "-n", "autoscaler-app", f"--replicas={desired}"])
            self.last_scale_time = now
        else:
            print(f"[Tuned-HPA] Holding {current} replicas (CPU={cpu:.1f}%)")

if __name__ == "__main__":
    tuned = TunedHPA()
    while True:
        tuned.evaluate()
        time.sleep(15)

