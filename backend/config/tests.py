"""Database configuration guards; these tests never open a database connection."""

import os
from pathlib import Path
import runpy
import secrets
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class PostgreSQLSettingsTests(SimpleTestCase):
    def setUp(self):
        self.database_env = {
            'DB_NAME': 's1_settings_checks',
            'DB_USER': 's1_settings_role',
            'DB_PASSWORD': secrets.token_urlsafe(24),
            'DB_HOST': '127.0.0.1',
            'DB_PORT': '5432',
        }

    def load_settings(self, environment):
        # Ignore developers' local .env files and never print their credentials.
        with patch.dict(os.environ, environment, clear=True), patch('dotenv.load_dotenv'):
            return runpy.run_path(str(Path(__file__).with_name('settings.py')))

    def test_database_backend_is_always_postgresql(self):
        values = self.load_settings(self.database_env)
        database = values['DATABASES']['default']
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(database['TEST']['NAME'], 'test_s1_settings_checks')
        self.assertNotEqual(database['NAME'], database['TEST']['NAME'])

    def test_missing_connection_details_fail_without_fallback(self):
        for name in self.database_env:
            with self.subTest(variable=name):
                environment = self.database_env.copy()
                del environment[name]
                with self.assertRaisesRegex(ImproperlyConfigured, name):
                    self.load_settings(environment)

    def test_test_database_must_be_separate_and_clearly_named(self):
        for name in ['s1_settings_checks', 'another_application_database', '']:
            with self.subTest(test_database=name):
                environment = dict(self.database_env, DB_TEST_NAME=name)
                with self.assertRaisesRegex(ImproperlyConfigured, 'DB_TEST_NAME'):
                    self.load_settings(environment)

    def test_database_names_cannot_be_silently_truncated(self):
        for name in ['DB_NAME', 'DB_TEST_NAME']:
            with self.subTest(variable=name):
                environment = dict(self.database_env, **{name: 'test_' + 'x' * 64})
                with self.assertRaisesRegex(ImproperlyConfigured, '63 bytes'):
                    self.load_settings(environment)
