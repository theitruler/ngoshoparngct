import os
from pocketbase import PocketBase

# ======================
# POCKETBASE CONFIGURATION
# ======================
PB_URL = os.getenv("PB_URL", "http://pocketbase-yco4cwww4c0scwksss4kgk08.93.127.185.52.sslip.io")
ADMIN_EMAIL = os.getenv("PB_ADMIN_EMAIL", "ashishrajams@gmail.com")
ADMIN_PASSWORD = os.getenv("PB_ADMIN_PASSWORD", "Ashishrajams@1")
COLLECTION_NAME = "products"

_client = None
_auth_data = None

def get_client():
    """Initializes and returns the PocketBase client."""
    global _client, _auth_data
    if _client is None:
        _client = PocketBase(PB_URL)
        try:
            if not _client.admins.auth_store.token:
                _auth_data = _client.admins.auth_with_password(ADMIN_EMAIL, ADMIN_PASSWORD)
        except Exception as e:
            print(f"⚠️ PocketBase Auth Warning: {str(e)}")
    return _client

def get_all_products():
    """Fetches all products from PocketBase and normalizes the data."""
    client = get_client()
    try:
        collection_service = client.collection(COLLECTION_NAME)
        all_records = []
        page = 1
        per_page = 500
        
        while True:
            response = collection_service.get_list(
                page=page,
                per_page=per_page,
                query_params={"sort": "-created"}
            )
            
            for item in response.items:
                data = vars(item)
                
                # FIX: Keep ID as String. Do NOT convert to int or hash.
                # PocketBase IDs are strings (e.g., "pbc_1234567890abcdef")
                product = {
                    'id': str(item.id), 
                    'name': data.get('name', 'Unknown Product'),
                    'price': float(data.get('price', 0)),
                    'description': data.get('description', '') or '',
                    'images': normalize_images(data.get('images'), data.get('field')),
                    'colors': data.get('colors') if isinstance(data.get('colors'), list) else [],
                    'sizes': data.get('sizes') if isinstance(data.get('sizes'), list) else [],
                    'tags': data.get('tags') if isinstance(data.get('tags'), list) else [],
                    '_pb_id': item.id,
                    '_pb_collection': item.collection_name
                }
                all_records.append(product)
                
            if page >= response.total_pages:
                break
            page += 1
            
        return all_records
    except Exception as e:
        print(f"❌ ERROR fetching products from PocketBase: {str(e)}")
        return []

def normalize_images(images_data, field_data):
    """Ensures we always return a list of valid image URLs."""
    result = []
    source = images_data
    
    if not source and field_data:
        source = field_data
        
    if not source:
        return ['/static/placeholder.png']
        
    if isinstance(source, str):
        source = [source]
        
    if isinstance(source, list):
        for item in source:
            if isinstance(item, str):
                url = item.strip()
                # If it's not a full URL, you might need to construct it here
                # assuming your PB stores filenames in 'field' and URLs in 'images'
                if not url.startswith(('http://', 'https://')):
                    # Skip non-URLs for now unless you have logic to build the full path
                    continue 
                result.append(url)
                
    return result if result else ['/static/placeholder.png']