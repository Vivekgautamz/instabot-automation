import re
from typing import List, Dict, Any
import yt_dlp

def extract_username_or_url(input_str: str) -> str:
    """Normalize input URL or username."""
    input_str = input_str.strip()
    if not input_str.startswith("http"):
        # Username was entered
        username = input_str.lstrip("@").strip("/")
        return f"https://www.instagram.com/{username}/"
    return input_str

def fetch_recent_reels(profile_or_reel_url: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch public metadata for reels from the profile or single reel URL using yt-dlp.
    """
    normalized_url = extract_username_or_url(profile_or_reel_url)
    if "/reel/" not in normalized_url and "/reels/" not in normalized_url and not normalized_url.endswith("/reels/"):
        reels_url = normalized_url.rstrip("/") + "/reels/"
    else:
        reels_url = normalized_url

    ydl_opts = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'playlist_items': f"1-{limit}",
        'quiet': True,
        'no_warnings': True,
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reels_url, download=False)
            
            entries = info.get('entries', []) if 'entries' in info else [info]
            for entry in entries:
                if not entry:
                    continue
                reel_id = entry.get('id') or "reel"
                # Always use clean canonical instagram reel URL
                url = f"https://www.instagram.com/reel/{reel_id}/"
                title = entry.get('title') or entry.get('description') or "No description"
                view_count = entry.get('view_count') or 0
                like_count = entry.get('like_count') or 0
                
                results.append({
                    "id": str(reel_id),
                    "url": url,
                    "title": title,
                    "views": view_count,
                    "likes": like_count,
                    "thumbnail": entry.get('thumbnail')
                })

    except Exception as e:
        print(f"[!] Info: Direct flat extraction encountered ({e}). Falling back to single entry inspect.")
        # Single reel check
        try:
            with yt_dlp.YoutubeDL({'skip_download': True, 'quiet': True}) as ydl:
                info = ydl.extract_info(profile_or_reel_url, download=False)
                if info:
                    reel_id = info.get('id') or "single_reel"
                    web_url = info.get('webpage_url') or profile_or_reel_url
                    if not web_url.startswith("https://www.instagram.com/reel/"):
                        web_url = f"https://www.instagram.com/reel/{reel_id}/"
                    results.append({
                        "id": str(reel_id),
                        "url": web_url,
                        "title": info.get('title') or info.get('description') or "Reel",
                        "views": info.get('view_count') or 0,
                        "likes": info.get('like_count') or 0,
                        "thumbnail": info.get('thumbnail')
                    })
        except Exception as err:
            print(f"[!] Extraction error: {err}")


    # Sort candidates by views or likes descending
    results.sort(key=lambda x: (x.get('views') or 0, x.get('likes') or 0), reverse=True)
    return results
