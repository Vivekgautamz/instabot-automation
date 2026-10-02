import os
import re
from pathlib import Path
import yt_dlp
from config import DOWNLOADS_DIR

def extract_safe_reel_id(url: str, fallback_id: str = "") -> str:
    """Extract clean Instagram shortcode or return safe fallback ID."""
    match = re.search(r"/(?:reel|p)/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    if fallback_id:
        clean = re.sub(r'[^A-Za-z0-9_-]', '_', fallback_id)
        return clean[:30]
    return "reel_video"

def download_reel(reel_url: str, custom_id: str = "", browser_cookies: str = "") -> str:
    """
    Downloads the Reel video file to the downloads directory using a clean,
    sanitized filename without URL query strings or illegal characters.
    """
    clean_id = extract_safe_reel_id(reel_url, custom_id)
    download_path = Path(DOWNLOADS_DIR)
    download_path.mkdir(parents=True, exist_ok=True)

    outtmpl = str(download_path / f"{clean_id}.%(ext)s")

    ydl_opts = {
        'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
        'outtmpl': outtmpl,
        'windowsfilenames': True,
        'restrictfilenames': True,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'merge_output_format': 'mp4'
    }

    if browser_cookies:
        ydl_opts['cookiesfrombrowser'] = (browser_cookies, )

    # First attempt: direct or with cookies via yt-dlp
    download_error = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([reel_url])
    except Exception as e:
        download_error = e
        err_msg = str(e)
        if "There is no video in this post" in err_msg:
            print("[*] Detected photo post instead of video Reel. Downloading high-res image...")
            # Use instagrapi to download photo directly
            try:
                import instagrapi
                try:
                    from account_manager import get_session_path
                    session_path = get_session_path()
                except Exception:
                    session_path = os.path.abspath(os.path.join(DOWNLOADS_DIR, "..", "..", "session.json"))
                cl = instagrapi.Client()
                if os.path.exists(session_path):
                    cl.load_settings(session_path)
                pk = cl.media_pk_from_url(reel_url)
                img_path = cl.photo_download(pk, folder=download_path)
                return str(Path(img_path).resolve())
            except Exception as pe:
                raise Exception(f"This post contains only photos/images (not a video Reel). Error: {pe}")
        elif "certain audiences" in err_msg or "login" in err_msg.lower():
            if not browser_cookies:
                for b in ['chrome', 'edge', 'firefox']:
                    try:
                        print(f"[*] Trying to load session from {b} browser for restricted content...")
                        opts_with_cookie = dict(ydl_opts)
                        opts_with_cookie['cookiesfrombrowser'] = (b, )
                        with yt_dlp.YoutubeDL(opts_with_cookie) as ydl:
                            ydl.download([reel_url])
                        download_error = None
                        break
                    except Exception:
                        continue
                if download_error:
                    raise download_error
            else:
                raise download_error
        else:
            raise download_error


    expected_mp4 = download_path / f"{clean_id}.mp4"
    if expected_mp4.exists():
        return str(expected_mp4.resolve())

    # Fallback search if different extension was produced
    for f in download_path.glob(f"{clean_id}.*"):
        if f.suffix in ['.mp4', '.mkv', '.webm', '.mov']:
            return str(f.resolve())

    return str(expected_mp4.resolve())


