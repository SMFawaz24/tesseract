#!/usr/bin/env python3
"""
scaler.py - Cost-per-Request Custom Autoscaler for Kubernetes on AWS EC2.
Enhanced with Novelty Extensions:
- Novelty 1: Live AWS Spot Price Arbitrage Engine (ec2:DescribeSpotPriceHistory)
- Novelty 2: Lookahead Predictive Pre-Scaler (Holt-Winters Linear Trend)
- Novelty 3: Counterfactual Explainable JSON Telemetry
"""

import time
import os
import sys
import json
import argparse
import subprocess
import yaml
import boto3
from datetime import datetime, timezone

from cost import CostCalculator
from metrics import CloudWatchMetricsReader
from guardrails import Guardrails
from spot_pricing import SpotPriceReader
from forecaster import DemandForecaster

class CostAutoscaler:
    def __init__(self, config_path="scaler/config.yaml", delay_seconds=0, disable_guardrails=False, enable_spot=True, enable_forecast=True):
        # Load configuration
        if not os.path.exists(config_path):
            config_path = "config.yaml"
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.delay_seconds = delay_seconds
        self.enable_spot = enable_spot
        self.enable_forecast = enable_forecast

        self.namespace = self.config["cloudwatch"]["namespace"]
        self.region = self.config["cloudwatch"]["region"]
        self.k8s_ns = "autoscaler-app"
        self.deployment_name = "flask-api"

        # Initialize sub-modules
        self.cost_calc = CostCalculator(
            pod_cost_per_hour=self.config["pricing"]["pod_cost_per_hour"],
            capacity_per_pod=self.config["capacity"]["capacity_per_pod_rps"]
        )

        self.metrics_reader = CloudWatchMetricsReader(
            namespace=self.namespace,
            region=self.region,
            delay_seconds=self.delay_seconds
        )

        self.guardrails = Guardrails(
            min_replicas=self.config["guardrails"]["min_replicas"],
            max_replicas=self.config["guardrails"]["max_replicas"],
            cooldown_seconds=self.config["guardrails"]["cooldown_seconds"],
            max_step_size=self.config["guardrails"]["max_step_size"],
            up_thresh=self.config["guardrails"]["scale_up_hysteresis_score"],
            down_thresh=self.config["guardrails"]["scale_down_hysteresis_score"],
            enabled=not disable_guardrails
        )

        # Novelty 1: Live AWS Spot Price Reader
        self.spot_reader = SpotPriceReader(region=self.region, instance_type="t3.small")

        # Novelty 2: Lookahead Demand Forecaster
        self.forecaster = DemandForecaster(alpha=0.4, beta=0.3, horizon_steps=2)

        # S3 sync config
        self.s3_bucket = os.environ.get("BUCKET_NAME") or self.config.get("s3", {}).get("bucket_name")
        self.log_file = "decision_log.jsonl"
        self.s3_client = boto3.client("s3", region_name=self.region) if self.s3_bucket else None

    def get_current_replicas(self) -> int:
        """Fetch live replica count of deployment via kubectl."""
        try:
            res = subprocess.run(
                ["kubectl", "get", "deployment", self.deployment_name, "-n", self.k8s_ns, "-o", "jsonpath={.spec.replicas}"],
                capture_output=True, text=True, check=True
            )
            val = res.stdout.strip()
            return int(val) if val else 2
        except Exception:
            return 2

    def scale_deployment(self, target_replicas: int):
        """Execute scale action via kubectl."""
        try:
            subprocess.run(
                ["kubectl", "scale", "deployment", self.deployment_name, "-n", self.k8s_ns, f"--replicas={target_replicas}"],
                check=True
            )
            self.guardrails.record_action()
            print(f"[>>>] Scaled {self.deployment_name} to {target_replicas} replicas.")
        except Exception as e:
            print(f"[-] Failed to execute kubectl scale: {e}")

    def sync_log_to_s3(self):
        """Uploads the local decision log to the S3 bucket."""
        if not self.s3_client or not self.s3_bucket:
            return
        try:
            key = f"decision-logs/decision_log_{time.strftime('%Y%m%d')}.jsonl"
            self.s3_client.upload_file(self.log_file, self.s3_bucket, key)
        except Exception:
            pass

    def evaluate_cycle(self) -> dict:
        """Executes one MAPE-K evaluation iteration with Spot and Forecast integration."""
        ts = datetime.now(timezone.utc).isoformat()
        current_replicas = self.get_current_replicas()

        # 1. MONITOR: Fetch metrics & Live Spot Prices
        df_metrics = self.metrics_reader.fetch_recent_metrics()
        norm_metrics = self.metrics_reader.get_normalized_metrics(
            df=df_metrics,
            target_slo_lat=self.config["slo"]["target_p95_latency_ms"],
            pod_capacity_rps=self.config["capacity"]["capacity_per_pod_rps"],
            current_replicas=current_replicas
        )

        raw_rps = norm_metrics["raw"]["rps"]
        spot_info = self.spot_reader.get_live_spot_price() if self.enable_spot else None
        
        # Novelty 2: Forecast demand
        forecast_info = self.forecaster.update_and_predict(raw_rps) if self.enable_forecast else None
        effective_demand_rps = forecast_info["predicted_rps"] if (self.enable_forecast and forecast_info) else raw_rps

        # 2. ANALYSE: Weighted pressure score S
        w = self.config["weights"]
        score = (
            w["cpu"] * norm_metrics["cpu"] +
            w["mem"] * norm_metrics["mem"] +
            w["rps"] * norm_metrics["rps"] +
            w["lat"] * norm_metrics["lat"]
        )
        score = round(score, 3)

        # 3. PLAN: Candidate generation & Counterfactual SLO Filter
        candidates_pool = sorted(list(set([max(1, current_replicas - 1), current_replicas, current_replicas + 1])))
        candidate_evaluations = []
        feasible_candidates = []
        util_ceiling = self.config["slo"]["max_utilization_ceiling"]
        target_slo = self.config["slo"]["target_p95_latency_ms"]

        # Pod cost: on-demand vs live spot
        on_demand_pod_cost = self.config["pricing"]["pod_cost_per_hour"]
        spot_pod_cost = (spot_info["spot_price_per_hour"] / 2.0) if spot_info else on_demand_pod_cost

        for cand in candidates_pool:
            # Predict utilization under effective (lookahead) demand
            pred_util = float(self.cost_calc.predicted_utilization(cand, effective_demand_rps))
            cost_req_ondemand = float(self.cost_calc.cost_per_request(cand, effective_demand_rps))
            
            # Spot cost per request
            hourly_spot_cost = cand * spot_pod_cost
            served = self.cost_calc.served_rps(cand, effective_demand_rps)
            cost_req_spot = float(hourly_spot_cost / (served * 3600.0))

            is_feasible = bool(pred_util <= util_ceiling)
            reason = "feasible"
            if pred_util > util_ceiling:
                is_feasible = False
                reason = f"predicted utilisation {pred_util:.2f} > ceiling {util_ceiling:.2f}"
            elif norm_metrics["raw"]["lat_p95_ms"] > target_slo and cand < current_replicas:
                is_feasible = False
                reason = f"p95 latency {norm_metrics['raw']['lat_p95_ms']:.1f}ms exceeds SLO {target_slo:.1f}ms"

            eval_entry = {
                "replicas": int(cand),
                "feasible": bool(is_feasible),
                "cost_per_request_ondemand": round(cost_req_ondemand, 8) if is_feasible else None,
                "cost_per_request_spot": round(cost_req_spot, 8) if is_feasible else None,
                "predicted_utilization": round(pred_util, 2),
                "reason": reason
            }
            candidate_evaluations.append(eval_entry)
            if is_feasible:
                feasible_candidates.append(eval_entry)

        # 4. CHOOSE CHEAPEST FEASIBLE CANDIDATE
        if feasible_candidates:
            # Pick based on cost_per_request
            sort_key = "cost_per_request_spot" if self.enable_spot else "cost_per_request_ondemand"
            feasible_candidates.sort(key=lambda c: c[sort_key])
            desired_replicas = feasible_candidates[0]["replicas"]
            cheapest_cost = feasible_candidates[0][sort_key]
            decision_rationale = (
                f"{desired_replicas} replicas is cheapest feasible option "
                f"(${cheapest_cost:.8f}/req using {sort_key.replace('cost_per_request_', '')})"
            )
        else:
            desired_replicas = current_replicas + 1
            decision_rationale = "No candidate feasible; predictive pre-scale out triggered"

        # 5. EXECUTE: Guardrails & Action
        final_replicas, guardrail_status = self.guardrails.check_guardrails(
            current_replicas=current_replicas,
            desired_replicas=desired_replicas,
            pressure_score=score
        )

        if final_replicas > current_replicas:
            action = "scale_up"
        elif final_replicas < current_replicas:
            action = "scale_down"
        else:
            action = "hold"

        if action != "hold":
            self.scale_deployment(final_replicas)

        # 6. KNOWLEDGE: Structured Counterfactual Log Record
        decision_record = {
            "ts": ts,
            "current_replicas": current_replicas,
            "target_replicas": final_replicas,
            "action": action,
            "metrics": norm_metrics,
            "pressure_score": score,
            "forecast": forecast_info,
            "spot_market": spot_info,
            "candidates": candidate_evaluations,
            "guardrails": guardrail_status,
            "telemetry_delay_sec": self.delay_seconds,
            "reason": decision_rationale
        }

        # Append to JSONL log
        with open(self.log_file, "a") as f:
            f.write(json.dumps(decision_record, default=str) + "\n")

        print(json.dumps(decision_record, indent=2, default=str))
        self.sync_log_to_s3()

        return decision_record

    def run_loop(self, interval_seconds=30):
        print(f"[*] Starting Custom Cost Autoscaler (interval={interval_seconds}s, delay={self.delay_seconds}s, spot={self.enable_spot}, forecast={self.enable_forecast})")
        try:
            while True:
                self.evaluate_cycle()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n[!] Autoscaler loop stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cost-per-Request Autoscaler with Spot Arbitrage & Predictive Lookahead")
    parser.add_argument("--config", default="scaler/config.yaml", help="Path to config.yaml")
    parser.add_argument("--delay", type=int, default=0, help="Injected telemetry delay D (seconds)")
    parser.add_argument("--no-guardrails", action="store_true", help="Ablation: Disable safety guardrails")
    parser.add_argument("--no-spot", action="store_true", help="Disable live spot pricing")
    parser.add_argument("--no-forecast", action="store_true", help="Disable predictive pre-scaling")
    parser.add_argument("--once", action="store_true", help="Run a single evaluation cycle and exit")
    parser.add_argument("--interval", type=int, default=30, help="Cycle interval in seconds")

    args = parser.parse_args()

    scaler = CostAutoscaler(
        config_path=args.config,
        delay_seconds=args.delay,
        disable_guardrails=args.no_guardrails,
        enable_spot=not args.no_spot,
        enable_forecast=not args.no_forecast
    )

    if args.once:
        scaler.evaluate_cycle()
    else:
        scaler.run_loop(interval_seconds=args.interval)
