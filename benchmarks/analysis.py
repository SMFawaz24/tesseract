#!/usr/bin/env python3
"""
analysis.py - Generates publication-ready graphs and summary statistics
from benchmark results CSV.
Produces:
1. 'cost_per_request_by_controller.png' (Core objective comparison)
2. 'telemetry_delay_impact.png' (Novelty N3 delay sweep)
3. 'safety_ablation_tradeoff.png' (Novelty N4 cost-of-safety ablation)
"""
import os
import pandas as pd
import matplotlib.pyplot as plt

RESULTS_FILE = "results.csv"

def generate_charts():
    if not os.path.exists(RESULTS_FILE):
        print(f"[-] {RESULTS_FILE} not found. Run 'run_matrix.py' first.")
        return

    df = pd.read_csv(RESULTS_FILE)
    df["cost_per_request_dollar"] = df["cost_per_request_dollar"].astype(float)
    df["slo_violations_sec"] = df["slo_violations_sec"].astype(float)
    df["replica_churn"] = df["replica_churn"].astype(int)

    os.makedirs("charts", exist_ok=True)
    plt.style.use("ggplot")

    # -------------------------------------------------------------
    # Chart 1: Cost per Request by Controller (Core Comparison)
    # -------------------------------------------------------------
    plt.figure(figsize=(8, 5))
    core_df = df[(df["delay_sec"] == 0) & (df["guardrails_enabled"] == True)]
    grouped_cost = core_df.groupby("controller")["cost_per_request_dollar"].mean() * 1e6
    bars = grouped_cost.plot(kind="bar", color=["#e74c3c", "#f39c12", "#27ae60"], edgecolor="black")
    plt.title("Mean Cost per Million Requests ($) Across Controllers", fontsize=12, fontweight="bold")
    plt.ylabel("Cost per 1M Requests ($)", fontsize=10)
    plt.xlabel("Autoscaling Controller", fontsize=10)
    plt.xticks(rotation=0)
    plt.grid(axis="y", linestyle="--", alpha=0.7)
    for p in bars.patches:
        bars.annotate(f"${p.get_height():.2f}", (p.get_x() + p.get_width() / 2., p.get_height()),
                      ha="center", va="center", xytext=(0, 6), textcoords="offset points", fontweight="bold")
    plt.tight_layout()
    plt.savefig("charts/cost_per_request_comparison.png", dpi=300)
    plt.close()
    print("[+] Generated: charts/cost_per_request_comparison.png")

    # -------------------------------------------------------------
    # Chart 2: Telemetry Delay vs SLO Violations (Novelty N3)
    # -------------------------------------------------------------
    plt.figure(figsize=(8, 5))
    delay_df = df[(df["pattern"] == "spike") & (df["guardrails_enabled"] == True)]
    for ctrl, color, marker in [("tuned_hpa", "#f39c12", "s"), ("custom_cost", "#27ae60", "o")]:
        subset = delay_df[delay_df["controller"] == ctrl].sort_values("delay_sec")
        plt.plot(subset["delay_sec"], subset["slo_violations_sec"], marker=marker, label=f"{ctrl}", linewidth=2, color=color)

    plt.title("Impact of Telemetry Delay on SLO Violation Duration (Spike Traffic)", fontsize=12, fontweight="bold")
    plt.xlabel("Injected Telemetry Delay D (seconds)", fontsize=10)
    plt.ylabel("SLO Violation Time (seconds)", fontsize=10)
    plt.xticks([0, 60, 120, 180])
    plt.legend(title="Controller")
    plt.grid(True, linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig("charts/telemetry_delay_impact.png", dpi=300)
    plt.close()
    print("[+] Generated: charts/telemetry_delay_impact.png")

    # -------------------------------------------------------------
    # Chart 3: Cost-of-Safety Ablation (Novelty N4)
    # -------------------------------------------------------------
    plt.figure(figsize=(8, 5))
    ablation_df = df[(df["controller"] == "custom_cost") & (df["delay_sec"] == 0)]
    ablation_summary = ablation_df.groupby("guardrails_enabled")[["slo_violations_sec", "replica_churn"]].mean()
    
    ax = ablation_summary.plot(kind="bar", figsize=(8, 5), color=["#e74c3c", "#3498db"], edgecolor="black")
    plt.title("Ablation Study: Stability & SLO Penalty When Guardrails Disabled", fontsize=12, fontweight="bold")
    plt.ylabel("Seconds / Count", fontsize=10)
    plt.xlabel("Guardrails Enabled", fontsize=10)
    plt.xticks([0, 1], ["Guardrails OFF (Ablation)", "Guardrails ON (Default)"], rotation=0)
    plt.grid(axis="y", linestyle="--", alpha=0.7)
    plt.legend(["SLO Violations (sec)", "Replica Churn (count)"])
    plt.tight_layout()
    plt.savefig("charts/safety_ablation_tradeoff.png", dpi=300)
    plt.close()
    print("[+] Generated: charts/safety_ablation_tradeoff.png")

    print("\n[OK] All graphs generated in 'charts/' directory!")

if __name__ == "__main__":
    generate_charts()
