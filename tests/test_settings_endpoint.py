"""
Project: Reus
Founder: Lotfi Mahiddine
Organization: Reulink
Contact: Contact@reulink.app

اختبارات لمسار /settings الجديد وinfrastructure/env_file_writer.py —
يتيح تغيير إعدادات مختارة (تلغرام، منفِّذ المهام) من لوحة التحكم بدل
تحرير .env يدويًا. الأهم أمنيًا: التحقق أن REUS_API_KEY/REUS_USER_API_KEY
لا يمكن تغييرهما عبر هذا المسار مهما كانت الحمولة المُرسَلة.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from infrastructure.env_file_writer import (
    InvalidSettingKey,
    InvalidSettingValue,
    read_env_file,
    update_env_file,
)


class TestEnvFileWriter(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.env_path = os.path.join(self.tmp_dir, ".env")
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write("REUS_API_KEY=super-secret-admin-key\nREUS_TELEGRAM_ENABLED=false\n")

    def test_update_replaces_existing_key_in_place(self):
        update_env_file({"REUS_TELEGRAM_ENABLED": "true"}, self.env_path)
        values = read_env_file(self.env_path)
        self.assertEqual(values["REUS_TELEGRAM_ENABLED"], "true")

    def test_update_appends_a_new_key_not_previously_present(self):
        update_env_file({"REUS_TASK_EXECUTOR": "ollama"}, self.env_path)
        values = read_env_file(self.env_path)
        self.assertEqual(values["REUS_TASK_EXECUTOR"], "ollama")

    def test_admin_key_can_never_be_modified_through_this_path(self):
        with self.assertRaises(InvalidSettingKey):
            update_env_file({"REUS_API_KEY": "attacker-supplied-value"}, self.env_path)
        with open(self.env_path, encoding="utf-8") as f:
            self.assertIn("REUS_API_KEY=super-secret-admin-key", f.read())

    def test_user_key_can_never_be_modified_through_this_path(self):
        with self.assertRaises(InvalidSettingKey):
            update_env_file({"REUS_USER_API_KEY": "attacker-supplied-value"}, self.env_path)

    def test_newline_in_value_is_rejected_to_prevent_key_smuggling(self):
        with self.assertRaises(InvalidSettingValue):
            update_env_file(
                {"REUS_TELEGRAM_BOT_TOKEN": "x\nREUS_API_KEY=attacker_injected_key"}, self.env_path
            )
        with open(self.env_path, encoding="utf-8") as f:
            self.assertIn("REUS_API_KEY=super-secret-admin-key", f.read())

    def test_secret_fields_are_masked_not_returned_in_plaintext(self):
        update_env_file({"REUS_TELEGRAM_BOT_TOKEN": "12345:real-token-value"}, self.env_path)
        values = read_env_file(self.env_path)
        self.assertNotIn("real-token-value", values["REUS_TELEGRAM_BOT_TOKEN"])
        self.assertEqual(values["REUS_TELEGRAM_BOT_TOKEN"], "***configured***")

    def test_non_editable_fields_are_never_returned_at_all(self):
        values = read_env_file(self.env_path)
        self.assertNotIn("REUS_API_KEY", values)

    def test_unrelated_lines_and_comments_survive_an_update_untouched(self):
        with open(self.env_path, "a", encoding="utf-8") as f:
            f.write("# a manual comment\nREUS_DATABASE_URL=postgresql://example\n")
        update_env_file({"REUS_TASK_EXECUTOR": "model_router"}, self.env_path)
        with open(self.env_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# a manual comment", content)
        self.assertIn("REUS_DATABASE_URL=postgresql://example", content)


class TestSettingsEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp_dir)
        with open(".env", "w", encoding="utf-8") as f:
            f.write("REUS_API_KEY=admin-test-key\nREUS_TELEGRAM_ENABLED=false\n")

        os.environ["REUS_API_KEY"] = "admin-test-key"
        import config

        config.get_settings.cache_clear()

        from fastapi.testclient import TestClient

        from api.main import app

        self.client = TestClient(app)

    def tearDown(self):
        os.chdir(self.original_cwd)
        os.environ.pop("REUS_API_KEY", None)
        import config

        config.get_settings.cache_clear()

    def test_get_requires_admin_key(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 401)

    def test_get_returns_editable_keys_and_current_values(self):
        response = self.client.get("/settings", headers={"x-api-key": "admin-test-key"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("REUS_TELEGRAM_BOT_TOKEN", body["editable_keys"])
        self.assertNotIn("REUS_API_KEY", body["editable_keys"])

    def test_post_saves_and_reports_restart_required(self):
        response = self.client.post(
            "/settings",
            json={"values": {"REUS_TELEGRAM_ENABLED": "true", "REUS_TELEGRAM_BOT_TOKEN": "123:abc"}},
            headers={"x-api-key": "admin-test-key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restart_required"])

        with open(".env", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("REUS_TELEGRAM_ENABLED=true", content)

    def test_post_rejects_admin_key_change_with_400(self):
        response = self.client.post(
            "/settings", json={"values": {"REUS_API_KEY": "hacked"}}, headers={"x-api-key": "admin-test-key"}
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
