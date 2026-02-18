import os
import sys
import json
import uuid
import requests
from flask import Flask, render_template, session, jsonify, request, redirect, url_for

# Import PocketBase helper
from services.pocketbaseapi import get_all_products, get_client, COLLECTION_NAME

# ======================
# CONDITIONAL .ENV LOADING
# ======================
if os.getenv('FLASK_ENV', 'production').strip().lower() == 'development' and os.path.exists('.env'):
    try:
        from dotenv import load_dotenv
        load_dotenv()
        if '--no-dotenv' not in sys.argv:
            print("✓ Loaded configuration from .env file", file=sys.stderr)
    except ImportError:
        print("⚠️  WARNING: Install python-dotenv for .env support:", file=sys.stderr)

# ======================
# ENVIRONMENT CONFIGURATION
# ======================
FLASK_ENV = os.getenv('FLASK_ENV', 'production').strip().lower()
IS_DEV = FLASK_ENV == 'development'
app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do')

# SECRET_KEY HANDLING
if IS_DEV:
    app.secret_key = os.getenv('SECRET_KEY', 'secretcode')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
else:
    secret = os.getenv('SECRET_KEY', 'RcnaZ6u0dC3xlnu6WDiTZrcPochP0WR6I/CxiGmNV6/jDBkWTtCpc0HeZ4zxPMcS').strip()
    if not secret or len(secret) < 32:
        # Fallback for dev if not set properly, but strict in prod
        if not IS_DEV:
            raise ValueError("❌ SECURITY ERROR: SECRET_KEY not set or too weak in production!")
    app.secret_key = secret
    app.config['TEMPLATES_AUTO_RELOAD'] = False

# ======================
# HELPER: Fetch Fresh Products
# ======================
PRODUCTS_CACHE = []

def fetch_fresh_products():
    """Fetches products directly from PocketBase."""
    global PRODUCTS_CACHE
    try:
        fresh_products = get_all_products()
        if fresh_products:
            PRODUCTS_CACHE = fresh_products
            return fresh_products
        else:
            print("⚠️ PocketBase returned empty list, using cache.", file=sys.stderr)
            return PRODUCTS_CACHE
    except Exception as e:
        print(f"❌ Error fetching fresh products: {str(e)}. Using cache.", file=sys.stderr)
        return PRODUCTS_CACHE

# Initialize cache on startup
try:
    PRODUCTS_CACHE = get_all_products()
    if PRODUCTS_CACHE:
        print(f"✅ Initial load: {len(PRODUCTS_CACHE)} products cached.", file=sys.stderr)
except Exception as e:
    print(f"⚠️ Initial load failed: {str(e)}", file=sys.stderr)

# ======================
# COUPON LOADING
# ======================
try:
    with open('coupons.json') as f:
        COUPONS = json.load(f)
except FileNotFoundError:
    COUPONS = {"50_percent": [], "25_percent": [], "10_percent": [], "bogo_hoodie": [], "bogo_cap": []}
except json.JSONDecodeError:
    COUPONS = {"50_percent": [], "25_percent": [], "10_percent": [], "bogo_hoodie": [], "bogo_cap": []}

# ======================
# SESSION MANAGEMENT
# ======================
@app.before_request
def init_cart():
    if 'cart' not in session:
        session['cart'] = []

# ======================
# HELPER: Compare variants
# ======================
def variants_match(v1, v2):
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
    return (v1.get('color') == v2.get('color')) and (v1.get('size') == v2.get('size'))

