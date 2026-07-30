import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zoom_meeting


class TestLoadEnv(unittest.TestCase):
    def test_load_env_parses_key_value_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# 주석\n"
                "ZOOM_ACCOUNT_ID=acc123\n"
                'ZOOM_CLIENT_ID="cid123"\n'
                "\n"
                "ZOOM_CLIENT_SECRET=secret123\n",
                encoding="utf-8",
            )
            result = zoom_meeting.load_env(env_path)
        self.assertEqual(result["ZOOM_ACCOUNT_ID"], "acc123")
        self.assertEqual(result["ZOOM_CLIENT_ID"], "cid123")
        self.assertEqual(result["ZOOM_CLIENT_SECRET"], "secret123")

    def test_load_env_missing_file_returns_empty_dict(self):
        result = zoom_meeting.load_env(Path("존재하지않는경로") / ".env")
        self.assertEqual(result, {})


class TestLoadCredentials(unittest.TestCase):
    def test_load_credentials_success(self):
        env = {
            "ZOOM_ACCOUNT_ID": "acc123",
            "ZOOM_CLIENT_ID": "cid123",
            "ZOOM_CLIENT_SECRET": "secret123",
            "ZOOM_USER_EMAIL": "user@example.com",
        }
        creds = zoom_meeting.load_credentials(env)
        self.assertEqual(creds["ZOOM_USER_EMAIL"], "user@example.com")

    def test_load_credentials_missing_raises_with_key_names(self):
        env = {"ZOOM_ACCOUNT_ID": "acc123"}
        with self.assertRaises(ValueError) as ctx:
            zoom_meeting.load_credentials(env)
        self.assertIn("ZOOM_CLIENT_ID", str(ctx.exception))
        self.assertIn("ZOOM_CLIENT_SECRET", str(ctx.exception))
        self.assertIn("ZOOM_USER_EMAIL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
