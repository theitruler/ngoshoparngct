import os
import sys
import json
import uuid
import requests
from flask import Flask, render_template, session, jsonify, request, redirect, url_for

# ======================
# CONDITIONAL .ENV LOADING (DEV ONLY - SAFE FOR PRODUCTION)
# ======================
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
app.jinja_env.add_extension('jinja2.ext.do') 

# SECRET_KEY HANDLING WITH STRICT VALIDATION
if IS_DEV:
    app.secret_key = os.getenv('SECRET_KEY', 'secretcode')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    print(f"🚀 DEVELOPMENT MODE ACTIVE (FLASK_ENV={FLASK_ENV})", file=sys.stderr)
else:
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
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 3600
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
# COUPON LOADING
# ======================
try:
    with open('coupons.json') as f:
        COUPONS = json.load(f)
except FileNotFoundError:
    COUPONS = {"50_percent": [], "25_percent": []}
    if IS_DEV:
        print("⚠️  WARNING: coupons.json not found. Coupon validation disabled.", file=sys.stderr)
except json.JSONDecodeError as e:
    COUPONS = {"50_percent": [], "25_percent": []}
    print(f"❌ ERROR: Invalid coupons.json format: {str(e)}", file=sys.stderr)

# ======================
# SESSION MANAGEMENT
# ======================
@app.before_request
def init_cart():
    if 'cart' not in session:
        session['cart'] = []

# ======================
# HELPER: Compare variants (for cart logic)
# ======================
def variants_match(v1, v2):
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False
    return v1 == v2

# ======================
# API ENDPOINTS (CRITICAL FIXES + VARIANT SUPPORT)
# ======================

