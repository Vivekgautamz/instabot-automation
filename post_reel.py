r"""
post_reel.py
------------
Post an image as an Instagram Reel with trending/searched music.

Usage:
  .venv\Scripts\python post_reel.py --image images\photo.jpg --music "tere bina"
  .venv\Scripts\python post_reel.py --music "arijit singh"          (uses first pending image)
  .venv\Scripts\python post_reel.py --list-music "love shayari"     (search & preview tracks)
"""
import argparse
import os
import sys
import subprocess
import shutil
import time
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SESSION_FILE = Path(__file__).resolve().parent / "session.json"
IMAGES_DIR = Path(__file__).resolve().parent / "images"
POSTED_DIR = Path(__file__).resolve().parent / "posted"
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
REEL_DURATION = 30  # seconds


# ── helpers ──────────────────────────────────────────────────────────────────

FFMPEG_BIN = "ffmpeg"
_local_ffmpeg = Path(__file__).resolve().parent / "ffmpeg.exe"
if _local_ffmpeg.exists():
    FFMPEG_BIN = str(_local_ffmpeg)


def check_ffmpeg() -> bool:
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_ig_client():
    from instagrapi import Client
    if not SESSION_FILE.exists():
        print("[ERROR] session.json not found. Run login first:")
        print("  .venv\\Scripts\\python login_instagram.py")
        sys.exit(1)
    username = os.getenv("IG_USERNAME", "poetghazipur61")
    password = os.getenv("IG_PASSWORD", "")
    cl = Client()
    cl.delay_range = [2, 5]
    cl.load_settings(str(SESSION_FILE))
    cl.login(username, password)
    return cl


def image_to_video(image_path: Path, duration: int, out_path: Path) -> Path:
    """Convert an image to a looping MP4 video (required for Reels upload)."""
    cmd = [
        FFMPEG_BIN, "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", "scale='if(gt(iw,ih),1080,trunc(1080*iw/ih/2)*2)':'if(gt(iw,ih),trunc(1080*ih/iw/2)*2,1080)',pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black",
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-an",
        str(out_path),
    ]
    print(f"  [ffmpeg] Converting image to video ({duration}s)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] ffmpeg failed: {result.stderr[-500:]}")
        sys.exit(1)
    return out_path


def search_music(cl, query: str, limit: int = 10):
    """Search Instagram for music tracks matching query."""
    print(f"\nSearching Instagram music: '{query}'...")
    try:
        results = cl.music_search_v2(query)
    except Exception as e:
        print(f"[ERROR] Music search failed: {e}")
        return []

    tracks = []
    items = results.get("items", [])
    for item in items[:limit]:
        track = item.get("track") if isinstance(item, dict) else item
        if track:
            tracks.append(track)
    return tracks


