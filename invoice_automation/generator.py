"""
Auto-invoice generator for restaurant orders.

Accepts an Order and produces a fully populated Invoice,
applying tax, optional discounts, and sequential invoice numbering.
"""
from datetime import datetime, timedelta
from typing import Optional
import threading

from .models import Invoice, Order


_counter_lock = threading.Lock()
_invoice_counter: int = 1


def _next_invoice_number(prefix: str = "INV") -> str:
    """Thread-safe sequential invoice number generator."""
    global _invoice_counter
    with _counter_lock:
        number = _invoice_counter
        _invoice_counter += 1
    now = datetime.now()
    return f"{prefix}-{now.year}{now.month:02d}-{number:04d}"


def generate_invoice(
    order: Order,
    discount_percent: float = 0.0,
    due_days: int = 0,
    invoice_number: Optional[str] = None,
    notes: Optional[str] = None,
) -> Invoice:
    """
    Auto-generate an invoice from a restaurant order.

    Args:
        order:            The Order to invoice.
        discount_percent: Percentage discount to apply (0–100).
        due_days:         Days until payment is due (0 = due immediately).
        invoice_number:   Override auto-generated invoice number.
        notes:            Extra notes printed on the invoice.

    Returns:
        A fully populated Invoice ready for PDF export or storage.
    """
    # Calculate subtotal from line items
    subtotal = round(sum(item.subtotal for item in order.items), 2)

    # Apply discount before tax
    discount_amount = round(subtotal * (discount_percent / 100), 2)
    taxable_amount = subtotal - discount_amount

    # Apply restaurant tax rate
    tax_amount = round(taxable_amount * order.restaurant.tax_rate, 2)
    total = round(taxable_amount + tax_amount, 2)

    issued_at = datetime.now()
    due_date = issued_at + timedelta(days=due_days) if due_days > 0 else issued_at

    return Invoice(
        invoice_number=invoice_number or _next_invoice_number(),
        order=order,
        issued_at=issued_at,
        due_date=due_date,
        subtotal=subtotal,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total=total,
        notes=notes,
    )


def bulk_generate(orders: list, **kwargs) -> list:
    """Generate invoices for multiple orders at once."""
    return [generate_invoice(order, **kwargs) for order in orders]
