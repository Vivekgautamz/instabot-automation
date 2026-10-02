import os
import sys
import shutil
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from instagrapi import Client

from account_manager import get_instagram_client, get_active_account

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

# Image folders
IMAGES_DIR = os.path.join(BASE_DIR, "images")
NEW_IMAGES_DIR = os.path.join(IMAGES_DIR, "new")
POSTED_IMAGES_DIR = os.path.join(IMAGES_DIR, "posted")
LEGACY_POSTED_DIR = os.path.join(BASE_DIR, "posted_images")
DOWNLOADED_IMAGES_DIR = os.path.join(PARENT_DIR, "downloaded_images")

for d in [IMAGES_DIR, NEW_IMAGES_DIR, POSTED_IMAGES_DIR, LEGACY_POSTED_DIR]:
    os.makedirs(d, exist_ok=True)

DEFAULT_IMAGE_HASHTAGS = "#photo #photography #instagood #instagram #instadaily #photooftheday #explore #picoftheday"

def get_available_images():
    valid_exts = (".jpg", ".jpeg", ".png", ".webp")
    results = []

    # Check images/new/ first (recommended structure)
    if os.path.exists(NEW_IMAGES_DIR):
        for f in os.listdir(NEW_IMAGES_DIR):
            p = os.path.join(NEW_IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                results.append(p)

    # Check local images/ root folder (excluding subfolders)
    if os.path.exists(IMAGES_DIR):
        for f in os.listdir(IMAGES_DIR):
            p = os.path.join(IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                if p not in results:
                    results.append(p)

    # Also check parent downloaded_images folder
    if os.path.exists(DOWNLOADED_IMAGES_DIR):
        for f in os.listdir(DOWNLOADED_IMAGES_DIR):
            p = os.path.join(DOWNLOADED_IMAGES_DIR, f)
            if os.path.isfile(p) and f.lower().endswith(valid_exts):
                if p not in results:
                    results.append(p)

    return sorted(results)

def main():
    active_acc = get_active_account()
    print("=" * 55)
    print(f"      INSTAGRAM IMAGE PUBLISHER (@{active_acc})")
    print("=" * 55)

    cl = get_instagram_client(active_acc)
    if not cl:
        return

    images = get_available_images()
    if not images:
        print(f"\n[!] No images found in:")
        print(f"    - {NEW_IMAGES_DIR}")
        print(f"    - {IMAGES_DIR}")
        print(f"    - {DOWNLOADED_IMAGES_DIR}")
        print("\nPlease put your image (.jpg or .png) in 'images/new/' and run again.")
        return

    # Check if image was passed as command argument
    target_image = None
    if len(sys.argv) > 1:
        arg_path = " ".join(sys.argv[1:]).strip().strip('"').strip("'")
        if os.path.exists(arg_path):
            target_image = os.path.abspath(arg_path)

    if not target_image:
        print(f"\nFound {len(images)} image(s) available to post:\n")
        display_limit = min(len(images), 10)
        for i in range(display_limit):
            img_path = images[i]
            size_kb = os.path.getsize(img_path) / 1024
            print(f"[{i+1}] {os.path.basename(img_path)} ({size_kb:.1f} KB)")
        if len(images) > display_limit:
            print(f"... and {len(images) - display_limit} more.")

        choice = input("\nSelect Image number (or press Enter for [1]): ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        if 0 <= idx < len(images):
            target_image = images[idx]
        else:
            print("[!] Invalid choice.")
            return

    print(f"\nSelected image: {os.path.basename(target_image)}")

    caption_text = input("\nEnter caption (Press Enter for default caption):\n> ").strip()
    if not caption_text:
        caption_text = "Words from the heart. ✨"

    tags_input = input("Enter hashtags (Press Enter for default hashtags):\n> ").strip()
    if not tags_input:
        tags_input = DEFAULT_IMAGE_HASHTAGS

    full_caption = f"{caption_text}\n\n{tags_input}"

    print("\n" + "-" * 40)
    print("PROPOSED POST:")
    print("-" * 40)
    print(full_caption)
    print("-" * 40)

    confirm = input(f"\nPublish to @{active_acc}? [Y/N]: ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Cancelled.")
        return

    print(f"\n[*] Uploading photo to Instagram (@{active_acc})...")
    try:
        media = cl.photo_upload(
            path=Path(target_image),
            caption=full_caption
        )
        print(f"\n[OK] PHOTO PUBLISHED SUCCESSFULLY!")
        print(f"    Media PK: {media.pk}")
        print(f"    Code: {media.code}")
        print(f"    URL: https://www.instagram.com/p/{media.code}/")

        # Move to images/posted/
        dest = os.path.join(POSTED_IMAGES_DIR, os.path.basename(target_image))
        shutil.move(target_image, dest)
        print(f"[OK] Moved image -> images/posted/{os.path.basename(target_image)}")
        
        # Also mirror to legacy posted_images for compatibility
        try:
            legacy_dest = os.path.join(LEGACY_POSTED_DIR, os.path.basename(target_image))
            shutil.copy2(dest, legacy_dest)
        except Exception:
            pass
    except Exception as e:
        print(f"\n[!] Upload error: {e}")

if __name__ == "__main__":
    main()
