"""
cost.py - Dollar cost per request calculations and capacity modeling.
Implements the core economic optimization formulas for the custom autoscaler.
"""

class CostCalculator:
    def __init__(self, pod_cost_per_hour=0.0104, capacity_per_pod=50.0):
        self.pod_cost_per_hour = pod_cost_per_hour
        self.capacity_per_pod = capacity_per_pod

    def cost_per_hour(self, replicas: int) -> float:
        """Total cluster pod running cost per hour for n replicas."""
        return max(1, replicas) * self.pod_cost_per_hour

    def served_rps(self, replicas: int, demand_rps: float) -> float:
        """Throughput served by n replicas under current demand."""
        max_capacity = max(1, replicas) * self.capacity_per_pod
        return min(max(0.1, demand_rps), max_capacity)

    def cost_per_request(self, replicas: int, demand_rps: float) -> float:
        """
        Calculates dollar cost per served request:
        cost_per_request(n) = cost_per_hour(n) / (served_rps(n) * 3600)
        """
        hourly_cost = self.cost_per_hour(replicas)
        served = self.served_rps(replicas, demand_rps)
        requests_per_hour = served * 3600.0
        return hourly_cost / requests_per_hour

    def predicted_utilization(self, replicas: int, demand_rps: float) -> float:
        """Calculates predicted pod capacity utilization (0.0 to 1.0+)."""
        total_capacity = max(1, replicas) * self.capacity_per_pod
        return demand_rps / total_capacity

