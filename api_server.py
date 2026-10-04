import os
import sys
import json
import re
import shutil
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
        if parsed.path in ["/api/status", "/health", "/api/health"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            response = {"status": "online", "worker": "active", "service": "InstaBot Remote Worker", "message": "InstaBot Backend API Service is active"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
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
  <h2>🤖 InstaBot Automation API & Worker Documentation</h2>
  <p>Status: <span style="color:#10b981;">ONLINE (Worker Active)</span></p>
  <h3>Available Endpoints:</h3>
  <ul>
    <li><code>GET /health</code> - Service Health Check</li>
    <li><code>GET /api/status</code> - Service Status JSON</li>
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

    def _serve_file(self, file_path: Path, content_type: str = None):
        if content_type is None:
            ext = file_path.suffix.lower()
            if ext == ".html": content_type = "text/html"
            elif ext == ".js": content_type = "application/javascript"
            elif ext == ".css": content_type = "text/css"
            elif ext == ".json": content_type = "application/json"
            elif ext == ".png": content_type = "image/png"
            elif ext == ".jpg" or ext == ".jpeg": content_type = "image/jpeg"
            elif ext == ".svg": content_type = "image/svg+xml"
            else: content_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip('/')
        if clean_path in ["/api/process-url", "/api/repost", "/process-url", "/repost"]:
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length).decode("utf-8")
            
            try:
                data = json.loads(post_body) if post_body else {}
            except Exception:
                data = {}

            url = data.get("url", "").strip()
            account = data.get("account", "gautammmmm20").strip().replace("@", "")
            repost_mode = data.get("repost_mode", "as_is")
            custom_caption = data.get("custom_caption", "").strip()

            if not url:
                self._send_json_response({"success": False, "error": "No URL provided"}, status_code=400)
                return

            print(f"\n[*] API Request Received: Repost URL '{url}' to account '@{account}' (mode: {repost_mode})")
            
            result = process_and_publish_instagram_post(url, account, repost_mode, custom_caption)
            
            if result.get("success"):
                self._send_json_response(result, status_code=200)
            else:
                self._send_json_response(result, status_code=500)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def process_and_publish_instagram_post(url: str, username: str, repost_mode: str = "as_is", custom_caption: str = "") -> dict:
    """
    Downloads media from target Instagram URL (Photo, Video/Reel, Carousel 1..N)
    and publishes it to the specified Instagram account using instagrapi.
    """
    try:
        from instagrapi import Client
        import account_manager
        import downloader

        # 1. Get authenticated Instagram client
        cl = account_manager.get_instagram_client(username)
        if not cl:
            return {
                "success": False,
                "error": f"Session not found or invalid for @{username}. Please log in via Add Account or check session file sessions/{username}.json."
            }

        # 2. Extract media PK and media info
        try:
            media_pk = cl.media_pk_from_url(url)
            media_info = cl.media_info(media_pk)
        except Exception as e:
            # Fallback for private or restricted posts via downloader
            media_pk = None
            media_info = None
            print(f"[*] instagrapi media info warning: {e}. Attempting fallback download...")

        media_type = "Reel"
        original_caption = ""
        if media_info:
            original_caption = media_info.caption_text or ""
            if media_info.media_type == 1:
                media_type = "Single Photo"
            elif media_info.media_type == 2:
                media_type = "Reel"
            elif media_info.media_type == 8:
                media_type = "Carousel (1..N)"

        # Prepare final caption
        if custom_caption:
            final_caption = custom_caption
        elif repost_mode == "ai_caption":
            final_caption = f"{original_caption}\n\n✨ Viral Poetry & Romantic Quotes #reels #poetry #viral"
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
                return {"success": False, "error": "Failed to download Carousel album slides."}

            paths_list = [Path(p) for p in downloaded_paths if os.path.exists(p)]
            print(f"[*] Publishing Carousel album ({len(paths_list)} slides) to @{username}...")
            published_media = cl.album_upload(paths=paths_list, caption=final_caption)
            media_code = published_media.code if published_media else str(media_pk)
            posted_url = f"https://www.instagram.com/p/{media_code}/"

        elif media_info and media_info.media_type == 1:
            # SINGLE PHOTO
            print(f"[*] Downloading Photo (PK: {media_pk})...")
            photo_path = cl.photo_download(media_pk, folder=downloads_dir)
            print(f"[*] Publishing Photo to @{username}...")
            published_media = cl.photo_upload(path=Path(photo_path), caption=final_caption)
            media_code = published_media.code if published_media else str(media_pk)
            posted_url = f"https://www.instagram.com/p/{media_code}/"

        else:
            # REEL VIDEO
            print(f"[*] Downloading Reel video from {url} using authenticated session...")
            video_file = None

            if media_pk:
                try:
                    video_file = str(cl.clip_download(media_pk, folder=downloads_dir))
                except Exception as ex:
                    print(f"[*] clip_download notice: {ex}")

            if not video_file or not os.path.exists(video_file):
                try:
                    video_file = str(cl.clip_download_by_url(url, folder=downloads_dir))
                except Exception as ex:
                    print(f"[*] clip_download_by_url notice: {ex}")

            if not video_file or not os.path.exists(video_file):
                video_file = downloader.download_reel(url)

            if not video_file or not os.path.exists(video_file):
                return {"success": False, "error": "Failed to download Reel video file."}

            print(f"[*] Publishing Reel to @{username}...")
            published_media = cl.clip_upload(path=Path(video_file), caption=final_caption)
            media_code = published_media.code if published_media else "reel"
            posted_url = f"https://www.instagram.com/reel/{media_code}/"

        # 4. Save to Supabase DB & Activity Logs
        if sm.is_configured():
            sm.record_posting_history(
                media_id=str(published_media.pk) if published_media else f"pk_{media_pk}",
                account_id=username,
                media_filename=url,
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
        print(f"[!] Real Instagram Repost Error: {error_msg}")
        
        if "login_required" in error_msg.lower() or "403" in error_msg:
            user_friendly_error = f"Instagram session expired for @{username}. Please click '+ Add Account' in InstaBot to re-authenticate."
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
                    account = item.get("account_username", "gautammmmm20").strip()
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
