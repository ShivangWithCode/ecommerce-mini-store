from flask import Flask, render_template, url_for, session, redirect, request, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# pyrefly: ignore [missing-import]
import mysql.connector
from functools import wraps
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import time
import random

load_dotenv()

def calculate_estimated_delivery(order_date, days=4):
    if not order_date:
        return "3-5 Business Days"
    try:
        if isinstance(order_date, str):
            dt = datetime.strptime(order_date, '%Y-%m-%d %H:%M:%S')
        else:
            dt = order_date
        return (dt + timedelta(days=days)).strftime('%a, %d %b %Y')
    except Exception:
        return "3-5 Business Days"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to continue.")
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            flash("Access denied. Admin privileges required.")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access the seller portal.")
            return redirect(url_for('login'))
        if session.get('role') != 'seller' and not session.get('is_admin'):
            flash("Access denied. Seller privileges required.")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    connection = mysql.connector.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        database=os.environ.get('DB_NAME')
    )
    return connection

def fetch_filtered_products(search_query='', category='', sort='newest'):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT products.id, products.name, products.price, products.description, products.category,
               products.image_url, products.stock, products.seller_id,
               COALESCE(users.shop_name, users.name, 'MiniStore Official') AS seller_name
        FROM products
        LEFT JOIN users ON products.seller_id = users.id
        WHERE 1=1
    """
    params = []

    if search_query:
        query += " AND (products.name LIKE %s OR products.description LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    if category:
        query += " AND products.category = %s"
        params.append(category)

    if sort == 'price_asc':
        query += " ORDER BY products.price ASC"
    elif sort == 'price_desc':
        query += " ORDER BY products.price DESC"
    elif sort == 'name_asc':
        query += " ORDER BY products.name ASC"
    else:
        query += " ORDER BY products.id DESC"

    cursor.execute(query, tuple(params))
    products = cursor.fetchall()

    cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    category_rows = cursor.fetchall()
    categories = [cat['category'] for cat in category_rows]

    connection.close()
    return products, categories

@app.route('/')
def home():
    search_query = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', 'newest').strip()

    products, categories = fetch_filtered_products(search_query, category, sort)

    return render_template(
        'home.html',
        products=products,
        categories=categories,
        search_query=search_query,
        selected_category=category,
        selected_sort=sort
    )

@app.route('/api/products')
def api_products():
    search_query = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    sort = request.args.get('sort', 'newest').strip()

    products, _ = fetch_filtered_products(search_query, category, sort)

    serialized = []
    for p in products:
        serialized.append({
            'id': p['id'],
            'name': p['name'],
            'price': float(p['price']),
            'formatted_price': f"{float(p['price']):.2f}",
            'description': p['description'] or '',
            'category': p['category'] or 'General',
            'image_url': p['image_url'] or 'bag.jpg',
            'stock': p['stock'] if p['stock'] is not None else 0,
            'seller_name': p.get('seller_name') or 'MiniStore Official',
            'detail_url': url_for('product_detail', product_id=p['id'])
        })

    return jsonify({
        'count': len(serialized),
        'products': serialized
    })

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT products.id, products.name, products.price, products.description, products.category,
               products.image_url, products.stock, products.seller_id,
               COALESCE(users.shop_name, users.name, 'MiniStore Official') AS seller_name
        FROM products
        LEFT JOIN users ON products.seller_id = users.id
        WHERE products.id = %s
    """, (product_id,))
    product = cursor.fetchone()
    connection.close()
    return render_template('product_detail.html', product=product)

