import unittest

from backend.accounts.domain.notification import Notification
from backend.accounts.domain.user import User
from backend.accounts.domain.user_preferences import UserPreferences


class UserTests(unittest.TestCase):
    def setUp(self):
        self.user = User(1, "Marwan@Example.com", "secret123")

    def test_email_normalised(self):
        self.assertEqual(self.user.get_email(), "marwan@example.com")

    def test_password_is_hashed_and_checked(self):
        self.assertNotEqual(self.user.get_password_hash(), "secret123")
        self.assertTrue(self.user.check_password("secret123"))
        self.assertFalse(self.user.check_password("wrong"))

    def test_invalid_values_rejected(self):
        with self.assertRaises(ValueError):
            self.user.set_email("nope")
        with self.assertRaises(ValueError):
            self.user.set_role("GUEST")
        with self.assertRaises(ValueError):
            self.user.set_password("short")

    def test_unread_notifications(self):
        n1, n2 = Notification(1, "a"), Notification(2, "b")
        self.user.add_notification(n1)
        self.user.add_notification(n2)
        n1.mark_read()
        self.assertEqual(self.user.unread_notifications(), [n2])


class UserPreferencesTests(unittest.TestCase):
    def test_defaults_and_reset(self):
        prefs = UserPreferences()
        prefs.set_theme("DARK")
        prefs.set_alert_threshold_kw(50)
        prefs.reset()
        self.assertEqual(prefs.get_theme(), "LIGHT")
        self.assertEqual(prefs.get_alert_threshold_kw(), 100.0)

    def test_validation(self):
        prefs = UserPreferences()
        with self.assertRaises(ValueError):
            prefs.set_theme("BLUE")
        with self.assertRaises(ValueError):
            prefs.set_alert_threshold_kw(0)


class NotificationTests(unittest.TestCase):
    def test_mark_read(self):
        n = Notification(1, "HIGH anomaly on HQ-HVAC-1", anomaly_id=7)
        self.assertFalse(n.get_is_read())
        n.mark_read()
        self.assertTrue(n.get_is_read())
        self.assertEqual(n.get_anomaly_id(), 7)

    def test_empty_message_rejected(self):
        with self.assertRaises(ValueError):
            Notification(1, "")


if __name__ == "__main__":
    unittest.main()
