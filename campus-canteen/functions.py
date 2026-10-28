"""Database functions for the Campus Canteen.

Plain Python + sqlite3. No FastAPI in this file.
Functions answer questions (return a value or None) or do one job.
main.py decides which HTTP status code to send.

Money: the database stores prices in paise (Rs 45.50 -> 4550) so sums are exact.
We divide by 100 only when returning a value.

Tables in canteen.db:
  menu_items  (id, name, description, price, category, available)   available is 0 or 1
  cart_items  (id, item_id, quantity)                                 item_id is UNIQUE
  orders      (id, status, total, created_at)                         status starts as 'placed'
  order_items (id, order_id, item_id, item_name, quantity, price_per_unit)
"""

import sqlite3
from pathlib import Path

# canteen.db sits next to this file.
DB_PATH = Path(__file__).parent / "canteen.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us use row["name"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves this OFF by default
    return conn


def to_rupees(paise: int) -> float:
    return paise / 100


# ---------- Checking user input ----------

def check_body(body: dict, expected_fields: set) -> str | None:
    """Return an error message if the body is wrong, or None if it is fine.

    The body must have exactly the expected fields, and each must be a positive whole number.
    """
    if set(body) != expected_fields:
        return f"Request body must contain exactly these fields: {sorted(expected_fields)}"
    for field in sorted(expected_fields):
        value = body[field]
        # In Python True is also an int (True == 1), so we check the exact type.
        if type(value) is not int or value <= 0:
            return f"{field} must be a positive whole number."
    return None


def check_cancel_body(body: dict) -> str | None:
    """Students may only cancel an order, so the body must be exactly {"status": "cancelled"}."""
    if body != {"status": "cancelled"}:
        return 'Request body must be {"status": "cancelled"}. Students can only cancel an order.'
    return None


# ---------- Menu ----------

def get_menu(category: str | None = None, available: bool | None = None) -> list[dict]:
    sql = "SELECT * FROM menu_items WHERE 1 = 1"  # 1 = 1 lets each filter start with AND
    params = []
    if category is not None:
        sql += " AND LOWER(category) = LOWER(?)"  # "Snacks" and "snacks" both match
        params.append(category)
    if available is not None:
        sql += " AND available = ?"
        params.append(int(available))

    conn = connect()
    rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    conn.close()
    return [menu_item_to_dict(row) for row in rows]


def get_menu_item(item_id: int) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return menu_item_to_dict(row)


def menu_item_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["price"] = to_rupees(item["price"])
    item["available"] = bool(item["available"])
    return item


# ---------- Cart ----------

def get_cart() -> dict:
    conn = connect()
    rows = conn.execute(
        """
        SELECT c.item_id, m.name, m.price, c.quantity, m.available
        FROM cart_items AS c
        JOIN menu_items AS m ON m.id = c.item_id
        ORDER BY c.id
        """
    ).fetchall()
    conn.close()

    items = []
    total = 0  # paise
    for row in rows:
        line_total = row["price"] * row["quantity"]
        total += line_total
        items.append({
            "item_id": row["item_id"],
            "name": row["name"],
            "price": to_rupees(row["price"]),
            "quantity": row["quantity"],
            "line_total": to_rupees(line_total),
            "available": bool(row["available"]),
        })
    return {"items": items, "total": to_rupees(total)}


def is_in_cart(item_id: int) -> bool:
    conn = connect()
    row = conn.execute("SELECT id FROM cart_items WHERE item_id = ?", (item_id,)).fetchone()
    conn.close()
    return row is not None


def add_to_cart(item_id: int, quantity: int) -> dict:
    conn = connect()
    with conn:  # saves the change
        # Already in the cart? Then add to its quantity instead of inserting a second row.
        conn.execute(
            """
            INSERT INTO cart_items (item_id, quantity) VALUES (?, ?)
            ON CONFLICT (item_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (item_id, quantity),
        )
    conn.close()
    return get_cart()


def update_cart_item(item_id: int, quantity: int) -> dict:
    conn = connect()
    with conn:
        conn.execute("UPDATE cart_items SET quantity = ? WHERE item_id = ?", (quantity, item_id))
    conn.close()
    return get_cart()


def remove_from_cart(item_id: int) -> None:
    conn = connect()
    with conn:
        conn.execute("DELETE FROM cart_items WHERE item_id = ?", (item_id,))
    conn.close()


# ---------- Orders ----------

def place_order() -> dict:
    """Turn the cart into an order. main.py checks the cart is not empty first."""
    conn = connect()
    # One transaction: create the order, copy the items, empty the cart.
    # If any step fails, none of them are saved.
    with conn:
        rows = conn.execute(
            """
            SELECT c.item_id, m.name, m.price, c.quantity
            FROM cart_items AS c
            JOIN menu_items AS m ON m.id = c.item_id
            """
        ).fetchall()
        total = sum(row["price"] * row["quantity"] for row in rows)  # from DB prices, in paise

        order_id = conn.execute(
            "INSERT INTO orders (status, total) VALUES ('placed', ?)", (total,)
        ).lastrowid
        for row in rows:
            # Save name and price now, so the order stays correct if the menu changes later.
            conn.execute(
                """
                INSERT INTO order_items (order_id, item_id, item_name, quantity, price_per_unit)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, row["item_id"], row["name"], row["quantity"], row["price"]),
            )
        conn.execute("DELETE FROM cart_items")
    conn.close()
    return get_order(order_id)


def get_order(order_id: int) -> dict | None:
    conn = connect()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()
    conn.close()
    if order is None:
        return None

    items = []
    for row in rows:
        items.append({
            "item_id": row["item_id"],
            "item_name": row["item_name"],
            "quantity": row["quantity"],
            "price_per_unit": to_rupees(row["price_per_unit"]),
            "line_total": to_rupees(row["price_per_unit"] * row["quantity"]),
        })
    return {
        "id": order["id"],
        "status": order["status"],
        "total": to_rupees(order["total"]),
        "created_at": order["created_at"],
        "items": items,
    }


def get_orders() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT id FROM orders ORDER BY id DESC").fetchall()  # newest first
    conn.close()
    return [get_order(row["id"]) for row in rows]


def cancel_order(order_id: int) -> dict:
    conn = connect()
    with conn:
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
    conn.close()
    return get_order(order_id)
