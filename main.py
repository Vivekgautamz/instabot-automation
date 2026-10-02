import argparse
import os
import shutil
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

import ai_caption
import instagram
import storage

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "images"
POSTED_DIR = BASE_DIR / "posted"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def setup_directories() -> None:
    """Ensure images/ and posted/ directories exist."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)


def get_pending_images() -> list[Path]:
    """Find all unposted image files inside the images/ directory."""
    setup_directories()
    images = []
    for file in sorted(IMAGES_DIR.iterdir()):
        if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
            if not storage.is_already_posted(str(file)):
                images.append(file)
    return images


def check_status() -> None:
    """Check connectivity to Ollama and Meta Instagram API."""
    print("=" * 60)
    print("🔍 Instagram Auto Poster System Diagnostic")
    print("=" * 60)

    # 1. Ollama status
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2-vision")
    print(f"\n[1] Checking Ollama AI ({ollama_host})...")
    try:
        import requests
        res = requests.get(f"{ollama_host.rstrip('/')}/api/tags", timeout=5)
        if res.status_code == 200:
            models = [m.get("name") for m in res.json().get("models", [])]
            print(f"  ✅ Ollama is running.")
            matched = any(ollama_model in m for m in models)
            if matched:
                print(f"  ✅ Model '{ollama_model}' is installed and ready.")
            else:
                print(f"  ⚠️ Model '{ollama_model}' not found in installed models: {models}")
                print(f"     Run: ollama pull {ollama_model}")
        else:
            print(f"  ❌ Ollama returned status {res.status_code}")
    except Exception as e:
        print(f"  ❌ Could not connect to Ollama: {e}")
        print(f"     Make sure Ollama is installed and running (`ollama serve`).")

    # 2. Instagram Account Status
    print(f"\n[2] Checking Instagram Account...")
    ig_client = instagram.get_instagram_client()
    client_type = "Meta Graph API" if isinstance(ig_client, instagram.MetaGraphInstagramClient) else "Direct Login"
    print(f"  Mode: {client_type}")
    ok, message = ig_client.validate_credentials()
    if ok:
        print(f"  ✅ {message}")
    else:
        print(f"  ⚠️ {message}")

    # 3. Storage & Folders
    setup_directories()
    pending = get_pending_images()
    posted_count = storage.get_posted_count()
    print(f"\n[3] Folder & Queue Status:")
    print(f"  📁 images/ queue: {len(pending)} pending image(s)")
    print(f"  📁 posted/ archive: {posted_count} previously posted image(s)")

    # 4. Supabase Database Status
    print(f"\n[4] Checking Supabase Database...")
    try:
        import supabase_client
        sb = supabase_client.get_supabase_manager()
        if sb.is_configured():
            print(f"  ✅ Supabase connected ({sb.url})")
        else:
            print(f"  ⚠️ Supabase service key not set in .env (SUPABASE_SERVICE_ROLE_KEY)")
    except Exception as e:
        print(f"  ⚠️ Supabase check error: {e}")

    print("=" * 60)



def process_image(
    image_path: Path,
    dry_run: bool = False,
    model: str = None,
    style: str = None,
    override_url: str = None,
) -> bool:
    """Process a single image through the complete pipeline."""
    print(f"\n📸 Processing: {image_path.name}")
    print("-" * 50)

    # 1. Duplicate check
    if storage.is_already_posted(str(image_path)):
        print(f"  ⏭️ Skipping: Image already posted previously.")
        return False

    # 2. AI Caption Generation
    print("  🤖 Generating AI caption with Ollama...")
    try:
        caption = ai_caption.generate_caption(
            str(image_path),
            model=model,
            style=style,
        )
        print("\n--- [Generated Caption & Hashtags] ---")
        print(caption)
        print("--------------------------------------\n")
    except Exception as e:
        print(f"  ❌ Failed to generate caption: {e}")
        return False

    if dry_run:
        print("  💡 DRY RUN MODE: Skipping Instagram publication and file move.")
        return True

    # 3. Publish to Instagram
    ig_client = instagram.get_instagram_client()
    ok, status_msg = ig_client.validate_credentials()
    if not ok:
        print(f"  ❌ Instagram authentication error: {status_msg}")
        return False

    print(f"  🚀 Publishing to Instagram (@{getattr(ig_client, 'username', 'Account')})...")
    try:
        if isinstance(ig_client, instagram.DirectInstagramClient):
            media_id = ig_client.post_local_photo(str(image_path), caption=caption)
        else:
            # Meta Graph API requires public URL
            public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
            image_url = override_url or (f"{public_base_url}/{image_path.name}" if public_base_url else None)
            if not image_url:
                print("  ❌ Meta Instagram Graph API requires an accessible HTTPS image URL.")
                print("     Set PUBLIC_BASE_URL in .env (e.g. using ngrok or cloud storage)")
                return False
            media_id = ig_client.post_photo(image_url=image_url, caption=caption)

        print(f"  🎉 Published successfully! Instagram Media ID: {media_id}")
    except Exception as e:
        print(f"  ❌ Instagram publishing error: {e}")
        storage.record_post(str(image_path), None, caption, status="FAILED")
        return False

    # 4. Record & Archive
    storage.record_post(str(image_path), media_id, caption, status="SUCCESS")
    dest_path = POSTED_DIR / image_path.name
    if dest_path.exists():
        timestamp = int(time.time())
        dest_path = POSTED_DIR / f"{image_path.stem}_{timestamp}{image_path.suffix}"

    shutil.move(str(image_path), str(dest_path))
    print(f"  📁 Moved to: {dest_path.relative_to(BASE_DIR)}")
    return True


def run_pipeline(
    single_image: str = None,
    dry_run: bool = False,
    model: str = None,
    style: str = None,
    override_url: str = None,
) -> None:
    """Run pipeline for single image or batch queue."""
    setup_directories()

    if single_image:
        target = Path(single_image)
        if not target.exists():
            print(f"❌ Error: Specified file '{single_image}' does not exist.")
            sys.exit(1)
        process_image(target, dry_run=dry_run, model=model, style=style, override_url=override_url)
        return

    images = get_pending_images()
    if not images:
        print("📁 No pending images found in 'images/' directory.")
        print("   Drop .jpg or .png images into the 'images/' folder to auto-post.")
        return

    print(f"🚀 Found {len(images)} pending image(s) to process.")
    for idx, img in enumerate(images, 1):
        try:
            print(f"\n[{idx}/{len(images)}]")
            success = process_image(img, dry_run=dry_run, model=model, style=style, override_url=override_url)
            if success and not dry_run and idx < len(images):
                # Gentle pause between posts to respect Instagram rate limits
                time.sleep(5)
        except Exception as exc:
            print(f"  ❌ Error processing {img.name}: {exc}")
            continue


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Python Instagram Auto Poster with Ollama Vision AI & Meta Graph API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze image and generate caption without publishing to Instagram",
    )
    parser.add_argument(
        "--image",
        type=str,
        help="Process a specific image path instead of the entire images/ folder",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Provide public HTTPS image URL corresponding to the image",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Override Ollama vision model (e.g. llama3.2-vision, llava)",
    )
    parser.add_argument(
        "--style",
        type=str,
        choices=["engaging", "aesthetic", "witty", "minimalist", "informative"],
        help="Override caption tone and writing style",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously and monitor the images/ folder",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds when using --watch (default: 60)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check connectivity to Ollama and Meta Instagram API",
    )
    parser.add_argument(
        "--code",
        type=str,
        help="Two-factor authentication (2FA) verification code for first-time login",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show recent post history",
    )

    args = parser.parse_args()

    if args.code:
        os.environ["IG_2FA_CODE"] = args.code.strip()

    if args.status:
        check_status()
        return

    if args.history:
        posts = storage.list_recent_posts(10)
        print("\n📜 Recent Post History:")
        if not posts:
            print("  No posts recorded yet.")
        for p in posts:
            print(f"  • [{p['posted_at'][:19]}] {p['file_name']} (Status: {p['status']}, IG ID: {p['ig_media_id']})")
        print()
        return

    if args.watch:
        print(f"👀 Monitoring images/ folder every {args.interval}s. Press Ctrl+C to stop.")
        try:
            while True:
                run_pipeline(
                    dry_run=args.dry_run,
                    model=args.model,
                    style=args.style,
                    override_url=args.url,
                )
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n🛑 Stopped monitoring.")
    else:
        run_pipeline(
            single_image=args.image,
            dry_run=args.dry_run,
            model=args.model,
            style=args.style,
            override_url=args.url,
        )


if __name__ == "__main__":
    main()
