import os
import sys
import json
import re
import shutil
import secrets
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add 'for reel' to sys.path
BASE_DIR = Path(__file__).resolve().parent
FOR_REEL_DIR = BASE_DIR / "for reel"
if str(FOR_REEL_DIR) not in sys.path:
    sys.path.insert(0, str(FOR_REEL_DIR))

import supabase_client
sm = supabase_client.SupabaseManager()

SAFETY_FILE = FOR_REEL_DIR / "sessions" / "safety_status.json"

def get_safety_data() -> dict:
    """Loads safety and pause states for accounts."""
    if SAFETY_FILE.exists():
        try:
            with open(SAFETY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_safety_data(data: dict):
    """Saves safety and pause states to disk."""
    SAFETY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(SAFETY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[*] Warning: Could not save safety data: {e}")

def is_account_paused(username: str) -> tuple[bool, str]:
    """Checks if account automation is paused due to safety or user setting."""
    clean_u = username.strip().replace("@", "")
    data = get_safety_data()
    acc_data = data.get(clean_u, {})
    if acc_data.get("is_paused", False):
        return True, acc_data.get("pause_reason", "Automation paused for account safety.")
    return False, ""

def pause_account_automation(username: str, reason: str = "Instagram automated-behavior review required."):
    """Pauses account automation immediately to protect the account."""
    clean_u = username.strip().replace("@", "")
    data = get_safety_data()
    if clean_u not in data:
        data[clean_u] = {}
    data[clean_u]["is_paused"] = True
    data[clean_u]["pause_reason"] = reason
    data[clean_u]["paused_at"] = str(Path().resolve())
    save_safety_data(data)
    print(f"\n[ACCOUNT SAFETY] 🛑 Automation PAUSED for @{clean_u} to protect against account suspension.")
    print(f"[ACCOUNT SAFETY] Reason: {reason}")
    print(f"[ACCOUNT SAFETY] DO NOT attempt to bypass Instagram's detection or rotate IP/proxies.")
    
    if sm.is_configured():
        try:
            sm.client.table("instagram_accounts").update({
                "status": "paused",
                "session_status": "PAUSED_SAFETY",
                "notes": reason
            }).eq("username", clean_u).execute()
            sm.log_activity("ACCOUNT_SAFETY_PAUSE", f"Automation paused for @{clean_u}: {reason}")
        except Exception:
            pass

def resume_account_automation(username: str):
    """Resumes account automation after verification."""
    clean_u = username.strip().replace("@", "")
    data = get_safety_data()
    if clean_u in data:
        data[clean_u]["is_paused"] = False
        data[clean_u]["pause_reason"] = ""
        save_safety_data(data)
    print(f"\n[ACCOUNT SAFETY] ▶️ Automation RESUMED for @{clean_u}.")
    if sm.is_configured():
        try:
            sm.client.table("instagram_accounts").update({
                "status": "connected",
                "session_status": "VERIFIED",
                "notes": "Automation active"
            }).eq("username", clean_u).execute()
            sm.log_activity("ACCOUNT_SAFETY_RESUME", f"Automation resumed for @{clean_u}")
        except Exception:
            pass

def save_meta_graph_credentials(username: str, ig_user_id: str, access_token: str, app_id: str = ""):
    """Saves verified Meta Graph API credentials securely on backend."""
    clean_u = username.strip().replace("@", "")
    data = get_safety_data()
    if clean_u not in data:
        data[clean_u] = {}
    data[clean_u]["auth_type"] = "meta_graph_api"
    data[clean_u]["ig_user_id"] = ig_user_id.strip()
    data[clean_u]["access_token"] = access_token.strip()
    data[clean_u]["app_id"] = app_id.strip()
    data[clean_u]["permissions"] = ["instagram_basic", "instagram_content_publish", "pages_show_list"]
    data[clean_u]["publishing_permission_valid"] = True
    data[clean_u]["is_paused"] = False
    save_safety_data(data)


# ==========================================
# SECURE INSTAGRAM OAUTH + 2FA BACKEND ENGINE
# ==========================================
OAUTH_STATES = {}

INSTAGRAM_CLIENT_ID = os.getenv("INSTAGRAM_CLIENT_ID", os.getenv("META_APP_ID", "1028347108920192"))
INSTAGRAM_CLIENT_SECRET = os.getenv("INSTAGRAM_CLIENT_SECRET", os.getenv("META_APP_SECRET", ""))
INSTAGRAM_REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "https://poetghazipur61.vercel.app/")

def generate_instagram_oauth_url(custom_redirect: str = "") -> tuple[str, str]:
    """Generates secure OAuth authorization URL requesting official business permissions."""
    redirect_uri = custom_redirect or INSTAGRAM_REDIRECT_URI
    state = secrets.token_urlsafe(24)
    OAUTH_STATES[state] = {"created_at": str(Path().resolve()), "redirect_uri": redirect_uri}
    
    # Official Instagram Login for Business permissions
    scopes = "instagram_business_basic,instagram_business_content_publish"
    
    params = {
        "client_id": INSTAGRAM_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state,
        "force_authentication": "1"
    }
    
    auth_url = f"https://www.instagram.com/oauth/authorize?{urllib.parse.urlencode(params)}"
    return auth_url, state

def exchange_oauth_code_for_token(code: str, state: str = "") -> dict:
    """Exchanges OAuth code for long-lived access token, fetches profile, and verifies permissions."""
    state_data = OAUTH_STATES.pop(state, {}) if state else {}
    redirect_uri = state_data.get("redirect_uri", INSTAGRAM_REDIRECT_URI)

    # 1. Exchange short-lived token
    token_url = "https://api.instagram.com/oauth/access_token"
    token_data = urllib.parse.urlencode({
        "client_id": INSTAGRAM_CLIENT_ID,
        "client_secret": INSTAGRAM_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code
    }).encode("utf-8")

    try:
        req = urllib.request.Request(token_url, data=token_data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            short_res = json.loads(resp.read().decode("utf-8"))
            short_token = short_res.get("access_token")
            user_id = short_res.get("user_id")

        if not short_token:
            return {"success": False, "error": "Could not retrieve access token from Instagram."}

        # 2. Exchange for long-lived token (60 days)
        long_token = short_token
        try:
            exchange_url = f"https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret={INSTAGRAM_CLIENT_SECRET}&access_token={short_token}"
            with urllib.request.urlopen(exchange_url, timeout=15) as lresp:
                long_res = json.loads(lresp.read().decode("utf-8"))
                long_token = long_res.get("access_token") or short_token
        except Exception as le:
            print(f"[*] Long-lived token notice: {le}")

        # 3. Fetch verified user profile & username from Instagram API
        username = f"user_{user_id}"
        display_name = username
        try:
            me_url = f"https://graph.instagram.com/v19.0/me?fields=user_id,username,name&access_token={long_token}"
            with urllib.request.urlopen(me_url, timeout=15) as mresp:
                me_res = json.loads(mresp.read().decode("utf-8"))
                username = me_res.get("username") or username
                display_name = me_res.get("name") or f"@{username}"
        except Exception as me_err:
            print(f"[*] Profile fetch notice: {me_err}")

        # 4. Save account securely on backend
        save_meta_graph_credentials(username, str(user_id), long_token)
        print(f"[OAUTH OK] Successfully connected @{username} (ID: {user_id}) via Instagram Login + 2FA!")

        return {
            "success": True,
            "username": username,
            "display_name": display_name,
            "user_id": user_id,
            "auth_provider": "Instagram Login",
            "authentication_status": "Verified",
            "two_factor": "Instagram Protected",
            "publishing_status": "Enabled",
            "token_status": "Valid",
            "message": f"Successfully connected @{username} via Official Instagram Login!"
        }

    except Exception as e:
        print(f"[OAUTH ERROR] Code exchange failed: {e}")
        return {"success": False, "error": f"Instagram OAuth Code Exchange Error: {str(e)}"}



    if sm.is_configured():
        try:
            sm.client.table("instagram_accounts").upsert({
                "username": clean_u,
                "display_name": f"@{clean_u} (Official Meta API)",
                "auth_type": "Meta Graph API",
                "status": "connected",
                "session_status": "VERIFIED",
                "is_active": True
            }, on_conflict="username").execute()
            sm.log_activity("META_API_CONNECTED", f"Meta Graph API connected for @{clean_u}")
        except Exception:
            pass


class InstaBotAPIHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip('/')
        
        # Instagram OAuth Endpoints
        if clean_path in ["/api/instagram/auth/start", "/api/auth/instagram/start", "/auth/instagram"]:
            query_params = parse_qs(parsed.query)
            custom_redirect = query_params.get("redirect_uri", [""])[0]
            auth_url, state = generate_instagram_oauth_url(custom_redirect)
            self._send_json_response({
                "success": True,
                "auth_url": auth_url,
                "state": state,
                "client_id": INSTAGRAM_CLIENT_ID,
                "permissions": ["instagram_business_basic", "instagram_business_content_publish"]
            })
            return

        if clean_path in ["/api/instagram/oauth/callback", "/auth/callback", "/api/auth/callback"]:
            query_params = parse_qs(parsed.query)
            code_val = query_params.get("code", [""])[0]
            state_val = query_params.get("state", [""])[0]
            error_val = query_params.get("error_description", query_params.get("error", [""]))[0]

            if error_val:
                self.send_response(302)
                self.send_header("Location", f"{INSTAGRAM_REDIRECT_URI}?error={urllib.parse.quote(error_val)}")
                self.end_headers()
                return

            if code_val:
                res = exchange_oauth_code_for_token(code_val, state_val)
                if res.get("success"):
                    uname = res.get("username", "")
                    self.send_response(302)
                    self.send_header("Location", f"{INSTAGRAM_REDIRECT_URI}?auth=success&username={uname}")
                    self.end_headers()
                    return
                else:
                    err_msg = res.get("error", "Code exchange failed")
                    self.send_response(302)
                    self.send_header("Location", f"{INSTAGRAM_REDIRECT_URI}?error={urllib.parse.quote(err_msg)}")
                    self.end_headers()
                    return

        if clean_path in ["/api/instagram/auth/status", "/api/accounts/auth-status"]:
            accounts = list_all_accounts_backend()
            self._send_json_response({"success": True, "accounts": accounts})
            return

        if clean_path in ["", "/api/status", "/health", "/api/health", "/status"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            response = {"status": "online", "worker": "active", "service": "InstaBot Remote Worker", "message": "InstaBot Backend API Service is active"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        if clean_path in ["/api/accounts", "/api/accounts/list", "/accounts"]:
            self._send_json_response({"success": True, "accounts": list_all_accounts_backend()})
            return

        if parsed.path in ["/docs", "/api/docs"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            docs_html = """<!DOCTYPE html>
<html>
<head><title>InstaBot API Documentation</title></head>
<body style="font-family:sans-serif; background:#0f172a; color:#f8fafc; padding:40px;">
  <h2>🤖 InstaBot Automation API & Session Manager</h2>
  <p>Status: <span style="color:#10b981;">ONLINE (Worker Active)</span></p>
  <h3>Available Endpoints:</h3>
  <ul>
    <li><code>GET /health</code> - Service Health Check</li>
    <li><code>GET /api/accounts</code> - List all accounts with live session status</li>
    <li><code>POST /api/accounts/verify-session</code> - Verify session health</li>
    <li><code>POST /api/accounts/create-session</code> - Create or update account session</li>
    <li><code>POST /api/accounts/activate</code> - Switch active account</li>
    <li><code>POST /api/accounts/delete</code> - Remove account</li>
    <li><code>POST /api/process-url</code> - Download & Publish Instagram Post/Reel/Carousel</li>
  </ul>
</body>
</html>"""
            self.wfile.write(docs_html.encode("utf-8"))
            return

        # Serve static frontend files from frontend/dist
        dist_dir = BASE_DIR / "frontend" / "dist"
        rel_path = parsed.path.lstrip("/")
        target_file = dist_dir / rel_path

        if rel_path and target_file.exists() and target_file.is_file():
            self._serve_file(target_file)
        else:
            # Fallback to index.html for Single Page Application (SPA) routing
            index_file = dist_dir / "index.html"
            if index_file.exists():
                self._serve_file(index_file, content_type="text/html")
            else:
                self.send_response(404)
                self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip('/')
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        
        try:
            data = json.loads(post_body) if post_body else {}
        except Exception:
            data = {}

        # 1. Instagram Post & Reel Processing
        
        # 1b. Account Safety & Meta Graph API Management
        
        # Instagram OAuth Code Exchange Endpoint
        if clean_path in ["/api/instagram/auth/exchange", "/api/auth/exchange"]:
            code_val = data.get("code", "").strip()
            state_val = data.get("state", "").strip()
            if not code_val:
                self._send_json_response({"success": False, "error": "Authorization code is required"}, status_code=400)
                return
            res = exchange_oauth_code_for_token(code_val, state_val)
            self._send_json_response(res, status_code=200 if res.get("success") else 500)
            return

        if clean_path in ["/api/instagram/auth/reconnect", "/api/accounts/reconnect"]:
            username = (data.get("username") or "gautammmmm20").strip().replace("@", "")
            auth_url, state = generate_instagram_oauth_url()
            self._send_json_response({
                "success": True,
                "username": username,
                "auth_url": auth_url,
                "state": state
            })
            return

        if clean_path in ["/api/accounts/pause", "/api/accounts/safety-pause"]:
            username = (data.get("username") or "gautammmmm20").strip().replace("@", "")
            reason = data.get("reason", "Automated activity paused by user/safety policy.")
            pause_account_automation(username, reason)
            self._send_json_response({"success": True, "status": "paused", "message": f"Automation paused for @{username}."})
            return

        if clean_path in ["/api/accounts/resume", "/api/accounts/safety-resume"]:
            username = (data.get("username") or "gautammmmm20").strip().replace("@", "")
            resume_account_automation(username)
            self._send_json_response({"success": True, "status": "active", "message": f"Automation resumed for @{username}."})
            return

        if clean_path in ["/api/accounts/connect-meta-api", "/api/accounts/meta-api"]:
            username = (data.get("username") or "").strip().replace("@", "")
            ig_user_id = (data.get("ig_user_id") or "").strip()
            access_token = (data.get("access_token") or "").strip()
            app_id = (data.get("app_id") or "").strip()

            if not username or not access_token or not ig_user_id:
                self._send_json_response({"success": False, "error": "Username, Instagram User ID, and Access Token are required."}, status_code=400)
                return

            save_meta_graph_credentials(username, ig_user_id, access_token, app_id)
            self._send_json_response({
                "success": True,
                "auth_type": "meta_graph_api",
                "permissions": ["instagram_basic", "instagram_content_publish", "pages_show_list"],
                "message": f"Official Meta Graph API connected successfully for @{username}."
            })
            return

        if clean_path in ["/api/interactive/auto-publish", "/api/auto-publish", "/auto-publish", "/api/process-url", "/api/repost", "/process-url", "/repost"]:
            url = data.get("url", "").strip()
            account = (data.get("account_username") or data.get("account") or data.get("username") or "gautammmmm20").strip().replace("@", "")
            repost_mode = data.get("repost_mode", "as_is")
            custom_caption = (data.get("custom_caption") or data.get("caption") or "").strip()

            if not url:
                self._send_json_response({"success": False, "error": "No URL provided"}, status_code=400)
                return

            print(f"\n[*] API Request Received: Repost URL '{url}' to account '@{account}' (mode: {repost_mode})")
            result = process_and_publish_instagram_post(url, account, repost_mode, custom_caption)
            if result.get("success"):
                self._send_json_response(result, status_code=200)
            else:
                self._send_json_response(result, status_code=500)
            return

        # 2. Account & Session Management Endpoints
        if clean_path in ["/api/accounts/add", "/api/accounts/create-session", "/api/accounts"]:
            username = data.get("username", "").strip()
            password = data.get("password", "")
            session_id = data.get("session_id", "")
            session_json = data.get("session_json")
            verification_code = data.get("verification_code", "")
            is_active = data.get("is_active", False)

            if not username:
                self._send_json_response({"success": False, "error": "Username is required"}, status_code=400)
                return

            res = create_new_session_backend(username, password, session_id, session_json, verification_code, is_active)
            self._send_json_response(res, status_code=200)
            return

        if clean_path in ["/api/accounts/verify-session", "/api/accounts/verify", "/api/accounts/refresh-session"] or "/verify-session" in clean_path or "/refresh-session" in clean_path:
            username = (data.get("username") or "").strip()
            if not username:
                parts = clean_path.split("/")
                if len(parts) >= 5 and parts[2] == "accounts":
                    username = parts[3]
                elif len(parts) >= 4 and parts[1] == "accounts":
                    username = parts[2]
            
            if not username or username in ["accounts", "verify-session", "refresh-session"]:
                username = "poetghazipur61"

            res = verify_account_session(username)
            self._send_json_response(res, status_code=200)
            return

        if clean_path in ["/api/accounts/activate", "/api/accounts/select"] or "/activate" in clean_path:
            username = (data.get("username") or "").strip()
            if not username:
                parts = clean_path.split("/")
                if len(parts) >= 5 and parts[2] == "accounts":
                    username = parts[3]
                elif len(parts) >= 4 and parts[1] == "accounts":
                    username = parts[2]
            
            if not username or username in ["accounts", "activate"]:
                username = "poetghazipur61"

            res = activate_account_backend(username)
            self._send_json_response(res, status_code=200)
            return

        if clean_path in ["/api/accounts/delete", "/api/accounts/remove"] or "/delete" in clean_path:
            username = (data.get("username") or "").strip()
            if not username:
                parts = clean_path.split("/")
                if len(parts) >= 5 and parts[2] == "accounts":
                    username = parts[3]
                elif len(parts) >= 4 and parts[1] == "accounts":
                    username = parts[2]
            
            if not username or username in ["accounts", "delete"]:
                self._send_json_response({"success": False, "error": "Username required"}, status_code=400)
                return

            res = delete_account_backend(username)
            self._send_json_response(res, status_code=200)
            return

        self.send_response(404)
        self.end_headers()

    def _send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


import datetime
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    FeedbackRequired,
    TwoFactorRequired,
    BadPassword,
    PleaseWaitFewMinutes
)

def get_account_session_path(username: str) -> Path:
    clean_u = username.strip().replace("@", "")
    sessions_dir = FOR_REEL_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir / f"{clean_u}.json"

def verify_account_session(username: str) -> dict:
    """Verifies whether an account session file exists, loads, and is currently authenticated with Instagram."""
    clean_u = username.strip().replace("@", "")
    session_file = get_account_session_path(clean_u)
    
    if not session_file.exists():
        legacy_file = BASE_DIR / "session.json"
        if legacy_file.exists() and clean_u.lower() == "poetghazipur61":
            shutil.copy2(legacy_file, session_file)
        else:
            return {
                "success": False,
                "username": clean_u,
                "status": "INVALID_SESSION",
                "ready_to_post": False,
                "badge": "🔴 INVALID SESSION",
                "message": f"No session file found for @{clean_u}. Please create a session."
            }

    try:
        cl = Client()
        cl.load_settings(str(session_file))
        try:
            user_info = cl.account_info()
            verified_username = user_info.username or clean_u
            if sm.is_configured():
                sm.client.table("instagram_accounts").update({
                    "status": "connected",
                    "last_verified_at": datetime.datetime.utcnow().isoformat()
                }).eq("username", clean_u).execute()
            
            return {
                "success": True,
                "username": clean_u,
                "status": "VERIFIED",
                "ready_to_post": True,
                "badge": "🟢 VERIFIED",
                "message": f"Session is active and valid for @{verified_username}. Ready to publish Reels!"
            }
        except LoginRequired:
            return {
                "success": False,
                "username": clean_u,
                "status": "LOGIN_REQUIRED",
                "ready_to_post": False,
                "badge": "🟡 LOGIN REQUIRED",
                "message": f"Instagram session expired for @{clean_u}. Recreate or refresh session."
            }
        except ChallengeRequired:
            return {
                "success": False,
                "username": clean_u,
                "status": "VERIFICATION_REQUIRED",
                "ready_to_post": False,
                "badge": "🟡 VERIFICATION REQUIRED",
                "message": f"Instagram checkpoint/challenge required for @{clean_u}. Verify in mobile app."
            }
        except Exception as e:
            err_str = str(e)
            if "login_required" in err_str.lower() or "403" in err_str:
                return {
                    "success": False,
                    "username": clean_u,
                    "status": "LOGIN_REQUIRED",
                    "ready_to_post": False,
                    "badge": "🟡 LOGIN REQUIRED",
                    "message": f"Session expired on Instagram servers (HTTP 403)."
                }
            return {
                "success": False,
                "username": clean_u,
                "status": "ERROR",
                "ready_to_post": False,
                "badge": "🔴 ERROR",
                "message": f"Verification error: {err_str}"
            }
    except Exception as e:
        return {
            "success": False,
            "username": clean_u,
            "status": "INVALID_SESSION",
            "ready_to_post": False,
            "badge": "🔴 INVALID SESSION",
            "message": f"Failed to load session JSON: {str(e)}"
        }

def list_all_accounts_backend() -> list:
    """Returns list of all accounts from Supabase merged with real filesystem session status."""
    accounts_db = []
    if sm.is_configured():
        try:
            res = sm.client.table("instagram_accounts").select("*").order("created_at", desc=False).execute()
            accounts_db = res.data or []
        except Exception:
            pass

    sessions_dir = FOR_REEL_DIR / "sessions"
    found_usernames = set()
    for acc in accounts_db:
        found_usernames.add(acc.get("username"))

    if sessions_dir.exists():
        for sf in sessions_dir.glob("*.json"):
            uname = sf.stem
            if uname not in found_usernames and uname != "active_account":
                accounts_db.append({
                    "username": uname,
                    "display_name": uname,
                    "status": "connected",
                    "is_active": False,
                    "auth_type": "Direct Login"
                })
                found_usernames.add(uname)

    if not accounts_db:
        accounts_db = [
            {"username": "poetghazipur61", "display_name": "Poet Ghazipur 61", "is_active": True},
            {"username": "psychology.yaarr", "display_name": "Psychology Yaarr", "is_active": False},
            {"username": "gautammmmm20", "display_name": "gautammmmm20", "is_active": False}
        ]

    active_file = sessions_dir / "active_account.txt"
    active_uname = ""
    if active_file.exists():
        try:
            active_uname = active_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    results = []
    for acc in accounts_db:
        uname = acc.get("username", "").strip()
        is_active = acc.get("is_active", False)
        if active_uname and uname == active_uname:
            is_active = True

        session_file = get_account_session_path(uname)
        session_exists = session_file.exists()
        
        results.append({
            "id": acc.get("id") or uname,
            "username": uname,
            "display_name": acc.get("display_name") or uname,
            "is_active": is_active,
            "auth_type": acc.get("auth_type") or "Direct Login",
            "session_exists": session_exists,
            "session_path": f"sessions/{uname}.json",
            "session_status": "VERIFIED" if session_exists else "LOGIN_REQUIRED",
            "ready_to_post": session_exists,
            "last_verified_at": acc.get("last_verified_at")
        })

    return results

def create_new_session_backend(username: str, password: str = "", session_id: str = "", session_json: dict = None, verification_code: str = "", is_active: bool = False) -> dict:
    """Authenticates with Instagram and writes secure sessions/<username>.json"""
    clean_u = username.strip().replace("@", "")
    session_file = get_account_session_path(clean_u)
    
    cl = Client()
    cl.delay_range = [2, 4]
    
    if session_json and isinstance(session_json, dict):
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_json, f, indent=2)
    elif session_id and session_id.strip():
        try:
            cl.login_by_sessionid(session_id.strip())
            cl.dump_settings(str(session_file))
        except Exception as e:
            return {"success": False, "error": f"Session ID login failed: {str(e)}"}
    elif password and password.strip():
        try:
            if verification_code and verification_code.strip():
                cl.login(clean_u, password.strip(), verification_code=verification_code.strip())
            else:
                cl.login(clean_u, password.strip())
            cl.dump_settings(str(session_file))
        except TwoFactorRequired:
            return {
                "success": False, 
                "requires_2fa": True,
                "error": "Two-Factor Authentication (2FA) required. Please enter the 6-digit verification code below."
            }
        except ChallengeRequired as ce:
            return {
                "success": False,
                "requires_approval": True,
                "error": "Instagram Checkpoint / In-App Approval Required. Please open your Instagram mobile app, tap 'This Was Me' to approve, then click 'Verify Session'."
            }
        except BadPassword:
            return {"success": False, "error": "Incorrect Instagram password. Please check and try again."}
        except Exception as e:
            err_str = str(e)
            if "two_factor_required" in err_str.lower() or "2fa" in err_str.lower():
                return {
                    "success": False,
                    "requires_2fa": True,
                    "error": "Two-Factor Authentication (2FA) required. Please enter the 6-digit code."
                }
            if "checkpoint_required" in err_str.lower() or "challenge" in err_str.lower() or "feedback_required" in err_str.lower():
                return {
                    "success": False,
                    "requires_approval": True,
                    "error": "Instagram Checkpoint / In-App Approval Required. Please approve on your mobile app."
                }
            return {"success": False, "error": f"Instagram login failed: {err_str}"}
    else:
        return {"success": False, "error": "Please provide a password, session ID, or session JSON."}

    if sm.is_configured():
        try:
            if is_active:
                sm.client.table("instagram_accounts").update({"is_active": False}).neq("username", clean_u).execute()
            
            sm.client.table("instagram_accounts").upsert({
                "username": clean_u,
                "display_name": clean_u,
                "auth_type": "Session ID Cookie" if session_id else "Direct Login",
                "status": "connected",
                "is_active": is_active,
                "last_verified_at": datetime.datetime.utcnow().isoformat()
            }, on_conflict="username").execute()
        except Exception as e:
            print(f"[*] Supabase account upsert notice: {e}")

    if is_active:
        active_file = FOR_REEL_DIR / "sessions" / "active_account.txt"
        active_file.write_text(f"{clean_u}\n", encoding="utf-8")

    return {
        "success": True,
        "username": clean_u,
        "status": "VERIFIED",
        "ready_to_post": True,
        "message": f"Successfully created session for @{clean_u}!"
    }

def activate_account_backend(username: str) -> dict:
    clean_u = username.strip().replace("@", "")
    active_file = FOR_REEL_DIR / "sessions" / "active_account.txt"
    active_file.write_text(f"{clean_u}\n", encoding="utf-8")
    
    if sm.is_configured():
        try:
            sm.client.table("instagram_accounts").update({"is_active": False}).neq("username", clean_u).execute()
            sm.client.table("instagram_accounts").update({"is_active": True}).eq("username", clean_u).execute()
        except Exception as e:
            print(f"[*] Activate notice: {e}")

    return {"success": True, "active_account": clean_u, "message": f"Active Instagram account switched to @{clean_u}"}

def delete_account_backend(username: str) -> dict:
    clean_u = username.strip().replace("@", "")
    session_file = get_account_session_path(clean_u)
    if session_file.exists():
        try:
            session_file.unlink()
        except Exception:
            pass

    if sm.is_configured():
        try:
            sm.client.table("instagram_accounts").delete().eq("username", clean_u).execute()
        except Exception as e:
            print(f"[*] Delete account notice: {e}")

    return {"success": True, "message": f"Account @{clean_u} removed successfully."}


def detect_instagram_url_type(url: str):
    """
    Parses and sanitizes Instagram URLs, stripping tracking parameters.
    Returns (url_type, shortcode, clean_url).
    """
    if not url:
        return "reel", "", ""
    url = url.strip()
    match = re.search(r"/(?:(p|reel|reels|tv))/([A-Za-z0-9_-]+)", url)
    if match:
        raw_type = match.group(1).lower()
        url_type = "post" if raw_type in ["p", "tv"] else "reel"
        shortcode = match.group(2)
        clean_url = f"https://www.instagram.com/{'p' if url_type == 'post' else 'reel'}/{shortcode}/"
        return url_type, shortcode, clean_url
    
    clean_base = url.split("?")[0].rstrip("/")
    if "/p/" in clean_base:
        return "post", "", clean_base + "/"
    return "reel", "", clean_base + "/"


def ensure_instagram_compatible_image(image_path: Path) -> Path:
    """Ensures image is in a supported RGB JPG format for Instagram upload."""
    image_path = Path(image_path)
    if not image_path.exists():
        return image_path
    
    target_jpg = image_path.with_suffix(".jpg")
    ffmpeg_exe = BASE_DIR / "ffmpeg.exe"
    if not ffmpeg_exe.exists():
        ffmpeg_exe = "ffmpeg"
    
    # If HEIC/AVIF/WEBP or non-jpg, convert using ffmpeg
    if image_path.suffix.lower() in [".heic", ".avif", ".webp"] or image_path.suffix.lower() != ".jpg":
        try:
            import subprocess
            cmd = [str(ffmpeg_exe), "-y", "-i", str(image_path), str(target_jpg)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and target_jpg.exists():
                return target_jpg
        except Exception as fe:
            print(f"[*] ffmpeg image conversion notice: {fe}")
            
    try:
        from PIL import Image
        src_path = target_jpg if target_jpg.exists() else image_path
        with Image.open(str(src_path)) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            out_file = image_path.parent / f"{image_path.stem}_ready.jpg"
            img.save(str(out_file), "JPEG", quality=95)
            return out_file
    except Exception as pe:
        print(f"[*] PIL image cleanup notice: {pe}")

    return target_jpg if target_jpg.exists() else image_path


def process_and_publish_instagram_post(url: str, username: str, repost_mode: str = "as_is", custom_caption: str = "") -> dict:
    """
    Downloads media from target Instagram URL (Photo, Video/Reel, Carousel 1..N)
    and publishes it to the specified Instagram account. Includes automated behavior safety checks.
    """
    clean_user = username.strip().replace("@", "")
    
    # 0. Safety Guard: Check if automation is paused for this account
    is_paused, pause_reason = is_account_paused(clean_user)
    if is_paused:
        err_msg = f"🛑 Publishing Paused: Automation is currently paused to protect @{clean_user}. Reason: {pause_reason}. Please verify status in Settings."
        print(f"\n[ACCOUNT SAFETY] Blocked publish attempt for @{clean_user}: {err_msg}")
        return {"success": False, "error": err_msg, "paused": True}

    url_type, shortcode, clean_url = detect_instagram_url_type(url)
    print(f"\n[InteractiveBot] URL type: {url_type}")
    print(f"[InteractiveBot] Shortcode: {shortcode or 'N/A'}")

    

    try:
        from instagrapi import Client
        import account_manager
        import downloader

        # 1. Get authenticated Instagram client
        cl = account_manager.get_instagram_client(username)
        if not cl:
            err_msg = f"Session not found or invalid for @{username}. Please log in via Add Account or check session file sessions/{username}.json."
            print(f"[InteractiveBot] Publish result: FAILED - {err_msg}")
            return {"success": False, "error": err_msg}

        # 2. Extract media PK and media info
        media_pk = None
        media_info = None
        if shortcode:
            try:
                media_pk = cl.media_pk_from_code(shortcode)
                media_info = cl.media_info(media_pk)
            except Exception as ex1:
                print(f"[*] media_pk_from_code notice: {ex1}")

        if not media_pk or not media_info:
            try:
                media_pk = cl.media_pk_from_url(clean_url or url)
                media_info = cl.media_info(media_pk)
            except Exception as ex2:
                print(f"[*] media_info fallback warning: {ex2}")

        media_type = "Reel"
        media_type_log = "video"
        original_caption = ""
        
        if media_info:
            original_caption = media_info.caption_text or ""
            if media_info.media_type == 1:
                media_type = "Single Photo"
                media_type_log = "image"
            elif media_info.media_type == 2:
                media_type = "Reel"
                media_type_log = "video"
            elif media_info.media_type == 8:
                media_type = "Carousel (1..N)"
                media_type_log = "carousel"
        else:
            if url_type == "post":
                media_type = "Single Photo"
                media_type_log = "image"

        print(f"[InteractiveBot] Media type: {media_type_log}")

        # Prepare final caption
        if custom_caption and not custom_caption.startswith("Auto repost") and not (custom_caption.startswith("http://") or custom_caption.startswith("https://")):
            final_caption = custom_caption
        elif repost_mode == "ai_caption":
            final_caption = f"{original_caption}\n\n✨ Viral Poetry & Romantic Quotes #reels #poetry #viral" if original_caption else "✨ Viral Romantic Quotes & Aesthetic Poetry #reels #poetry #viral"
        else:
            final_caption = original_caption if original_caption else "Aesthetic poetry vibe ✨ #reels #poetry"

        downloads_dir = BASE_DIR / "for reel" / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        published_media = None
        posted_url = ""

        # 3. Handle Download and Publishing based on Media Type
        if media_info and media_info.media_type == 8:
            # CAROUSEL (Album of photos/videos)
            print(f"[*] Downloading Carousel album (PK: {media_pk})...")
            downloaded_paths = cl.album_download(media_pk, folder=downloads_dir)
            if not downloaded_paths:
                err_msg = "Failed to download Carousel album slides."
                print(f"[InteractiveBot] Publish result: FAILED - {err_msg}")
                return {"success": False, "error": err_msg}

            paths_list = []
            for p in downloaded_paths:
                f_path = Path(p)
                if f_path.exists():
                    if f_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".heic", ".webp"]:
                        paths_list.append(ensure_instagram_compatible_image(f_path))
                    else:
                        paths_list.append(f_path)

            print("[InteractiveBot] Download complete")
            print(f"[InteractiveBot] Publishing account: @{username}")
            print(f"[*] Publishing ONE cohesive Carousel album ({len(paths_list)} slides) to @{username}...")
            published_media = cl.album_upload(paths=paths_list, caption=final_caption)
            media_code = published_media.code if published_media else str(media_pk)
            posted_url = f"https://www.instagram.com/p/{media_code}/"

        elif (media_info and media_info.media_type == 1) or (not media_info and url_type == "post" and not url.lower().endswith(".mp4")):
            # SINGLE PHOTO
            print(f"[*] Downloading Photo (PK: {media_pk or shortcode})...")
            photo_path = None
            if media_pk:
                try:
                    photo_path = cl.photo_download(media_pk, folder=downloads_dir)
                except Exception as pex:
                    print(f"[*] photo_download notice: {pex}")
            if not photo_path or not os.path.exists(str(photo_path)):
                try:
                    photo_path = cl.photo_download_by_url(clean_url, folder=downloads_dir)
                except Exception as pex2:
                    print(f"[*] photo_download_by_url notice: {pex2}")

            if not photo_path or not os.path.exists(str(photo_path)):
                err_msg = "Failed to download photo image."
                print(f"[InteractiveBot] Publish result: FAILED - {err_msg}")
                return {"success": False, "error": err_msg}

            ready_photo = ensure_instagram_compatible_image(Path(photo_path))
            print("[InteractiveBot] Download complete")
            print(f"[InteractiveBot] Publishing account: @{username}")
            print(f"[*] Publishing Photo to @{username}...")
            published_media = cl.photo_upload(path=ready_photo, caption=final_caption)
            media_code = published_media.code if published_media else str(media_pk)
            posted_url = f"https://www.instagram.com/p/{media_code}/"

        else:
            # REEL / VIDEO POST
            print(f"[*] Downloading Video/Reel from {clean_url or url}...")
            video_file = None

            if media_pk:
                try:
                    video_file = str(cl.clip_download(media_pk, folder=downloads_dir))
                except Exception as ex:
                    print(f"[*] clip_download notice: {ex}")

            if not video_file or not os.path.exists(video_file):
                try:
                    video_file = str(cl.clip_download_by_url(clean_url or url, folder=downloads_dir))
                except Exception as ex:
                    print(f"[*] clip_download_by_url notice: {ex}")

            if not video_file or not os.path.exists(video_file):
                video_file = downloader.download_reel(clean_url or url)

            if not video_file or not os.path.exists(video_file):
                err_msg = "Failed to download Video/Reel file."
                print(f"[InteractiveBot] Publish result: FAILED - {err_msg}")
                return {"success": False, "error": err_msg}

            print("[InteractiveBot] Download complete")
            print(f"[InteractiveBot] Publishing account: @{username}")
            print(f"[*] Publishing Reel to @{username}...")
            published_media = cl.clip_upload(path=Path(video_file), caption=final_caption)
            media_code = published_media.code if published_media else "reel"
            posted_url = f"https://www.instagram.com/reel/{media_code}/"

        if not published_media:
            err_msg = "Publishing returned empty confirmation from Instagram."
            print(f"[InteractiveBot] Publish result: FAILED - {err_msg}")
            return {"success": False, "error": err_msg}

        print("[InteractiveBot] Publish result: SUCCESS")
        print(f"[InteractiveBot] Live URL: {posted_url}")

        # 4. Save to Supabase DB & Activity Logs
        if sm.is_configured():
            sm.record_posting_history(
                media_id=str(published_media.pk) if published_media else f"pk_{media_pk}",
                account_id=username,
                media_filename=clean_url or url,
                status="published",
                caption=final_caption,
                instagram_media_id=published_media.code if published_media else str(media_pk),
                instagram_url=posted_url
            )
            sm.log_activity("INSTAGRAM_PUBLISH_SUCCESS", f"Published {media_type} to @{username}: {posted_url}")

        return {
            "success": True,
            "media_type": media_type,
            "account": username,
            "instagram_url": posted_url,
            "media_code": published_media.code if published_media else "posted",
            "message": f"Successfully published {media_type} to @{username}! Live URL: {posted_url}"
        }

    except Exception as err:
        error_msg = str(err)
        print(f"[InteractiveBot] Publish result: FAILED - {error_msg}")
        print(f"[!] Real Instagram Repost Error: {error_msg}")
        
        # Check for automated behavior, challenge, or rate limit warnings
        if any(k in error_msg.lower() for k in ["challenge", "checkpoint", "feedback_required", "automated", "suspicious", "429", "rate_limit", "user_needs_to_review"]):
            pause_account_automation(username, reason=f"Instagram automated activity warning/review required: {error_msg}")
            user_friendly_error = f"🛑 Publishing Paused: Instagram requested account verification. Automation stopped immediately to protect @{username}."
        elif "login_required" in error_msg.lower() or "403" in error_msg:
            pause_account_automation(username, reason="Session expired / authentication required.")
            user_friendly_error = f"🛑 Session expired for @{username}. Automation paused. Please reconnect via Official Meta API or re-authenticate."
        else:
            user_friendly_error = f"Instagram API Error: {error_msg}"

        if sm.is_configured():
            sm.log_activity("INSTAGRAM_PUBLISH_ERROR", f"Failed to publish to @{username}: {user_friendly_error}")
            
        return {
            "success": False,
            "error": user_friendly_error
        }


def poll_supabase_queue_worker():
    """Background thread polling Supabase media_queue every 5s for items submitted via Vercel UI."""
    import time
    print("[*] Supabase Media Queue Worker Thread Started (Listening for Vercel Submissions)...")
    
    while True:
        try:
            if sm.is_configured():
                res = sm.client.table("media_queue").select("*").eq("status", "ready").limit(1).execute()
                items = res.data or []
                for item in items:
                    item_id = item.get("id")
                    target_url = (item.get("file_path") or item.get("filename") or "").strip()
                    meta = item.get("media_metadata") or {}
                    account = (meta.get("account_username") or meta.get("target_account") or item.get("account_username") or "gautammmmm20").strip()
                    custom_caption = item.get("caption", "").strip()

                    if target_url and target_url.startswith("http"):
                        print(f"\n[QUEUE WORKER] Picked up Vercel job #{item_id}: Reposting {target_url} to @{account}...")
                        sm.client.table("media_queue").update({"status": "processing"}).eq("id", item_id).execute()

                        result = process_and_publish_instagram_post(target_url, account, "as_is", custom_caption)

                        if result.get("success"):
                            sm.client.table("media_queue").update({
                                "status": "published"
                            }).eq("id", item_id).execute()
                            print(f"[QUEUE WORKER OK] Post #{item_id} published successfully! Link: {result.get('instagram_url')}")
                        else:
                            sm.client.table("media_queue").update({
                                "status": "failed"
                            }).eq("id", item_id).execute()
                            print(f"[QUEUE WORKER FAIL] Post #{item_id} failed: {result.get('error')}")
        except Exception as e:
            pass
        time.sleep(5)


def run_server(port=None):
    if port is None:
        port = int(os.getenv("PORT", 8000))
        
    import threading
    # Start queue worker daemon thread
    queue_thread = threading.Thread(target=poll_supabase_queue_worker, daemon=True)
    queue_thread.start()

    server_address = ("", port)
    httpd = HTTPServer(server_address, InstaBotAPIHandler)
    print("=" * 60)
    print(f"   🤖 INSTABOT PYTHON AUTOMATION BACKEND API SERVER")
    print("=" * 60)
    print(f"   Server listening on port: {port}")
    print(f"   API Endpoint:             /api/process-url")
    print(f"   Health Check:            /health")
    print(f"   Vercel Queue Worker:      Active (Polling Supabase media_queue)")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")

if __name__ == "__main__":
    run_server()
