from ..errors import InvalidThresholdError


class BaselineAnomalyDetector:
    def __init__(self, threshold_pct=30):
        self.threshold_pct = None
        self.set_threshold_pct(threshold_pct)

    def get_threshold_pct(self):
        return self.threshold_pct

    def set_threshold_pct(self, threshold_pct):
        if threshold_pct <= 0:
            raise InvalidThresholdError("Threshold must be positive")
        self.threshold_pct = float(threshold_pct)

    def detect(self, readings, baseline):
        anomalies = []
        for hour, kwh in readings.items():
            expected = baseline.get(hour)
            if not expected:
                continue
            deviation = (kwh - expected) / expected * 100
            if deviation > self.threshold_pct:
                anomalies.append({
                    "hour": hour,
                    "deviation_pct": round(deviation, 1),
                    "severity": self._rate(deviation),
                })
        return anomalies

    def _rate(self, deviation):
        if deviation >= self.threshold_pct * 2:
            return "HIGH"
        if deviation >= self.threshold_pct * 1.5:
            return "MEDIUM"
        return "LOW"
