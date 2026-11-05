"""
forecaster.py - Online Lookahead Predictive Pre-Scaler.
Implements Holt's Double Exponential Smoothing (Holt-Winters Linear Trend)
to extrapolate request arrival rates (RPS) and defeat CloudWatch telemetry delay.
"""

class DemandForecaster:
    def __init__(self, alpha=0.4, beta=0.3, horizon_steps=2):
        """
        alpha: Smoothing parameter for level (0.0 to 1.0)
        beta: Smoothing parameter for trend (0.0 to 1.0)
        horizon_steps: Number of cycles into the future to forecast (e.g. 2 cycles = 60s)
        """
        self.alpha = alpha
        self.beta = beta
        self.horizon_steps = horizon_steps

        self.level = None
        self.trend = 0.0
        self.history = []

    def update_and_predict(self, current_rps: float) -> dict:
        """
        Ingests the latest observed RPS, updates level & trend,
        and forecasts demand h steps ahead.
        """
        self.history.append(current_rps)
        if len(self.history) > 20:
            self.history.pop(0)

        if self.level is None:
            self.level = current_rps
            self.trend = 0.0
            predicted_rps = current_rps
        else:
            prev_level = self.level
            # Update level
            self.level = self.alpha * current_rps + (1.0 - self.alpha) * (self.level + self.trend)
            # Update trend
            self.trend = self.beta * (self.level - prev_level) + (1.0 - self.beta) * self.trend
            # Project h steps into future
            predicted_rps = max(0.0, self.level + self.horizon_steps * self.trend)

        trend_direction = "rising" if self.trend > 0.5 else ("falling" if self.trend < -0.5 else "stable")

        return {
            "current_rps": round(current_rps, 2),
            "predicted_rps": round(predicted_rps, 2),
            "trend_rate": round(self.trend, 3),
            "trend_direction": trend_direction,
            "lookahead_cycles": self.horizon_steps
        }

