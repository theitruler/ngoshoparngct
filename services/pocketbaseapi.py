import os
from pocketbase import PocketBase

# ======================
# POCKETBASE CONFIGURATION
# ======================
PB_URL = os.getenv("PB_URL", "https://db.arngct.org")
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
        except Exception:
            pass # Silent fail for auth to keep logs clean
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
                
                product = {
                    'id': str(item.id),
                    'name': data.get('name', 'Unknown Product'),
                    'price': float(data.get('price', 0)),
                    'description': data.get('description', '') or '',
                    'images': normalize_images(data.get('image'), item.id, item.collection_name),
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
    except Exception:
        return []

def normalize_images(image_field_data, record_id, collection_id):
    """
    Converts PocketBase filenames into full HTTPS URLs.
    No logging included.
    """
    result = []
    
    if not image_field_data:
        return ['/static/placeholder.png']
        
    if isinstance(image_field_data, str):
        image_field_data = [image_field_data]
        
    if isinstance(image_field_data, list):
        for filename in image_field_data:
            if not isinstance(filename, str) or not filename.strip():
                continue
                
            filename = filename.strip()
            
            if filename.startswith(('http://', 'https://')):
                url = filename.replace('http://', 'https://')
                result.append(url)
            else:
                full_url = f"{PB_URL.rstrip('/')}/api/files/{collection_id}/{record_id}/{filename}"
                result.append(full_url)
                
    return result if result else ['/static/placeholder.png']