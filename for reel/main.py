import sys
import os
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from database import init_db, record_reel, mark_published, is_reel_processed
from instagram_source import fetch_recent_reels, extract_username_or_url
from downloader import download_reel
from caption_ai import generate_reel_content, save_caption_cache
from post_reel_direct import get_instagram_client, ensure_thumbnail

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEW_REELS_DIR = os.path.join(BASE_DIR, "reels", "new")
POSTED_DIR = os.path.join(BASE_DIR, "reels", "posted")

for d in [NEW_REELS_DIR, POSTED_DIR]:
    os.makedirs(d, exist_ok=True)

def format_count(count: int) -> str:
    if not count:
        return "N/A"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)

def main():
    init_db()
    print("=" * 50)
    print("         INSTAGRAM VIRAL REEL BOT")
    print("=" * 50)

    profile_url = input("\nEnter Instagram profile or Reel URL:\n> ").strip()
    if not profile_url:
        print("[!] No URL provided. Exiting.")
        return

    print("\nSearching and analyzing Reels...")
    reels = fetch_recent_reels(profile_url, limit=5)

    if not reels:
        print("[!] No Reels found or URL is inaccessible. Make sure the post is public.")
        return

    print(f"\nFound {len(reels)} candidate(s):\n")
    for idx, r in enumerate(reels, 1):
        processed_tag = " [PROCESSED]" if is_reel_processed(r["id"]) else ""
        title_snippet = (r["title"][:40] + "...") if len(r["title"]) > 40 else r["title"]
        print(f"[{idx}] Views: {format_count(r['views']) : <7} | Likes: {format_count(r['likes']) : <7} | Title: {title_snippet}{processed_tag}")

    top_reel = reels[0]
    print(f"\nTop Candidate: {top_reel['url']} ({format_count(top_reel['likes'])} likes)")

    choice = input("\nDownload this Reel? [Y/N]: ").strip().lower()
    if choice not in ['y', 'yes']:
        print("Cancelled.")
        return

    print("\n[*] Downloading media...")
    try:
        download_target_url = top_reel["url"]
        local_file = download_reel(download_target_url, custom_id=top_reel["id"])
        print(f"[✓] Saved locally to: {local_file}")
    except Exception as e:
        print(f"[!] Download failed: {e}")
        return

    # Move a copy or link into reels/new for workflow consistency
    reel_filename = os.path.basename(local_file)
    new_reel_path = os.path.join(NEW_REELS_DIR, reel_filename)
    if os.path.abspath(local_file) != os.path.abspath(new_reel_path):
        shutil.copy2(local_file, new_reel_path)

    # Content-Aware Caption & Hashtag Generation
    print("\n[*] Analyzing video content & generating AI caption + hashtags...")
    ai_meta = generate_reel_content(new_reel_path)
    full_caption = ai_meta["full"]

    print("\n" + "-" * 45)
    print("PROPOSED CAPTION:")
    print("-" * 45)
    print(ai_meta["caption"])
    print("\nHASHTAGS:")
    print(ai_meta["hashtags"])
    print("-" * 45)

    user_caption_choice = input("\nPress ENTER to accept this caption, or type 'edit' to change:\n> ").strip().lower()
    if user_caption_choice == 'edit':
        custom_body = input("\nEnter custom caption text:\n> ").strip()
        custom_tags = input("Enter custom hashtags (or press Enter to keep AI tags):\n> ").strip()
        tags = custom_tags if custom_tags else ai_meta["hashtags"]
        full_caption = f"{custom_body}\n\n{tags}"
        save_caption_cache(reel_filename, custom_body, tags, topic="Custom")

    # Record in history
    record_reel(
        reel_id=top_reel["id"],
        original_url=top_reel["url"],
        views=top_reel.get("views") or 0,
        likes=top_reel.get("likes") or 0,
        caption=full_caption,
        local_filepath=local_file,
        status="downloaded"
    )

    publish_choice = input(f"\nPost this Reel to your Instagram (@poetghazipur61)? [Y/N]: ").strip().lower()
    if publish_choice in ['y', 'yes']:
        cl = get_instagram_client()
        if not cl:
            print("[!] Could not connect to Instagram session. Skipping publish.")
            return

        print(f"\n[*] Preparing thumbnail & publishing Reel directly to @poetghazipur61...")
        thumb_path = ensure_thumbnail(new_reel_path)
        try:
            upload_kwargs = {
                "path": Path(new_reel_path),
                "caption": full_caption
            }
            if thumb_path and os.path.exists(thumb_path):
                upload_kwargs["thumbnail"] = Path(thumb_path)

            media = cl.clip_upload(**upload_kwargs)
            print(f"\n[✓] REEL PUBLISHED SUCCESSFULLY!")
            print(f"    Media PK: {media.pk}")
            print(f"    Code: {media.code}")
            print(f"    Instagram URL: https://www.instagram.com/reel/{media.code}/")

            mark_published(top_reel["id"])

            dest_path = os.path.join(POSTED_DIR, reel_filename)
            shutil.move(new_reel_path, dest_path)
            if thumb_path and os.path.exists(thumb_path):
                shutil.move(thumb_path, os.path.join(POSTED_DIR, os.path.basename(thumb_path)))
            print(f"[✓] Moved '{reel_filename}' -> reels/posted/")
        except Exception as e:
            print(f"[!] Publishing error: {e}")
    else:
        print("[*] Skipped publishing. Video saved in downloads/ and reels/new/ for later.")

if __name__ == "__main__":
    main()
