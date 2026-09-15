# ============================================================
# core/auth.py
# Label Lens - Authentication System
# ============================================================
#
# Features:
#   - SQLite authentication database
#   - Signup using email + username + password
#   - Gmail OTP email verification
#   - Secure password hashing using PBKDF2-HMAC-SHA256
#   - Login using EMAIL + PASSWORD
#   - Case-insensitive email handling
#   - Duplicate email protection
#   - Duplicate username protection
#   - OTP expiry
#   - OTP attempt limit
#
# Database:
#   data/auth.db
#
# ============================================================

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import sqlite3
import time

from pathlib import Path
from email.message import EmailMessage

from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "auth.db"


# ============================================================
# EMAIL CONFIGURATION
# ============================================================

EMAIL_ADDRESS = os.getenv(
    "EMAIL_ADDRESS",
    ""
).strip()

EMAIL_APP_PASSWORD = os.getenv(
    "EMAIL_APP_PASSWORD",
    ""
).strip()


# ============================================================
# OTP CONFIGURATION
# ============================================================

OTP_EXPIRY_SECONDS = 5 * 60

OTP_LENGTH = 6

MAX_OTP_ATTEMPTS = 5


# ============================================================
# PASSWORD CONFIGURATION
# ============================================================

# Number of PBKDF2 iterations.
# This makes password guessing much more expensive.
PASSWORD_ITERATIONS = 310_000

PASSWORD_SALT_BYTES = 16


# ============================================================
# TEMPORARY OTP STORAGE
# ============================================================
#
# OTP is kept only in memory.
#
# Structure:
#
# {
#     "user@gmail.com": {
#         "otp_hash": "...",
#         "expires_at": 1234567890,
#         "attempts": 0
#     }
# }
#
# ============================================================

