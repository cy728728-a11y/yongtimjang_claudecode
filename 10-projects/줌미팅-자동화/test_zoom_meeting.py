import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

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


class TestGetAccessToken(unittest.TestCase):
    @patch("zoom_meeting.urllib.request.urlopen")
    def test_get_access_token_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"access_token": "abc123"}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        token = zoom_meeting.get_access_token("acc", "cid", "secret")

        self.assertEqual(token, "abc123")

    @patch("zoom_meeting.urllib.request.urlopen")
    def test_get_access_token_http_error_raises_runtime_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://zoom.us/oauth/token", code=401,
            msg="Unauthorized", hdrs=None,
            fp=__import__("io").BytesIO(b'{"error":"invalid_client"}'),
        )

        with self.assertRaises(RuntimeError) as ctx:
            zoom_meeting.get_access_token("acc", "bad-cid", "bad-secret")

        self.assertIn("401", str(ctx.exception))


class TestCreateMeeting(unittest.TestCase):
    @patch("zoom_meeting.urllib.request.urlopen")
    def test_create_meeting_success_returns_expected_fields(self, mock_urlopen):
        api_response = {
            "topic": "구매대행 실전반 3주차",
            "start_time": "2026-08-05T14:00:00Z",
            "duration": 120,
            "join_url": "https://zoom.us/j/1234567890",
            "start_url": "https://zoom.us/s/1234567890?zak=xyz",
            "id": 1234567890,
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_response).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = zoom_meeting.create_meeting(
            access_token="token123",
            user_email="bulsaja23@gmail.com",
            topic="구매대행 실전반 3주차",
            start_time="2026-08-05T14:00:00",
            duration_minutes=120,
        )

        self.assertEqual(result["topic"], "구매대행 실전반 3주차")
        self.assertEqual(result["join_url"], "https://zoom.us/j/1234567890")
        self.assertEqual(result["start_url"], "https://zoom.us/s/1234567890?zak=xyz")
        self.assertEqual(result["duration"], 120)

        sent_request = mock_urlopen.call_args[0][0]
        self.assertIn("bulsaja23%40gmail.com", sent_request.full_url)
        sent_body = json.loads(sent_request.data.decode())
        self.assertEqual(sent_body["settings"]["waiting_room"], False)
        self.assertEqual(sent_body["timezone"], "Asia/Seoul")
        self.assertEqual(sent_body["type"], 2)

    @patch("zoom_meeting.urllib.request.urlopen")
    def test_create_meeting_http_error_raises_runtime_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.zoom.us/v2/users/x/meetings", code=400,
            msg="Bad Request", hdrs=None,
            fp=__import__("io").BytesIO(b'{"message":"Invalid start_time"}'),
        )

        with self.assertRaises(RuntimeError) as ctx:
            zoom_meeting.create_meeting(
                access_token="token123",
                user_email="bulsaja23@gmail.com",
                topic="테스트",
                start_time="잘못된형식",
                duration_minutes=60,
            )

        self.assertIn("400", str(ctx.exception))


class TestMain(unittest.TestCase):
    @patch("zoom_meeting.create_meeting")
    @patch("zoom_meeting.get_access_token")
    @patch("zoom_meeting.find_env")
    def test_main_success_prints_json_to_stdout(self, mock_find_env, mock_get_token, mock_create_meeting):
        mock_find_env.return_value = Path("dummy/.env")
        with patch("zoom_meeting.load_env", return_value={
            "ZOOM_ACCOUNT_ID": "acc", "ZOOM_CLIENT_ID": "cid",
            "ZOOM_CLIENT_SECRET": "secret", "ZOOM_USER_EMAIL": "user@example.com",
        }):
            mock_get_token.return_value = "token123"
            mock_create_meeting.return_value = {
                "topic": "테스트 미팅", "start_time": "2026-08-05T14:00:00Z",
                "duration": 120, "join_url": "https://zoom.us/j/111",
                "start_url": "https://zoom.us/s/111",
            }
            test_args = ["zoom_meeting.py", "--topic", "테스트 미팅",
                          "--start", "2026-08-05T14:00:00", "--duration", "120"]
            captured = io.StringIO()
            with patch("sys.argv", test_args), patch("sys.stdout", captured):
                zoom_meeting.main()

        output = json.loads(captured.getvalue().strip())
        self.assertEqual(output["join_url"], "https://zoom.us/j/111")
        self.assertEqual(output["start_url"], "https://zoom.us/s/111")

    @patch("zoom_meeting.find_env")
    def test_main_missing_credentials_exits_with_error(self, mock_find_env):
        mock_find_env.return_value = Path("dummy/.env")
        with patch("zoom_meeting.load_env", return_value={}):
            test_args = ["zoom_meeting.py", "--topic", "테스트",
                          "--start", "2026-08-05T14:00:00", "--duration", "60"]
            captured_err = io.StringIO()
            with patch("sys.argv", test_args), patch("sys.stderr", captured_err):
                with self.assertRaises(SystemExit) as ctx:
                    zoom_meeting.main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("ZOOM_ACCOUNT_ID", captured_err.getvalue())


if __name__ == "__main__":
    unittest.main()
