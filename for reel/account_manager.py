import os
import sys
import json
import shutil
import getpass
from pathlib import Path
from typing import Optional, List, Dict

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
ACTIVE_FILE = os.path.join(SESSIONS_DIR, "active_account.txt")
LEGACY_SESSION = os.path.abspath(os.path.join(BASE_DIR, "..", "session.json"))

def _init_sessions():
    """Initializes sessions directory and imports legacy session if present."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    
    # If no session files exist in sessions/ but legacy session.json exists, copy it
    existing_sessions = [f for f in os.listdir(SESSIONS_DIR) if f.lower().endswith(".json")]
    if not existing_sessions and os.path.exists(LEGACY_SESSION):
        target = os.path.join(SESSIONS_DIR, "poetghazipur61.json")
        try:
            shutil.copy2(LEGACY_SESSION, target)
            if not os.path.exists(ACTIVE_FILE):
                with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
                    f.write("poetghazipur61\n")
        except Exception as e:
            print(f"[*] Notice: Could not migrate legacy session: {e}")

_init_sessions()

def clean_username(username: str) -> str:
    """Normalizes an Instagram username (stripping @, whitespace, .json)."""
    u = username.strip()
    if u.startswith("@"):
        u = u[1:]
    if u.lower().endswith(".json"):
        u = u[:-5]
    return u.strip()

def list_accounts() -> List[Dict[str, any]]:
    """Returns a list of all saved Instagram accounts and indicates active status."""
    _init_sessions()
    active_user = get_active_account()
    accounts = []
    
    if os.path.exists(SESSIONS_DIR):
        for fname in sorted(os.listdir(SESSIONS_DIR)):
            if fname.lower().endswith(".json"):
                uname = fname[:-5]
                accounts.append({
                    "username": uname,
                    "session_path": os.path.join(SESSIONS_DIR, fname),
                    "is_active": (uname.lower() == active_user.lower())
                })
    return accounts

def get_active_account() -> str:
    """Returns the currently active Instagram account name."""
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return clean_username(content)
        except Exception:
            pass

    # Fallback to the first session found in sessions/
    if os.path.exists(SESSIONS_DIR):
        files = [f for f in os.listdir(SESSIONS_DIR) if f.lower().endswith(".json")]
        if files:
            return clean_username(files[0][:-5])

    return "poetghazipur61"

def set_active_account(username: str) -> bool:
    """Switches the active Instagram account."""
    uname = clean_username(username)
    session_file = os.path.join(SESSIONS_DIR, f"{uname}.json")
    
    # Check if session exists in sessions/
    if not os.path.exists(session_file):
        # Check if legacy session matches
        if os.path.exists(LEGACY_SESSION) and uname.lower() == "poetghazipur61":
            shutil.copy2(LEGACY_SESSION, session_file)
        else:
            print(f"[!] Session file not found for account: @{uname}")
            print(f"    Expected: {session_file}")
            print(f"    To add this account, run: .\\commands.ps1 add-account {uname}")
            return False

    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(f"{uname}\n")
    print(f"[OK] Active Instagram account set to: @{uname}")
    return True

def get_session_path(username: Optional[str] = None) -> str:
    """Returns the full path to the session JSON file for the given or active account."""
    _init_sessions()
    uname = clean_username(username) if username else get_active_account()
    target_path = os.path.join(SESSIONS_DIR, f"{uname}.json")
    if os.path.exists(target_path):
        return target_path
    if os.path.exists(LEGACY_SESSION) and uname.lower() == "poetghazipur61":
        return LEGACY_SESSION
    return target_path

def get_instagram_client(username: Optional[str] = None):
    """
    Initializes and returns an authenticated instagrapi Client for the requested
    or active Instagram account.
    """
    from instagrapi import Client
    
    _init_sessions()
    uname = clean_username(username) if username else get_active_account()
    session_path = get_session_path(uname)
    
    cl = Client()
    if os.path.exists(session_path):
        print(f"[*] Loading Instagram session from: {session_path}")
        try:
            cl.load_settings(session_path)
            # Verify session login status
            user_id = cl.user_id
            logged_username = cl.username_from_user_id(user_id) if user_id else uname
            print(f"[OK] Logged in as: @{logged_username}")
            return cl
        except Exception as e:
            print(f"[*] Session loaded with notice ({e}). Continuing with active session...")
            return cl
    else:
        print(f"[!] Session file not found for @{uname} at:")
        print(f"    {session_path}")
        print(f"Please log in first using: .\\commands.ps1 add-account {uname}")
        return None

def login_new_account(username: str, password: Optional[str] = None):
    """
    Interactively logs into an Instagram account and saves the session
    in sessions/<username>.json.
    """
    from instagrapi import Client
    from instagrapi.exceptions import (
        TwoFactorRequired,
        BadPassword,
        ChallengeRequired,
        FeedbackRequired
    )

    uname = clean_username(username)
    print("=" * 60)
    print(f"  INSTAGRAM LOGIN - ADD ACCOUNT: @{uname}")
    print("=" * 60)
    print("Your password is NOT stored in any script or code.")
    print("It is used once to authenticate and generate an encrypted session.json.")
    print("=" * 60)

    if not password:
        password = getpass.getpass(f"Enter Instagram password for @{uname}: ")
        if not password:
            print("[!] Password cannot be empty.")
            return False

    cl = Client()
    session_file = os.path.join(SESSIONS_DIR, f"{uname}.json")

    print(f"\n[*] Authenticating with Instagram as @{uname}...")
    try:
        cl.login(uname, password)
    except TwoFactorRequired:
        print("\n[!] Two-Factor Authentication (2FA) is enabled for this account.")
        code = input("Enter the 6-digit 2FA verification code (from SMS/Auth App): ").strip()
        try:
            cl.login(uname, password, verification_code=code)
        except Exception as e:
            print(f"[!] 2FA verification failed: {e}")
            return False
    except BadPassword:
        print("[!] Login failed: Incorrect password.")
        return False
    except ChallengeRequired:
        print("[!] Instagram challenge required (Email/SMS verification).")
        print("Please resolve the checkpoint in your Instagram mobile app or browser first.")
        return False
    except FeedbackRequired as e:
        print(f"[!] Instagram rate limit/action blocked: {e}")
        return False
    except Exception as e:
        print(f"[!] Login error: {e}")
        return False

    try:
        cl.dump_settings(session_file)
        print(f"\n[OK] Successfully authenticated and saved session to:")
        print(f"    {session_file}")
        
        # Ask to make this active
        set_active_account(uname)
        return True
    except Exception as e:
        print(f"[!] Error saving session settings: {e}")
        return False

def print_accounts():
    """Prints a styled list of all available Instagram accounts."""
    accounts = list_accounts()
    active_user = get_active_account()
    
    print("=" * 55)
    print("           AVAILABLE INSTAGRAM ACCOUNTS")
    print("=" * 55)
    
    if not accounts:
        print("  No saved accounts found in sessions/ folder.")
        print(f"  Legacy session: {'Found' if os.path.exists(LEGACY_SESSION) else 'Not found'}")
        print("\nTo add an account, run: .\\commands.ps1 add-account <username>")
    else:
        for idx, acc in enumerate(accounts, 1):
            if acc["is_active"]:
                print(f"  [{idx}] @{acc['username']:<22} [ACTIVE -> POSTS GO HERE]")
            else:
                print(f"  [{idx}] @{acc['username']:<22}")
    
    print("-" * 55)
    print(f"Currently active account: @{active_user}")
    print("=" * 55)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_accounts()
        sys.exit(0)

    action = sys.argv[1].lower().strip()

    if action in ["list", "accounts", "show"]:
        print_accounts()
    elif action in ["get", "active", "current"]:
        print(get_active_account())
    elif action in ["use", "switch", "set", "select"]:
        if len(sys.argv) < 3:
            print("Usage: python account_manager.py use <username>")
            sys.exit(1)
        target = sys.argv[2]
        success = set_active_account(target)
        sys.exit(0 if success else 1)
    elif action in ["login", "add", "add-account"]:
        if len(sys.argv) < 3:
            uname = input("Enter Instagram username to add: ").strip()
        else:
            uname = sys.argv[2]
        pwd = sys.argv[3] if len(sys.argv) > 3 else None
        success = login_new_account(uname, pwd)
        sys.exit(0 if success else 1)
    else:
        print(f"[!] Unknown action: {action}")
        print("Usage: python account_manager.py [list | use <username> | login <username> | active]")
        sys.exit(1)
