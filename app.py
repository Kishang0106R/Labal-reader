
from __future__ import annotations

import time

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

from core.auth import (
    init_auth_db,
    create_user,
    verify_user,
    get_user_by_email,
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

load_dotenv()


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Label Lens",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

try:
    init_auth_db()
except Exception as e:
    st.error(f"Authentication database error: {e}")
    st.stop()

try:
    init_db()
except Exception as e:
    st.error(f"Application database error: {e}")
    st.stop()


# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

def initialize_session_state():

    defaults = {
        # ----------------------------------------------------
        # Authentication
        # ----------------------------------------------------
        "authenticated": False,
        "logged_in_email": None,
        "logged_in_username": None,

        # ----------------------------------------------------
        # Login
        # ----------------------------------------------------
        "login_email": "",
        "login_password": "",

        # ----------------------------------------------------
        # Signup
        # ----------------------------------------------------
        "signup_username": "",
        "signup_email": "",
        "signup_password": "",
        "signup_confirm_password": "",

        # ----------------------------------------------------
        # OTP
        # ----------------------------------------------------
        "otp_sent": False,
        "otp_expiry": None,
        "email_verified": False,
        "verified_email": None,
        "signup_otp": "",

        # ----------------------------------------------------
        # Scanner
        # ----------------------------------------------------
        "last_result": None,
        "last_extracted_text": "",
        "last_product_name": "",

        # ----------------------------------------------------
        # Navigation
        # ----------------------------------------------------
        "current_page": "🏠 Home",

        # ----------------------------------------------------
        # Logout flag
        # ----------------------------------------------------
        "logout_requested": False,
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def normalize_email(email: str) -> str:
    return email.strip().lower()


# ============================================================
# RESET OTP
# ============================================================

def reset_otp_state():

    st.session_state.otp_sent = False
    st.session_state.otp_expiry = None
    st.session_state.email_verified = False
    st.session_state.verified_email = None
    st.session_state.signup_otp = ""


# ============================================================
# LOGIN SUCCESS CALLBACK
# ============================================================

def perform_login(email: str, password: str):

    email = normalize_email(email)

    if not email:
        st.session_state.login_error = (
            "Please enter your email."
        )
        return

    if "@" not in email:
        st.session_state.login_error = (
            "Please enter a valid email address."
        )
        return

    if not password:
        st.session_state.login_error = (
            "Please enter your password."
        )
        return

    try:

        valid = verify_user(
            email,
            password,
        )

    except Exception as e:

        st.session_state.login_error = (
            f"Login error: {e}"
        )

        return

    # ========================================================
    # LOGIN SUCCESS
    # ========================================================

    if valid:

        try:

            user = get_user_by_email(
                email
            )

        except Exception:

            user = None

        st.session_state.authenticated = True

        st.session_state.logged_in_email = email

        username = None

        if user is not None:

            try:

                username = user["username"]

            except Exception:

                try:
                    username = user.get(
                        "username"
                    )
                except Exception:
                    username = None

        st.session_state.logged_in_username = (
            username
        )

        # ----------------------------------------------------
        # Clear login error
        # ----------------------------------------------------

        st.session_state.pop(
            "login_error",
            None,
        )

        # ----------------------------------------------------
        # Clear password safely
        #
        # IMPORTANT:
        # login_password is a widget key.
        # We do NOT modify it here.
        # ----------------------------------------------------

        st.session_state.login_password_clear = True

        # ----------------------------------------------------
        # Dashboard
        # ----------------------------------------------------

        st.session_state.current_page = (
            "🏠 Home"
        )

    else:

        st.session_state.login_error = (
            "Invalid email or password."
        )


# ============================================================
# LOGOUT CALLBACK
# ============================================================

def perform_logout():

    # --------------------------------------------------------
    # Authentication state
    # --------------------------------------------------------

    st.session_state.authenticated = False

    st.session_state.logged_in_email = None

    st.session_state.logged_in_username = None

    # --------------------------------------------------------
    # OTP
    # --------------------------------------------------------

    reset_otp_state()

    # --------------------------------------------------------
    # Scanner
    # --------------------------------------------------------

    st.session_state.last_result = None

    st.session_state.last_extracted_text = ""

    st.session_state.last_product_name = ""

    # --------------------------------------------------------
    # Navigation
    #
    # DO NOT modify a radio widget key.
    # We use a separate variable.
    # --------------------------------------------------------

    st.session_state.current_page = (
        "🏠 Home"
    )

    # --------------------------------------------------------
    # Login fields
    #
    # These will be cleared on the next unauthenticated
    # render using widget-safe logic.
    # --------------------------------------------------------

    st.session_state.login_email_clear = True

    st.session_state.login_password_clear = True


# ============================================================
# OTP COUNTDOWN
# ============================================================

@st.fragment(run_every=1)
def otp_countdown():

    if not st.session_state.otp_sent:
        return

    expiry = st.session_state.otp_expiry

    if expiry is None:
        return

    remaining = int(
        expiry - time.time()
    )

    if remaining > 0:

        minutes = remaining // 60

        seconds = remaining % 60

        st.info(
            f"⏳ OTP expires in "
            f"**{minutes}:{seconds:02d}**"
        )

    else:

        st.warning(
            "⏰ OTP has expired. "
            "Please resend OTP."
        )


# ============================================================
# AUTHENTICATION PAGE
# ============================================================

def authentication_page():

    # ========================================================
    # SAFE CLEAR LOGIN FIELDS
    #
    # We cannot modify a widget's state after the widget
    # has been instantiated.
    #
    # Therefore, only delete the keys BEFORE creating widgets.
    # ========================================================

    if st.session_state.pop(
        "login_email_clear",
        False,
    ):

        st.session_state.pop(
            "login_email",
            None,
        )

    if st.session_state.pop(
        "login_password_clear",
        False,
    ):

        st.session_state.pop(
            "login_password",
            None,
        )

    # ========================================================
    # HEADER
    # ========================================================

    st.title(
        "Label Lens 🔍"
    )

    st.caption(
        "Legal Metrology Product Label Compliance Scanner"
    )

    st.divider()

    # ========================================================
    # TABS
    # ========================================================

    login_tab, signup_tab = st.tabs(
        [
            "🔐 Login",
            "📝 Create Account",
        ]
    )

    # ========================================================
    # LOGIN TAB
    # ========================================================

    with login_tab:

        st.subheader(
            "Welcome back 👋"
        )

        st.write(
            "Login using your email address and password."
        )

        # ----------------------------------------------------
        # Email
        # ----------------------------------------------------

        login_email = st.text_input(
            "Email",
            key="login_email",
            placeholder="Enter your email",
        )

        # ----------------------------------------------------
        # Password
        # ----------------------------------------------------

        login_password = st.text_input(
            "Password",
            type="password",
            key="login_password",
            placeholder="Enter your password",
        )

        st.write("")

        # ----------------------------------------------------
        # Login
        # ----------------------------------------------------

        login_clicked = st.button(
            "🔐 Login",
            type="primary",
            use_container_width=True,
            key="login_button",
        )

        if login_clicked:

            with st.spinner(
                "Checking login details..."
            ):

                perform_login(
                    login_email,
                    login_password,
                )

            if st.session_state.authenticated:

                st.success(
                    "Login successful! 🎉"
                )

                time.sleep(0.5)

                st.rerun()

            else:

                error = st.session_state.get(
                    "login_error"
                )

                if error:

                    st.error(error)

    # ========================================================
    # SIGNUP TAB
    # ========================================================

    with signup_tab:

        st.subheader(
            "Create your account"
        )

        st.caption(
            "Verify your email before creating your account."
        )

        # ====================================================
        # USERNAME
        # ====================================================

        new_username = st.text_input(
            "Username",
            key="signup_username",
            placeholder="Enter your username",
        )

        # ====================================================
        # EMAIL
        # ====================================================

        new_email = st.text_input(
            "Email",
            key="signup_email",
            placeholder="Enter your email",
        )

        current_email = normalize_email(
            new_email
        )

        # ====================================================
        # PASSWORD
        # ====================================================

        new_password = st.text_input(
            "Password",
            type="password",
            key="signup_password",
            placeholder="Minimum 8 characters",
        )

        # ====================================================
        # CONFIRM PASSWORD
        # ====================================================

        confirm_password = st.text_input(
            "Confirm Password",
            type="password",
            key="signup_confirm_password",
            placeholder="Enter password again",
        )

        st.divider()

        # ====================================================
        # EMAIL VERIFICATION
        # ====================================================

        st.subheader(
            "📧 Email Verification"
        )

        # ====================================================
        # NOT VERIFIED
        # ====================================================

        if not st.session_state.email_verified:

            # ------------------------------------------------
            # SEND OTP
            # ------------------------------------------------

            if st.button(
                "📨 Send OTP",
                use_container_width=True,
                key="send_otp_button",
            ):

                if not current_email:

                    st.error(
                        "Please enter your email."
                    )

                elif "@" not in current_email:

                    st.error(
                        "Please enter a valid email address."
                    )

                else:

                    with st.spinner(
                        "Sending OTP..."
                    ):

                        try:

                            (
                                success,
                                message,
                                verified_email,
                                expires_at,
                            ) = send_email_otp(
                                current_email
                            )

                        except Exception as e:

                            success = False

                            message = (
                                f"Could not send OTP: {e}"
                            )

                            verified_email = None

                            expires_at = None

                    if success:

                        st.session_state.otp_sent = True

                        st.session_state.otp_expiry = (
                            expires_at
                        )

                        st.session_state.email_verified = (
                            False
                        )

                        st.session_state.verified_email = (
                            None
                        )

                        st.session_state.signup_otp = ""

                        st.success(
                            "OTP sent successfully! 📧"
                        )

                        st.rerun()

                    else:

                        st.error(
                            message
                        )

            # ------------------------------------------------
            # OTP FORM
            # ------------------------------------------------

            if st.session_state.otp_sent:

                st.divider()

                st.markdown(
                    "### Enter OTP"
                )

                st.caption(
                    f"Enter the 6-digit OTP sent to "
                    f"**{current_email}**"
                )

                otp_countdown()

                otp = st.text_input(
                    "6-digit OTP",
                    key="signup_otp",
                    max_chars=6,
                    placeholder="123456",
                )

                if st.button(
                    "✅ Verify OTP",
                    type="primary",
                    use_container_width=True,
                    key="verify_otp_button",
                ):

                    if not otp:

                        st.error(
                            "Please enter the OTP."
                        )

                    elif not otp.isdigit():

                        st.error(
                            "OTP must contain numbers only."
                        )

                    elif len(otp) != 6:

                        st.error(
                            "OTP must be exactly 6 digits."
                        )

                    else:

                        with st.spinner(
                            "Verifying OTP..."
                        ):

                            try:

                                (
                                    verified,
                                    verify_message,
                                ) = verify_email_otp(
                                    current_email,
                                    otp,
                                )

                            except Exception as e:

                                verified = False

                                verify_message = (
                                    f"OTP verification error: {e}"
                                )

                        if verified:

                            st.session_state.email_verified = (
                                True
                            )

                            st.session_state.verified_email = (
                                current_email
                            )

                            st.session_state.otp_sent = (
                                False
                            )

                            st.session_state.otp_expiry = (
                                None
                            )

                            st.session_state.signup_otp = ""

                            st.success(
                                "Email verified successfully! ✅"
                            )

                            st.rerun()

                        else:

                            st.error(
                                verify_message
                            )

                # ------------------------------------------------
                # RESEND
                # ------------------------------------------------

                expired = (
                    st.session_state.otp_expiry
                    is not None
                    and time.time()
                    >= st.session_state.otp_expiry
                )

                if expired:

                    if st.button(
                        "🔄 Resend OTP",
                        use_container_width=True,
                        key="resend_otp_button",
                    ):

                        with st.spinner(
                            "Sending new OTP..."
                        ):

                            try:

                                (
                                    success,
                                    message,
                                    verified_email,
                                    expires_at,
                                ) = send_email_otp(
                                    current_email
                                )

                            except Exception as e:

                                success = False

                                message = (
                                    f"Could not send OTP: {e}"
                                )

                                expires_at = None

                        if success:

                            st.session_state.otp_sent = True

                            st.session_state.otp_expiry = (
                                expires_at
                            )

                            st.session_state.signup_otp = ""

                            st.success(
                                "New OTP sent successfully! 📧"
                            )

                            st.rerun()

                        else:

                            st.error(message)

        # ====================================================
        # VERIFIED
        # ====================================================

        if st.session_state.email_verified:

            verified_email = (
                st.session_state.verified_email
            )

            st.success(
                f"✅ Email verified: {verified_email}"
            )

            st.divider()

            st.subheader(
                "Create your account"
            )

            # =================================================
            # CREATE ACCOUNT
            # =================================================

            if st.button(
                "🚀 Create Account",
                type="primary",
                use_container_width=True,
                key="create_account_button",
            ):

                # --------------------------------------------
                # Username
                # --------------------------------------------

                if not new_username.strip():

                    st.error(
                        "Please enter a username."
                    )

                # --------------------------------------------
                # Verified email
                # --------------------------------------------

                elif (
                    current_email
                    != st.session_state.verified_email
                ):

                    st.error(
                        "The verified email does not match "
                        "the current email."
                    )

                    reset_otp_state()

                    st.rerun()

                # --------------------------------------------
                # Password
                # --------------------------------------------

                elif not new_password:

                    st.error(
                        "Please enter a password."
                    )

                elif len(new_password) < 8:

                    st.error(
                        "Password must be at least 8 characters."
                    )

                # --------------------------------------------
                # Confirm password
                # --------------------------------------------

                elif new_password != confirm_password:

                    st.error(
                        "Passwords do not match."
                    )

                # --------------------------------------------
                # Create user
                # --------------------------------------------

                else:

                    with st.spinner(
                        "Creating your account..."
                    ):

                        try:

                            (
                                success,
                                message,
                            ) = create_user(
                                new_username.strip(),
                                current_email,
                                new_password,
                            )

                        except Exception as e:

                            success = False

                            message = (
                                f"Could not create account: {e}"
                            )

                    if success:

                        # ==================================
                        # AUTOMATIC LOGIN
                        # ==================================

                        st.session_state.authenticated = True

                        st.session_state.logged_in_email = (
                            current_email
                        )

                        st.session_state.logged_in_username = (
                            new_username.strip()
                        )

                        # ==================================
                        # Reset OTP
                        # ==================================

                        reset_otp_state()

                        # ==================================
                        # DO NOT MODIFY WIDGET KEYS HERE
                        #
                        # Just delete them.
                        # ==================================

                        st.session_state.pop(
                            "signup_username",
                            None,
                        )

                        st.session_state.pop(
                            "signup_email",
                            None,
                        )

                        st.session_state.pop(
                            "signup_password",
                            None,
                        )

                        st.session_state.pop(
                            "signup_confirm_password",
                            None,
                        )

                        st.session_state.current_page = (
                            "🏠 Home"
                        )

                        st.success(
                            "🎉 Account created successfully!"
                        )

                        time.sleep(0.7)

                        st.rerun()

                    else:

                        st.error(
                            message
                        )


# ============================================================
# DASHBOARD
# ============================================================

def dashboard():

    # ========================================================
    # SIDEBAR
    # ========================================================

    with st.sidebar:

        st.title(
            "Label Lens 🔍"
        )

        st.success(
            "Logged in ✅"
        )

        if st.session_state.logged_in_username:

            st.write(
                f"👤 **{st.session_state.logged_in_username}**"
            )

        if st.session_state.logged_in_email:

            st.caption(
                st.session_state.logged_in_email
            )

        st.divider()

        # ====================================================
        # NAVIGATION
        # ====================================================

        selected_page = st.radio(
            "Navigation",
            [
                "🏠 Home",
                "🔍 Scanner",
                "📋 Scan History",
            ],
            index=[
                "🏠 Home",
                "🔍 Scanner",
                "📋 Scan History",
            ].index(
                st.session_state.current_page
                if st.session_state.current_page
                in [
                    "🏠 Home",
                    "🔍 Scanner",
                    "📋 Scan History",
                ]
                else "🏠 Home"
            ),
            key="navigation_radio",
        )

        # ----------------------------------------------------
        # Store selected page in separate state variable
        # ----------------------------------------------------

        st.session_state.current_page = (
            selected_page
        )

        st.divider()

        # ====================================================
        # LOGOUT
        # ====================================================

        if st.button(
            "🚪 Logout",
            use_container_width=True,
            key="logout_button",
        ):

            perform_logout()

            st.rerun()

    # ========================================================
    # PAGE
    # ========================================================

    if (
        st.session_state.current_page
        == "🏠 Home"
    ):

        home_page()

    elif (
        st.session_state.current_page
        == "🔍 Scanner"
    ):

        scanner_page()

    elif (
        st.session_state.current_page
        == "📋 Scan History"
    ):

        history_page()


# ============================================================
# HOME PAGE
# ============================================================

def home_page():

    st.title(
        "Welcome to Label Lens 👋"
    )

    username = (
        st.session_state.logged_in_username
        or "User"
    )

    st.subheader(
        f"Hello, {username}! 🎉"
    )

    st.write(
        """
        Label Lens helps you scan product labels,
        extract important declarations using OCR,
        and check them against compliance requirements.
        """
    )

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "📦 Product Scanner",
            "Available",
        )

    with col2:

        st.metric(
            "📧 Email Verification",
            "Active",
        )

    with col3:

        st.metric(
            "📄 PDF Reports",
            "Available",
        )

    st.divider()

    st.info(
        "💡 Select **Scanner** from the sidebar "
        "to scan a product label."
    )


# ============================================================
# SCANNER PAGE
# ============================================================

def scanner_page():

    st.title(
        "🔍 Product Label Scanner"
    )

    st.caption(
        "Upload a product label and check compliance."
    )

    # ========================================================
    # PRODUCT NAME
    # ========================================================

    product_name = st.text_input(
        "Product Name",
        placeholder="e.g. Sunrise Wheat Flour 1kg",
        key="product_name",
    )

    # ========================================================
    # IMAGE
    # ========================================================

    uploaded_file = st.file_uploader(
        "Upload Product Label",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],
        key="label_uploader",
    )

    if uploaded_file is None:

        st.info(
            "📷 Upload a product label image to begin."
        )

        return

    # ========================================================
    # OPEN IMAGE
    # ========================================================

    try:

        image = Image.open(
            uploaded_file
        ).convert("RGB")

    except Exception as e:

        st.error(
            f"Could not open image: {e}"
        )

        return

    # ========================================================
    # PREVIEW
    # ========================================================

    st.subheader(
        "Uploaded Label"
    )

    st.image(
        image,
        caption="Product Label",
        use_container_width=True,
    )

    # ========================================================
    # SCAN
    # ========================================================

    if st.button(
        "🔍 Scan Label",
        type="primary",
        use_container_width=True,
        key="scan_label_button",
    ):

        # ----------------------------------------------------
        # PREPROCESS
        # ----------------------------------------------------

        with st.spinner(
            "Processing image..."
        ):

            try:

                processed = preprocess_for_ocr(
                    image
                )

            except Exception as e:

                st.error(
                    f"Image preprocessing failed: {e}"
                )

                return

        # ----------------------------------------------------
        # OCR
        # ----------------------------------------------------

        with st.spinner(
            "Extracting text..."
        ):

            try:

                extracted_text = extract_text(
                    processed
                )

            except Exception as e:

                st.error(
                    f"OCR failed: {e}"
                )

                return

        # ----------------------------------------------------
        # COMPLIANCE
        # ----------------------------------------------------

        with st.spinner(
            "Checking compliance..."
        ):

            try:

                result = check_compliance(
                    extracted_text
                )

            except Exception as e:

                st.error(
                    f"Compliance check failed: {e}"
                )

                return

        # ----------------------------------------------------
        # SAVE SESSION RESULT
        # ----------------------------------------------------

        st.session_state.last_result = result

        st.session_state.last_extracted_text = (
            extracted_text
        )

        st.session_state.last_product_name = (
            product_name
        )

        st.success(
            "Scan completed successfully! ✅"
        )

    # ========================================================
    # RESULT
    # ========================================================

    result = st.session_state.last_result

    if result is None:
        return

    extracted_text = (
        st.session_state.last_extracted_text
    )

    current_product_name = (
        st.session_state.last_product_name
    )

    # ========================================================
    # OCR TEXT
    # ========================================================

    st.divider()

    st.subheader(
        "📝 Extracted Text"
    )

    st.text_area(
        "OCR Result",
        extracted_text
        if extracted_text
        else "No text detected.",
        height=250,
        disabled=True,
        key="ocr_result",
    )

    # ========================================================
    # COMPLIANCE
    # ========================================================

    st.subheader(
        "📊 Compliance Summary"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Mandatory Fields",
            result.total_required,
        )

    with col2:

        st.metric(
            "Fields Found",
            result.passed_required,
        )

    with col3:

        st.metric(
            "Compliance Score",
            f"{result.score_pct}%",
        )

    # ========================================================
    # VERDICT
    # ========================================================

    if result.is_compliant:

        st.success(
            "✅ VERDICT: COMPLIANT"
        )

    else:

        st.error(
            "❌ VERDICT: NON-COMPLIANT"
        )

    # ========================================================
    # FIELD DETAILS
    # ========================================================

    st.subheader(
        "📋 Declaration Details"
    )

    rows = []

    for field in result.fields:

        rows.append(
            {
                "Declaration": field.label,
                "Required": (
                    "Yes"
                    if field.required
                    else "No"
                ),
                "Found": (
                    "✅ Yes"
                    if field.found
                    else "❌ No"
                ),
                "Matched Text": (
                    field.matched_text
                    if field.matched_text
                    else "-"
                ),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # NOTES
    # ========================================================

    st.subheader(
        "📝 Report Notes"
    )

    notes = st.text_area(
        "Inspector Notes",
        placeholder="Add observations...",
        key="report_notes",
    )

    # ========================================================
    # SAVE / PDF
    # ========================================================

    col1, col2 = st.columns(2)

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    with col1:

        if st.button(
            "💾 Save Scan",
            use_container_width=True,
            key="save_scan_button",
        ):

            try:

                scan_id = save_scan(
                    current_product_name,
                    extracted_text,
                    result,
                )

                st.success(
                    f"Scan saved successfully! ID: {scan_id}"
                )

            except Exception as e:

                st.error(
                    f"Could not save scan: {e}"
                )

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    with col2:

        try:

            report_bytes = generate_pdf_report(
                current_product_name,
                result,
                notes,
            )

            safe_name = (
                current_product_name.strip()
                .replace(" ", "_")
                .replace("/", "_")
                .replace("\\", "_")
            )

            if not safe_name:

                safe_name = "product"

            st.download_button(
                "📄 Download PDF Report",
                data=report_bytes,
                file_name=(
                    f"{safe_name}_report.pdf"
                ),
                mime="application/pdf",
                use_container_width=True,
                key="download_pdf_button",
            )

        except Exception as e:

            st.error(
                f"Could not generate PDF: {e}"
            )


# ============================================================
# HISTORY PAGE
# ============================================================

def history_page():

    st.title(
        "📋 Scan History"
    )

    st.caption(
        "Previously saved product scans."
    )

    try:

        scans = list_scans()

    except Exception as e:

        st.error(
            f"Could not load scan history: {e}"
        )

        return

    if not scans:

        st.info(
            "No scans have been saved yet."
        )

        return

    rows = []

    for row in scans:

        rows.append(
            {
                "ID": row["id"],
                "Product": row["product_name"],
                "Score": f"{row['score_pct']}%",
                "Status": (
                    "✅ Compliant"
                    if row["is_compliant"]
                    else "❌ Non-compliant"
                ),
                "Scanned At": row["scanned_at"],
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if st.session_state.authenticated:

        dashboard()

    else:

        authentication_page()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()