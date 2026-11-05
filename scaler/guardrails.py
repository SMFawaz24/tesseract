"""
guardrails.py - Safety bounds, cooldown, and hysteresis controller.
Supports full ablation mode (enabled=False) to measure the cost-of-safety.
"""
import time

class Guardrails:
    def __init__(self, min_replicas=1, max_replicas=8, cooldown_seconds=45, 
                 max_step_size=2, up_thresh=0.65, down_thresh=0.35, enabled=True):
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.cooldown_seconds = cooldown_seconds
        self.max_step_size = max_step_size
        self.up_thresh = up_thresh
        self.down_thresh = down_thresh
        self.enabled = enabled
        
        self.last_scale_time = 0.0

    def check_guardrails(self, current_replicas: int, desired_replicas: int, pressure_score: float) -> tuple[int, dict]:
        """
        Applies guardrails:
        1. If disabled (ablation mode), allows any valid candidate within [1, 20].
        2. Clamps to [min_replicas, max_replicas].
        3. Enforces cooldown periods.
        4. Applies hysteresis thresholds.
        5. Limits step size.
        Returns: (approved_replicas, guardrail_status_dict)
        """
        now = time.time()
        time_since_scale = now - self.last_scale_time
        
        status = {
            "enabled": self.enabled,
            "cooldown_active": False,
            "hysteresis_applied": False,
            "clamped_by_bounds": False,
            "clamped_by_step": False
        }

        # Ablation mode: guardrails completely bypassed
        if not self.enabled:
            return max(1, desired_replicas), status

        # 1. Cooldown check
        if time_since_scale < self.cooldown_seconds and desired_replicas != current_replicas:
            status["cooldown_active"] = True
            return current_replicas, status

        target = desired_replicas

        # 2. Hysteresis check
        if target > current_replicas and pressure_score < self.up_thresh:
            # Not enough sustained pressure to scale up
            status["hysteresis_applied"] = True
            target = current_replicas
        elif target < current_replicas and pressure_score > self.down_thresh:
            # Pressure not low enough to safely scale down
            status["hysteresis_applied"] = True
            target = current_replicas

        # 3. Step size clamping
        if target > current_replicas + self.max_step_size:
            target = current_replicas + self.max_step_size
            status["clamped_by_step"] = True
        elif target < current_replicas - self.max_step_size:
            target = current_replicas - self.max_step_size
            status["clamped_by_step"] = True

        # 4. Hard Min / Max bounds
        if target < self.min_replicas:
            target = self.min_replicas
            status["clamped_by_bounds"] = True
        elif target > self.max_replicas:
            target = self.max_replicas
            status["clamped_by_bounds"] = True

        return target, status

    def record_action(self):
        """Call whenever a scaling action actually executes."""
        self.last_scale_time = time.time()

