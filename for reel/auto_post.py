import os
import sys
import time
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from account_manager import (
    get_instagram_client,
    get_active_account,
    set_active_account,
    list_accounts
)
from post_image import (
    get_available_images,
    POSTED_IMAGES_DIR,
    LEGACY_POSTED_DIR,
    DEFAULT_IMAGE_HASHTAGS
)
from post_reel_direct import (
    get_pending_reels,
    upload_single_reel,
    NEW_REELS_DIR
)
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def auto_post_all(account: str = None, delay_seconds: int = 5):
    """
    Automatically posts all pending images in images/new/ and reels in reels/new/
    to the active or designated Instagram account.
    """
    if account:
        set_active_account(account)

    active_user = get_active_account()

    print("=" * 65)
    print(f"       INSTAGRAM AUTOMATIC BATCH POSTER (@{active_user})")
    print("=" * 65)

    # 1. Fetch pending items
    images = get_available_images()
    reels = get_pending_reels()

    total_items = len(images) + len(reels)
    print(f"[*] Queue Status:")
    print(f"    - Pending Images : {len(images)}")
    print(f"    - Pending Reels  : {len(reels)}")
    print(f"    - Target Account : @{active_user}")
    print(f"    - Safe Delay     : {delay_seconds}s between posts")
    print("-" * 65)

    if total_items == 0:
        print("[!] No pending content found to post.")
        print(f"    Drop photos into:  images/new/")
        print(f"    Drop videos into:  reels/new/")
        print("\nThen run this command again.")
        return

    # 2. Authenticate
    cl = get_instagram_client(active_user)
    if not cl:
        print(f"[!] Authentication failed for @{active_user}. Aborting auto-post.")
        return

    posted_count = 0
    failed_count = 0

    # 3. Post Images First
    if images:
        print(f"\n>>> PROCESSING {len(images)} IMAGE(S)...")
        for idx, img_path in enumerate(images, 1):
            fname = os.path.basename(img_path)
            print(f"\n[{idx}/{len(images)}] Posting image: {fname}")
            
            caption_text = "Words from the heart. ✨"
            full_caption = f"{caption_text}\n\n{DEFAULT_IMAGE_HASHTAGS}"
            
            try:
                media = cl.photo_upload(
                    path=Path(img_path),
                    caption=full_caption
                )
                print(f"[OK] Photo uploaded: https://www.instagram.com/p/{media.code}/")
                
                # Move to images/posted/
                dest = os.path.join(POSTED_IMAGES_DIR, fname)
                shutil.move(img_path, dest)
                print(f"[OK] Moved to: images/posted/{fname}")
                
                # Mirror to legacy folder
                try:
                    shutil.copy2(dest, os.path.join(LEGACY_POSTED_DIR, fname))
                except Exception:
                    pass
                
                posted_count += 1
            except Exception as e:
                print(f"[!] Failed to post image {fname}: {e}")
                failed_count += 1

            if idx < len(images) or reels:
                print(f"[*] Cooling down for {delay_seconds}s to protect account health...")
                time.sleep(delay_seconds)

    # 4. Post Reels Next
    if reels:
        print(f"\n>>> PROCESSING {len(reels)} REEL(S)...")
        for idx, r_fname in enumerate(reels, 1):
            print(f"\n[{idx}/{len(reels)}] Preparing Reel: {r_fname}")
            try:
                success = upload_single_reel(cl, r_fname, auto_confirm=True)
                if success:
                    posted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"[!] Failed to post Reel {r_fname}: {e}")
                failed_count += 1

            if idx < len(reels):
                print(f"[*] Cooling down for {delay_seconds}s to protect account health...")
                time.sleep(delay_seconds)

    print("\n" + "=" * 65)
    print("                 AUTO-POST RUN COMPLETE")
    print("=" * 65)
    print(f"  Target Account  : @{active_user}")
    print(f"  Successfully Posted : {posted_count}")
    print(f"  Failed / Skipped   : {failed_count}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Instagram Auto-Post for Images and Reels")
    parser.add_argument(
        "--account", "-a",
        type=str,
        default=None,
        help="Specify Instagram account username to post to"
    )
    parser.add_argument(
        "--delay", "-d",
        type=int,
        default=5,
        help="Seconds delay between consecutive uploads (default: 5)"
    )
    args = parser.parse_args()
    auto_post_all(account=args.account, delay_seconds=args.delay)

if __name__ == "__main__":
    main()
