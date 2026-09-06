from flask import Flask, render_template, url_for, session, redirect, request, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# pyrefly: ignore [missing-import]
import mysql.connector
from functools import wraps
from dotenv import load_dotenv
import os
import time

load_dotenv()


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
            flash("Kripya pehle login karein!")
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            flash("Access denied! Sirf Admin hi is page ko open kar sakta hai.")
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

@app.route('/')
def home():
    search_query = request.args.get('search', '')
    category = request.args.get('category', '')

    connection = get_db_connection()
    cursor = connection.cursor()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search_query:
        query += " AND name LIKE %s"
        params.append(f"%{search_query}%")

    if category:
        query += " AND category = %s"
        params.append(category)

    cursor.execute(query, tuple(params))
    products = cursor.fetchall()

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    connection.close()
    return render_template('home.html', products=products, categories=categories, search_query=search_query, selected_category=category)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    connection.close()
    return render_template('product_detail.html', product=product)

@app.route('/add-to-cart/<int:product_id>')
@login_required
def add_to_cart(product_id):
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    existing_item = cursor.fetchone()

    if existing_item:
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
    cursor = connection.cursor()

    if action == 'increase':
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

    cursor.execute(
        "SELECT quantity FROM cart_items WHERE user_id = %s AND product_id = %s",
        (user_id, product_id)
    )
    updated = cursor.fetchone()
    new_quantity = updated[0] if updated else 0

    cursor.execute("""
        SELECT SUM(products.price * cart_items.quantity)
        FROM cart_items JOIN products ON cart_items.product_id = products.id
        WHERE cart_items.user_id = %s
    """, (user_id,))
    total_result = cursor.fetchone()
    new_total = float(total_result[0]) if total_result[0] else 0

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
        SELECT products.id, products.name, products.price, cart_items.quantity, products.image_url
        FROM cart_items
        JOIN products ON cart_items.product_id = products.id
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
            'item_total': item_total
        })
        total += item_total

    connection.close()
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if len(password) < 6:
            flash("Password kam se kam 6 characters ka hona chahiye!")
            return redirect(url_for('signup'))

        if len(name.strip()) == 0:
            flash("Naam khaali nahi ho sakta!")
            return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed_password)
            )

            connection.commit()
            connection.close()

            return redirect(url_for('home'))

        except mysql.connector.IntegrityError:
            connection.close()
            flash("Ye email already registered hai! Login karo.")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/place-order')
@login_required
def place_order():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT products.id, products.price, cart_items.quantity
        FROM cart_items
        JOIN products ON cart_items.product_id = products.id
        WHERE cart_items.user_id = %s
    """, (user_id,))
    cart_rows = cursor.fetchall()

    if not cart_rows:
        connection.close()
        return redirect(url_for('cart_page'))

    total_amount = 0
    for row in cart_rows:
        total_amount += float(row[1]) * row[2]

    cursor.execute(
        "INSERT INTO orders (user_id, total_amount, status) VALUES (%s, %s, %s)",
        (user_id, total_amount, 'Pending')
    )
    order_id = cursor.lastrowid

    for row in cart_rows:
        product_id = row[0]
        price = row[1]
        quantity = row[2]
        cursor.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, quantity, price)
        )

    cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))

    connection.commit()
    connection.close()
    return redirect(url_for('order_success', order_id=order_id))

@app.route('/order-success/<int:order_id>')
@login_required
def order_success(order_id):
    return render_template('order_success.html', order_id=order_id)

@app.route('/orders')
@login_required
def order_history():
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT id, total_amount, order_date, status FROM orders WHERE user_id = %s ORDER BY order_date DESC",
        (user_id,)
    )
    orders = cursor.fetchall()

    all_orders = []
    for order in orders:
        order_id = order[0]
        cursor.execute("""
            SELECT products.name, order_items.quantity, order_items.price
            FROM order_items
            JOIN products ON order_items.product_id = products.id
            WHERE order_items.order_id = %s
        """, (order_id,))
        items = cursor.fetchall()

        all_orders.append({
            'id': order_id,
            'total_amount': order[1],
            'order_date': order[2],
            'status': order[3] if len(order) > 3 and order[3] else 'Pending',
            'products': items
        })

    connection.close()
    return render_template('order_history.html', all_orders=all_orders)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT id, name, email, password, is_admin FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        connection.close()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['is_admin'] = bool(user[4]) if len(user) > 4 and user[4] else False
            if session['is_admin']:
                flash(f"Welcome Admin, {user[1]}!")
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        else:
            flash("Galat email ya password!")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

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

    stats = {
        'total_revenue': float(order_stats['total_revenue']) if order_stats else 0.0,
        'total_orders': order_stats['total_orders'] if order_stats else 0,
        'total_products': product_stats['total_products'] if product_stats else 0,
        'total_users': user_stats['total_users'] if user_stats else 0,
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
    cursor.execute("SELECT id, name, price, description, category, image_url FROM products ORDER BY id DESC")
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

        if not name or not price:
            flash("Product name aur price zaroori hain!")
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
            "INSERT INTO products (name, price, description, category, image_url) VALUES (%s, %s, %s, %s, %s)",
            (name, price, description, category, filename)
        )
        connection.commit()
        connection.close()

        flash("Naya product safalta-purvak add ho gaya!")
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

        image_file = request.files.get('image')
        if image_file and image_file.filename and allowed_file(image_file.filename):
            sec_name = secure_filename(image_file.filename)
            filename = f"{int(time.time())}_{sec_name}"
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cursor.execute(
                "UPDATE products SET name = %s, price = %s, description = %s, category = %s, image_url = %s WHERE id = %s",
                (name, price, description, category, filename, product_id)
            )
        else:
            cursor.execute(
                "UPDATE products SET name = %s, price = %s, description = %s, category = %s WHERE id = %s",
                (name, price, description, category, product_id)
            )

        connection.commit()
        connection.close()
        flash("Product details update ho gayi hain!")
        return redirect(url_for('admin_products'))

    cursor.execute("SELECT id, name, price, description, category, image_url FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    connection.close()

    if not product:
        flash("Product nahi mila!")
        return redirect(url_for('admin_products'))

    return render_template('admin/product_form.html', product=product)

@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM cart_items WHERE product_id = %s", (product_id,))
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    connection.commit()
    connection.close()

    flash("Product delete kar diya gaya hai.")
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT orders.id, orders.total_amount, orders.order_date, orders.status,
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
        flash(f"Order #{order_id} ka status '{new_status}' update ho gaya!")
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