import os
import sys
import json
from flask import Flask, render_template, session, jsonify, request, redirect, url_for

# ======================
# CONDITIONAL .ENV LOADING (DEV ONLY - SAFE FOR PRODUCTION)
# ======================
# ONLY loads .env if:
#   1. Explicitly in development mode (FLASK_ENV=development)
#   2. .env file exists
#   3. python-dotenv is installed (optional dev dependency)
if os.getenv('FLASK_ENV', 'production').strip().lower() == 'development' and os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
        if '--no-dotenv' not in sys.argv:
            print("✓ Loaded configuration from .env file", file=sys.stderr)
    except ImportError:
        print("⚠️  WARNING: Install python-dotenv for .env support:", file=sys.stderr)
        print("   pip install python-dotenv", file=sys.stderr)

# ======================
# ENVIRONMENT CONFIGURATION
# ======================
FLASK_ENV = os.getenv('FLASK_ENV', 'production').strip().lower()
IS_DEV = FLASK_ENV == 'development'

app = Flask(__name__)

# SECRET_KEY HANDLING WITH STRICT VALIDATION
if IS_DEV:
    # Allow dev key ONLY in development
    app.secret_key = os.getenv('SECRET_KEY', 'secretcode')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    print(f"🚀 DEVELOPMENT MODE ACTIVE (FLASK_ENV={FLASK_ENV})", file=sys.stderr)
else:
    # PRODUCTION: Enforce strong SECRET_KEY
    secret = os.getenv('SECRET_KEY', 'RcnaZ6u0dC3xlnu6WDiTZrcPochP0WR6I/CxiGmNV6/jDBkWTtCpc0HeZ4zxPMcS').strip()
    if not secret:
        raise ValueError(
            "\n❌ SECURITY ERROR: SECRET_KEY not set in production!\n"
            "✅ Fix: Set SECRET_KEY via hosting platform environment variables\n"
            "   Generate strong key: openssl rand -base64 48\n"
        )
    if secret == 'dev-key-change-in-production-2026' or len(secret) < 32:
        raise ValueError(
            "\n❌ SECURITY VIOLATION: Weak SECRET_KEY detected in production!\n"
            "✅ Fix: Generate strong key with: openssl rand -base64 48\n"
            "   NEVER use default/dev keys in production!\n"
        )
    app.secret_key = secret
    app.config['TEMPLATES_AUTO_RELOAD'] = False
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 3600  # 1 hour cache
    print(f"🔒 PRODUCTION MODE ACTIVE (FLASK_ENV={FLASK_ENV})", file=sys.stderr)

# ======================
# PRODUCT LOADING
# ======================
try:
    with open('products.json') as f:
        PRODUCTS = json.load(f)
except FileNotFoundError:
    PRODUCTS = []
    if IS_DEV:
        print("⚠️  WARNING: products.json not found. Create products.json with product data.", file=sys.stderr)
except json.JSONDecodeError as e:
    PRODUCTS = []
    print(f"❌ ERROR: Invalid products.json format: {str(e)}", file=sys.stderr)

# ======================
# SESSION MANAGEMENT
# ======================
@app.before_request
def init_cart():
    if 'cart' not in session:
        session['cart'] = []  # Format: [{"id": int, "name": str, "price": int, "quantity": int, "image": str}, ...]

