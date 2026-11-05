"""
Unit tests for the Cost-per-Request Custom Autoscaler.
Tests candidate scoring, SLO filtering, cost calculations, and guardrails.
"""
import pytest
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cost import CostCalculator
from guardrails import Guardrails

def test_cost_calculation():
    calc = CostCalculator(pod_cost_per_hour=0.0104, capacity_per_pod=50.0)
    
    # Cost for 2 replicas
    assert calc.cost_per_hour(2) == 0.0208
    
    # 2 replicas serving 80 RPS
    served = calc.served_rps(2, 80.0)
    assert served == 80.0
    
    # Cost per request
    cost_req = calc.cost_per_request(2, 80.0)
    expected = 0.0208 / (80.0 * 3600.0)
    assert abs(cost_req - expected) < 1e-12

def test_predicted_utilization_slo_ceiling():
    calc = CostCalculator(pod_cost_per_hour=0.0104, capacity_per_pod=50.0)
    
    # 1 replica with 40 RPS -> 40/50 = 0.80 (exceeds 0.70 ceiling)
    util_1 = calc.predicted_utilization(1, 40.0)
    assert util_1 == 0.80
    assert util_1 > 0.70  # Should be flagged unfeasible
    
    # 2 replicas with 40 RPS -> 40/100 = 0.40 (feasible)
    util_2 = calc.predicted_utilization(2, 40.0)
    assert util_2 == 0.40
    assert util_2 <= 0.70  # Feasible

def test_guardrails_cooldown_and_bounds():
    gr = Guardrails(min_replicas=1, max_replicas=5, cooldown_seconds=60, enabled=True)
    
    # 1. First scaling action is allowed
    target, status = gr.check_guardrails(current_replicas=2, desired_replicas=3, pressure_score=0.75)
    assert target == 3
    assert status["cooldown_active"] is False
    
    # Record action
    gr.record_action()
    
    # 2. Immediate second action should be blocked by cooldown
    target_blocked, status_blocked = gr.check_guardrails(current_replicas=3, desired_replicas=4, pressure_score=0.85)
    assert target_blocked == 3
    assert status_blocked["cooldown_active"] is True

def test_guardrails_ablation_mode():
    # Ablation mode: guardrails disabled
    gr = Guardrails(enabled=False)
    gr.record_action()
    
    # Should allow scale action without cooldown
    target, status = gr.check_guardrails(current_replicas=2, desired_replicas=4, pressure_score=0.9)
    assert target == 4
    assert status["enabled"] is False

