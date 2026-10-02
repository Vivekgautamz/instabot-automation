import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

DEFAULT_API_VERSION = "v20.0"
GRAPH_API_BASE = "https://graph.facebook.com"
SESSION_FILE = Path(__file__).resolve().parent / "session.json"


class DirectInstagramClient:
    """Client for posting directly to Instagram using account credentials (instagrapi)."""

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.username = username or os.getenv("IG_USERNAME")
        self.password = password or os.getenv("IG_PASSWORD")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from instagrapi import Client
        except ImportError:
            raise ImportError(
                "The 'instagrapi' package is required for direct posting.\n"
                "Install it using: pip install instagrapi"
            )

        cl = Client()
        cl.delay_range = [2, 5]

        session_id = os.getenv("IG_SESSION_ID", "").strip()
        if session_id:
            try:
                cl.login_by_sessionid(session_id)
                cl.dump_settings(str(SESSION_FILE))
                self._client = cl
                return cl
            except Exception:
                pass

        def custom_challenge_code_handler(username, choice):
            code = os.getenv("IG_2FA_CODE", "").strip()
            if code:
                return code
            try:
                return input(f"\n🔐 Enter Instagram verification code sent to phone/email for @{username} (Choice {choice}): ").strip()
            except Exception:
                return ""

        cl.challenge_code_handler = custom_challenge_code_handler


        # 1. Try to reuse existing authenticated session from session.json
        if SESSION_FILE.exists():
            try:
                cl.load_settings(str(SESSION_FILE))
                # Validate session is active without forcing a full login
                cl.account_info()
                self._client = cl
                return cl
            except Exception:
                # Session might need refresh; attempt login with credentials
                try:
                    cl.login(self.username, self.password)
                    cl.dump_settings(str(SESSION_FILE))
                    self._client = cl
                    return cl
                except Exception:
                    pass

        # 2. Fresh login if no session or session expired
        if not self.username or not self.password or "your_instagram_password" in self.password:
            raise ValueError(
                "Please configure IG_USERNAME and IG_PASSWORD in your .env file."
            )

        verification_code = os.getenv("IG_2FA_CODE", "").strip() or None
        if verification_code:
            cl.login(self.username, self.password, verification_code=verification_code)
        else:
            cl.login(self.username, self.password)

        cl.dump_settings(str(SESSION_FILE))
        self._client = cl
        return cl


    def validate_credentials(self) -> Tuple[bool, str]:
        """Verify username & password and connection to Instagram."""
        if not self.username:
            return False, "Missing IG_USERNAME in .env."
        if not self.password or "your_instagram_password" in self.password:
            return False, f"Missing IG_PASSWORD for @{self.username} in .env."

        try:
            cl = self._get_client()
            user_info = cl.account_info()
            return True, f"Logged in as @{user_info.username} ({user_info.full_name or 'Direct Account'})"
        except Exception as e:
            return False, f"Instagram login failed for @{self.username}: {e}"

    def post_local_photo(self, image_path: str, caption: str) -> str:
        """Upload a local image file directly to Instagram."""
        cl = self._get_client()
        media = cl.photo_upload(path=Path(image_path), caption=caption)
        try:
            cl.dump_settings(str(SESSION_FILE))
        except Exception:
            pass
        return str(media.pk)


class MetaGraphInstagramClient:
    """Client for official Meta Instagram Graph API publishing (requires public URL)."""

    def __init__(
        self,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: str = DEFAULT_API_VERSION,
    ):
        self.user_id = user_id or os.getenv("IG_USER_ID")
        self.access_token = access_token or os.getenv("IG_ACCESS_TOKEN")
        self.api_version = api_version
        self.base_url = f"{GRAPH_API_BASE}/{self.api_version}"

    def validate_credentials(self) -> Tuple[bool, str]:
        if not self.user_id or not self.access_token:
            return False, "Missing IG_USER_ID or IG_ACCESS_TOKEN in .env"

        endpoint = f"{self.base_url}/{self.user_id}"
        params = {"fields": "id,username,name", "access_token": self.access_token}
        try:
            res = requests.get(endpoint, params=params, timeout=10)
            if res.status_code == 200:
                username = res.json().get("username", "Unknown")
                return True, f"Connected to Meta Graph API: @{username} (ID: {self.user_id})"
            return False, f"Meta API error: {res.text}"
        except Exception as e:
            return False, f"Meta API connection error: {e}"

    def post_photo(self, image_url: str, caption: str) -> str:
        endpoint = f"{self.base_url}/{self.user_id}/media"
        res = requests.post(
            endpoint,
            data={"image_url": image_url, "caption": caption, "access_token": self.access_token},
            timeout=30,
        )
        if res.status_code != 200:
            raise RuntimeError(f"Failed to create media container: {res.text}")
        creation_id = res.json().get("id")

        time.sleep(3)
        publish_endpoint = f"{self.base_url}/{self.user_id}/media_publish"
        pub_res = requests.post(
            publish_endpoint,
            data={"creation_id": creation_id, "access_token": self.access_token},
            timeout=30,
        )
        if pub_res.status_code != 200:
            raise RuntimeError(f"Failed to publish media: {pub_res.text}")
        return pub_res.json().get("id")


_active_client = None


def get_instagram_client():
    """Factory returning DirectInstagramClient (default) or MetaGraphInstagramClient."""
    global _active_client
    ig_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if ig_token and not ig_token.startswith("your_"):
        return MetaGraphInstagramClient()
    if _active_client is None:
        _active_client = DirectInstagramClient()
    return _active_client