_otp_store: dict[str, dict] = {}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def _get_connection() -> sqlite3.Connection:
    """
    Create a connection to the authentication database.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    return conn


# ============================================================
# INITIALIZE AUTH DATABASE
# ============================================================

def init_auth_db() -> None:
    """
    Create the authentication database and users table.
    """

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = _get_connection()

    try:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                username TEXT NOT NULL UNIQUE,

                email TEXT NOT NULL UNIQUE,

                password_hash TEXT NOT NULL,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # ----------------------------------------------------
        # Index for faster email login
        # ----------------------------------------------------

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_users_email
            ON users(email)

            """
        )

        # ----------------------------------------------------
        # Index for username lookup
        # ----------------------------------------------------

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_users_username
            ON users(username)
            """
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# NORMALIZE EMAIL
# ============================================================

def _normalize_email(
    email: str,
) -> str:
    """
    Normalize email for database operations.

    Example:

        User@Gmail.com

    becomes:

        user@gmail.com
    """

    return email.strip().lower()


# ============================================================
# VALIDATE EMAIL
# ============================================================

def _valid_email(
    email: str,
) -> bool:
    """
    Basic email validation.
    """

    email = _normalize_email(email)

    if not email:
        return False

    if "@" not in email:
        return False

    if email.startswith("@"):
        return False

    if email.endswith("@"):
        return False

    if " " in email:
        return False

    parts = email.split("@")

    if len(parts) != 2:
        return False

    local_part, domain = parts

    if not local_part:
        return False

    if not domain:
        return False

    if "." not in domain:
        return False

    return True


# ============================================================
# PASSWORD HASH
# ============================================================

def _hash_password(
    password: str,
) -> str:
    """
    Create a secure PBKDF2 password hash.

    Stored format:

        pbkdf2_sha256$iterations$salt$hash
    """

    salt = secrets.token_bytes(
        PASSWORD_SALT_BYTES
    )

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )

    return (
        "pbkdf2_sha256$"
        f"{PASSWORD_ITERATIONS}$"
        f"{salt.hex()}$"
        f"{password_hash.hex()}"
    )


# ============================================================
# VERIFY PASSWORD
# ============================================================

def _verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    """
    Verify a password against its stored PBKDF2 hash.
    """

    try:

        parts = stored_hash.split("$")

        if len(parts) != 4:
            return False

        algorithm = parts[0]

        iterations_text = parts[1]

        salt_hex = parts[2]

        stored_password_hash = parts[3]

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(
            iterations_text
        )

        salt = bytes.fromhex(
            salt_hex
        )

        calculated_hash = (
            hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                iterations,
            )
        )

        calculated_hash_hex = (
            calculated_hash.hex()
        )

        return hmac.compare_digest(
            calculated_hash_hex,
            stored_password_hash,
        )

    except Exception:
        return False


# ============================================================
# CREATE USER
# ============================================================

def create_user(
    username: str,
    email: str,
    password: str,
) -> tuple[bool, str]:
    """
    Create a new user.

    Parameters:
        username
        email
        password

    Returns:
        (True, success_message)

    or:

        (False, error_message)
    """

    init_auth_db()

    username = username.strip()

    email = _normalize_email(
        email
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not username:

        return (
            False,
            "Username cannot be empty.",
        )

    if len(username) < 3:

        return (
            False,
            "Username must be at least 3 characters.",
        )

    if len(username) > 50:

        return (
            False,
            "Username cannot exceed 50 characters.",
        )

    if not _valid_email(email):

        return (
            False,
            "Please enter a valid email address.",
        )

    if not password:

        return (
            False,
            "Password cannot be empty.",
        )

    if len(password) < 8:

        return (
            False,
            "Password must be at least 8 characters.",
        )

    # ========================================================
    # HASH PASSWORD
    # ========================================================

    password_hash = _hash_password(
        password
    )

    # ========================================================
    # DATABASE
    # ========================================================

    conn = _get_connection()

    try:

        # ----------------------------------------------------
        # Check email
        # ----------------------------------------------------

        existing_email = conn.execute(
            """
            SELECT id
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()

        if existing_email is not None:

            return (
                False,
                "Email is already registered.",
            )

        # ----------------------------------------------------
        # Check username
        # ----------------------------------------------------

        existing_username = conn.execute(
            """
            SELECT id
            FROM users
            WHERE username = ?
            LIMIT 1
            """,
            (username,),
        ).fetchone()

        if existing_username is not None:

            return (
                False,
                "Username already exists.",
            )

        # ----------------------------------------------------
        # Insert user
        # ----------------------------------------------------

        conn.execute(
            """
            INSERT INTO users (
                username,
                email,
                password_hash
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                email,
                password_hash,
            ),
        )

        conn.commit()

        return (
            True,
            "Account created successfully!",
        )

    except sqlite3.IntegrityError as error:

        error_text = str(
            error
        ).lower()

        if "email" in error_text:

            return (
                False,
                "Email is already registered.",
            )

        if "username" in error_text:

            return (
                False,
                "Username already exists.",
            )

        return (
        False,
        f"Database error: {error}",
        )

    except Exception as error:

        return (
            False,
            f"Could not create account: {error}",
        )

    finally:

        conn.close()


# ============================================================
# GET USER BY EMAIL
# ============================================================

def get_user_by_email(
    email: str,
):
    """
    Get user information using email.

    Returns:
        dict-like sqlite Row

    or:

        None
    """

    init_auth_db()

    email = _normalize_email(
        email
    )

    if not email:
        return None

    conn = _get_connection()

    try:

        row = conn.execute(
            """
            SELECT
                id,
                username,
                email,
                created_at,
                updated_at
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()

        return row

    finally:

        conn.close()


# ============================================================
# VERIFY USER LOGIN
# ============================================================

def verify_user(
    email: str,
    password: str,
) -> bool:
    """
    Verify login using:

        EMAIL + PASSWORD

    IMPORTANT:
        Login does NOT use username.

    Returns:

        True  -> valid credentials

        False -> invalid credentials
    """

    init_auth_db()

    # ========================================================
    # NORMALIZE EMAIL
    # ========================================================

    email = _normalize_email(
        email
    )

    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    if not email:
        return False

    if not password:
        return False

    # ========================================================
    # FIND USER BY EMAIL
    # ========================================================

    conn = _get_connection()

    try:

        row = conn.execute(
            """
            SELECT
                id,
                username,
                email,
                password_hash
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()

    except Exception:

        return False

    finally:

        conn.close()

    # ========================================================
    # USER DOES NOT EXIST
    # ========================================================

    if row is None:

        return False

    # ========================================================
    # GET STORED PASSWORD HASH
    # ========================================================

    stored_password_hash = row[
        "password_hash"
    ]

    if not stored_password_hash:

        return False

    # ========================================================
    # VERIFY PASSWORD
    # ========================================================

    return _verify_password(
        password,
        stored_password_hash,
    )


# ============================================================
# CHECK EMAIL CONFIGURATION
# ============================================================

def _check_email_config() -> tuple[bool, str]:
    """
    Check Gmail SMTP configuration.
    """

    if not EMAIL_ADDRESS:

        return (
            False,
            "EMAIL_ADDRESS is missing from your .env file.",
        )

    if not EMAIL_APP_PASSWORD:

        return (
            False,
            "EMAIL_APP_PASSWORD is missing from your .env file.",
        )

    return (
        True,
        "",
    )


# ============================================================
# GENERATE OTP
# ============================================================

def _generate_otp() -> str:
    """
    Generate a secure 6-digit OTP.
    """

    return "".join(
        str(
            secrets.randbelow(10)
        )
        for _ in range(OTP_LENGTH)
    )


# ============================================================
# HASH OTP
# ============================================================

def _hash_otp(
    otp: str,
) -> str:
    """
    Hash OTP before storing it in memory.
    """

    return hashlib.sha256(
        otp.encode("utf-8")
    ).hexdigest()


# ============================================================
# SEND OTP EMAIL
# ============================================================

def _send_otp_email(
    recipient_email: str,
    otp: str,
) -> tuple[bool, str]:
    """
    Send OTP using Gmail SMTP.
    """

    # ========================================================
    # CHECK CONFIGURATION
    # ========================================================

    configured, message = (
        _check_email_config()
    )

    if not configured:

        return (
            False,
            message,
        )

    # ========================================================
    # CREATE EMAIL
    # ========================================================

    email_message = EmailMessage()

    email_message["Subject"] = (
        "Label Lens - Email Verification OTP"
    )

    email_message["From"] = (
        EMAIL_ADDRESS
    )

    email_message["To"] = (
        recipient_email
    )

    email_message.set_content(
        f"""
Hello,

Your Label Lens email verification OTP is:

{otp}

This OTP is valid for 5 minutes.

You have a maximum of {MAX_OTP_ATTEMPTS} attempts.

If you did not request this OTP,
you can safely ignore this email.

Regards,
Label Lens Team
"""
    )

    # ========================================================
    # SEND EMAIL
    # ========================================================

    try:

        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=30,
        ) as server:

            server.ehlo()

            server.starttls()

            server.ehlo()

            server.login(
                EMAIL_ADDRESS,
                EMAIL_APP_PASSWORD,
            )

            server.send_message(
                email_message
            )

        return (
            True,
            "OTP sent successfully.",
        )

    except smtplib.SMTPAuthenticationError:

        return (
            False,
            (
                "Gmail authentication failed. "
                "Please check EMAIL_ADDRESS and "
                "EMAIL_APP_PASSWORD in your .env file."
            ),
        )

    except smtplib.SMTPException as error:

        return (
            False,
            f"Could not send email: {error}",
        )

    except Exception as error:

        return (
            False,
            f"Email sending failed: {error}",
        )


# ============================================================
# SEND EMAIL OTP
# ============================================================

def send_email_otp(
    email: str,
):
    """
    Generate and send an OTP.

    Returns:

        (
            success,
            message,
            verified_email,
            expires_at
        )
    """

    email = _normalize_email(
        email
    )

    # ========================================================
    # VALIDATE EMAIL
    # ========================================================

    if not email:

        return (
            False,
            "Email cannot be empty.",
            None,
            None,
        )

    if not _valid_email(email):

        return (
            False,
            "Please enter a valid email address.",
            None,
            None,
        )

    # ========================================================
    # CHECK EMAIL CONFIGURATION
    # ========================================================

    configured, message = (
        _check_email_config()
    )

    if not configured:

        return (
            False,
            message,
            None,
            None,
        )

    # ========================================================
    # GENERATE OTP
    # ========================================================

    otp = _generate_otp()

    # ========================================================
    # EXPIRY
    # ========================================================

    expires_at = (
        time.time()
        + OTP_EXPIRY_SECONDS
    )

    # ========================================================
    # STORE OTP HASH
    # ========================================================

    _otp_store[email] = {
        "otp_hash": _hash_otp(otp),
        "expires_at": expires_at,
        "attempts": 0,
    }

    # ========================================================
    # SEND EMAIL
    # ========================================================

    success, message = (
        _send_otp_email(
            email,
            otp,
        )
    )

    # ========================================================
    # EMAIL FAILED
    # ========================================================

    if not success:

        _otp_store.pop(
            email,
            None,
        )

        return (
            False,
            message,
            None,
            None,
        )

    # ========================================================
    # SUCCESS
    # ========================================================

    return (
        True,
        "OTP sent successfully.",
        email,
        expires_at,
    )


# ============================================================
# VERIFY EMAIL OTP
# ============================================================

def verify_email_otp(
    email: str,
    otp: str,
) -> tuple[bool, str]:
    """
    Verify an email OTP.
    """

    email = _normalize_email(
        email
    )

    otp = otp.strip()

    # ========================================================
    # CHECK EMAIL
    # ========================================================

    if not email:

        return (
            False,
            "Email is required.",
        )

    # ========================================================
    # CHECK OTP
    # ========================================================

    if not otp:

        return (
            False,
            "OTP is required.",
        )

    # ========================================================
    # FIND OTP
    # ========================================================

    otp_data = _otp_store.get(
        email
    )

    if otp_data is None:

        return (
            False,
            "No OTP found. Please request a new OTP.",
        )

    # ========================================================
    # CHECK EXPIRY
    # ========================================================

    if time.time() >= otp_data[
        "expires_at"
    ]:

        _otp_store.pop(
            email,
            None,
        )

        return (
            False,
            "OTP has expired. Please request a new OTP.",
        )

    # ========================================================
    # CHECK ATTEMPTS
    # ========================================================

    if (
        otp_data["attempts"]
        >= MAX_OTP_ATTEMPTS
    ):

        _otp_store.pop(
            email,
            None,
        )

        return (
            False,
            (
                "Too many incorrect attempts. "
                "Please request a new OTP."
            ),
        )

    # ========================================================
    # CHECK OTP FORMAT
    # ========================================================

    if not otp.isdigit():

        otp_data["attempts"] += 1

        return (
            False,
            "OTP must contain numbers only.",
        )

    if len(otp) != OTP_LENGTH:

        otp_data["attempts"] += 1

        return (
            False,
            "OTP must be exactly 6 digits.",
        )

    # ========================================================
    # HASH ENTERED OTP
    # ========================================================

    entered_hash = _hash_otp(
        otp
    )

    # ========================================================
    # COMPARE OTP
    # ========================================================

    if not hmac.compare_digest(
        entered_hash,
        otp_data["otp_hash"],
    ):

        otp_data["attempts"] += 1

        remaining_attempts = (
            MAX_OTP_ATTEMPTS
            - otp_data["attempts"]
        )

        if remaining_attempts <= 0:

            _otp_store.pop(
                email,
                None,
            )

            return (
                False,
                (
                    "Too many incorrect attempts. "
                    "Please request a new OTP."
                ),
            )

        return (
            False,
            (
                "Incorrect OTP. "
                f"{remaining_attempts} attempts remaining."
            ),
        )

    # ========================================================
    # OTP CORRECT
    # ========================================================

    _otp_store.pop(
        email,
        None,
    )

    return (
        True,
        "Email verified successfully.",
    )