"""
metrics.py - CloudWatch metrics reader with support for telemetry delay injection.
Reads CPU, memory, request rate, and latency, returning normalized values.
"""
import time
import os
import boto3
import pandas as pd

class CloudWatchMetricsReader:
    def __init__(self, namespace="AutoScaler/App", region="us-east-1", delay_seconds=0):
        self.namespace = namespace
        self.region = region
        self.delay_seconds = delay_seconds  # Delay injection D in {0, 60, 120, 180}
        self.cw = boto3.client("cloudwatch", region_name=region)

    def fetch_recent_metrics(self, window_seconds=120) -> pd.DataFrame:
        """
        Fetches metric data from CloudWatch using GetMetricData.
        If delay_seconds > 0, shifts query window backwards by D seconds.
        """
        now = time.time() - self.delay_seconds
        start_time = pd.Timestamp.utcfromtimestamp(now - window_seconds)
        end_time = pd.Timestamp.utcfromtimestamp(now)

        queries = [
            {
                "Id": "m_cpu",
                "MetricStat": {
                    "Metric": {
                        "Namespace": self.namespace,
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "Service", "Value": "flask-api"}]
                    },
                    "Period": 60,
                    "Stat": "Average"
                },
                "ReturnData": True
            },
            {
                "Id": "m_mem",
                "MetricStat": {
                    "Metric": {
                        "Namespace": self.namespace,
                        "MetricName": "MemoryUtilization",
                        "Dimensions": [{"Name": "Service", "Value": "flask-api"}]
                    },
                    "Period": 60,
                    "Stat": "Average"
                },
                "ReturnData": True
            },
            {
                "Id": "m_rps",
                "MetricStat": {
                    "Metric": {
                        "Namespace": self.namespace,
                        "MetricName": "RequestRate",
                        "Dimensions": [{"Name": "Service", "Value": "flask-api"}]
                    },
                    "Period": 60,
                    "Stat": "Average"
                },
                "ReturnData": True
            },
            {
                "Id": "m_lat",
                "MetricStat": {
                    "Metric": {
                        "Namespace": self.namespace,
                        "MetricName": "LatencyP95",
                        "Dimensions": [{"Name": "Service", "Value": "flask-api"}]
                    },
                    "Period": 60,
                    "Stat": "Average"
                },
                "ReturnData": True
            }
        ]

        try:
            response = self.cw.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending"
            )
            
            results = {}
            for item in response.get("MetricDataResults", []):
                metric_id = item["Id"]
                values = item.get("Values", [])
                results[metric_id] = values[0] if values else 0.0

            df = pd.DataFrame([{
                "cpu_percent": results.get("m_cpu", 20.0),
                "mem_percent": results.get("m_mem", 30.0),
                "request_rate": results.get("m_rps", 10.0),
                "latency_p95_ms": results.get("m_lat", 25.0)
            }])
            return df

        except Exception as e:
            # Fallback for local simulation or when CloudWatch data is still populating
            return pd.DataFrame([{
                "cpu_percent": 25.0,
                "mem_percent": 35.0,
                "request_rate": 15.0,
                "latency_p95_ms": 20.0
            }])

    def get_normalized_metrics(self, df: pd.DataFrame, target_slo_lat: float, pod_capacity_rps: float, current_replicas: int) -> dict:
        """
        Normalizes raw metrics into 0.0 to 1.0 ranges:
        - cpu: raw_cpu / 100
        - mem: raw_mem / 100
        - rps: demand / (current_replicas * pod_capacity_rps)
        - lat: p95 / target_slo_lat
        """
        row = df.iloc[0]
        cpu_norm = min(1.0, max(0.0, row["cpu_percent"] / 100.0))
        mem_norm = min(1.0, max(0.0, row["mem_percent"] / 100.0))
        
        cluster_capacity = max(1, current_replicas) * pod_capacity_rps
        rps_norm = min(1.0, max(0.0, row["request_rate"] / cluster_capacity))
        lat_norm = min(1.0, max(0.0, row["latency_p95_ms"] / target_slo_lat))

        return {
            "cpu": round(cpu_norm, 3),
            "mem": round(mem_norm, 3),
            "rps": round(rps_norm, 3),
            "lat": round(lat_norm, 3),
            "raw": {
                "cpu_pct": round(row["cpu_percent"], 2),
                "mem_pct": round(row["mem_percent"], 2),
                "rps": round(row["request_rate"], 2),
                "lat_p95_ms": round(row["latency_p95_ms"], 2)
            }
        }

