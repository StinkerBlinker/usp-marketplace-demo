from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
import random
import string
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-later"
DATABASE = "marketplace.db"


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT,
            seller_name TEXT,
            pickup_location TEXT,
            image_url TEXT,
            contact TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER,
            confirmation_code TEXT,
            total REAL,
            created_at TEXT
        )
    """)
    count = db.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    if count == 0:
        sample = [
            ("Calculus Textbook (8th Ed)", "Barely used, no highlights.", 35.00, "Textbooks", "Aveshal A.", "Library", "", "aveshal@student.usp.ac.fj"),
            ("Mini Fridge", "Great for dorm rooms, works perfectly.", 120.00, "Dorm Essentials", "Pranay S.", "Hostel Block A", "", "pranay@student.usp.ac.fj"),
            ("USB-C Charger", "Fast charger, 65W, like new.", 25.00, "Electronics", "Lyndray D.", "Student Union", "", "lyndray@student.usp.ac.fj"),
            ("Study Desk Lamp", "LED, adjustable brightness.", 18.00, "Dorm Essentials", "Mosese B.", "Hostel Block B", "", "mosese@student.usp.ac.fj"),
            ("Wireless Mouse", "Logitech, barely used.", 15.00, "Electronics", "Joshua D.", "Bus Stop", "", "joshua@student.usp.ac.fj"),
            ("Database Systems Textbook", "Silberschatz, good condition.", 40.00, "Textbooks", "Aveshal A.", "Library", "", "aveshal@student.usp.ac.fj"),
        ]
        db.executemany(
            "INSERT INTO listings (title, description, price, category, seller_name, pickup_location, image_url, contact) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            sample,
        )
        db.commit()
    db.close()


def generate_confirmation_code():
    return "USP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ---------- Functionality 2: Inventory Management & Search (partial) ----------

@app.route("/", methods=["GET"])
def listings():
    db = get_db()
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    query = "SELECT * FROM listings WHERE status = 'active'"
    params = []
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    if category:
        query += " AND category = ?"
        params.append(category)

    items = db.execute(query, params).fetchall()
    return render_template("listings.html", listings=items, search=search, category=category)


@app.route("/add-listing", methods=["GET", "POST"])
def add_listing():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        price = request.form.get("price", "").strip()

        if not title:
            flash("Please give your item a title before posting.", "error")
            return render_template("add_listing.html")

        db = get_db()
        db.execute(
            "INSERT INTO listings (title, description, price, category, seller_name, pickup_location, image_url, contact) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                request.form.get("description"),
                price or 0,
                request.form.get("category"),
                request.form.get("seller_name"),
                request.form.get("pickup_location"),
                request.form.get("image_url"),
                request.form.get("contact"),
            ),
        )
        db.commit()
        flash("Listing posted!", "success")
        return redirect(url_for("listings"))
    return render_template("add_listing.html")


@app.route("/edit-listing/<int:listing_id>", methods=["GET", "POST"])
def edit_listing(listing_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            "UPDATE listings SET title=?, description=?, price=?, category=?, seller_name=?, pickup_location=?, image_url=?, contact=? WHERE id=?",
            (
                request.form.get("title"),
                request.form.get("description"),
                request.form.get("price") or 0,
                request.form.get("category"),
                request.form.get("seller_name"),
                request.form.get("pickup_location"),
                request.form.get("image_url"),
                request.form.get("contact"),
                listing_id,
            ),
        )
        db.commit()
        flash("Listing updated.", "success")
        return redirect(url_for("listings"))

    item = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return render_template("add_listing.html", item=item)


@app.route("/remove-listing/<int:listing_id>", methods=["POST"])
def remove_listing(listing_id):
    db = get_db()
    db.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
    db.commit()
    flash("Listing removed.", "info")
    return redirect(url_for("listings"))


# ---------- Functionality 3: Buying, Checkout & Payment (full, with validation) ----------

@app.route("/cart/add/<int:listing_id>", methods=["POST"])
def add_to_cart(listing_id):
    cart = session.get("cart", [])
    if listing_id not in cart:
        cart.append(listing_id)
        session["cart"] = cart
        flash("Item added to cart.", "success")
    else:
        flash("Item is already in your cart.", "info")
    return redirect(url_for("listings"))


@app.route("/cart/remove/<int:listing_id>", methods=["POST"])
def remove_from_cart(listing_id):
    cart = session.get("cart", [])
    if listing_id in cart:
        cart.remove(listing_id)
        session["cart"] = cart
    return redirect(url_for("view_cart"))


@app.route("/cart", methods=["GET"])
def view_cart():
    db = get_db()
    cart = session.get("cart", [])
    cart_items = []
    total = 0
    for listing_id in cart:
        item = db.execute("SELECT * FROM listings WHERE id = ? AND status = 'active'", (listing_id,)).fetchone()
        if item:
            cart_items.append(item)
            total += item["price"]
    return render_template("cart.html", cart_items=cart_items, total=total)


@app.route("/checkout-review", methods=["GET"])
def checkout_review():
    db = get_db()
    cart = session.get("cart", [])
    if not cart:
        flash("Your cart is empty. Add an item before checking out.", "error")
        return redirect(url_for("view_cart"))

    cart_items = []
    total = 0
    for listing_id in cart:
        item = db.execute("SELECT * FROM listings WHERE id = ? AND status = 'active'", (listing_id,)).fetchone()
        if item:
            cart_items.append(item)
            total += item["price"]
    return render_template("checkout_review.html", cart_items=cart_items, total=total)


@app.route("/checkout", methods=["POST"])
def checkout():
    db = get_db()
    cart = session.get("cart", [])

    if not cart:
        flash("Your cart is empty. Add an item before checking out.", "error")
        return redirect(url_for("view_cart"))

    if request.form.get("simulate_failure") == "yes":
        flash("Payment could not be processed. Please try again.", "error")
        return redirect(url_for("checkout_review"))

    valid_items = []
    total = 0
    for listing_id in cart:
        item = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if item and item["status"] == "active":
            valid_items.append(item)
            total += item["price"]

    if not valid_items:
        flash("Sorry, the item(s) in your cart were just sold. Please browse again.", "error")
        session["cart"] = []
        return redirect(url_for("listings"))

    confirmation_code = generate_confirmation_code()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in valid_items:
        db.execute("UPDATE listings SET status = 'sold' WHERE id = ?", (item["id"],))
        db.execute(
            "INSERT INTO orders (listing_id, confirmation_code, total, created_at) VALUES (?, ?, ?, ?)",
            (item["id"], confirmation_code, item["price"], created_at),
        )
    db.commit()

    session["cart"] = []
    order_summary = {"confirmation_code": confirmation_code, "total": total, "created_at": created_at}
    return render_template("confirmation.html", order=order_summary, items=valid_items)


# ---------- Demo utility ----------

@app.route("/reset-demo", methods=["POST"])
def reset_demo():
    db = get_db()
    db.execute("DELETE FROM orders")
    db.execute("UPDATE listings SET status = 'active'")
    db.commit()
    session["cart"] = []
    flash("Demo data has been reset.", "info")
    return redirect(url_for("listings"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)