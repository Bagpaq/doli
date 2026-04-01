"""
PDF invoice generator for restaurant clients.

Produces a clean, branded PDF invoice using fpdf2.
Install: pip install fpdf2
"""
import os
from datetime import datetime
from typing import Optional

from .models import Invoice


def _currency(amount: float, symbol: str = "$") -> str:
    return f"{symbol}{amount:,.2f}"


def generate_pdf(
    invoice: Invoice,
    output_path: Optional[str] = None,
) -> str:
    """
    Render an Invoice to a PDF file.

    Args:
        invoice:     The Invoice to render.
        output_path: File path for the output PDF.
                     Defaults to ./<invoice_number>.pdf

    Returns:
        Absolute path to the generated PDF file.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError(
            "fpdf2 is required for PDF generation. "
            "Install it with: pip install fpdf2"
        )

    if output_path is None:
        output_path = f"{invoice.invoice_number}.pdf"

    r = invoice.restaurant
    c = invoice.customer
    currency_symbol = "$" if r.currency == "USD" else r.currency

    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Header ────────────────────────────────────────────────────────────
    # Restaurant logo (optional)
    if r.logo_path and os.path.exists(r.logo_path):
        pdf.image(r.logo_path, x=15, y=15, w=40)
        pdf.set_y(50)
    else:
        pdf.set_y(15)

    # Restaurant name
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(0, 10, r.name, ln=True)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5, f"{r.address}, {r.city}, {r.country}")
    pdf.cell(0, 5, f"Tel: {r.phone}  |  {r.email}", ln=True)
    pdf.cell(0, 5, f"Tax ID: {r.tax_id}", ln=True)

    # ── Title bar ─────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_fill_color(30, 30, 30)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "  INVOICE", ln=True, fill=True)

    # ── Invoice meta ──────────────────────────────────────────────────────
    pdf.set_text_color(40, 40, 40)
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(4)

    def meta_row(label: str, value: str):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(40, 6, label)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, value, ln=True)

    meta_row("Invoice No:", invoice.invoice_number)
    meta_row("Order ID:", invoice.order.order_id)
    meta_row("Date Issued:", invoice.issued_at.strftime("%B %d, %Y"))
    meta_row("Due Date:", invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "Immediate")
    meta_row("Order Type:", invoice.order.order_type.value.replace("_", " ").title())
    meta_row("Payment:", invoice.order.payment_method.value.replace("_", " ").title())
    if invoice.order.table_number:
        meta_row("Table:", invoice.order.table_number)

    # ── Bill To ───────────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(0, 7, "  Bill To", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(2)
    pdf.cell(0, 5, c.name, ln=True)
    pdf.cell(0, 5, c.email, ln=True)
    if c.phone:
        pdf.cell(0, 5, c.phone, ln=True)
    if c.address:
        pdf.multi_cell(0, 5, c.address)

    # ── Line items table ──────────────────────────────────────────────────
    pdf.ln(6)
    col_widths = [80, 25, 35, 35]  # Description, Qty, Unit Price, Subtotal

    # Table header
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9)
    headers = ["Description", "Qty", "Unit Price", "Amount"]
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 8, f"  {h}", border=0, fill=True)
    pdf.ln()

    # Table rows
    pdf.set_text_color(40, 40, 40)
    fill = False
    for i, item in enumerate(invoice.items):
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 9)
        label = f"  {item.name}"
        if item.note:
            label += f" ({item.note})"
        pdf.cell(col_widths[0], 7, label, fill=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_widths[1], 7, f"  {item.quantity:g}", fill=True)
        pdf.cell(col_widths[2], 7, f"  {_currency(item.unit_price, currency_symbol)}", fill=True)
        pdf.cell(col_widths[3], 7, f"  {_currency(item.subtotal, currency_symbol)}", fill=True)
        pdf.ln()

        # Category sub-label
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(col_widths[0], 4, f"    {item.category}", fill=fill)
        pdf.cell(sum(col_widths[1:]), 4, "", ln=True, fill=fill)
        pdf.set_text_color(40, 40, 40)
        fill = not fill

    # ── Totals ────────────────────────────────────────────────────────────
    pdf.ln(4)
    right_x = 15 + sum(col_widths[:2])  # align totals to right columns

    def total_row(label: str, value: str, bold: bool = False, highlight: bool = False):
        pdf.set_x(right_x)
        if highlight:
            pdf.set_fill_color(30, 30, 30)
            pdf.set_text_color(255, 255, 255)
        else:
            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "B" if bold else "", 9)
        pdf.cell(col_widths[2], 7, label, fill=True)
        pdf.cell(col_widths[3], 7, value, fill=True)
        pdf.ln()

    total_row("Subtotal:", _currency(invoice.subtotal, currency_symbol))
    if invoice.discount_amount > 0:
        total_row(
            f"Discount ({invoice.subtotal and round(invoice.discount_amount/invoice.subtotal*100)}%):",
            f"- {_currency(invoice.discount_amount, currency_symbol)}"
        )
    total_row(
        f"Tax ({int(r.tax_rate * 100)}%):",
        _currency(invoice.tax_amount, currency_symbol)
    )
    total_row(
        "TOTAL:",
        _currency(invoice.total, currency_symbol),
        bold=True,
        highlight=True,
    )

    # ── Notes ─────────────────────────────────────────────────────────────
    note_text = invoice.notes or invoice.order.notes
    if note_text:
        pdf.ln(6)
        pdf.set_text_color(80, 80, 80)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 5, f"Note: {note_text}")

    # ── Footer ────────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(
        0, 5,
        f"Thank you for dining with us!  |  {r.name}  |  {r.email}",
        align="C",
    )

    # Save
    abs_path = os.path.abspath(output_path)
    pdf.output(abs_path)
    return abs_path