# ======================
# API ENDPOINTS
# ======================
@app.route('/api/cart/state')
def get_cart_state():
    cart = session.get('cart', [])
    distinct_count = len(cart)
    # Ensure IDs are strings
    cart_dict = {str(item['id']): item['quantity'] for item in cart}
    return jsonify({
        'success': True,
        'cart': cart,
        'distinct_count': distinct_count,
        'cart_dict': cart_dict
    })

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    try:
        data = request.get_json()
        if not data or 'product_id' not in data:
            return jsonify({'success': False, 'error': 'Invalid request payload'}), 400
        
        # CRITICAL FIX: Treat ID as String immediately
        product_id_str = str(data['product_id'])
        quantity = int(data.get('quantity', 1))
        variant = data.get('variant')
        
        if quantity < 1:
            return jsonify({'success': False, 'error': 'Quantity must be at least 1'}), 400
        
        # Fetch fresh products to ensure new items are found
        current_products = fetch_fresh_products()
        
        # CRITICAL FIX: Compare String to String
        product = next((p for p in current_products if str(p['id']) == product_id_str), None)
        
        if not product:
            # Debug log to help you see what's happening
            print(f"❌ Product Not Found: Looking for '{product_id_str}'. Available IDs: {[str(p['id']) for p in current_products[:5]]}...", file=sys.stderr)
            return jsonify({'success': False, 'error': 'Product not found in catalog'}), 404
        
        cart = session.get('cart', [])
        existing_item = None
        
        for item in cart:
            if str(item['id']) == product_id_str and variants_match(item.get('variant'), variant):
                existing_item = item
                break
        
        if existing_item:
            existing_item['quantity'] += quantity
        else:
            product_image_url = ""
            if 'images' in product and isinstance(product['images'], list) and len(product['images']) > 0:
                product_image_url = product['images'][0]
            elif 'image' in product:
                product_image_url = product['image']
            else:
                product_image_url = '/static/placeholder.png'
            
            new_item = {
                'id': product['id'], # Keep as String
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'image': product_image_url
            }
            if variant is not None:
                new_item['variant'] = variant
            cart.append(new_item)
        
        session['cart'] = cart
        session.modified = True
        
        cart_dict = {str(item['id']): item['quantity'] for item in cart}
        distinct_count = len(cart)
        
        return jsonify({
            'success': True,
            'cart_count': distinct_count,
            'cart_dict': cart_dict,
            'message': f"{product['name']} added to cart!",
            'quantity': next(item['quantity'] for item in cart if str(item['id']) == product_id_str and variants_match(item.get('variant'), variant))
        })
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': f'Invalid data format: {str(e)}'}), 400
    except Exception as e:
        app.logger.error(f"Cart add error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/update-cart', methods=['POST'])
def update_cart():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        variant = data.get('variant')
        
        if product_id is None or quantity is None:
            return jsonify({'success': False, 'message': 'Missing product_id or quantity'}), 400
        if quantity < 1:
            return jsonify({'success': False, 'message': 'Quantity must be at least 1'}), 400
        
        cart = session.get('cart', [])
        item_found = False
        
        for item in cart:
            variant_match = True
            if variant:
                variant_match = (
                    item.get('variant', {}).get('color') == variant.get('color') and
                    item.get('variant', {}).get('size') == variant.get('size')
                )
            # Compare as Strings
            if str(item['id']) == str(product_id) and variant_match:
                item['quantity'] = quantity
                item_found = True
                break
        
        if not item_found:
            return jsonify({'success': False, 'message': 'Item not found in cart'}), 404
        
        session['cart'] = cart
        session.modified = True
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        cart_count = sum(item['quantity'] for item in cart)
        
        return jsonify({
            'success': True,
            'subtotal': subtotal,
            'cart_count': cart_count,
            'message': 'Cart updated successfully'
        })
    except Exception as e:
        print(f"Error updating cart: {str(e)}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        variant = data.get('variant')
        cart = session.get('cart', [])
        
        cart = [
            item for item in cart
            if not (
                str(item['id']) == str(product_id) and
                (not variant or (
                    item.get('variant', {}).get('color') == variant.get('color') and
                    item.get('variant', {}).get('size') == variant.get('size')
                ))
            )
        ]
        
        session['cart'] = cart
        session.modified = True
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        cart_count = sum(item['quantity'] for item in cart)
        
        return jsonify({
            'success': True,
            'subtotal': subtotal,
            'cart_count': cart_count,
            'message': 'Item removed from cart'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/clear-cart', methods=['POST'])
def clear_cart_page():
    session['cart'] = []
    session.modified = True
    return jsonify({'success': True, 'subtotal': 0, 'cart_count': 0, 'message': 'Cart cleared successfully'})

@app.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    session['cart'] = []
    session.modified = True
    return jsonify({'success': True, 'message': 'Cart cleared successfully', 'cart_count': 0, 'cart_dict': {}})

@app.route('/api/coupon/validate', methods=['POST'])
def validate_coupon():
    try:
        data = request.get_json()
        code = data.get('code', '').strip().upper()
        subtotal = float(data.get('subtotal', 0))
        cart_items = session.get('cart', [])
        
        if not code:
            return jsonify({'success': False, 'error': 'Coupon code is required'}), 400
        
        valid_50 = [c.strip() for c in COUPONS.get('50_percent', []) if isinstance(c, str)]
        valid_25 = [c.strip() for c in COUPONS.get('25_percent', []) if isinstance(c, str)]
        valid_10 = [c.strip() for c in COUPONS.get('10_percent', []) if isinstance(c, str)]
        valid_bogo_hoodie = [c.strip() for c in COUPONS.get('bogo_hoodie', []) if isinstance(c, str)]
        valid_bogo_cap = [c.strip() for c in COUPONS.get('bogo_cap', []) if isinstance(c, str)]
        
        current_products = fetch_fresh_products()

        def get_product_by_id(pid):
            return next((p for p in current_products if str(p.get('id')) == str(pid)), None)
        
        target_tag = None
        error_msg = ''
        
        if code in valid_bogo_hoodie:
            target_tag = 'hoodie'
            error_msg = 'Add at least 1 hoodies to use this coupon'
        elif code in valid_bogo_cap:
            target_tag = 'cap'
            error_msg = 'Add at least 1 caps to use this coupon'
        
        if target_tag:
            qualifying_items = []
            for item in cart_items:
                product = get_product_by_id(item['id'])
                if not product:
                    continue
                tags = product.get('tags', [])
                if isinstance(tags, list) and any(t.lower() == target_tag for t in tags):
                    qualifying_items.append({'price': item['price'], 'quantity': item['quantity']})
            
            total_count = sum(h['quantity'] for h in qualifying_items)
            if total_count < 1:
                return jsonify({'success': False, 'error': error_msg}), 400
            
            cheapest_price = min(h['price'] for h in qualifying_items)
            discount_amount = round(cheapest_price, 2)
            final_amount = subtotal - discount_amount
            
            return jsonify({
                'success': True,
                'discount_percent': 0,
                'discount_amount': discount_amount,
                'final_amount': final_amount,
                'message': f'BOGO: One {target_tag} free!'
            })
        
        elif code in valid_50: discount_percent = 50
        elif code in valid_25: discount_percent = 25
        elif code in valid_10: discount_percent = 10
        else:
            return jsonify({'success': False, 'error': 'Invalid or expired coupon'}), 400
        
        discount_amount = round(subtotal * (discount_percent / 100), 2)
        final_amount = subtotal - discount_amount
        
        return jsonify({
            'success': True,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'final_amount': final_amount,
            'message': f'{discount_percent}% discount applied!'
        })
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid subtotal value'}), 400
    except Exception as e:
        app.logger.error(f"Coupon validation error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ======================
# PAGE ROUTES
# ======================
@app.route('/')
def products():
    current_products = fetch_fresh_products()
    cart = session.get('cart', [])
    cart_dict = {str(item['id']): item['quantity'] for item in cart}
    return render_template('products.html', products=current_products, cart_dict=cart_dict)

@app.route('/product/<pid>')
def product_detail(pid):
    current_products = fetch_fresh_products()
    # Ensure pid is treated as string for comparison
    product = next((p for p in current_products if str(p['id']) == str(pid)), None)
    if not product:
        return render_template('error.html', message="Product not found", status_code=404), 404
    
    cart = session.get('cart', [])
    cart_dict = {str(item['id']): item['quantity'] for item in cart}
    in_cart = any(str(item['id']) == str(pid) for item in cart)
    qty = next((item['quantity'] for item in cart if str(item['id']) == str(pid)), 0)
    
    return render_template(
        'product_detail.html',
        product=product,
        in_cart=in_cart,
        cart_quantity=qty
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

@app.route('/personal-detail/submit', methods=['POST'])
def submit_personal_detail():
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('cart'))
    
    full_name = request.form.get('full_name', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    postal_code = request.form.get('postal_code', '').strip()
    phone = request.form.get('phone', '').strip()
    
    if not all([full_name, address, city, postal_code, phone]):
        return redirect(url_for('error_page', message='All personal details are required.'))
    
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    total = subtotal
    order_id = str(uuid.uuid4())
    session['order_id'] = order_id
    
    webhook_payload = {
        "id": order_id,
        "payment": 'False',
        "personal_details": {
            "full_name": full_name, "address": address, "city": city,
            "postal_code": postal_code, "phone": phone
        },
        "order": {
            "items": [
                {
                    "id": item['id'], "name": item['name'], "price": item['price'],
                    "quantity": item['quantity'], "total_price": item['price'] * item['quantity'],
                    "variant": item.get('variant')
                } for item in cart_items
            ],
            "subtotal": subtotal, "total": total, "currency": "INR"
        }
    }
    
    webhook_url = 'https://n8n.arngct.org/webhook/demo'
    if webhook_url:
        try:
            response = requests.post(webhook_url, json=webhook_payload, headers={'Content-Type': 'application/json'}, timeout=10)
            if response.status_code not in (200, 201, 202, 204):
                app.logger.warning(f"Webhook returned {response.status_code}: {response.text}")
        except Exception as e:
            app.logger.error(f"Webhook delivery failed: {str(e)}")
    
    session['personal_details'] = {
        'full_name': full_name, 'address': address, 'city': city,
        'postal_code': postal_code, 'phone': phone
    }
    session.modified = True
    return redirect(url_for('payment'))

@app.route('/payment')
def payment():
    cart_items = session.get('cart', [])
    if not cart_items:
        return redirect(url_for('cart'))
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    amount_paise = int(subtotal * 100)
    personal_details = session.get('personal_details', {})
    
    return render_template(
        'payment.html',
        amount=amount_paise,
        full_name=personal_details.get('full_name', ''),
        phone=personal_details.get('phone', '')
    )

@app.route('/payment/success', methods=['POST'])
def payment_success():
    try:
        data = request.get_json()
        if not data or 'razorpay_payment_id' not in data:
            app.logger.warning("Invalid payment success payload")
            return jsonify({'success': False}), 400
        
        order_id = session.get('order_id')
        if not order_id:
            app.logger.error("No order_id found in session during payment success")
            return jsonify({'success': False, 'error': 'Missing order ID'}), 400
        
        webhook_url = 'https://n8n.arngct.org/webhook/paymentstatus'
        try:
            webhook_resp = requests.post(webhook_url, json={'order_id': order_id}, headers={'Content-Type': 'application/json'}, timeout=10)
            if webhook_resp.status_code not in (200, 201, 202, 204):
                app.logger.warning(f"Payment status webhook failed ({webhook_resp.status_code}): {webhook_resp.text}")
        except Exception as e:
            app.logger.error(f"Failed to call payment status webhook: {str(e)}")
        
        session['payment_successful'] = True
        session.pop('cart', None)
        session.pop('personal_details', None)
        session.modified = True
        return jsonify({'success': True}), 200
    except Exception as e:
        app.logger.error(f"Payment success handler error: {str(e)}")
        return jsonify({'success': False}), 500

@app.route('/confirm')
def confirm():
    if not session.get('payment_successful'):
        return render_template('error.html', message="Access denied. Payment confirmation required."), 403
    session.pop('payment_successful', None)
    session.modified = True
    return render_template('confirm.html')

@app.route('/error')
def error_page():
    message = request.args.get('message', 'An unexpected error occurred')
    return render_template('error.html', message=message), 400

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message="Page not found", status_code=404), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.error(f"Server error: {str(e)}")
    return render_template('error.html', message="Internal server error", status_code=500), 500

@app.route('/health')
def health_check():
    current_products = fetch_fresh_products()
    return jsonify({
        'status': 'ok',
        'environment': FLASK_ENV,
        'debug': app.debug,
        'cart_items': len(session.get('cart', [])),
        'products_loaded': len(current_products)
    }), 200

# ======================
# DEVELOPMENT SERVER
# ======================
if __name__ == '__main__':
    if not IS_DEV:
        print("\n❌ CRITICAL: DO NOT RUN WITH 'python app.py' IN PRODUCTION", file=sys.stderr)
        print("✅ DEPLOY WITH GUNICORN INSTEAD:", file=sys.stderr)
        print("   gunicorn -w 4 -b 0.0.0.0:$PORT app:app\n", file=sys.stderr)
        sys.exit(1)
    
    port = int(os.getenv('PORT', 3000))
    host = os.getenv('HOST', '0.0.0.0')
    print(f"\n🚀 Starting DEVELOPMENT server at http://{host}:{port}", file=sys.stderr)
    print(f"   Environment: {FLASK_ENV} | Debug: {app.debug}", file=sys.stderr)
    print(f"   Products Source: PocketBase (Fresh Fetch Enabled)\n", file=sys.stderr)
    app.run(debug=True, host=host, port=port)