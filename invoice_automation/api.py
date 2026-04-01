"""
REST API for restaurant invoice automation.

Run:  uvicorn invoice_automation.api:app --reload
Docs: http://localhost:8000/docs

Install: pip install fastapi uvicorn fpdf2
"""
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from .models import (
    Customer, LineItem, Order, OrderType, PaymentMethod, Restaurant
)
from .generator import generate_invoice
from .pdf_generator import generate_pdf


app = FastAPI(
    title="Restaurant Invoice Automation API",
    description="Auto-generate PDF invoices from restaurant orders.",
    version="1.0.0",
)

# ── Request / Response schemas ─────────────────────────────────────────────

class RestaurantSchema(BaseModel):
    name: str
    address: str
    city: str
    country: str
    phone: str
    email: str
    tax_id: str
    currency: str = "USD"
    tax_rate: float = 0.10

class LineItemSchema(BaseModel):
    name: str
    quantity: float
    unit_price: float
    category: str = "Food"
    note: Optional[str] = None

class CustomerSchema(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    customer_id: Optional[str] = None

class OrderRequest(BaseModel):
    restaurant: RestaurantSchema
    customer: CustomerSchema
    items: List[LineItemSchema]
    order_type: OrderType = OrderType.DINE_IN
    payment_method: PaymentMethod = PaymentMethod.CARD
    table_number: Optional[str] = None
    notes: Optional[str] = None
    discount_percent: float = 0.0
    due_days: int = 0

class InvoiceResponse(BaseModel):
    invoice_number: str
    order_id: str
    customer_name: str
    customer_email: str
    issued_at: datetime
    due_date: Optional[datetime]
    subtotal: float
    discount_amount: float
    tax_amount: float
    total: float
    currency: str
    pdf_url: str


# ── In-memory invoice store (replace with DB in production) ───────────────

_invoices: dict = {}


# ── Routes ────────────────────────────────────────────────────────────────

@app.post("/invoices", response_model=InvoiceResponse, status_code=201)
def create_invoice(request: OrderRequest):
    """
    Auto-generate an invoice from a restaurant order.
    Returns invoice metadata and a URL to download the PDF.
    """
    restaurant = Restaurant(**request.restaurant.dict())
    customer = Customer(**request.customer.dict())
    items = [LineItem(**i.dict()) for i in request.items]

    order = Order(
        restaurant=restaurant,
        customer=customer,
        items=items,
        order_type=request.order_type,
        payment_method=request.payment_method,
        table_number=request.table_number,
        notes=request.notes,
    )

    invoice = generate_invoice(
        order,
        discount_percent=request.discount_percent,
        due_days=request.due_days,
    )

    pdf_path = generate_pdf(invoice, output_path=f"/tmp/{invoice.invoice_number}.pdf")
    _invoices[invoice.invoice_number] = {"invoice": invoice, "pdf_path": pdf_path}

    return InvoiceResponse(
        invoice_number=invoice.invoice_number,
        order_id=order.order_id,
        customer_name=customer.name,
        customer_email=customer.email,
        issued_at=invoice.issued_at,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        tax_amount=invoice.tax_amount,
        total=invoice.total,
        currency=restaurant.currency,
        pdf_url=f"/invoices/{invoice.invoice_number}/pdf",
    )


@app.get("/invoices/{invoice_number}/pdf")
def download_invoice_pdf(invoice_number: str):
    """Download the generated PDF invoice."""
    entry = _invoices.get(invoice_number)
    if not entry:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return FileResponse(
        path=entry["pdf_path"],
        media_type="application/pdf",
        filename=f"{invoice_number}.pdf",
    )


@app.get("/invoices/{invoice_number}", response_model=InvoiceResponse)
def get_invoice(invoice_number: str):
    """Retrieve invoice metadata by invoice number."""
    entry = _invoices.get(invoice_number)
    if not entry:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = entry["invoice"]
    return InvoiceResponse(
        invoice_number=invoice.invoice_number,
        order_id=invoice.order.order_id,
        customer_name=invoice.customer.name,
        customer_email=invoice.customer.email,
        issued_at=invoice.issued_at,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        tax_amount=invoice.tax_amount,
        total=invoice.total,
        currency=invoice.restaurant.currency,
        pdf_url=f"/invoices/{invoice.invoice_number}/pdf",
    )


@app.get("/invoices", response_model=List[InvoiceResponse])
def list_invoices():
    """List all generated invoices."""
    result = []
    for inv_num, entry in _invoices.items():
        invoice = entry["invoice"]
        result.append(InvoiceResponse(
            invoice_number=invoice.invoice_number,
            order_id=invoice.order.order_id,
            customer_name=invoice.customer.name,
            customer_email=invoice.customer.email,
            issued_at=invoice.issued_at,
            due_date=invoice.due_date,
            subtotal=invoice.subtotal,
            discount_amount=invoice.discount_amount,
            tax_amount=invoice.tax_amount,
            total=invoice.total,
            currency=invoice.restaurant.currency,
            pdf_url=f"/invoices/{invoice.invoice_number}/pdf",
        ))
    return result
