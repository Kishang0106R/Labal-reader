"""
PDF compliance report generation.

Takes a ComplianceResult (from core.rules) and a product name, and
produces a downloadable PDF summary — pass/fail per declaration,
overall verdict, and timestamp.
"""

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from core.rules import ComplianceResult


def _pdf_text(value: str) -> str:
    """Keep dynamic text encodable by fpdf2's built-in Helvetica font."""
    return value.encode("latin-1", errors="replace").decode("latin-1")


def generate_pdf_report(product_name: str, result: ComplianceResult, notes: str = "") -> bytes:
    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Legal Metrology Compliance Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0,
        6,
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(4)

    # Product + verdict
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_text(f"Product: {product_name}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    verdict = "COMPLIANT" if result.is_compliant else "NON-COMPLIANT"
    pdf.set_font("Helvetica", "B", 12)
    if result.is_compliant:
        pdf.set_text_color(20, 120, 20)
    else:
        pdf.set_text_color(180, 30, 30)
    pdf.cell(
        0,
        8,
        f"Verdict: {verdict}  ({result.score_pct}% of mandatory fields present)",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Field-by-field table
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(70, 8, "Declaration", border=1)
    pdf.cell(30, 8, "Required", border=1)
    pdf.cell(30, 8, "Status", border=1)
    pdf.cell(60, 8, "Detected text", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    for f in result.fields:
        pdf.cell(70, 8, _pdf_text(f.label[:38]), border=1)
        pdf.cell(30, 8, "Yes" if f.required else "No", border=1)
        status = "Present" if f.found else "MISSING"
        if f.found:
            pdf.set_text_color(20, 120, 20)
        else:
            pdf.set_text_color(180, 30, 30)
        pdf.cell(30, 8, status, border=1)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(
            60,
            8,
            _pdf_text((f.matched_text or "-")[:32]),
            border=1,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    pdf.set_x(pdf.l_margin)
    pdf.ln(6)

    # Missing summary
    if result.missing_required:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(180, 30, 30)
        pdf.cell(0, 8, "Violations found:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        for f in result.missing_required:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, _pdf_text(f"- {f.label}: {f.description}"))
        pdf.set_text_color(0, 0, 0)

    if notes:
        pdf.set_x(pdf.l_margin)
        pdf.ln(4)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "I", 10)
        pdf.multi_cell(0, 6, _pdf_text(f"Notes: {notes}"))

    # fpdf2 returns a bytearray from output(); normalize to bytes
    return bytes(pdf.output())
