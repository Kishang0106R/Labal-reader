"""
MetroVigil AI — Streamlit prototype

Legal Metrology (Packaged Commodities) Rules, 2011 compliance scanner.
Flow: Upload -> Extract (OCR) -> Validate (rules) -> Report (PDF) -> Dashboard (history)
"""

import streamlit as st
from PIL import Image

from core.auth import create_user, init_auth_db, verify_user
from core.ocr import extract_text
from core.preprocess import preprocess_for_ocr
from core.report import generate_pdf_report
from core.rules import check_compliance
from core.storage import init_db, list_scans, save_scan

st.set_page_config(page_title="MetroVigil AI", page_icon=":shield:", layout="wide")
init_db()
init_auth_db()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None

# ----------------------------------------------------------------------
# Login / Sign Up gate — nothing below renders until logged_in is True
# ----------------------------------------------------------------------
if not st.session_state.logged_in:
    st.title("MetroVigil AI")
    st.caption("Legal Metrology (Packaged Commodities) Rules, 2011 — compliance scanner")

    tab_signin, tab_signup = st.tabs(["Sign In", "Sign Up"])

    with tab_signin:
        st.subheader("Sign in to your account")
        si_username = st.text_input("Username", key="signin_username")
        si_password = st.text_input("Password", type="password", key="signin_password")
        if st.button("Sign In", type="primary"):
            if verify_user(si_username, si_password):
                st.session_state.logged_in = True
                st.session_state.username = si_username.strip()
                st.rerun()
            else:
                st.error("Incorrect username or password.")

    with tab_signup:
        st.subheader("Create an account")
        su_username = st.text_input("Choose a username", key="signup_username")
        su_password = st.text_input("Choose a password", type="password", key="signup_password")
        su_password_confirm = st.text_input(
            "Confirm password", type="password", key="signup_password_confirm"
        )
        if st.button("Sign Up", type="primary"):
            if su_password != su_password_confirm:
                st.error("Passwords do not match.")
            else:
                success, message = create_user(su_username, su_password)
                if success:
                    st.success(message + " Switch to the Sign In tab to log in.")
                else:
                    st.error(message)

    st.stop()  # nothing past this point renders until the user is logged in

# ----------------------------------------------------------------------
# Logged in — show the app
# ----------------------------------------------------------------------
with st.sidebar:
    st.write(f"Signed in as **{st.session_state.username}**")
    if st.button("Log out"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()

st.title("MetroVigil AI")
st.caption("Legal Metrology (Packaged Commodities) Rules, 2011 — compliance scanner")

tab_scan, tab_dashboard = st.tabs(["Scan a product", "Dashboard & history"])

# ----------------------------------------------------------------------
# TAB 1: Scan a product (Upload -> Extract -> Validate -> Report)
# ----------------------------------------------------------------------
with tab_scan:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("1. Upload")
        product_name = st.text_input("Product name", placeholder="e.g. Sunrise Wheat Flour 1kg")
        uploaded_file = st.file_uploader(
            "Upload a photo of the product label", type=["jpg", "jpeg", "png"]
        )

        image = None
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Original image", use_container_width=True)

    with col_right:
        if image is not None:
            st.subheader("2. Extract")
            with st.spinner("Preprocessing image..."):
                cleaned = preprocess_for_ocr(image)
            st.image(cleaned, caption="Preprocessed for OCR", use_container_width=True)

            with st.spinner("Running OCR..."):
                extracted_text = extract_text(cleaned)

            with st.expander("View extracted text"):
                st.text(extracted_text if extracted_text.strip() else "(no text detected)")

    if image is not None:
        st.divider()
        st.subheader("3. Validate")

        if not product_name:
            st.warning("Enter a product name above before checking compliance.")
        else:
            result = check_compliance(extracted_text)

            m1, m2, m3 = st.columns(3)
            m1.metric("Compliance score", f"{result.score_pct}%")
            m2.metric("Fields found", f"{result.passed_required}/{result.total_required}")
            m3.metric("Verdict", "COMPLIANT" if result.is_compliant else "NON-COMPLIANT")

            for f in result.fields:
                icon = ":white_check_mark:" if f.found else (":x:" if f.required else ":heavy_minus_sign:")
                label = f"{icon} **{f.label}**" + (" *(required)*" if f.required else " *(optional)*")
                st.markdown(label)
                if f.found:
                    st.caption(f"Detected: \u201c{f.matched_text}\u201d")
                else:
                    st.caption(f.description)

            st.divider()
            st.subheader("4. Report")

            notes = st.text_area("Inspector notes (optional)", placeholder="Any additional observations...")

            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button("Save scan to repository", type="primary"):
                    save_scan(product_name, extracted_text, result)
                    st.success("Scan saved. See it in the Dashboard tab.")

            pdf_bytes = generate_pdf_report(product_name, result, notes)
            st.download_button(
                "Download PDF report",
                data=pdf_bytes,
                file_name=f"{product_name.replace(' ', '_')}_compliance_report.pdf",
                mime="application/pdf",
            )

# ----------------------------------------------------------------------
# TAB 2: Dashboard & history (Repository + search)
# ----------------------------------------------------------------------
with tab_dashboard:
    st.subheader("Scan repository")

    search_term = st.text_input("Search by product name", key="search_box")
    scans = list_scans(search=search_term if search_term else None)

    if not scans:
        st.info("No scans yet. Run a scan in the first tab to see it appear here.")
    else:
        total = len(scans)
        compliant = sum(1 for s in scans if s["is_compliant"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Total scans", total)
        c2.metric("Compliant", compliant)
        c3.metric("Non-compliant", total - compliant)

        st.divider()

        for s in scans:
            status = "COMPLIANT" if s["is_compliant"] else "NON-COMPLIANT"
            with st.expander(f"{s['product_name']} — {status} ({s['score_pct']}%) — {s['scanned_at']}"):
                st.write(f"Scan ID: {s['id']}")
                st.write(f"Score: {s['score_pct']}%")
                if s["extracted_text"]:
                    st.caption("Extracted text:")
                    st.text(s["extracted_text"][:500])
