from datetime import datetime, timedelta
from db.session import get_session, init_db
from db.models import (
    Customer,
    Product,
    Order,
    SupportTicket,
    ToolDefinition,
)


def seed_tool_definitions(session):
    """Seed tool definitions into DB"""

    tools = [
        {
            "name": "get_order_status",
            "description": "Get the status and details of an order including customer and product information",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "The unique ID of the order to look up",
                    }
                },
                "required": ["order_id"],
            },
        },
        {
            "name": "get_product_inventory",
            "description": "Get the current inventory level and details of a product",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "The unique ID of the product to check inventory for",
                    }
                },
                "required": ["product_id"],
            },
        },
        {
            "name": "list_customer_orders",
            "description": "List all orders belonging to a specific customer",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "The unique ID of the customer",
                    }
                },
                "required": ["customer_id"],
            },
        },
        {
            "name": "create_support_ticket",
            "description": "Create a new support ticket for a customer (write operation - requires confirmation)",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "integer",
                        "description": "The unique ID of the customer creating the ticket",
                    },
                    "message": {
                        "type": "string",
                        "description": "The support message or issue description (max 1000 characters)",
                    },
                },
                "required": ["customer_id", "message"],
            },
        },
    ]

    for tool_data in tools:
        existing = session.query(ToolDefinition).filter_by(name=tool_data["name"]).first()
        if not existing:
            tool = ToolDefinition(
                name=tool_data["name"],
                description=tool_data["description"],
                parameters_schema=tool_data["parameters_schema"],
                enabled=True,
            )
            session.add(tool)

    session.commit()


def seed_operational_data(session):
    """Seed mock operational data"""

    # Clear existing data
    session.query(Order).delete()
    session.query(SupportTicket).delete()
    session.query(Product).delete()
    session.query(Customer).delete()

    # Customers
    customers = [
        Customer(name="Alice Johnson", email="alice@example.com"),
        Customer(name="Bob Smith", email="bob@example.com"),
        Customer(name="Carol White", email="carol@example.com"),
    ]
    session.add_all(customers)
    session.commit()

    # Products
    products = [
        Product(name="Laptop", price=999.99, inventory=5),
        Product(name="Mouse", price=29.99, inventory=50),
        Product(name="Keyboard", price=79.99, inventory=25),
        Product(name="Monitor", price=299.99, inventory=10),
        Product(name="USB Cable", price=9.99, inventory=100),
    ]
    session.add_all(products)
    session.commit()

    # Orders
    orders = [
        Order(customer_id=1, product_id=1, quantity=1, status="shipped"),
        Order(customer_id=1, product_id=2, quantity=2, status="delivered"),
        Order(customer_id=2, product_id=3, quantity=1, status="pending"),
        Order(customer_id=2, product_id=4, quantity=1, status="shipped"),
        Order(customer_id=3, product_id=5, quantity=5, status="delivered"),
    ]
    session.add_all(orders)
    session.commit()


def seed_database():
    """Initialize and seed the database"""
    init_db()
    session = get_session()

    try:
        seed_tool_definitions(session)
        seed_operational_data(session)
        print("[OK] Database initialized and seeded successfully")
    except Exception as e:
        print(f"[ERROR] Error seeding database: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