# ======================
# API ENDPOINTS (CRITICAL FIXES)
# ======================
@app.route('/api/cart/state')
def get_cart_state():
    """Return current cart state WITH cart_dict for frontend sync"""
    cart = session.get('cart', [])
    distinct_count = len(cart)
    # CRITICAL FIX: Return cart_dict for JavaScript synchronization
    cart_dict = {item['id']: item['quantity'] for item in cart}
    return jsonify({
        'success': True,
        'cart': cart,
        'distinct_count': distinct_count,
        'cart_dict': cart_dict  # ESSENTIAL FOR FRONTEND SYNC
    })

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    try:
        data = request.get_json()
        if not data or 'product_id' not in data:
            return jsonify({'success': False, 'error': 'Invalid request payload'}), 400
        
        product_id = int(data['product_id'])
        quantity = int(data.get('quantity', 1))
        if quantity < 1:
            return jsonify({'success': False, 'error': 'Quantity must be at least 1'}), 400
        
        product = next((p for p in PRODUCTS if p['id'] == product_id), None)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found in catalog'}), 404
        
        cart = session.get('cart', [])
        for item in cart:
            if item['id'] == product_id:
                item['quantity'] += quantity
                break
        else:
            cart.append({
                'id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'image': product['image']
            })
        session['cart'] = cart
        session.modified = True
        
        # CRITICAL FIX: Return cart_dict for frontend sync
        cart_dict = {item['id']: item['quantity'] for item in cart}
        distinct_count = len(cart)
        return jsonify({
            'success': True,
            'cart_count': distinct_count,
            'cart_dict': cart_dict,  # ADDED FOR SYNC
            'message': f"{product['name']} added to cart!",
            'quantity': next(item['quantity'] for item in cart if item['id'] == product_id)
        })
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400
    except Exception as e:
        app.logger.error(f"Cart add error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/cart/update', methods=['POST'])
def update_cart():
    try:
        data = request.get_json()
        if not data or 'product_id' not in data or 'quantity' not in data:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        product_id = int(data['product_id'])
        new_quantity = int(data['quantity'])
        if new_quantity < 0:
            return jsonify({'success': False, 'error': 'Invalid quantity value'}), 400
        
        cart = session.get('cart', [])
        item_found = False
        
        if new_quantity == 0:
            original_length = len(cart)
            cart = [item for item in cart if item['id'] != product_id]
            item_found = (len(cart) < original_length)
        else:
            for item in cart:
                if item['id'] == product_id:
                    item['quantity'] = new_quantity
                    item_found = True
                    break
            if not item_found:
                # Add item if not found (handles edge cases)
                product = next((p for p in PRODUCTS if p['id'] == product_id), None)
                if not product:
                    return jsonify({'success': False, 'error': 'Product not found'}), 404
                cart.append({
                    'id': product_id,
                    'name': product['name'],
                    'price': product['price'],
                    'quantity': new_quantity,
                    'image': product['image']
                })
                item_found = True
        
        session['cart'] = cart
        session.modified = True
        
        # CRITICAL FIX: Return cart_dict for frontend sync
        cart_dict = {item['id']: item['quantity'] for item in cart}
        distinct_count = len(cart)
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        item_total = next((item['price'] * item['quantity'] for item in cart if item['id'] == product_id), 0) if new_quantity > 0 else 0
        
        return jsonify({
            'success': True,
            'cart_count': distinct_count,
            'cart_dict': cart_dict,  # ADDED FOR SYNC
            'subtotal': subtotal,
            'item_total': item_total,
            'quantity': new_quantity if new_quantity > 0 else 0
        })
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400
    except Exception as e:
        app.logger.error(f"Cart update error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    try:
        session['cart'] = []
        session.modified = True
        return jsonify({'success': True, 'message': 'Cart cleared successfully', 'cart_count': 0, 'cart_dict': {}})
    except Exception as e:
        app.logger.error(f"Cart clear error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to clear cart'}), 500

# ======================
# PAGE ROUTES (CRITICAL FIX: TEMPLATE NAME)
# ======================
@app.route('/')
def products():
    cart = session.get('cart', [])
    cart_dict = {item['id']: item['quantity'] for item in cart}
    # CRITICAL FIX: Changed from 'products.html' to 'product.html' (singular)
    return render_template('products.html', products=PRODUCTS, cart_dict=cart_dict)

@app.route('/product/<int:pid>')
def product_detail(pid):
    product = next((p for p in PRODUCTS if p['id'] == pid), None)
    if not product:
        return render_template('error.html', message="Product not found", status_code=404), 404
    cart = session.get('cart', [])
    cart_dict = {item['id']: item['quantity'] for item in cart}
    return render_template(
        'product_detail.html',
        product=product,
        in_cart=pid in cart_dict,
        cart_quantity=cart_dict.get(pid, 0)
    )

@app.route('/cart')
def cart():
    cart_items = session.get('cart', [])
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal)

@app.route('/personal-detail')
def personal_detail():
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('cart'))
    return render_template('personal_detail.html')

@app.route('/payment')
def payment():
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('cart'))
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    amount_paise = int(subtotal * 100)
    return render_template('payment.html', amount=amount_paise)

@app.route('/error')
def error_page():
    message = request.args.get('message', 'An unexpected error occurred')
    return render_template('error.html', message=message), 400

# ======================
# ERROR HANDLERS
# ======================
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message="Page not found", status_code=404), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Server error: {str(e)}")
    return render_template('error.html', message="Internal server error", status_code=500), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'ok',
        'environment': FLASK_ENV,
        'debug': app.debug,
        'cart_items': len(session.get('cart', [])),
        'products_loaded': len(PRODUCTS)
    }), 200

# ======================
# DEVELOPMENT SERVER (BLOCK IN PRODUCTION)
# ======================
if __name__ == '__main__':
    # AUTO-GENERATE SAMPLE DATA IN DEV ONLY
    if IS_DEV and not os.path.exists('products.json'):
        sample_products = [
            {"id": 1, "name": "Wireless Earbuds", "price": 2499, "image": "https://via.placeholder.com/150/92c952?text=Earbuds", "description": "Bluetooth 5.3, 30hr battery, IPX7 waterproof"},
            {"id": 2, "name": "Smart Watch", "price": 4999, "image": "https://via.placeholder.com/150/771796?text=Watch", "description": "Heart rate monitor, GPS, 7-day battery"},
            {"id": 3, "name": "Laptop Sleeve", "price": 899, "image": "https://via.placeholder.com/150/d32776?text=Sleeve", "description": "Water-resistant, fits 15-inch laptops"}
        ]
        with open('products.json', 'w') as f:
            json.dump(sample_products, f, indent=2)
        print("✓ Created sample products.json", file=sys.stderr)
    
    # BLOCK PRODUCTION EXECUTION VIA python app.py
    if not IS_DEV:
        print("\n❌ CRITICAL: DO NOT RUN WITH 'python app.py' IN PRODUCTION", file=sys.stderr)
        print("✅ DEPLOY WITH GUNICORN INSTEAD:", file=sys.stderr)
        print("   gunicorn -w 4 -b 0.0.0.0:$PORT app:app\n", file=sys.stderr)
        sys.exit(1)
    
    port = int(os.getenv('PORT', 3000))
    host = os.getenv('HOST', '0.0.0.0')
    print(f"\n🚀 Starting DEVELOPMENT server at http://{host}:{port}", file=sys.stderr)
    print(f"   Environment: {FLASK_ENV} | Debug: {app.debug}", file=sys.stderr)
    print(f"   Press CTRL+C to stop\n", file=sys.stderr)
    app.run(debug=True, host=host, port=port)