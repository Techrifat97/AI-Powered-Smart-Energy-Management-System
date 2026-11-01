from datetime import datetime


class Notification:
    def __init__(self, notification_id, message, anomaly_id=None):
        self.id = notification_id
        self.message = None
        self.anomaly_id = anomaly_id
        self.is_read = False
        self.created_at = datetime.now()
        self.set_message(message)

    def get_message(self):
        return self.message

    def get_anomaly_id(self):
        return self.anomaly_id

    def get_is_read(self):
        return self.is_read

    def get_created_at(self):
        return self.created_at

    def set_message(self, new_message):
        if not new_message:
            raise ValueError("Message cannot be empty")
        self.message = new_message

    def set_is_read(self, value):
        self.is_read = bool(value)

    def mark_read(self):
        self.is_read = True
