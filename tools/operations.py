from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from db.models import Order, Product, Customer, SupportTicket


class ToolOperations:
    """Tool implementations for the agent. Static methods bound to registry"""

    @staticmethod
    def get_order_status(db: Session, order_id: int) -> Dict[str, Any]:
        """Get the status and details of an order"""
        order = db.query(Order).filter_by(id=order_id).first()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        customer = db.query(Customer).filter_by(id=order.customer_id).first()
        product = db.query(Product).filter_by(id=order.product_id).first()

        return {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "customer_name": customer.name if customer else "Unknown",
            "product_id": order.product_id,
            "product_name": product.name if product else "Unknown",
            "quantity": order.quantity,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
        }

    @staticmethod
    def get_product_inventory(db: Session, product_id: int) -> Dict[str, Any]:
        """Get the current inventory level and details of a product"""
        product = db.query(Product).filter_by(id=product_id).first()

        if not product:
            raise ValueError(f"Product {product_id} not found")

        return {
            "product_id": product.id,
            "product_name": product.name,
            "price": product.price,
            "inventory": product.inventory,
        }

    @staticmethod
    def list_customer_orders(db: Session, customer_id: int) -> Dict[str, Any]:
        """List all orders belonging to a specific customer"""
        customer = db.query(Customer).filter_by(id=customer_id).first()

        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        orders = db.query(Order).filter_by(customer_id=customer_id).all()

        if not orders:
            return {
                "customer_id": customer_id,
                "customer_name": customer.name,
                "orders": [],
                "order_count": 0,
            }

        order_list = [
            {
                "order_id": o.id,
                "product_id": o.product_id,
                "product_name": db.query(Product).filter_by(id=o.product_id).first().name or "Unknown",
                "quantity": o.quantity,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ]

        return {
            "customer_id": customer_id,
            "customer_name": customer.name,
            "orders": order_list,
            "order_count": len(order_list),
        }

    @staticmethod
    def create_support_ticket(db: Session, customer_id: int, message: str) -> Dict[str, Any]:
        """Create a new support ticket for a customer"""
        customer = db.query(Customer).filter_by(id=customer_id).first()

        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        if len(message.strip()) == 0:
            raise ValueError("Message cannot be empty")

        ticket = SupportTicket(customer_id=customer_id, message=message, status="open")
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        return {
            "ticket_id": ticket.id,
            "customer_id": ticket.customer_id,
            "customer_name": customer.name,
            "message": ticket.message,
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat(),
        }


def bind_tools_to_registry(registry, db: Session):
    """Bind all tool implementations to the registry"""

    # Create wrapper functions that inject db session
    @registry.register("get_order_status")
    def get_order_status_wrapper(order_id: int):
        return ToolOperations.get_order_status(db, order_id)

    @registry.register("get_product_inventory")
    def get_product_inventory_wrapper(product_id: int):
        return ToolOperations.get_product_inventory(db, product_id)

    @registry.register("list_customer_orders")
    def list_customer_orders_wrapper(customer_id: int):
        return ToolOperations.list_customer_orders(db, customer_id)

    @registry.register("create_support_ticket")
    def create_support_ticket_wrapper(customer_id: int, message: str):
        return ToolOperations.create_support_ticket(db, customer_id, message)
