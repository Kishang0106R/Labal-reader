
"""
Label Lens - Authentication

SQLite:
    - Stores username, email and password hash.

Authsignal:
    - Sends Email OTP.
    - Verifies Email OTP.
    - OTP itself is NOT stored in SQLite.

IMPORTANT:
    Put your Authsignal credentials in a .env file.
"""

import hashlib
import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "auth.db"


# ---------------------------------------------------------
# Authsignal configuration
# ---------------------------------------------------------

AUTHSIGNAL_API_SECRET = os.getenv("AUTHSIGNAL_API_SECRET")
AUTHSIGNAL_API_URL = os.getenv(
    "AUTHSIGNAL_API_URL",
    "https://api.authsignal.com/v1"
)


# ---------------------------------------------------------
# Initialize authentication database
# ---------------------------------------------------------

def init_auth_db() -> None:
    """
    Create the users table if it does not exist, and migrate older
    databases that were created before the email column was added.
    """

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            email    TEXT    NOT NULL UNIQUE,
            salt     TEXT    NOT NULL,
            pw_hash  TEXT    NOT NULL
        )
        """
    )

    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    column_names = [column[1] for column in columns]

    if "email" not in column_names:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
            ON users(email)
            """
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# Password hashing
# ---------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    """
    Hash password using SHA-256 + per-user salt.
    """

    return hashlib.sha256(
        (salt + password).encode()
    ).hexdigest()


# ---------------------------------------------------------
# Create user
# ---------------------------------------------------------

def create_user(
    username: str,
    email: str,
    password: str
) -> tuple[bool, str]:
    """
    Create a new user after email verification.

    Returns:
        (True, success message)
        (False, error message)
    """

    init_auth_db()

    username = username.strip()
    email = email.strip().lower()

    if not username:
        return False, "Username cannot be empty."

    if not email:
        return False, "Email cannot be empty."

    if not password:
        return False, "Password cannot be empty."

    # Generate a random salt for this user.
    salt = os.urandom(16).hex()

    # Hash the password.
    pw_hash = _hash_password(password, salt)

    conn = sqlite3.connect(DB_PATH)

    try:

        conn.execute(
            """
            INSERT INTO users
            (username, email, salt, pw_hash)
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                email,
                salt,
                pw_hash
            )
        )

        conn.commit()

        return True, "Account created successfully!"

    except sqlite3.IntegrityError as e:

        # Username already exists.
        if "username" in str(e).lower():
            return False, "Username already taken."

        # Email already exists.
        if "email" in str(e).lower():
            return False, "Email is already registered."

        return False, "Could not create account."

    finally:

        conn.close()


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------

def verify_user(username: str, password: str) -> bool:
    """
    Check username and password.

    Returns True when credentials are correct.
    """

    init_auth_db()

    username = username.strip()

    if not username or not password:
        return False

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT salt, pw_hash
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    conn.close()

    if row is None:
        return False

    # Hash the entered password using
    # the same salt stored for this user.
    entered_hash = _hash_password(
        password,
        row["salt"]
    )

    return entered_hash == row["pw_hash"]


# =========================================================
# AUTHSIGNAL EMAIL OTP
# =========================================================
#
# Correct Authsignal flow:
#   1. Track Action  (Server API, Basic Auth)  → returns token
#   2. Challenge     (Client API, Bearer token) → sends OTP
#   3. Verify        (Client API, Bearer token) → checks OTP
# =========================================================


def _check_authsignal_config():
    """
    Make sure Authsignal credentials exist.
    """

    if not AUTHSIGNAL_API_SECRET:
        return False, "AUTHSIGNAL_API_SECRET is missing from .env"

    if not AUTHSIGNAL_API_URL:
        return False, "AUTHSIGNAL_API_URL is missing."

    return True, ""


# ---------------------------------------------------------
# Step 1: Track Action (Server API)
# ---------------------------------------------------------

def _track_action(email: str, action: str = "signupEmailVerification"):
    """
    Call the Authsignal Server API to track an action.

    Uses HTTP Basic Auth (secret key as username, empty password).
    Returns (success, data_or_error).
    """

    url = (
        f"{AUTHSIGNAL_API_URL}/users/"
        f"{requests.utils.quote(email, safe='')}"
        f"/actions/{action}"
    )

    try:

        response = requests.post(
            url,
            auth=(AUTHSIGNAL_API_SECRET, ""),
            json={"email": email},
            timeout=15,
        )

        data = response.json()

    except requests.RequestException as e:
        return False, f"Could not connect to Authsignal: {e}"

    except ValueError:
        return False, "Authsignal returned an invalid response."

    if response.ok:
        return True, data

    error_message = (
        data.get("message")
        or data.get("error")
        or f"Track action failed (HTTP {response.status_code})."
    )

    return False, error_message


# ---------------------------------------------------------
# Send Email OTP
# ---------------------------------------------------------

def send_email_otp(email: str):
    """
    Ask Authsignal to send an Email OTP.

    Flow:
        1. Track action → get short-lived token
        2. Challenge email-otp → Authsignal sends the email

    Returns:
        success, message, token, expires_at
    """

    email = email.strip().lower()

    if not email:
        return False, "Email cannot be empty.", None, None

    configured, message = _check_authsignal_config()

    if not configured:
        return False, message, None, None

    # ---- Step 1: Track action ----

    ok, result = _track_action(email)

    if not ok:
        return False, result, None, None

    token = result.get("token")

    if not token:
        return (
            False,
            "Authsignal did not return a token.",
            None,
            None,
        )

    # ---- Step 2: Challenge email-otp ----

    challenge_url = (
        f"{AUTHSIGNAL_API_URL}/client/challenge/email-otp"
    )

    challenge_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:

        response = requests.post(
            challenge_url,
            headers=challenge_headers,
            json={},
            timeout=15,
        )

        data = response.json()

    except requests.RequestException as e:

        return (
            False,
            f"Could not send OTP: {e}",
            None,
            None,
        )

    except ValueError:

        return (
            False,
            "Authsignal returned an invalid response.",
            None,
            None,
        )

    if response.ok:

        import time

        expires_at = time.time() + 120

        return (
            True,
            "OTP sent successfully to your email.",
            token,
            expires_at,
        )

    error_message = (
        data.get("message")
        or data.get("error")
        or "Failed to send OTP."
    )

    return (
        False,
        error_message,
        None,
        None,
    )


# ---------------------------------------------------------
# Verify Email OTP
# ---------------------------------------------------------

def verify_email_otp(
    token: str,
    otp: str
):
    """
    Verify the OTP entered by the user.

    Uses the short-lived Bearer token obtained during
    send_email_otp (stored as otp_challenge_id in session).

    Returns:
        success, message
    """

    otp = otp.strip()

    if not token:
        return False, "Please request an OTP first."

    if not otp:
        return False, "Please enter the OTP."

    configured, message = _check_authsignal_config()

    if not configured:
        return False, message

    url = (
        f"{AUTHSIGNAL_API_URL}/client/verify/email-otp"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "verificationCode": otp
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        data = response.json()

    except requests.RequestException as e:

        return (
            False,
            f"Could not connect to Authsignal: {e}"
        )

    except ValueError:

        return (
            False,
            "Authsignal returned an invalid response."
        )

    if response.ok:

        is_verified = data.get("isVerified")
        status = data.get("status")

        if (
            is_verified is True
            or status == "VERIFIED"
            or status == "verified"
        ):
            return True, "Email verified successfully."

        return False, "Invalid or expired OTP."

    error_message = (
        data.get("message")
        or data.get("error")
        or "Invalid or expired OTP."
    )

    return False, error_message