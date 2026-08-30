
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

    try:

        conn = sqlite3.connect(DB_PATH)

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
        conn.close()

        return True, "Account created successfully!"

    except sqlite3.IntegrityError as e:

        # Username already exists.
        if "username" in str(e).lower():
            return False, "Username already taken."

        # Email already exists.
        if "email" in str(e).lower():
            return False, "Email is already registered."

        return False, "Could not create account."


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
# Send Email OTP
# ---------------------------------------------------------

def send_email_otp(email: str):
    """
    Ask Authsignal to send an Email OTP.

    Returns:
        success, message, challenge_id
    """

    email = email.strip().lower()

    if not email:
        return False, "Email cannot be empty.", None

    configured, message = _check_authsignal_config()

    if not configured:
        return False, message, None

    # Authsignal API endpoint for initiating a challenge.
    url = f"{AUTHSIGNAL_API_URL}/challenges"

    headers = {
        "Authorization": f"Bearer {AUTHSIGNAL_API_SECRET}",
        "Content-Type": "application/json",
    }

    payload = {
        # Email OTP authenticator
        "verificationMethod": "EMAIL_OTP",

        # This identifies what the user is verifying.
        "action": "signupEmailVerification",

        # Email receiving the OTP.
        "email": email,

        # Use email as the user's identifier.
        "userId": email,
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
        )

        # Convert response into JSON.
        data = response.json()

    except requests.RequestException as e:

        return (
            False,
            f"Could not connect to Authsignal: {e}",
            None
        )

    except ValueError:

        return (
            False,
            "Authsignal returned an invalid response.",
            None
        )

    # Authsignal accepted the request.
    if response.ok:

        challenge_id = data.get("challengeId")

        if not challenge_id:

            return (
                False,
                "Authsignal did not return a challenge ID.",
                None
            )

        return (
            True,
            "OTP sent successfully to your email.",
            challenge_id
        )

    # Authsignal rejected the request.
    error_message = (
        data.get("message")
        or data.get("error")
        or "Failed to send OTP."
    )

    return False, error_message, None


# ---------------------------------------------------------
# Verify Email OTP
# ---------------------------------------------------------

def verify_email_otp(
    email: str,
    challenge_id: str,
    otp: str
):
    """
    Verify the OTP entered by the user.

    Returns:
        success, message
    """

    email = email.strip().lower()
    otp = otp.strip()

    if not email:
        return False, "Email cannot be empty."

    if not challenge_id:
        return False, "Please request an OTP first."

    if not otp:
        return False, "Please enter the OTP."

    configured, message = _check_authsignal_config()

    if not configured:
        return False, message

    # Authsignal verification endpoint.
    url = (
        f"{AUTHSIGNAL_API_URL}/challenges/"
        f"{challenge_id}/verify"
    )

    headers = {
        "Authorization": f"Bearer {AUTHSIGNAL_API_SECRET}",
        "Content-Type": "application/json",
    }

    payload = {
        "code": otp
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15
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

    # OTP verified.
    if response.ok:

        # Authsignal may return different success
        # information depending on API version.
        status = data.get("status")
        verified = data.get("verified")

        if (
            status == "VERIFIED"
            or status == "verified"
            or verified is True
            or response.ok
        ):
            return True, "Email verified successfully."

    # OTP failed.
    error_message = (
        data.get("message")
        or data.get("error")
        or "Invalid or expired OTP."
    )

    return False, error_message