@app.route('/add-to-cart/<int:product_id>', methods=['GET', 'POST'])
@login_required
def add_to_cart(product_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT id, name, stock FROM products WHERE id = %s", (product_id,))
    prod = cursor.fetchone()
    if not prod:
        connection.close()
        flash("Product not found.")
        return redirect(url_for('home'))

    available_stock = prod['stock'] if prod['stock'] is not None else 0
    if available_stock <= 0:
        connection.close()
        flash(f"Sorry, '{prod['name']}' is out of stock.")
        return redirect(request.referrer or url_for('home'))

    cursor.execute(
        "SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    existing_item = cursor.fetchone()

    if existing_item:
        if existing_item['quantity'] + 1 > available_stock:
            connection.close()
            flash(f"Cannot add more than available stock ({available_stock}) for '{prod['name']}'.")
            return redirect(url_for('cart_page'))
        cursor.execute(
            "UPDATE cart_items SET quantity = quantity + 1 WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )
    else:
        cursor.execute(
            "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)",
            (user_id, product_id, 1)
        )

    connection.commit()
    connection.close()
    return redirect(url_for('cart_page'))

@app.route('/remove-from-cart/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )

    connection.commit()
    connection.close()
    return redirect(url_for('cart_page'))

@app.route('/clear-cart', methods=['GET', 'POST'])
@login_required
def clear_cart():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
    connection.commit()
    connection.close()

    flash("Your cart has been cleared.")
    return redirect(url_for('cart_page'))

@app.route('/increase-quantity/<int:product_id>')
@login_required
def increase_quantity(product_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "UPDATE cart_items SET quantity = quantity + 1 WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )

    connection.commit()
    connection.close()
    return redirect(url_for('cart_page'))

@app.route('/decrease-quantity/<int:product_id>')
@login_required
def decrease_quantity(product_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    current = cursor.fetchone()

    if current and current[0] <= 1:
        cursor.execute(
            "DELETE FROM cart_items WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )
    else:
        cursor.execute(
            "UPDATE cart_items SET quantity = quantity - 1 WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )

    connection.commit()
    connection.close()
    return redirect(url_for('cart_page'))

@app.route('/api/update-cart/<int:product_id>/<action>')
@login_required
def api_update_cart(product_id, action):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if action == 'increase':
        cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
        p = cursor.fetchone()
        stock = p['stock'] if p and p['stock'] is not None else 999

        cursor.execute("SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        cur = cursor.fetchone()
        if cur and cur['quantity'] < stock:
            cursor.execute(
                "UPDATE cart_items SET quantity = quantity + 1 WHERE user_id = %s AND product_id = %s",
                (user_id, product_id)
            )
    elif action == 'decrease':
        cursor.execute(
            "SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
            (user_id, product_id)
        )
        current = cursor.fetchone()
        if current and current['quantity'] <= 1:
            cursor.execute(
                "DELETE FROM cart_items WHERE user_id = %s AND product_id = %s",
                (user_id, product_id)
            )
        elif current:
            cursor.execute(
                "UPDATE cart_items SET quantity = quantity - 1 WHERE user_id = %s AND product_id = %s",
                (user_id, product_id)
            )
    connection.commit()

    cursor.execute(
        "SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    updated = cursor.fetchone()
    new_quantity = updated['quantity'] if updated else 0

    cursor.execute("""
        SELECT SUM(products.price * cart_items.quantity) AS total
        FROM cart_items JOIN products ON cart_items.product_id = products.id
        WHERE cart_items.user_id = %s
    """, (user_id,))
    total_result = cursor.fetchone()
    new_total = float(total_result['total']) if total_result and total_result['total'] else 0.0

    connection.close()

    return jsonify({
        'quantity': new_quantity,
        'total': new_total
    })

@app.route('/cart')
@login_required
def cart_page():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT products.id, products.name, products.price, cart_items.quantity, products.image_url,
               COALESCE(users.shop_name, 'MiniStore Official') AS seller_name
        FROM cart_items
        JOIN products ON cart_items.product_id = products.id
        LEFT JOIN users ON products.seller_id = users.id
        WHERE cart_items.user_id = %s
    """, (user_id,))

    rows = cursor.fetchall()

    cart_items = []
    total = 0

    for row in rows:
        item_total = float(row[2]) * row[3]
        cart_items.append({
            'id': row[0],
            'name': row[1],
            'price': row[2],
            'quantity': row[3],
            'image_url': row[4],
            'seller_name': row[5] if len(row) > 5 else 'MiniStore Official',
            'item_total': item_total
        })
        total += item_total

    connection.close()
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'customer').strip().lower()
        if role not in ['customer', 'seller']:
            role = 'customer'

        shop_name = request.form.get('shop_name', '').strip() if role == 'seller' else None
        if role == 'seller' and not shop_name:
            shop_name = f"{name}'s Store"

        if len(password) < 6:
            flash("Password must be at least 6 characters long.")
            return redirect(url_for('signup', role=role))

        if len(name) == 0:
            flash("Name field cannot be empty.")
            return redirect(url_for('signup', role=role))

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password, role, shop_name) VALUES (%s, %s, %s, %s, %s)",
                (name, email, hashed_password, role, shop_name)
            )
            user_id = cursor.lastrowid
            connection.commit()
            connection.close()

            # Auto-login after signup
            session['user_id'] = user_id
            session['user_name'] = name
            session['is_admin'] = False
            session['role'] = role
            session['shop_name'] = shop_name

            if role == 'seller':
                flash(f"Welcome, {shop_name or name}! Your Seller Portal is ready.")
                return redirect(url_for('seller_dashboard'))
            else:
                flash(f"Welcome to MiniStore, {name}!")
                return redirect(url_for('home'))

        except mysql.connector.IntegrityError:
            connection.close()
            flash("Email address is already registered. Please log in.")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT products.id, products.name, products.price, products.stock, products.image_url, 
               products.seller_id, cart_items.quantity
        FROM cart_items
        JOIN products ON cart_items.product_id = products.id
        WHERE cart_items.user_id = %s
    """, (user_id,))
    cart_items = cursor.fetchall()

    if not cart_items:
        connection.close()
        flash("Your shopping cart is empty.")
        return redirect(url_for('cart_page'))

    total = sum(float(item['price']) * item['quantity'] for item in cart_items)

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        pincode = request.form.get('pincode', '').strip()
        
        payment_type = request.form.get('payment_method_type', '').strip()
        if not payment_type:
            payment_type = 'Online' if 'online' in request.form.get('payment_method', '').lower() else 'COD'

        if payment_type == 'Online':
            sub_method = request.form.get('online_sub_method', 'upi')
            if sub_method == 'upi':
                upi_mode = request.form.get('upi_mode', 'qr')
                if upi_mode == 'qr':
                    utr = request.form.get('upi_utr', '').strip()
                    payment_method = f"UPI (QR: {utr})" if utr else "UPI (QR Scan)"
                else:
                    upi_id = request.form.get('upi_id', '').strip()
                    payment_method = f"UPI ({upi_id})" if upi_id else "UPI / Online"
            elif sub_method == 'card':
                card_number = request.form.get('card_number', '').replace(' ', '').strip()
                last4 = card_number[-4:] if len(card_number) >= 4 else "Card"
                payment_method = f"Card (Ending {last4})"
            elif sub_method == 'netbanking':
                bank_name = request.form.get('bank_name', 'Net Banking').strip()
                payment_method = f"Net Banking ({bank_name})"
            else:
                payment_method = "Online Payment"
            order_status = 'Paid'
            transaction_id = f"TXN-{int(time.time())}{random.randint(1000, 9999)}"
        else:
            payment_method = 'Cash on Delivery (COD)'
            order_status = 'Pending'
            transaction_id = None

        payment_method = payment_method[:50]

        if not full_name or not phone or not address or not city or not pincode:
            connection.close()
            flash("Please fill in all required delivery details.")
            return render_template('checkout.html', cart_items=cart_items, total=total)

        shipping_address = f"{full_name}\n{address}, {city} - {pincode}\nPhone: {phone}"

        # Validate stock availability
        for item in cart_items:
            stock = item['stock'] if item['stock'] is not None else 0
            if item['quantity'] > stock:
                connection.close()
                flash(f"Sorry, insufficient stock for '{item['name']}' (Available: {stock}).")
                return redirect(url_for('cart_page'))

        try:
            cursor.execute("""
                INSERT INTO orders (user_id, total_amount, status, shipping_address, phone, payment_method, transaction_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, total, order_status, shipping_address, phone, payment_method, transaction_id))
            order_id = cursor.lastrowid

            for item in cart_items:
                cursor.execute(
                    "INSERT INTO order_items (order_id, product_id, seller_id, quantity, price) VALUES (%s, %s, %s, %s, %s)",
                    (order_id, item['id'], item.get('seller_id'), item['quantity'], item['price'])
                )
                cursor.execute(
                    "UPDATE products SET stock = stock - %s WHERE id = %s",
                    (item['quantity'], item['id'])
                )

            cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
            connection.commit()
            connection.close()

            return redirect(url_for('order_success', order_id=order_id))

        except Exception as e:
            connection.rollback()
            connection.close()
            flash("An error occurred while processing the order. Transaction rolled back.")
            return redirect(url_for('checkout'))

    connection.close()
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/place-order')
@login_required
def place_order():
    return redirect(url_for('checkout'))

@app.route('/upi-qr')
def upi_qr():
    amount = request.args.get('amount', '0.00')
    upi_pa = os.getenv('UPI_ID', 'ministore@okaxis')
    upi_pn = os.getenv('STORE_NAME', 'MiniStore')
    upi_data = f"upi://pay?pa={upi_pa}&pn={upi_pn}&am={amount}&cu=INR&tn=MiniStoreOrder"
    
    import qrcode
    import qrcode.image.svg
    import io
    from flask import Response

    qr = qrcode.QRCode(image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=1)
    qr.add_data(upi_data)
    qr.make(fit=True)
    img = qr.make_image()
    stream = io.BytesIO()
    img.save(stream)
    return Response(stream.getvalue(), mimetype='image/svg+xml')

@app.route('/order-success/<int:order_id>')
@login_required
def order_success(order_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, total_amount, order_date, status, shipping_address, phone, payment_method, transaction_id
        FROM orders
        WHERE id = %s AND user_id = %s
    """, (order_id, user_id))
    order = cursor.fetchone()
    connection.close()

    if not order:
        flash("Order not found.")
        return redirect(url_for('home'))

    est_delivery = calculate_estimated_delivery(order['order_date'], days=4)
    return render_template('order_success.html', order=order, estimated_delivery=est_delivery)

@app.route('/order/invoice/<int:order_id>')
@app.route('/invoice/<int:order_id>', endpoint='view_invoice')
@login_required
def order_invoice(order_id):
    user_id = session['user_id']
    is_admin = session.get('is_admin')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if is_admin:
        cursor.execute("""
            SELECT orders.*, users.name AS customer_name, users.email AS customer_email
            FROM orders
            JOIN users ON orders.user_id = users.id
            WHERE orders.id = %s
        """, (order_id,))
    else:
        cursor.execute("""
            SELECT orders.*, users.name AS customer_name, users.email AS customer_email
            FROM orders
            JOIN users ON orders.user_id = users.id
            WHERE orders.id = %s AND orders.user_id = %s
        """, (order_id, user_id))

    order = cursor.fetchone()
    if not order:
        connection.close()
        flash("Invoice not found.")
        return redirect(url_for('home'))

    cursor.execute("""
        SELECT products.name, order_items.quantity, order_items.price
        FROM order_items
        JOIN products ON order_items.product_id = products.id
        WHERE order_items.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()
    connection.close()

    est_delivery = calculate_estimated_delivery(order['order_date'], days=4)
    return render_template('invoice.html', order=order, items=items, estimated_delivery=est_delivery)

@app.route('/orders')
@login_required
def order_history():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, total_amount, order_date, status, shipping_address, phone, payment_method, transaction_id
        FROM orders WHERE user_id = %s ORDER BY order_date DESC
    """, (user_id,))
    orders = cursor.fetchall()

    for order in orders:
        order['estimated_delivery'] = calculate_estimated_delivery(order['order_date'], days=4)
        cursor.execute("""
            SELECT products.name, order_items.quantity, order_items.price
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = %s
        """, (order['id'],))
        order['products'] = cursor.fetchall()

    connection.close()
    return render_template('order_history.html', all_orders=orders)

@app.route('/orders/cancel/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT id, status FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
    order = cursor.fetchone()

    if not order:
        connection.close()
        flash("Order not found or unauthorized.")
        return redirect(url_for('order_history'))

    if order['status'] not in ['Pending', 'Paid']:
        connection.close()
        flash(f"Order #{order_id} cannot be cancelled as it is already '{order['status']}'.")
        return redirect(url_for('order_history'))

    try:
        cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE id = %s", (order_id,))

        # Restore product stock
        cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
        items = cursor.fetchall()
        for item in items:
            cursor.execute(
                "UPDATE products SET stock = stock + %s WHERE id = %s",
                (item['quantity'], item['product_id'])
            )

        connection.commit()
        connection.close()
        flash(f"Order #{order_id} has been cancelled successfully. Stock has been restored.")
    except Exception as e:
        connection.rollback()
        connection.close()
        flash("An error occurred while cancelling your order.")

    return redirect(url_for('order_history'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, password, is_admin, role, shop_name FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        connection.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = bool(user['is_admin'])
            user_role = user.get('role') or ('admin' if session['is_admin'] else 'customer')
            session['role'] = user_role
            session['shop_name'] = user.get('shop_name')

            if session['is_admin']:
                flash(f"Welcome Admin, {user['name']}!")
                return redirect(url_for('admin_dashboard'))
            elif session['role'] == 'seller':
                flash(f"Welcome Seller, {session['shop_name'] or user['name']}!")
                return redirect(url_for('seller_dashboard'))
            return redirect(url_for('home'))
        else:
            flash("Invalid email or password.")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ===== SELLER / RETAILER PORTAL ROUTES =====

@app.route('/seller')
@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    seller_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total_products FROM products WHERE seller_id = %s", (seller_id,))
    prod_row = cursor.fetchone()
    total_products = prod_row['total_products'] if prod_row else 0

    cursor.execute("""
        SELECT COALESCE(SUM(order_items.quantity), 0) AS total_units_sold,
               COALESCE(SUM(order_items.quantity * order_items.price), 0) AS total_earnings,
               COUNT(DISTINCT order_items.order_id) AS total_orders
        FROM order_items
        WHERE order_items.seller_id = %s
    """, (seller_id,))
    sales_row = cursor.fetchone()
    total_units_sold = sales_row['total_units_sold'] if sales_row else 0
    total_earnings = float(sales_row['total_earnings']) if sales_row else 0.0
    total_orders = sales_row['total_orders'] if sales_row else 0

    cursor.execute("""
        SELECT orders.id AS order_id, orders.order_date, orders.status, orders.shipping_address, orders.phone,
               products.name AS product_name, products.image_url,
               order_items.quantity, order_items.price,
               (order_items.quantity * order_items.price) AS item_total
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE order_items.seller_id = %s
        ORDER BY orders.order_date DESC
        LIMIT 8
    """, (seller_id,))
    recent_orders = cursor.fetchall()
    connection.close()

    stats = {
        'total_products': total_products,
        'total_units_sold': total_units_sold,
        'total_earnings': total_earnings,
        'total_orders': total_orders
    }

    return render_template('seller/dashboard.html', stats=stats, recent_orders=recent_orders)

@app.route('/seller/products')
@seller_required
def seller_products():
    seller_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, name, price, stock, category, image_url
        FROM products
        WHERE seller_id = %s
        ORDER BY id DESC
    """, (seller_id,))
    products = cursor.fetchall()
    connection.close()

    return render_template('seller/products.html', products=products)

@app.route('/seller/products/add', methods=['GET', 'POST'])
@seller_required
def seller_add_product():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General').strip()
        stock = request.form.get('stock', '15').strip()
        seller_id = session['user_id']

        if not name or not price:
            flash("Product name and price are required.")
            return redirect(url_for('seller_add_product'))

        filename = 'bag.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                unique_name = f"{int(time.time())}_{fname}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                filename = unique_name

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO products (name, price, description, category, image_url, stock, seller_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, price, description, category, filename, stock, seller_id))
        connection.commit()
        connection.close()

        flash(f"Product '{name}' successfully published in your store!")
        return redirect(url_for('seller_products'))

    return render_template('seller/product_form.html', product=None)

@app.route('/seller/products/edit/<int:product_id>', methods=['GET', 'POST'])
@seller_required
def seller_edit_product(product_id):
    seller_id = session['user_id']
    is_admin = session.get('is_admin')
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if is_admin:
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    else:
        cursor.execute("SELECT * FROM products WHERE id = %s AND seller_id = %s", (product_id, seller_id))
    product = cursor.fetchone()

    if not product:
        connection.close()
        flash("Product not found or permission denied.")
        return redirect(url_for('seller_products'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        price = request.form.get('price', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General').strip()
        stock = request.form.get('stock', '15').strip()

        filename = product['image_url']
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                unique_name = f"{int(time.time())}_{fname}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                filename = unique_name

        cursor.execute("""
            UPDATE products
            SET name = %s, price = %s, description = %s, category = %s, stock = %s, image_url = %s
            WHERE id = %s
        """, (name, price, description, category, stock, filename, product_id))
        connection.commit()
        connection.close()

        flash(f"Product '{name}' updated successfully.")
        return redirect(url_for('seller_products'))

    connection.close()
    return render_template('seller/product_form.html', product=product)

@app.route('/seller/products/delete/<int:product_id>', methods=['POST'])
@seller_required
def seller_delete_product(product_id):
    seller_id = session['user_id']
    is_admin = session.get('is_admin')
    connection = get_db_connection()
    cursor = connection.cursor()

    if not is_admin:
        cursor.execute("SELECT id FROM products WHERE id = %s AND seller_id = %s", (product_id, seller_id))
        if not cursor.fetchone():
            connection.close()
            flash("Permission denied.")
            return redirect(url_for('seller_products'))

    cursor.execute("DELETE FROM cart_items WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM order_items WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    connection.commit()
    connection.close()

    flash("Product deleted successfully.")
    return redirect(url_for('seller_products'))

@app.route('/seller/orders')
@seller_required
def seller_orders():
    seller_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT orders.id AS order_id, orders.order_date, orders.status, orders.shipping_address, orders.phone,
               orders.payment_method, orders.transaction_id, users.name AS customer_name, users.email AS customer_email,
               products.name AS product_name, products.image_url,
               order_items.quantity, order_items.price,
               (order_items.quantity * order_items.price) AS item_total
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        JOIN users ON orders.user_id = users.id
        WHERE order_items.seller_id = %s
        ORDER BY orders.order_date DESC
    """, (seller_id,))
    orders = cursor.fetchall()
    connection.close()

    return render_template('seller/orders.html', orders=orders)

# ===== ADMIN PANEL ROUTES =====

@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("SELECT COALESCE(SUM(total_amount), 0) AS total_revenue, COUNT(*) AS total_orders FROM orders")
    order_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total_products FROM products")
    product_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total_users FROM users WHERE is_admin = FALSE")
    user_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) AS total_sellers FROM users WHERE role = 'seller'")
    seller_stats = cursor.fetchone()

    stats = {
        'total_revenue': float(order_stats['total_revenue']) if order_stats else 0.0,
        'total_orders': order_stats['total_orders'] if order_stats else 0,
        'total_products': product_stats['total_products'] if product_stats else 0,
        'total_users': user_stats['total_users'] if user_stats else 0,
        'total_sellers': seller_stats['total_sellers'] if seller_stats else 0,
    }

    cursor.execute("""
        SELECT orders.id, orders.total_amount, orders.order_date, orders.status,
               users.name AS customer_name, users.email AS customer_email
        FROM orders
        JOIN users ON orders.user_id = users.id
        ORDER BY orders.order_date DESC
        LIMIT 5
    """)
    recent_orders = cursor.fetchall()

    connection.close()
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders)

@app.route('/admin/products')
@admin_required
def admin_products():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT products.id, products.name, products.price, products.description, products.category,
               products.image_url, products.stock,
               COALESCE(users.shop_name, 'Admin Direct') AS seller_name
        FROM products
        LEFT JOIN users ON products.seller_id = users.id
        ORDER BY products.id DESC
    """)
    products = cursor.fetchall()
    connection.close()
    return render_template('admin/products.html', products=products)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip() or 'General'
        price = request.form.get('price', 0)
        description = request.form.get('description', '').strip()
        stock = int(request.form.get('stock', 15) or 15)

        if not name or not price:
            flash("Product name and price are required.")
            return redirect(url_for('admin_add_product'))

        # Handle image upload
        image_file = request.files.get('image')
        filename = 'bag.jpg'
        if image_file and image_file.filename and allowed_file(image_file.filename):
            sec_name = secure_filename(image_file.filename)
            filename = f"{int(time.time())}_{sec_name}"
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO products (name, price, description, category, image_url, stock) VALUES (%s, %s, %s, %s, %s, %s)",
            (name, price, description, category, filename, stock)
        )
        connection.commit()
        connection.close()

        flash("Product added successfully.")
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html', product=None)

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip() or 'General'
        price = request.form.get('price', 0)
        description = request.form.get('description', '').strip()
        stock = int(request.form.get('stock', 15) or 15)

        image_file = request.files.get('image')
        if image_file and image_file.filename and allowed_file(image_file.filename):
            sec_name = secure_filename(image_file.filename)
            filename = f"{int(time.time())}_{sec_name}"
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cursor.execute(
                "UPDATE products SET name = %s, price = %s, description = %s, category = %s, stock = %s, image_url = %s WHERE id = %s",
                (name, price, description, category, stock, filename, product_id)
            )
        else:
            cursor.execute(
                "UPDATE products SET name = %s, price = %s, description = %s, category = %s, stock = %s WHERE id = %s",
                (name, price, description, category, stock, product_id)
            )

        connection.commit()
        connection.close()
        flash("Product updated successfully.")
        return redirect(url_for('admin_products'))

    cursor.execute("SELECT id, name, price, description, category, image_url, stock FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    connection.close()

    if not product:
        flash("Product not found.")
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html', product=product)

@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM cart_items WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM order_items WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    connection.commit()
    connection.close()

    flash("Product deleted successfully.")
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT orders.id, orders.total_amount, orders.order_date, orders.status,
               orders.shipping_address, orders.phone, orders.payment_method, orders.transaction_id,
               users.name AS customer_name, users.email AS customer_email
        FROM orders
        JOIN users ON orders.user_id = users.id
        ORDER BY orders.order_date DESC
    """)
    orders = cursor.fetchall()

    for order in orders:
        cursor.execute("""
            SELECT products.name, order_items.quantity, order_items.price
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = %s
        """, (order['id'],))
        order['order_items'] = cursor.fetchall()

    connection.close()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    new_status = request.form.get('status')
    if new_status:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
        connection.commit()
        connection.close()
        flash(f"Order #{order_id} status updated to '{new_status}'.")
    return redirect(url_for('admin_orders'))


@app.route('/about')
def about():
    return render_template("about.html")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)