def pick_track(tracks, query: str):
    """Display tracks and let user select one, or auto-pick first."""
    if not tracks:
        return None

    print(f"\nFound {len(tracks)} track(s):\n")
    for i, t in enumerate(tracks):
        title = t.get("title", "Unknown") if isinstance(t, dict) else getattr(t, "title", "Unknown")
        artist = t.get("display_artist", t.get("subtitle", "Unknown")) if isinstance(t, dict) else getattr(t, "display_artist", "Unknown")
        tid = t.get("id", "?") if isinstance(t, dict) else getattr(t, "id", "?")
        print(f"  [{i+1}] {title} — {artist}  (id: {tid})")

    choice = input(f"\nSelect track [1-{len(tracks)}] or Enter for #1: ").strip()
    idx = int(choice) - 1 if choice.isdigit() else 0
    return tracks[max(0, min(idx, len(tracks) - 1))]


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Post Instagram Reel from image + trending music")
    parser.add_argument("--image", type=str, help="Path to image file")
    parser.add_argument("--music", type=str, default="shayari love poetry", help="Music search query")
    parser.add_argument("--duration", type=int, default=REEL_DURATION, help="Reel duration in seconds (default: 30)")
    parser.add_argument("--list-music", type=str, help="Search & list music tracks without posting")
    parser.add_argument("--caption", type=str, help="Custom caption (otherwise AI/preset used)")
    args = parser.parse_args()

    # ffmpeg check
    if not check_ffmpeg():
        print("\n[ERROR] ffmpeg is required to convert images to Reels video.")
        print("Please install ffmpeg:")
        print("  1. Download from: https://www.gyan.dev/ffmpeg/builds/")
        print("     (get 'ffmpeg-release-essentials.zip')")
        print("  2. Extract and copy ffmpeg.exe to: C:\\Windows\\System32\\")
        print("  3. Or add the bin/ folder to your PATH")
        print("\nAfter installing ffmpeg, run this script again.")
        sys.exit(1)

    # Login
    cl = get_ig_client()

    # Music search only mode
    if args.list_music:
        tracks = search_music(cl, args.list_music)
        if not tracks:
            print("No tracks found.")
        return

    # Resolve image
    if args.image:
        image_path = Path(args.image)
    else:
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        candidates = [f for f in sorted(IMAGES_DIR.iterdir())
                      if f.is_file() and f.suffix.lower() in exts]
        if not candidates:
            print("[ERROR] No images found in images/ folder.")
            sys.exit(1)
        image_path = candidates[0]

    if not image_path.exists():
        print(f"[ERROR] Image not found: {image_path}")
        sys.exit(1)

    print(f"\n[Reel] Image: {image_path.name}")
    print(f"[Reel] Music query: {args.music}")

    # Search music
    tracks = search_music(cl, args.music)
    if not tracks:
        print("[ERROR] No music tracks found. Try a different query with --music 'song name'")
        sys.exit(1)
    track = pick_track(tracks, args.music)
    if track is None:
        print("[ERROR] Could not select a track.")
        sys.exit(1)

    # Generate caption
    if args.caption:
        caption = args.caption
    else:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import ai_caption
            caption = ai_caption.generate_caption(str(image_path))
        except Exception:
            stem = image_path.stem.replace("_", " ").title()
            caption = (
                f"✨ {stem}\n\n"
                f"हर तस्वीर एक कहानी कहती है, कुछ अनकहे जज़्बात बयां करती है। ✍️\n\n"
                f"What story does this picture whisper to you?\n\n"
                f"#poetghazipur61 #poetry #shayari #reels #aesthetic #words"
            )

    print("\n--- [Caption] ---")
    print(caption)
    print("-----------------\n")

    # Convert image to video
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        video_path = tmp / f"{image_path.stem}_reel.mp4"
        thumbnail_path = tmp / f"{image_path.stem}_thumb.jpg"

        image_to_video(image_path, args.duration, video_path)

        # Generate thumbnail from source image using Pillow
        print("  [thumbnail] Generating thumbnail from image...")
        try:
            from PIL import Image as PILImage
            with PILImage.open(image_path) as img:
                img = img.convert("RGB")
                # Fit to 1080x1920 (Instagram Reel ratio) with black bars
                thumb = PILImage.new("RGB", (1080, 1920), (0, 0, 0))
                img.thumbnail((1080, 1920), PILImage.LANCZOS)
                offset = ((1080 - img.width) // 2, (1920 - img.height) // 2)
                thumb.paste(img, offset)
                thumb.save(str(thumbnail_path), "JPEG", quality=90)
            print(f"  [thumbnail] Saved: {thumbnail_path.name}")
        except Exception as e:
            print(f"  [WARN] Could not generate thumbnail: {e}")
            thumbnail_path = None

        # Upload as Reel with music
        print(f"\n[Reel] Uploading to @poetghazipur61 with music...")
        try:
            media = cl.clip_upload_with_music(
                path=video_path,
                caption=caption,
                track=track,
                thumbnail=thumbnail_path,
                music_volume=0.8,
                original_volume=0.0,
            )
            print(f"\n[SUCCESS] Reel published! Media ID: {media.pk}")
            print(f"View at: https://www.instagram.com/reel/{media.code}/")

            # Archive
            POSTED_DIR.mkdir(exist_ok=True)
            dest = POSTED_DIR / image_path.name
            if dest.exists():
                dest = POSTED_DIR / f"{image_path.stem}_{int(time.time())}{image_path.suffix}"
            shutil.move(str(image_path), str(dest))
            print(f"[Archive] Moved to: posted/{dest.name}")

        except Exception as e:
            print(f"\n[ERROR] Reel upload failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
