from datetime import datetime
from ..errors import InvalidNotificationError


class Notification:
    SEVERITIES = ("LOW", "MEDIUM", "HIGH")

    def __init__(self, notification_id, message, severity="LOW"):
        self.id = notification_id
        self.message = None
        self.severity = None
        self._acknowledged = False
        self.created_at = datetime.now()
        self.set_message(message)
        self.set_severity(severity)

    def get_message(self):
        return self.message

    def get_severity(self):
        return self.severity

    def is_acknowledged(self):
        return self._acknowledged

    def get_created_at(self):
        return self.created_at

    def set_message(self, new_message):
        if not new_message:
            raise InvalidNotificationError("Message cannot be empty")
        self.message = new_message

    def set_severity(self, new_severity):
        if new_severity not in Notification.SEVERITIES:
            raise InvalidNotificationError("Severity must be one of " + ", ".join(Notification.SEVERITIES))
        self.severity = new_severity

    def acknowledge(self):
        self._acknowledged = True
