#!/usr/bin/env python3
"""
Genera dati sample per MongoDB basati su schema
"""
import json
from datetime import datetime, timedelta
import random

# ========================================
# HOTELS (20 documenti)
# ========================================
cities_italy = ["Milano", "Roma", "Firenze", "Venezia", "Napoli", "Torino", "Bologna"]

hotels = []
for i in range(1, 21):
    city = random.choice(cities_italy)
    hotels.append({
        "_id": f"hotel_{i:03d}",
        "name": f"Hotel {['Grand', 'Luxury', 'Royal', 'Palace', 'Imperial'][i % 5]} {city}",
        "location": {
            "city": city,
            "country": "Italy",
            "address": f"Via Roma {i}",
            "coordinates": {
                "lat": round(41 + random.uniform(0, 4), 6),
                "lng": round(9 + random.uniform(0, 5), 6)
            }
        },
        "rating": round(random.uniform(3.0, 5.0), 1),
        "price_per_night": random.choice([80, 100, 120, 150, 200, 250, 300]),
        "stars": random.randint(3, 5),
        "amenities": random.sample(["wifi", "parking", "pool", "gym", "spa", "restaurant"], k=random.randint(2, 5)),
        "rooms": random.randint(50, 200),
        "available": random.choice([True, True, True, False]),
        "parking": random.choice([True, False]),
        "wifi": random.choice([True, True, True, False]),
        "breakfast_included": random.choice([True, False])
    })

# ========================================
# PRODUCTS (30 documenti)
# ========================================
categories = ["electronics", "clothing", "books", "food", "sports"]
brands = ["Samsung", "Apple", "Sony", "Dell", "HP", "Nike", "Adidas"]

products = []
for i in range(1, 31):
    cat = random.choice(categories)
    products.append({
        "_id": f"prod_{i:03d}",
        "name": f"Product {cat.title()} {i}",
        "category": cat,
        "price": round(random.uniform(20, 2000), 2),
        "stock": random.randint(0, 100),
        "brand": random.choice(brands) if cat == "electronics" else None,
        "discount": random.choice([0, 5, 10, 15, 20, 25, 30]),
        "rating": round(random.uniform(3.0, 5.0), 1),
        "organic": random.choice([True, False]) if cat == "food" else False,
        "description": f"High quality {cat} product",
        "reviews": [
            {"user": f"user_{j:03d}", "rating": random.randint(3, 5), "comment": "Great product"}
            for j in range(random.randint(0, 5))
        ]
    })

# ========================================
# USERS (25 documenti)
# ========================================
users = []
for i in range(1, 26):
    city = random.choice(cities_italy)
    registration_date = datetime.now() - timedelta(days=random.randint(1, 365))
    
    users.append({
        "_id": f"user_{i:03d}",
        "name": f"User {i}",
        "email": f"user{i}@email.com" if random.random() > 0.1 else None,
        "age": random.randint(18, 65),
        "city": city,
        "country": "Italy",
        "premium": random.choice([True, False, False]),
        "active": random.choice([True, True, True, False]),
        "email_verified": random.choice([True, True, False]),
        "phone": f"+39 {random.randint(300, 399)} {random.randint(1000000, 9999999)}" if random.random() > 0.2 else None,
        "registration_date": registration_date.strftime("%Y-%m-%d"),
        "orders": [f"order_{j:03d}" for j in range(random.randint(0, 10))]
    })

# ========================================
# ORDERS (20 documenti)
# ========================================
statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
priorities = ["low", "normal", "high", "urgent"]

orders = []
for i in range(1, 21):
    order_date = datetime.now() - timedelta(days=random.randint(1, 90))
    
    orders.append({
        "_id": f"order_{i:03d}",
        "user_id": f"user_{random.randint(1, 25):03d}",
        "total": round(random.uniform(50, 1000), 2),
        "status": random.choice(statuses),
        "items": [
            {"product_id": f"prod_{j:03d}", "quantity": random.randint(1, 3)}
            for j in range(random.randint(1, 5))
        ],
        "shipping_address": f"Via {random.choice(['Roma', 'Milano', 'Venezia'])} {random.randint(1, 100)}",
        "order_date": order_date.strftime("%Y-%m-%d"),
        "tracking_number": f"IT{random.randint(10000000, 99999999)}" if random.random() > 0.3 else None,
        "priority": random.choice(priorities)
    })

# ========================================
# RESTAURANTS (15 documenti)
# ========================================
cuisines = ["Italian", "Japanese", "Chinese", "French", "Mexican"]
price_ranges = ["$", "$$", "$$$", "$$$$"]

restaurants = []
for i in range(1, 16):
    city = random.choice(cities_italy)
    restaurants.append({
        "_id": f"rest_{i:03d}",
        "name": f"Restaurant {random.choice(['La Dolce Vita', 'Il Giardino', 'Bella Napoli', 'Antica Trattoria'])} {i}",
        "city": city,
        "cuisine": random.choice(cuisines),
        "rating": round(random.uniform(3.5, 5.0), 1),
        "price_range": random.choice(price_ranges),
        "status": random.choice(["open", "open", "open", "closed"]),
        "outdoor_seating": random.choice([True, False]),
        "gluten_free_menu": random.choice([True, False])
    })

# ========================================
# SALVA FILE JSON
# ========================================
def save_collection(name, data):
    filename = f"backend/database/data_{name}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Salvato: {filename} ({len(data)} documenti)")

save_collection("hotels", hotels)
save_collection("products", products)
save_collection("users", users)
save_collection("orders", orders)
save_collection("restaurants", restaurants)

print(f"\n📊 TOTALE: {len(hotels) + len(products) + len(users) + len(orders) + len(restaurants)} documenti")
print("\n✅ Dati sample generati!")