"""
Example: auto-generate a PDF invoice from a restaurant order.

Usage:
    pip install fpdf2
    python -m invoice_automation.examples.sample_order
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from invoice_automation import (
    Restaurant, Customer, LineItem, Order, OrderType, PaymentMethod,
    generate_invoice, generate_pdf,
)


def main():
    # 1. Define the restaurant
    restaurant = Restaurant(
        name="Bella Cucina",
        address="123 Main Street",
        city="New York, NY 10001",
        country="USA",
        phone="+1 (212) 555-0198",
        email="billing@bellacucina.com",
        tax_id="US-TAX-88271",
        currency="USD",
        tax_rate=0.08,  # 8% sales tax
    )

    # 2. Define the customer
    customer = Customer(
        name="John Smith",
        email="john.smith@email.com",
        phone="+1 (917) 555-0143",
        address="456 Park Ave, New York, NY",
    )

    # 3. Build the order from website items
    order = Order(
        restaurant=restaurant,
        customer=customer,
        items=[
            LineItem("Margherita Pizza",       quantity=2, unit_price=18.50, category="Pizza"),
            LineItem("Caesar Salad",            quantity=1, unit_price=12.00, category="Salad"),
            LineItem("Grilled Salmon",          quantity=1, unit_price=28.00, category="Main Course"),
            LineItem("Tiramisu",                quantity=2, unit_price=9.50,  category="Dessert"),
            LineItem("House Red Wine (bottle)", quantity=1, unit_price=42.00, category="Beverage"),
            LineItem("Sparkling Water",         quantity=2, unit_price=4.00,  category="Beverage"),
        ],
        order_type=OrderType.DINE_IN,
        payment_method=PaymentMethod.CARD,
        table_number="T-07",
        notes="Gluten-free options requested for dessert.",
    )

    # 4. Auto-generate invoice (5% loyalty discount, due immediately)
    invoice = generate_invoice(order, discount_percent=5.0)

    print(f"Invoice generated: {invoice.invoice_number}")
    print(f"  Customer : {invoice.customer.name}")
    print(f"  Subtotal : ${invoice.subtotal:.2f}")
    print(f"  Discount : -${invoice.discount_amount:.2f}")
    print(f"  Tax      : ${invoice.tax_amount:.2f}")
    print(f"  TOTAL    : ${invoice.total:.2f}")

    # 5. Export to PDF
    pdf_path = generate_pdf(invoice, output_path=f"{invoice.invoice_number}.pdf")
    print(f"\nPDF saved: {pdf_path}")


if __name__ == "__main__":
    main()
