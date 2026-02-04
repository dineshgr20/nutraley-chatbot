"""
Shipping tracker tool for order status lookup
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

def load_orders():
    """Load orders from JSON file"""
    orders_path = Path(__file__).parent.parent / "data" / "orders.json"
    with open(orders_path, 'r') as f:
        return json.load(f)

def get_shipping_status(order_id: str) -> dict:
    """
    Look up order status by order ID

    Args:
        order_id: The order ID to look up (e.g., "ORD-1001")

    Returns:
        Dictionary with order status information or error message
    """
    try:
        orders = load_orders()

        # Find the order
        order = next((o for o in orders if o["order_id"] == order_id), None)

        if not order:
            return {
                "success": False,
                "error": f"Order {order_id} not found in our system."
            }

        # Format the response
        result = {
            "success": True,
            "order_id": order["order_id"],
            "customer_name": order["customer_name"],
            "product_name": order["product_name"],
            "quantity": order["quantity"],
            "order_date": order["order_date"],
            "status": order["status"],
            "shipping_method": order["shipping_method"]
        }

        # Add shipping dates if available
        if order.get("shipped_date"):
            result["shipped_date"] = order["shipped_date"]

        if order.get("estimated_delivery"):
            result["estimated_delivery"] = order["estimated_delivery"]

        if order.get("actual_delivery"):
            result["actual_delivery"] = order["actual_delivery"]

        # Add shipping policy info based on method
        if order["shipping_method"] == "Standard":
            result["shipping_policy"] = "Standard shipping: 5-7 business days"
        elif order["shipping_method"] == "Express":
            result["shipping_policy"] = "Express shipping: 2-3 business days"

        return result

    except Exception as e:
        return {
            "success": False,
            "error": f"Error looking up order: {str(e)}"
        }
