import os
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class SupabaseManager:
    """Helper class to manage interactions with Supabase database."""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = url or os.getenv("SUPABASE_URL", "https://ocnpefagfqbjviurgkeb.supabase.co")
        self.key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.client = None

        if self.key and not self.key.startswith("YOUR_"):
            try:
                from supabase import create_client, Client
                self.client: Optional[Client] = create_client(self.url, self.key)
            except Exception as e:
                print(f"⚠️ Supabase client initialization warning: {e}")

    def is_configured(self) -> bool:
        return self.client is not None

    def get_app_settings(self, setting_key: str) -> Optional[Dict[str, Any]]:
        """Fetch setting by key from app_settings table."""
        if not self.is_configured():
            return None
        try:
            res = self.client.table("app_settings").select("*").eq("setting_key", setting_key).execute()
            if res.data:
                return res.data[0].get("setting_value", {})
        except Exception as e:
            print(f"⚠️ Error fetching app setting '{setting_key}': {e}")
        return None

    def update_app_settings(self, setting_key: str, setting_value: Dict[str, Any]) -> bool:
        """Update or insert app setting."""
        if not self.is_configured():
            return False
        try:
            self.client.table("app_settings").upsert({
                "setting_key": setting_key,
                "setting_value": setting_value
            }, on_conflict="setting_key").execute()
            return True
        except Exception as e:
            print(f"⚠️ Error updating app setting '{setting_key}': {e}")
            return False

    def log_activity(self, event_type: str, message: str, account_id: Optional[str] = None, details: Optional[Dict] = None) -> None:
        """Log an event into activity_logs table."""
        if not self.is_configured():
            return
        try:
            payload = {
                "event_type": event_type,
                "message": message,
                "details": details or {}
            }
            if account_id:
                payload["account_id"] = account_id
            self.client.table("activity_logs").insert(payload).execute()
        except Exception as e:
            print(f"⚠️ Error logging activity to Supabase: {e}")

    def get_pending_media(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve ready media from media_queue."""
        if not self.is_configured():
            return []
        try:
            res = self.client.table("media_queue").select("*").eq("status", "ready").limit(limit).execute()
            return res.data or []
        except Exception as e:
            print(f"⚠️ Error fetching pending media from Supabase: {e}")
            return []

    def record_posting_history(
        self,
        media_id: Optional[str],
        account_id: Optional[str],
        media_filename: str,
        status: str,
        caption: Optional[str] = None,
        instagram_media_id: Optional[str] = None,
        instagram_url: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Record post execution in posting_history table."""
        if not self.is_configured():
            return False
        try:
            payload = {
                "media_filename": media_filename,
                "status": status,
                "caption": caption,
                "instagram_media_id": instagram_media_id,
                "instagram_url": instagram_url,
                "error_message": error_message
            }
            if media_id:
                payload["media_id"] = media_id
            if account_id:
                payload["account_id"] = account_id
            self.client.table("posting_history").insert(payload).execute()
            return True
        except Exception as e:
            print(f"⚠️ Error recording posting history to Supabase: {e}")
            return False

_supabase_manager: Optional[SupabaseManager] = None

def get_supabase_manager() -> SupabaseManager:
    global _supabase_manager
    if _supabase_manager is None:
        _supabase_manager = SupabaseManager()
    return _supabase_manager