@app.route('/api/cart/state')
def get_cart_state():
    cart = session.get('cart', [])
    distinct_count = len(cart)
    cart_dict = {item['id']: item['quantity'] for item in cart}
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

        product_id = int(data['product_id'])
        quantity = int(data.get('quantity', 1))
        variant = data.get('variant')  # May be dict or None

        if quantity < 1:
            return jsonify({'success': False, 'error': 'Quantity must be at least 1'}), 400

        product = next((p for p in PRODUCTS if p['id'] == product_id), None)
        if not product:
            return jsonify({'success': False, 'error': 'Product not found in catalog'}), 404

        cart = session.get('cart', [])

        # Check if same product + same variant already exists
        existing_item = None
        for item in cart:
            if item['id'] == product_id and variants_match(item.get('variant'), variant):
                existing_item = item
                break

        if existing_item:
            existing_item['quantity'] += quantity
        else:
            new_item = {
                'id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'image': product['image']
            }
            if variant is not None:
                new_item['variant'] = variant
            cart.append(new_item)

        session['cart'] = cart
        session.modified = True

        cart_dict = {item['id']: item['quantity'] for item in cart}
        distinct_count = len(cart)
        return jsonify({
            'success': True,
            'cart_count': distinct_count,
            'cart_dict': cart_dict,
            'message': f"{product['name']} added to cart!",
            'quantity': next(item['quantity'] for item in cart if item['id'] == product_id and variants_match(item.get('variant'), variant))
        })
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400
    except Exception as e:
        app.logger.error(f"Cart add error: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


# Add this to your Flask app.py or routes file

from flask import Flask, request, jsonify, session

@app.route('/update-cart', methods=['POST'])
def update_cart():
    """
    Update cart item quantity
    Expects JSON: {product_id: int, quantity: int, variant: dict (optional)}
    Returns: {success: bool, subtotal: float, cart_count: int, message: str}
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        product_id = data.get('product_id')
        quantity = data.get('quantity')
        variant = data.get('variant')
        
        if product_id is None or quantity is None:
            return jsonify({
                'success': False,
                'message': 'Missing product_id or quantity'
            }), 400
        
        if quantity < 1:
            return jsonify({
                'success': False,
                'message': 'Quantity must be at least 1'
            }), 400
        
        # Get cart from session (adjust based on your cart storage method)
        cart = session.get('cart', [])
        
        # Find and update the item
        item_found = False
        for item in cart:
            # Match by product_id and variant (if applicable)
            variant_match = True
            if variant:
                variant_match = (
                    item.get('variant', {}).get('color') == variant.get('color') and
                    item.get('variant', {}).get('size') == variant.get('size')
                )
            
            if item['id'] == product_id and variant_match:
                item['quantity'] = quantity
                item_found = True
                break
        
        if not item_found:
            return jsonify({
                'success': False,
                'message': 'Item not found in cart'
            }), 404
        
        # Update session
        session['cart'] = cart
        session.modified = True
        
        # Calculate new subtotal
        subtotal = sum(item['price'] * item['quantity'] for item in cart)
        
        # Calculate total item count
        cart_count = sum(item['quantity'] for item in cart)
        
        return jsonify({
            'success': True,
            'subtotal': subtotal,
            'cart_count': cart_count,
            'message': 'Cart updated successfully'
        })
        
    except Exception as e:
        print(f"Error updating cart: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500


# Optional: Add a remove from cart route
@app.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    """
    Remove item from cart
    Expects JSON: {product_id: int, variant: dict (optional)}
    """
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        variant = data.get('variant')
        
        cart = session.get('cart', [])
        
        # Filter out the item to remove
        cart = [
            item for item in cart
            if not (
                item['id'] == product_id and
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
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500



@app.route('/clear-cart', methods=['POST'])
def clear_cart_page():
    """
    Clear all items from cart (for cart.html page)
    Returns: {success: bool, message: str}
    """
    try:
        # Clear the cart in session
        session['cart'] = []
        session.modified = True
        
        return jsonify({
            'success': True,
            'subtotal': 0,
            'cart_count': 0,
            'message': 'Cart cleared successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error clearing cart: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Server error: {str(e)}'
        }), 500


@app.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    try:
        session['cart'] = []
        session.modified = True
        return jsonify({'success': True, 'message': 'Cart cleared successfully', 'cart_count': 0, 'cart_dict': {}})
    except Exception as e:
        app.logger.error(f"Cart clear error: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to clear cart'}), 500

@app.route('/api/coupon/validate', methods=['POST'])
def validate_coupon():
    try:
        data = request.get_json()
        code = data.get('code', '').strip().upper()
        subtotal = float(data.get('subtotal', 0))
        cart_items = session.get('cart', [])

        if not code:
            return jsonify({'success': False, 'error': 'Coupon code is required'}), 400

        # Normalize coupon lists
        valid_50 = [c.strip() for c in COUPONS.get('50_percent', []) if isinstance(c, str)]
        valid_25 = [c.strip() for c in COUPONS.get('25_percent', []) if isinstance(c, str)]
        valid_10 = [c.strip() for c in COUPONS.get('10_percent', []) if isinstance(c, str)]
        valid_bogo_hoodie = [c.strip() for c in COUPONS.get('bogo_hoodie', []) if isinstance(c, str)]
        valid_bogo_cap = [c.strip() for c in COUPONS.get('bogo_cap', []) if isinstance(c, str)]

        # Helper: Find product by ID
        def get_product_by_id(pid):
            return next((p for p in PRODUCTS if p.get('id') == pid), None)

        # BOGO HOODIE
        if code in valid_bogo_hoodie:
            target_tag = 'hoodie'
            error_msg = 'Add at least 1 hoodies to use this coupon'
        # BOGO CAP
        elif code in valid_bogo_cap:
            target_tag = 'cap'
            error_msg = 'Add at least 1 caps to use this coupon'
        else:
            target_tag = None

        # Handle BOGO types
        if target_tag:
            qualifying_items = []
            for item in cart_items:
                product = get_product_by_id(item['id'])
                if not product:
                    continue
                tags = product.get('tags', [])
                if isinstance(tags, list) and any(t.lower() == target_tag for t in tags):
                    qualifying_items.append({
                        'price': item['price'],
                        'quantity': item['quantity']
                    })

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

        # Standard % discounts
        elif code in valid_50:
            discount_percent = 50
        elif code in valid_25:
            discount_percent = 25
        elif code in valid_10:
            discount_percent = 10
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
    cart = session.get('cart', [])
    cart_dict = {item['id']: item['quantity'] for item in cart}
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

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# UPDATED ROUTE: Send VARIANT in webhook payload
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
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

    # ✅ Generate a unique order ID
    order_id = str(uuid.uuid4())

    # Prepare webhook payload — INCLUDE VARIANT FOR EACH ITEM
    webhook_payload = {
        "id": order_id,
        "payment": 'False',
        "personal_details": {
            "full_name": full_name,
            "address": address,
            "city": city,
            "postal_code": postal_code,
            "phone": phone
        },
        "order": {
            "items": [
                {
                    "id": item['id'],
                    "name": item['name'],
                    "price": item['price'],
                    "quantity": item['quantity'],
                    "total_price": item['price'] * item['quantity'],
                    "variant": item.get('variant')  # <-- SEND VARIANT IF EXISTS
                }
                for item in cart_items
            ],
            "subtotal": subtotal,
            "total": total,
            "currency": "INR"
        }
    }

    # Send to webhook
    webhook_url = 'http://n8n-x0owwcgwcg4s4o8w4g80g4go.93.127.185.52.sslip.io/webhook/demo'
    if webhook_url:
        try:
            response = requests.post(
                webhook_url,
                json=webhook_payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code not in (200, 201, 202, 204):
                app.logger.warning(f"Webhook returned {response.status_code}: {response.text}")
        except Exception as e:
            app.logger.error(f"Webhook delivery failed: {str(e)}")
    else:
        app.logger.warning("WEBHOOK_URL not set – skipping webhook")

    # Store in session
    session['personal_details'] = {
        'full_name': full_name,
        'address': address,
        'city': city,
        'postal_code': postal_code,
        'phone': phone
    }
    session.modified = True

    return redirect(url_for('payment'))
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

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

# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# PAYMENT SUCCESS HANDLER
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
@app.route('/payment/success', methods=['POST'])
def payment_success():
    try:
        data = request.get_json()
        if not data or 'razorpay_payment_id' not in data:
            app.logger.warning("Invalid payment success payload")
            return jsonify({'success': False}), 400
        session.pop('cart', None)
        session.pop('personal_details', None)
        session.modified = True
        return jsonify({'success': True}), 200
    except Exception as e:
        app.logger.error(f"Payment success handler error: {str(e)}")
        return jsonify({'success': False}), 500
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

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
# DEVELOPMENT SERVER
# ======================
if __name__ == '__main__':
    if IS_DEV and not os.path.exists('products.json'):
        sample_products = [
            {"id": 1, "name": "Wireless Earbuds", "price": 2499, "image": "https://via.placeholder.com/150/92c952?text=Earbuds", "description": "Bluetooth 5.3, 30hr battery, IPX7 waterproof", "variants": [{"color": "Black", "size": "Standard"}, {"color": "White", "size": "Standard"}]},
            {"id": 2, "name": "Smart Watch", "price": 4999, "image": "https://via.placeholder.com/150/771796?text=Watch", "description": "Heart rate monitor, GPS, 7-day battery", "variants": [{"color": "Silver", "size": "42mm"}, {"color": "Black", "size": "46mm"}]},
            {"id": 3, "name": "Laptop Sleeve", "price": 899, "image": "https://via.placeholder.com/150/d32776?text=Sleeve", "description": "Water-resistant, fits 15-inch laptops", "variants": [{"color": "Navy", "size": "13-inch"}, {"color": "Gray", "size": "15-inch"}]}
        ]
        with open('products.json', 'w') as f:
            json.dump(sample_products, f, indent=2)
        print("✓ Created sample products.json", file=sys.stderr)

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