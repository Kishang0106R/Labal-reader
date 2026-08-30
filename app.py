"""Label Lens — product-label compliance scanner.

This file boots the Streamlit app and wires together the existing OCR,
preprocessing, rules, storage, and report modules.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from core.auth import create_user, init_auth_db, verify_user
from core.ocr import extract_text
from core.preprocess import preprocess_for_ocr
from core.report import generate_pdf_report
from core.rules import check_compliance
from core.storage import init_db, list_scans, save_scan

load_dotenv()


st.set_page_config(page_title="Label Lens", page_icon="📦", layout="wide")


def _login_signup_ui() -> None:
    """Display auth UI and gate access to the scanner."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return

    st.title("Label Lens")
    st.caption("Legal Metrology compliance scanner")

    login_tab, signup_tab = st.tabs(["Login", "Create account"])

    with login_tab:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_button"):
            if verify_user(username, password):
                st.session_state.authenticated = True
                st.success("Login successful.")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with signup_tab:
        new_username = st.text_input("Username", key="signup_username")
        email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Create account", key="signup_button"):
            ok, message = create_user(new_username, email, new_password)
            if ok:
                st.session_state.authenticated = True
                st.success(message)
                st.rerun()
            else:
                st.error(message)


def _scanner_ui() -> None:
    """Main OCR and compliance evaluation workflow."""
    st.title("Label Lens")
    st.caption("Scan product labels for mandatory legal-metrology declarations")

    if st.sidebar.button("Log out"):
        st.session_state.authenticated = False
        st.rerun()

    init_auth_db()
    init_db()

    product_name = st.text_input("Product name", value="Sample product")
    uploaded_file = st.file_uploader("Upload product label image", type=["png", "jpg", "jpeg", "webp"])

    if uploaded_file is None:
        st.info("Upload a photo of a packaged label to begin the compliance check.")
        st.stop()

    image = Image.open(uploaded_file).convert("RGB")
    st.image(image, caption="Uploaded label", use_container_width=True)

    with st.spinner("Processing label..."):
        processed = preprocess_for_ocr(image)
        extracted_text = extract_text(processed)
        result = check_compliance(extracted_text)

    st.subheader("Extracted text")
    st.text_area("OCR output", extracted_text or "No text detected.", height=240)

    st.subheader("Compliance summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Mandatory fields", result.total_required)
    col2.metric("Found", result.passed_required)
    col3.metric("Score", f"{result.score_pct}%")

    status_color = "green" if result.is_compliant else "red"
    st.markdown(f"<p style='color:{status_color}; font-weight:bold; font-size:1.1rem;'>Verdict: {'COMPLIANT' if result.is_compliant else 'NON-COMPLIANT'}</p>", unsafe_allow_html=True)

    st.dataframe(
        [{
            "Declaration": field.label,
            "Required": field.required,
            "Found": field.found,
            "Matched text": field.matched_text or "-",
        } for field in result.fields],
        use_container_width=True,
        hide_index=True,
    )

    notes = st.text_area("Notes for report", "")
    if st.button("Save scan"):
        scan_id = save_scan(product_name, extracted_text, result)
        st.success(f"Scan saved with ID {scan_id}.")

    report_bytes = generate_pdf_report(product_name, result, notes)
    st.download_button(
        label="Download compliance report (PDF)",
        data=report_bytes,
        file_name=f"{product_name.replace(' ', '_')}_report.pdf",
        mime="application/pdf",
    )

    st.subheader("Recent scans")
    scans = list_scans()
    if scans:
        st.dataframe(
            [
                {
                    "ID": row["id"],
                    "Product": row["product_name"],
                    "Score": row["score_pct"],
                    "Status": "Compliant" if row["is_compliant"] else "Non-compliant",
                    "Time": row["scanned_at"],
                }
                for row in scans[:10]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No scans saved yet.")


def main() -> None:
    """Entry point for the Streamlit app."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        _login_signup_ui()
    else:
        _scanner_ui()


if __name__ == "__main__":
    main()