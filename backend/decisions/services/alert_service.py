from ..domain.notification import Notification


class AlertService:
    def __init__(self, detector, budget):
        self.detector = detector
        self.budget = budget
        self.notifications = []
        self._next_id = 1

    def check_and_notify(self, projected_cost, readings, baseline):
        created = []
        if self.budget.is_overrun(projected_cost):
            created.append(self._notify(
                "Projected bill EUR %s exceeds budget EUR %s"
                % (projected_cost, self.budget.get_monthly_limit_eur()), "HIGH"))
        for anomaly in self.detector.detect(readings, baseline):
            created.append(self._notify(
                "Hour %s is %s%% above baseline" % (anomaly["hour"], anomaly["deviation_pct"]),
                anomaly["severity"]))
        return created

    def pending(self):
        return [n for n in self.notifications if not n.is_acknowledged()]

    def _notify(self, message, severity):
        notification = Notification(self._next_id, message, severity)
        self._next_id += 1
        self.notifications.append(notification)
        return notification
