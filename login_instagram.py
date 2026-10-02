import os
import sys
import json
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
DEBUG_JSON = Path(__file__).resolve().parent / "debug_login_response.json"


def find_key_recursive(data, key):
    """Recursively search for a key in deeply nested dicts/lists."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            result = find_key_recursive(v, key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_key_recursive(item, key)
            if result is not None:
                return result
    return None


def login_interactive():
    print("=" * 60)
    print("Instagram Login Helper for @poetghazipur61")
    print("=" * 60)

    username = os.getenv("IG_USERNAME", "poetghazipur61").strip()
    password = os.getenv("IG_PASSWORD", "").strip()
    if not password:
        password = input(f"Enter Instagram password for @{username}: ").strip()

    try:
        from instagrapi import Client
        from instagrapi.exceptions import TwoFactorRequired
    except ImportError:
        print("instagrapi not found. Run: .venv\\Scripts\\pip install instagrapi")
        return

    # Remove stale session
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

    cl = Client()
    cl.delay_range = [2, 5]

    print(f"\nLogging in as @{username}...")

    login_exc = None
    login_json = None

    try:
        cl.login(username, password)
        # No 2FA needed
        cl.dump_settings(str(SESSION_FILE))
        info = cl.account_info()
        print(f"\n[OK] Logged in as @{info.username} - session saved!")
        print("Now run: .venv\\Scripts\\python main.py --image \"images\\DdX9ksWmaoS_image_1.jpg\"")
        return
    except TwoFactorRequired as e:
        login_exc = e
        login_json = cl.last_json
    except Exception as e:
        print(f"\n[ERROR] Login error: {e}")
        return

    # Save raw login JSON for debugging
    with open(DEBUG_JSON, "w", encoding="utf-8") as f:
        json.dump(login_json, f, indent=2, default=str)

    # Check if two_step_verification_context is present
    context = find_key_recursive(login_json, "two_step_verification_context")
    if not context:
        print("\n[DIAGNOSTIC] two_step_verification_context NOT found in login response.")
        print(f"Raw response saved to: {DEBUG_JSON.name}")
        print("\nThis usually means Instagram requires you to verify via the app first.")
        print("\n--- SOLUTION ---")
        print("Option 1 (Easiest): Open Instagram on your phone ->")
        print("  Settings -> Accounts Centre -> Password and security ->")
        print("  Two-factor authentication -> TURN OFF 2FA")
        print("  Then run this script again. (You can re-enable 2FA after.)")
        print("")
        print("Option 2: Open Instagram app and approve the login from")
        print("  the notification that says 'Did you try to log in?' -> Approve")
        print("  Then run this script again immediately.")
        return

    print(f"\n[OK] two_step_verification_context found.")
    print("Instagram requires a verification code.")
    print("Check your phone (SMS) or Authenticator app NOW for a fresh code.")

    code = input("\nEnter the 6-digit code: ").strip()

    try:
        success = cl._login_with_bloks_two_factor(
            verification_code=code,
            login_json=login_json,
            exc=login_exc,
        )
        if success:
            cl.dump_settings(str(SESSION_FILE))
            try:
                info = cl.account_info()
                uname = info.username
            except Exception:
                uname = username
            print("\n" + "=" * 60)
            print(f"[SUCCESS] Logged in as @{uname}!")
            print("Session saved. Now run:")
            print("  .venv\\Scripts\\python main.py --image \"images\\DdX9ksWmaoS_image_1.jpg\"")
            print("=" * 60)
        else:
            print("\n[ERROR] 2FA returned False. Try again with a fresh code.")
    except TwoFactorRequired as e:
        print(f"\n[ERROR] Bloks 2FA failed: {e}")
        print("\n--- SOLUTION ---")
        print("Please TEMPORARILY disable 2FA in Instagram settings:")
        print("  Phone -> Instagram -> Settings -> Accounts Centre ->")
        print("  Password and security -> Two-factor authentication -> Turn Off")
        print("Then run this script again.")
        print("Once session is saved, you can re-enable 2FA.")
    except Exception as e:
        print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    login_interactive()
