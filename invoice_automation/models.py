"""
Data models for restaurant invoice automation.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum
import uuid


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    ONLINE = "online"
    INVOICE = "invoice"


class OrderType(str, Enum):
    DINE_IN = "dine_in"
    TAKEAWAY = "takeaway"
    DELIVERY = "delivery"
    RESERVATION = "reservation"


@dataclass
class Restaurant:
    name: str
    address: str
    city: str
    country: str
    phone: str
    email: str
    tax_id: str
    logo_path: Optional[str] = None
    currency: str = "USD"
    tax_rate: float = 0.10  # 10% default


@dataclass
class LineItem:
    name: str
    quantity: float
    unit_price: float
    category: str = "Food"
    note: Optional[str] = None

    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class Customer:
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    customer_id: Optional[str] = None


@dataclass
class Order:
    restaurant: Restaurant
    customer: Customer
    items: List[LineItem]
    order_type: OrderType = OrderType.DINE_IN
    payment_method: PaymentMethod = PaymentMethod.CARD
    table_number: Optional[str] = None
    order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())[:8].upper()
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class Invoice:
    invoice_number: str
    order: Order
    issued_at: datetime
    due_date: Optional[datetime]
    subtotal: float
    tax_amount: float
    discount_amount: float
    total: float
    paid: bool = False
    notes: Optional[str] = None

    @property
    def restaurant(self) -> Restaurant:
        return self.order.restaurant

    @property
    def customer(self) -> Customer:
        return self.order.customer

    @property
    def items(self) -> List[LineItem]:
        return self.order.items
