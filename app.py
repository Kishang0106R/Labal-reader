"""Label Lens — product-label compliance scanner.

Flow:
    Login
    OR
    Signup → Email OTP → Verify Email → Create Account

Scanner:
    Upload → Preprocess → OCR → Compliance Check → Save → PDF Report
"""

from __future__ import annotations

import time

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from core.auth import (
    create_user,
    init_auth_db,
    verify_user,
    send_email_otp,
    verify_email_otp,
)

from core.ocr import extract_text
from core.preprocess import preprocess_for_ocr
from core.report import generate_pdf_report
from core.rules import check_compliance
from core.storage import init_db, list_scans, save_scan


# ============================================================
# ENVIRONMENT
# ============================================================

# Loads values from .env
load_dotenv()


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title="Label Lens",
    page_icon="🔍",
    layout="wide",
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

# Initialize databases once when the application starts.
init_auth_db()
init_db()


# ============================================================
# SESSION STATE
# ============================================================

def initialize_session_state() -> None:
    """Create session-state variables used by the application."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # OTP related state
    if "otp_sent" not in st.session_state:
        st.session_state.otp_sent = False

    if "otp_challenge_id" not in st.session_state:
        st.session_state.otp_challenge_id = None

    if "otp_expiry" not in st.session_state:
        st.session_state.otp_expiry = None

    if "email_verified" not in st.session_state:
        st.session_state.email_verified = False

    if "verified_email" not in st.session_state:
        st.session_state.verified_email = None


initialize_session_state()


# ============================================================
# OTP COUNTDOWN
# ============================================================

@st.fragment(run_every=1)
def otp_countdown() -> None:
    """
    Display a live OTP countdown.

    This fragment refreshes every second without refreshing
    the entire Streamlit page.
    """

    if not st.session_state.otp_sent:
        return

    expiry = st.session_state.otp_expiry

    if expiry is None:
        return

    remaining = int(expiry - time.time())

    if remaining > 0:

        minutes = remaining // 60
        seconds = remaining % 60

        st.info(
            f"OTP expires in **{minutes}:{seconds:02d}**"
        )

    else:

        st.warning(
            "OTP has expired. Please resend OTP."
        )


# ============================================================
# RESET OTP
# ============================================================

def reset_otp_state() -> None:
    """Clear all OTP-related session state."""

    st.session_state.otp_sent = False
    st.session_state.otp_challenge_id = None
    st.session_state.otp_expiry = None
    st.session_state.email_verified = False
    st.session_state.verified_email = None


# ============================================================
# LOGIN / SIGNUP UI
# ============================================================

def _login_signup_ui() -> None:
    """Display authentication UI."""

    st.title("Label Lens 🔍")
    st.caption(
        "Legal Metrology compliance scanner"
    )

    login_tab, signup_tab = st.tabs(
        ["Login", "Create account"]
    )

    # ========================================================
    # LOGIN
    # ========================================================

    with login_tab:

        st.subheader(
            "Sign in to your account"
        )

        username = st.text_input(
            "Username",
            key="login_username",
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button(
            "Login",
            type="primary",
            key="login_button",
        ):

            if not username:

                st.error(
                    "Please enter your username."
                )

            elif not password:

                st.error(
                    "Please enter your password."
                )

            elif verify_user(
                username,
                password,
            ):

                st.session_state.authenticated = True

                st.success(
                    "Login successful."
                )

                st.rerun()

            else:

                st.error(
                    "Invalid username or password."
                )

    # ========================================================
    # SIGNUP
    # ========================================================

    with signup_tab:

        st.subheader(
            "Create your account"
        )

        # ----------------------------------------------------
        # Username
        # ----------------------------------------------------

        new_username = st.text_input(
            "Username",
            key="signup_username",
        )

        # ----------------------------------------------------
        # Email
        # ----------------------------------------------------

        email = st.text_input(
            "Email address",
            key="signup_email",
            placeholder="you@example.com",
        )

        current_email = email.strip().lower()

        # ----------------------------------------------------
        # Password
        # ----------------------------------------------------

        new_password = st.text_input(
            "Password",
            type="password",
            key="signup_password",
        )

        confirm_password = st.text_input(
            "Confirm password",
            type="password",
            key="signup_confirm_password",
        )

        # ====================================================
        # SEND OTP
        # ====================================================

        if st.button(
            "Send OTP",
            key="send_otp_button",
        ):

            if not current_email:

                st.error(
                    "Please enter your email address."
                )

            else:

                with st.spinner(
                    "Sending OTP..."
                ):

                    (
                        success,
                        message,
                        challenge_id,
                        expires_at,
                    ) = send_email_otp(
                        current_email
                    )

                if success:

                    # Save Authsignal challenge ID.
                    st.session_state.otp_challenge_id = (
                        challenge_id
                    )

                    # Authsignal returns the expiry timestamp.
                    st.session_state.otp_expiry = (
                        expires_at
                    )

                    st.session_state.otp_sent = True

                    # This is a new OTP.
                    st.session_state.email_verified = False
                    st.session_state.verified_email = None

                    st.success(
                        "OTP sent successfully! "
                        "Check your email."
                    )

                else:

                    st.error(message)

        # ====================================================
        # OTP VERIFICATION SECTION
        # ====================================================

        if st.session_state.otp_sent:

            st.divider()

            st.subheader(
                "Verify your email 📧"
            )

            st.caption(
                f"Enter the 6-digit OTP sent to {current_email}"
            )

            # ------------------------------------------------
            # Live countdown
            # ------------------------------------------------

            otp_countdown()

            # ------------------------------------------------
            # OTP input
            # ------------------------------------------------

            otp = st.text_input(
                "Enter OTP",
                key="signup_otp",
                max_chars=6,
                placeholder="123456",
            )

            # ------------------------------------------------
            # Verify OTP button
            # ------------------------------------------------

            if st.button(
                "Verify OTP",
                key="verify_otp_button",
            ):

                if not otp:

                    st.error(
                        "Please enter the OTP."
                    )

                elif not otp.isdigit():

                    st.error(
                        "OTP must contain only numbers."
                    )

                elif len(otp) != 6:

                    st.error(
                        "OTP must be 6 digits."
                    )

                else:

                    # Check local expiry before calling API.
                    if (
                        st.session_state.otp_expiry
                        and time.time()
                        >= st.session_state.otp_expiry
                    ):

                        st.error(
                            "OTP has expired. "
                            "Please resend OTP."
                        )

                    else:

                        with st.spinner(
                            "Verifying OTP..."
                        ):

                            (
                                verified,
                                verify_message,
                            ) = verify_email_otp(
                                st.session_state.otp_challenge_id,
                                otp,
                            )

                        if verified:

                            st.session_state.email_verified = True

                            st.session_state.verified_email = (
                                current_email
                            )

                            st.success(
                                "Email verified successfully! ✅"
                            )

                        else:

                            st.error(
                                verify_message
                            )

            # =================================================
            # RESEND OTP
            # =================================================

            otp_expired = (
                st.session_state.otp_expiry is not None
                and time.time()
                >= st.session_state.otp_expiry
            )

            if otp_expired:

                if st.button(
                    "Resend OTP",
                    key="resend_otp_button",
                ):

                    with st.spinner(
                        "Sending new OTP..."
                    ):

                        (
                            success,
                            message,
                            challenge_id,
                            expires_at,
                        ) = send_email_otp(
                            current_email
                        )

                    if success:

                        st.session_state.otp_challenge_id = (
                            challenge_id
                        )

                        st.session_state.otp_expiry = (
                            expires_at
                        )

                        st.session_state.otp_sent = True

                        st.session_state.email_verified = False

                        st.session_state.verified_email = None

                        st.success(
                            "New OTP sent successfully!"
                        )

                        st.rerun()

                    else:

                        st.error(message)

        # ====================================================
        # VERIFIED EMAIL STATUS
        # ====================================================

        if st.session_state.email_verified:

            st.success(
                "✅ Email verified"
            )

        # ====================================================
        # CREATE ACCOUNT
        # ====================================================

        if st.button(
            "Create account",
            type="primary",
            key="signup_button",
        ):

            # ------------------------------------------------
            # Validation
            # ------------------------------------------------

            if not new_username.strip():

                st.error(
                    "Please enter a username."
                )

            elif not current_email:

                st.error(
                    "Please enter your email."
                )

            elif not st.session_state.email_verified:

                st.error(
                    "Please verify your email first."
                )

            elif (
                st.session_state.verified_email
                != current_email
            ):

                st.error(
                    "Please verify the current email address."
                )

            elif not new_password:

                st.error(
                    "Please enter a password."
                )

            elif len(new_password) < 8:

                st.error(
                    "Password must be at least 8 characters."
                )

            elif new_password != confirm_password:

                st.error(
                    "Passwords do not match."
                )

            else:

                # ------------------------------------------------
                # Create account AFTER email verification.
                # ------------------------------------------------

                ok, message = create_user(
                    new_username,
                    current_email,
                    new_password,
                )

                if ok:

                    st.success(
                        "Account created successfully! 🎉"
                    )

                    # Reset authentication/OTP state.
                    reset_otp_state()

                    # User can now log in.
                    st.info(
                        "Please switch to the Login tab."
                    )

                else:

                    st.error(message)


# ============================================================
# SCANNER UI
# ============================================================

def _scanner_ui() -> None:
    """Main OCR and compliance evaluation workflow."""

    st.title("Label Lens 🔍")

    st.caption(
        "Scan product labels for mandatory "
        "legal-metrology declarations"
    )

    # ========================================================
    # SIDEBAR
    # ========================================================

    with st.sidebar:

        st.write(
            "You are logged in."
        )

        if st.button(
            "Log out",
            key="logout_button",
        ):

            st.session_state.authenticated = False

            st.rerun()

    # ========================================================
    # PRODUCT NAME
    # ========================================================

    product_name = st.text_input(
        "Product name",
        value="Sample product",
        placeholder="e.g. Sunrise Wheat Flour 1kg",
    )

    # ========================================================
    # UPLOAD IMAGE
    # ========================================================

    uploaded_file = st.file_uploader(
        "Upload product label image",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],
    )

    if uploaded_file is None:

        st.info(
            "Upload a photo of a packaged label "
            "to begin the compliance check."
        )

        return

    # ========================================================
    # IMAGE
    # ========================================================

    try:

        image = Image.open(
            uploaded_file
        ).convert("RGB")

    except Exception:

        st.error(
            "Could not read the uploaded image."
        )

        return

    st.image(
        image,
        caption="Uploaded label",
        use_container_width=True,
    )

    # ========================================================
    # OCR + COMPLIANCE
    # ========================================================

    with st.spinner(
        "Processing label..."
    ):

        processed = preprocess_for_ocr(
            image
        )

        extracted_text = extract_text(
            processed
        )

        result = check_compliance(
            extracted_text
        )

    # ========================================================
    # OCR OUTPUT
    # ========================================================

    st.subheader(
        "Extracted text"
    )

    st.text_area(
        "OCR output",
        extracted_text
        if extracted_text
        else "No text detected.",
        height=240,
    )

    # ========================================================
    # COMPLIANCE SUMMARY
    # ========================================================

    st.subheader(
        "Compliance summary"
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Mandatory fields",
        result.total_required,
    )

    col2.metric(
        "Found",
        result.passed_required,
    )

    col3.metric(
        "Score",
        f"{result.score_pct}%",
    )

    # ========================================================
    # VERDICT
    # ========================================================

    if result.is_compliant:

        st.success(
            "✅ Verdict: COMPLIANT"
        )

    else:

        st.error(
            "❌ Verdict: NON-COMPLIANT"
        )

    # ========================================================
    # FIELD DETAILS
    # ========================================================

    st.subheader(
        "Declaration details"
    )

    st.dataframe(
        [
            {
                "Declaration": field.label,
                "Required": field.required,
                "Found": field.found,
                "Matched text": (
                    field.matched_text
                    or "-"
                ),
            }
            for field in result.fields
        ],
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # REPORT NOTES
    # ========================================================

    st.subheader(
        "Report"
    )

    notes = st.text_area(
        "Notes for report",
        "",
        placeholder="Add inspector observations...",
    )

    # ========================================================
    # SAVE SCAN
    # ========================================================

    if st.button(
        "Save scan",
        type="primary",
        key="save_scan_button",
    ):

        try:

            scan_id = save_scan(
                product_name,
                extracted_text,
                result,
            )

            st.success(
                f"Scan saved with ID {scan_id}."
            )

        except Exception as error:

            st.error(
                f"Could not save scan: {error}"
            )

    # ========================================================
    # PDF REPORT
    # ========================================================

    report_bytes = generate_pdf_report(
        product_name,
        result,
        notes,
    )

    st.download_button(
        label="Download compliance report (PDF)",
        data=report_bytes,
        file_name=(
            f"{product_name.replace(' ', '_')}"
            "_report.pdf"
        ),
        mime="application/pdf",
        key="download_report_button",
    )

    # ========================================================
    # RECENT SCANS
    # ========================================================

    st.subheader(
        "Recent scans"
    )

    scans = list_scans()

    if scans:

        st.dataframe(
            [
                {
                    "ID": row["id"],
                    "Product": row["product_name"],
                    "Score": row["score_pct"],
                    "Status": (
                        "Compliant"
                        if row["is_compliant"]
                        else "Non-compliant"
                    ),
                    "Time": row["scanned_at"],
                }
                for row in scans[:10]
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No scans saved yet."
        )

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    """Application entry point."""

    if not st.session_state.authenticated:

        _login_signup_ui()

    else:

        _scanner_ui()


if __name__ == "__main__":
    main()