import hashlib
import hmac
import os
from datetime import datetime

from .user_preferences import UserPreferences


class User:
    ROLES = ("OWNER", "ADMIN")
    ITERATIONS = 100_000

    def __init__(self, user_id, email, raw_password, role="OWNER"):
        self.id = user_id
        self.email = None
        self.role = None
        self.password_hash = None
        self._salt = None
        self.preferences = UserPreferences()
        self.notifications = []
        self.created_at = datetime.now()
        self.set_email(email)
        self.set_role(role)
        self.set_password(raw_password)

    def get_email(self):
        return self.email

    def get_role(self):
        return self.role

    def get_password_hash(self):
        return self.password_hash

    def get_preferences(self):
        return self.preferences

    def set_email(self, new_email):
        if not isinstance(new_email, str) or "@" not in new_email:
            raise ValueError("Invalid email address")
        self.email = new_email.strip().lower()

    def set_role(self, new_role):
        if new_role not in User.ROLES:
            raise ValueError("Role must be one of " + ", ".join(User.ROLES))
        self.role = new_role

    def set_password(self, raw_password):
        if not isinstance(raw_password, str) or len(raw_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        self._salt = os.urandom(16)
        self.password_hash = self._hash(raw_password, self._salt)

    def _hash(self, raw_password, salt):
        digest = hashlib.pbkdf2_hmac(
            "sha256", raw_password.encode(), salt, User.ITERATIONS
        )
        return digest.hex()

    def check_password(self, raw):
        return hmac.compare_digest(self._hash(raw, self._salt), self.password_hash)

    def add_notification(self, notification):
        self.notifications.append(notification)

    def unread_notifications(self):
        unread_list = []
        for notification in self.notifications:
            if not notification.is_read:
                unread_list.append(notification)

        return unread_list
